# Database Schema — Entourage

## Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│organizations │       │    users     │       │   api_keys   │
│──────────────│       │──────────────│       │──────────────│
│ id (UUID) PK │       │ id (UUID) PK │       │ id (UUID) PK │
│ name         │       │ email UNIQUE │       │ org_id FK    │
│ slug UNIQUE  │       │ name         │       │ name         │
│ created_at   │       │ password_hash│       │ key_hash     │
│ updated_at   │       │ created_at   │       │ prefix       │
└──────┬───────┘       └──────┬───────┘       │ scopes[]     │
       │ 1:N                  │               │ expires_at   │
       ▼                      │               └──────────────┘
┌──────────────┐    ┌─────────▼────────┐
│    teams     │    │  team_members    │
│──────────────│    │──────────────────│
│ id (UUID) PK │◄───│ team_id FK       │
│ org_id FK    │    │ user_id FK       │
│ name         │    │ role             │
│ slug         │    │ UNIQUE(team,user)│
│ config JSONB │    └──────────────────┘
│ UNIQUE(org,  │
│   slug)      │
│ created_at   │
└──┬───┬───┬───┘
   │   │   │
   │   │   │ 1:N
   │   │   ▼
   │   │ ┌──────────────────┐
   │   │ │   repositories   │
   │   │ │──────────────────│       ┌──────────────────┐
   │   │ │ id (UUID) PK     │       │    webhooks      │
   │   │ │ team_id FK       │       │──────────────────│
   │   │ │ name             │       │ id (UUID) PK     │
   │   │ │ local_path       │       │ org_id FK        │
   │   │ │ default_branch   │       │ team_id FK       │
   │   │ │ config (JSONB)   │       │ name             │
   │   │ │ UNIQUE(team,name)│       │ provider         │
   │   │ │ created_at       │       │ secret           │
   │   │ └──────────────────┘       │ events[]         │
   │   │                            │ active           │
   │   │ 1:N                        │ config JSONB     │
   │   ▼                            └────────┬─────────┘
   │ ┌──────────────────┐                    │ 1:N
   │ │     agents       │           ┌────────▼─────────┐
   │ │──────────────────│           │webhook_deliveries│
   │ │ id (UUID) PK     │           │──────────────────│
   │ │ team_id FK       │           │ id (SERIAL) PK   │
   │ │ name             │           │ webhook_id FK    │
   │ │ role             │           │ event_type       │
   │ │ model            │           │ payload JSONB    │
   │ │ config (JSONB)   │           │ status           │
   │ │ status           │           │ error            │
   │ │ UNIQUE(team,name)│           │ created_at       │
   │ │ created_at       │           └──────────────────┘
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
│ status             │     │ sender_type      │
│ priority           │     │ recipient_id     │
│ dri_id FK→agents   │     │ recipient_type   │
│ assignee_id FK     │     │ content          │
│ depends_on INT[]   │     │ delivered_at     │
│ repo_ids UUID[]    │     │ seen_at          │
│ tags TEXT[]        │     │ processed_at     │
│ branch             │     │ created_at       │
│ metadata JSONB     │     └──────────────────┘
│ created_at         │
│ updated_at         │     ┌──────────────────┐
│ completed_at       │     │ human_requests   │
└──────────┬─────────┘     │──────────────────│
           │               │ id (SERIAL) PK   │
           │               │ team_id FK       │
           │               │ agent_id FK      │
           │               │ task_id FK       │
           │               │ kind             │
           │               │ question         │
           │               │ options[]        │
           │               │ status           │
           │               │ response         │
           │               │ responded_by     │
           │               │ timeout_at       │
           │               │ created_at       │
           │               │ resolved_at      │
           │               └──────────────────┘
           │
           ├──── reviews ──── review_comments
           │
           └──── merge_jobs

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
| config | JSONB | Team settings: budget limits, model prefs, workflow config |
| created_at | TIMESTAMPTZ | |

Creating a team auto-provisions a manager agent.

### users

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| email | VARCHAR(255) | Unique |
| name | VARCHAR(100) | |
| password_hash | VARCHAR(255) | Nullable (for OAuth users) |
| created_at | TIMESTAMPTZ | |

### team_members

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| team_id | UUID FK→teams | |
| user_id | UUID FK→users | |
| role | VARCHAR(50) | `owner`, `admin`, `member` |
| | | UNIQUE(team_id, user_id) |

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

### repositories

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| team_id | UUID FK→teams | |
| name | VARCHAR(100) | Unique per team |
| local_path | TEXT | Filesystem path |
| default_branch | VARCHAR(100) | Default: `main` |
| config | JSONB | Approval mode, test commands, etc. |
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

Inter-agent and human-agent communication. Insert trigger fires PG NOTIFY for dispatcher.

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
**Trigger:** `notify_new_message()` — fires PG NOTIFY on INSERT

### events

Append-only event log. Source of truth for event sourcing.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key, monotonic |
| stream_id | VARCHAR(200) | e.g. `task:42`, `team:<uuid>`, `webhook:<uuid>` |
| type | VARCHAR(100) | e.g. `task.created`, `review.verdict`, `webhook.delivery_received` |
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

### human_requests

Agent requests for human input — questions, approvals, reviews.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key |
| team_id | UUID FK→teams | |
| agent_id | UUID FK→agents | |
| task_id | INTEGER FK→tasks | Optional |
| kind | VARCHAR(30) | `question`, `approval`, `review` |
| question | TEXT | The request text |
| options | TEXT[] | Pre-defined answer options |
| status | VARCHAR(20) | `pending`, `resolved`, `expired` |
| response | TEXT | Human's response |
| responded_by | UUID | User who responded |
| timeout_at | TIMESTAMPTZ | Auto-expire time |
| created_at | TIMESTAMPTZ | |
| resolved_at | TIMESTAMPTZ | |

**Indexes:** `(team_id, status)`
**Trigger:** `notify_human_request_resolved()` — fires PG NOTIFY on status UPDATE

### reviews

Code review for a task. Multiple review attempts tracked.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key |
| task_id | INTEGER FK→tasks | |
| attempt | INTEGER | Auto-incremented per task |
| reviewer_id | UUID | User or agent who reviewed |
| reviewer_type | VARCHAR(10) | `user` or `agent` |
| verdict | VARCHAR(20) | `approve`, `request_changes`, `reject` (null = pending) |
| summary | TEXT | Review summary |
| created_at | TIMESTAMPTZ | |
| resolved_at | TIMESTAMPTZ | |

**Constraints:** UNIQUE(task_id, attempt)

### review_comments

Comments anchored to specific files/lines in a review.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key |
| review_id | INTEGER FK→reviews | |
| author_id | UUID | |
| author_type | VARCHAR(10) | `user` or `agent` |
| file_path | TEXT | Optional file anchor |
| line_number | INTEGER | Optional line anchor |
| content | TEXT | Comment text |
| created_at | TIMESTAMPTZ | |

### merge_jobs

Background merge jobs queued after review approval.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key |
| task_id | INTEGER FK→tasks | |
| repo_id | UUID FK→repositories | |
| status | VARCHAR(20) | `queued`, `running`, `success`, `failed` |
| strategy | VARCHAR(20) | `rebase`, `merge`, `squash` |
| error | TEXT | Error message if failed |
| merge_commit | VARCHAR(40) | SHA of merge commit |
| created_at | TIMESTAMPTZ | |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |

### api_keys

API keys for programmatic access (agents, CI systems).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| org_id | UUID FK→organizations | |
| name | VARCHAR(100) | |
| key_hash | VARCHAR(255) | SHA-256 hash (key never stored) |
| prefix | VARCHAR(10) | e.g. `oc_abc123` for identification |
| scopes | TEXT[] | `all`, `read`, `agent` |
| last_used_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |
| expires_at | TIMESTAMPTZ | Optional expiry |

### webhooks

Incoming webhook configurations for GitHub/GitLab/etc.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| org_id | UUID FK→organizations | |
| team_id | UUID FK→teams | Optional (null = org-wide) |
| name | VARCHAR(100) | |
| provider | VARCHAR(30) | `github`, `gitlab`, `bitbucket`, `custom` |
| secret | VARCHAR(255) | HMAC signing secret |
| events | TEXT[] | Event types to listen for |
| active | BOOLEAN | Enable/disable |
| config | JSONB | Provider-specific config |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### webhook_deliveries

Audit trail for incoming webhook payloads.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL | Primary key |
| webhook_id | UUID FK→webhooks | |
| event_type | VARCHAR(50) | `push`, `pull_request`, `issues`, etc. |
| payload | JSONB | Incoming payload (sanitized) |
| status | VARCHAR(20) | `received`, `processed`, `failed`, `ignored` |
| error | TEXT | Error message if processing failed |
| created_at | TIMESTAMPTZ | |

## PostgreSQL-Specific Features

- **JSONB** for flexible config and event data (indexable, queryable)
- **ARRAY columns** for `depends_on`, `repo_ids`, `tags`, `scopes`, `events` (native PostgreSQL)
- **UUID primary keys** for distributed-safe IDs
- **LISTEN/NOTIFY** for instant agent dispatch via PG triggers
- **Trigger functions**: `notify_new_message()`, `notify_human_request_resolved()`, `notify_task_status_changed()`

## Alembic Migrations

| Revision | Description |
|----------|-------------|
| `858c9f17a644` | Phase 1: orgs, teams, users, agents, repos, events, sessions |
| `0ac40d24a4c8` | Phase 2: tasks and messages |
| `31a70288aa72` | Phase 7: human_requests table |
| `ba9513c684e2` | Phase 8: reviews, review_comments, merge_jobs |
| `85a67264382e` | Phase 6: PG LISTEN/NOTIFY trigger functions |
| `b9273a98ca4c` | Phase 9: api_keys table |
| `8fd38d37a5f3` | Phase 10: webhooks and webhook_deliveries |
| `d29768ed705e` | Phase 10: add config column to teams |

## Schema Coverage

The database schema documented above covers all features through Phase 17. Phases 11-17 (agent adapters, CLI, merge worker, auth hardening, orchestration tools, batch task creation, multi-agent orchestration, E2E tests, DevOps, and frontend enhancements) did not introduce new database tables. These features operate on the existing schema — the agent adapter system uses the `agents` and `sessions` tables, batch task creation writes to the existing `tasks` table, and the merge worker reads from `merge_jobs` which was added in Phase 8.
