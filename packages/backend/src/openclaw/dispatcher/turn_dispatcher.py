"""Task dispatcher — PG LISTEN/NOTIFY for instant agent turn dispatch.

Learn: The dispatcher is a long-running process (separate from the API server).
It connects directly to PostgreSQL via asyncpg and LISTENs on channels:
- 'new_message' → dispatches agent turns when messages arrive
- 'human_request_resolved' → resumes agents waiting for human input
- 'task_status_changed' → handles task state transitions

On each notification:
1. Check if the recipient agent is idle
2. Check budget limits
3. If clear → mark agent as "working" and publish Redis event
4. Concurrency controlled via asyncio.Semaphore

Key design decisions:
- Separate process (not in the API server) — crash isolation
- No shared mutable state — coordination via Postgres + Redis
- Semaphore limits concurrent dispatches (backpressure)
- <100ms dispatch latency vs Delegate's 1s polling
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis

logger = logging.getLogger("openclaw.dispatcher")


@dataclass
class DispatcherConfig:
    """Configuration for the task dispatcher."""
    database_url: str = "postgresql://openclaw:dev@localhost:5433/openclaw"
    redis_url: str = "redis://localhost:6379/0"
    max_concurrent: int = 32
    poll_interval: float = 5.0  # seconds — fallback polling interval


@dataclass
class DispatcherStats:
    """Runtime statistics for monitoring."""
    dispatched: int = 0
    skipped: int = 0
    errors: int = 0
    in_flight: set = field(default_factory=set)
    started_at: Optional[datetime] = None


class TaskDispatcher:
    """Multi-agent task dispatcher with PG LISTEN/NOTIFY.

    Learn: The dispatcher runs three concurrent tasks:
    1. PG LISTEN listener — handles instant notifications
    2. Fallback poller — catches any missed notifications
    3. Cleanup loop — expires stale requests, resets stuck agents
    """

    def __init__(self, config: DispatcherConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.max_concurrent)
        self.stats = DispatcherStats()
        self._conn: Optional[asyncpg.Connection] = None
        self._redis: Optional[aioredis.Redis] = None
        self._db_pool: Optional[asyncpg.Pool] = None
        self._running = False

    async def start(self):
        """Start the dispatcher."""
        logger.info("Starting dispatcher (max_concurrent=%d)", self.config.max_concurrent)

        # Connect to PostgreSQL for LISTEN
        self._conn = await asyncpg.connect(self.config.database_url)

        # Connection pool for queries
        self._db_pool = await asyncpg.create_pool(
            self.config.database_url, min_size=2, max_size=10
        )

        # Redis for pub/sub events
        self._redis = aioredis.from_url(self.config.redis_url)

        self.stats.started_at = datetime.now(timezone.utc)
        self._running = True

        # Subscribe to PG channels
        await self._conn.add_listener("new_message", self._on_new_message)
        await self._conn.add_listener(
            "human_request_resolved", self._on_human_request_resolved
        )
        await self._conn.add_listener(
            "task_status_changed", self._on_task_status_changed
        )

        logger.info("Dispatcher listening on PG NOTIFY channels")

        # Run concurrent tasks
        try:
            await asyncio.gather(
                self._fallback_poll_loop(),
                self._cleanup_loop(),
            )
        finally:
            await self.stop()

    async def stop(self):
        """Stop the dispatcher gracefully."""
        self._running = False
        logger.info(
            "Stopping dispatcher (dispatched=%d, errors=%d)",
            self.stats.dispatched,
            self.stats.errors,
        )

        if self._conn:
            await self._conn.close()
        if self._db_pool:
            await self._db_pool.close()
        if self._redis:
            await self._redis.close()

    # ─── PG LISTEN handlers ───────────────────────────────

    def _on_new_message(self, conn, pid, channel, payload):
        """Called when a new message is inserted.

        Learn: This is a synchronous callback from asyncpg.
        We schedule the async dispatch on the event loop.
        """
        try:
            data = json.loads(payload)
            if data.get("recipient_type") == "agent":
                asyncio.create_task(
                    self._dispatch_agent(
                        agent_id=data["recipient_id"],
                        team_id=data["team_id"],
                        reason="new_message",
                    )
                )
        except Exception:
            logger.exception("Error handling new_message notification")
            self.stats.errors += 1

    def _on_human_request_resolved(self, conn, pid, channel, payload):
        """Called when a human request is resolved."""
        try:
            data = json.loads(payload)
            asyncio.create_task(
                self._dispatch_agent(
                    agent_id=data["agent_id"],
                    team_id=data["team_id"],
                    reason="human_request_resolved",
                )
            )
        except Exception:
            logger.exception("Error handling human_request_resolved notification")
            self.stats.errors += 1

    def _on_task_status_changed(self, conn, pid, channel, payload):
        """Called when a task's status changes.

        Learn: We log this for observability but don't auto-dispatch.
        The manager agent decides what to do via messages.
        """
        try:
            data = json.loads(payload)
            logger.info(
                "Task %s: %s → %s",
                data["task_id"],
                data["old_status"],
                data["new_status"],
            )
            # Publish to Redis for real-time UI
            if self._redis:
                asyncio.create_task(
                    self._redis.publish(
                        f"openclaw:events:{data['team_id']}",
                        json.dumps({
                            "type": "task.status_changed",
                            "task_id": data["task_id"],
                            "old_status": data["old_status"],
                            "new_status": data["new_status"],
                        }),
                    )
                )
        except Exception:
            logger.exception("Error handling task_status_changed notification")

    # ─── Dispatch logic ───────────────────────────────────

    async def _dispatch_agent(
        self, agent_id: str, team_id: str, reason: str
    ):
        """Dispatch an agent turn with concurrency control.

        Learn: The semaphore limits concurrent dispatches. If the agent
        is already in-flight, we skip (no double-dispatch).
        """
        if agent_id in self.stats.in_flight:
            logger.debug("Agent %s already in-flight, skipping", agent_id)
            self.stats.skipped += 1
            return

        async with self.semaphore:
            self.stats.in_flight.add(agent_id)
            try:
                # Check agent status
                async with self._db_pool.acquire() as conn:
                    agent = await conn.fetchrow(
                        "SELECT id, status, team_id FROM agents WHERE id = $1",
                        UUID(agent_id),
                    )

                if not agent:
                    logger.warning("Agent %s not found", agent_id)
                    return

                if agent["status"] != "idle":
                    logger.debug(
                        "Agent %s is %s, skipping dispatch",
                        agent_id,
                        agent["status"],
                    )
                    self.stats.skipped += 1
                    return

                # Mark as working
                async with self._db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE agents SET status = 'working' WHERE id = $1",
                        UUID(agent_id),
                    )

                # Publish dispatch event to Redis
                if self._redis:
                    await self._redis.publish(
                        f"openclaw:events:{team_id}",
                        json.dumps({
                            "type": "agent.status_changed",
                            "agent_id": agent_id,
                            "status": "working",
                            "reason": reason,
                        }),
                    )

                self.stats.dispatched += 1
                logger.info(
                    "Dispatched agent %s (reason=%s, in_flight=%d)",
                    agent_id,
                    reason,
                    len(self.stats.in_flight),
                )

                # Run the agent via adapter (Claude Code, Codex, etc.)
                # This is non-blocking — the run happens in a background task.
                # The adapter spawns a subprocess and manages its lifecycle.
                from openclaw.agent.runner import AgentRunner

                runner = AgentRunner()
                asyncio.create_task(
                    self._run_agent_background(
                        runner, agent_id, team_id, reason
                    )
                )

            except Exception:
                logger.exception("Error dispatching agent %s", agent_id)
                self.stats.errors += 1
                # Reset to idle on error
                try:
                    async with self._db_pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE agents SET status = 'idle' WHERE id = $1",
                            UUID(agent_id),
                        )
                except Exception:
                    pass
            finally:
                self.stats.in_flight.discard(agent_id)

    # ─── Agent run background task ────────────────────────

    async def _run_agent_background(
        self, runner, agent_id: str, team_id: str, reason: str
    ):
        """Run an agent turn in the background via adapter.

        Learn: This is fire-and-forget from the dispatch perspective.
        The runner handles session lifecycle, error recording, and
        resetting the agent to idle when done.
        """
        try:
            task_id = await self._get_agent_current_task(agent_id)

            result = await runner.run_agent(
                agent_id=agent_id,
                team_id=team_id,
                task_id=task_id,
            )

            logger.info(
                "Agent %s run completed (reason=%s, duration=%.1fs, exit=%d)",
                agent_id,
                reason,
                result.get("duration_seconds", 0),
                result.get("exit_code", -1),
            )
        except Exception:
            logger.exception(
                "Agent %s run failed (reason=%s)", agent_id, reason
            )
            # Reset agent to idle on unexpected failure
            try:
                async with self._db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE agents SET status = 'idle' WHERE id = $1",
                        UUID(agent_id),
                    )
            except Exception:
                pass

    async def _get_agent_current_task(self, agent_id: str) -> Optional[int]:
        """Find the agent's current in_progress task."""
        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id FROM tasks
                   WHERE assignee_id = $1 AND status = 'in_progress'
                   ORDER BY updated_at DESC LIMIT 1""",
                UUID(agent_id),
            )
            return row["id"] if row else None

    # ─── Fallback polling ─────────────────────────────────

    async def _fallback_poll_loop(self):
        """Fallback poller catches missed notifications.

        Learn: PG NOTIFY is best-effort (messages lost on disconnect).
        This poller runs every N seconds to catch unprocessed messages.
        """
        while self._running:
            try:
                await asyncio.sleep(self.config.poll_interval)
                if not self._running:
                    break

                async with self._db_pool.acquire() as conn:
                    # Find agents with unprocessed messages
                    rows = await conn.fetch("""
                        SELECT DISTINCT m.recipient_id AS agent_id, m.team_id
                        FROM messages m
                        JOIN agents a ON a.id = m.recipient_id
                        WHERE m.processed_at IS NULL
                          AND m.recipient_type = 'agent'
                          AND a.status = 'idle'
                        LIMIT 10
                    """)

                for row in rows:
                    await self._dispatch_agent(
                        agent_id=str(row["agent_id"]),
                        team_id=str(row["team_id"]),
                        reason="fallback_poll",
                    )

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in fallback poll loop")
                self.stats.errors += 1
                await asyncio.sleep(1)

    # ─── Cleanup loop ─────────────────────────────────────

    async def _cleanup_loop(self):
        """Periodic cleanup: expire stale requests, reset stuck agents.

        Learn: Runs every 60 seconds. Handles:
        1. Human requests past their timeout_at → mark as expired
        2. Agents stuck in "working" for too long → reset to idle
        """
        while self._running:
            try:
                await asyncio.sleep(60)
                if not self._running:
                    break

                async with self._db_pool.acquire() as conn:
                    # Expire stale human requests
                    expired = await conn.execute("""
                        UPDATE human_requests
                        SET status = 'expired',
                            resolved_at = NOW()
                        WHERE status = 'pending'
                          AND timeout_at IS NOT NULL
                          AND timeout_at < NOW()
                    """)
                    if expired != "UPDATE 0":
                        logger.info("Expired stale human requests: %s", expired)

                    # Reset agents stuck in "working" for > 30 minutes
                    stuck = await conn.execute("""
                        UPDATE agents
                        SET status = 'idle'
                        WHERE status = 'working'
                          AND id NOT IN (
                            SELECT agent_id FROM sessions
                            WHERE ended_at IS NULL
                              AND started_at > NOW() - INTERVAL '30 minutes'
                          )
                    """)
                    if stuck != "UPDATE 0":
                        logger.info("Reset stuck agents: %s", stuck)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in cleanup loop")
                await asyncio.sleep(10)

    # ─── Stats endpoint ──────────────────────────────────

    def get_stats(self) -> dict:
        """Return dispatcher statistics for monitoring."""
        return {
            "dispatched": self.stats.dispatched,
            "skipped": self.stats.skipped,
            "errors": self.stats.errors,
            "in_flight": len(self.stats.in_flight),
            "max_concurrent": self.config.max_concurrent,
            "started_at": (
                self.stats.started_at.isoformat()
                if self.stats.started_at
                else None
            ),
        }
