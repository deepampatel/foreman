"""Event store — append-only event log.

Learn: Event sourcing means every state change is an immutable event.
Instead of UPDATE task SET status='done', we INSERT an event
{type: "task.status_changed", data: {from: "in_review", to: "done"}}.

The events table is the source of truth. Other tables (tasks, agents)
are "projections" — materialized views that can be rebuilt from events.

This is the foundation used by all services starting in Phase 2.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.models import Event


class EventStore:
    """Append-only event store backed by PostgreSQL."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def append(
        self,
        stream_id: str,
        event_type: str,
        data: dict,
        metadata: dict | None = None,
    ) -> Event:
        """Append an event to a stream. Returns the created event."""
        event = Event(
            stream_id=stream_id,
            type=event_type,
            data=data,
            meta=metadata or {},
        )
        self.db.add(event)
        await self.db.flush()  # get the auto-generated id
        return event

    async def read_stream(
        self,
        stream_id: str,
        after_id: int = 0,
        limit: int = 100,
    ) -> list[Event]:
        """Read events for a specific stream, optionally after a given position."""
        result = await self.db.execute(
            select(Event)
            .where(Event.stream_id == stream_id, Event.id > after_id)
            .order_by(Event.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def read_all(
        self,
        after_id: int = 0,
        event_types: list[str] | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Read events across all streams (for projections and feeds)."""
        query = select(Event).where(Event.id > after_id).order_by(Event.id).limit(limit)
        if event_types:
            query = query.where(Event.type.in_(event_types))
        result = await self.db.execute(query)
        return list(result.scalars().all())
