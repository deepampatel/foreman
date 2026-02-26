# Database Schema

## Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────┐
│organizations │       │    users     │
│──────────────│       │──────────────│
│ id (UUID) PK │       │ id (UUID) PK │
│ name         │       │ email UNIQUE │
│ slug UNIQUE  │       │ name         │
│ created_at   │       │ password_hash│
│ updated_at   │       │ created_at   │
└──────┬───────┘       └──────┬───────┘
       │ 1:N                  │
       ▼                      │
┌──────────────┐    ┌─────────▼────────┐
│    teams     │    │  team_members    │
│──────────────│    │──────────────────│
│ id (UUID) PK │◄───│ team_id FK       │
│ org_id FK    │    │ user_id FK       │
│ name         │    │ role             │
│ slug         │    │ UNIQUE(team,user)│
│ UNIQUE(org,  │    └──────────────────┘
│   slug)      │
│ created_at   │
└──┬───┬───┬───┘
   │   │   │
   │   │   │ 1:N
   │   │   ▼
   │   │ ┌──────────────────┐
   │   │ │   repositories   │
   │   │ │──────────────────│
   │   │ │ id (UUID) PK     │
   │   │ │ team_id FK       │
   │   │ │ name             │
   │   │ │ local_path       │
   │   │ │ default_branch   │
   │   │ │ config (JSONB)   │
   │   │ │ UNIQUE(team,name)│
   │   │ │ created_at       │
   │   │ └──────────────────┘
   │   │
   │   │ 1:N
   │   ▼
   │ ┌──────────────────┐
   │ │     agents       │
   │ │──────────────────│
   │ │ id (UUID) PK     │
   │ │ team_id FK       │
   │ │ name             │
   │ │ role             │  manager | engineer | reviewer
   │ │ model            │  default: claude-sonnet-4-20250514
   │ │ config (JSONB)   │  token budgets, tool restrictions
   │ │ status           │  idle | working | paused
   │ │ UNIQUE(team,name)│
   │ │ created_at       │
   │ └──────────────────┘
   │
   │ 1:N
   ▼
┌────────────────────┐     ┌──────────────────┐
│       tasks        │     │    messages       │
│────────────────────│     │──────────────────│
│ id (SERIAL) PK     │◄────│ task_id FK       │
│ team_id FK         │     │ id (SERIAL) PK   │
│ title              │     │ team_id FK       │
│ description        │     │ sender_id        │
│ status             │     │ sender_type      │  agent | user
│ priority           │     │ recipient_id     │
│ dri_id FK→agents   │     │ recipient_type   │  agent | user
│ assignee_id FK     │     │ content          │
│ depends_on INT[]   │     │ delivered_at     │
│ repo_ids UUID[]    │     │ seen_at          │
│ tags TEXT[]        │     │ processed_at     │
│ branch             │     │ created_at       │
│ metadata JSONB     │     └──────────────────┘
│ created_at         │
│ updated_at         │
│ completed_at       │
└────────────────────┘

┌──────────────────┐     ┌──────────────────┐
│     events       │     │    sessions      │
│──────────────────│     │──────────────────│
│ id (SERIAL) PK   │     │ id (SERIAL) PK   │
│ stream_id        │     │ agent_id FK      │
│ type             │     │ task_id          │
│ data JSONB       │     │ started_at       │
│ metadata JSONB   │     │ ended_at         │
│ created_at       │     │ tokens_in        │
└──────────────────┘     │ tokens_out       │
                         │ cache_read       │
  Append-only.           │ cache_write      │
  Never updated.         │ cost_usd         │
  Never deleted.         │ model            │
                         │ error            │
                         └──────────────────┘
```

## Tables

### organizations

Top-level tenant boundary. All data is scoped to an org.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| name | VARCHAR(100) | |
| slug | VARCHAR(100) | Unique, URL-friendly |
| created_at | TIMESTAMPTZ | Server default: now() |
| updated_at | TIMESTAMPTZ | Auto-updated on change |

### teams

Scopes work within an org. Each team has its own agents, repos, and tasks.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| org_id | UUID FK→organizations | |
| name | VARCHAR(100) | |
| slug | VARCHAR(100) | Unique per org |
| created_at | TIMESTAMPTZ | |

Creating a team auto-provisions a manager agent.

### agents

AI agents within a team.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| team_id | UUID FK→teams | |
| name | VARCHAR(100) | Unique per team |
| role | VARCHAR(50) | `manager`, `engineer`, `reviewer` |
| model | VARCHAR(50) | Default: `claude-sonnet-4-20250514` |
| config | JSONB | Token budgets, allowed tools, etc. |
| status | VARCHAR(20) | `idle`, `working`, `paused` |
| created_at | TIMESTAMPTZ | |

### tasks

Central entity. Flows through a DAG-enforced state machine.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key |
| team_id | UUID FK→teams | |
| title | VARCHAR(500) | |
| description | TEXT | |
| status | VARCHAR(30) | See [state machine](tasks.md) |
| priority | VARCHAR(10) | `low`, `medium`, `high`, `critical` |
| dri_id | UUID FK→agents | Directly responsible individual |
| assignee_id | UUID FK→agents | Who's working on it |
| depends_on | INTEGER[] | Task IDs that must be done first |
| repo_ids | UUID[] | Repos this task touches |
| tags | TEXT[] | Flexible categorization |
| branch | VARCHAR(200) | Auto-generated: `task-{id}-{slug}` |
| metadata | JSONB | Extensible metadata |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-updated |
| completed_at | TIMESTAMPTZ | Set when status → done |

**Indexes:** `(team_id, status)`, `(assignee_id)`

### messages

Inter-agent and human-agent communication.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key |
| team_id | UUID FK→teams | |
| sender_id | UUID | Agent or user UUID |
| sender_type | VARCHAR(10) | `agent` or `user` |
| recipient_id | UUID | Agent or user UUID |
| recipient_type | VARCHAR(10) | `agent` or `user` |
| task_id | INTEGER FK→tasks | Optional, links message to a task |
| content | TEXT | |
| delivered_at | TIMESTAMPTZ | |
| seen_at | TIMESTAMPTZ | |
| processed_at | TIMESTAMPTZ | Set when recipient handles message |
| created_at | TIMESTAMPTZ | |

**Indexes:** `(recipient_id, processed_at)`, `(task_id)`

### events

Append-only event log. Source of truth for event sourcing.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key, monotonic |
| stream_id | VARCHAR(200) | e.g. `task:42`, `team:<uuid>` |
| type | VARCHAR(100) | e.g. `task.created`, `task.status_changed` |
| data | JSONB | Event payload |
| metadata | JSONB | actor_id, correlation_id, causation_id |
| created_at | TIMESTAMPTZ | |

**Indexes:** `(stream_id, id)`, `(type)`, `(created_at)`

Never updated. Never deleted.

### sessions

Tracks agent work sessions for cost control.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key |
| agent_id | UUID FK→agents | |
| task_id | INTEGER | |
| started_at | TIMESTAMPTZ | |
| ended_at | TIMESTAMPTZ | |
| tokens_in | INTEGER | Input tokens |
| tokens_out | INTEGER | Output tokens |
| cache_read | INTEGER | Cached tokens read |
| cache_write | INTEGER | Cached tokens written |
| cost_usd | NUMERIC(10,6) | Computed cost |
| model | VARCHAR(50) | Model used |
| error | TEXT | Error message if session failed |

## PostgreSQL-Specific Features

- **JSONB** for flexible config and event data (indexable, queryable)
- **ARRAY columns** for `depends_on`, `repo_ids`, `tags` (native PostgreSQL, not JSON strings)
- **UUID primary keys** for distributed-safe IDs
- **LISTEN/NOTIFY** (Phase 6) for instant agent dispatch
- **Row-level security** (Phase 9) for multi-tenant isolation
