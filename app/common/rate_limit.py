"""
In-memory sliding-window rate limiter.

Protects the cost-bearing LLM endpoints (/assistant/ask, /answer)
from runaway or abusive request rates. Per-process (single-worker
uvicorn) — intentionally simple; swap for Redis when scaling out.

Configuration (env):
    LLM_RATE_LIMIT=<requests>/<seconds>     e.g. "30/60" (default 30 per 60s)
    ASSISTANT_RATE_LIMIT=<requests>/<seconds>  e.g. "10/60" (default 10 per 60s)
    FBR_RATE_LIMIT_DISABLED=1               disables all limiting (tests)

Usage:
    limiter = RateLimiter.from_env("ASSISTANT_RATE_LIMIT", default=10, window=60)

    @router.post("/ask", dependencies=[Depends(require_user)])
    async def handler(request: Request, ...):
        limiter.check(request)
        ...
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_SLIDE_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+(?:\.\d+)?)\s*$")


class RateLimiter:
    """Sliding-window counter keyed by bearer-token hash or client host."""

    def __init__(self, limit: int, window_seconds: float, scope: str = "llm"):
        self.limit = max(1, int(limit))
        self.window = max(1.0, float(window_seconds))
        self.scope = scope
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    @classmethod
    def from_env(
        cls,
        env_var: str,
        default_limit: int,
        default_window: float = 60.0,
    ) -> "RateLimiter":
        raw = os.getenv(env_var, "").strip()
        disabled = os.getenv("FBR_RATE_LIMIT_DISABLED", "").strip() in {"1", "true", "yes"}
        if disabled:
            return cls(limit=10**9, window_seconds=default_window, scope=env_var)
        m = _SLIDE_RE.match(raw)
        if m:
            return cls(limit=int(m.group(1)), window_seconds=float(m.group(2)), scope=env_var)
        return cls(limit=default_limit, window_seconds=default_window, scope=env_var)

    @staticmethod
    def _identity(request: Request) -> str:
        """Prefer the bearer token (per-user), fall back to client host."""
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            if token:
                return "tok:" + hashlib.sha256(token.encode()).hexdigest()[:24]
        host = getattr(request.client, "host", None) if request.client else None
        return "host:" + (host or "unknown")

    def check(self, request: Request) -> None:
        """Raise HTTP 429 (with Retry-After) when the caller exceeds the limit."""
        key = self._identity(request)
        now = time.monotonic()
        with self._lock:
            bucket = [t for t in self._hits.get(key, ()) if now - t < self.window]
            if len(bucket) >= self.limit:
                retry_after = max(1, int(self.window - (now - bucket[0])) + 1)
                self._hits[key] = bucket
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Rate limit reached ({self.limit} requests per "
                        f"{int(self.window)}s). Please retry in {retry_after}s."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
            self._hits[key] = bucket

    def current_usage(self, request: Request) -> dict:
        key = self._identity(request)
        now = time.monotonic()
        with self._lock:
            used = len([t for t in self._hits.get(key, ()) if now - t < self.window])
        return {"scope": self.scope, "used": used, "limit": self.limit,
                "window_seconds": int(self.window)}
