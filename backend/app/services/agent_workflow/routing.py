from __future__ import annotations

import asyncio

from app.schemas import AgentFinding
from app.services.agent_workflow.base import AgentContext, available_source_ids


class RoutingAgent:
    name = "Routing Agent"

    async def run(self, context: AgentContext) -> AgentFinding:
        await asyncio.sleep(0)
        request = context.request
        live = context.live_intelligence
        access_risk = 0 if request.emergency_access_route else 20
        evidence = [
            "Emergency access route available"
            if request.emergency_access_route
            else "No confirmed emergency access route"
        ]
        source_ids = ["operator-assessment-inputs"]
        if live and live.alternate_route:
            route = live.alternate_route
            evidence.append(
                f"Suggested detour: {route.distance_km:.1f} km, approximately {route.duration_minutes:.0f} minutes."
            )
            source_ids.append("osrm-routing")
        if live and live.critical_infrastructure:
            evidence.append(f"Mapped critical facilities near assessment: {len(live.critical_infrastructure)}.")
            source_ids.append("openstreetmap-critical-infrastructure")
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary="Response routing and critical-facility exposure were evaluated.",
            evidence=evidence,
            data={"access_risk_score": access_risk},
            source_ids=[source_id for source_id in source_ids if source_id in available_source_ids(live)],
        )
