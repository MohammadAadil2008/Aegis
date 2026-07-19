from __future__ import annotations

from dataclasses import dataclass

from app.schemas import AssessmentRequest, LiveIntelligence


@dataclass(frozen=True)
class AgentContext:
    """Shared, immutable assessment evidence passed to every independent agent."""

    request: AssessmentRequest
    live_intelligence: LiveIntelligence | None


def available_source_ids(live_intelligence: LiveIntelligence | None) -> list[str]:
    source_ids = ["operator-field-report", "operator-assessment-inputs"]
    if live_intelligence:
        source_ids.extend(source.id for source in live_intelligence.sources)
    return source_ids
