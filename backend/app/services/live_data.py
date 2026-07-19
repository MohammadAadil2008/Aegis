from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from math import cos
from threading import Lock
from time import monotonic
from typing import Any

import httpx

from app.schemas import (
    AssessmentRequest,
    CriticalInfrastructureAsset,
    Coordinates,
    DailyDischargeForecast,
    EvidenceSource,
    FloodForecast,
    FloodScreeningArea,
    GaugeReading,
    LiveIntelligence,
    MapAsset,
    OfficialBridge,
    RadarLayer,
    RoutePlan,
    SeismicEvent,
    TerrainProfile,
    WeatherAlert,
    WeatherForecastWindow,
    WeatherSnapshot,
)

logger = logging.getLogger(__name__)


class LiveDataService:
    """Reads public data sources with short timeouts and a safe offline fallback."""

    _cache_ttl_seconds = 300
    _max_cache_entries = 128
    _asset_location_warning = (
        "The assessed-asset marker uses the resolved city-level location; verify bridge coordinates "
        "before making route, flood-zone, or proximity decisions."
    )

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, LiveIntelligence]] = {}
        self._cache_lock = Lock()

    def collect(
        self, request: AssessmentRequest, official_bridge: OfficialBridge | None = None
    ) -> LiveIntelligence:
        if not request.use_live_data:
            return LiveIntelligence(enabled=False, warnings=["Live sources are disabled for this assessment."])

        cache_key = (
            f"nbi:{official_bridge.nbi_record_id}"
            if official_bridge
            else " ".join(request.location.casefold().split())
        )
        cached = self._get_cached(cache_key)
        if cached is not None:
            return self._for_request(cached, request, official_bridge)

        warnings: list[str] = []
        resolved = (
            (request.location, official_bridge.coordinates)
            if official_bridge
            else self.resolve_location(request.location)
        )
        if resolved is None:
            return LiveIntelligence(
                enabled=True,
                warnings=["Location could not be resolved. Manual inputs remain in use."],
            )

        resolved_name, coordinates = resolved
        with ThreadPoolExecutor(max_workers=10) as executor:
            weather_future = executor.submit(self._weather, coordinates)
            flood_future = executor.submit(self._flood_forecast, coordinates)
            gauge_future = executor.submit(self._nearest_gauge, coordinates)
            bridges_future = executor.submit(self._nearby_bridges, coordinates)
            route_future = executor.submit(self._alternate_route, coordinates)
            alerts_future = executor.submit(self._weather_alerts, coordinates)
            earthquakes_future = executor.submit(self._recent_earthquakes, coordinates)
            radar_future = executor.submit(self._radar_layer)
            terrain_future = executor.submit(self._terrain, coordinates)
            infrastructure_future = executor.submit(self._nearby_critical_infrastructure, coordinates)
            weather = self._future_result("weather", weather_future)
            flood_forecast = self._future_result("flood forecast", flood_future)
            gauge = self._future_result("river gauge", gauge_future)
            bridges = self._future_result("bridge inventory", bridges_future) or []
            route = self._future_result("routing", route_future)
            alerts = self._future_result("weather alerts", alerts_future)
            earthquakes = self._future_result("earthquake catalog", earthquakes_future)
            radar = self._future_result("rain radar", radar_future)
            terrain = self._future_result("terrain elevation", terrain_future)
            critical_infrastructure = (
                self._future_result("critical infrastructure inventory", infrastructure_future) or []
            )

        sources = [
            EvidenceSource(
                id="open-meteo-geocoding",
                label="Location resolution",
                provider="Open-Meteo geocoding",
                url="https://geocoding-api.open-meteo.com/v1/search",
            )
        ]
        if official_bridge:
            sources.append(
                EvidenceSource(
                    id="fhwa-national-bridge-inventory",
                    label="Official bridge inventory record",
                    provider="FHWA National Bridge Inventory",
                    url=official_bridge.source_url,
                )
            )
        if weather is None:
            warnings.append("Live weather was unavailable; manual forecast inputs remain in use.")
        else:
            sources.append(
                EvidenceSource(
                    id="open-meteo-weather",
                    label="Forecast weather",
                    provider=weather.source,
                    url="https://api.open-meteo.com/v1/forecast",
                )
            )
        if flood_forecast is None:
            warnings.append("Modelled river-discharge forecast was unavailable.")
        else:
            sources.append(
                EvidenceSource(
                    id="open-meteo-flood",
                    label="Flood forecast",
                    provider=flood_forecast.source,
                    url="https://flood-api.open-meteo.com/v1/flood",
                )
            )
        if gauge is None:
            warnings.append("No nearby USGS gauge reading was available.")
        else:
            sources.append(
                EvidenceSource(
                    id="usgs-water",
                    label="River gauge reading",
                    provider="USGS Water Services",
                    url="https://waterdata.usgs.gov/",
                )
            )
        if not bridges:
            warnings.append("No nearby OpenStreetMap bridge features were returned.")
        else:
            sources.append(
                EvidenceSource(
                    id="openstreetmap-bridges",
                    label="Nearby bridge features",
                    provider="OpenStreetMap via Overpass",
                    url="https://overpass-api.de/",
                )
            )
        if route is None:
            warnings.append("A routing service did not return a suggested detour.")
        else:
            sources.append(
                EvidenceSource(
                    id="osrm-routing",
                    label="Response detour",
                    provider="OSRM routing",
                    url="https://router.project-osrm.org/",
                )
            )
        if alerts is None:
            warnings.append("Official National Weather Service alerts were unavailable.")
            alerts = []
        else:
            sources.append(
                EvidenceSource(
                    id="nws-alerts",
                    label="Official weather alerts",
                    provider="National Weather Service",
                    url="https://api.weather.gov/alerts",
                )
            )
        if earthquakes is None:
            warnings.append("Recent earthquake evidence was unavailable.")
            earthquakes = []
        else:
            sources.append(
                EvidenceSource(
                    id="usgs-earthquakes",
                    label="Recent earthquakes",
                    provider="USGS Earthquake Catalog",
                    url="https://earthquake.usgs.gov/fdsnws/event/1/",
                )
            )
        if radar is None:
            warnings.append("Rain radar imagery was unavailable.")
        else:
            sources.append(
                EvidenceSource(
                    id="rainviewer-radar",
                    label="Rain radar layer",
                    provider="RainViewer",
                    url="https://www.rainviewer.com/",
                )
            )
        if terrain is None:
            warnings.append("Terrain elevation was unavailable.")
        else:
            sources.append(
                EvidenceSource(
                    id="open-meteo-elevation",
                    label="Terrain elevation",
                    provider=terrain.source,
                    url="https://api.open-meteo.com/v1/elevation",
                )
            )
        if critical_infrastructure:
            sources.append(
                EvidenceSource(
                    id="openstreetmap-critical-infrastructure",
                    label="Nearby critical infrastructure",
                    provider="OpenStreetMap via Overpass",
                    url="https://overpass-api.de/",
                )
            )
        else:
            warnings.append("No nearby mapped hospitals, fire stations, police stations, or schools were returned.")

        assets = [
            MapAsset(
                name=official_bridge.name if official_bridge else request.asset_name,
                coordinates=coordinates,
                source=(
                    "FHWA National Bridge Inventory verified bridge coordinate"
                    if official_bridge
                    else "City-level assessment location; asset coordinates not verified"
                ),
            ),
            *bridges,
        ]
        result = LiveIntelligence(
            enabled=True,
            resolved_location=resolved_name,
            coordinates=coordinates,
            weather=weather,
            nearest_gauge=gauge,
            bridge_assets=assets,
            flood_forecast=flood_forecast,
            flood_screening=self._flood_screening(coordinates, weather, flood_forecast, gauge),
            alternate_route=route,
            weather_alerts=alerts,
            seismic_events=earthquakes,
            radar_layer=radar,
            terrain=terrain,
            critical_infrastructure=critical_infrastructure,
            sources=sources,
            warnings=(warnings if official_bridge else [*warnings, self._asset_location_warning]),
        )
        self._cache_result(cache_key, result)
        return result

    def _get_cached(self, cache_key: str) -> LiveIntelligence | None:
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is None or cached[0] < monotonic():
                self._cache.pop(cache_key, None)
                return None
            return cached[1]

    def _cache_result(self, cache_key: str, result: LiveIntelligence) -> None:
        with self._cache_lock:
            now = monotonic()
            expired_keys = [key for key, (expires_at, _) in self._cache.items() if expires_at < now]
            for key in expired_keys:
                self._cache.pop(key, None)
            if cache_key not in self._cache and len(self._cache) >= self._max_cache_entries:
                oldest_key = min(self._cache, key=lambda key: self._cache[key][0])
                self._cache.pop(oldest_key, None)
            self._cache[cache_key] = (monotonic() + self._cache_ttl_seconds, result)

    @classmethod
    def _for_request(
        cls,
        cached: LiveIntelligence,
        request: AssessmentRequest,
        official_bridge: OfficialBridge | None = None,
    ) -> LiveIntelligence:
        """Rebind location-scoped cached evidence to the asset in the current request."""
        if not cached.bridge_assets:
            return cached
        marker = cached.bridge_assets[0].model_copy(
            update={
                "name": official_bridge.name if official_bridge else request.asset_name,
                "source": (
                    "FHWA National Bridge Inventory verified bridge coordinate"
                    if official_bridge
                    else "City-level assessment location; asset coordinates not verified"
                ),
                "risk_level": None,
            }
        )
        warnings = (
            list(cached.warnings)
            if official_bridge
            else list(dict.fromkeys([*cached.warnings, cls._asset_location_warning]))
        )
        return cached.model_copy(
            update={"bridge_assets": [marker, *cached.bridge_assets[1:]], "warnings": warnings}
        )

    @staticmethod
    def _future_result(source_name: str, future: Future[Any]) -> Any | None:
        """Keep one malformed or unavailable public provider from failing the assessment."""
        try:
            return future.result()
        except Exception:
            logger.warning("Public data source task failed: %s", source_name, exc_info=True)
            return None

    @staticmethod
    def _request_json(
        method: str, url: str, timeout_seconds: float = 6.0, **kwargs: Any
    ) -> dict[str, Any] | None:
        try:
            response = httpx.request(
                method,
                url,
                timeout=timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "Aegis-MVP/0.1 (educational decision support)"},
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except (httpx.HTTPError, ValueError):
            return None

    def resolve_location(self, location: str) -> tuple[str, Coordinates] | None:
        return self._geocode(location)

    def _geocode(self, location: str) -> tuple[str, Coordinates] | None:
        search_name = location.split(",", maxsplit=1)[0].strip()
        data = self._request_json(
            "GET",
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": search_name, "count": 1, "language": "en", "format": "json"},
        )
        result = (data or {}).get("results", [])
        if not result:
            return None
        match = result[0]
        try:
            pieces = [match.get("name"), match.get("admin1"), match.get("country")]
            return ", ".join(piece for piece in pieces if piece), Coordinates(
                latitude=float(match["latitude"]), longitude=float(match["longitude"])
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            return None

    def _weather(self, coordinates: Coordinates) -> WeatherSnapshot | None:
        data = self._request_json(
            "GET",
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": coordinates.latitude,
                "longitude": coordinates.longitude,
                "hourly": "precipitation,wind_gusts_10m,weather_code",
                "current": "weather_code",
                "forecast_days": 2,
                "timezone": "auto",
            },
        )
        hourly = (data or {}).get("hourly") or {}
        times = hourly.get("time") or []
        precipitation = hourly.get("precipitation") or []
        gusts = hourly.get("wind_gusts_10m") or []
        if not times or not precipitation or not gusts:
            return None
        current_time = ((data or {}).get("current") or {}).get("time")
        start = times.index(current_time) if current_time in times else 0
        end = min(start + 24, len(times))
        forecast_windows = []
        for hours_ahead in (2, 6, 12, 24):
            window_end = min(start + hours_ahead, len(times))
            if window_end <= start:
                continue
            forecast_windows.append(
                WeatherForecastWindow(
                    hours_ahead=hours_ahead,
                    forecast_end=str(times[window_end - 1]),
                    precipitation_mm=round(
                        sum(float(value or 0) for value in precipitation[start:window_end]), 1
                    ),
                    wind_gust_kph=round(
                        max(float(value or 0) for value in gusts[start:window_end]), 1
                    ),
                )
            )
        return WeatherSnapshot(
            source="Open-Meteo forecast",
            observed_at=current_time,
            precipitation_next_24h_mm=round(sum(float(value or 0) for value in precipitation[start:end]), 1),
            wind_gust_kph=round(max(float(value or 0) for value in gusts[start:end]), 1),
            weather_code=((data or {}).get("current") or {}).get("weather_code"),
            forecast_windows=forecast_windows,
        )

    def _flood_forecast(self, coordinates: Coordinates) -> FloodForecast | None:
        data = self._request_json(
            "GET",
            "https://flood-api.open-meteo.com/v1/flood",
            params={
                "latitude": coordinates.latitude,
                "longitude": coordinates.longitude,
                "daily": "river_discharge,river_discharge_max",
                "forecast_days": 7,
            },
        )
        daily = (data or {}).get("daily") or {}
        times = daily.get("time") or []
        discharge = daily.get("river_discharge") or []
        peak = daily.get("river_discharge_max") or discharge
        if not times or not discharge:
            return None
        values = [float(value) for value in discharge if value is not None]
        peak_values = [float(value) for value in peak if value is not None]
        if not values or not peak_values:
            return None
        return FloodForecast(
            source="Open-Meteo GloFAS river-discharge forecast",
            forecast_start=times[0],
            river_discharge_m3s=round(values[0], 1),
            peak_7day_discharge_m3s=round(max(peak_values), 1),
            daily_discharge=[
                DailyDischargeForecast(
                    forecast_date=str(forecast_date),
                    discharge_m3s=round(float(discharge[index]), 1),
                    peak_discharge_m3s=round(
                        float(peak[index] if index < len(peak) and peak[index] is not None else discharge[index]),
                        1,
                    ),
                )
                for index, forecast_date in enumerate(times)
                if index < len(discharge) and discharge[index] is not None
            ],
        )

    def _weather_alerts(self, coordinates: Coordinates) -> list[WeatherAlert] | None:
        data = self._request_json(
            "GET",
            "https://api.weather.gov/alerts/active",
            params={"point": f"{coordinates.latitude},{coordinates.longitude}"},
        )
        if data is None:
            return None
        alerts: list[WeatherAlert] = []
        for feature in (data.get("features") or [])[:8]:
            properties = feature.get("properties") or {}
            headline = properties.get("headline") or properties.get("description")
            event = properties.get("event")
            if not isinstance(headline, str) or not isinstance(event, str):
                continue
            alerts.append(
                WeatherAlert(
                    event=event,
                    severity=properties.get("severity"),
                    headline=headline[:500],
                    effective=properties.get("effective"),
                    expires=properties.get("expires"),
                )
            )
        return alerts

    def _recent_earthquakes(self, coordinates: Coordinates) -> list[SeismicEvent] | None:
        start_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        data = self._request_json(
            "GET",
            "https://earthquake.usgs.gov/fdsnws/event/1/query",
            params={
                "format": "geojson",
                "latitude": coordinates.latitude,
                "longitude": coordinates.longitude,
                "maxradiuskm": 100,
                "starttime": start_time,
                "minmagnitude": 2.5,
                "orderby": "time",
                "limit": 8,
            },
        )
        if data is None:
            return None
        events: list[SeismicEvent] = []
        for feature in data.get("features") or []:
            properties = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}
            point = geometry.get("coordinates") or []
            if len(point) < 2 or properties.get("mag") is None or not properties.get("time"):
                continue
            occurred_at = datetime.fromtimestamp(
                float(properties["time"]) / 1_000, tz=timezone.utc
            ).isoformat()
            try:
                events.append(
                    SeismicEvent(
                        event_id=str(feature.get("id") or "unknown"),
                        magnitude=float(properties["mag"]),
                        place=str(properties.get("place") or "Unnamed USGS event"),
                        occurred_at=occurred_at,
                        coordinates=Coordinates(latitude=float(point[1]), longitude=float(point[0])),
                    )
                )
            except (TypeError, ValueError):
                continue
        return events

    def _radar_layer(self) -> RadarLayer | None:
        data = self._request_json(
            "GET", "https://api.rainviewer.com/public/weather-maps.json", timeout_seconds=5.0
        )
        radar = (data or {}).get("radar") or {}
        frames = radar.get("past") or radar.get("nowcast") or []
        if not frames:
            return None
        latest = frames[-1]
        path = latest.get("path")
        if not isinstance(path, str) or not path:
            return None
        host = str((data or {}).get("host") or "https://tilecache.rainviewer.com").rstrip("/")
        observed_at = latest.get("time")
        timestamp = (
            datetime.fromtimestamp(float(observed_at), tz=timezone.utc).isoformat()
            if observed_at is not None
            else None
        )
        return RadarLayer(
            tile_url=f"{host}{path}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",
            observed_at=timestamp,
            attribution="Rain radar: RainViewer",
        )

    def _terrain(self, coordinates: Coordinates) -> TerrainProfile | None:
        data = self._request_json(
            "GET",
            "https://api.open-meteo.com/v1/elevation",
            params={"latitude": coordinates.latitude, "longitude": coordinates.longitude},
        )
        elevations = (data or {}).get("elevation") or []
        if not elevations or elevations[0] is None:
            return None
        return TerrainProfile(
            elevation_meters=round(float(elevations[0]), 1),
            source="Open-Meteo elevation",
        )

    def _nearest_gauge(self, coordinates: Coordinates) -> GaugeReading | None:
        delta = 0.18
        data = self._request_json(
            "GET",
            "https://waterservices.usgs.gov/nwis/iv/",
            params={
                "format": "json",
                "bBox": (
                    f"{coordinates.longitude - delta},{coordinates.latitude - delta},"
                    f"{coordinates.longitude + delta},{coordinates.latitude + delta}"
                ),
                "parameterCd": "00065,00060",
                "siteStatus": "all",
            },
        )
        series = ((data or {}).get("value") or {}).get("timeSeries") or []
        candidates: dict[str, GaugeReading] = {}
        for item in series:
            source = item.get("sourceInfo") or {}
            code = ((source.get("siteCode") or [{}])[0]).get("value")
            location = ((source.get("geoLocation") or {}).get("geogLocation") or {})
            if not code or "latitude" not in location or "longitude" not in location:
                continue
            point = Coordinates(latitude=float(location["latitude"]), longitude=float(location["longitude"]))
            reading = candidates.get(code) or GaugeReading(
                site_id=code,
                site_name=source.get("siteName", "USGS gauge"),
                coordinates=point,
            )
            measurements = ((item.get("values") or [{}])[0]).get("value") or []
            if not measurements:
                continue
            latest = measurements[-1]
            try:
                value = float(latest.get("value"))
            except (TypeError, ValueError):
                continue
            parameter = (((item.get("variable") or {}).get("variableCode") or [{}])[0]).get("value")
            update = {"observed_at": latest.get("dateTime")}
            if parameter == "00065":
                update["stage_ft"] = value
            elif parameter == "00060":
                update["flow_cfs"] = value
            candidates[code] = reading.model_copy(update=update)
        if not candidates:
            return None
        return min(candidates.values(), key=lambda gauge: self._distance_squared(coordinates, gauge.coordinates))

    def _nearby_bridges(self, coordinates: Coordinates) -> list[MapAsset]:
        query = (
            "[out:json][timeout:6];"
            "("
            f"way(around:10000,{coordinates.latitude},{coordinates.longitude})[bridge];"
            f"node(around:10000,{coordinates.latitude},{coordinates.longitude})[man_made=bridge];"
            ");"
            "out center 30;"
        )
        data = self._request_json(
            "POST",
            "https://overpass-api.de/api/interpreter",
            timeout_seconds=12.0,
            data={"data": query},
        )
        assets: list[MapAsset] = []
        for element in (data or {}).get("elements") or []:
            center = element.get("center") or element
            if "lat" not in center or "lon" not in center:
                continue
            tags = element.get("tags") or {}
            name = tags.get("name") or tags.get("ref") or "Unnamed mapped bridge"
            assets.append(
                MapAsset(
                    name=name,
                    coordinates=Coordinates(latitude=float(center["lat"]), longitude=float(center["lon"])),
                    source="OpenStreetMap bridge feature",
                )
            )
        return assets

    def _nearby_critical_infrastructure(
        self, coordinates: Coordinates
    ) -> list[CriticalInfrastructureAsset]:
        query = (
            "[out:json][timeout:6];"
            "("
            f"nwr(around:10000,{coordinates.latitude},{coordinates.longitude})[amenity=hospital];"
            f"nwr(around:10000,{coordinates.latitude},{coordinates.longitude})[amenity=police];"
            f"nwr(around:10000,{coordinates.latitude},{coordinates.longitude})[amenity=school];"
            f"nwr(around:10000,{coordinates.latitude},{coordinates.longitude})[amenity=fire_station];"
            f"nwr(around:10000,{coordinates.latitude},{coordinates.longitude})[emergency=fire_station];"
            ");"
            "out center 40;"
        )
        data = self._request_json(
            "POST",
            "https://overpass-api.de/api/interpreter",
            timeout_seconds=12.0,
            data={"data": query},
        )
        facilities: list[CriticalInfrastructureAsset] = []
        for element in (data or {}).get("elements") or []:
            center = element.get("center") or element
            if "lat" not in center or "lon" not in center:
                continue
            tags = element.get("tags") or {}
            category = tags.get("amenity") or tags.get("emergency")
            if category not in {"hospital", "fire_station", "police", "school"}:
                continue
            name = tags.get("name") or f"Mapped {category.replace('_', ' ')}"
            facilities.append(
                CriticalInfrastructureAsset(
                    name=name,
                    category=category.replace("_", " "),
                    coordinates=Coordinates(latitude=float(center["lat"]), longitude=float(center["lon"])),
                    source="OpenStreetMap critical infrastructure feature",
                )
            )
        return facilities

    def _alternate_route(self, coordinates: Coordinates) -> RoutePlan | None:
        origin = Coordinates(latitude=coordinates.latitude + 0.035, longitude=coordinates.longitude - 0.04)
        detour = Coordinates(latitude=coordinates.latitude, longitude=coordinates.longitude + 0.045)
        destination = Coordinates(latitude=coordinates.latitude - 0.035, longitude=coordinates.longitude - 0.04)
        points = ";".join(
            f"{point.longitude},{point.latitude}" for point in (origin, detour, destination)
        )
        data = self._request_json(
            "GET",
            f"https://router.project-osrm.org/route/v1/driving/{points}",
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
        )
        routes = (data or {}).get("routes") or []
        if not routes:
            return None
        route = routes[0]
        line = ((route.get("geometry") or {}).get("coordinates") or [])
        if len(line) < 2:
            return None
        return RoutePlan(
            geometry=[Coordinates(latitude=float(lat), longitude=float(lon)) for lon, lat in line],
            distance_km=round(float(route.get("distance", 0)) / 1_000, 1),
            duration_minutes=round(float(route.get("duration", 0)) / 60, 0),
            label="Illustrative regional route; verify the actual alternate crossing",
        )

    @staticmethod
    def _flood_screening(
        coordinates: Coordinates,
        weather: WeatherSnapshot | None,
        flood_forecast: FloodForecast | None,
        gauge: GaugeReading | None,
    ) -> FloodScreeningArea | None:
        if weather is None and flood_forecast is None and gauge is None:
            return None
        precipitation = weather.precipitation_next_24h_mm if weather else 0
        stage = gauge.stage_ft if gauge and gauge.stage_ft is not None else 0
        discharge = flood_forecast.peak_7day_discharge_m3s if flood_forecast else 0
        radius = min(4_000, max(700, int(700 + precipitation * 22 + stage * 100 + discharge * 5)))
        classification = "Elevated screening" if precipitation >= 35 or discharge >= 250 or stage >= 8 else "Monitor screening"
        return FloodScreeningArea(
            center=coordinates,
            radius_meters=radius,
            classification=classification,
            disclaimer="Screening overlay based on live forecast and gauge data. It is not an official flood zone or evacuation order.",
        )

    @staticmethod
    def _distance_squared(first: Coordinates, second: Coordinates) -> float:
        latitude_scale = 69.0
        longitude_scale = 69.0 * cos(first.latitude * 0.01745329252)
        return (
            (first.latitude - second.latitude) * latitude_scale
        ) ** 2 + ((first.longitude - second.longitude) * longitude_scale) ** 2
