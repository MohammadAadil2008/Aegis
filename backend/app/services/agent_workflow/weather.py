from __future__ import annotations

import asyncio

from app.schemas import AgentFinding
from app.services.agent_workflow.base import AgentContext, available_source_ids


class WeatherAgent:
    name = "Weather Agent"

    async def run(self, context: AgentContext) -> AgentFinding:
        await asyncio.sleep(0)
        request = context.request
        live = context.live_intelligence
        weather = live.weather if live else None
        precipitation = weather.precipitation_next_24h_mm if weather else request.forecast_rainfall_mm
        wind_gusts = weather.wind_gust_kph if weather else request.forecast_wind_kph
        rainfall_risk = min(35, round(precipitation / 4))
        wind_risk = min(10, round(wind_gusts / 15))
        evidence = [
            f"Forecast rainfall: {precipitation:.0f} mm",
            f"Forecast wind: {wind_gusts:.0f} km/h",
        ]
        source_ids = ["operator-assessment-inputs"]
        if weather:
            evidence.append("Live weather forecast was used for the next 24 hours.")
            source_ids.append("open-meteo-weather")
        if live and live.weather_alerts:
            evidence.append(f"Official National Weather Service alerts: {len(live.weather_alerts)} active.")
            source_ids.append("nws-alerts")
        if live and live.radar_layer:
            evidence.append("A RainViewer radar frame was available for map review.")
            source_ids.append("rainviewer-radar")
        return AgentFinding(
            agent=self.name,
            status="complete",
            summary="Forecast weather and official alerts were evaluated for operational impact.",
            evidence=evidence,
            data={"weather_risk_score": rainfall_risk + wind_risk},
            source_ids=[source_id for source_id in source_ids if source_id in available_source_ids(live)],
        )
