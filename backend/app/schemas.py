from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RiskLevel(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class OfficialBridge(BaseModel):
    """A bridge record retrieved server-side from the FHWA National Bridge Inventory."""

    nbi_record_id: str = Field(pattern=r"^[0-9]{1,12}$")
    name: str = Field(min_length=1, max_length=240)
    coordinates: Coordinates
    route: str | None = Field(default=None, max_length=160)
    location_description: str | None = Field(default=None, max_length=240)
    year_built: int | None = Field(default=None, ge=1800, le=2100)
    condition_score: int | None = Field(default=None, ge=0, le=100)
    deck_condition_code: int | None = Field(default=None, ge=0, le=9)
    superstructure_condition_code: int | None = Field(default=None, ge=0, le=9)
    substructure_condition_code: int | None = Field(default=None, ge=0, le=9)
    average_daily_traffic: int | None = Field(default=None, ge=0)
    traffic_year: int | None = Field(default=None, ge=1900, le=2100)
    last_inspection_date: str | None = Field(default=None, max_length=32)
    data_as_of: str | None = Field(default=None, max_length=32)
    source_url: str
    limitations: list[str] = Field(default_factory=list)


class BridgeSearchResponse(BaseModel):
    location: str
    coordinates: Coordinates | None = None
    bridges: list[OfficialBridge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AssessmentRequest(BaseModel):
    location: str = Field(min_length=3, max_length=160)
    asset_name: str = Field(min_length=3, max_length=160)
    official_bridge_id: str | None = Field(default=None, pattern=r"^[0-9]{1,12}$")
    field_report: str = Field(min_length=10, max_length=2_000)
    forecast_rainfall_mm: float = Field(ge=0, le=1_000)
    forecast_wind_kph: float = Field(default=0, ge=0, le=400)
    river_rise_m: float = Field(default=0, ge=0, le=30)
    condition_score: int = Field(ge=0, le=100)
    asset_age_years: int = Field(ge=0, le=250)
    observed_scour: bool = False
    emergency_access_route: bool = True
    use_live_data: bool = True
    demo_scenario: bool = False

    @field_validator("official_bridge_id", mode="before")
    @classmethod
    def normalize_optional_bridge_id(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("field_report")
    @classmethod
    def strip_report(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field_report must contain non-whitespace text")
        return normalized


class OperatorDecisionRequest(BaseModel):
    """A human decision recorded against a completed assessment audit snapshot."""

    operator_identifier: str = Field(min_length=2, max_length=160)
    decision: str = Field(min_length=3, max_length=500)
    rationale: str = Field(min_length=3, max_length=2_000)


class OperatorDecisionResponse(BaseModel):
    decision_id: str
    assessment_id: str
    recorded_at: str


class AgentFinding(BaseModel):
    agent: str
    status: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)
    duration_ms: int | None = Field(default=None, ge=0)


class AgentProgressEvent(BaseModel):
    agent: str
    status: str
    message: str
    duration_ms: int | None = Field(default=None, ge=0)


class AssetInformation(BaseModel):
    name: str
    location: str
    condition_score: int = Field(ge=0, le=100)
    age_years: int = Field(ge=0, le=250)
    observed_scour: bool
    emergency_access_route: bool
    field_report: str


class WeatherForecastWindow(BaseModel):
    hours_ahead: int = Field(ge=1, le=48)
    forecast_end: str
    precipitation_mm: float = Field(ge=0)
    wind_gust_kph: float = Field(ge=0)


class WeatherSnapshot(BaseModel):
    source: str
    observed_at: str | None = None
    precipitation_next_24h_mm: float = Field(ge=0)
    wind_gust_kph: float = Field(ge=0)
    weather_code: int | None = None
    forecast_windows: list[WeatherForecastWindow] = Field(default_factory=list)


class GaugeReading(BaseModel):
    site_id: str
    site_name: str
    coordinates: Coordinates
    observed_at: str | None = None
    stage_ft: float | None = None
    flow_cfs: float | None = None


class DailyDischargeForecast(BaseModel):
    forecast_date: str
    discharge_m3s: float = Field(ge=0)
    peak_discharge_m3s: float = Field(ge=0)


class FloodForecast(BaseModel):
    source: str
    forecast_start: str
    river_discharge_m3s: float = Field(ge=0)
    peak_7day_discharge_m3s: float = Field(ge=0)
    daily_discharge: list[DailyDischargeForecast] = Field(default_factory=list)


class EvidenceSource(BaseModel):
    """A traceable source that may be cited by the Incident Commander."""

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    label: str
    provider: str
    url: str | None = None


class WeatherAlert(BaseModel):
    event: str
    severity: str | None = None
    headline: str
    effective: str | None = None
    expires: str | None = None


class SeismicEvent(BaseModel):
    event_id: str
    magnitude: float = Field(ge=0)
    place: str
    occurred_at: str
    coordinates: Coordinates


class RadarLayer(BaseModel):
    tile_url: str
    observed_at: str | None = None
    attribution: str


class TerrainProfile(BaseModel):
    elevation_meters: float
    source: str


class CriticalInfrastructureAsset(BaseModel):
    name: str
    category: str
    coordinates: Coordinates
    source: str


class MapAsset(BaseModel):
    name: str
    coordinates: Coordinates
    source: str
    risk_level: RiskLevel | None = None


class RoutePlan(BaseModel):
    geometry: list[Coordinates]
    distance_km: float = Field(ge=0)
    duration_minutes: float = Field(ge=0)
    label: str


class FloodScreeningArea(BaseModel):
    center: Coordinates
    radius_meters: int = Field(ge=100)
    classification: str
    disclaimer: str


class CitedStatement(BaseModel):
    text: str = Field(min_length=1, max_length=800)
    source_ids: list[str] = Field(min_length=1, max_length=6)


class ScoreComponent(BaseModel):
    """A deterministic contribution to the composite risk score."""

    label: str = Field(min_length=1, max_length=100)
    points: int = Field(ge=0, le=100)
    max_points: int = Field(ge=1, le=100)
    explanation: str = Field(min_length=1, max_length=500)
    source_ids: list[str] = Field(min_length=1, max_length=6)


class RiskExplanation(BaseModel):
    """Traceable evidence and known limits for a deterministic assessment."""

    score_components: list[ScoreComponent] = Field(default_factory=list)
    positive_evidence: list[CitedStatement] = Field(default_factory=list)
    negative_evidence: list[CitedStatement] = Field(default_factory=list)
    confidence_rationale: CitedStatement | None = None
    missing_data: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    risk_level: RiskLevel
    score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    reasons: list[str]
    recommended_actions: list[str]
    explanation: RiskExplanation = Field(default_factory=RiskExplanation)


class TimelineEntry(BaseModel):
    """A time-bounded observation or forecast with traceable supporting sources."""

    label: str = Field(min_length=1, max_length=40)
    hours_ahead: int = Field(ge=0, le=24)
    kind: str = Field(pattern=r"^(observation|forecast)$")
    weather: CitedStatement
    river_level: CitedStatement
    flood_risk: CitedStatement
    bridge_status: CitedStatement
    recommended_action: CitedStatement
    limitations: list[str] = Field(default_factory=list)


class EmergencyAlert(BaseModel):
    """A public-agency alert, never an Aegis or model-generated conclusion."""

    id: str = Field(min_length=1, max_length=160)
    category: str = Field(pattern=r"^(weather|flood|road|bridge)$")
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=1_000)
    severity: str | None = Field(default=None, max_length=80)
    observed_at: str | None = None
    source_name: str = Field(min_length=1, max_length=160)
    source_url: str | None = None
    verified: bool = True


class EmergencyFeedResponse(BaseModel):
    location: str
    refreshed_at: str
    alerts: list[EmergencyAlert] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BridgeAnalysis(BaseModel):
    """A mapped bridge's operational exposure, not an engineering condition rating."""

    bridge_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    coordinates: Coordinates
    distance_km: float = Field(ge=0)
    risk_level: RiskLevel
    risk_scope: str = Field(pattern=r"^(full_assessment|flood_exposure)$")
    importance: str = Field(pattern=r"^(LOW|MODERATE|HIGH|CRITICAL)$")
    nearby_hospitals: int = Field(ge=0)
    nearby_schools: int = Field(ge=0)
    traffic_impact: str = Field(pattern=r"^(LOW|MODERATE|HIGH)$")
    alternative_crossings: int = Field(ge=0)
    risk_basis: str = Field(min_length=1, max_length=600)
    importance_basis: str = Field(min_length=1, max_length=600)
    traffic_impact_basis: str = Field(min_length=1, max_length=600)
    source_ids: list[str] = Field(min_length=1, max_length=6)
    limitations: list[str] = Field(default_factory=list)


class ActionPlanSection(BaseModel):
    """Separates evidence observations from human-approved operational guidance."""

    title: str = Field(min_length=1, max_length=120)
    observations: list[CitedStatement] = Field(default_factory=list)
    recommendations: list[CitedStatement] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class EmergencyActionPlan(BaseModel):
    immediate_actions: ActionPlanSection
    plan_30_minutes: ActionPlanSection
    plan_2_hours: ActionPlanSection
    plan_12_hours: ActionPlanSection
    public_communication: ActionPlanSection
    inspection_priorities: ActionPlanSection
    resource_deployment: ActionPlanSection
    limitations: list[str] = Field(default_factory=list)


class IncidentCommanderBrief(BaseModel):
    """Validated AI synthesis. The deterministic assessment remains authoritative."""

    available: bool
    executive_summary: str
    risk_level: RiskLevel
    confidence_score: int = Field(ge=0, le=100)
    reasoning: list[CitedStatement] = Field(default_factory=list)
    recommended_actions: list[CitedStatement] = Field(default_factory=list)
    immediate_priorities: list[CitedStatement] = Field(default_factory=list)
    long_term_recommendations: list[CitedStatement] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    warning: str | None = None


class LiveIntelligence(BaseModel):
    enabled: bool
    resolved_location: str | None = None
    coordinates: Coordinates | None = None
    weather: WeatherSnapshot | None = None
    flood_forecast: FloodForecast | None = None
    nearest_gauge: GaugeReading | None = None
    bridge_assets: list[MapAsset] = Field(default_factory=list)
    flood_screening: FloodScreeningArea | None = None
    alternate_route: RoutePlan | None = None
    weather_alerts: list[WeatherAlert] = Field(default_factory=list)
    seismic_events: list[SeismicEvent] = Field(default_factory=list)
    radar_layer: RadarLayer | None = None
    terrain: TerrainProfile | None = None
    critical_infrastructure: list[CriticalInfrastructureAsset] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AssessmentResponse(BaseModel):
    assessment_id: str
    status: str
    asset: AssetInformation
    official_bridge: OfficialBridge | None = None
    risk: RiskAssessment
    timeline: list[TimelineEntry] = Field(default_factory=list)
    bridge_analysis: list[BridgeAnalysis] = Field(default_factory=list)
    emergency_action_plan: EmergencyActionPlan | None = None
    findings: list[AgentFinding]
    public_alert_draft: str
    situation_report: str
    live_intelligence: LiveIntelligence | None = None
    incident_commander: IncidentCommanderBrief | None = None
    report_url: str | None = None
    demo_scenario: bool = False
    narrative_enriched: bool = False
    human_review_required: bool = True
