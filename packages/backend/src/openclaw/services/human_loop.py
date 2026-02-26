"""Human-in-the-loop service — agents ask, humans answer.

Learn: This service manages the async request/response flow:
1. Agent creates a request (question/approval/review)
2. Request is persisted + published to Redis for real-time UI
3. Human sees notification in dashboard, responds
4. Response persisted + published → dispatcher continues agent work

All state is in PostgreSQL — survives restarts (unlike Delegate's in-memory).
Timeout handling marks stale requests as expired.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.models import Agent, HumanRequest
from openclaw.events.store import EventStore
from openclaw.events.types import (
    HUMAN_REQUEST_CREATED,
    HUMAN_REQUEST_EXPIRED,
    HUMAN_REQUEST_RESOLVED,
)


class HumanRequestNotFoundError(Exception):
    """Raised when a human request is not found."""


class HumanRequestAlreadyResolvedError(Exception):
    """Raised when trying to respond to an already-resolved request."""


class HumanLoopService:
    """Manages human-in-the-loop request lifecycle."""

    def __init__(self, db: AsyncSession, events: EventStore):
        self.db = db
        self.events = events

    # ─── Create request ───────────────────────────────────

    async def create_request(
        self,
        *,
        team_id: str,
        agent_id: str,
        kind: str,
        question: str,
        task_id: Optional[int] = None,
        options: Optional[list[str]] = None,
        timeout_minutes: Optional[int] = None,
    ) -> HumanRequest:
        """Create a new human request from an agent.

        Learn: Validates the agent exists, computes timeout, persists,
        and appends an event for the audit trail.
        """
        # Validate agent exists
        agent = await self.db.get(Agent, uuid.UUID(agent_id))
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Compute timeout
        timeout_at = None
        if timeout_minutes:
            timeout_at = datetime.now(timezone.utc) + timedelta(
                minutes=timeout_minutes
            )

        # Create request
        hr = HumanRequest(
            team_id=uuid.UUID(team_id),
            agent_id=uuid.UUID(agent_id),
            task_id=task_id,
            kind=kind,
            question=question,
            options=options or [],
            status="pending",
            timeout_at=timeout_at,
        )
        self.db.add(hr)
        await self.db.flush()

        # Event sourcing
        await self.events.append(
            stream_id=f"human_request:{hr.id}",
            event_type=HUMAN_REQUEST_CREATED,
            data={
                "request_id": hr.id,
                "team_id": team_id,
                "agent_id": agent_id,
                "task_id": task_id,
                "kind": kind,
                "question": question,
                "options": options or [],
            },
        )

        await self.db.commit()
        await self.db.refresh(hr)
        return hr

    # ─── Respond to request ───────────────────────────────

    async def respond(
        self,
        request_id: int,
        response: str,
        responded_by: Optional[str] = None,
    ) -> HumanRequest:
        """Human responds to a pending request.

        Learn: Validates the request is pending, records the response,
        updates status, and appends an event.
        """
        hr = await self.db.get(HumanRequest, request_id)
        if not hr:
            raise HumanRequestNotFoundError(
                f"Human request {request_id} not found"
            )

        if hr.status != "pending":
            raise HumanRequestAlreadyResolvedError(
                f"Human request {request_id} is already {hr.status}"
            )

        # Update the request
        hr.response = response
        hr.status = "resolved"
        hr.resolved_at = datetime.now(timezone.utc)
        if responded_by:
            hr.responded_by = uuid.UUID(responded_by)

        # Event sourcing
        await self.events.append(
            stream_id=f"human_request:{hr.id}",
            event_type=HUMAN_REQUEST_RESOLVED,
            data={
                "request_id": hr.id,
                "response": response,
                "responded_by": responded_by,
            },
        )

        await self.db.commit()
        await self.db.refresh(hr)
        return hr

    # ─── Get request ──────────────────────────────────────

    async def get_request(self, request_id: int) -> Optional[HumanRequest]:
        """Get a single human request by ID."""
        return await self.db.get(HumanRequest, request_id)

    # ─── List requests ────────────────────────────────────

    async def list_requests(
        self,
        team_id: str,
        *,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[int] = None,
        limit: int = 50,
    ) -> list[HumanRequest]:
        """List human requests for a team with optional filters."""
        q = (
            select(HumanRequest)
            .where(HumanRequest.team_id == uuid.UUID(team_id))
            .order_by(HumanRequest.created_at.desc())
            .limit(limit)
        )
        if status:
            q = q.where(HumanRequest.status == status)
        if agent_id:
            q = q.where(HumanRequest.agent_id == uuid.UUID(agent_id))
        if task_id:
            q = q.where(HumanRequest.task_id == task_id)

        result = await self.db.execute(q)
        return list(result.scalars().all())

    # ─── Expire stale requests ────────────────────────────

    async def expire_stale_requests(self) -> int:
        """Mark timed-out requests as expired.

        Learn: Called periodically (or by the dispatcher). Finds
        pending requests past their timeout_at and marks them expired.
        Returns count of expired requests.
        """
        now = datetime.now(timezone.utc)
        q = (
            select(HumanRequest)
            .where(HumanRequest.status == "pending")
            .where(HumanRequest.timeout_at.isnot(None))
            .where(HumanRequest.timeout_at < now)
        )
        result = await self.db.execute(q)
        stale = list(result.scalars().all())

        for hr in stale:
            hr.status = "expired"
            hr.resolved_at = now
            await self.events.append(
                stream_id=f"human_request:{hr.id}",
                event_type=HUMAN_REQUEST_EXPIRED,
                data={"request_id": hr.id, "reason": "timeout"},
            )

        if stale:
            await self.db.commit()

        return len(stale)
