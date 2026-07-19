import asyncio
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.schemas import (
    AssessmentRequest,
    CriticalInfrastructureAsset,
    CitedStatement,
    Coordinates,
    DailyDischargeForecast,
    EvidenceSource,
    EmergencyFeedResponse,
    FloodForecast,
    FloodScreeningArea,
    GaugeReading,
    LiveIntelligence,
    RiskAssessment,
    RiskLevel,
    MapAsset,
    OfficialBridge,
    WeatherForecastWindow,
    WeatherSnapshot,
)
from app.services.commander import GroqIncidentCommander, _CommanderPayload
from app.services.agent_workflow.base import AgentContext
from app.services.agent_workflow.workflow import AsyncAgentWorkflow
from app.services.emergency_feed import EmergencyFeedService
from app.services.bridge_analysis import BridgeAnalysisService
from app.services.bridge_catalog import BridgeCatalogService, OfficialBridgeVerificationError
from app.services.rate_limit import InMemoryRateLimiter
from app.services.groq import GroqNarrativeService, NarrativeDrafts
from app.services.live_data import LiveDataService
from app.services.orchestrator import IncidentCoordinator


def test_critical_conditions_escalate_to_critical_risk() -> None:
    result = IncidentCoordinator().assess(
        AssessmentRequest(
            location="Albany, NY",
            asset_name="Hudson Crossing",
            field_report="Flood debris, collapse concerns, and visible scour near bridge foundation.",
            forecast_rainfall_mm=160,
            forecast_wind_kph=75,
            river_rise_m=2.8,
            condition_score=20,
            asset_age_years=80,
            observed_scour=True,
            emergency_access_route=False,
        )
    )

    assert result.risk.risk_level is RiskLevel.CRITICAL
    assert result.human_review_required is True
    assert [finding.agent for finding in result.findings] == [
        "Weather Agent",
        "Flood Agent",
        "Infrastructure Agent",
        "Routing Agent",
        "Emergency Planning Agent",
        "Coordinator Agent",
    ]


def test_low_conditions_remain_low_risk() -> None:
    result = IncidentCoordinator().assess(
        AssessmentRequest(
            location="Albany, NY",
            asset_name="Pine Creek Bridge",
            field_report="Routine observation completed with no visible defects.",
            forecast_rainfall_mm=5,
            condition_score=95,
            asset_age_years=8,
        )
    )

    assert result.risk.risk_level is RiskLevel.LOW


def test_risk_explanation_is_traceable_and_matches_the_score() -> None:
    result = IncidentCoordinator().assess(
        AssessmentRequest(
            location="Albany, NY",
            asset_name="Pine Creek Bridge",
            field_report="Flood debris is accumulating near the foundation.",
            forecast_rainfall_mm=95,
            forecast_wind_kph=45,
            river_rise_m=1.8,
            condition_score=48,
            asset_age_years=55,
            observed_scour=True,
            emergency_access_route=False,
            use_live_data=False,
        )
    )

    explanation = result.risk.explanation
    assert sum(component.points for component in explanation.score_components) == result.risk.score
    assert explanation.missing_data
    assert explanation.confidence_rationale is not None
    known_sources = {
        "operator-field-report",
        "operator-assessment-inputs",
        "aegis-risk-model",
    }
    statements = (
        explanation.positive_evidence
        + explanation.negative_evidence
        + [explanation.confidence_rationale]
    )
    for statement in statements:
        assert statement.source_ids
        assert set(statement.source_ids).issubset(known_sources)


def test_forecast_timeline_distinguishes_observations_from_forecasts() -> None:
    live = LiveIntelligence(
        enabled=True,
        weather=WeatherSnapshot(
            source="Test weather source",
            observed_at="2026-07-18T10:00",
            weather_code=61,
            precipitation_next_24h_mm=44,
            wind_gust_kph=58,
            forecast_windows=[
                WeatherForecastWindow(hours_ahead=2, forecast_end="2026-07-18T12:00", precipitation_mm=4, wind_gust_kph=30),
                WeatherForecastWindow(hours_ahead=6, forecast_end="2026-07-18T16:00", precipitation_mm=14, wind_gust_kph=42),
                WeatherForecastWindow(hours_ahead=12, forecast_end="2026-07-18T22:00", precipitation_mm=27, wind_gust_kph=50),
                WeatherForecastWindow(hours_ahead=24, forecast_end="2026-07-19T10:00", precipitation_mm=44, wind_gust_kph=58),
            ],
        ),
        flood_forecast=FloodForecast(
            source="Test flood source",
            forecast_start="2026-07-18",
            river_discharge_m3s=122,
            peak_7day_discharge_m3s=320,
            daily_discharge=[
                DailyDischargeForecast(forecast_date="2026-07-18", discharge_m3s=122, peak_discharge_m3s=280)
            ],
        ),
        nearest_gauge=GaugeReading(
            site_id="test-gauge",
            site_name="Test gauge",
            coordinates=Coordinates(latitude=42.65, longitude=-73.75),
            observed_at="2026-07-18T10:00",
            stage_ft=7.2,
        ),
        sources=[
            EvidenceSource(id="open-meteo-weather", label="Weather", provider="Test weather source"),
            EvidenceSource(id="open-meteo-flood", label="Flood", provider="Test flood source"),
            EvidenceSource(id="usgs-water", label="Gauge", provider="USGS"),
        ],
    )
    result = IncidentCoordinator(live_data_service=StaticLiveDataService(live)).assess(
        AssessmentRequest(
            location="Albany, NY",
            asset_name="Pine Creek Bridge",
            field_report="Flood debris is accumulating near the foundation.",
            forecast_rainfall_mm=0,
            condition_score=48,
            asset_age_years=55,
        )
    )

    assert [entry.label for entry in result.timeline] == ["Now", "2 hours", "6 hours", "12 hours", "24 hours"]
    assert result.timeline[0].kind == "observation"
    assert all(entry.kind == "forecast" for entry in result.timeline[1:])
    assert "Observation:" in result.timeline[0].weather.text
    assert "No sub-daily river-discharge forecast" in result.timeline[1].river_level.text
    assert "Forecast:" in result.timeline[-1].river_level.text
    assert "does not predict bridge failure" in result.timeline[-1].bridge_status.text
    assert any("contextual evidence only" in item for item in result.risk.explanation.missing_data)
    known_sources = {"operator-field-report", "operator-assessment-inputs", "aegis-risk-model", "open-meteo-weather", "open-meteo-flood", "usgs-water"}
    for entry in result.timeline:
        for statement in (entry.weather, entry.river_level, entry.flood_risk, entry.bridge_status, entry.recommended_action):
            assert set(statement.source_ids).issubset(known_sources)


def test_disabled_groq_service_returns_deterministic_drafts() -> None:
    fallback_alert = "DRAFT - HUMAN APPROVAL REQUIRED: Deterministic alert."
    fallback_report = "SITUATION REPORT\nDecision authority: Human review required before any public alert, closure, or dispatch."
    result = GroqNarrativeService(
        Settings(groq_api_key=None, groq_model=None, enable_groq_enrichment=False)
    ).enhance(
        asset_name="Pine Creek Bridge",
        location="Albany, NY",
        risk=RiskAssessment(
            risk_level=RiskLevel.LOW,
            score=10,
            confidence=55,
            reasons=["Low risk."],
            recommended_actions=["Observe."],
        ),
        fallback_public_alert=fallback_alert,
        fallback_situation_report=fallback_report,
    )

    assert result == NarrativeDrafts(fallback_alert, fallback_report, enriched=False)


class StubLiveDataService:
    def collect(self, request: AssessmentRequest) -> LiveIntelligence:
        return LiveIntelligence(
            enabled=True,
            resolved_location="Albany, New York, United States",
            coordinates=Coordinates(latitude=42.6526, longitude=-73.7562),
            weather=WeatherSnapshot(
                source="Test weather source",
                precipitation_next_24h_mm=140,
                wind_gust_kph=70,
            ),
        )


class StaticLiveDataService:
    def __init__(self, intelligence: LiveIntelligence) -> None:
        self._intelligence = intelligence

    def collect(self, request: AssessmentRequest) -> LiveIntelligence:
        return self._intelligence


def test_live_weather_replaces_manual_weather_inputs() -> None:
    result = IncidentCoordinator(live_data_service=StubLiveDataService()).assess(
        AssessmentRequest(
            location="Albany, NY",
            asset_name="Pine Creek Bridge",
            field_report="Routine observation completed with no visible defects.",
            forecast_rainfall_mm=0,
            condition_score=95,
            asset_age_years=8,
        )
    )

    weather_finding = next(item for item in result.findings if item.agent == "Weather Agent")
    assert "Forecast rainfall: 140 mm" in weather_finding.evidence
    assert "Live weather forecast was used for the next 24 hours." in weather_finding.evidence
    assert result.live_intelligence is not None
    assert result.live_intelligence.weather is not None


def test_location_cache_rebinds_evidence_to_the_current_asset() -> None:
    service = LiveDataService()
    coordinates = Coordinates(latitude=42.6526, longitude=-73.7562)
    service._cache_result(
        "albany, ny",
        LiveIntelligence(
            enabled=True,
            bridge_assets=[
                MapAsset(
                    name="Previously assessed bridge",
                    coordinates=coordinates,
                    source="City-level assessment location; asset coordinates not verified",
                )
            ],
        ),
    )

    result = service.collect(
        AssessmentRequest(
            location=" Albany,  NY ",
            asset_name="Current assessment bridge",
            field_report="Routine observation completed with no visible defects.",
            forecast_rainfall_mm=5,
            condition_score=95,
            asset_age_years=8,
        )
    )

    assert result.bridge_assets[0].name == "Current assessment bridge"
    assert "asset coordinates not verified" in result.bridge_assets[0].source
    assert any("city-level location" in warning for warning in result.warnings)


def test_live_collection_isolates_an_unexpected_provider_failure(monkeypatch) -> None:
    service = LiveDataService()
    coordinates = Coordinates(latitude=42.6526, longitude=-73.7562)
    monkeypatch.setattr(service, "_geocode", lambda location: ("Albany, New York", coordinates))

    def fail_weather(_coordinates):
        raise RuntimeError("unexpected provider payload")

    monkeypatch.setattr(service, "_weather", fail_weather)
    for method_name in (
        "_flood_forecast",
        "_nearest_gauge",
        "_alternate_route",
        "_weather_alerts",
        "_recent_earthquakes",
        "_terrain",
    ):
        monkeypatch.setattr(service, method_name, lambda _coordinates: None)
    monkeypatch.setattr(service, "_nearby_bridges", lambda _coordinates: [])
    monkeypatch.setattr(service, "_nearby_critical_infrastructure", lambda _coordinates: [])
    monkeypatch.setattr(service, "_radar_layer", lambda: None)

    result = service.collect(
        AssessmentRequest(
            location="Albany, NY",
            asset_name="Current assessment bridge",
            field_report="Routine observation completed with no visible defects.",
            forecast_rainfall_mm=5,
            condition_score=95,
            asset_age_years=8,
        )
    )

    assert result.enabled is True
    assert result.weather is None
    assert any("Live weather was unavailable" in warning for warning in result.warnings)


def test_fhwa_bridge_catalog_parses_real_record_fields_defensively() -> None:
    bridge = BridgeCatalogService._to_bridge(
        {
            "attributes": {
                "fid": 123456,
                "structure_": "000012345678900",
                "facility_c": "HUDSON AVENUE",
                "location_0": "OVER HUDSON RIVER",
                "route_numb": "NY 32",
                "year_built": 1978,
                "deck_cond_": "6",
                "superstruc": "7",
                "substructu": "5",
                "adt_029": 12400,
                "year_adt_0": 2023,
                "date_of_in": "20230512",
                "date": "20230615",
            },
            "geometry": {"x": -73.7562, "y": 42.6526},
        }
    )

    assert bridge is not None
    assert bridge.nbi_record_id == "123456"
    assert bridge.coordinates == Coordinates(latitude=42.6526, longitude=-73.7562)
    assert bridge.condition_score == 56
    assert bridge.average_daily_traffic == 12400
    assert bridge.year_built == 1978
    assert bridge.last_inspection_date == "2023-05"


def test_official_bridge_record_overrides_browser_metadata_before_scoring() -> None:
    official_bridge = OfficialBridge(
        nbi_record_id="123456",
        name="Hudson Avenue Bridge",
        coordinates=Coordinates(latitude=42.6526, longitude=-73.7562),
        year_built=1978,
        condition_score=56,
        source_url="https://www.fhwa.dot.gov/bridge/nbi.cfm",
    )

    class StubBridgeCatalog:
        def get(self, bridge_id: str) -> OfficialBridge | None:
            assert bridge_id == "123456"
            return official_bridge

    class CapturingLiveData:
        def __init__(self) -> None:
            self.request: AssessmentRequest | None = None
            self.official_bridge: OfficialBridge | None = None

        def collect(
            self, request: AssessmentRequest, bridge: OfficialBridge | None = None
        ) -> LiveIntelligence:
            self.request = request
            self.official_bridge = bridge
            return LiveIntelligence(enabled=True, coordinates=official_bridge.coordinates)

    live_data = CapturingLiveData()
    result = IncidentCoordinator(
        live_data_service=live_data, bridge_catalog_service=StubBridgeCatalog()
    ).assess(
        AssessmentRequest(
            location="Albany, NY",
            asset_name="Browser-edited bridge name",
            official_bridge_id="123456",
            field_report="Routine observation completed with no visible defects.",
            forecast_rainfall_mm=0,
            condition_score=1,
            asset_age_years=1,
        )
    )

    assert live_data.request is not None
    assert live_data.request.asset_name == "Hudson Avenue Bridge"
    assert live_data.request.condition_score == 56
    assert live_data.request.asset_age_years == datetime.now(timezone.utc).year - 1978
    assert live_data.official_bridge == official_bridge
    assert result.official_bridge == official_bridge
    assert result.asset.name == "Hudson Avenue Bridge"


def test_selected_official_bridge_must_be_reverified_before_scoring() -> None:
    class MissingBridgeCatalog:
        def get(self, bridge_id: str) -> None:
            return None

    coordinator = IncidentCoordinator(bridge_catalog_service=MissingBridgeCatalog())
    with pytest.raises(OfficialBridgeVerificationError, match="could not be verified"):
        coordinator.assess(
            AssessmentRequest(
                location="Albany, NY",
                asset_name="Browser-edited bridge name",
                official_bridge_id="123456",
                field_report="Routine observation completed with no visible defects.",
                forecast_rainfall_mm=0,
                condition_score=1,
                asset_age_years=1,
            )
        )


def test_bridge_search_endpoint_returns_official_candidates(monkeypatch) -> None:
    official_bridge = OfficialBridge(
        nbi_record_id="123456",
        name="Hudson Avenue Bridge",
        coordinates=Coordinates(latitude=42.6526, longitude=-73.7562),
        source_url="https://www.fhwa.dot.gov/bridge/nbi.cfm",
    )

    class StubBridgeCatalog:
        def search(self, location: str):
            return main.BridgeSearchResponse(
                location="Albany, New York, United States",
                coordinates=official_bridge.coordinates,
                bridges=[official_bridge],
            )

    monkeypatch.setattr(main, "bridge_catalog", StubBridgeCatalog())
    client = TestClient(main.app)
    response = client.get("/api/bridges", params={"location": "Albany, NY"})

    assert response.status_code == 200
    assert response.json()["bridges"][0]["nbi_record_id"] == "123456"


def test_disabled_incident_commander_returns_source_cited_fallback() -> None:
    commander = GroqIncidentCommander(
        Settings(groq_api_key=None, groq_model=None, enable_groq_enrichment=False)
    )
    live = LiveIntelligence(
        enabled=True,
        sources=[
            EvidenceSource(
                id="open-meteo-weather",
                label="Forecast weather",
                provider="Open-Meteo forecast",
            )
        ],
        warnings=["No nearby USGS gauge reading was available."],
    )
    result = IncidentCoordinator(
        live_data_service=StaticLiveDataService(live), incident_commander=commander
    ).assess(
        AssessmentRequest(
            location="Albany, NY",
            asset_name="Pine Creek Bridge",
            field_report="Routine observation completed with no visible defects.",
            forecast_rainfall_mm=5,
            condition_score=95,
            asset_age_years=8,
        )
    )

    assert result.incident_commander is not None
    assert result.incident_commander.available is False
    assert result.incident_commander.risk_level is result.risk.risk_level
    assert result.incident_commander.warning is not None
    known_sources = {"operator-field-report", "operator-assessment-inputs", "aegis-risk-model", "open-meteo-weather"}
    statements = (
        result.incident_commander.reasoning
        + result.incident_commander.recommended_actions
        + result.incident_commander.immediate_priorities
        + result.incident_commander.long_term_recommendations
    )
    for statement in statements:
        assert statement.source_ids
        assert set(statement.source_ids).issubset(known_sources)


def test_incident_commander_rejects_unknown_source_citations() -> None:
    risk = RiskAssessment(
        risk_level=RiskLevel.LOW,
        score=10,
        confidence=55,
        reasons=["Low risk."],
        recommended_actions=["Observe."],
    )
    payload = _CommanderPayload(
        executive_summary="Assessment summary.",
        risk_level=RiskLevel.LOW,
        confidence_score=55,
        reasoning=[CitedStatement(text="Reason", source_ids=["unknown-source"])],
        recommended_actions=[CitedStatement(text="Action", source_ids=["unknown-source"])],
        immediate_priorities=[CitedStatement(text="Priority", source_ids=["unknown-source"])],
        long_term_recommendations=[CitedStatement(text="Long term", source_ids=["unknown-source"])],
        data_gaps=[],
    )

    with pytest.raises(ValueError, match="unavailable source"):
        GroqIncidentCommander._validate_payload(
            payload,
            risk,
            [
                EvidenceSource(
                    id="aegis-risk-model",
                    label="Deterministic Aegis risk model",
                    provider="Aegis",
                )
            ],
            None,
        )


def test_async_workflow_recovers_when_an_independent_agent_fails() -> None:
    class FailingAgent:
        name = "Failing Agent"

        async def run(self, context: AgentContext):
            raise RuntimeError("simulated source failure")

    workflow = AsyncAgentWorkflow()
    workflow._independent_agents = [FailingAgent()]  # type: ignore[list-item]
    events = []

    async def publish(event):
        events.append(event)

    output = asyncio.run(
        workflow.run(
            AgentContext(
                request=AssessmentRequest(
                    location="Albany, NY",
                    asset_name="Pine Creek Bridge",
                    field_report="Routine observation completed with no visible defects.",
                    forecast_rainfall_mm=5,
                    condition_score=95,
                    asset_age_years=8,
                ),
                live_intelligence=None,
            ),
            publish,
        )
    )

    assert output.findings[0].status == "degraded"
    assert output.findings[-1].agent == "Coordinator Agent"
    assert any(event.agent == "Failing Agent" and event.status == "degraded" for event in events)


def test_stream_endpoint_emits_agent_progress_and_a_result(monkeypatch) -> None:
    monkeypatch.setattr(main, "coordinator", IncidentCoordinator())
    client = TestClient(main.app)
    response = client.post(
        "/api/assessments/stream",
        json={
            "location": "Albany, NY",
            "asset_name": "Pine Creek Bridge",
            "field_report": "Routine observation completed with no visible defects.",
            "forecast_rainfall_mm": 5,
            "condition_score": 95,
            "asset_age_years": 8,
            "use_live_data": False,
        },
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line]
    progress_agents = {event["progress"]["agent"] for event in events if event["type"] == "progress"}
    assert {"Weather Agent", "Flood Agent", "Infrastructure Agent", "Routing Agent", "Coordinator Agent"}.issubset(progress_agents)
    assert events[-1]["type"] == "result"


def test_emergency_feed_keeps_verified_alerts_separate_from_source_limits(monkeypatch) -> None:
    service = EmergencyFeedService()

    def fake_request(url: str, **params):
        assert "weather.gov" in url
        return {
            "features": [
                {
                    "properties": {
                        "id": "flood-1",
                        "event": "Flood Warning",
                        "headline": "Flooding is expected near the river.",
                        "severity": "Severe",
                        "sent": "2026-07-18T10:00:00+00:00",
                        "@id": "https://api.weather.gov/alerts/flood-1",
                    }
                },
                {
                    "properties": {
                        "id": "weather-1",
                        "event": "Wind Advisory",
                        "headline": "Strong winds are expected.",
                    }
                },
            ]
        }

    monkeypatch.setattr(service, "_request_json", fake_request)
    feed = service.collect(Coordinates(latitude=42.65, longitude=-73.75), "Albany, NY")

    assert [alert.category for alert in feed.alerts] == ["flood", "weather"]
    assert all(alert.verified for alert in feed.alerts)
    assert all(alert.source_name == "National Weather Service" for alert in feed.alerts)
    assert any("NY511_API_KEY" in warning for warning in feed.warnings)


def test_emergency_feed_endpoint_returns_typed_verified_alerts(monkeypatch) -> None:
    class StubEmergencyFeed:
        def collect(self, coordinates: Coordinates, location: str) -> EmergencyFeedResponse:
            return EmergencyFeedResponse(
                location=location,
                refreshed_at="2026-07-18T10:00:00+00:00",
                alerts=[],
                warnings=["Source refresh test."],
            )

    monkeypatch.setattr(main, "emergency_feed", StubEmergencyFeed())
    client = TestClient(main.app)
    response = client.get(
        "/api/emergency-feed",
        params={"latitude": 42.65, "longitude": -73.75, "location": "Albany, NY"},
    )

    assert response.status_code == 200
    assert response.json()["location"] == "Albany, NY"


def test_bridge_analysis_distinguishes_full_assessment_from_nearby_exposure() -> None:
    assessed = Coordinates(latitude=42.65, longitude=-73.75)
    nearby = Coordinates(latitude=42.655, longitude=-73.75)
    live = LiveIntelligence(
        enabled=True,
        bridge_assets=[
            MapAsset(name="Assessed Bridge", coordinates=assessed, source="Operator location"),
            MapAsset(name="Nearby Bridge", coordinates=nearby, source="OpenStreetMap bridge feature"),
        ],
        flood_screening=FloodScreeningArea(
            center=assessed,
            radius_meters=1_500,
            classification="Elevated screening",
            disclaimer="Screening only.",
        ),
        critical_infrastructure=[
            CriticalInfrastructureAsset(name="Test Hospital", category="hospital", coordinates=nearby, source="OpenStreetMap"),
            CriticalInfrastructureAsset(name="Test School", category="school", coordinates=nearby, source="OpenStreetMap"),
        ],
        sources=[
            EvidenceSource(id="openstreetmap-bridges", label="Bridges", provider="OpenStreetMap"),
            EvidenceSource(id="openstreetmap-critical-infrastructure", label="Facilities", provider="OpenStreetMap"),
        ],
    )
    risk = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        score=71,
        confidence=55,
        reasons=["High screening risk."],
        recommended_actions=["Inspect."],
    )

    analyses = BridgeAnalysisService().build(live, risk)

    assert len(analyses) == 2
    assert analyses[0].risk_scope == "full_assessment"
    assert analyses[0].risk_level is RiskLevel.HIGH
    assert analyses[1].risk_scope == "flood_exposure"
    assert analyses[1].risk_level is RiskLevel.HIGH
    assert analyses[1].nearby_hospitals == 1
    assert analyses[1].nearby_schools == 1
    assert analyses[1].alternative_crossings == 1
    assert "structural condition is unknown" in analyses[1].limitations[1]


def test_emergency_action_plan_separates_observations_and_recommendations() -> None:
    result = IncidentCoordinator().assess(
        AssessmentRequest(
            location="Albany, NY",
            asset_name="Pine Creek Bridge",
            field_report="Flood debris is accumulating near the foundation.",
            forecast_rainfall_mm=95,
            forecast_wind_kph=45,
            river_rise_m=1.8,
            condition_score=48,
            asset_age_years=55,
            observed_scour=True,
            emergency_access_route=False,
            use_live_data=False,
        )
    )

    plan = result.emergency_action_plan
    assert plan is not None
    sections = (
        plan.immediate_actions,
        plan.plan_30_minutes,
        plan.plan_2_hours,
        plan.plan_12_hours,
        plan.public_communication,
        plan.inspection_priorities,
        plan.resource_deployment,
    )
    known_sources = {"operator-field-report", "operator-assessment-inputs", "aegis-risk-model"}
    for section in sections:
        assert section.observations
        assert section.recommendations
        for statement in section.observations + section.recommendations:
            assert statement.source_ids
            assert set(statement.source_ids).issubset(known_sources)


def test_security_headers_are_present_and_health_does_not_expose_feature_state() -> None:
    client = TestClient(main.app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_in_memory_rate_limiter_rejects_requests_over_the_window_limit() -> None:
    limiter = InMemoryRateLimiter()

    assert limiter.allow("127.0.0.1", "assessment", limit=2, window_seconds=60)
    assert limiter.allow("127.0.0.1", "assessment", limit=2, window_seconds=60)
    assert not limiter.allow("127.0.0.1", "assessment", limit=2, window_seconds=60)


def test_commander_payload_excludes_raw_field_report() -> None:
    request = AssessmentRequest(
        location="Albany, NY",
        asset_name="Pine Creek Bridge",
        field_report="Sensitive operator prose that should remain local.",
        forecast_rainfall_mm=5,
        condition_score=95,
        asset_age_years=8,
    )
    risk = RiskAssessment(
        risk_level=RiskLevel.LOW,
        score=10,
        confidence=55,
        reasons=["Low risk."],
        recommended_actions=["Observe."],
    )
    facts = GroqIncidentCommander._facts(
        request,
        risk,
        [],
        None,
        GroqIncidentCommander._source_catalog(None),
    )

    assert "field_report" not in facts["assessment"]
    assert request.field_report not in str(facts)
