# Development Guide

## Prerequisites

- Docker Desktop (for Postgres + Redis)
- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 18+

## Setup

### 1. Infrastructure

```bash
docker compose up -d
```

This starts:
- PostgreSQL 16 on port **5433** (not 5432, to avoid conflicts with local Postgres)
- Redis 7 on port **6379**

### 2. Backend

```bash
cd packages/backend
uv sync                       # install all dependencies
uv run alembic upgrade head   # create/update database tables
uv run uvicorn openclaw.main:app --reload --port 8000
```

The API is now at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

### 3. MCP Server

```bash
cd packages/mcp-server
npm install
npm run build     # compile TypeScript → dist/
npm run dev       # watch mode for development
```

### 4. Frontend

```bash
cd packages/frontend
npm install
npm run dev       # Vite dev server at http://localhost:5173
```

The frontend proxies `/api` requests to the backend (configured in `vite.config.ts`).

## Configuration

All config is via environment variables with the `OPENCLAW_` prefix.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENCLAW_DATABASE_URL` | `postgresql+asyncpg://openclaw:openclaw_dev@localhost:5433/openclaw` | Database connection |
| `OPENCLAW_REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `OPENCLAW_ANTHROPIC_API_KEY` | `""` | For built-in agent runner |
| `OPENCLAW_JWT_SECRET` | `change-me-in-production` | JWT signing key |
| `OPENCLAW_DEBUG` | `false` | Enable SQL echo logging |
| `OPENCLAW_ENVIRONMENT` | `development` | Environment name |
| `OPENCLAW_API_URL` | `http://localhost:8000` | MCP server → backend URL |

## Running Tests

```bash
cd packages/backend
uv run pytest tests/ -v
```

### Test Architecture

Tests use a **savepoint rollback** pattern for isolation:

1. Each test gets its own database connection + transaction
2. The session uses `join_transaction_mode="create_savepoint"` — when the service layer calls `commit()`, it creates a SAVEPOINT instead of a real commit
3. After the test, the outer transaction rolls back — all test data vanishes

This means:
- Tests run against the real database (not mocks)
- Tests are fully isolated — no data leaks between tests
- No cleanup needed — rollback handles everything
- Fast — 36 tests in ~2.7 seconds

### Test Structure

```
tests/
  conftest.py           Fixtures: db_session (savepoint), client (HTTP)
  test_health.py        Smoke test
  test_teams_api.py     Phase 1: orgs, teams, agents, repos (17 tests)
  test_tasks_api.py     Phase 2: tasks, state machine, deps, messages (19 tests)
```

### Writing New Tests

```python
@pytest.mark.asyncio
async def test_something(client):
    """client fixture gives you an HTTP client with DB isolation."""
    # Create test data via the API
    resp = await client.post("/api/v1/orgs", json={"name": "Test", "slug": "test"})
    org = resp.json()

    # Assert
    assert resp.status_code == 201
    assert org["slug"] == "test"
```

For tests that need direct DB access:

```python
@pytest.mark.asyncio
async def test_with_db(client, db_session):
    """db_session gives you direct SQLAlchemy access."""
    from sqlalchemy import select
    from openclaw.db.models import Event

    # Do something via API...
    await client.post(...)

    # Query DB directly
    result = await db_session.execute(select(Event))
    events = list(result.scalars().all())
```

## Database Migrations

Migrations are auto-generated from model changes using Alembic.

```bash
cd packages/backend

# After changing models.py:
uv run alembic revision --autogenerate -m "description of change"

# Apply:
uv run alembic upgrade head

# Rollback one step:
uv run alembic downgrade -1
```

## Project Structure

```
foreman/
├── docker-compose.yml                  Postgres 16 (port 5433) + Redis 7
├── pnpm-workspace.yaml                 Monorepo config
├── .github/workflows/ci.yml            CI pipeline
│
├── packages/
│   ├── backend/                        Python — FastAPI
│   │   ├── pyproject.toml              Dependencies + pytest config
│   │   ├── alembic.ini                 Migration config
│   │   ├── uv.lock                     Lockfile (commit this)
│   │   ├── src/openclaw/
│   │   │   ├── __init__.py             Version string
│   │   │   ├── main.py                 App factory, lifespan, CORS
│   │   │   ├── config.py              pydantic-settings
│   │   │   ├── api/
│   │   │   │   ├── __init__.py         Router aggregation
│   │   │   │   ├── health.py           Health check (Postgres + Redis)
│   │   │   │   ├── teams.py            Org/Team/Agent/Repo CRUD
│   │   │   │   └── tasks.py            Tasks + state machine + messages
│   │   │   ├── db/
│   │   │   │   ├── models.py           10 ORM models (source of truth)
│   │   │   │   ├── engine.py           Async engine + get_db dependency
│   │   │   │   └── migrations/         Alembic versions
│   │   │   ├── services/
│   │   │   │   ├── team_service.py     Team logic + auto-provision
│   │   │   │   └── task_service.py     State machine + DAG + messages
│   │   │   ├── events/
│   │   │   │   ├── store.py            Append-only EventStore
│   │   │   │   └── types.py            Event type constants
│   │   │   └── schemas/
│   │   │       ├── team.py             Pydantic models (request/response)
│   │   │       └── task.py
│   │   └── tests/
│   │
│   ├── mcp-server/                     TypeScript — MCP tools
│   │   ├── src/
│   │   │   ├── index.ts                19 tool definitions
│   │   │   └── client.ts               Typed HTTP client
│   │   ├── tsconfig.json
│   │   └── package.json
│   │
│   └── frontend/                       React 19 + Vite
│       ├── src/
│       │   ├── main.tsx                Entry point
│       │   ├── App.tsx                 Root component
│       │   └── api/client.ts           Typed API client
│       ├── vite.config.ts              Proxy config
│       └── tsconfig.json
│
└── docs/                               Documentation
    ├── architecture.md
    ├── database.md
    ├── tasks.md
    ├── mcp-tools.md
    └── development.md                  (this file)
```

## Code Patterns

### API Route → Service → EventStore

```
POST /api/v1/teams/{id}/tasks
  → api/tasks.py: create_task()        HTTP handling
    → services/task_service.py          Business logic
      → events/store.py: append()       Record event
      → db session commit               Persist
```

Routes handle HTTP concerns (status codes, error mapping). Services handle business logic. The EventStore handles event persistence.

### FastAPI Dependency Injection

```python
def _task_svc(db: AsyncSession = Depends(get_db)) -> TaskService:
    return TaskService(db)

@router.post("/teams/{team_id}/tasks")
async def create_task(body: TaskCreate, svc: TaskService = Depends(_task_svc)):
    return await svc.create_task(...)
```

### Pydantic Schemas

Separate `Create` (input) from `Read` (output) schemas:

```python
class TaskCreate(BaseModel):    # What the client sends
    title: str
    priority: str = "medium"

class TaskRead(BaseModel):      # What the API returns
    id: int
    title: str
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}
```
