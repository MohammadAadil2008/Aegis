from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from app.schemas import (
    BridgeAnalysis,
    Coordinates,
    LiveIntelligence,
    MapAsset,
    RiskAssessment,
    RiskLevel,
)


class BridgeAnalysisService:
    """Creates transparent operational exposure estimates for mapped nearby bridges."""

    _facility_radius_km = 5.0
    _alternate_crossing_radius_km = 5.0

    def build(self, live: LiveIntelligence | None, risk: RiskAssessment) -> list[BridgeAnalysis]:
        if not live or not live.bridge_assets:
            return []

        assessed_asset = live.bridge_assets[0]
        available_sources = {source.id for source in live.sources}
        analyses = []
        for index, bridge in enumerate(live.bridge_assets[:30]):
            is_assessed_asset = index == 0
            nearby_facilities = [
                facility
                for facility in live.critical_infrastructure
                if self._distance_km(bridge.coordinates, facility.coordinates) <= self._facility_radius_km
            ]
            hospitals = sum(facility.category == "hospital" for facility in nearby_facilities)
            schools = sum(facility.category == "school" for facility in nearby_facilities)
            alternatives = sum(
                other is not bridge
                and self._distance_km(bridge.coordinates, other.coordinates)
                <= self._alternate_crossing_radius_km
                for other in live.bridge_assets
            )
            importance, importance_basis = self._importance(hospitals, schools)
            traffic_impact, traffic_basis = self._traffic_impact(importance, alternatives)
            risk_level, risk_scope, risk_basis = self._risk_estimate(
                bridge, is_assessed_asset, live, risk
            )
            source_ids = ["openstreetmap-bridges"]
            if nearby_facilities:
                source_ids.append("openstreetmap-critical-infrastructure")
            if live.flood_screening:
                source_ids.append("aegis-risk-model")
            if is_assessed_asset:
                source_ids.extend(["operator-field-report", "operator-assessment-inputs"])
            source_ids = [source_id for source_id in source_ids if source_id in available_sources or source_id.startswith("operator-") or source_id == "aegis-risk-model"]
            if not source_ids:
                source_ids = ["operator-assessment-inputs"]
            analyses.append(
                BridgeAnalysis(
                    bridge_id=f"bridge-{index}",
                    name=bridge.name,
                    coordinates=bridge.coordinates,
                    distance_km=round(self._distance_km(assessed_asset.coordinates, bridge.coordinates), 1),
                    risk_level=risk_level,
                    risk_scope=risk_scope,
                    importance=importance,
                    nearby_hospitals=hospitals,
                    nearby_schools=schools,
                    traffic_impact=traffic_impact,
                    alternative_crossings=alternatives,
                    risk_basis=risk_basis,
                    importance_basis=importance_basis,
                    traffic_impact_basis=traffic_basis,
                    source_ids=list(dict.fromkeys(source_ids))[:6],
                    limitations=self._limitations(is_assessed_asset, nearby_facilities),
                )
            )
        return analyses

    def _risk_estimate(
        self,
        bridge: MapAsset,
        is_assessed_asset: bool,
        live: LiveIntelligence,
        assessment_risk: RiskAssessment,
    ) -> tuple[RiskLevel, str, str]:
        if is_assessed_asset:
            return (
                assessment_risk.risk_level,
                "full_assessment",
                f"Full Aegis assessment for the operator-selected bridge: {assessment_risk.score}/100.",
            )

        screening = live.flood_screening
        if not screening:
            return (
                RiskLevel.LOW,
                "flood_exposure",
                "No flood-screening area was available; structural condition was not estimated.",
            )

        distance_meters = self._distance_km(bridge.coordinates, screening.center) * 1_000
        if distance_meters <= screening.radius_meters:
            exposure = (
                assessment_risk.risk_level
                if assessment_risk.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
                else RiskLevel.MODERATE
            )
            return (
                exposure,
                "flood_exposure",
                f"Mapped inside the {screening.classification.lower()} area; this is exposure screening, not a structural rating.",
            )
        if distance_meters <= screening.radius_meters * 2 and assessment_risk.risk_level in {
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        }:
            return (
                RiskLevel.MODERATE,
                "flood_exposure",
                "Mapped near the flood-screening area while the assessed bridge has elevated risk; structural condition was not estimated.",
            )
        return (
            RiskLevel.LOW,
            "flood_exposure",
            "Outside the mapped flood-screening area; structural condition was not estimated.",
        )

    @staticmethod
    def _importance(hospitals: int, schools: int) -> tuple[str, str]:
        score = hospitals * 3 + schools * 2
        if score >= 6:
            level = "CRITICAL"
        elif score >= 3:
            level = "HIGH"
        elif score >= 1:
            level = "MODERATE"
        else:
            level = "LOW"
        return (
            level,
            f"{hospitals} mapped hospital(s) and {schools} mapped school(s) within 5 km; operational importance is a facility-proximity proxy.",
        )

    @staticmethod
    def _traffic_impact(importance: str, alternatives: int) -> tuple[str, str]:
        if alternatives <= 1 and importance in {"HIGH", "CRITICAL"}:
            level = "HIGH"
        elif alternatives <= 3 or importance in {"HIGH", "CRITICAL"}:
            level = "MODERATE"
        else:
            level = "LOW"
        return (
            level,
            f"{alternatives} mapped alternative crossing(s) within 5 km; this is an access proxy, not measured traffic volume.",
        )

    @staticmethod
    def _limitations(is_assessed_asset: bool, nearby_facilities: list[object]) -> list[str]:
        limitations = [
            "No measured traffic volume, load rating, inspection record, or closure status was used."
        ]
        if not is_assessed_asset:
            limitations.append("Nearby bridge risk is flood exposure only; its structural condition is unknown.")
        if not nearby_facilities:
            limitations.append("No mapped hospitals or schools were returned within the 5 km screening radius.")
        return limitations

    @staticmethod
    def _distance_km(first: Coordinates, second: Coordinates) -> float:
        latitude_delta = radians(second.latitude - first.latitude)
        longitude_delta = radians(second.longitude - first.longitude)
        latitude_one = radians(first.latitude)
        latitude_two = radians(second.latitude)
        haversine = sin(latitude_delta / 2) ** 2 + cos(latitude_one) * cos(latitude_two) * sin(longitude_delta / 2) ** 2
        return 6_371 * 2 * asin(sqrt(haversine))
