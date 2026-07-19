from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import AssessmentRequest, AssessmentResponse, OperatorDecisionRequest, OperatorDecisionResponse


class AuditStoreError(RuntimeError):
    """Raised when configured durable audit storage cannot safely record an event."""


class PostgresAuditStore:
    """PostgreSQL/PostGIS audit persistence, enabled only when DATABASE_URL is configured."""

    def __init__(self, database_url: str | None) -> None:
        self._database_url = database_url

    @property
    def enabled(self) -> bool:
        return bool(self._database_url)

    def persist_assessment(self, request: AssessmentRequest, assessment: AssessmentResponse) -> None:
        if not self.enabled:
            return
        psycopg = self._driver()
        bridge = assessment.official_bridge
        coordinates = bridge.coordinates if bridge else None
        evidence = assessment.live_intelligence.model_dump(mode="json") if assessment.live_intelligence else {}
        sources = evidence.get("sources", [])
        try:
            with psycopg.connect(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO assessment_audit (
                            assessment_id, bridge_id, assessed_at, bridge_geometry, risk_score, risk_level,
                            assessment_request, evidence_snapshot, sources_snapshot, assessment_snapshot
                        ) VALUES (
                            %s::uuid, %s, NOW(),
                            CASE WHEN %s IS NULL OR %s IS NULL THEN NULL
                                 ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326) END,
                            %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                        )
                        ON CONFLICT (assessment_id) DO UPDATE SET
                            bridge_id = EXCLUDED.bridge_id,
                            bridge_geometry = EXCLUDED.bridge_geometry,
                            risk_score = EXCLUDED.risk_score,
                            risk_level = EXCLUDED.risk_level,
                            assessment_request = EXCLUDED.assessment_request,
                            evidence_snapshot = EXCLUDED.evidence_snapshot,
                            sources_snapshot = EXCLUDED.sources_snapshot,
                            assessment_snapshot = EXCLUDED.assessment_snapshot
                        """,
                        (
                            assessment.assessment_id,
                            bridge.nbi_record_id if bridge else None,
                            coordinates.longitude if coordinates else None,
                            coordinates.latitude if coordinates else None,
                            coordinates.longitude if coordinates else None,
                            coordinates.latitude if coordinates else None,
                            assessment.risk.score,
                            assessment.risk.risk_level.value,
                            json.dumps(request.model_dump(mode="json")),
                            json.dumps(evidence),
                            json.dumps(sources),
                            json.dumps(assessment.model_dump(mode="json")),
                        ),
                    )
        except Exception as error:
            raise AuditStoreError("Configured audit storage could not persist the assessment.") from error

    def record_decision(
        self, assessment_id: str, decision: OperatorDecisionRequest
    ) -> OperatorDecisionResponse:
        if not self.enabled:
            raise AuditStoreError("Durable audit storage is not configured.")
        psycopg = self._driver()
        decision_id = str(uuid4())
        recorded_at = datetime.now(timezone.utc)
        try:
            with psycopg.connect(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO operator_decision_audit (
                            decision_id, assessment_id, recorded_at, operator_identifier, decision, rationale
                        ) VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s)
                        """,
                        (
                            decision_id,
                            assessment_id,
                            recorded_at,
                            decision.operator_identifier,
                            decision.decision,
                            decision.rationale,
                        ),
                    )
        except Exception as error:
            raise AuditStoreError("Configured audit storage could not record the operator decision.") from error
        return OperatorDecisionResponse(
            decision_id=decision_id,
            assessment_id=assessment_id,
            recorded_at=recorded_at.isoformat(),
        )

    def _driver(self):
        try:
            import psycopg
        except ImportError as error:
            raise AuditStoreError("PostgreSQL support is unavailable; install the configured application dependencies.") from error
        return psycopg
