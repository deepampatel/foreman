# Architecture

## System Overview

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

## Data Flow

```
Agent calls               Backend validates              Database stores
─────────────────         ────────────────────           ─────────────────
create_task        →      TaskService.create()      →    tasks table + event
change_task_status →      state machine check       →    tasks table + event
                          dependency DAG check
send_message       →      MessageService.send()     →    messages table + event
get_inbox          →      MessageService.get_inbox() →   query messages
```

1. **AI Agent** calls an MCP tool (e.g. `create_task`)
2. **MCP Server** (TypeScript) translates the tool call into an HTTP request
3. **FastAPI Backend** (Python) receives the request, routes it to the service layer
4. **Service Layer** validates business rules (state machine, DAG dependencies)
5. **EventStore** records the change as an immutable event
6. **Database** stores both the projection (tasks table) and the event
7. **WebSocket** (planned) pushes the change to the React dashboard

## Layer Separation

```
MCP Tool Definition (index.ts)     What agents see
        │
        ▼
HTTP Client (client.ts)            Protocol bridge (MCP → HTTP)
        │
        ▼
API Route (api/tasks.py)           HTTP translation + error handling
        │
        ▼
Service (services/task_service.py) Business logic + state machine
        │
        ▼
EventStore (events/store.py)       Immutable event recording
        │
        ▼
SQLAlchemy Models (db/models.py)   Database schema
```

Each layer has a single responsibility. API routes never contain business logic. Services never touch HTTP concepts. The EventStore is the only writer to the events table.

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

## Multi-Tenant Model

```
Organization (Acme Corp)
  └── Team (Backend)
        ├── Agent: manager (auto-created)
        ├── Agent: eng-1 (engineer)
        ├── Agent: eng-2 (engineer)
        ├── Repo: api-server
        ├── Repo: frontend
        ├── Task: Fix login bug
        │     ├── Event: task.created
        │     ├── Event: task.assigned → eng-1
        │     └── Event: task.status_changed → in_progress
        └── Message: manager → eng-1: "Work on login bug"
```

Organizations are the top-level tenant boundary. Teams scope all work. Creating a team auto-provisions a manager agent.
