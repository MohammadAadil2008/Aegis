from __future__ import annotations

from datetime import datetime, timezone
from math import cos, radians
from threading import Lock
from time import monotonic
from typing import Any

import httpx

from app.schemas import Coordinates, EmergencyAlert, EmergencyFeedResponse


class EmergencyFeedService:
    """Collects source-verified public alerts without mixing in model conclusions."""

    _cache_ttl_seconds = 55

    def __init__(self, ny511_api_key: str | None = None) -> None:
        self._ny511_api_key = ny511_api_key
        self._cache: dict[str, tuple[float, EmergencyFeedResponse]] = {}
        self._cache_lock = Lock()

    def collect(self, coordinates: Coordinates, location: str) -> EmergencyFeedResponse:
        cache_key = f"{coordinates.latitude:.3f},{coordinates.longitude:.3f}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        alerts, warnings = self._nws_alerts(coordinates)
        if self._is_new_york(coordinates):
            traffic_alerts, traffic_warning = self._ny511_alerts(coordinates)
            alerts.extend(traffic_alerts)
            if traffic_warning:
                warnings.append(traffic_warning)
        else:
            warnings.append(
                "No verified regional road or bridge closure feed is configured for this jurisdiction."
            )

        result = EmergencyFeedResponse(
            location=location,
            refreshed_at=datetime.now(timezone.utc).isoformat(),
            alerts=sorted(alerts, key=lambda alert: (alert.category, alert.title)),
            warnings=warnings,
        )
        self._cache_result(cache_key, result)
        return result

    @staticmethod
    def _request_json(url: str, **params: str) -> dict[str, Any] | list[Any] | None:
        try:
            response = httpx.get(
                url,
                params=params,
                timeout=8.0,
                follow_redirects=True,
                headers={"User-Agent": "Aegis-MVP/0.1 (educational decision support)"},
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    def _nws_alerts(self, coordinates: Coordinates) -> tuple[list[EmergencyAlert], list[str]]:
        response = self._request_json(
            "https://api.weather.gov/alerts/active",
            point=f"{coordinates.latitude},{coordinates.longitude}",
        )
        if not isinstance(response, dict):
            return [], ["National Weather Service alerts were unavailable during this refresh."]

        alerts = []
        for feature in response.get("features", [])[:20]:
            properties = feature.get("properties") or {}
            event = properties.get("event")
            headline = properties.get("headline") or properties.get("description")
            if not isinstance(event, str) or not isinstance(headline, str):
                continue
            category = "flood" if "flood" in event.lower() else "weather"
            alerts.append(
                EmergencyAlert(
                    id=str(properties.get("id") or properties.get("@id") or event),
                    category=category,
                    title=event,
                    summary=headline[:1_000],
                    severity=properties.get("severity"),
                    observed_at=properties.get("sent") or properties.get("effective"),
                    source_name="National Weather Service",
                    source_url=properties.get("@id"),
                )
            )
        return alerts, []

    def _ny511_alerts(self, coordinates: Coordinates) -> tuple[list[EmergencyAlert], str | None]:
        if not self._ny511_api_key:
            return [], "Road and bridge alerts require an optional NY511_API_KEY for New York assessments."
        response = self._request_json(
            "https://511ny.org/api/v2/get/event",
            key=self._ny511_api_key,
            format="json",
        )
        if not isinstance(response, list):
            return [], "The official 511NY traffic event feed was unavailable during this refresh."

        alerts = []
        for event in response:
            if not isinstance(event, dict) or not self._within_radius(event, coordinates):
                continue
            description = str(event.get("Description") or event.get("Comment") or "Traffic event")
            roadway = str(event.get("RoadwayName") or event.get("Location") or "Affected roadway")
            combined = f"{roadway} {description} {event.get('EventType') or ''}".lower()
            category = "bridge" if "bridge" in combined else "road"
            is_closure = bool(event.get("IsFullClosure")) or "closure" in combined or "closed" in combined
            title = f"{'Closure' if is_closure else 'Traffic event'}: {roadway}"
            alerts.append(
                EmergencyAlert(
                    id=f"511ny-{event.get('ID') or event.get('Id') or roadway}",
                    category=category,
                    title=title[:300],
                    summary=description[:1_000],
                    severity=str(event.get("Severity") or ("Closure" if is_closure else "Advisory")),
                    observed_at=self._source_timestamp(event.get("LastUpdated") or event.get("Reported")),
                    source_name="511NY / NYSDOT",
                    source_url="https://511ny.org/",
                )
            )
        return alerts[:30], None

    @staticmethod
    def _is_new_york(coordinates: Coordinates) -> bool:
        return 40.4 <= coordinates.latitude <= 45.1 and -79.9 <= coordinates.longitude <= -71.7

    @staticmethod
    def _source_timestamp(value: Any) -> str | None:
        if value is None:
            return None
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            return str(value) or None

    @staticmethod
    def _within_radius(event: dict[str, Any], center: Coordinates, radius_miles: float = 75) -> bool:
        try:
            latitude = float(event.get("Latitude"))
            longitude = float(event.get("Longitude"))
        except (TypeError, ValueError):
            return False
        latitude_miles = latitude - center.latitude
        longitude_miles = (longitude - center.longitude) * cos(radians(center.latitude))
        return (latitude_miles * latitude_miles + longitude_miles * longitude_miles) ** 0.5 * 69 <= radius_miles

    def _get_cached(self, cache_key: str) -> EmergencyFeedResponse | None:
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if not cached or cached[0] < monotonic():
                return None
            return cached[1]

    def _cache_result(self, cache_key: str, result: EmergencyFeedResponse) -> None:
        with self._cache_lock:
            self._cache[cache_key] = (monotonic() + self._cache_ttl_seconds, result)
