# Examples

Runnable scripts that demonstrate Entourage workflows. Each example is self-contained — it creates its own org, team, and agents, then walks through a specific scenario.

## Prerequisites

```bash
# Backend must be running
docker compose up -d
cd packages/backend && uv sync && uv run alembic upgrade head
uv run uvicorn openclaw.main:app --reload --port 8000

# Install httpx for the examples
pip install httpx
```

## Examples

| Script | What it demonstrates | Time |
|--------|---------------------|------|
| [quickstart.py](quickstart.py) | Full lifecycle: org → team → agent → task → assign → complete | 30s |
| [multi_agent.py](multi_agent.py) | Manager + engineers coordinating with messages and DAG dependencies | 30s |
| [human_in_the_loop.py](human_in_the_loop.py) | Agent pauses to ask a question, human responds, agent continues | 30s |
| [code_review_flow.py](code_review_flow.py) | Review with file-anchored comments, request changes, approve | 30s |
| [webhook_automation.py](webhook_automation.py) | Register webhook, simulate GitHub event, verify HMAC security | 30s |

## Running

```bash
cd examples

# Run any example
python quickstart.py
python multi_agent.py
python human_in_the_loop.py
python code_review_flow.py
python webhook_automation.py
```

Each script prints step-by-step output showing what's happening. Example output from `quickstart.py`:

```
Checking backend health...
  Postgres: ✓
  Redis:    ✓

1. Creating organization...
   Org: Demo Corp (a3cefc2d...)

2. Creating team...
   Team: Engineering (27c98d5f...)
   Manager auto-created: manager (manager)

3. Adding engineer agent...
   Agent: eng-1 (b8d987b6...)

...

✓ Complete lifecycle finished. Task #594 is done.
  7 events recorded in the audit trail.
```

## What to explore next

After running the examples, check out the [guides](../docs/guides/) for deeper dives:

- [Getting Started](../docs/guides/getting-started.md) — Full setup walkthrough
- [Daily Workflow](../docs/guides/daily-workflow.md) — How a typical day looks
- [Multi-Agent Teams](../docs/guides/multi-agent-team.md) — Coordination patterns
- [Cost Control](../docs/guides/cost-control.md) — Budget management
- [Webhook Automation](../docs/guides/webhook-automation.md) — GitHub integration
