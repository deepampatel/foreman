# Foreman

Orchestration platform for AI developer agents. Foreman handles the structure — tasks, teams, git, reviews, approvals, cost tracking — so agents can focus on writing code.

AI agents connect via [MCP](https://modelcontextprotocol.io) tools. Humans get a real-time dashboard. Every action is event-sourced.

```
┌─────────────┐         ┌─────────────┐         ┌──────────────┐
│  AI Agents  │──MCP───►│   Foreman   │◄──HTTP──│   Dashboard  │
│  (Claude,   │  stdio  │   Backend   │         │   (React)    │
│  OpenClaw)  │◄────────│             │────────►│              │
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
- **MCP-first** — 19 tools today, growing to 34. Agents manage all work through MCP, not custom APIs
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

# 4. Connect an agent
OPENCLAW_API_URL=http://localhost:8000 node packages/mcp-server/dist/index.js
```

**Prerequisites:** Docker Desktop, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node.js 18+

## MCP Tools

Agents interact with Foreman entirely through MCP tools:

| Category | Tools |
|----------|-------|
| **Platform** | `ping` |
| **Orgs & Teams** | `list_orgs` `create_org` `list_teams` `create_team` `get_team` |
| **Agents** | `list_agents` `create_agent` |
| **Repos** | `list_repos` `register_repo` |
| **Tasks** | `create_task` `list_tasks` `get_task` `update_task` `change_task_status` `assign_task` `get_task_events` |
| **Messages** | `send_message` `get_inbox` |

## Project Structure

```
packages/
  backend/        Python — FastAPI + SQLAlchemy + Alembic
  mcp-server/     TypeScript — MCP tool definitions
  frontend/       React 19 + Vite + TanStack Query
```

## Tests

```bash
cd packages/backend
uv run pytest tests/ -v    # 36 tests, ~2.7s
```

Tests use per-test savepoint rollback — fully isolated, no cleanup needed.

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| 0 | Project skeleton + MCP | Done |
| 1 | Orgs, teams, agents, repos | Done |
| 2 | Tasks, state machine, messages, event sourcing | Done |
| 3 | Git integration (worktrees, branch-per-task) | Next |
| 4 | Agent sessions + cost controls | Planned |
| 5 | Real-time dashboard (WebSocket) | Planned |
| 6 | Multi-agent dispatch (PG LISTEN/NOTIFY) | Planned |
| 7 | Human-in-the-loop | Planned |
| 8 | Code review + merge worker | Planned |
| 9 | Auth + multi-tenant security | Planned |
| 10 | Settings + integrations | Planned |

## Documentation

- [Architecture](docs/architecture.md) — System design, data flow, tech stack
- [Database Schema](docs/database.md) — All tables, relationships, column details
- [Task State Machine](docs/tasks.md) — Transitions, DAG enforcement, event sourcing
- [MCP Tools Reference](docs/mcp-tools.md) — Every tool with parameters and examples
- [Development Guide](docs/development.md) — Setup, testing patterns, project structure

## License

MIT
