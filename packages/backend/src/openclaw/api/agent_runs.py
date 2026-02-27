"""Agent runs API — trigger and monitor agent runs.

Learn: This endpoint lets the CLI and dashboard trigger agent runs.
The run starts in the background — the request returns immediately
with a confirmation. The agent runs as a subprocess via the adapter.
"""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.agent.runner import AgentRunner
from openclaw.db.engine import get_db
from openclaw.db.models import Agent

router = APIRouter()


class RunAgentRequest(BaseModel):
    """Request body for triggering an agent run."""

    task_id: Optional[int] = Field(None, description="Task to work on")
    prompt: Optional[str] = Field(
        None, description="Override prompt (uses task description if not set)"
    )
    adapter: Optional[str] = Field(
        None, description="Adapter override (e.g. claude_code, codex, aider)"
    )


class RunAgentResponse(BaseModel):
    """Response from triggering an agent run."""

    status: str  # "started" or "error"
    message: str = ""
    agent_id: str = ""
    task_id: Optional[int] = None


@router.post("/agents/{agent_id}/run", response_model=RunAgentResponse)
async def run_agent(
    agent_id: str,
    body: RunAgentRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger an agent run on a task.

    Learn: The run happens in a BackgroundTask — the HTTP response returns
    immediately. The AgentRunner handles session lifecycle, adapter spawning,
    and error recording.

    The agent must be idle to start a run. If it's already working,
    return 409 Conflict.
    """
    # Validate agent exists
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalars().first()

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    if agent.status != "idle":
        raise HTTPException(
            status_code=409,
            detail=f"Agent is currently '{agent.status}'. Must be idle to start a run.",
        )

    # Dispatch the run in background
    runner = AgentRunner()
    background_tasks.add_task(
        runner.run_agent,
        agent_id=agent_id,
        team_id=str(agent.team_id),
        task_id=body.task_id,
        prompt_override=body.prompt,
        adapter_override=body.adapter,
    )

    return RunAgentResponse(
        status="started",
        message=f"Agent run dispatched (adapter={body.adapter or 'default'})",
        agent_id=agent_id,
        task_id=body.task_id,
    )
