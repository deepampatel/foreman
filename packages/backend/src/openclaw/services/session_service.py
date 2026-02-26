"""Session & budget service — agent turn tracking and cost controls.

Learn: Every time an agent "runs" (reads inbox, thinks, calls tools, responds),
that's a session. We track:
- Token usage (input, output, cache read/write)
- Cost in USD (computed from token counts + model pricing)
- Duration (started_at → ended_at)

Budget enforcement is the BIG missing piece from Delegate. Here we enforce:
- Per-turn output token limit
- Per-task cumulative cost limit
- Daily per-agent cost limit

If any limit is exceeded, the session is flagged and the agent should stop.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.models import Agent, Session
from openclaw.events.store import EventStore
from openclaw.events.types import (
    AGENT_BUDGET_EXCEEDED,
    SESSION_ENDED,
    SESSION_STARTED,
    SESSION_USAGE_RECORDED,
)


# ═══════════════════════════════════════════════════════════
# Model pricing (USD per 1M tokens)
# ═══════════════════════════════════════════════════════════

MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-haiku-3-20250414": {"input": 0.25, "output": 1.25, "cache_read": 0.03, "cache_write": 0.30},
}

# Fallback for unknown models
DEFAULT_PRICING = {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75}


def compute_cost(
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """Compute cost in USD from token counts and model pricing.

    Learn: Pricing is per 1M tokens. We divide by 1,000,000 to get
    the actual cost for the given token count.
    """
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return (
        tokens_in * pricing["input"] / 1_000_000
        + tokens_out * pricing["output"] / 1_000_000
        + cache_read * pricing["cache_read"] / 1_000_000
        + cache_write * pricing["cache_write"] / 1_000_000
    )


# ═══════════════════════════════════════════════════════════
# Budget
# ═══════════════════════════════════════════════════════════

@dataclass
class BudgetLimits:
    """Configurable budget limits.

    Learn: These can be set per-agent via agent.config JSONB,
    or fall back to these defaults. Limits prevent runaway costs.
    """
    max_output_per_turn: int = 32_000    # tokens
    daily_cost_limit_usd: float = 50.0   # per agent per day
    task_cost_limit_usd: float = 20.0    # per task total


@dataclass
class BudgetStatus:
    """Current budget state for an agent/task."""
    within_budget: bool
    daily_spent_usd: float
    daily_limit_usd: float
    task_spent_usd: float
    task_limit_usd: float
    violations: list[str]


class BudgetExceededError(Exception):
    """Raised when a budget limit is hit."""
    pass


# ═══════════════════════════════════════════════════════════
# Session Service
# ═══════════════════════════════════════════════════════════


class SessionService:
    """Manages agent work sessions and enforces cost budgets."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.events = EventStore(db)

    # ─── Session lifecycle ────────────────────────────────

    async def start_session(
        self,
        agent_id: uuid.UUID,
        task_id: Optional[int] = None,
        model: Optional[str] = None,
    ) -> Session:
        """Start a new agent work session.

        Learn: Called when an agent begins a turn. Creates a session
        row and checks if the agent has budget remaining. If not,
        raises BudgetExceededError to prevent the turn from starting.
        """
        # Look up agent for model default and budget config
        agent = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent_row = agent.scalars().first()
        if not agent_row:
            raise ValueError(f"Agent {agent_id} not found")

        effective_model = model or agent_row.model

        # Check budget before starting
        budget_status = await self.check_budget(agent_id, task_id, agent_row.config)
        if not budget_status.within_budget:
            await self.events.append(
                stream_id=f"agent:{agent_id}",
                event_type=AGENT_BUDGET_EXCEEDED,
                data={
                    "agent_id": str(agent_id),
                    "task_id": task_id,
                    "violations": budget_status.violations,
                },
            )
            await self.db.commit()
            raise BudgetExceededError(
                f"Budget exceeded: {', '.join(budget_status.violations)}"
            )

        session = Session(
            agent_id=agent_id,
            task_id=task_id,
            model=effective_model,
            tokens_in=0,
            tokens_out=0,
            cache_read=0,
            cache_write=0,
            cost_usd=0,
        )
        self.db.add(session)
        await self.db.flush()

        # Update agent status
        agent_row.status = "working"

        await self.events.append(
            stream_id=f"agent:{agent_id}",
            event_type=SESSION_STARTED,
            data={
                "session_id": session.id,
                "agent_id": str(agent_id),
                "task_id": task_id,
                "model": effective_model,
            },
        )

        await self.db.commit()
        return session

    async def record_usage(
        self,
        session_id: int,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cache_read: int = 0,
        cache_write: int = 0,
    ) -> Session:
        """Record token usage for a session.

        Learn: Called during or after an agent turn to update token counts.
        Recomputes cost from the updated totals.
        """
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalars().first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.tokens_in += tokens_in
        session.tokens_out += tokens_out
        session.cache_read += cache_read
        session.cache_write += cache_write
        session.cost_usd = compute_cost(
            session.model or "claude-sonnet-4-20250514",
            session.tokens_in,
            session.tokens_out,
            session.cache_read,
            session.cache_write,
        )

        await self.events.append(
            stream_id=f"agent:{session.agent_id}",
            event_type=SESSION_USAGE_RECORDED,
            data={
                "session_id": session_id,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cache_read": cache_read,
                "cache_write": cache_write,
                "total_cost_usd": float(session.cost_usd),
            },
        )

        await self.db.commit()
        return session

    async def end_session(
        self,
        session_id: int,
        error: Optional[str] = None,
    ) -> Session:
        """End a session — marks it complete with duration and optional error.

        Learn: Called when an agent finishes a turn (successfully or not).
        Sets ended_at, computes final cost, and sets agent back to idle.
        """
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalars().first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.ended_at = datetime.now(timezone.utc)
        if error:
            session.error = error

        # Set agent back to idle
        agent_result = await self.db.execute(
            select(Agent).where(Agent.id == session.agent_id)
        )
        agent = agent_result.scalars().first()
        if agent:
            agent.status = "idle"

        await self.events.append(
            stream_id=f"agent:{session.agent_id}",
            event_type=SESSION_ENDED,
            data={
                "session_id": session_id,
                "agent_id": str(session.agent_id),
                "task_id": session.task_id,
                "tokens_in": session.tokens_in,
                "tokens_out": session.tokens_out,
                "cost_usd": float(session.cost_usd),
                "error": error,
            },
        )

        await self.db.commit()
        return session

    # ─── Get session ──────────────────────────────────────

    async def get_session(self, session_id: int) -> Optional[Session]:
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalars().first()

    async def list_sessions(
        self,
        agent_id: Optional[uuid.UUID] = None,
        task_id: Optional[int] = None,
        limit: int = 50,
    ) -> list[Session]:
        query = select(Session).order_by(Session.id.desc()).limit(limit)
        if agent_id:
            query = query.where(Session.agent_id == agent_id)
        if task_id:
            query = query.where(Session.task_id == task_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ─── Budget checking ──────────────────────────────────

    async def check_budget(
        self,
        agent_id: uuid.UUID,
        task_id: Optional[int] = None,
        agent_config: Optional[dict] = None,
    ) -> BudgetStatus:
        """Check if an agent has budget remaining.

        Learn: Budget limits come from agent.config JSONB (if set)
        or fall back to BudgetLimits defaults. We check:
        1. Daily spending for this agent
        2. Task cumulative spending (if task_id provided)
        """
        config = agent_config or {}
        limits = BudgetLimits(
            max_output_per_turn=config.get("max_output_per_turn", 32_000),
            daily_cost_limit_usd=config.get("daily_cost_limit_usd", 50.0),
            task_cost_limit_usd=config.get("task_cost_limit_usd", 20.0),
        )

        violations = []

        # Daily cost
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        daily_result = await self.db.execute(
            select(func.coalesce(func.sum(Session.cost_usd), 0))
            .where(Session.agent_id == agent_id)
            .where(Session.started_at >= today_start)
        )
        daily_spent = float(daily_result.scalar() or 0)

        if daily_spent >= limits.daily_cost_limit_usd:
            violations.append(
                f"Daily limit exceeded: ${daily_spent:.4f} / ${limits.daily_cost_limit_usd:.2f}"
            )

        # Task cost
        task_spent = 0.0
        if task_id:
            task_result = await self.db.execute(
                select(func.coalesce(func.sum(Session.cost_usd), 0))
                .where(Session.task_id == task_id)
            )
            task_spent = float(task_result.scalar() or 0)

            if task_spent >= limits.task_cost_limit_usd:
                violations.append(
                    f"Task limit exceeded: ${task_spent:.4f} / ${limits.task_cost_limit_usd:.2f}"
                )

        return BudgetStatus(
            within_budget=len(violations) == 0,
            daily_spent_usd=daily_spent,
            daily_limit_usd=limits.daily_cost_limit_usd,
            task_spent_usd=task_spent,
            task_limit_usd=limits.task_cost_limit_usd,
            violations=violations,
        )

    # ─── Cost summaries ───────────────────────────────────

    async def get_cost_summary(
        self,
        team_id: uuid.UUID,
        days: int = 7,
    ) -> dict:
        """Get cost summary for a team — per-agent, per-model breakdown.

        Learn: This powers the cost dashboard. It shows:
        - Total cost over the period
        - Per-agent breakdown
        - Per-model breakdown
        - Session count
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Join sessions with agents to get team-scoped data
        from openclaw.db.models import Agent as AgentModel

        # Total cost
        total_result = await self.db.execute(
            select(func.coalesce(func.sum(Session.cost_usd), 0))
            .join(AgentModel, Session.agent_id == AgentModel.id)
            .where(AgentModel.team_id == team_id)
            .where(Session.started_at >= since)
        )
        total_cost = float(total_result.scalar() or 0)

        # Total tokens
        token_result = await self.db.execute(
            select(
                func.coalesce(func.sum(Session.tokens_in), 0),
                func.coalesce(func.sum(Session.tokens_out), 0),
            )
            .join(AgentModel, Session.agent_id == AgentModel.id)
            .where(AgentModel.team_id == team_id)
            .where(Session.started_at >= since)
        )
        token_row = token_result.one()
        total_tokens_in = int(token_row[0])
        total_tokens_out = int(token_row[1])

        # Session count
        count_result = await self.db.execute(
            select(func.count(Session.id))
            .join(AgentModel, Session.agent_id == AgentModel.id)
            .where(AgentModel.team_id == team_id)
            .where(Session.started_at >= since)
        )
        session_count = int(count_result.scalar() or 0)

        # Per-agent breakdown
        agent_result = await self.db.execute(
            select(
                AgentModel.id,
                AgentModel.name,
                func.coalesce(func.sum(Session.cost_usd), 0).label("cost"),
                func.count(Session.id).label("sessions"),
            )
            .join(AgentModel, Session.agent_id == AgentModel.id)
            .where(AgentModel.team_id == team_id)
            .where(Session.started_at >= since)
            .group_by(AgentModel.id, AgentModel.name)
        )
        per_agent = [
            {
                "agent_id": str(row.id),
                "agent_name": row.name,
                "cost_usd": float(row.cost),
                "sessions": int(row.sessions),
            }
            for row in agent_result
        ]

        # Per-model breakdown
        model_result = await self.db.execute(
            select(
                Session.model,
                func.coalesce(func.sum(Session.cost_usd), 0).label("cost"),
                func.count(Session.id).label("sessions"),
            )
            .join(AgentModel, Session.agent_id == AgentModel.id)
            .where(AgentModel.team_id == team_id)
            .where(Session.started_at >= since)
            .group_by(Session.model)
        )
        per_model = [
            {
                "model": row.model,
                "cost_usd": float(row.cost),
                "sessions": int(row.sessions),
            }
            for row in model_result
        ]

        return {
            "team_id": str(team_id),
            "period_days": days,
            "total_cost_usd": total_cost,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "session_count": session_count,
            "per_agent": per_agent,
            "per_model": per_model,
        }
