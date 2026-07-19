from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import main
from app.schemas import (
    AssessmentRequest,
    Coordinates,
    FloodScreeningArea,
    LiveIntelligence,
    MapAsset,
    OfficialBridge,
    RoutePlan,
)
from app.services.orchestrator import IncidentCoordinator
from app.services.pdf_report import PdfIncidentReportGenerator
from app.services.report_store import InMemoryReportStore


def _assessment_payload() -> dict[str, object]:
    return {
        "location": "Albany, NY",
        "asset_name": "North River Bridge",
        "field_report": "Floodwater is approaching bridge supports and debris is accumulating upstream.",
        "forecast_rainfall_mm": 95,
        "forecast_wind_kph": 45,
        "river_rise_m": 1.8,
        "condition_score": 48,
        "asset_age_years": 55,
        "observed_scour": True,
        "emergency_access_route": True,
        "use_live_data": False,
    }


def test_pdf_report_contains_core_incident_details() -> None:
    assessment = IncidentCoordinator().assess(AssessmentRequest(**_assessment_payload()))
    document = PdfIncidentReportGenerator().generate(assessment)

    assert document.startswith(b"%PDF")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(document)).pages)
    assert "AEGIS INCIDENT REPORT" in text
    assert assessment.assessment_id in text
    assert "North River Bridge" in text
    assert "Bridge and Risk Analysis" in text
    assert "Data Sources and Known Gaps" in text


def test_pdf_report_includes_the_verified_official_bridge_record() -> None:
    assessment = IncidentCoordinator().assess(AssessmentRequest(**_assessment_payload()))
    official_bridge = OfficialBridge(
        nbi_record_id="123456",
        name="North River Bridge",
        coordinates=Coordinates(latitude=42.6526, longitude=-73.7562),
        year_built=1978,
        condition_score=56,
        average_daily_traffic=12400,
        last_inspection_date="2023-05",
        data_as_of="FHWA NBI 2023 snapshot",
        source_url="https://www.fhwa.dot.gov/bridge/nbi.cfm",
    )
    document = PdfIncidentReportGenerator().generate(
        assessment.model_copy(update={"official_bridge": official_bridge})
    )

    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(document)).pages)
    assert "Official Bridge Record" in text
    assert "123456" in text
    assert "FHWA National Bridge Inventory" in text


def test_completed_assessment_exposes_a_downloadable_pdf(monkeypatch) -> None:
    monkeypatch.setattr(main, "coordinator", IncidentCoordinator())
    monkeypatch.setattr(main, "pdf_reports", InMemoryReportStore())
    client = TestClient(main.app)

    response = client.post("/api/assessments", json=_assessment_payload())

    assert response.status_code == 200
    report_url = response.json()["report_url"]
    assert report_url
    download = client.get(report_url)
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/pdf")
    assert download.content.startswith(b"%PDF")


def test_completed_assessment_persists_audit_snapshot_when_storage_is_configured(monkeypatch) -> None:
    class RecordingAuditStore:
        def __init__(self) -> None:
            self.saved: tuple[AssessmentRequest, object] | None = None

        def persist_assessment(self, request: AssessmentRequest, assessment: object) -> None:
            self.saved = (request, assessment)

    store = RecordingAuditStore()
    monkeypatch.setattr(main, "coordinator", IncidentCoordinator())
    monkeypatch.setattr(main, "pdf_reports", InMemoryReportStore())
    monkeypatch.setattr(main, "audit_store", store)
    client = TestClient(main.app)

    response = client.post("/api/assessments", json=_assessment_payload())

    assert response.status_code == 200
    assert store.saved is not None
    saved_request, saved_assessment = store.saved
    assert saved_request.location == "Albany, NY"
    assert saved_assessment.risk.score == response.json()["risk"]["score"]
    assert saved_assessment.report_url == response.json()["report_url"]


def test_pdf_report_renders_an_operational_map_from_live_evidence() -> None:
    assessment = IncidentCoordinator().assess(AssessmentRequest(**_assessment_payload()))
    location = Coordinates(latitude=42.6526, longitude=-73.7562)
    live = LiveIntelligence(
        enabled=True,
        resolved_location="Albany, New York, United States",
        coordinates=location,
        bridge_assets=[
            MapAsset(name="North River Bridge", coordinates=location, source="Operator-reported asset"),
            MapAsset(
                name="Nearby bridge",
                coordinates=Coordinates(latitude=42.659, longitude=-73.748),
                source="OpenStreetMap bridge feature",
            ),
        ],
        flood_screening=FloodScreeningArea(
            center=location,
            radius_meters=1_500,
            classification="Elevated screening",
            disclaimer="Screening only.",
        ),
        alternate_route=RoutePlan(
            geometry=[
                Coordinates(latitude=42.67, longitude=-73.79),
                Coordinates(latitude=42.6526, longitude=-73.71),
                Coordinates(latitude=42.63, longitude=-73.79),
            ],
            distance_km=8.4,
            duration_minutes=14,
            label="Suggested response detour",
        ),
    )
    document = PdfIncidentReportGenerator().generate(
        assessment.model_copy(update={"live_intelligence": live})
    )

    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(document)).pages)
    assert "OPERATIONAL MAP OVERVIEW" in text
    assert "Alternative Route and Nearby Infrastructure" in text
