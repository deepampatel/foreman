# OpenClaw

Orchestration platform for AI developer agents. OpenClaw handles the structure — tasks, teams, git, reviews, approvals, cost tracking — so agents can focus on writing code.

AI agents connect via [MCP](https://modelcontextprotocol.io) tools. Humans get a real-time dashboard. Every action is event-sourced.

```
┌─────────────┐         ┌─────────────┐         ┌──────────────┐
│  AI Agents  │──MCP───►│  OpenClaw   │◄──HTTP──│   Dashboard  │
│  (Claude,   │  stdio  │   Backend   │         │   (React)    │
│   etc.)     │◄────────│             │────────►│              │
└─────────────┘         └──────┬──────┘         └──────────────┘
                               │
                    ┌──────────┼──────────┐
                    │          │          │
               PostgreSQL    Redis      Git
```

## Features

- **Task state machine** — `todo` → `in_progress` → `in_review` → `in_approval` → `merging` → `done`, with validated transitions and cancellation from any active state
- **DAG dependencies** — Task B can't start until Task A is done. Enforced at the database level
- **Event sourcing** — Every state change is an immutable event. Full audit trail for any entity
- **Multi-agent messaging** — Decoupled inbox system for agent-to-agent and human-to-agent communication
- **Git integration** — Branch-per-task worktrees, diffs, file browsing, commit history
- **Session & cost tracking** — Per-agent token usage, budget enforcement (daily + per-task limits), cost summaries
- **Real-time dashboard** — WebSocket + Redis pub/sub for live updates
- **Human-in-the-loop** — Agents can ask questions, request approvals, and wait for human responses
- **Code review + merge** — Review cycles with comments, verdicts (approve/reject/request_changes), merge queue
- **Multi-agent dispatch** — PG LISTEN/NOTIFY triggers agent turns on new messages (<100ms latency)
- **Auth** — JWT access/refresh tokens for users, SHA-256 hashed API keys for agents
- **Webhooks** — GitHub webhook receiver with HMAC-SHA256 signature verification and delivery audit trail
- **Team settings** — Configurable budget limits, model preferences, workflow settings per team
- **MCP-first** — 44 tools. Agents manage all work through MCP, not custom APIs
- **Multi-tenant** — Organizations → Teams → Agents. Auto-provisions a manager agent per team

## Quick Start

```bash
# 1. Start Postgres + Redis
docker compose up -d

# 2. Backend
cd packages/backend
uv sync
uv run alembic upgrade head
uv run uvicorn openclaw.main:app --reload

# 3. MCP server
cd packages/mcp-server
npm install && npm run build

# 4. Frontend
cd packages/frontend
npm install && npx vite build

# 5. Connect an agent
OPENCLAW_API_URL=http://localhost:8000 node packages/mcp-server/dist/index.js
```

**Prerequisites:** Docker Desktop, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node.js 18+

## MCP Tools (44)

Agents interact with OpenClaw entirely through MCP tools:

| Category | Tools |
|----------|-------|
| **Platform** | `ping` |
| **Orgs & Teams** | `list_orgs` `create_org` `list_teams` `create_team` `get_team` |
| **Agents** | `list_agents` `create_agent` |
| **Repos** | `list_repos` `register_repo` |
| **Tasks** | `create_task` `list_tasks` `get_task` `update_task` `change_task_status` `assign_task` `get_task_events` |
| **Messages** | `send_message` `get_inbox` |
| **Git** | `create_worktree` `get_worktree` `remove_worktree` `get_task_diff` `get_changed_files` `read_file` `get_commits` |
| **Sessions & Costs** | `start_session` `record_usage` `end_session` `check_budget` `get_cost_summary` |
| **Human-in-the-loop** | `ask_human` `get_pending_requests` `respond_to_request` |
| **Reviews & Merge** | `request_review` `approve_task` `reject_task` `get_merge_status` |
| **Auth** | `authenticate` |
| **Webhooks** | `create_webhook` `list_webhooks` `update_webhook` |
| **Settings** | `get_team_settings` `update_team_settings` |

## Project Structure

```
packages/
  backend/        Python — FastAPI + SQLAlchemy 2.0 + Alembic + asyncpg
  mcp-server/     TypeScript — MCP tool definitions + HTTP client
  frontend/       React 19 + Vite + TanStack Query
```

### Backend Layout

```
src/openclaw/
  api/            REST endpoints (teams, tasks, git, sessions, reviews, auth, webhooks, settings)
  auth/           JWT + API key authentication
  db/             Models, engine, Alembic migrations
  dispatcher/     PG LISTEN/NOTIFY multi-agent dispatcher
  events/         Event store + type constants
  services/       Business logic (sessions, reviews, human loop, webhooks)
```

## Tests

```bash
cd packages/backend
uv run pytest tests/ -v    # 147 tests, ~10s
```

Tests use per-test savepoint rollback — fully isolated, no cleanup needed.

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| 0 | Project skeleton + MCP | Done |
| 1 | Orgs, teams, agents, repos | Done |
| 2 | Tasks, state machine, messages, event sourcing | Done |
| 3 | Git integration (worktrees, branch-per-task) | Done |
| 4 | Agent sessions + cost controls | Done |
| 5 | Real-time dashboard (WebSocket + Redis pub/sub) | Done |
| 6 | Multi-agent dispatch (PG LISTEN/NOTIFY) | Done |
| 7 | Human-in-the-loop | Done |
| 8 | Code review + merge worker | Done |
| 9 | Auth + multi-tenant security | Done |
| 10 | Settings + integrations (webhooks, team config) | Done |

## Documentation

- [Architecture](docs/architecture.md) — System design, data flow, tech stack
- [Database Schema](docs/database.md) — All tables, relationships, column details
- [Task State Machine](docs/tasks.md) — Transitions, DAG enforcement, event sourcing
- [MCP Tools Reference](docs/mcp-tools.md) — Every tool with parameters and examples
- [Development Guide](docs/development.md) — Setup, testing patterns, project structure

## License

MIT
