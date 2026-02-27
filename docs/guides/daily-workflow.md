# Daily Workflow with Entourage

What does a typical day look like when you're running AI agents through Entourage instead of raw chatting with Claude? This guide walks through a realistic workday.

## The mental model

Without Entourage, working with AI agents looks like this:

```
You → Chat with Claude → Hope it does the right thing → Manually check everything
```

With Entourage:

```
You → Create tasks → Agents work in governed pipelines → You review and approve
```

The difference: **structure**. Tasks have states. Code has reviews. Budgets have limits. Every action has an audit trail.

## Morning: Check what happened overnight

If you have agents running async work, start by checking the dashboard or querying the API:

```bash
# What tasks are in progress?
curl http://localhost:8000/api/v1/teams/{team_id}/tasks

# Any agents waiting for human input?
curl http://localhost:8000/api/v1/teams/{team_id}/human-requests

# How much did overnight work cost?
curl http://localhost:8000/api/v1/teams/{team_id}/costs
```

**Human requests are the critical ones.** If an agent hit something it wasn't sure about, it called `ask_human` and paused. You'll see questions like:

- "The API returns 500 for empty arrays. Should I return 200 with an empty list, or 204 No Content?"
- "Found 3 places where this function is called. Should I update all callers or add a backward-compatible wrapper?"

Respond via the API or dashboard:

```bash
curl -X POST http://localhost:8000/api/v1/human-requests/{request_id}/respond \
  -H "Content-Type: application/json" \
  -d '{"response": "Return 200 with empty array — our frontend expects it", "decision": "approved"}'
```

The agent gets unblocked and continues working.

## Mid-morning: Create new work

A bug report comes in. Instead of opening Claude and explaining the whole codebase, you create a structured task:

```bash
curl -X POST http://localhost:8000/api/v1/teams/{team_id}/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Fix: login endpoint returns 500 for special characters in email",
    "description": "Steps to reproduce: POST /auth/login with email containing + symbol. Expected: 400 validation error. Actual: 500 unhandled exception. Root cause likely in email regex in auth/password.py.",
    "priority": "high",
    "task_type": "bugfix"
  }'
```

Assign it to an agent:

```bash
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/assign \
  -H "Content-Type: application/json" \
  -d '{"assignee_id": "{eng-1 id}"}'
```

The agent picks it up through the MCP dispatcher. It will:

1. Create a **git worktree** (isolated branch, no conflicts with other agents)
2. Investigate the bug
3. Write a fix + tests
4. Request a **code review** when done

All of this is tracked. You can check progress anytime:

```bash
# Task status + event history
curl http://localhost:8000/api/v1/tasks/{task_id}/events

# What files changed?
curl http://localhost:8000/api/v1/tasks/{task_id}/files

# See the diff
curl http://localhost:8000/api/v1/tasks/{task_id}/diff
```

## Afternoon: Review agent work

The agent finished the bug fix and requested review. You get notified via the dashboard (WebSocket push).

### Look at the review

```bash
# List reviews for the task
curl http://localhost:8000/api/v1/tasks/{task_id}/reviews
```

### Add comments on specific files

```bash
curl -X POST http://localhost:8000/api/v1/reviews/{review_id}/comments \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "src/openclaw/auth/password.py",
    "line_number": 42,
    "body": "Good fix, but also add a test for unicode characters in email"
  }'
```

### Give a verdict

```bash
# Request changes — agent will go back and fix
curl -X POST http://localhost:8000/api/v1/reviews/{review_id}/verdict \
  -H "Content-Type: application/json" \
  -d '{"verdict": "request_changes", "body": "See comments — need one more test case"}'
```

The agent sees the feedback, makes changes, and requests review again. This cycle continues until you approve:

```bash
curl -X POST http://localhost:8000/api/v1/reviews/{review_id}/verdict \
  -H "Content-Type: application/json" \
  -d '{"verdict": "approve", "body": "Looks good, ship it"}'
```

### Merge

```bash
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/merge \
  -H "Content-Type: application/json" \
  -d '{"strategy": "squash"}'
```

The task moves to `done`. The worktree is cleaned up. The event log shows the complete trail: created → assigned → in_progress → in_review → done.

## End of day: Check costs

```bash
curl http://localhost:8000/api/v1/teams/{team_id}/costs
```

You'll see per-agent, per-session breakdowns:

- eng-1: 3 sessions, 45k tokens, $0.12
- eng-2: 1 session, 12k tokens, $0.03

If an agent is burning through budget, you can cap it:

```bash
curl -X PATCH http://localhost:8000/api/v1/settings/teams/{team_id} \
  -H "Content-Type: application/json" \
  -d '{"daily_cost_limit_usd": 5.00}'
```

## The key patterns

### 1. Tasks, not chat threads

Instead of a conversation that gets lost when context runs out, you have persistent tasks with defined states. An agent can crash and restart — the task is still there, still assigned, still tracked.

### 2. Review before merge — always

No agent code goes to main without your explicit approval. The state machine enforces this: you can't transition from `in_review` to `done` without an approve verdict.

### 3. Questions, not assumptions

When agents hit ambiguity, they don't guess — they call `ask_human` and wait. This is the difference between "it rewrote my auth system" and "it asked me whether to use JWT or sessions."

### 4. Budget limits, not surprise bills

Set daily and per-task cost caps. Entourage tracks every token spent in every session. When a budget is exceeded, the agent is told to stop.

### 5. Audit everything

Every state change, every assignment, every review verdict is an immutable event. Six months from now, you can trace exactly what happened on any task.

## Compared to raw Claude

| What you do | Raw Claude | With Entourage |
|-------------|-----------|----------------|
| Assign work | Paste context into chat | `create_task` + `assign_task` |
| Check progress | Scroll through chat | `get_task` / `get_task_events` |
| Review code | Read the chat output | `get_task_diff` + file-anchored comments |
| Approve changes | Say "looks good" | `approve_task` → auto-merge |
| Track costs | Check Anthropic dashboard manually | `check_budget` / `get_cost_summary` |
| Handle ambiguity | Agent guesses or asks in chat | `ask_human` — agent pauses and waits |
| Multiple agents | Open multiple chat windows | Dispatcher routes work automatically |
| Audit trail | Re-read old chats | Event store with immutable history |
