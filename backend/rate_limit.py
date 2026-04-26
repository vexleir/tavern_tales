"""
Minimal in-memory token-bucket rate limiter (D4).

The app is localhost-only, so this is primarily a safety net against runaway
frontend retry loops rather than real abuse prevention.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, rate: int, per_seconds: float) -> None:
        self.rate = rate
        self.per = per_seconds
        self._buckets: dict[str, Deque[float]] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, deque())
        cutoff = now - self.per
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.rate:
            raise HTTPException(429, "Rate limit exceeded — slow down.")
        bucket.append(now)


_chat_limiter = RateLimiter(rate=60, per_seconds=60.0)


async def chat_rate_limit(request: Request) -> None:
    host = request.client.host if request.client else "unknown"
    _chat_limiter.check(host)
