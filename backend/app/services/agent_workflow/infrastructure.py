from __future__ import annotations

import asyncio

from app.schemas import AgentFinding
from app.services.agent_workflow.base import AgentContext, available_source_ids


class InfrastructureAgent:
    name = "Infrastructure Agent"

    async def run(self, context: AgentContext) -> AgentFinding:
        await asyncio.sleep(0)
        request = context.request
        report = request.field_report.lower()
        signals = [
            word
            for word in ("crack", "washout", "flood", "collapse", "scour", "debris")
            if word in report
        ]
        condition_risk = round((100 - request.condition_score) * 0.4)
        age_risk = min(15, round(max(0, request.asset_age_years - 30) / 4))
        scour_risk = 25 if request.observed_scour else 0
        score = min(80, condition_risk + age_risk + scour_risk)
        evidence = [
            f"Condition score: {request.condition_score}/100",
            f"Asset age: {request.asset_age_years} years",
            f"Detected field-report signals: {', '.join(signals) or 'none'}",
        ]
        if request.observed_scour:
            evidence.append("Observed scour raises foundation failure concern.")
        live = context.live_intelligence
        if live and live.bridge_assets:
            evidence.append(f"Mapped bridge features near assessment: {len(live.bridge_assets) - 1}.")
        if live and live.seismic_events:
            evidence.append(f"Recent USGS seismic events within 100 km: {len(live.seismic_events)}.")
        source_ids = ["operator-field-report", "operator-assessment-inputs"]
        if live and live.bridge_assets:
            source_ids.append("openstreetmap-bridges")
        if live and live.seismic_events:
            source_ids.append("usgs-earthquakes")
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary="Structural vulnerability and field-report warning signals were evaluated.",
            evidence=evidence,
            data={"infrastructure_risk_score": score, "report_signals": signals},
            source_ids=[source_id for source_id in source_ids if source_id in available_source_ids(live)],
        )
