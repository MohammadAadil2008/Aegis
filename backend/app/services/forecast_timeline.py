from __future__ import annotations

from app.schemas import (
    AssessmentRequest,
    CitedStatement,
    LiveIntelligence,
    RiskAssessment,
    TimelineEntry,
    WeatherForecastWindow,
)


class ForecastTimelineBuilder:
    """Builds a source-limited 24-hour outlook without inferring unavailable data."""

    _horizons = ((0, "Now"), (2, "2 hours"), (6, "6 hours"), (12, "12 hours"), (24, "24 hours"))

    def build(
        self,
        request: AssessmentRequest,
        risk: RiskAssessment,
        live: LiveIntelligence | None,
    ) -> list[TimelineEntry]:
        windows = {
            window.hours_ahead: window
            for window in (live.weather.forecast_windows if live and live.weather else [])
        }
        entries = []
        for hours_ahead, label in self._horizons:
            weather_window = windows.get(hours_ahead)
            entries.append(
                TimelineEntry(
                    label=label,
                    hours_ahead=hours_ahead,
                    kind="observation" if hours_ahead == 0 else "forecast",
                    weather=self._weather(request, live, weather_window, hours_ahead),
                    river_level=self._river(request, live, hours_ahead),
                    flood_risk=self._flood_risk(live, risk, weather_window, hours_ahead),
                    bridge_status=self._bridge_status(request, risk, hours_ahead),
                    recommended_action=self._action(live, risk, hours_ahead),
                    limitations=self._limitations(live, weather_window, hours_ahead),
                )
            )
        return entries

    @staticmethod
    def _source_ids(live: LiveIntelligence | None, *source_ids: str, model: bool = False) -> list[str]:
        available = {source.id for source in live.sources} if live else set()
        selected = [source_id for source_id in source_ids if source_id in available]
        if model:
            selected = ["aegis-risk-model", "operator-assessment-inputs", *selected]
        if not selected:
            selected.append("operator-assessment-inputs")
        return list(dict.fromkeys(selected))[:6]

    def _weather(
        self,
        request: AssessmentRequest,
        live: LiveIntelligence | None,
        window: WeatherForecastWindow | None,
        hours_ahead: int,
    ) -> CitedStatement:
        if hours_ahead == 0 and live and live.weather and live.weather.weather_code is not None:
            observed_at = live.weather.observed_at or "the latest source update"
            return CitedStatement(
                text=f"Observation: current weather code {live.weather.weather_code} reported at {observed_at}.",
                source_ids=self._source_ids(live, "open-meteo-weather"),
            )
        if hours_ahead == 0 and live and live.weather:
            return CitedStatement(
                text=(
                    "No current weather observation was returned by the source; the available forecast "
                    f"shows {live.weather.precipitation_next_24h_mm:.1f} mm precipitation and "
                    f"{live.weather.wind_gust_kph:.1f} km/h peak gusts over the next 24 hours."
                ),
                source_ids=self._source_ids(live, "open-meteo-weather"),
            )
        if window:
            return CitedStatement(
                text=(
                    f"Forecast: cumulative precipitation of {window.precipitation_mm:.1f} mm and "
                    f"peak gusts of {window.wind_gust_kph:.1f} km/h by {window.forecast_end}."
                ),
                source_ids=self._source_ids(live, "open-meteo-weather"),
            )
        return CitedStatement(
            text=(
                "No time-bounded weather forecast was returned; operator fallback values remain "
                f"{request.forecast_rainfall_mm:.1f} mm rain and {request.forecast_wind_kph:.1f} km/h gusts over 24 hours."
            ),
            source_ids=["operator-assessment-inputs"],
        )

    def _river(
        self, request: AssessmentRequest, live: LiveIntelligence | None, hours_ahead: int
    ) -> CitedStatement:
        gauge = live.nearest_gauge if live else None
        flood = live.flood_forecast if live else None
        if hours_ahead == 0 and gauge:
            if gauge.stage_ft is not None:
                return CitedStatement(
                    text=f"Observation: nearest USGS gauge stage is {gauge.stage_ft:.2f} ft at {gauge.observed_at or 'the latest update'}.",
                    source_ids=self._source_ids(live, "usgs-water"),
                )
            if gauge.flow_cfs is not None:
                return CitedStatement(
                    text=f"Observation: nearest USGS gauge flow is {gauge.flow_cfs:.0f} cfs at {gauge.observed_at or 'the latest update'}.",
                    source_ids=self._source_ids(live, "usgs-water"),
                )
        if hours_ahead == 24 and flood and flood.daily_discharge:
            forecast = flood.daily_discharge[0]
            return CitedStatement(
                text=(
                    f"Forecast: daily discharge beginning {forecast.forecast_date} is {forecast.discharge_m3s:.1f} m3/s "
                    f"with a daily maximum of {forecast.peak_discharge_m3s:.1f} m3/s."
                ),
                source_ids=self._source_ids(live, "open-meteo-flood"),
            )
        if hours_ahead == 0:
            return CitedStatement(
                text=(
                    "No river gauge observation is included in this assessment; the operator supplied "
                    f"an expected river rise of {request.river_rise_m:.1f} m."
                ),
                source_ids=["operator-assessment-inputs"],
            )
        return CitedStatement(
            text="No sub-daily river-discharge forecast is available for this time point.",
            source_ids=self._source_ids(live, "open-meteo-flood"),
        )

    def _flood_risk(
        self,
        live: LiveIntelligence | None,
        risk: RiskAssessment,
        window: WeatherForecastWindow | None,
        hours_ahead: int,
    ) -> CitedStatement:
        if hours_ahead == 0:
            return CitedStatement(
                text=f"Current screening assessment: {risk.risk_level} risk ({risk.score}/100).",
                source_ids=self._source_ids(
                    live, "open-meteo-weather", "open-meteo-flood", "usgs-water", model=True
                ),
            )
        if hours_ahead < 24:
            return CitedStatement(
                text="No interval-specific flood-risk forecast is available; reassessment is required as new source data arrives.",
                source_ids=self._source_ids(live, "open-meteo-weather", "open-meteo-flood", model=True),
            )
        flood = live.flood_forecast if live else None
        daily_peak = flood.daily_discharge[0].peak_discharge_m3s if flood and flood.daily_discharge else None
        if window or daily_peak is not None:
            elevated = (window and window.precipitation_mm >= 35) or (daily_peak is not None and daily_peak >= 250)
            drivers = []
            if window:
                drivers.append(f"{window.precipitation_mm:.1f} mm forecast precipitation")
            if daily_peak is not None:
                drivers.append(f"{daily_peak:.1f} m3/s forecast daily maximum discharge")
            return CitedStatement(
                text=(
                    f"24-hour forecast screening: {'ELEVATED' if elevated else 'MONITOR'} flood risk "
                    f"based on {' and '.join(drivers)}."
                ),
                source_ids=self._source_ids(live, "open-meteo-weather", "open-meteo-flood", model=True),
            )
        return CitedStatement(
            text="No 24-hour flood-risk forecast can be produced because forecast inputs were unavailable.",
            source_ids=self._source_ids(live, model=True),
        )

    def _bridge_status(
        self, request: AssessmentRequest, risk: RiskAssessment, hours_ahead: int
    ) -> CitedStatement:
        if hours_ahead == 0:
            text = f"Current screening status: {risk.risk_level} risk ({risk.score}/100); human engineering review is required."
        else:
            text = (
                "No structural-status forecast is available. Current screening status is carried forward "
                "for planning only and does not predict bridge failure."
            )
        return CitedStatement(
            text=text,
            source_ids=["aegis-risk-model", "operator-field-report", "operator-assessment-inputs"],
        )

    def _action(
        self, live: LiveIntelligence | None, risk: RiskAssessment, hours_ahead: int
    ) -> CitedStatement:
        if hours_ahead == 0:
            action = (
                "Confirm qualified engineering review and the appropriate authority decision."
                if risk.risk_level in {"HIGH", "CRITICAL"}
                else "Continue observation and verify the next source update."
            )
        elif hours_ahead < 12:
            action = "Monitor official weather and river sources; reassess if conditions or field observations change."
        elif hours_ahead < 24:
            action = "Prepare the next qualified inspection decision using updated forecast and field evidence."
        else:
            action = "Re-run the assessment with refreshed public-source data before operational action."
        return CitedStatement(
            text=action,
            source_ids=self._source_ids(live, "open-meteo-weather", "open-meteo-flood", "usgs-water", model=True),
        )

    @staticmethod
    def _limitations(
        live: LiveIntelligence | None, window: WeatherForecastWindow | None, hours_ahead: int
    ) -> list[str]:
        limits = []
        if hours_ahead and not window:
            limits.append("No time-bounded weather forecast was available for this horizon.")
        if 0 < hours_ahead < 24:
            limits.append("The flood source provides daily, not sub-daily, discharge forecasts.")
        if hours_ahead:
            limits.append("No structural-status forecast is available; bridge status is not predicted.")
        if hours_ahead == 0 and (not live or not live.nearest_gauge):
            limits.append("No current USGS river gauge observation was available.")
        return limits
