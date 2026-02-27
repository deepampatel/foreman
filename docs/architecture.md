# Architecture

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        E N T O U R A G E                         │
│                                                                  │
│   ┌──────────┐    MCP (stdio)    ┌──────────────────────────┐   │
│   │ AI Agent │◄─────────────────►│     MCP Server (TS)      │   │
│   │ (Claude, │    44 tools       │  tasks, git, reviews,    │   │
│   │  etc.)   │                   │  sessions, webhooks, ... │   │
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
│   │  React   │                   │  │  │ Auth (JWT/API)│  │ │   │
│   │ Frontend │                   │  │  └───────────────┘  │ │   │
│   └──────────┘                   │  └─────────────────────┘ │   │
│                                  └────────────┬─────────────┘   │
│                                               │                  │
│        ┌──────────────────────────────────────┼──────────┐      │
│        │                     │                │          │      │
│  ┌─────▼─────┐    ┌─────────▼──┐   ┌────────▼──┐ ┌────▼───┐  │
│  │ PostgreSQL│    │ Dispatcher  │   │   Redis   │ │  Git   │  │
│  │    16     │    │ (LISTEN/    │   │     7     │ │Worktree│  │
│  │           │◄───│  NOTIFY)    │   │  pub/sub  │ │        │  │
│  └───────────┘    └────────────┘   └───────────┘ └────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Agent workflow
```
Agent calls               Backend validates              Database stores
─────────────────         ────────────────────           ─────────────────
create_task        →      TaskService.create()      →    tasks table + event
change_task_status →      state machine check       →    tasks table + event
                          dependency DAG check
send_message       →      MessageService.send()     →    messages table + event
                                                         + PG NOTIFY trigger
start_session      →      SessionService.start()    →    sessions table
ask_human          →      HumanLoopService.create() →    human_requests table
request_review     →      ReviewService.request()   →    reviews table + event
```

### Real-time dispatch
```
Message inserted → PG trigger → NOTIFY 'new_message' → Dispatcher picks up
                                                        → Routes to agent
                                                        → Agent processes turn
```

### Webhook flow
```
GitHub POST → /webhooks/{id}/receive → Verify HMAC-SHA256 signature
                                     → Log delivery in webhook_deliveries
                                     → Process event (create/update tasks)
                                     → Emit event via Redis pub/sub
```

## Request Lifecycle

1. **AI Agent** calls an MCP tool (e.g. `create_task`)
2. **MCP Server** (TypeScript) translates the tool call into an HTTP request
3. **FastAPI Backend** (Python) receives the request, routes it to the service layer
4. **Auth Layer** validates JWT token or API key (if endpoint is protected)
5. **Service Layer** validates business rules (state machine, DAG dependencies, budgets)
6. **EventStore** records the change as an immutable event
7. **Database** stores both the projection (tasks table) and the event
8. **PG Trigger** fires NOTIFY for relevant changes (messages, human requests, task status)
9. **Dispatcher** picks up notifications and routes work to agents
10. **Redis pub/sub** pushes the change to WebSocket clients (React dashboard)

## Layer Separation

```
MCP Tool Definition (index.ts)      What agents see (44 tools)
        │
        ▼
HTTP Client (client.ts)              Protocol bridge (MCP → HTTP)
        │
        ▼
API Route (api/*.py)                 HTTP translation + error handling
        │
        ▼
Auth (auth/dependencies.py)          JWT / API key verification
        │
        ▼
Service (services/*.py)              Business logic + state machine
        │
        ▼
EventStore (events/store.py)         Immutable event recording
        │
        ▼
SQLAlchemy Models (db/models.py)     Database schema (15 models)
```

Each layer has a single responsibility. API routes never contain business logic. Services never touch HTTP concepts. The EventStore is the only writer to the events table.

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Database | PostgreSQL 16 | JSONB, ARRAY, LISTEN/NOTIFY, triggers |
| Cache/Pubsub | Redis 7 | Real-time events, job queues, pub/sub |
| Backend | FastAPI + SQLAlchemy 2.0 async | Async-native, type-safe, dependency injection |
| Migrations | Alembic | Auto-generated from ORM model diffs + manual for triggers |
| Auth | PyJWT + SHA-256 | JWT access/refresh tokens, hashed API keys |
| Config | pydantic-settings | Env vars with `OPENCLAW_` prefix, validated types |
| MCP Server | TypeScript + @modelcontextprotocol/sdk | Typed tools, stdio transport |
| Frontend | React 19 + Vite + TanStack Query | Fast dev, server state management |
| Package mgmt | uv (Python), npm (Node) | uv is 10-100x faster than pip |
| Testing | pytest-asyncio + httpx | Async tests with savepoint rollback isolation |

## Multi-Tenant Model

```
Organization (Acme Corp)
  ├── API Key: oc_abc123... (SHA-256 hashed, org-scoped)
  ├── Webhook: GitHub → /webhooks/{id}/receive
  └── Team (Backend)
        ├── Config: {daily_cost_limit_usd: 100, auto_merge: true, ...}
        ├── Agent: manager (auto-created)
        ├── Agent: eng-1 (engineer)
        ├── Agent: eng-2 (engineer)
        ├── Repo: api-server
        ├── Task: Fix login bug
        │     ├── Event: task.created
        │     ├── Event: task.assigned → eng-1
        │     ├── Event: task.status_changed → in_progress
        │     ├── Session: 1500 tokens, $0.004
        │     ├── HumanRequest: "Should I refactor auth too?"
        │     ├── Review: attempt 1, verdict: approve
        │     └── MergeJob: status: success
        └── Message: manager → eng-1: "Work on login bug"
              └── PG NOTIFY → Dispatcher → eng-1 turn
```

Organizations are the top-level tenant boundary. Teams scope all work. Creating a team auto-provisions a manager agent.

## Key Subsystems

### Dispatcher (Phase 6)
PG LISTEN/NOTIFY-based agent dispatcher. Listens for:
- `new_message` — route message to recipient agent
- `human_request_resolved` — resume blocked agent
- `task_status_changed` — trigger dependent work

Features: semaphore-based concurrency (max 32), double-dispatch prevention, fallback poll loop, stale request cleanup.

### Auth (Phase 9)
Dual authentication:
- **JWT tokens** — For human users (60min access + 30-day refresh)
- **API keys** — For agents/CI (`oc_` prefix, SHA-256 hashed, org-scoped, optional expiry)

### Webhook Receiver (Phase 10)
GitHub/GitLab webhook ingestion:
- HMAC-SHA256 signature verification
- Event filtering (configurable per webhook)
- Delivery audit trail (every payload logged)
- Extensible event processing
