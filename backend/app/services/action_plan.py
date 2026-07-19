from __future__ import annotations

from app.schemas import (
    ActionPlanSection,
    AssessmentRequest,
    BridgeAnalysis,
    CitedStatement,
    EmergencyActionPlan,
    LiveIntelligence,
    RiskAssessment,
    RiskLevel,
)


class EmergencyActionPlanBuilder:
    """Builds a bounded operational plan from collected evidence and deterministic risk."""

    def build(
        self,
        request: AssessmentRequest,
        risk: RiskAssessment,
        live: LiveIntelligence | None,
        bridge_analysis: list[BridgeAnalysis],
    ) -> EmergencyActionPlan:
        immediate = ActionPlanSection(
            title="Immediate actions",
            observations=[self._risk_observation(risk, live), self._weather_observation(request, live)],
            recommendations=[
                self._recommendation(
                    self._immediate_action(risk.risk_level), live, "open-meteo-weather", "open-meteo-flood"
                )
            ],
            limitations=["Recommendations require approval by the responsible emergency or infrastructure authority."],
        )
        plan_30 = ActionPlanSection(
            title="30-minute plan",
            observations=[self._flood_observation(request, live), self._route_observation(live)],
            recommendations=[
                self._recommendation(
                    "Refresh official alerts, weather, and gauge evidence; confirm whether the planned response route remains usable.",
                    live,
                    "nws-alerts",
                    "open-meteo-weather",
                    "usgs-water",
                    "osrm-routing",
                )
            ],
            limitations=["Route output is planning context only and is not a verified road-closure status."],
        )
        plan_2h = ActionPlanSection(
            title="2-hour plan",
            observations=[self._condition_observation(request), self._bridge_exposure_observation(bridge_analysis, live)],
            recommendations=[
                self._recommendation(
                    "Arrange qualified inspection only when conditions are safe, and document any new field observations before changing access decisions.",
                    live,
                    "open-meteo-weather",
                    "open-meteo-flood",
                )
            ],
            limitations=["Aegis does not authorize inspections, closures, or field deployment."],
        )
        plan_12h = ActionPlanSection(
            title="12-hour plan",
            observations=[self._forecast_observation(live), self._risk_observation(risk, live)],
            recommendations=[
                self._recommendation(
                    "Re-run the assessment with refreshed public-source and field evidence; compare the updated risk and action plan before continuing any elevated posture.",
                    live,
                    "open-meteo-weather",
                    "open-meteo-flood",
                    "usgs-water",
                )
            ],
            limitations=["The 12-hour plan does not predict structural change or resource availability."],
        )
        public_communication = ActionPlanSection(
            title="Public communication",
            observations=[self._alerts_observation(live)],
            recommendations=[
                self._recommendation(
                    "Use only verified agency alerts and authority-approved language in public communications; treat Aegis text as an internal draft until approved.",
                    live,
                    "nws-alerts",
                )
            ],
            limitations=["Aegis cannot issue public warnings or represent an official agency."],
        )
        inspection = ActionPlanSection(
            title="Inspection priorities",
            observations=[self._condition_observation(request), self._bridge_exposure_observation(bridge_analysis, live)],
            recommendations=[
                self._recommendation(
                    "Prioritize the assessed bridge, then review any nearby bridges with HIGH or CRITICAL flood exposure where qualified personnel can safely access them.",
                    live,
                    "openstreetmap-bridges",
                    "openstreetmap-critical-infrastructure",
                    "open-meteo-flood",
                )
            ],
            limitations=["Nearby bridge exposure is not an inspection result or structural condition rating."],
        )
        resources = ActionPlanSection(
            title="Resource deployment",
            observations=[self._resource_observation(live), self._route_observation(live)],
            recommendations=[
                self._recommendation(
                    "Coordinate any staging, medical, traffic-control, or inspection resources through the responsible agencies after confirming access and safety conditions.",
                    live,
                    "openstreetmap-critical-infrastructure",
                    "osrm-routing",
                )
            ],
            limitations=["No responder availability, inventory, dispatch status, or deployment order is available in this assessment."],
        )
        limits = [
            "This plan is decision support only; human authority approval is required before any dispatch, closure, inspection, or public communication."
        ]
        if live:
            limits.extend(live.warnings)
        else:
            limits.append("No live public-source snapshot was available; the plan relies on operator inputs and the deterministic risk model.")
        return EmergencyActionPlan(
            immediate_actions=immediate,
            plan_30_minutes=plan_30,
            plan_2_hours=plan_2h,
            plan_12_hours=plan_12h,
            public_communication=public_communication,
            inspection_priorities=inspection,
            resource_deployment=resources,
            limitations=list(dict.fromkeys(limits)),
        )

    @staticmethod
    def _source_ids(live: LiveIntelligence | None, *sources: str, model: bool = False) -> list[str]:
        available = {source.id for source in live.sources} if live else set()
        selected = [source for source in sources if source in available]
        if model:
            selected = ["aegis-risk-model", "operator-assessment-inputs", *selected]
        if not selected:
            selected = ["operator-assessment-inputs"]
        return list(dict.fromkeys(selected))[:6]

    def _recommendation(self, text: str, live: LiveIntelligence | None, *sources: str) -> CitedStatement:
        return CitedStatement(text=text, source_ids=self._source_ids(live, *sources, model=True))

    def _risk_observation(self, risk: RiskAssessment, live: LiveIntelligence | None) -> CitedStatement:
        return CitedStatement(
            text=f"Aegis's current deterministic assessment is {risk.risk_level} risk ({risk.score}/100) with {risk.confidence}% model confidence.",
            source_ids=self._source_ids(live, "open-meteo-weather", "open-meteo-flood", "usgs-water", model=True),
        )

    def _weather_observation(self, request: AssessmentRequest, live: LiveIntelligence | None) -> CitedStatement:
        if live and live.weather:
            return CitedStatement(
                text=f"Forecast observation: {live.weather.precipitation_next_24h_mm:.1f} mm precipitation and {live.weather.wind_gust_kph:.1f} km/h peak gusts over the next 24 hours.",
                source_ids=self._source_ids(live, "open-meteo-weather"),
            )
        return CitedStatement(
            text=f"Operator fallback forecast: {request.forecast_rainfall_mm:.1f} mm rain and {request.forecast_wind_kph:.1f} km/h gusts over the next 24 hours.",
            source_ids=["operator-assessment-inputs"],
        )

    def _flood_observation(self, request: AssessmentRequest, live: LiveIntelligence | None) -> CitedStatement:
        if live and live.flood_forecast:
            flood = live.flood_forecast
            return CitedStatement(
                text=f"Flood forecast: {flood.river_discharge_m3s:.1f} m3/s current modelled discharge and {flood.peak_7day_discharge_m3s:.1f} m3/s seven-day peak.",
                source_ids=self._source_ids(live, "open-meteo-flood"),
            )
        return CitedStatement(
            text=f"Operator-reported expected river rise: {request.river_rise_m:.1f} m.",
            source_ids=["operator-assessment-inputs"],
        )

    def _route_observation(self, live: LiveIntelligence | None) -> CitedStatement:
        if live and live.alternate_route:
            route = live.alternate_route
            return CitedStatement(
                text=f"Planning route: {route.label}, {route.distance_km:.1f} km and approximately {route.duration_minutes:.0f} minutes.",
                source_ids=self._source_ids(live, "osrm-routing"),
            )
        return CitedStatement(
            text="No suggested response route was returned for this assessment.",
            source_ids=self._source_ids(live, "osrm-routing"),
        )

    @staticmethod
    def _condition_observation(request: AssessmentRequest) -> CitedStatement:
        scour = "Observed scour was reported." if request.observed_scour else "No observed scour was reported."
        return CitedStatement(
            text=f"Operator field inputs: condition score {request.condition_score}/100; asset age {request.asset_age_years} years. {scour}",
            source_ids=["operator-field-report", "operator-assessment-inputs"],
        )

    def _forecast_observation(self, live: LiveIntelligence | None) -> CitedStatement:
        if live and live.weather and live.weather.forecast_windows:
            forecast = next((item for item in live.weather.forecast_windows if item.hours_ahead == 12), live.weather.forecast_windows[-1])
            return CitedStatement(
                text=f"Available forecast window: {forecast.precipitation_mm:.1f} mm precipitation and {forecast.wind_gust_kph:.1f} km/h peak gusts by {forecast.forecast_end}.",
                source_ids=self._source_ids(live, "open-meteo-weather"),
            )
        return CitedStatement(
            text="No time-bounded weather forecast window was available for the 12-hour planning horizon.",
            source_ids=self._source_ids(live, "open-meteo-weather"),
        )

    def _alerts_observation(self, live: LiveIntelligence | None) -> CitedStatement:
        if live and live.weather_alerts:
            return CitedStatement(
                text=f"Official National Weather Service alerts returned: {', '.join(alert.event for alert in live.weather_alerts[:4])}.",
                source_ids=self._source_ids(live, "nws-alerts"),
            )
        return CitedStatement(
            text="No official weather alerts were included in the assessment snapshot, or the source was unavailable.",
            source_ids=self._source_ids(live, "nws-alerts"),
        )

    def _bridge_exposure_observation(self, analyses: list[BridgeAnalysis], live: LiveIntelligence | None) -> CitedStatement:
        elevated = [
            bridge.name
            for bridge in analyses
            if bridge.risk_scope == "flood_exposure" and bridge.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        ]
        if elevated:
            return CitedStatement(
                text=f"Mapped nearby bridges with elevated flood exposure: {', '.join(elevated[:5])}.",
                source_ids=self._source_ids(live, "openstreetmap-bridges", "open-meteo-flood", model=True),
            )
        return CitedStatement(
            text="No mapped nearby bridges met the elevated flood-exposure screening threshold in this assessment.",
            source_ids=self._source_ids(live, "openstreetmap-bridges", "open-meteo-flood", model=True),
        )

    def _resource_observation(self, live: LiveIntelligence | None) -> CitedStatement:
        facilities = live.critical_infrastructure if live else []
        if facilities:
            categories = sorted({facility.category for facility in facilities})
            return CitedStatement(
                text=f"Mapped critical facilities: {len(facilities)} across {', '.join(categories)} categories.",
                source_ids=self._source_ids(live, "openstreetmap-critical-infrastructure"),
            )
        return CitedStatement(
            text="No mapped critical facilities were returned for resource-planning context.",
            source_ids=self._source_ids(live, "openstreetmap-critical-infrastructure"),
        )

    @staticmethod
    def _immediate_action(level: RiskLevel) -> str:
        if level is RiskLevel.CRITICAL:
            return "Escalate to incident command for authority review and consider access restrictions only after the responsible authority approves them."
        if level is RiskLevel.HIGH:
            return "Request urgent qualified engineering review and prepare traffic-control options for authority approval."
        if level is RiskLevel.MODERATE:
            return "Schedule qualified visual inspection and monitor weather and water updates."
        return "Continue routine observation and re-assess if forecast or field conditions change."
