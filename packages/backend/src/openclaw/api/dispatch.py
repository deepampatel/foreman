"""Dispatch API — monitor unprocessed messages and dispatch readiness.

Learn: These endpoints let the dashboard show dispatch-related info:
- Unprocessed messages per agent
- Which agents are idle and ready for dispatch

The actual dispatching is done by the separate dispatcher process.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.engine import get_db

router = APIRouter()


@router.get("/teams/{team_id}/dispatch-status")
async def get_dispatch_status(
    team_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get dispatch status for a team — pending messages, idle agents.

    Learn: This shows what the dispatcher would see:
    - How many unprocessed messages per agent
    - Which agents are idle and could be dispatched
    """
    # Unprocessed messages per agent
    result = await db.execute(
        text("""
            SELECT
                m.recipient_id AS agent_id,
                a.name AS agent_name,
                a.status AS agent_status,
                COUNT(*) AS pending_messages
            FROM messages m
            JOIN agents a ON a.id = m.recipient_id
            WHERE m.team_id = :team_id
              AND m.recipient_type = 'agent'
              AND m.processed_at IS NULL
            GROUP BY m.recipient_id, a.name, a.status
            ORDER BY pending_messages DESC
        """),
        {"team_id": team_id},
    )
    pending = [
        {
            "agent_id": str(row.agent_id),
            "agent_name": row.agent_name,
            "agent_status": row.agent_status,
            "pending_messages": row.pending_messages,
        }
        for row in result
    ]

    # Idle agents (ready for dispatch)
    result = await db.execute(
        text("""
            SELECT id, name, role, model
            FROM agents
            WHERE team_id = :team_id AND status = 'idle'
        """),
        {"team_id": team_id},
    )
    idle_agents = [
        {
            "id": str(row.id),
            "name": row.name,
            "role": row.role,
            "model": row.model,
        }
        for row in result
    ]

    return {
        "team_id": team_id,
        "pending_messages": pending,
        "idle_agents": idle_agents,
        "total_pending": sum(p["pending_messages"] for p in pending),
        "total_idle": len(idle_agents),
    }
