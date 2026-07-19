from __future__ import annotations

import asyncio

from app.schemas import (
    AgentFinding,
    CitedStatement,
    RiskAssessment,
    RiskExplanation,
    RiskLevel,
    ScoreComponent,
)
from app.services.agent_workflow.base import AgentContext, available_source_ids


def _risk_level(score: int) -> RiskLevel:
    if score >= 80:
        return RiskLevel.CRITICAL
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 35:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def _unique_source_ids(source_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(source_ids))[:6]


class CoordinatorAgent:
    name = "Coordinator Agent"

    async def run(
        self, context: AgentContext, findings: list[AgentFinding]
    ) -> tuple[RiskAssessment, AgentFinding]:
        await asyncio.sleep(0)
        finding_by_name = {finding.agent: finding for finding in findings}
        values = {finding.agent: finding.data for finding in findings}
        weather = values.get("Weather Agent", {}).get("weather_risk_score", 0)
        flood = values.get("Flood Agent", {}).get("flood_risk_score", 0)
        infrastructure = values.get("Infrastructure Agent", {}).get("infrastructure_risk_score", 0)
        access = values.get("Routing Agent", {}).get("access_risk_score", 0)
        report_signals = len(values.get("Infrastructure Agent", {}).get("report_signals", [])) * 4
        water_and_weather = weather + flood

        # Preserve the established score formula, then reconcile rounded display values to it.
        weighted_contributions = [
            water_and_weather * 0.35,
            infrastructure * 0.55,
            access * 0.1,
            report_signals,
        ]
        score = min(100, round(sum(weighted_contributions)))
        component_points = [round(contribution) for contribution in weighted_contributions]
        rounding_difference = score - sum(component_points)
        for index, points in enumerate(component_points):
            if not rounding_difference:
                break
            adjustment = rounding_difference
            if points + adjustment < 0:
                adjustment = -points
            component_points[index] += adjustment
            rounding_difference -= adjustment

        def sources_for(*agent_names: str) -> list[str]:
            evidence_sources = ["aegis-risk-model"]
            for agent_name in agent_names:
                finding = finding_by_name.get(agent_name)
                if finding:
                    evidence_sources.extend(finding.source_ids)
            return _unique_source_ids(evidence_sources)

        weather_sources = sources_for("Weather Agent", "Flood Agent")
        infrastructure_sources = sources_for("Infrastructure Agent")
        routing_sources = sources_for("Routing Agent")
        field_report_sources = _unique_source_ids(
            ["aegis-risk-model", "operator-field-report", "operator-assessment-inputs"]
        )
        components = [
            ScoreComponent(
                label="Weather and water",
                points=component_points[0],
                max_points=26,
                explanation=(
                    f"Weather and flood signals total {water_and_weather}/75 and add "
                    f"{component_points[0]} point(s) after model weighting."
                ),
                source_ids=weather_sources,
            ),
            ScoreComponent(
                label="Structural vulnerability",
                points=component_points[1],
                max_points=44,
                explanation=(
                    f"Condition, age, and observed scour total {infrastructure}/80 and add "
                    f"{component_points[1]} point(s) after model weighting."
                ),
                source_ids=infrastructure_sources,
            ),
            ScoreComponent(
                label="Emergency access",
                points=component_points[2],
                max_points=2,
                explanation=(
                    "Unconfirmed emergency access adds a small operational penalty."
                    if access
                    else "A reported emergency access route adds no operational penalty."
                ),
                source_ids=routing_sources,
            ),
            ScoreComponent(
                label="Field-report warning signals",
                points=component_points[3],
                max_points=24,
                explanation=(
                    f"{len(values.get('Infrastructure Agent', {}).get('report_signals', []))} detected "
                    "warning signal(s) in the operator field report add "
                    f"{component_points[3]} point(s)."
                ),
                source_ids=field_report_sources,
            ),
        ]
        positive_evidence = [
            CitedStatement(
                text=f"Weather and water evidence increased the score by {component_points[0]} point(s).",
                source_ids=weather_sources,
            )
            for _ in [0]
            if component_points[0]
        ]
        positive_evidence.extend(
            CitedStatement(
                text=f"Structural vulnerability evidence increased the score by {component_points[1]} point(s).",
                source_ids=infrastructure_sources,
            )
            for _ in [0]
            if component_points[1]
        )
        positive_evidence.extend(
            CitedStatement(
                text=f"Emergency-access evidence increased the score by {component_points[2]} point(s).",
                source_ids=routing_sources,
            )
            for _ in [0]
            if component_points[2]
        )
        positive_evidence.extend(
            CitedStatement(
                text=f"Field-report warning signals increased the score by {component_points[3]} point(s).",
                source_ids=field_report_sources,
            )
            for _ in [0]
            if component_points[3]
        )

        negative_evidence: list[CitedStatement] = []
        if context.request.condition_score >= 70:
            negative_evidence.append(
                CitedStatement(
                    text=(
                        f"The reported condition score is {context.request.condition_score}/100, "
                        "which reduces the condition-based structural penalty."
                    ),
                    source_ids=infrastructure_sources,
                )
            )
        if not context.request.observed_scour:
            negative_evidence.append(
                CitedStatement(
                    text="No observed scour was reported, so scour added 0 structural points.",
                    source_ids=field_report_sources,
                )
            )
        if context.request.emergency_access_route:
            negative_evidence.append(
                CitedStatement(
                    text="An emergency access route was reported available, so access added 0 points.",
                    source_ids=routing_sources,
                )
            )

        missing_data = self._missing_data(context)
        explanation = RiskExplanation(
            score_components=components,
            positive_evidence=positive_evidence,
            negative_evidence=negative_evidence,
            confidence_rationale=CitedStatement(
                text=(
                    "Confidence is limited to 55% because this screening model uses current operator "
                    "inputs and available public-source evidence; it is not a structural engineering certification."
                ),
                source_ids=_unique_source_ids(
                    ["aegis-risk-model", "operator-assessment-inputs"]
                ),
            ),
            missing_data=missing_data,
        )
        level = _risk_level(score)
        reasons = [
            f"Weather and water conditions contribute {water_and_weather}/75 signal points.",
            f"Asset vulnerability contributes {infrastructure}/80 signal points.",
        ]
        if access:
            reasons.append("Emergency access route is not confirmed.")
        actions = {
            RiskLevel.LOW: ["Continue routine observation.", "Reassess if forecast conditions change."],
            RiskLevel.MODERATE: ["Schedule a qualified visual inspection.", "Monitor rainfall and water-level updates."],
            RiskLevel.HIGH: ["Request an urgent engineer assessment.", "Prepare traffic-control and alternate-route plans.", "Stage emergency resources."],
            RiskLevel.CRITICAL: ["Escalate to incident command immediately.", "Consider restriction or closure after authority approval.", "Deploy qualified inspection resources only when safe."],
        }[level]
        risk = RiskAssessment(
            risk_level=level,
            score=score,
            confidence=55,
            reasons=reasons,
            recommended_actions=actions,
            explanation=explanation,
        )
        source_ids = ["operator-field-report", "operator-assessment-inputs"]
        for finding in findings:
            source_ids.extend(finding.source_ids)
        finding = AgentFinding(
            agent=self.name,
            status="complete",
            summary=f"Combined {len(findings)} agent outputs into a {level} assessment.",
            evidence=[f"Risk score: {score}/100", "Deterministic risk model remains authoritative."],
            data={"risk_score": score, "risk_level": level.value, "confidence": risk.confidence},
            source_ids=list(
                dict.fromkeys(
                    source_id
                    for source_id in source_ids
                    if source_id in available_source_ids(context.live_intelligence)
                )
            ),
        )
        return risk, finding

    @staticmethod
    def _missing_data(context: AgentContext) -> list[str]:
        live = context.live_intelligence
        if not live or not live.enabled:
            return [
                "Live public-source collection was unavailable or disabled; fallback weather and "
                "operator inputs may have been used."
            ]

        missing: list[str] = list(live.warnings)
        if not live.weather:
            missing.append("Live weather forecast was unavailable; fallback rainfall and wind inputs were used.")
        if not live.flood_forecast:
            missing.append("Live flood forecast was unavailable; the operator river-rise input was used.")
        else:
            missing.append(
                "The live river-discharge forecast is contextual evidence only; Aegis has no "
                "validated local stage/discharge threshold to convert it into bridge-risk points."
            )
        if not live.nearest_gauge:
            missing.append("No nearby river gauge reading was available.")
        if not live.bridge_assets:
            missing.append("No nearby bridge features were returned for map context.")
        if not live.alternate_route:
            missing.append("No alternate route was returned for operational planning.")
        return list(dict.fromkeys(missing))
