"""Tests for security middleware — headers, request IDs.

Learn: Rate limiting is skipped in tests (no Redis available),
so we only test security headers and request ID middleware here.
"""

import pytest


@pytest.mark.asyncio
async def test_security_headers_on_health(client):
    """Health endpoint returns security headers."""
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-XSS-Protection"] == "1; mode=block"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_request_id_generated(client):
    """Each request gets a unique X-Request-ID header."""
    r1 = await client.get("/api/v1/health")
    r2 = await client.get("/api/v1/health")
    assert "X-Request-ID" in r1.headers
    assert "X-Request-ID" in r2.headers
    # Each request gets a unique ID
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_request_id_propagated(client):
    """Incoming X-Request-ID is propagated through the response."""
    custom_id = "test-trace-12345"
    r = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": custom_id},
    )
    assert r.headers["X-Request-ID"] == custom_id


@pytest.mark.asyncio
async def test_no_hsts_on_http(client):
    """HSTS header is NOT set on HTTP connections (only HTTPS)."""
    r = await client.get("/api/v1/health")
    assert "Strict-Transport-Security" not in r.headers
