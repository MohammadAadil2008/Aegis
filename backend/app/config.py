from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded only from environment variables."""

    groq_api_key: str | None
    groq_model: str | None
    enable_groq_enrichment: bool
    enable_groq_incident_commander: bool = False
    ny511_api_key: str | None = None
    database_url: str | None = None

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            groq_api_key=os.getenv("GROQ_API_KEY") or None,
            groq_model=os.getenv("GROQ_MODEL") or None,
            enable_groq_enrichment=os.getenv("ENABLE_GROQ_ENRICHMENT", "false").lower()
            == "true",
            enable_groq_incident_commander=os.getenv(
                "ENABLE_GROQ_INCIDENT_COMMANDER", "false"
            ).lower()
            == "true",
            ny511_api_key=os.getenv("NY511_API_KEY") or None,
            database_url=os.getenv("DATABASE_URL") or None,
        )
