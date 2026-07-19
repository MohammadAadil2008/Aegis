from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import (
    AgentProgressEvent,
    AssessmentRequest,
    AssessmentResponse,
    AssetInformation,
    IncidentCommanderBrief,
    LiveIntelligence,
    OfficialBridge,
    RiskAssessment,
)
from app.services.agent_workflow.base import AgentContext
from app.services.agent_workflow.workflow import AsyncAgentWorkflow, ProgressCallback
from app.services.agents import AgentContext as LegacyAgentContext
from app.services.agents import ReportGenerator
from app.services.commander import GroqIncidentCommander
from app.services.bridge_analysis import BridgeAnalysisService
from app.services.bridge_catalog import BridgeCatalogService, OfficialBridgeVerificationError
from app.services.action_plan import EmergencyActionPlanBuilder
from app.services.forecast_timeline import ForecastTimelineBuilder
from app.services.groq import GroqNarrativeService, NarrativeDrafts
from app.services.live_data import LiveDataService


class IncidentCoordinator:
    """Runs the asynchronous agent workflow and produces one reviewable assessment."""

    def __init__(
        self,
        narrative_service: GroqNarrativeService | None = None,
        live_data_service: LiveDataService | None = None,
        incident_commander: GroqIncidentCommander | None = None,
        workflow: AsyncAgentWorkflow | None = None,
        timeline_builder: ForecastTimelineBuilder | None = None,
        bridge_analysis_service: BridgeAnalysisService | None = None,
        action_plan_builder: EmergencyActionPlanBuilder | None = None,
        bridge_catalog_service: BridgeCatalogService | None = None,
    ) -> None:
        self._workflow = workflow or AsyncAgentWorkflow()
        self._reporter = ReportGenerator()
        self._narrative_service = narrative_service
        self._live_data_service = live_data_service
        self._incident_commander = incident_commander
        self._timeline_builder = timeline_builder or ForecastTimelineBuilder()
        self._bridge_analysis_service = bridge_analysis_service or BridgeAnalysisService()
        self._action_plan_builder = action_plan_builder or EmergencyActionPlanBuilder()
        self._bridge_catalog_service = bridge_catalog_service

    def assess(self, request: AssessmentRequest) -> AssessmentResponse:
        """Compatibility wrapper for existing synchronous callers and tests."""
        return asyncio.run(self.assess_async(request))

    async def assess_async(
        self, request: AssessmentRequest, publish: ProgressCallback | None = None
    ) -> AssessmentResponse:
        official_bridge = await self._resolve_official_bridge(request)
        effective_request = self._apply_official_bridge(request, official_bridge)
        await self._publish(publish, "Coordinator Agent", "running", "Collecting shared public evidence.")
        live_intelligence = await self._collect_live_data(effective_request, official_bridge)
        effective_request = self._apply_live_weather(effective_request, live_intelligence)
        await self._publish(
            publish,
            "Coordinator Agent",
            "running",
            "Shared evidence ready; launching independent agents.",
        )
        workflow_output = await self._workflow.run(
            AgentContext(request=effective_request, live_intelligence=live_intelligence), publish
        )
        risk = workflow_output.risk
        assessment_live_intelligence = self._attach_assessment_risk(live_intelligence, risk)
        timeline = self._timeline_builder.build(effective_request, risk, assessment_live_intelligence)
        bridge_analysis = self._bridge_analysis_service.build(assessment_live_intelligence, risk)
        emergency_action_plan = self._action_plan_builder.build(
            effective_request, risk, assessment_live_intelligence, bridge_analysis
        )
        fallback_alert = self._reporter.public_alert(LegacyAgentContext(request=effective_request), risk)
        fallback_report = self._reporter.situation_report(LegacyAgentContext(request=effective_request), risk)
        drafts = await asyncio.to_thread(
            self._enrich_drafts,
            effective_request,
            risk,
            fallback_alert,
            fallback_report,
        )
        commander_brief = await asyncio.to_thread(
            self._create_commander_brief,
            effective_request,
            risk,
            workflow_output.findings,
            assessment_live_intelligence,
        )
        return AssessmentResponse(
            assessment_id=str(uuid4()),
            status="human_review_required",
            asset=AssetInformation(
                name=effective_request.asset_name,
                location=effective_request.location,
                condition_score=effective_request.condition_score,
                age_years=effective_request.asset_age_years,
                observed_scour=effective_request.observed_scour,
                emergency_access_route=effective_request.emergency_access_route,
                field_report=effective_request.field_report,
            ),
            official_bridge=official_bridge,
            risk=risk,
            timeline=timeline,
            bridge_analysis=bridge_analysis,
            emergency_action_plan=emergency_action_plan,
            findings=workflow_output.findings,
            public_alert_draft=drafts.public_alert_draft,
            situation_report=drafts.situation_report,
            live_intelligence=assessment_live_intelligence,
            incident_commander=commander_brief,
            demo_scenario=request.demo_scenario,
            narrative_enriched=drafts.enriched,
        )

    async def _collect_live_data(
        self, request: AssessmentRequest, official_bridge: OfficialBridge | None
    ) -> LiveIntelligence | None:
        if not request.use_live_data or self._live_data_service is None:
            return None
        if official_bridge is None:
            return await asyncio.to_thread(self._live_data_service.collect, request)
        return await asyncio.to_thread(self._live_data_service.collect, request, official_bridge)

    async def _resolve_official_bridge(
        self, request: AssessmentRequest
    ) -> OfficialBridge | None:
        if not request.official_bridge_id or self._bridge_catalog_service is None:
            return None
        bridge = await asyncio.to_thread(self._bridge_catalog_service.get, request.official_bridge_id)
        if bridge is None:
            raise OfficialBridgeVerificationError(
                "The selected official bridge record could not be verified. Search and select it again."
            )
        return bridge

    @staticmethod
    def _apply_official_bridge(
        request: AssessmentRequest, official_bridge: OfficialBridge | None
    ) -> AssessmentRequest:
        if official_bridge is None:
            return request
        updates: dict[str, object] = {"asset_name": official_bridge.name}
        if official_bridge.condition_score is not None:
            updates["condition_score"] = official_bridge.condition_score
        if official_bridge.year_built is not None:
            updates["asset_age_years"] = max(
                0, datetime.now(timezone.utc).year - official_bridge.year_built
            )
        return request.model_copy(update=updates)

    @staticmethod
    def _apply_live_weather(
        request: AssessmentRequest, live_intelligence: LiveIntelligence | None
    ) -> AssessmentRequest:
        if request.demo_scenario or live_intelligence is None or live_intelligence.weather is None:
            return request
        weather = live_intelligence.weather
        return request.model_copy(
            update={
                "forecast_rainfall_mm": weather.precipitation_next_24h_mm,
                "forecast_wind_kph": weather.wind_gust_kph,
            }
        )

    @staticmethod
    def _attach_assessment_risk(
        live_intelligence: LiveIntelligence | None, risk: RiskAssessment
    ) -> LiveIntelligence | None:
        if live_intelligence is None or not live_intelligence.bridge_assets:
            return live_intelligence
        assets = list(live_intelligence.bridge_assets)
        assets[0] = assets[0].model_copy(update={"risk_level": risk.risk_level})
        return live_intelligence.model_copy(update={"bridge_assets": assets})

    def _enrich_drafts(
        self,
        request: AssessmentRequest,
        risk: RiskAssessment,
        fallback_alert: str,
        fallback_report: str,
    ) -> NarrativeDrafts:
        if self._narrative_service is None:
            return NarrativeDrafts(fallback_alert, fallback_report, enriched=False)
        return self._narrative_service.enhance(
            asset_name=request.asset_name,
            location=request.location,
            risk=risk,
            fallback_public_alert=fallback_alert,
            fallback_situation_report=fallback_report,
        )

    def _create_commander_brief(
        self,
        request: AssessmentRequest,
        risk: RiskAssessment,
        findings: list,
        live_intelligence: LiveIntelligence | None,
    ) -> IncidentCommanderBrief | None:
        if self._incident_commander is None:
            return None
        return self._incident_commander.generate(
            request=request,
            risk=risk,
            findings=findings,
            live_intelligence=live_intelligence,
        )

    @staticmethod
    async def _publish(
        callback: Callable[[AgentProgressEvent], Awaitable[None]] | None,
        agent: str,
        status: str,
        message: str,
    ) -> None:
        if callback:
            await callback(AgentProgressEvent(agent=agent, status=status, message=message))
