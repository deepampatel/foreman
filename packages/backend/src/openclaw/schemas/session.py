"""Pydantic schemas for sessions and cost tracking.

Learn: UUID fields from the ORM need serialization to strings.
We use uuid.UUID as the Python type and let Pydantic handle
the str conversion via json_encoders / serialization mode.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Session ──────────────────────────────────────────────


class SessionStart(BaseModel):
    agent_id: str
    task_id: Optional[int] = None
    model: Optional[str] = None


class UsageRecord(BaseModel):
    tokens_in: int = Field(0, ge=0)
    tokens_out: int = Field(0, ge=0)
    cache_read: int = Field(0, ge=0)
    cache_write: int = Field(0, ge=0)


class SessionEnd(BaseModel):
    error: Optional[str] = None


class SessionRead(BaseModel):
    id: int
    agent_id: uuid.UUID
    task_id: Optional[int]
    started_at: datetime
    ended_at: Optional[datetime]
    tokens_in: int
    tokens_out: int
    cache_read: int
    cache_write: int
    cost_usd: float
    model: Optional[str]
    error: Optional[str]

    model_config = {"from_attributes": True}


# ─── Budget ───────────────────────────────────────────────


class BudgetStatusRead(BaseModel):
    within_budget: bool
    daily_spent_usd: float
    daily_limit_usd: float
    task_spent_usd: float
    task_limit_usd: float
    violations: list[str]


# ─── Cost summary ─────────────────────────────────────────


class AgentCost(BaseModel):
    agent_id: str
    agent_name: str
    cost_usd: float
    sessions: int


class ModelCost(BaseModel):
    model: Optional[str]
    cost_usd: float
    sessions: int


class CostSummary(BaseModel):
    team_id: str
    period_days: int
    total_cost_usd: float
    total_tokens_in: int
    total_tokens_out: int
    session_count: int
    per_agent: list[AgentCost]
    per_model: list[ModelCost]
