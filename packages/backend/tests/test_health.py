"""Health endpoint tests."""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    """Health endpoint should return server status and version."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["server"] == "ok"
    assert "version" in data
