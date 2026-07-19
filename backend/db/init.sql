CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS assessment_audit (
    assessment_id UUID PRIMARY KEY,
    bridge_id TEXT,
    assessed_at TIMESTAMPTZ NOT NULL,
    bridge_geometry geometry(Point, 4326),
    risk_score SMALLINT NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MODERATE', 'HIGH', 'CRITICAL')),
    assessment_request JSONB NOT NULL,
    evidence_snapshot JSONB NOT NULL,
    sources_snapshot JSONB NOT NULL,
    assessment_snapshot JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS assessment_audit_assessed_at_idx ON assessment_audit (assessed_at DESC);
CREATE INDEX IF NOT EXISTS assessment_audit_bridge_id_idx ON assessment_audit (bridge_id);
CREATE INDEX IF NOT EXISTS assessment_audit_bridge_geometry_idx ON assessment_audit USING GIST (bridge_geometry);

CREATE TABLE IF NOT EXISTS operator_decision_audit (
    decision_id UUID PRIMARY KEY,
    assessment_id UUID NOT NULL REFERENCES assessment_audit(assessment_id) ON DELETE RESTRICT,
    recorded_at TIMESTAMPTZ NOT NULL,
    operator_identifier TEXT NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS operator_decision_audit_assessment_idx ON operator_decision_audit (assessment_id, recorded_at DESC);
