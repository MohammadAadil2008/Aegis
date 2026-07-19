from __future__ import annotations

from dataclasses import dataclass

from app.schemas import AgentFinding, AssessmentRequest, RiskAssessment, RiskLevel


def _risk_level(score: int) -> RiskLevel:
    if score >= 80:
        return RiskLevel.CRITICAL
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 35:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


@dataclass(frozen=True)
class AgentContext:
    request: AssessmentRequest


class ResearchAgent:
    name = "Research Agent"

    def run(self, context: AgentContext) -> AgentFinding:
        report = context.request.field_report.lower()
        keywords = [word for word in ("crack", "washout", "flood", "collapse", "scour", "debris") if word in report]
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary="Field report classified for infrastructure warning signals.",
            evidence=[f"Detected report signals: {', '.join(keywords) or 'none'}"],
            data={"detected_signals": keywords},
        )


class WeatherAgent:
    name = "Weather Agent"

    def run(self, context: AgentContext) -> AgentFinding:
        request = context.request
        rainfall_risk = min(35, round(request.forecast_rainfall_mm / 4))
        river_risk = min(30, round(request.river_rise_m * 10))
        wind_risk = min(10, round(request.forecast_wind_kph / 15))
        score = rainfall_risk + river_risk + wind_risk
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary=f"Forecast conditions create a {_risk_level(score).lower()} weather hazard.",
            evidence=[
                f"Forecast rainfall: {request.forecast_rainfall_mm:.0f} mm",
                f"Expected river rise: {request.river_rise_m:.1f} m",
                f"Forecast wind: {request.forecast_wind_kph:.0f} km/h",
            ],
            data={"weather_risk_score": score},
        )


class GISAgent:
    name = "GIS Agent"

    def run(self, context: AgentContext) -> AgentFinding:
        request = context.request
        access_risk = 0 if request.emergency_access_route else 20
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary="Route dependency and flood exposure were prepared for mapping review.",
            evidence=[
                f"Location supplied: {request.location}",
                "Emergency access route available" if request.emergency_access_route else "No confirmed emergency access route",
            ],
            data={"access_risk_score": access_risk},
        )


class InfrastructureAgent:
    name = "Infrastructure Agent"

    def run(self, context: AgentContext) -> AgentFinding:
        request = context.request
        condition_risk = round((100 - request.condition_score) * 0.4)
        age_risk = min(15, round(max(0, request.asset_age_years - 30) / 4))
        scour_risk = 25 if request.observed_scour else 0
        score = min(80, condition_risk + age_risk + scour_risk)
        evidence = [
            f"Condition score: {request.condition_score}/100",
            f"Asset age: {request.asset_age_years} years",
        ]
        if request.observed_scour:
            evidence.append("Observed scour raises foundation failure concern")
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary=f"Structural vulnerability is {_risk_level(score).lower()}.",
            evidence=evidence,
            data={"infrastructure_risk_score": score},
        )


class MedicalAgent:
    name = "Medical Agent"

    def run(self, context: AgentContext) -> AgentFinding:
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary="Medical staging recommendation prepared; no patient data is collected in this MVP.",
            evidence=["Prepare trauma-capable EMS standby for HIGH or CRITICAL risk."],
        )


class DroneAgent:
    name = "Drone Agent"

    def run(self, context: AgentContext) -> AgentFinding:
        return AgentFinding(
            agent=self.name,
            status="review_required",
            summary="A visual inspection mission is recommended if it can be conducted safely and legally.",
            evidence=["Human operator must check airspace, weather, and local authorization."],
        )


class LogisticsAgent:
    name = "Logistics Agent"

    def run(self, context: AgentContext) -> AgentFinding:
        unavailable = not context.request.emergency_access_route
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary="Route continuity reviewed for response staging.",
            evidence=["Identify an alternate crossing before restricting this asset."] if unavailable else ["Primary emergency access is currently reported as available."],
        )


class CommunicationsAgent:
    name = "Communications Agent"

    def run(self, context: AgentContext) -> AgentFinding:
        return AgentFinding(
            agent=self.name,
            status="draft_ready",
            summary="Plain-language public alert draft prepared for human approval.",
            evidence=["No alert is sent automatically."],
        )


class PredictionAgent:
    name = "Risk Assessment Agent"

    def run(self, findings: list[AgentFinding]) -> RiskAssessment:
        values = {finding.agent: finding.data for finding in findings}
        weather = values.get("Weather Agent", {}).get("weather_risk_score", 0)
        infrastructure = values.get("Infrastructure Agent", {}).get("infrastructure_risk_score", 0)
        access = values.get("GIS Agent", {}).get("access_risk_score", 0)
        report_signals = len(values.get("Research Agent", {}).get("detected_signals", [])) * 4
        score = min(100, round(weather * 0.35 + infrastructure * 0.55 + access * 0.1 + report_signals))
        reasons = [
            f"Weather and water conditions contribute {weather}/75 signal points.",
            f"Asset vulnerability contributes {infrastructure}/80 signal points.",
        ]
        if access:
            reasons.append("Emergency access route is not confirmed.")
        level = _risk_level(score)
        actions = {
            RiskLevel.LOW: ["Continue routine observation.", "Reassess if forecast conditions change."],
            RiskLevel.MODERATE: ["Schedule a qualified visual inspection.", "Monitor rainfall and water-level updates."],
            RiskLevel.HIGH: ["Request an urgent engineer assessment.", "Prepare traffic-control and alternate-route plans.", "Stage emergency resources."],
            RiskLevel.CRITICAL: ["Escalate to incident command immediately.", "Consider restriction or closure after authority approval.", "Deploy qualified inspection resources only when safe."],
        }[level]
        return RiskAssessment(
            risk_level=level,
            score=score,
            confidence=55,
            reasons=reasons,
            recommended_actions=actions,
        )


class ReportGenerator:
    name = "Report Generator"

    def public_alert(self, context: AgentContext, risk: RiskAssessment) -> str:
        return (
            f"DRAFT - HUMAN APPROVAL REQUIRED: Elevated infrastructure risk has been identified near "
            f"{context.request.asset_name} in {context.request.location}. Current assessment: "
            f"{risk.risk_level}. Follow official local instructions and avoid restricted areas."
        )

    def situation_report(self, context: AgentContext, risk: RiskAssessment) -> str:
        return (
            f"SITUATION REPORT\nAsset: {context.request.asset_name}\nLocation: {context.request.location}\n"
            f"Risk: {risk.risk_level} ({risk.score}/100, confidence {risk.confidence}%).\n"
            f"Assessment basis: {' '.join(risk.reasons)}\n"
            f"Recommended actions: {' '.join(risk.recommended_actions)}\n"
            "Decision authority: Human review required before any public alert, closure, or dispatch."
        )
