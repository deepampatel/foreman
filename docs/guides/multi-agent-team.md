# Running a Multi-Agent Team

One agent is useful. Multiple agents coordinating on complex work is where Entourage really shines. This guide shows how to set up a team where a manager breaks down work and engineers execute in parallel.

## Why multiple agents?

A single agent working on a large feature hits problems:

- **Context limits** — One conversation can't hold an entire codebase
- **Sequential bottleneck** — One task at a time, no parallelism
- **No specialization** — The same agent does architecture decisions AND writes regex

With Entourage, you can have:

- A **manager** that understands the big picture and creates tasks
- **Engineers** that focus on specific, well-scoped work
- **Parallel execution** — eng-1 works on the API while eng-2 works on the UI

## Setting up the team

### 1. Create the team (manager is auto-created)

```bash
curl -X POST http://localhost:8000/api/v1/orgs/{org_id}/teams \
  -H "Content-Type: application/json" \
  -d '{"name": "Platform", "slug": "platform"}'
```

### 2. Add engineers

```bash
# Backend engineer
curl -X POST http://localhost:8000/api/v1/teams/{team_id}/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "eng-backend",
    "role": "engineer",
    "model": "claude-sonnet-4-20250514",
    "config": {"description": "Backend specialist — Python, APIs, databases"}
  }'

# Frontend engineer
curl -X POST http://localhost:8000/api/v1/teams/{team_id}/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "eng-frontend",
    "role": "engineer",
    "model": "claude-sonnet-4-20250514",
    "config": {"description": "Frontend specialist — React, TypeScript, UI"}
  }'
```

Your team:

```
Platform (team)
  ├── manager        — Decomposes features, coordinates
  ├── eng-backend    — Python, FastAPI, database work
  └── eng-frontend   — React, TypeScript, UI work
```

## The coordination pattern

### Step 1: Manager creates a task breakdown

You give the manager a high-level feature:

```bash
curl -X POST http://localhost:8000/api/v1/teams/{team_id}/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Add user profile page",
    "description": "Users should be able to view and edit their profile (name, email, avatar). Needs API endpoint + React page.",
    "priority": "high",
    "task_type": "feature"
  }'
```

The manager (via MCP tools) breaks this into sub-tasks:

```bash
# Task 2: Backend API (assigned to eng-backend)
curl -X POST http://localhost:8000/api/v1/teams/{team_id}/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Create GET/PATCH /api/v1/users/me endpoint",
    "description": "Return current user profile. PATCH to update name and avatar_url.",
    "priority": "high",
    "task_type": "feature"
  }'

# Task 3: Frontend page (assigned to eng-frontend, depends on Task 2)
curl -X POST http://localhost:8000/api/v1/teams/{team_id}/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Build profile page component in React",
    "description": "Form with name, email (read-only), avatar. Calls PATCH /api/v1/users/me on save.",
    "priority": "high",
    "task_type": "feature",
    "depends_on": ["{task_2_id}"]
  }'
```

### Step 2: DAG enforces execution order

Task 3 (frontend) **depends on** Task 2 (backend). Entourage's DAG engine ensures:

- eng-backend can start immediately
- eng-frontend **cannot start** until eng-backend's task is complete
- No race conditions. No "I built the UI against an API that doesn't exist yet"

### Step 3: Agents work in isolated worktrees

Each agent gets its own git worktree:

```
main branch
  ├── .worktrees/task-2-create-get-patch/    ← eng-backend works here
  └── .worktrees/task-3-build-profile-page/  ← eng-frontend works here (after task 2)
```

Agents can't step on each other's code. No merge conflicts during development.

### Step 4: Agents communicate via messages

The manager can send instructions to engineers:

```bash
curl -X POST http://localhost:8000/api/v1/teams/{team_id}/messages \
  -H "Content-Type: application/json" \
  -d '{
    "sender_id": "{manager_id}",
    "recipient_id": "{eng-backend_id}",
    "body": "For the profile endpoint, use the same auth pattern as /auth/me. Return 404 if user not found."
  }'
```

This triggers PG LISTEN/NOTIFY → the dispatcher routes the message to eng-backend's inbox. The agent can read it via the `get_inbox` MCP tool.

## Dispatch: How agents get work

Entourage uses PostgreSQL LISTEN/NOTIFY for instant dispatch:

```
Message inserted → PG trigger fires → NOTIFY channel
                                         ↓
                                    Dispatcher process
                                         ↓
                                    Routes to agent
                                         ↓
                                    Agent processes turn
```

The dispatcher:
- Handles **concurrent execution** (semaphore, max 32 agents by default)
- Prevents **double-dispatch** (same message won't trigger two turns)
- Falls back to **polling** if NOTIFY is missed
- Cleans up **stale requests** automatically

## Example: 3-agent feature build

Here's a realistic scenario — building a notification system:

```
Manager creates:
  Task 1: "Design notification schema"           → eng-backend
  Task 2: "Build notification API endpoints"      → eng-backend  (depends on 1)
  Task 3: "Add notification bell to navbar"       → eng-frontend (depends on 2)
  Task 4: "Write integration tests"              → eng-backend  (depends on 2, 3)
```

Execution order (enforced by DAG):

```
Timeline:
  t0 ─── eng-backend starts Task 1 (schema)
  t1 ─── eng-backend finishes Task 1, starts Task 2 (API)
         eng-frontend is still blocked (waiting for Task 2)
  t2 ─── eng-backend finishes Task 2
         eng-frontend starts Task 3 (UI) ← unblocked!
  t3 ─── eng-frontend finishes Task 3
         eng-backend starts Task 4 (tests) ← both deps met
  t4 ─── All tasks complete → manager marks feature done
```

Every transition is tracked. You can query `get_task_events` for any task and see the full timeline.

## Tips for effective multi-agent teams

### Keep tasks small and specific

Bad: "Build the user system"
Good: "Create users table migration" → "Add registration endpoint" → "Build signup form"

Smaller tasks = fewer context issues, faster reviews, clearer blame if something breaks.

### Use DAG dependencies aggressively

If Task B needs Task A's output, declare it. Don't rely on timing. The DAG engine is the one guarantee that work happens in the right order.

### Let the manager coordinate, not you

The manager agent is there to decompose work. Give it the high-level feature description, and let it create the sub-tasks and assignments. You review and approve the plan.

### Set budget limits per team

```bash
curl -X PATCH http://localhost:8000/api/v1/settings/teams/{team_id} \
  -H "Content-Type: application/json" \
  -d '{"daily_cost_limit_usd": 10.00, "max_concurrent_agents": 3}'
```

Multiple agents burn through tokens faster. Set reasonable daily caps.
