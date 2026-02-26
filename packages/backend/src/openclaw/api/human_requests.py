"""Human-in-the-loop API — agents ask, humans answer.

Learn: Routes for the full human request lifecycle:
- POST /human-requests → agent creates a request
- POST /human-requests/:id/respond → human answers
- GET /human-requests/:id → get a specific request
- GET /teams/:id/human-requests → list requests for a team
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.engine import get_db
from openclaw.events.store import EventStore
from openclaw.schemas.human_request import (
    HumanRequestCreate,
    HumanRequestRead,
    HumanRequestRespond,
)
from openclaw.services.human_loop import (
    HumanLoopService,
    HumanRequestAlreadyResolvedError,
    HumanRequestNotFoundError,
)

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> HumanLoopService:
    return HumanLoopService(db=db, events=EventStore(db))


# ─── Create request (agent → platform) ──────────────────


@router.post("/human-requests", response_model=HumanRequestRead, status_code=201)
async def create_human_request(
    body: HumanRequestCreate,
    svc: HumanLoopService = Depends(_get_service),
):
    """Agent creates a human request (question, approval, or review)."""
    try:
        hr = await svc.create_request(
            team_id=body.team_id,
            agent_id=body.agent_id,
            kind=body.kind,
            question=body.question,
            task_id=body.task_id,
            options=body.options,
            timeout_minutes=body.timeout_minutes,
        )
        return hr
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Respond to request (human → platform) ──────────────


@router.post(
    "/human-requests/{request_id}/respond",
    response_model=HumanRequestRead,
)
async def respond_to_request(
    request_id: int,
    body: HumanRequestRespond,
    svc: HumanLoopService = Depends(_get_service),
):
    """Human responds to a pending request."""
    try:
        hr = await svc.respond(
            request_id=request_id,
            response=body.response,
            responded_by=body.responded_by,
        )
        return hr
    except HumanRequestNotFoundError:
        raise HTTPException(status_code=404, detail="Human request not found")
    except HumanRequestAlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ─── Get single request ─────────────────────────────────


@router.get("/human-requests/{request_id}", response_model=HumanRequestRead)
async def get_human_request(
    request_id: int,
    svc: HumanLoopService = Depends(_get_service),
):
    """Get a specific human request by ID."""
    hr = await svc.get_request(request_id)
    if not hr:
        raise HTTPException(status_code=404, detail="Human request not found")
    return hr


# ─── List requests for team ──────────────────────────────


@router.get(
    "/teams/{team_id}/human-requests",
    response_model=list[HumanRequestRead],
)
async def list_human_requests(
    team_id: str,
    status: Optional[str] = Query(None, description="Filter by status: pending, resolved, expired"),
    agent_id: Optional[str] = Query(None, description="Filter by agent UUID"),
    task_id: Optional[int] = Query(None, description="Filter by task ID"),
    limit: int = Query(50, ge=1, le=200),
    svc: HumanLoopService = Depends(_get_service),
):
    """List human requests for a team with optional filters."""
    return await svc.list_requests(
        team_id=team_id,
        status=status,
        agent_id=agent_id,
        task_id=task_id,
        limit=limit,
    )
