from __future__ import annotations

from datetime import datetime, timezone
from math import cos
from typing import Any

import httpx

from app.schemas import BridgeSearchResponse, Coordinates, OfficialBridge
from app.services.live_data import LiveDataService


class OfficialBridgeVerificationError(ValueError):
    """Raised when a requested official bridge record cannot be re-verified."""


class BridgeCatalogService:
    """Reads selectable U.S. bridge records from the FHWA National Bridge Inventory."""

    _layer_url = (
        "https://geo.dot.gov/server/rest/services/Hosted/"
        "National_Bridge_Inventory/FeatureServer/0"
    )
    _query_url = f"{_layer_url}/query"
    _source_url = "https://www.fhwa.dot.gov/bridge/nbi.cfm"
    _out_fields = ",".join(
        (
            "fid",
            "structure_",
            "facility_c",
            "location_0",
            "route_numb",
            "year_built",
            "deck_cond_",
            "superstruc",
            "substructu",
            "adt_029",
            "year_adt_0",
            "date_of_in",
            "date",
            "submitted_",
        )
    )

    def __init__(self, location_service: LiveDataService | None = None) -> None:
        self._location_service = location_service or LiveDataService()

    def search(self, location: str) -> BridgeSearchResponse:
        resolved = self._location_service.resolve_location(location)
        if resolved is None:
            return BridgeSearchResponse(
                location=location,
                warnings=["Location could not be resolved. Try a U.S. city, state, or ZIP code."],
            )
        resolved_name, coordinates = resolved
        data = self._query_nearby(coordinates)
        features = (data or {}).get("features") or []
        bridges = [bridge for feature in features if (bridge := self._to_bridge(feature)) is not None]
        bridges.sort(key=lambda bridge: self._distance_squared(coordinates, bridge.coordinates))
        warnings = []
        if data is None:
            warnings.append("The official FHWA bridge inventory is temporarily unavailable.")
        elif not bridges:
            warnings.append("No official bridge records were returned within 20 km of this location.")
        return BridgeSearchResponse(
            location=resolved_name,
            coordinates=coordinates,
            bridges=bridges,
            warnings=warnings,
        )

    def get(self, nbi_record_id: str) -> OfficialBridge | None:
        if not nbi_record_id.isdigit():
            return None
        data = self._request_json(
            self._query_url,
            params={
                "f": "json",
                "where": f"fid={int(nbi_record_id)}",
                "outFields": self._out_fields,
                "returnGeometry": "true",
                "outSR": "4326",
            },
        )
        features = (data or {}).get("features") or []
        return self._to_bridge(features[0]) if features else None

    def _query_nearby(self, coordinates: Coordinates) -> dict[str, Any] | None:
        return self._request_json(
            self._query_url,
            params={
                "f": "json",
                "geometry": f"{coordinates.longitude},{coordinates.latitude}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "distance": "20000",
                "units": "esriSRUnit_Meter",
                "outFields": self._out_fields,
                "returnGeometry": "true",
                "outSR": "4326",
                "resultRecordCount": "30",
            },
        )

    @staticmethod
    def _request_json(url: str, **kwargs: Any) -> dict[str, Any] | None:
        try:
            response = httpx.get(
                url,
                timeout=10.0,
                follow_redirects=True,
                headers={"User-Agent": "Aegis-MVP/0.1 (educational decision support)"},
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) and "error" not in payload else None
        except (httpx.HTTPError, ValueError):
            return None

    @classmethod
    def _to_bridge(cls, feature: object) -> OfficialBridge | None:
        if not isinstance(feature, dict):
            return None
        attributes = feature.get("attributes")
        geometry = feature.get("geometry")
        if not isinstance(attributes, dict) or not isinstance(geometry, dict):
            return None
        record_id = cls._int(attributes.get("fid"))
        latitude = cls._float(geometry.get("y"))
        longitude = cls._float(geometry.get("x"))
        if record_id is None or latitude is None or longitude is None:
            return None
        try:
            coordinates = Coordinates(latitude=latitude, longitude=longitude)
        except ValueError:
            return None

        condition_codes = {
            "deck": cls._condition_code(attributes.get("deck_cond_")),
            "superstructure": cls._condition_code(attributes.get("superstruc")),
            "substructure": cls._condition_code(attributes.get("substructu")),
        }
        usable_codes = [code for code in condition_codes.values() if code is not None and code > 0]
        condition_score = round(min(usable_codes) / 9 * 100) if usable_codes else None
        year_built = cls._year(attributes.get("year_built"))
        facility = cls._text(attributes.get("facility_c"))
        structure = cls._text(attributes.get("structure_"))
        limitations = [
            "FHWA NBI values are inventory and inspection data, not a real-time structural sensor feed.",
            "The Aegis condition score is a conservative normalization of the lowest available NBI component condition code; it is not an engineering certification.",
        ]
        if condition_score is None:
            limitations.append("No usable NBI deck, superstructure, or substructure condition code was returned.")
        if year_built is None:
            limitations.append("No usable NBI year-built value was returned.")
        return OfficialBridge(
            nbi_record_id=str(record_id),
            name=facility or f"NBI bridge {structure or record_id}",
            coordinates=coordinates,
            route=cls._text(attributes.get("route_numb")),
            location_description=cls._text(attributes.get("location_0")),
            year_built=year_built,
            condition_score=condition_score,
            deck_condition_code=condition_codes["deck"],
            superstructure_condition_code=condition_codes["superstructure"],
            substructure_condition_code=condition_codes["substructure"],
            average_daily_traffic=cls._non_negative_int(attributes.get("adt_029")),
            traffic_year=cls._year(attributes.get("year_adt_0")),
            last_inspection_date=cls._month_year(attributes.get("date_of_in")),
            data_as_of="FHWA NBI 2023 snapshot",
            source_url=cls._source_url,
            limitations=limitations,
        )

    @staticmethod
    def _text(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _float(value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _int(cls, value: object) -> int | None:
        numeric = cls._float(value)
        return int(numeric) if numeric is not None and numeric.is_integer() else None

    @classmethod
    def _non_negative_int(cls, value: object) -> int | None:
        numeric = cls._int(value)
        return numeric if numeric is not None and numeric >= 0 else None

    @classmethod
    def _year(cls, value: object) -> int | None:
        year = cls._int(value)
        return year if year is not None and 1800 <= year <= datetime.now(timezone.utc).year else None

    @classmethod
    def _condition_code(cls, value: object) -> int | None:
        code = cls._int(value)
        return code if code is not None and 0 <= code <= 9 else None

    @staticmethod
    def _month_year(value: object) -> str | None:
        digits = "".join(character for character in str(value or "") if character.isdigit())
        if len(digits) == 8:
            year = int(digits[:4])
            month = int(digits[4:6])
            return f"{year:04d}-{month:02d}" if 1800 <= year <= datetime.now(timezone.utc).year and 1 <= month <= 12 else None
        if not digits or len(digits) > 4:
            return None
        digits = digits.zfill(4)
        month = int(digits[:-2])
        year_suffix = int(digits[-2:])
        if not 1 <= month <= 12:
            return None
        current_suffix = datetime.now(timezone.utc).year % 100
        year = 2000 + year_suffix if year_suffix <= current_suffix else 1900 + year_suffix
        return f"{year:04d}-{month:02d}"

    @staticmethod
    def _distance_squared(first: Coordinates, second: Coordinates) -> float:
        latitude_scale = 69.0
        longitude_scale = 69.0 * cos(first.latitude * 0.01745329252)
        return (
            (first.latitude - second.latitude) * latitude_scale
        ) ** 2 + ((first.longitude - second.longitude) * longitude_scale) ** 2
