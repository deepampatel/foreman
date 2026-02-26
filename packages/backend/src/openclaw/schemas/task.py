"""Pydantic schemas for tasks and messages.

Learn: Separate schemas for create/update/read keeps the API clean.
- TaskCreate: what you POST to create a task
- TaskUpdate: what you PATCH to modify a task (all optional)
- TaskRead: what the API returns (includes computed fields)
- StatusChange: dedicated schema for status transitions (validated by state machine)
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Tasks ───────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="")
    priority: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    assignee_id: Optional[uuid.UUID] = None
    dri_id: Optional[uuid.UUID] = None
    depends_on: list[int] = Field(default_factory=list)
    repo_ids: list[uuid.UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    """Partial update — only non-None fields are applied."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    priority: Optional[str] = Field(None, pattern=r"^(low|medium|high|critical)$")
    tags: Optional[list[str]] = None


class StatusChange(BaseModel):
    """Request to change task status. Validated by the state machine."""
    status: str = Field(..., pattern=r"^(todo|in_progress|in_review|in_approval|merging|done|cancelled)$")
    actor_id: Optional[uuid.UUID] = None  # who initiated the change


class TaskAssign(BaseModel):
    """Assign an agent to a task."""
    assignee_id: uuid.UUID


class TaskRead(BaseModel):
    id: int
    team_id: uuid.UUID
    title: str
    description: str
    status: str
    priority: str
    dri_id: Optional[uuid.UUID]
    assignee_id: Optional[uuid.UUID]
    depends_on: list[int]
    repo_ids: list[uuid.UUID]
    tags: list[str]
    branch: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── Messages ────────────────────────────────────────────

class MessageCreate(BaseModel):
    sender_id: uuid.UUID
    sender_type: str = Field(..., pattern=r"^(agent|user)$")
    recipient_id: uuid.UUID
    recipient_type: str = Field(..., pattern=r"^(agent|user)$")
    task_id: Optional[int] = None
    content: str = Field(..., min_length=1)


class MessageRead(BaseModel):
    id: int
    team_id: uuid.UUID
    sender_id: uuid.UUID
    sender_type: str
    recipient_id: uuid.UUID
    recipient_type: str
    task_id: Optional[int]
    content: str
    delivered_at: Optional[datetime]
    seen_at: Optional[datetime]
    processed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
