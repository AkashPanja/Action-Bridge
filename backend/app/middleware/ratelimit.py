"""In-memory sliding-window rate limiter for abuse-prone auth endpoints.

Brute-force protection for login/setup/register/password-reset without new
dependencies. Single-process scope (matches the single-worker deployment);
a distributed deployment should move this to Redis.
"""

import asyncio
import os
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# path prefix -> (max requests, window seconds)
BUDGETS: dict[str, tuple[int, int]] = {
    "/api/v1/auth/login": (15, 60),
    "/api/v1/auth/register": (10, 60),
    "/api/v1/auth/setup": (10, 60),
    "/api/v1/auth/password-reset": (10, 60),
}

_hits: dict[str, list[float]] = {}
_lock = asyncio.Lock()


def _enabled() -> bool:
    return os.getenv("RATE_LIMIT_ENABLED", "true").lower() not in ("0", "false", "no")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _budget(path: str) -> tuple[int, int] | None:
    for prefix, budget in BUDGETS.items():
        if path == prefix or path.startswith(prefix + "/"):
            return budget
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _enabled():
            budget = _budget(request.url.path)
            if budget and request.method == "POST":
                max_hits, window = budget
                key = f"{_client_ip(request)}:{request.url.path}"
                now = time.monotonic()
                async with _lock:
                    stamps = [s for s in _hits.get(key, []) if now - s < window]
                    if len(stamps) >= max_hits:
                        retry_after = int(window - (now - stamps[0])) + 1
                        return JSONResponse(
                            status_code=429,
                            content={"detail": "Too many requests. Slow down."},
                            headers={"Retry-After": str(retry_after)},
                        )
                    stamps.append(now)
                    _hits[key] = stamps
        return await call_next(request)


def reset_limiter() -> None:
    """Test helper: clear all recorded windows."""
    _hits.clear()
