"""Session & cost API routes — agent turn tracking and budget enforcement.

Learn: These routes let agents (via MCP) track their work sessions
and let humans (via dashboard) monitor costs. Budget enforcement
happens at session start — agents can't begin work if over budget.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.engine import get_db
from openclaw.schemas.session import (
    BudgetStatusRead,
    CostSummary,
    SessionEnd,
    SessionRead,
    SessionStart,
    UsageRecord,
)
from openclaw.services.session_service import BudgetExceededError, SessionService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> SessionService:
    return SessionService(db)


# ─── Session lifecycle ────────────────────────────────────────


@router.post("/sessions/start", response_model=SessionRead, status_code=201)
async def start_session(
    body: SessionStart,
    svc: SessionService = Depends(_svc),
):
    """Start a new agent work session. Checks budget first."""
    try:
        session = await svc.start_session(
            agent_id=uuid.UUID(body.agent_id),
            task_id=body.task_id,
            model=body.model,
        )
        return session
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BudgetExceededError as e:
        raise HTTPException(status_code=429, detail=str(e))


@router.post("/sessions/{session_id}/usage", response_model=SessionRead)
async def record_usage(
    session_id: int,
    body: UsageRecord,
    svc: SessionService = Depends(_svc),
):
    """Record token usage for an active session."""
    try:
        session = await svc.record_usage(
            session_id=session_id,
            tokens_in=body.tokens_in,
            tokens_out=body.tokens_out,
            cache_read=body.cache_read,
            cache_write=body.cache_write,
        )
        return session
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sessions/{session_id}/end", response_model=SessionRead)
async def end_session(
    session_id: int,
    body: SessionEnd = SessionEnd(),
    svc: SessionService = Depends(_svc),
):
    """End an agent work session."""
    try:
        session = await svc.end_session(
            session_id=session_id,
            error=body.error,
        )
        return session
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Session queries ──────────────────────────────────────────


@router.get("/sessions/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: int,
    svc: SessionService = Depends(_svc),
):
    """Get a specific session by ID."""
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/agents/{agent_id}/sessions", response_model=list[SessionRead])
async def list_agent_sessions(
    agent_id: uuid.UUID,
    task_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    svc: SessionService = Depends(_svc),
):
    """List sessions for an agent, optionally filtered by task."""
    return await svc.list_sessions(
        agent_id=agent_id,
        task_id=task_id,
        limit=limit,
    )


# ─── Budget ───────────────────────────────────────────────────


@router.get("/agents/{agent_id}/budget", response_model=BudgetStatusRead)
async def check_budget(
    agent_id: uuid.UUID,
    task_id: Optional[int] = Query(None),
    svc: SessionService = Depends(_svc),
):
    """Check if an agent has budget remaining."""
    from openclaw.db.models import Agent
    from sqlalchemy import select

    # Get agent config for budget limits
    result = await svc.db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    status = await svc.check_budget(
        agent_id=agent_id,
        task_id=task_id,
        agent_config=agent.config,
    )
    return status


# ─── Cost summary ─────────────────────────────────────────────


@router.get("/teams/{team_id}/costs", response_model=CostSummary)
async def get_cost_summary(
    team_id: uuid.UUID,
    days: int = Query(7, ge=1, le=90),
    svc: SessionService = Depends(_svc),
):
    """Get cost summary for a team — per-agent and per-model breakdown."""
    return await svc.get_cost_summary(team_id=team_id, days=days)
