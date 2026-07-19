from __future__ import annotations

from threading import Lock
from time import monotonic


class InMemoryReportStore:
    """Short-lived PDF storage for the current application process.

    This avoids writing potentially sensitive operational reports to disk. A
    database-backed encrypted store should replace it before multi-instance use.
    """

    def __init__(self, ttl_seconds: int = 3_600, max_reports: int = 100) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_reports = max_reports
        self._reports: dict[str, tuple[float, bytes]] = {}
        self._lock = Lock()

    def put(self, assessment_id: str, document: bytes) -> None:
        with self._lock:
            self._remove_expired()
            if len(self._reports) >= self._max_reports:
                oldest_id = min(self._reports, key=lambda key: self._reports[key][0])
                self._reports.pop(oldest_id, None)
            self._reports[assessment_id] = (monotonic() + self._ttl_seconds, document)

    def get(self, assessment_id: str) -> bytes | None:
        with self._lock:
            self._remove_expired()
            record = self._reports.get(assessment_id)
            return record[1] if record else None

    def _remove_expired(self) -> None:
        now = monotonic()
        expired = [key for key, (expires_at, _) in self._reports.items() if expires_at <= now]
        for key in expired:
            self._reports.pop(key, None)
