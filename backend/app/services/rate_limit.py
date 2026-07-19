from __future__ import annotations

from collections import deque
from threading import Lock
from time import monotonic


class InMemoryRateLimiter:
    """Small single-process limiter for public MVP endpoints.

    A shared store should replace this before running multiple application instances.
    """

    def __init__(self) -> None:
        self._requests: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def allow(self, client_id: str, bucket: str, limit: int, window_seconds: float) -> bool:
        now = monotonic()
        key = (client_id, bucket)
        with self._lock:
            requests = self._requests.setdefault(key, deque())
            while requests and requests[0] <= now - window_seconds:
                requests.popleft()
            if len(requests) >= limit:
                return False
            requests.append(now)
            return True
