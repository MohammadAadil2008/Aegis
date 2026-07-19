from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from app.config import Settings
from app.schemas import (
    AgentFinding,
    AssessmentRequest,
    CitedStatement,
    EvidenceSource,
    IncidentCommanderBrief,
    LiveIntelligence,
    RiskAssessment,
    RiskLevel,
)

logger = logging.getLogger(__name__)


class _CommanderPayload(BaseModel):
    """The exact subset of fields that Groq is allowed to produce."""

    executive_summary: str = Field(min_length=1, max_length=1_200)
    risk_level: RiskLevel
    confidence_score: int = Field(ge=0, le=100)
    reasoning: list[CitedStatement] = Field(min_length=1, max_length=8)
    recommended_actions: list[CitedStatement] = Field(min_length=1, max_length=6)
    immediate_priorities: list[CitedStatement] = Field(min_length=1, max_length=5)
    long_term_recommendations: list[CitedStatement] = Field(min_length=1, max_length=5)
    data_gaps: list[str] = Field(max_length=12)


class GroqIncidentCommander:
    """Evidence-constrained AI synthesis kept outside the risk-calculation path."""

    def __init__(self, settings: Settings) -> None:
        self._enabled = settings.enable_groq_incident_commander
        self._api_key = settings.groq_api_key
        self._model = settings.groq_model

    @property
    def is_configured(self) -> bool:
        return bool(self._enabled and self._api_key and self._model)

    def generate(
        self,
        *,
        request: AssessmentRequest,
        risk: RiskAssessment,
        findings: list[AgentFinding],
        live_intelligence: LiveIntelligence | None,
    ) -> IncidentCommanderBrief:
        sources = self._source_catalog(live_intelligence)
        fallback = self._fallback_brief(risk, live_intelligence, sources, None)
        if not self.is_configured:
            return fallback.model_copy(
                update={
                    "warning": "Groq Incident Commander is disabled or not configured. Deterministic evidence summary shown.",
                }
            )

        facts = self._facts(request, risk, findings, live_intelligence, sources)
        try:
            from groq import Groq

            client = Groq(api_key=self._api_key)
            completion = client.chat.completions.create(
                model=self._model,
                temperature=0.0,
                max_completion_tokens=1_400,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Aegis's Incident Commander, an evidence-only decision-support "
                            "assistant. Return exactly one JSON object matching these keys: executive_summary, "
                            "risk_level, confidence_score, reasoning, recommended_actions, immediate_priorities, "
                            "long_term_recommendations, data_gaps. Each reasoning and recommendation item must "
                            "be an object with text and source_ids. Every source_ids list must be non-empty and "
                            "contain only IDs from allowed_sources. The risk_level must exactly equal the provided "
                            "deterministic_risk risk_level. Never invent measurements, alerts, locations, official "
                            "orders, closures, evacuations, or missing data. State unavailable evidence in data_gaps. "
                            "Recommendations are advisory and must preserve the requirement for human authority."
                        ),
                    },
                    {"role": "user", "content": json.dumps(facts)},
                ],
            )
            content = completion.choices[0].message.content
            if not content:
                return self._fallback_brief(risk, live_intelligence, sources, "Groq returned no content.")
            payload = _CommanderPayload.model_validate_json(content)
            self._validate_payload(payload, risk, sources, live_intelligence)
            return IncidentCommanderBrief(available=True, **payload.model_dump())
        except Exception:
            logger.warning("Groq Incident Commander failed validation or request; using deterministic summary.")
            return self._fallback_brief(
                risk,
                live_intelligence,
                sources,
                "Groq response was unavailable or failed evidence validation.",
            )

    @staticmethod
    def _facts(
        request: AssessmentRequest,
        risk: RiskAssessment,
        findings: list[AgentFinding],
        live_intelligence: LiveIntelligence | None,
        sources: list[EvidenceSource],
    ) -> dict[str, object]:
        """Minimize data sent to Groq; raw operator prose is retained only locally."""
        return {
            "assessment": {
                "asset_name": request.asset_name,
                "location": request.location,
                "operator_inputs": {
                    "condition_score": request.condition_score,
                    "asset_age_years": request.asset_age_years,
                    "observed_scour": request.observed_scour,
                    "emergency_access_route": request.emergency_access_route,
                },
                "deterministic_risk": risk.model_dump(mode="json"),
            },
            "live_intelligence": (
                live_intelligence.model_dump(mode="json", exclude_none=True)
                if live_intelligence
                else {"enabled": False, "warnings": ["Live data service was not configured."]}
            ),
            "specialist_findings": [finding.model_dump(mode="json") for finding in findings],
            "allowed_sources": [source.model_dump(mode="json") for source in sources],
        }

    @staticmethod
    def _source_catalog(live_intelligence: LiveIntelligence | None) -> list[EvidenceSource]:
        sources = [
            EvidenceSource(
                id="operator-field-report",
                label="Operator field report",
                provider="Aegis operator input",
            ),
            EvidenceSource(
                id="operator-assessment-inputs",
                label="Operator assessment inputs",
                provider="Aegis operator input",
            ),
            EvidenceSource(
                id="aegis-risk-model",
                label="Deterministic Aegis risk model",
                provider="Aegis",
            ),
        ]
        if live_intelligence:
            sources.extend(live_intelligence.sources)
        return sources

    @staticmethod
    def _validate_payload(
        payload: _CommanderPayload,
        risk: RiskAssessment,
        sources: list[EvidenceSource],
        live_intelligence: LiveIntelligence | None,
    ) -> None:
        if payload.risk_level is not risk.risk_level:
            raise ValueError("Commander attempted to change deterministic risk level.")
        valid_source_ids = {source.id for source in sources}
        statements = (
            payload.reasoning
            + payload.recommended_actions
            + payload.immediate_priorities
            + payload.long_term_recommendations
        )
        for statement in statements:
            if not set(statement.source_ids).issubset(valid_source_ids):
                raise ValueError("Commander cited an unavailable source.")
        if live_intelligence and live_intelligence.warnings and not payload.data_gaps:
            raise ValueError("Commander omitted known live-data gaps.")

    @staticmethod
    def _fallback_brief(
        risk: RiskAssessment,
        live_intelligence: LiveIntelligence | None,
        sources: list[EvidenceSource],
        warning: str | None,
    ) -> IncidentCommanderBrief:
        available_ids = {source.id for source in sources}
        supporting_ids = ["aegis-risk-model", "operator-assessment-inputs"]
        if "operator-field-report" in available_ids:
            supporting_ids.append("operator-field-report")
        for source_id in ("open-meteo-weather", "open-meteo-flood", "usgs-water", "nws-alerts"):
            if source_id in available_ids:
                supporting_ids.append(source_id)
        supporting_ids = supporting_ids[:4]
        risk_reasoning = [
            CitedStatement(text=reason, source_ids=supporting_ids) for reason in risk.reasons
        ]
        actions = [
            CitedStatement(text=action, source_ids=supporting_ids)
            for action in risk.recommended_actions
        ]
        immediate = actions[:2] or [
            CitedStatement(
                text="Maintain qualified human review of the assessment.",
                source_ids=["aegis-risk-model"],
            )
        ]
        long_term = [
            CitedStatement(
                text="Maintain inspection records and calibrate risk thresholds with validated local data.",
                source_ids=["aegis-risk-model", "operator-assessment-inputs"],
            )
        ]
        data_gaps = list(live_intelligence.warnings) if live_intelligence else [
            "Live data service was not configured."
        ]
        return IncidentCommanderBrief(
            available=False,
            executive_summary=(
                f"Deterministic assessment for {risk.risk_level} risk. "
                "A qualified authority must review all operational decisions."
            ),
            risk_level=risk.risk_level,
            confidence_score=risk.confidence,
            reasoning=risk_reasoning,
            recommended_actions=actions,
            immediate_priorities=immediate,
            long_term_recommendations=long_term,
            data_gaps=data_gaps,
            warning=warning,
        )
