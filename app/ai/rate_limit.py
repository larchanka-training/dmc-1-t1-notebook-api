"""Per-user sliding-window rate limiter for AI endpoints.

In-memory, per-process. Sufficient for a single ECS task; if the service
scales to multiple tasks, replace with a Redis-backed implementation.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.core.config import settings


class _SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._minute: dict[str, deque[float]] = defaultdict(deque)
        self._day: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def enforce(self, user_id: str) -> None:
        """Check and record a request for user_id. Raises HTTP 429 if over limit."""
        async with self._lock:
            now = time.monotonic()
            self._evict(self._minute[user_id], now - 60)
            self._evict(self._day[user_id], now - 86_400)

            if len(self._minute[user_id]) >= settings.ai_rate_limit_rpm:
                raise HTTPException(
                    status_code=429,
                    detail="AI rate limit exceeded: too many requests per minute",
                )
            if len(self._day[user_id]) >= settings.ai_rate_limit_rpd:
                raise HTTPException(
                    status_code=429,
                    detail="AI rate limit exceeded: daily limit reached",
                )

            self._minute[user_id].append(now)
            self._day[user_id].append(now)

    @staticmethod
    def _evict(dq: deque[float], cutoff: float) -> None:
        while dq and dq[0] < cutoff:
            dq.popleft()


ai_rate_limiter = _SlidingWindowRateLimiter()
