# Examples

Runnable scripts that demonstrate Entourage workflows. Each example is self-contained — it registers a fresh user, creates its own org, team, and agents, then walks through a specific scenario.

## Prerequisites

```bash
# Backend must be running
docker compose up -d
cd packages/backend && uv sync && uv run alembic upgrade head
uv run uvicorn openclaw.main:app --reload --port 8000

# Install httpx for the examples
pip install httpx
```

## Authentication

All API routes (except `/health` and `/auth/*`) require a JWT token. Each example handles this automatically via the shared `_common.py` helper:

1. Registers a fresh user with a unique email
2. Logs in to get a JWT access token
3. Attaches `Authorization: Bearer <token>` to all requests

You don't need to set up credentials — examples create ephemeral users on each run.

## Examples

| Script | What it demonstrates | Time |
|--------|---------------------|------|
| [quickstart.py](quickstart.py) | Full lifecycle: org → team → agent → task → assign → complete | 30s |
| [multi_agent.py](multi_agent.py) | Manager + engineers with batch task creation and DAG dependencies | 30s |
| [human_in_the_loop.py](human_in_the_loop.py) | Agent pauses to ask a question, human responds, agent continues | 30s |
| [code_review_flow.py](code_review_flow.py) | Review with file-anchored comments, request changes, approve | 30s |
| [webhook_automation.py](webhook_automation.py) | Register webhook, simulate GitHub event, verify HMAC security | 30s |
| [batch_orchestration.py](batch_orchestration.py) | DAG task decomposition, 4 specialist agents, session cost tracking | 30s |
| [auto_pr_and_review.py](auto_pr_and_review.py) | Push branch → create PR → two-tier agent+human code review | 30s |
| [context_carryover.py](context_carryover.py) | Save/load context between tasks so agents start warm | 30s |

## Running

```bash
cd examples

# Run any example
python quickstart.py
python multi_agent.py
python human_in_the_loop.py
python code_review_flow.py
python webhook_automation.py
python batch_orchestration.py
python auto_pr_and_review.py
python context_carryover.py
```

Each script prints step-by-step output showing what's happening. Example output from `quickstart.py`:

```
Backend health:
  Postgres: ✓
  Redis:    ✓
  Auth:     ✓ (JWT)

Setting up workspace 'Demo Corp'...
  Org:     Demo Corp (a3cefc2d...)
  Team:    Engineering (27c98d5f...)
  Manager: manager (manager)
  Agent:   eng-1 (b8d987b6...)
  Repo:    demo-app

1. Creating task...
   Task #594: Add health check to API
   Status: open
   Branch: feat/add-health-check-to-api-594

...

✓ Complete lifecycle finished. Task #594 is done.
  7 events recorded in the audit trail.
```

## Shared Helper

The `_common.py` module provides reusable setup logic:

```python
from _common import setup_workspace

ws = setup_workspace(
    "My Demo",
    engineers=[
        {"name": "eng-1", "description": "Backend specialist"},
        {"name": "eng-2", "description": "Frontend specialist"},
    ],
    repo={"name": "my-app"},
)

client = ws["client"]    # httpx.Client with auth headers
org = ws["org"]           # Organization dict
team = ws["team"]         # Team dict
manager = ws["manager"]   # Auto-created manager agent
engineers = ws["engineers"]  # List of created agent dicts
repo = ws["repo"]         # Repository dict (or None)
```

## What to explore next

After running the examples, check out the [guides](../docs/guides/) for deeper dives:

- [Getting Started](../docs/guides/getting-started.md) — Full setup walkthrough
- [Daily Workflow](../docs/guides/daily-workflow.md) — How a typical day looks
- [Multi-Agent Teams](../docs/guides/multi-agent-team.md) — Coordination patterns
- [Cost Control](../docs/guides/cost-control.md) — Budget management
- [Webhook Automation](../docs/guides/webhook-automation.md) — GitHub integration
