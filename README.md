# Foreman

AI agent orchestration platform. Manages tasks, teams, and code reviews for AI developer agents via MCP.

## Architecture

```
MCP Server (stdio)  →  FastAPI Backend  →  PostgreSQL + Redis
     ↑                      ↑
  AI agents            React Frontend
```

- **MCP Server**: Primary interface for AI agents (19 tools). Agents discover and call tools via Model Context Protocol.
- **Backend**: FastAPI + SQLAlchemy async + Alembic migrations. Service layer with DAG-enforced task state machine.
- **Frontend**: React 19 + Vite + TanStack Query.
- **Database**: PostgreSQL 16 with event sourcing (append-only events table).

## Quick Start

### Prerequisites

- Docker Desktop (for Postgres + Redis)
- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 18+

### 1. Start infrastructure

```bash
docker compose up -d
```

### 2. Run the backend

```bash
cd packages/backend
uv sync
uv run alembic upgrade head
uv run uvicorn openclaw.main:app --reload
```

### 3. Build the MCP server

```bash
cd packages/mcp-server
npm install
npm run build
```

### 4. Connect an agent

```bash
OPENCLAW_API_URL=http://localhost:8000 node packages/mcp-server/dist/index.js
```

### 5. Run tests

```bash
cd packages/backend
uv run pytest tests/ -v
```

## MCP Tools

| Phase | Tools |
|-------|-------|
| **0** | `ping` |
| **1** | `list_orgs`, `create_org`, `list_teams`, `create_team`, `get_team`, `list_agents`, `create_agent`, `list_repos`, `register_repo` |
| **2** | `create_task`, `list_tasks`, `get_task`, `update_task`, `change_task_status`, `assign_task`, `get_task_events`, `send_message`, `get_inbox` |

## Task State Machine

```
todo → in_progress → in_review → in_approval → merging → done
  ↓        ↓             ↓            ↓
cancelled  cancelled   cancelled    cancelled
```

- Transitions are validated (can't skip steps)
- Dependencies enforced via DAG (task B can't start until task A is done)
- Every change recorded as an immutable event

## Project Structure

```
packages/
  backend/          Python — FastAPI + SQLAlchemy
    src/openclaw/
      api/          Route handlers
      db/           Models + migrations
      events/       Event sourcing
      schemas/      Pydantic request/response models
      services/     Business logic
    tests/
  mcp-server/       TypeScript — MCP tool definitions
  frontend/         React — dashboard UI
```
