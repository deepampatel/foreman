"""Health check endpoint.

Learn: Simple GET endpoint that verifies the server is running
and dependencies (Postgres, Redis) are reachable.
"""

from fastapi import APIRouter
from sqlalchemy import text

from openclaw import __version__
from openclaw.db.engine import engine

router = APIRouter()


@router.get("/health")
async def health_check():
    """Check server health and dependency connectivity."""
    checks = {"server": "ok", "version": __version__}

    # Check Postgres
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # Check Redis
    try:
        from redis.asyncio import from_url
        from openclaw.config import settings

        r = from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    status = "healthy" if all(
        v == "ok" for k, v in checks.items() if k != "version"
    ) else "degraded"

    return {"status": status, **checks}
