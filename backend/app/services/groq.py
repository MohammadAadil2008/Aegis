from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.config import Settings
from app.schemas import RiskAssessment

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NarrativeDrafts:
    public_alert_draft: str
    situation_report: str
    enriched: bool


class GroqNarrativeService:
    """Optional language enhancement isolated from the safety-critical scoring path.

    Install the optional `groq` dependency only when this capability is enabled.
    The API key remains in the process environment and is never returned to clients.
    """

    def __init__(self, settings: Settings) -> None:
        self._enabled = settings.enable_groq_enrichment
        self._api_key = settings.groq_api_key
        self._model = settings.groq_model

    @property
    def is_configured(self) -> bool:
        return bool(self._enabled and self._api_key and self._model)

    def enhance(
        self,
        *,
        asset_name: str,
        location: str,
        risk: RiskAssessment,
        fallback_public_alert: str,
        fallback_situation_report: str,
    ) -> NarrativeDrafts:
        """Improve operator-facing drafts without participating in risk calculation.

        The LLM receives only already-calculated assessment facts. Any provider or
        parsing failure safely returns the deterministic fallback drafts.
        """
        fallback = NarrativeDrafts(
            public_alert_draft=fallback_public_alert,
            situation_report=fallback_situation_report,
            enriched=False,
        )
        if not self.is_configured:
            return fallback

        assessment_facts = {
            "asset_name": asset_name,
            "location": location,
            "risk_level": risk.risk_level.value,
            "risk_score": risk.score,
            "confidence": risk.confidence,
            "reasons": risk.reasons,
            "recommended_actions": risk.recommended_actions,
        }
        try:
            # Imported here so a disabled enrichment path never depends on the SDK.
            from groq import Groq

            client = Groq(api_key=self._api_key)
            completion = client.chat.completions.create(
                model=self._model,
                temperature=0.1,
                max_completion_tokens=500,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You edit emergency-management draft communications. "
                            "Use only the supplied assessment facts. Do not change risk level, score, "
                            "confidence, reasons, or recommended actions. Do not issue orders, claim an "
                            "alert was sent, or add facts. Return exactly one JSON object with string keys "
                            "public_alert_draft and situation_report."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(assessment_facts),
                    },
                ],
            )
            content = completion.choices[0].message.content
            if not content:
                return fallback
            payload = json.loads(content)
            public_alert = self._approved_alert(payload.get("public_alert_draft"), fallback_public_alert)
            situation_report = self._approved_report(
                payload.get("situation_report"), fallback_situation_report
            )
            return NarrativeDrafts(public_alert, situation_report, enriched=True)
        except (ImportError, json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError):
            logger.warning("Groq narrative enrichment returned an unusable response.")
            return fallback
        except Exception:
            logger.warning("Groq narrative enrichment failed; using deterministic drafts.")
            return fallback

    @staticmethod
    def _approved_alert(candidate: object, fallback: str) -> str:
        if not isinstance(candidate, str) or not candidate.strip() or len(candidate) > 800:
            return fallback
        alert = candidate.strip()
        if not alert.startswith("DRAFT - HUMAN APPROVAL REQUIRED:"):
            return f"DRAFT - HUMAN APPROVAL REQUIRED: {alert}"
        return alert

    @staticmethod
    def _approved_report(candidate: object, fallback: str) -> str:
        if not isinstance(candidate, str) or not candidate.strip() or len(candidate) > 3_000:
            return fallback
        report = candidate.strip()
        authority_note = "Decision authority: Human review required before any public alert, closure, or dispatch."
        if authority_note not in report:
            report = f"{report}\n{authority_note}"
        return report
