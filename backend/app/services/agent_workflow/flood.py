from __future__ import annotations

import asyncio

from app.schemas import AgentFinding
from app.services.agent_workflow.base import AgentContext, available_source_ids


class FloodAgent:
    name = "Flood Agent"

    async def run(self, context: AgentContext) -> AgentFinding:
        await asyncio.sleep(0)
        request = context.request
        live = context.live_intelligence
        flood = live.flood_forecast if live else None
        gauge = live.nearest_gauge if live else None
        flood_risk = min(30, round(request.river_rise_m * 10))
        evidence = [f"Expected river rise: {request.river_rise_m:.1f} m"]
        source_ids = ["operator-assessment-inputs"]
        if flood:
            evidence.append(
                f"Modelled discharge: {flood.river_discharge_m3s:.1f} m3/s; "
                f"seven-day peak: {flood.peak_7day_discharge_m3s:.1f} m3/s."
            )
            source_ids.append("open-meteo-flood")
        if gauge:
            if gauge.stage_ft is not None:
                evidence.append(f"Nearest gauge stage: {gauge.stage_ft:.2f} ft.")
            elif gauge.flow_cfs is not None:
                evidence.append(f"Nearest gauge flow: {gauge.flow_cfs:.0f} cfs.")
            source_ids.append("usgs-water")
        if live and live.flood_screening:
            evidence.append(f"Flood screening: {live.flood_screening.classification}.")
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary="Water-level and flood forecast evidence were evaluated.",
            evidence=evidence,
            data={"flood_risk_score": flood_risk},
            source_ids=[source_id for source_id in source_ids if source_id in available_source_ids(live)],
        )
