"""WebSocket endpoint — real-time event delivery to frontend clients.

Learn: Each client connects to /ws/{team_id}?token=JWT. The handler:
1. Authenticates via JWT query param (required in production)
2. Subscribes to the team's Redis pub/sub channel
3. Forwards every Redis message to the WebSocket client
4. Handles client disconnection gracefully

This is a long-lived connection — one per team per browser tab.
"""

import asyncio
import json

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from openclaw.config import settings
from openclaw.realtime.pubsub import get_redis

logger = structlog.get_logger()
router = APIRouter()


@router.websocket("/ws/{team_id}")
async def team_websocket(websocket: WebSocket, team_id: str):
    """WebSocket endpoint for real-time team events.

    Learn: Two concurrent tasks run:
    1. Redis listener — reads from pub/sub, sends to WebSocket
    2. Client listener — reads from WebSocket (for future bidirectional use)

    When either side disconnects, both tasks are cancelled cleanly.

    Authentication: JWT token required as ?token= query param.
    In development mode, unauthenticated connections are allowed.
    """
    # ── Authentication ──────────────────────────────────────
    token = websocket.query_params.get("token")

    if not token and settings.environment != "development":
        await websocket.close(code=4001, reason="Authentication required")
        return

    if token:
        from openclaw.auth.jwt import TokenError, verify_token

        try:
            verify_token(token)
        except TokenError:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return

    # ── Connection accepted ─────────────────────────────────
    await websocket.accept()

    r = get_redis()
    pubsub = r.pubsub()
    channel = f"openclaw:events:{team_id}"
    await pubsub.subscribe(channel)

    async def redis_listener():
        """Forward Redis messages to the WebSocket client."""
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])
        except asyncio.CancelledError:
            pass

    async def client_listener():
        """Handle incoming WebSocket messages (future: bidirectional)."""
        try:
            while True:
                data = await websocket.receive_text()
                # Future: handle client commands (e.g., subscribe to specific task)
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                except json.JSONDecodeError:
                    pass
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    # Run both listeners concurrently
    redis_task = asyncio.create_task(redis_listener())
    client_task = asyncio.create_task(client_listener())

    try:
        # Wait for either to finish (usually client disconnect)
        done, pending = await asyncio.wait(
            [redis_task, client_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
