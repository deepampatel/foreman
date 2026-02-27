"""Rate limiting middleware — Redis-based sliding window.

Learn: Uses a per-minute sliding window counter stored in Redis.
Each IP gets a counter key like "openclaw:rl:{ip}:{bucket}:{minute}".
Auth endpoints get a stricter limit (10/min) to prevent brute-force.

Gracefully skips rate limiting if Redis is unavailable (e.g., in tests).
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-based rate limiting per IP per minute."""

    def __init__(self, app, default_rpm: int = 100, auth_rpm: int = 10):
        super().__init__(app)
        self.default_rpm = default_rpm
        self.auth_rpm = auth_rpm

    async def dispatch(self, request: Request, call_next) -> Response:
        # Try to get Redis — skip rate limiting if unavailable
        try:
            from openclaw.realtime.pubsub import get_redis

            redis = get_redis()
        except Exception:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Stricter limit for auth endpoints
        is_auth = path.startswith("/api/v1/auth/login") or path.startswith(
            "/api/v1/auth/register"
        )
        rpm = self.auth_rpm if is_auth else self.default_rpm

        # Sliding window key: per IP, per bucket type, per minute
        window = int(time.time() // 60)
        bucket = "auth" if is_auth else "api"
        key = f"openclaw:rl:{client_ip}:{bucket}:{window}"

        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 120)  # 2-min TTL for safety

            if count > rpm:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again later."},
                    headers={"Retry-After": "60"},
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(rpm)
            response.headers["X-RateLimit-Remaining"] = str(max(0, rpm - count))
            return response
        except Exception:
            # Redis error — don't block the request
            return await call_next(request)
