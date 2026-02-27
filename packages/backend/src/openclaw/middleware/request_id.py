"""Request ID middleware — unique ID per request for tracing.

Learn: Every request gets a UUID, either from the incoming
X-Request-ID header (for distributed tracing) or auto-generated.
The ID is bound to structlog's contextvars so it appears in all
log entries for that request, and returned in the response header.
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate and propagate a unique request ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Use existing request ID or generate a new one
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Bind to structlog for correlated logging
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
