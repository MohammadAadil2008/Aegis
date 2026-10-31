import json
from types import SimpleNamespace

import groq
import pytest

from app.config import Settings
from app.schemas import AssessmentRequest, Coordinates, EvidenceSource, LiveIntelligence, RiskLevel, RoutePlan
from app.services.commander import GroqIncidentCommander
from app.services.groq import GroqNarrativeService
from app.services.groq_output import failure_code
from app.services.orchestrator import IncidentCoordinator


@pytest.fixture
def assessment():
    request = AssessmentRequest(
        location="Albany, NY", asset_name="Synthetic test bridge",
        field_report="Synthetic verification only. No actual incident reported.",
        forecast_rainfall_mm=0, condition_score=90, asset_age_years=5,
        use_live_data=False, demo_scenario=True,
    )
    result = IncidentCoordinator().assess(request)
    return request, result


def settings():
    return Settings(groq_api_key="fake-test-key", groq_model="openai/gpt-oss-20b",
                    enable_groq_enrichment=True, enable_groq_incident_commander=True)


def mock_completion(monkeypatch, payload, finish_reason="stop", error=None):
    captured = {}

    class FakeGroq:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def create(self, **kwargs):
            captured["request"] = kwargs
            if error:
                raise error
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=json.dumps(payload)),
            )])

    monkeypatch.setattr(groq, "Groq", FakeGroq)
    return captured


def commander_payload(result):
    statement = {"text": "Qualified human review is required.", "source_ids": ["aegis-risk-model"]}
    return dict(executive_summary="Synthetic screening assessment for human review.",
                risk_level=result.risk.risk_level.value, confidence_score=result.risk.confidence,
                reasoning=[statement], recommended_actions=[statement], immediate_priorities=[statement],
                long_term_recommendations=[statement], data_gaps=[])


def generate(assessment, live=None):
    request, result = assessment
    return GroqIncidentCommander(settings()).generate(
        request=request, risk=result.risk, findings=result.findings, live_intelligence=live)


def test_complete_structured_brief_preserves_risk_confidence_and_known_gaps(monkeypatch, assessment):
    captured = mock_completion(monkeypatch, commander_payload(assessment[1]))
    live = LiveIntelligence(enabled=True, warnings=["No nearby gauge observation."], sources=[
        EvidenceSource(id="open-meteo-weather", label="Forecast", provider="Open-Meteo")])
    brief = generate(assessment, live)
    assert brief.available is True
    assert brief.risk_level is assessment[1].risk.risk_level
    assert brief.confidence_score == assessment[1].risk.confidence
    assert "No nearby gauge observation." in brief.data_gaps
    schema = captured["request"]["response_format"]["json_schema"]["schema"]
    assert schema["$defs"]["RiskLevel"]["enum"] == [assessment[1].risk.risk_level.value]
    assert captured["request"]["reasoning_effort"] == "low"
    assert captured["request"]["max_completion_tokens"] == 4096
    assert captured["client"]["timeout"] == 25.0
    assert captured["client"]["max_retries"] == 0


def test_truncated_json_cannot_be_accepted_even_if_it_parses(monkeypatch, assessment):
    mock_completion(monkeypatch, commander_payload(assessment[1]), finish_reason="length")
    brief = generate(assessment)
    assert brief.available is False
    assert brief.warning_code == "incomplete_output"
    assert brief.risk_level is assessment[1].risk.risk_level


@pytest.mark.parametrize("change", ["risk", "confidence", "citation"])
def test_changed_deterministic_values_or_unknown_citations_are_rejected(monkeypatch, assessment, change):
    payload = commander_payload(assessment[1])
    if change == "risk":
        payload["risk_level"] = RiskLevel.CRITICAL.value
    elif change == "confidence":
        payload["confidence_score"] = 99
    else:
        payload["reasoning"][0]["source_ids"] = ["invented-source"]
    mock_completion(monkeypatch, payload)
    brief = generate(assessment)
    assert brief.available is False
    assert brief.warning_code == "invalid_output"


def test_rate_limit_diagnostics_do_not_expose_exception_or_key(monkeypatch, assessment, caplog):
    class Limited(Exception):
        status_code = 429
    mock_completion(monkeypatch, {}, error=Limited("secret-key-and-private-report"))
    brief = generate(assessment)
    assert brief.warning_code == "rate_limited"
    assert "secret-key-and-private-report" not in brief.model_dump_json()
    assert "secret-key-and-private-report" not in caplog.text
    assert "fake-test-key" not in caplog.text


@pytest.mark.parametrize("payload,finish", [({}, "stop"), ({"public_alert_draft": "", "situation_report": ""}, "stop"), ({"public_alert_draft": "Draft.", "situation_report": "Report."}, "length")])
def test_invalid_or_incomplete_narrative_is_not_reported_as_enriched(monkeypatch, assessment, payload, finish):
    mock_completion(monkeypatch, payload, finish_reason=finish)
    drafts = GroqNarrativeService(settings()).enhance(
        asset_name="Synthetic bridge", location="Albany, NY", risk=assessment[1].risk,
        fallback_public_alert="Original alert", fallback_situation_report="Original report")
    assert drafts.enriched is False
    assert drafts.public_alert_draft == "Original alert"


def test_low_risk_fallback_does_not_claim_elevated_risk(assessment):
    assert assessment[1].risk.risk_level is RiskLevel.LOW
    assert "Elevated" not in assessment[1].public_alert_draft
    assert "HUMAN APPROVAL REQUIRED" in assessment[1].public_alert_draft


def test_provider_failure_codes_distinguish_configuration_and_timeout():
    class ConfigurationError(Exception):
        status_code = 400
    assert failure_code(ConfigurationError()) == "provider_configuration"
    assert failure_code(TimeoutError()) == "provider_timeout"


def test_map_geometry_is_excluded_but_route_measurements_and_gaps_are_preserved(assessment):
    live = LiveIntelligence(enabled=True, warnings=["Gauge unavailable."],
        alternate_route=RoutePlan(geometry=[Coordinates(latitude=42,longitude=-73)]*1000,
                                  distance_km=12.3,duration_minutes=20,label="Suggested route"))
    request, result = assessment
    sources = GroqIncidentCommander._source_catalog(live)
    facts = GroqIncidentCommander._facts(request,result.risk,result.findings,live,sources)
    route = facts["live_intelligence"]["alternate_route"]
    assert "geometry" not in route
    assert route["distance_km"] == 12.3
    assert route["duration_minutes"] == 20
    assert facts["live_intelligence"]["warnings"] == ["Gauge unavailable."]
    assert facts["allowed_sources"] == [s.model_dump(mode="json") for s in sources]
    assert len(json.dumps(facts)) < 12000
