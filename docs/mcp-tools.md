# MCP Tools Reference — Entourage

Entourage exposes all platform capabilities as MCP tools. AI agents discover and call these tools via the [Model Context Protocol](https://modelcontextprotocol.io).

**Total tools: 50**

## Connection

```bash
OPENCLAW_API_URL=http://localhost:8000 node packages/mcp-server/dist/index.js
```

The MCP server communicates via stdio. Any MCP-compatible client (Claude, etc.) can connect.

---

## Platform

### `ping`
Check if the OpenClaw platform is reachable and healthy.

**Parameters:** none

---

## Organizations

### `list_orgs`
List all organizations.

**Parameters:** none

### `create_org`
Create a new organization.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | yes | Organization name |
| `slug` | string | yes | URL-friendly slug (lowercase, hyphens) |

---

## Teams

### `list_teams`
List all teams in an organization.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `org_id` | string | yes | Organization UUID |

### `create_team`
Create a new team. Auto-provisions a manager agent.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `org_id` | string | yes | Organization UUID |
| `name` | string | yes | Team name |
| `slug` | string | yes | URL-friendly slug |

### `get_team`
Get team details including agents and repositories.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |

---

## Agents

### `list_agents`
List all agents in a team.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |

### `create_agent`
Create a new agent in a team.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `team_id` | string | yes | | Team UUID |
| `name` | string | yes | | Agent name |
| `role` | string | no | `engineer` | `manager`, `engineer`, or `reviewer` |
| `model` | string | no | `claude-sonnet-4-20250514` | LLM model to use |

---

## Repositories

### `list_repos`
List all repositories registered with a team.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |

### `register_repo`
Register a git repository with a team.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `team_id` | string | yes | | Team UUID |
| `name` | string | yes | | Repository name |
| `local_path` | string | yes | | Local filesystem path |
| `default_branch` | string | no | `main` | Default branch name |

---

## Tasks

### `create_task`
Create a new task. Starts in `todo` status. Auto-generates a branch name.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `team_id` | string | yes | | Team UUID |
| `title` | string | yes | | Task title |
| `description` | string | no | `""` | Task description |
| `priority` | string | no | `medium` | `low`, `medium`, `high`, `critical` |
| `assignee_id` | string | no | | Agent UUID to assign |
| `depends_on` | number[] | no | `[]` | Task IDs this task depends on |
| `tags` | string[] | no | `[]` | Tags for categorization |

### `list_tasks`
List tasks for a team with optional filters.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |
| `status` | string | no | Filter by status |
| `assignee_id` | string | no | Filter by assigned agent |

### `get_task`
Get detailed info about a single task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |

### `update_task`
Update task fields. Does NOT change status (use `change_task_status`).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `title` | string | no | New title |
| `description` | string | no | New description |
| `priority` | string | no | New priority |
| `tags` | string[] | no | New tags |

### `change_task_status`
Change task status. Validates transitions and enforces DAG dependencies. Returns 409 if invalid.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `status` | string | yes | New status |
| `actor_id` | string | no | UUID of the agent/user making the change |

See [Task State Machine](tasks.md) for valid transitions.

### `assign_task`
Assign an agent to work on a task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `assignee_id` | string | yes | Agent UUID |

### `get_task_events`
Get the immutable event history for a task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |

---

## Messages

### `send_message`
Send a message to an agent or user. Triggers PG NOTIFY for dispatcher.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |
| `sender_id` | string | yes | Sender UUID |
| `sender_type` | string | yes | `agent` or `user` |
| `recipient_id` | string | yes | Recipient UUID |
| `recipient_type` | string | yes | `agent` or `user` |
| `content` | string | yes | Message content |
| `task_id` | number | no | Related task ID |

### `get_inbox`
Get an agent's inbox.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_id` | string | yes | | Agent UUID |
| `unprocessed_only` | boolean | no | `true` | Only return unprocessed messages |

---

## Git (Phase 3)

### `create_worktree`
Create a git worktree for a task (branch-per-task isolation).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `repo_id` | string | yes | Repository UUID |

### `get_worktree`
Get worktree info for a task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `repo_id` | string | yes | Repository UUID |

### `remove_worktree`
Remove a task's worktree.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `repo_id` | string | yes | Repository UUID |

### `get_task_diff`
Get the git diff for a task's branch.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `repo_id` | string | yes | Repository UUID |

### `get_changed_files`
List files changed in a task's branch.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `repo_id` | string | yes | Repository UUID |

### `read_file`
Read a file from a task's branch.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `repo_id` | string | yes | Repository UUID |
| `path` | string | yes | File path within the repo |

### `get_commits`
Get commit history for a task's branch.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `task_id` | number | yes | | Task ID |
| `repo_id` | string | yes | | Repository UUID |
| `limit` | number | no | 20 | Max commits to return |

---

## Sessions & Costs (Phase 4)

### `start_session`
Start an agent work session. Tracks tokens, cost, and time.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | yes | Agent UUID |
| `task_id` | number | no | Task being worked on |
| `model` | string | no | Model override |

### `record_usage`
Record token usage during a session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | number | yes | | Session ID |
| `tokens_in` | number | no | 0 | Input tokens |
| `tokens_out` | number | no | 0 | Output tokens |
| `cache_read` | number | no | 0 | Cache tokens read |
| `cache_write` | number | no | 0 | Cache tokens written |

### `end_session`
End a session. Sets agent back to idle.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | number | yes | Session ID |
| `error` | string | no | Error message if session failed |

### `check_budget`
Check if an agent has budget remaining (daily and per-task limits).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | yes | Agent UUID |
| `task_id` | number | no | Task ID for task-level budget check |

### `get_cost_summary`
Get cost summary for a team — per-agent and per-model breakdown.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `team_id` | string | yes | | Team UUID |
| `days` | number | no | 7 | Lookback period |

---

## Human-in-the-Loop (Phase 7)

### `ask_human`
Ask a human for input. Creates a persistent request shown in the dashboard.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `team_id` | string | yes | | Team UUID |
| `agent_id` | string | yes | | Agent UUID making the request |
| `kind` | string | yes | | `question`, `approval`, or `review` |
| `question` | string | yes | | The question or request text |
| `task_id` | number | no | | Related task ID |
| `options` | string[] | no | `[]` | Pre-defined answer options |
| `timeout_minutes` | number | no | | Auto-expire after N minutes |

### `get_pending_requests`
Get pending human requests for a team.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |
| `agent_id` | string | no | Filter by agent |
| `task_id` | number | no | Filter by task |

### `respond_to_request`
Respond to a pending human request.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `request_id` | number | yes | Human request ID |
| `response` | string | yes | The response text |
| `responded_by` | string | no | User UUID |

---

## Reviews & Merge (Phase 8)

### `request_review`
Request a code review for a task.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `task_id` | number | yes | | Task ID to review |
| `reviewer_id` | string | no | | Reviewer UUID |
| `reviewer_type` | string | no | `user` | `user` or `agent` |

### `approve_task`
Approve the latest review for a task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID to approve |
| `summary` | string | no | Approval notes |
| `reviewer_id` | string | no | Reviewer UUID |

### `reject_task`
Reject the latest review for a task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID to reject |
| `summary` | string | no | Rejection feedback |
| `reviewer_id` | string | no | Reviewer UUID |

### `get_merge_status`
Get merge readiness status — review verdict, merge jobs, can_merge flag.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |

### `get_review_feedback`
Get the latest review feedback for a task — comments, verdict, and summary from the most recent `request_changes` review. Use this to understand what the reviewer wants you to fix.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |

Returns formatted review comments, file locations, and the reviewer's summary. Returns `null` if no `request_changes` review exists.

---

## Auth (Phase 9)

### `authenticate`
Validate an API key and return the scoped identity.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `api_key` | string | yes | API key to validate (e.g. `oc_...`) |

---

## Webhooks (Phase 10)

### `create_webhook`
Create a webhook to receive events from GitHub/GitLab.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `org_id` | string | yes | | Organization UUID |
| `name` | string | yes | | Webhook name |
| `team_id` | string | no | | Scope to a team |
| `provider` | string | no | `github` | `github`, `gitlab`, `bitbucket`, `custom` |
| `events` | string[] | no | `["push", "pull_request"]` | Event types to listen for |

### `list_webhooks`
List webhooks for an organization.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `org_id` | string | yes | | Organization UUID |
| `team_id` | string | no | | Filter by team |
| `active_only` | boolean | no | false | Only show active webhooks |

### `update_webhook`
Update a webhook configuration.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `webhook_id` | string | yes | Webhook UUID |
| `name` | string | no | New name |
| `events` | string[] | no | New event types |
| `active` | boolean | no | Enable/disable |

---

## Settings (Phase 10)

### `get_team_settings`
Get team-level configuration.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |

### `update_team_settings`
Update team configuration. Only provided fields are changed (merge behavior).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |
| `daily_cost_limit_usd` | number | no | Daily cost limit |
| `task_cost_limit_usd` | number | no | Per-task cost limit |
| `default_model` | string | no | Default model for new sessions |
| `auto_merge` | boolean | no | Auto-merge after approval |
| `require_review` | boolean | no | Require review before merge |
| `branch_prefix` | string | no | Branch naming prefix |

### `get_team_conventions`
Get team coding conventions — standards, architecture decisions, testing strategies. These are injected into agent prompts automatically.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |

Returns an array of convention objects: `{key, content, active}`.

### `add_team_convention`
Record a new team convention. Agents will follow this in future runs.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `team_id` | string | yes | | Team UUID |
| `key` | string | yes | | Convention identifier (e.g. `testing`, `code_style`, `architecture`) |
| `content` | string | yes | | The convention text — what agents should follow |
| `active` | boolean | no | `true` | Whether the convention is active |

Conventions are stored in the team's JSONB config and automatically injected into agent prompts. Returns 409 if a convention with the same key already exists.

---

## Orchestration (Phase 14)

### `wait_for_task_completion`
Block until a task reaches a terminal status. Used by manager agents to coordinate multi-agent workflows — assign work, then wait for the engineer to finish before proceeding.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `task_id` | number | yes | | Task ID to wait on |
| `timeout_seconds` | number | no | 3600 | Max seconds to wait before timing out |
| `terminal_statuses` | string[] | no | `["done", "cancelled"]` | Statuses that count as "complete" |

Returns the task object once it reaches a terminal status, or errors on timeout.

### `create_tasks_batch`
Create multiple tasks in a single call with intra-batch dependency support. Tasks can reference other tasks in the same batch by index via `depends_on_indices`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |
| `tasks` | array | yes | Array of task objects (see below) |

Each task object in the array:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Task title |
| `description` | string | no | Task description |
| `assignee_id` | string | no | Agent UUID to assign |
| `depends_on_indices` | number[] | no | Indices (0-based) of other tasks in this batch that must complete first |

Indices are resolved to real task IDs after creation. Returns all created tasks.

### `list_team_agents`
List all agents in a team with their current status. Convenience tool for orchestration — lets a manager agent discover available engineers before assigning work.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | yes | Team UUID |
