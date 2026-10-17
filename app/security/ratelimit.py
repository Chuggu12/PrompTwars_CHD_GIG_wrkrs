"""Per-IP sliding-window rate limiting with periodic cleanup of idle clients."""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable
from typing import Final

from starlette.types import ASGIApp, Receive, Scope, Send

from app.constants import (
    RATE_LIMIT_AI,
    RATE_LIMIT_CLEANUP_SECONDS,
    RATE_LIMIT_DEFAULT,
    RATE_LIMIT_REPORT,
    RATE_LIMIT_SELFHEAL,
)

# (path prefix, group name, (limit, window)) - first match wins.
ROUTE_GROUPS: Final[tuple[tuple[str, str, tuple[int, int]], ...]] = (
    ("/api/selfheal", "selfheal", RATE_LIMIT_SELFHEAL),
    ("/api/report", "report", RATE_LIMIT_REPORT),
    ("/api/health/models/recheck", "report", RATE_LIMIT_REPORT),
    ("/api/ai", "ai", RATE_LIMIT_AI),
    ("/api/", "default", RATE_LIMIT_DEFAULT),
)


class RateLimiter:
    """Sliding window counter keyed by (client, group)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._windows: dict[tuple[str, str], int] = {}
        self._last_cleanup = clock()

    def __len__(self) -> int:
        return len(self._hits)

    def allow(self, client: str, group: str, limit: int, window: int) -> bool:
        now = self._clock()
        if now - self._last_cleanup > RATE_LIMIT_CLEANUP_SECONDS:
            self.cleanup(now)
        key = (client, group)
        hits = self._hits.setdefault(key, deque())
        self._windows[key] = window
        while hits and now - hits[0] >= window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

    def cleanup(self, now: float | None = None) -> None:
        """Forget clients whose most recent hit is outside their window."""
        now = self._clock() if now is None else now
        idle = [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= self._windows.get(k, 0)]
        for key in idle:
            self._hits.pop(key, None)
            self._windows.pop(key, None)
        self._last_cleanup = now


def client_ip(scope: Scope, trust_proxy: bool) -> str:
    """Client address. Behind Cloud Run's front end the real client is the last
    X-Forwarded-For entry (earlier entries can be forged by the client)."""
    if trust_proxy:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                return value.decode("latin-1").split(",")[-1].strip() or "unknown"
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


def route_group(path: str) -> tuple[str, tuple[int, int]] | None:
    for prefix, group, limits in ROUTE_GROUPS:
        if path.startswith(prefix):
            return group, limits
    return None


class RateLimitMiddleware:
    """Returns 429 with Retry-After when a client exceeds its group limit."""

    def __init__(self, app: ASGIApp, *, limiter: RateLimiter, trust_proxy: bool) -> None:
        self.app = app
        self.limiter = limiter
        self.trust_proxy = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        group = route_group(scope.get("path", "")) if scope["type"] == "http" else None
        if group is None:
            await self.app(scope, receive, send)
            return
        name, (limit, window) = group
        if self.limiter.allow(client_ip(scope, self.trust_proxy), name, limit, window):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"error": {"code": "rate_limited", "message": "Too many requests. Please wait a minute."}})
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [(b"content-type", b"application/json"), (b"retry-after", str(window).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body.encode()})
