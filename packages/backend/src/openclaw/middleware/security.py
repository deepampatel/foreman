"""Security headers middleware.

Learn: Adds standard security headers to every response.
These headers protect against common web attacks:
- X-Content-Type-Options: prevents MIME-type sniffing
- X-Frame-Options: prevents clickjacking
- X-XSS-Protection: legacy XSS filter (still useful for older browsers)
- Referrer-Policy: limits referrer info leakage
- Strict-Transport-Security: forces HTTPS (only on HTTPS connections)
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Only add HSTS on HTTPS connections
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
