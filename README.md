<p align="center">
  <img src="docs/assets/banner.svg" alt="Entourage" width="100%" />
</p>

<p align="center">
  <strong>Your AI development entourage.</strong>
  <br />
  Orchestrate AI developer agents with tasks, git, reviews, approvals, and cost tracking.
  <br />
  Agents connect via <a href="https://modelcontextprotocol.io">MCP</a>. Humans get a real-time dashboard. Every action is event-sourced.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/tests-147_passing-6366f1?style=flat-square" alt="Tests" />
  <img src="https://img.shields.io/badge/MCP_tools-44-8b5cf6?style=flat-square" alt="MCP Tools" />
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/TypeScript-5.0+-3178C6?style=flat-square&logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License" />
</p>

---

## How it works

```
┌─────────────┐         ┌─────────────┐         ┌──────────────┐
│  AI Agents  │──MCP───▶│  Entourage  │◀──HTTP──│   Dashboard  │
│  (Claude,   │  stdio  │   Backend   │         │   (React)    │
│   etc.)     │◀────────│             │────────▶│              │
└─────────────┘         └──────┬──────┘         └──────────────┘
                               │
                    ┌──────────┼──────────┐
                    │          │          │
               PostgreSQL    Redis      Git
              (all state)  (pub/sub)  (worktrees)
```

You define the work. Your entourage executes it. Agents get tasks, write code in isolated git worktrees, request reviews, wait for approvals, and merge — all through 44 MCP tools. Humans stay in the loop via a real-time dashboard.

## Features

<table>
<tr>
<td width="50%">

**Task orchestration**
- State machine with 7 states and validated transitions
- DAG dependencies — Task B waits for Task A
- Event sourcing — full audit trail for everything

**Git integration**
- Branch-per-task with git worktrees
- Diffs, file browsing, commit history
- Merge queue with rebase/squash strategies

**Agent management**
- Session tracking with token/cost accounting
- Budget enforcement (daily + per-task limits)
- Multi-agent dispatch via PG LISTEN/NOTIFY

</td>
<td width="50%">

**Human-in-the-loop**
- Agents ask questions, request approvals
- Review cycles with file-anchored comments
- Approve/reject/request changes verdicts

**Auth & multi-tenant**
- JWT access/refresh tokens for humans
- API keys (SHA-256 hashed) for agents
- Organizations → Teams → Agents hierarchy

**Integrations**
- GitHub webhooks with HMAC-SHA256 verification
- Configurable team settings (budgets, models, workflows)
- Real-time WebSocket + Redis pub/sub

</td>
</tr>
</table>

## Quick start

```bash
# 1. Infrastructure
docker compose up -d              # Postgres 16 + Redis 7

# 2. Backend
cd packages/backend
uv sync && uv run alembic upgrade head
uv run uvicorn openclaw.main:app --reload

# 3. MCP server
cd packages/mcp-server
npm install && npm run build

# 4. Connect an agent
OPENCLAW_API_URL=http://localhost:8000 node packages/mcp-server/dist/index.js
```

> **Prerequisites:** Docker Desktop, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node.js 18+

## MCP tools

44 tools across 13 categories. Agents discover and call these via the [Model Context Protocol](https://modelcontextprotocol.io).

| Category | Tools | Count |
|----------|-------|:-----:|
| **Platform** | `ping` | 1 |
| **Orgs & Teams** | `list_orgs` `create_org` `list_teams` `create_team` `get_team` | 5 |
| **Agents** | `list_agents` `create_agent` | 2 |
| **Repos** | `list_repos` `register_repo` | 2 |
| **Tasks** | `create_task` `list_tasks` `get_task` `update_task` `change_task_status` `assign_task` `get_task_events` | 7 |
| **Messages** | `send_message` `get_inbox` | 2 |
| **Git** | `create_worktree` `get_worktree` `remove_worktree` `get_task_diff` `get_changed_files` `read_file` `get_commits` | 7 |
| **Sessions** | `start_session` `record_usage` `end_session` `check_budget` `get_cost_summary` | 5 |
| **Human-in-the-loop** | `ask_human` `get_pending_requests` `respond_to_request` | 3 |
| **Reviews** | `request_review` `approve_task` `reject_task` `get_merge_status` | 4 |
| **Auth** | `authenticate` | 1 |
| **Webhooks** | `create_webhook` `list_webhooks` `update_webhook` | 3 |
| **Settings** | `get_team_settings` `update_team_settings` | 2 |

## Architecture

```
packages/
  backend/        Python — FastAPI + SQLAlchemy 2.0 + Alembic
  mcp-server/     TypeScript — 44 MCP tool definitions
  frontend/       React 19 + Vite + TanStack Query
```

15 database models, 8 Alembic migrations, 11 API routers, event sourcing throughout.

## Tests

```bash
cd packages/backend
uv run pytest tests/ -v    # 147 tests, ~10s
```

Per-test savepoint rollback — fully isolated, no cleanup, runs against real Postgres.

## Documentation

| Doc | What's inside |
|-----|--------------|
| [Architecture](docs/architecture.md) | System design, data flow, subsystems |
| [Database Schema](docs/database.md) | 15 tables, relationships, migrations |
| [Task State Machine](docs/tasks.md) | Transitions, DAG, review flow, event types |
| [MCP Tools Reference](docs/mcp-tools.md) | All 44 tools with parameters |
| [Development Guide](docs/development.md) | Setup, testing, patterns, project structure |

## Roadmap

| Phase | What | Status |
|:-----:|------|:------:|
| 0 | Project skeleton + MCP | ✅ |
| 1 | Orgs, teams, agents, repos | ✅ |
| 2 | Tasks, state machine, messages, events | ✅ |
| 3 | Git integration (worktrees, branch-per-task) | ✅ |
| 4 | Agent sessions + cost controls | ✅ |
| 5 | Real-time dashboard (WebSocket + Redis) | ✅ |
| 6 | Multi-agent dispatch (PG LISTEN/NOTIFY) | ✅ |
| 7 | Human-in-the-loop (approvals, questions) | ✅ |
| 8 | Code review + merge worker | ✅ |
| 9 | Auth + multi-tenant (JWT, API keys) | ✅ |
| 10 | Webhooks + team settings | ✅ |

## License

MIT
