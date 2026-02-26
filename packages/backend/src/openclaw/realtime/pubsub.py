"""Redis pub/sub — event broadcasting between services and WebSockets.

Learn: Redis pub/sub is fire-and-forget. If no one is listening, the message
is lost. That's fine for real-time UI updates (the frontend can always query
the API to catch up). Events are also stored in PostgreSQL for durability.

Channel naming: openclaw:events:{team_id}
This lets each team's WebSocket only subscribe to relevant events.
"""

import json
from typing import Any, Optional

import redis.asyncio as aioredis

from openclaw.config import settings

# Global Redis connection pool (initialized in lifespan)
_redis: Optional[aioredis.Redis] = None


async def init_redis() -> aioredis.Redis:
    """Initialize the Redis connection pool."""
    global _redis
    _redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    # Verify connection
    await _redis.ping()
    return _redis


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis
    if _redis:
        await _redis.close()
        _redis = None


def get_redis() -> aioredis.Redis:
    """Get the Redis connection (must be initialized first)."""
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis


async def publish_event(
    team_id: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Publish an event to a team's Redis channel.

    Learn: Every service publishes events here after database writes.
    WebSocket handlers subscribe to these channels and forward to clients.
    """
    r = get_redis()
    channel = f"openclaw:events:{team_id}"
    payload = json.dumps({
        "type": event_type,
        **data,
    })
    await r.publish(channel, payload)
