# MCP Tools Reference

Foreman exposes all platform capabilities as MCP tools. AI agents discover and call these tools via the [Model Context Protocol](https://modelcontextprotocol.io).

## Connection

```bash
OPENCLAW_API_URL=http://localhost:8000 node packages/mcp-server/dist/index.js
```

The MCP server communicates via stdio. Any MCP-compatible client (Claude, OpenClaw, etc.) can connect.

---

## Platform

### `ping`
Check if the Foreman platform is reachable and healthy.

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
Update task fields. Does NOT change status (use `change_task_status` for that).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | number | yes | Task ID |
| `title` | string | no | New title |
| `description` | string | no | New description |
| `priority` | string | no | New priority |
| `tags` | string[] | no | New tags |

### `change_task_status`
Change task status. Validates transitions and enforces DAG dependencies. Returns 409 if the transition is invalid or dependencies are unresolved.

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
Send a message to an agent or user.

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
Get an agent's inbox — messages addressed to them.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_id` | string | yes | | Agent UUID |
| `unprocessed_only` | boolean | no | `true` | Only return unprocessed messages |

---

## Planned Tools (Phase 3+)

| Phase | Tool | Description |
|-------|------|-------------|
| 3 | `get_task_diff` | Get git diff for a task's branch |
| 3 | `get_task_files` | List changed files for a task |
| 4 | `start_session` | Start an agent work session |
| 4 | `record_usage` | Record token/cost usage |
| 4 | `check_budget` | Check remaining budget |
| 7 | `ask_human` | Request human input |
| 7 | `respond_to_request` | Human responds to agent question |
| 8 | `approve_task` | Approve a task for merge |
| 8 | `reject_task` | Reject a task with feedback |
