# Foreman

The management layer for AI developer agents. Provides the structure — tasks, git, reviews, approvals, cost tracking, real-time visibility — so AI agents can focus on coding.

```
┌──────────────────────────────────────────────────────────────────┐
│                        FOREMAN PLATFORM                          │
│                                                                  │
│   ┌──────────┐    MCP (stdio)    ┌──────────────────────────┐   │
│   │ AI Agent │◄─────────────────►│     MCP Server (TS)      │   │
│   │ (OpenClaw│    19 tools       │  ping, create_task,      │   │
│   │  Claude, │                   │  change_status, inbox,   │   │
│   │  etc.)   │                   │  send_message, ...       │   │
│   └──────────┘                   └────────────┬─────────────┘   │
│                                               │ REST             │
│   ┌──────────┐    WebSocket      ┌────────────▼─────────────┐   │
│   │  Human   │◄─────────────────►│    FastAPI Backend (Py)  │   │
│   │  Users   │    REST           │  ┌─────────────────────┐ │   │
│   │          │◄─────────────────►│  │   Service Layer     │ │   │
│   └──────────┘                   │  │  ┌───────────────┐  │ │   │
│        ▲                         │  │  │ State Machine │  │ │   │
│        │                         │  │  │ DAG Enforcer  │  │ │   │
│   ┌────┴─────┐                   │  │  │ Event Store   │  │ │   │
│   │  React   │                   │  │  └───────────────┘  │ │   │
│   │ Frontend │                   │  └─────────────────────┘ │   │
│   └──────────┘                   └────────────┬─────────────┘   │
│                                               │                  │
│                         ┌─────────────────────┼──────────┐      │
│                         │                     │          │      │
│                   ┌─────▼─────┐    ┌──────────▼┐  ┌─────▼──┐   │
│                   │ PostgreSQL│    │   Redis    │  │ Git    │   │
│                   │    16     │    │     7      │  │Worktree│   │
│                   └───────────┘    └───────────┘  └────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## How It Works

AI agents connect via MCP tools. Humans see everything in a React dashboard. Every change is an immutable event.

```
Agent calls               Backend validates              Database stores
─────────────────         ────────────────────           ─────────────────
create_task        →      TaskService.create()      →    tasks table + event
change_task_status →      state machine check       →    tasks table + event
                          dependency DAG check
send_message       →      MessageService.send()     →    messages table + event
get_inbox          →      MessageService.get_inbox() →   query messages
```

---

## Task State Machine

Every task follows a strict workflow. Transitions are validated — you can't skip steps.

```
                    ┌──────────────────────────────────────────────────┐
                    │                                                  │
                    ▼                                                  │
               ┌────────┐     ┌─────────────┐     ┌─────────────┐    │
               │  todo   │────►│ in_progress │────►│  in_review  │    │
               └────┬────┘     └──────┬──────┘     └──────┬──────┘    │
                    │                 │                    │           │
                    │                 │    ┌───────────────┘           │
                    │                 │    │                           │
                    │                 │    ▼                           │
                    │                 │  ┌─────────────┐              │
                    │                 │  │ in_approval  │─────────────┘
                    │                 │  └──────┬──────┘    (reject)
                    │                 │         │
                    │                 │         ▼
                    │                 │  ┌─────────────┐
                    │                 │  │   merging    │─────────────┐
                    │                 │  └──────┬──────┘  (merge fail)│
                    │                 │         │                     │
                    │                 │         ▼                     │
                    │                 │  ┌─────────────┐             │
                    │                 │  │    done      │             │
                    │                 │  └─────────────┘             │
                    │                 │                               │
                    ▼                 ▼                               │
               ┌─────────────────────────┐                          │
               │       cancelled         │                          │
               └─────────────────────────┘                          │
```

**Valid transitions:**
```
todo         → in_progress, cancelled
in_progress  → in_review, todo, cancelled
in_review    → in_approval, in_progress, cancelled
in_approval  → merging, in_progress, cancelled
merging      → done, in_progress
done         → (terminal)
cancelled    → (terminal)
```

**DAG dependency enforcement:** Task B depends on Task A → B cannot move to `in_progress` until A is `done`.

---

## Database Schema

```
┌──────────────┐       ┌──────────────┐
│organizations │       │    users     │
│──────────────│       │──────────────│
│ id (UUID)    │       │ id (UUID)    │
│ name         │       │ email        │
│ slug (unique)│       │ name         │
│ created_at   │       │ password_hash│
└──────┬───────┘       └──────┬───────┘
       │ 1:N                  │
       ▼                      │
┌──────────────┐    ┌─────────▼────────┐
│    teams     │    │  team_members    │
│──────────────│    │──────────────────│
│ id (UUID)    │◄───│ team_id (FK)     │
│ org_id (FK)  │    │ user_id (FK)     │
│ name, slug   │    │ role             │
└──┬───┬───┬───┘    └──────────────────┘
   │   │   │
   │   │   │ 1:N
   │   │   ▼
   │   │ ┌──────────────┐
   │   │ │ repositories │
   │   │ │──────────────│
   │   │ │ id (UUID)    │
   │   │ │ team_id (FK) │
   │   │ │ name         │
   │   │ │ local_path   │
   │   │ │ config (JSONB)│
   │   │ └──────────────┘
   │   │
   │   │ 1:N
   │   ▼
   │ ┌──────────────┐
   │ │   agents     │
   │ │──────────────│
   │ │ id (UUID)    │
   │ │ team_id (FK) │
   │ │ name, role   │    role: manager | engineer | reviewer
   │ │ model        │    default: claude-sonnet-4-20250514
   │ │ config (JSONB)│   token budgets, tool restrictions
   │ │ status       │    idle | working | paused
   │ └──────────────┘
   │
   │ 1:N
   ▼
┌───────────────────┐     ┌──────────────────┐
│      tasks        │     │    messages       │
│───────────────────│     │──────────────────│
│ id (SERIAL)       │◄────│ task_id (FK)     │
│ team_id (FK)      │     │ sender_id        │
│ title, description│     │ sender_type      │  agent | user
│ status, priority  │     │ recipient_id     │
│ dri_id (FK→agent) │     │ recipient_type   │  agent | user
│ assignee_id (FK)  │     │ content          │
│ depends_on (INT[])│     │ processed_at     │
│ repo_ids (UUID[]) │     │ created_at       │
│ tags (TEXT[])     │     └──────────────────┘
│ branch            │
│ metadata (JSONB)  │
│ completed_at      │
└───────────────────┘

┌──────────────────┐     ┌──────────────────┐
│     events       │     │    sessions      │
│──────────────────│     │──────────────────│
│ id (SERIAL)      │     │ id (SERIAL)      │
│ stream_id        │     │ agent_id (FK)    │
│ type             │     │ task_id          │
│ data (JSONB)     │     │ tokens_in/out    │
│ metadata (JSONB) │     │ cache_read/write │
│ created_at       │     │ cost_usd         │
└──────────────────┘     │ model, error     │
  Append-only.           └──────────────────┘
  Never updated.
  Never deleted.
```

---

## Event Sourcing

Every state change is recorded as an immutable event. The `events` table is the source of truth.

```
stream_id       type                  data
─────────────   ────────────────────  ──────────────────────────────────
task:1          task.created          {"title": "Fix login", "priority": "high"}
task:1          task.status_changed   {"from": "todo", "to": "in_progress"}
task:1          task.assigned         {"from": null, "to": "<agent-uuid>"}
task:1          task.updated          {"priority": "critical"}
task:1          task.status_changed   {"from": "in_progress", "to": "in_review"}
team:<uuid>     team.created          {"name": "Backend", "slug": "backend"}
team:<uuid>     agent.created         {"name": "manager", "role": "manager"}
message:5       message.sent          {"sender_id": "...", "recipient_id": "..."}
```

Query any entity's full history: `GET /api/v1/tasks/1/events`

---

## MCP Tools

The MCP server is the primary interface. AI agents discover and call tools via the Model Context Protocol.

```
Phase 0 — Foundation                    Phase 2 — Tasks
────────────────────                    ──────────────────
ping                                    create_task
                                        list_tasks
Phase 1 — Teams                         get_task
────────────────────                    update_task
list_orgs                               change_task_status
create_org                              assign_task
list_teams                              get_task_events
create_team                             send_message
get_team                                get_inbox
list_agents
create_agent                            Phase 3+ (planned)
list_repos                              ──────────────────
register_repo                           get_task_diff
                                        start_session
                                        check_budget
                                        ask_human
                                        approve_task
                                        ... (34 total)
```

**19 tools today.** Grows to 34 by Phase 10.

---

## Project Structure

```
foreman/
├── docker-compose.yml                  Postgres 16 + Redis 7
├── pnpm-workspace.yaml
├── .github/workflows/ci.yml
│
├── packages/
│   ├── backend/                        Python — FastAPI
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   ├── src/openclaw/
│   │   │   ├── main.py                 App factory + lifespan
│   │   │   ├── config.py              pydantic-settings (OPENCLAW_* env vars)
│   │   │   ├── api/
│   │   │   │   ├── health.py           GET /health (Postgres + Redis check)
│   │   │   │   ├── teams.py            Org/Team/Agent/Repo CRUD
│   │   │   │   └── tasks.py            Task CRUD + state machine + messages
│   │   │   ├── db/
│   │   │   │   ├── models.py           10 SQLAlchemy ORM models
│   │   │   │   ├── engine.py           Async engine + session factory
│   │   │   │   └── migrations/         Alembic auto-generated migrations
│   │   │   ├── services/
│   │   │   │   ├── team_service.py     Team CRUD + auto-provision manager
│   │   │   │   └── task_service.py     State machine + DAG + messages
│   │   │   ├── events/
│   │   │   │   ├── store.py            Append-only EventStore
│   │   │   │   └── types.py            Event type constants
│   │   │   └── schemas/
│   │   │       ├── team.py             Pydantic request/response models
│   │   │       └── task.py
│   │   └── tests/                      36 tests, 2.7s, fully isolated
│   │       ├── conftest.py             Savepoint rollback per test
│   │       ├── test_health.py
│   │       ├── test_teams_api.py       Phase 1 (17 tests)
│   │       └── test_tasks_api.py       Phase 2 (19 tests)
│   │
│   ├── mcp-server/                     TypeScript — MCP tools
│   │   ├── src/
│   │   │   ├── index.ts                Tool definitions (19 tools)
│   │   │   └── client.ts               Typed HTTP client → backend API
│   │   └── package.json
│   │
│   └── frontend/                       React 19 + Vite
│       ├── src/
│       │   ├── App.tsx
│       │   ├── main.tsx
│       │   └── api/client.ts           Typed API client
│       └── vite.config.ts              Proxy /api → backend
```

---

## Quick Start

### Prerequisites

- Docker Desktop
- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 18+

### 1. Infrastructure

```bash
docker compose up -d          # Postgres on :5433, Redis on :6379
```

### 2. Backend

```bash
cd packages/backend
uv sync                       # install dependencies (~12s)
uv run alembic upgrade head   # apply migrations
uv run uvicorn openclaw.main:app --reload
```

### 3. MCP Server

```bash
cd packages/mcp-server
npm install && npm run build
```

### 4. Connect an agent

```bash
OPENCLAW_API_URL=http://localhost:8000 node packages/mcp-server/dist/index.js
```

### 5. Tests

```bash
cd packages/backend
uv run pytest tests/ -v       # 36 tests, ~2.7s
```

---

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| 0 | Project skeleton + MCP foundation | Done |
| 1 | Database + Team/Agent/Repo API | Done |
| 2 | Task management + event sourcing + messages | Done |
| 3 | Git integration (worktrees, diffs, branch-per-task) | Next |
| 4 | Agent session management + cost controls | Planned |
| 5 | Real-time dashboard (WebSocket + Redis pub/sub) | Planned |
| 6 | Multi-agent dispatch (LISTEN/NOTIFY, <100ms) | Planned |
| 7 | Human-in-the-loop (ask_human, approvals) | Planned |
| 8 | Code review + merge worker | Planned |
| 9 | Auth + multi-tenant | Planned |
| 10 | Settings + integrations | Planned |

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Database | PostgreSQL 16 | JSONB, ARRAY, LISTEN/NOTIFY, row-level security |
| Cache/Pubsub | Redis 7 | Real-time events, job queues, pub/sub |
| Backend | FastAPI + SQLAlchemy 2.0 async | Async-native, type-safe, dependency injection |
| Migrations | Alembic | Auto-generated from ORM model diffs |
| Config | pydantic-settings | Env vars with `OPENCLAW_` prefix, validated types |
| MCP Server | TypeScript + @modelcontextprotocol/sdk | Typed tools, stdio transport |
| Frontend | React 19 + Vite + TanStack Query | Fast dev, server state management |
| Package mgmt | uv (Python), npm (Node) | uv is 10-100x faster than pip |
| Testing | pytest-asyncio + httpx | Async tests with savepoint rollback isolation |
