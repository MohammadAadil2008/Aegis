from __future__ import annotations

import asyncio

from app.schemas import AgentFinding
from app.services.agent_workflow.base import AgentContext, available_source_ids


class EmergencyPlanningAgent:
    name = "Emergency Planning Agent"

    async def run(self, context: AgentContext, findings: list[AgentFinding]) -> AgentFinding:
        await asyncio.sleep(0)
        values = {finding.agent: finding.data for finding in findings}
        infrastructure = values.get("Infrastructure Agent", {}).get("infrastructure_risk_score", 0)
        flood = values.get("Flood Agent", {}).get("flood_risk_score", 0)
        access = values.get("Routing Agent", {}).get("access_risk_score", 0)
        actions = ["Confirm incident lead and qualified engineering review."]
        if infrastructure >= 40 or flood >= 15:
            actions.append("Prepare a safe visual inspection plan and traffic-control resources.")
        if access:
            actions.append("Confirm an alternate emergency access route before any restriction decision.")
        else:
            actions.append("Maintain alternate-route readiness in case conditions deteriorate.")
        live = context.live_intelligence
        evidence = [f"Prepared priorities from {len(findings)} completed specialist assessments.", *actions]
        source_ids = ["operator-assessment-inputs", "operator-field-report"]
        for finding in findings:
            source_ids.extend(finding.source_ids)
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary="Initial response priorities were prepared for human incident command review.",
            evidence=evidence,
            data={"prepared_actions": actions},
            source_ids=list(dict.fromkeys(source_id for source_id in source_ids if source_id in available_source_ids(live))),
        )
