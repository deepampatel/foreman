"""Task and Message API routes.

Learn: These routes are the HTTP interface to the task state machine.
The service layer handles all validation (transitions, dependencies).
Routes just translate HTTP to service calls and handle error responses.

Key patterns:
- POST for creation and state changes (not idempotent)
- PATCH for partial updates (idempotent)
- Query params for filtering (status, assignee_id)
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.engine import get_db
from openclaw.schemas.task import (
    MessageCreate,
    MessageRead,
    StatusChange,
    TaskAssign,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)
from openclaw.services.task_service import (
    DependencyBlockedError,
    InvalidTransitionError,
    MessageService,
    TaskService,
)

router = APIRouter()


def _task_svc(db: AsyncSession = Depends(get_db)) -> TaskService:
    return TaskService(db)


def _msg_svc(db: AsyncSession = Depends(get_db)) -> MessageService:
    return MessageService(db)


# ═══════════════════════════════════════════════════════════
# Tasks
# ═══════════════════════════════════════════════════════════


@router.post("/teams/{team_id}/tasks", response_model=TaskRead, status_code=201)
async def create_task(
    team_id: uuid.UUID,
    body: TaskCreate,
    svc: TaskService = Depends(_task_svc),
):
    """Create a new task in 'todo' status."""
    task = await svc.create_task(
        team_id=team_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        assignee_id=body.assignee_id,
        dri_id=body.dri_id,
        depends_on=body.depends_on,
        repo_ids=body.repo_ids,
        tags=body.tags,
    )
    return task


@router.get("/teams/{team_id}/tasks", response_model=list[TaskRead])
async def list_tasks(
    team_id: uuid.UUID,
    status: Optional[str] = Query(None, description="Filter by status"),
    assignee_id: Optional[uuid.UUID] = Query(None, description="Filter by assignee"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    svc: TaskService = Depends(_task_svc),
):
    """List tasks for a team with optional filters."""
    return await svc.list_tasks(
        team_id=team_id,
        status=status,
        assignee_id=assignee_id,
        limit=limit,
        offset=offset,
    )


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: int,
    svc: TaskService = Depends(_task_svc),
):
    """Get a single task by ID."""
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    body: TaskUpdate,
    svc: TaskService = Depends(_task_svc),
):
    """Partially update a task (title, description, priority, tags)."""
    task = await svc.update_task(
        task_id=task_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        tags=body.tags,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/status", response_model=TaskRead)
async def change_task_status(
    task_id: int,
    body: StatusChange,
    svc: TaskService = Depends(_task_svc),
):
    """Change task status. Validates transitions and enforces dependencies.

    Learn: This is the most important endpoint — it's the entry point
    to the DAG-enforced state machine. Returns 409 for invalid transitions
    or blocked dependencies (not 400, because the request is well-formed
    but conflicts with the current state).
    """
    try:
        task = await svc.change_status(
            task_id=task_id,
            new_status=body.status,
            actor_id=body.actor_id,
        )
        return task
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except DependencyBlockedError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/tasks/{task_id}/assign", response_model=TaskRead)
async def assign_task(
    task_id: int,
    body: TaskAssign,
    svc: TaskService = Depends(_task_svc),
):
    """Assign an agent to a task."""
    task = await svc.assign_task(task_id=task_id, assignee_id=body.assignee_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ═══════════════════════════════════════════════════════════
# Task Events (read-only event sourcing query)
# ═══════════════════════════════════════════════════════════


@router.get("/tasks/{task_id}/events")
async def get_task_events(
    task_id: int,
    svc: TaskService = Depends(_task_svc),
):
    """Get the event history for a task (immutable audit trail).

    Learn: This is the power of event sourcing — every state change
    is recorded. You can see exactly what happened, when, and who did it.
    """
    events = await svc.events.read_stream(f"task:{task_id}")
    return [
        {
            "id": e.id,
            "type": e.type,
            "data": e.data,
            "metadata": e.meta,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


# ═══════════════════════════════════════════════════════════
# Messages
# ═══════════════════════════════════════════════════════════


@router.post("/teams/{team_id}/messages", response_model=MessageRead, status_code=201)
async def send_message(
    team_id: uuid.UUID,
    body: MessageCreate,
    svc: MessageService = Depends(_msg_svc),
):
    """Send a message between agents or users."""
    return await svc.send_message(
        team_id=team_id,
        sender_id=body.sender_id,
        sender_type=body.sender_type,
        recipient_id=body.recipient_id,
        recipient_type=body.recipient_type,
        task_id=body.task_id,
        content=body.content,
    )


@router.get("/agents/{agent_id}/inbox", response_model=list[MessageRead])
async def get_inbox(
    agent_id: uuid.UUID,
    unprocessed_only: bool = Query(True, description="Only show unprocessed messages"),
    limit: int = Query(50, ge=1, le=200),
    svc: MessageService = Depends(_msg_svc),
):
    """Get an agent's inbox (messages addressed to them)."""
    return await svc.get_inbox(
        recipient_id=agent_id,
        unprocessed_only=unprocessed_only,
        limit=limit,
    )
