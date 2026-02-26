"""Pydantic schemas for human-in-the-loop requests.

Learn: These schemas define the API contract for human requests —
how agents ask questions, how humans respond, and what gets returned.

Kinds:
- 'question': Agent needs information (free-text answer)
- 'approval': Agent needs yes/no (options = ["approve", "reject"])
- 'review': Agent needs code/work review
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Create request (agent → platform) ──────────────────


class HumanRequestCreate(BaseModel):
    """Agent asks for human input."""
    agent_id: str = Field(..., description="Agent UUID making the request")
    team_id: str = Field(..., description="Team UUID")
    task_id: Optional[int] = Field(None, description="Related task ID")
    kind: str = Field(..., description="Request kind: question, approval, review")
    question: str = Field(..., description="The question or request text")
    options: list[str] = Field(
        default_factory=list,
        description="Pre-defined answer options (e.g. ['approve', 'reject'])",
    )
    timeout_minutes: Optional[int] = Field(
        None, description="Auto-expire after N minutes (None = no timeout)"
    )


# ─── Respond (human → platform) ─────────────────────────


class HumanRequestRespond(BaseModel):
    """Human responds to a request."""
    response: str = Field(..., description="The human's response text")
    responded_by: Optional[str] = Field(
        None, description="User UUID who responded (None = anonymous)"
    )


# ─── Read (platform → client) ───────────────────────────


class HumanRequestRead(BaseModel):
    """Full human request with all fields."""
    id: int
    team_id: uuid.UUID
    agent_id: uuid.UUID
    task_id: Optional[int]
    kind: str
    question: str
    options: list[str]
    status: str
    response: Optional[str]
    responded_by: Optional[uuid.UUID]
    timeout_at: Optional[datetime]
    created_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}
