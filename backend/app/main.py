from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.schemas import (
    AgentProgressEvent,
    AssessmentRequest,
    AssessmentResponse,
    BridgeSearchResponse,
    Coordinates,
    EmergencyFeedResponse,
    OperatorDecisionRequest,
    OperatorDecisionResponse,
)
from app.services.audit_store import AuditStoreError, PostgresAuditStore
from app.services.agent_workflow.workflow import ProgressCallback
from app.services.bridge_catalog import BridgeCatalogService, OfficialBridgeVerificationError
from app.services.commander import GroqIncidentCommander
from app.services.emergency_feed import EmergencyFeedService
from app.services.groq import GroqNarrativeService
from app.services.live_data import LiveDataService
from app.services.orchestrator import IncidentCoordinator
from app.services.pdf_report import PdfIncidentReportGenerator
from app.services.report_store import InMemoryReportStore
from app.services.rate_limit import InMemoryRateLimiter

APP_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = APP_ROOT / "frontend"
logger = logging.getLogger(__name__)
load_dotenv(APP_ROOT / ".env")

app = FastAPI(title="Aegis API", version="0.1.0")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

settings = Settings.from_environment()
audit_store = PostgresAuditStore(settings.database_url)
groq = GroqNarrativeService(settings)
incident_commander = GroqIncidentCommander(settings)
pdf_reports = InMemoryReportStore()
pdf_generator = PdfIncidentReportGenerator()
emergency_feed = EmergencyFeedService(settings.ny511_api_key)
rate_limiter = InMemoryRateLimiter()
live_data_service = LiveDataService()
bridge_catalog = BridgeCatalogService(live_data_service)
coordinator = IncidentCoordinator(
    narrative_service=groq,
    live_data_service=live_data_service,
    incident_commander=incident_commander,
    bridge_catalog_service=bridge_catalog,
)


@app.middleware("http")
async def apply_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health", include_in_schema=False)
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/bridges", response_model=BridgeSearchResponse)
async def search_official_bridges(
    request: Request,
    location: str = Query(min_length=3, max_length=160),
) -> BridgeSearchResponse:
    _enforce_rate_limit(request, "bridge-search", limit=12, window_seconds=60)
    return await asyncio.to_thread(bridge_catalog.search, location)


@app.get("/api/emergency-feed", response_model=EmergencyFeedResponse)
async def get_emergency_feed(
    request: Request,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    location: str = Query(min_length=1, max_length=160),
) -> EmergencyFeedResponse:
    _enforce_rate_limit(request, "emergency-feed", limit=30, window_seconds=60)
    return await asyncio.to_thread(
        emergency_feed.collect,
        Coordinates(latitude=latitude, longitude=longitude),
        location,
    )


async def _complete_assessment(
    request: AssessmentRequest, publish: ProgressCallback | None = None
) -> AssessmentResponse:
    assessment = await coordinator.assess_async(request, publish)
    await _publish(publish, "Incident Report Generator", "running", "Creating the incident report PDF.")
    try:
        document = await asyncio.to_thread(pdf_generator.generate, assessment)
        pdf_reports.put(assessment.assessment_id, document)
        completed = assessment.model_copy(
            update={"report_url": f"/api/assessments/{assessment.assessment_id}/report.pdf"}
        )
        await _publish(publish, "Incident Report Generator", "complete", "Incident report is ready for export.")
    except Exception:
        logger.exception("Incident report generation failed for assessment %s", assessment.assessment_id)
        await _publish(publish, "Incident Report Generator", "degraded", "Assessment completed, but the PDF report was unavailable.")
        completed = assessment
    try:
        await asyncio.to_thread(audit_store.persist_assessment, request, completed)
    except AuditStoreError:
        logger.exception("Audit storage failed for assessment %s", assessment.assessment_id)
        raise
    return completed


@app.post("/api/assessments", response_model=AssessmentResponse)
async def create_assessment(
    assessment_request: AssessmentRequest, request: Request
) -> AssessmentResponse:
    _enforce_rate_limit(request, "assessment", limit=8, window_seconds=60)
    try:
        return await _complete_assessment(assessment_request)
    except OfficialBridgeVerificationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AuditStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/assessments/stream")
async def stream_assessment(
    assessment_request: AssessmentRequest, request: Request
) -> StreamingResponse:
    _enforce_rate_limit(request, "assessment", limit=8, window_seconds=60)
    async def event_stream():
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        async def publish(event: AgentProgressEvent) -> None:
            await queue.put({"type": "progress", "progress": event.model_dump(mode="json")})

        async def complete() -> None:
            try:
                assessment = await _complete_assessment(assessment_request, publish)
                await queue.put({"type": "result", "assessment": assessment.model_dump(mode="json")})
            except OfficialBridgeVerificationError as error:
                await queue.put({"type": "error", "message": str(error)})
            except AuditStoreError as error:
                await queue.put({"type": "error", "message": str(error)})
            except Exception:
                logger.exception("Streamed assessment failed.")
                await queue.put(
                    {
                        "type": "error",
                        "message": "The assessment could not be completed. Please try again.",
                    }
                )

        task = asyncio.create_task(complete())
        try:
            while True:
                event = await queue.get()
                yield json.dumps(event) + "\n"
                if event["type"] in {"result", "error"}:
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post(
    "/api/assessments/{assessment_id}/decisions",
    response_model=OperatorDecisionResponse,
    status_code=201,
)
async def record_operator_decision(
    assessment_id: str, decision: OperatorDecisionRequest, request: Request
) -> OperatorDecisionResponse:
    _enforce_rate_limit(request, "operator-decision", limit=20, window_seconds=60)
    try:
        return await asyncio.to_thread(audit_store.record_decision, assessment_id, decision)
    except AuditStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


async def _publish(
    callback: ProgressCallback | None, agent: str, status: str, message: str
) -> None:
    if callback:
        await callback(AgentProgressEvent(agent=agent, status=status, message=message))


@app.get("/api/assessments/{assessment_id}/report.pdf", include_in_schema=False)
def download_incident_report(assessment_id: str) -> Response:
    document = pdf_reports.get(assessment_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Incident report was not found or has expired.")
    return Response(
        content=document,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="aegis-incident-{assessment_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )


def _enforce_rate_limit(
    request: Request, bucket: str, *, limit: int, window_seconds: float
) -> None:
    client_id = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_id, bucket, limit, window_seconds):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before trying again.",
            headers={"Retry-After": str(int(window_seconds))},
        )
