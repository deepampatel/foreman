# Task State Machine — Entourage

## State Diagram

```
                    ┌──────────────────────────────────────────────────┐
                    │                                                  │
                    ▼                                                  │
               ┌────────┐     ┌─────────────┐     ┌─────────────┐    │
               │  todo   │────►│ in_progress │────►│  in_review  │    │
               └────┬────┘     └──────┬──────┘     └──────┬──────┘    │
                    │                 │                    │           │
                    │                 │    ┌───────────────┘           │
                    │                 │    │                           │
                    │                 │    ▼                           │
                    │                 │  ┌─────────────┐              │
                    │                 │  │ in_approval  │─────────────┘
                    │                 │  └──────┬──────┘    (reject)
                    │                 │         │
                    │                 │         ▼
                    │                 │  ┌─────────────┐
                    │                 │  │   merging    │─────────────┐
                    │                 │  └──────┬──────┘  (merge fail)│
                    │                 │         │                     │
                    │                 │         ▼                     │
                    │                 │  ┌─────────────┐             │
                    │                 │  │    done      │             │
                    │                 │  └─────────────┘             │
                    │                 │                               │
                    ▼                 ▼                               │
               ┌─────────────────────────┐                          │
               │       cancelled         │                          │
               └─────────────────────────┘                          │
```

## Transition Table

| From | Allowed transitions |
|------|-------------------|
| `todo` | `in_progress`, `cancelled` |
| `in_progress` | `in_review`, `todo`, `cancelled` |
| `in_review` | `in_approval`, `in_progress`, `cancelled` |
| `in_approval` | `merging`, `in_progress`, `cancelled` |
| `merging` | `done`, `in_progress` |
| `done` | _(terminal — no transitions)_ |
| `cancelled` | _(terminal — no transitions)_ |

Any transition not in this table returns HTTP 409 Conflict.

## Typical Workflow

```
1. Manager creates task              → status: todo
2. Manager assigns to engineer       → assignee set
3. Engineer starts work              → status: in_progress
4. Engineer creates worktree         → git branch isolated
5. Engineer finishes, submits        → status: in_review
6. Review requested                  → review.created event
7. Reviewer approves code            → status: in_approval
8. Manager approves for merge        → status: merging
9. Merge worker merges the branch    → status: done
```

## Rejection / Failure Loops

Tasks can move backward:

- **Review rejection:** `in_review` → `in_progress` (reviewer found issues)
- **Approval rejection:** `in_approval` → `in_progress` (manager wants changes)
- **Merge failure:** `merging` → `in_progress` (conflicts or CI failure)

## DAG Dependency Enforcement

Tasks can declare dependencies via the `depends_on` integer array.

```
Task A: id=1, status=todo, depends_on=[]
Task B: id=2, status=todo, depends_on=[1]
Task C: id=3, status=todo, depends_on=[1, 2]
```

**Rules:**
- A task with `depends_on` cannot move to `in_progress` until ALL dependencies have status `done`
- Missing dependency IDs (referencing non-existent tasks) also block the transition
- Dependencies are only checked when transitioning TO `in_progress`
- No circular dependency detection yet (enforced by convention)

**Example:**
```
POST /api/v1/tasks/2/status  {"status": "in_progress"}

→ 409 Conflict: "Blocked by unresolved dependencies: task 1 (todo)"

# Complete task 1 first...
POST /api/v1/tasks/1/status  {"status": "in_progress"}
POST /api/v1/tasks/1/status  {"status": "in_review"}
POST /api/v1/tasks/1/status  {"status": "in_approval"}
POST /api/v1/tasks/1/status  {"status": "merging"}
POST /api/v1/tasks/1/status  {"status": "done"}

# Now task 2 can start
POST /api/v1/tasks/2/status  {"status": "in_progress"}
→ 200 OK
```

## Human-in-the-Loop Integration

At any point during a task, an agent can pause to request human input:

```
Agent working on task → ask_human("Should I refactor the auth module?")
  → HumanRequest created (status: pending)
  → Agent waits for response
  → Human responds via dashboard or API
  → PG NOTIFY fires → Dispatcher resumes agent
```

Request types:
- **question** — Free-text answer
- **approval** — Yes/no decision
- **review** — Code/work review

## Code Review Flow

```
1. Agent completes work              → request_review(task_id)
2. Review created                    → attempt=1, verdict=null
3. Reviewer adds comments            → review_comments table
4. Reviewer renders verdict          → approve / reject / request_changes
5a. If approved                      → task moves to in_approval
5b. If rejected/request_changes      → task moves back to in_progress
                                       → new review attempt on resubmit
```

Multiple review cycles are tracked via the `attempt` field. Each cycle is a fresh review.

## Event Sourcing

Every task state change is recorded as an immutable event in the `events` table.

```
stream_id   type                  data
──────────  ────────────────────  ──────────────────────────────────
task:1      task.created          {"title": "Fix login", "priority": "high"}
task:1      task.assigned         {"from": null, "to": "<agent-uuid>"}
task:1      task.status_changed   {"from": "todo", "to": "in_progress"}
task:1      task.updated          {"priority": "critical"}
task:1      task.status_changed   {"from": "in_progress", "to": "in_review"}
task:1      review.created        {"review_id": 1, "attempt": 1}
task:1      review.verdict        {"verdict": "approve", "reviewer_id": "..."}
task:1      task.status_changed   {"from": "in_review", "to": "in_approval"}
task:1      task.status_changed   {"from": "in_approval", "to": "merging"}
task:1      merge.completed       {"merge_commit": "abc123"}
task:1      task.status_changed   {"from": "merging", "to": "done"}
```

Query the full history: `GET /api/v1/tasks/1/events`

## Event Types

### Task events
| Type | When | Data |
|------|------|------|
| `task.created` | Task created | title, priority, team_id, assignee_id, depends_on |
| `task.updated` | Fields changed (not status) | Changed fields only |
| `task.status_changed` | Status transition | from, to, actor_id |
| `task.assigned` | Assignee changed | from, to |
| `task.comment_added` | Comment added | content, author |
| `message.sent` | Message sent | sender_id, recipient_id, task_id |

### Session events
| Type | When | Data |
|------|------|------|
| `session.started` | Agent session begins | agent_id, task_id, model |
| `session.ended` | Agent session ends | cost_usd, tokens, error |
| `session.usage_recorded` | Token usage recorded | tokens_in, tokens_out |
| `agent.budget_exceeded` | Budget limit hit | agent_id, limit |

### Human-in-the-loop events
| Type | When | Data |
|------|------|------|
| `human_request.created` | Agent requests human input | kind, question |
| `human_request.resolved` | Human responds | response, responded_by |
| `human_request.expired` | Request timed out | |

### Review & merge events
| Type | When | Data |
|------|------|------|
| `review.created` | Review requested | task_id, attempt |
| `review.verdict` | Verdict rendered | verdict, reviewer_id |
| `review.comment_added` | Comment on review | file_path, line_number |
| `merge.queued` | Merge job created | task_id, strategy |
| `merge.started` | Merge worker picks up job | |
| `merge.completed` | Merge succeeded | merge_commit |
| `merge.failed` | Merge failed | error |

### Webhook & settings events
| Type | When | Data |
|------|------|------|
| `webhook.created` | Webhook configured | org_id, provider |
| `webhook.delivery_received` | Incoming payload | event_type |
| `webhook.delivery_processed` | Successfully processed | actions |
| `settings.updated` | Team settings changed | changes |

## Priority Levels

| Priority | Use case |
|----------|----------|
| `low` | Nice to have, no deadline |
| `medium` | Default. Standard work items |
| `high` | Important, should be done soon |
| `critical` | Blocking other work, do immediately |

## Batch Task Creation

The `POST /api/v1/teams/{team_id}/tasks/batch` endpoint (and the `create_tasks_batch` MCP tool) creates multiple tasks in a single request with support for intra-batch dependencies.

### Request Format

```json
{
  "tasks": [
    {"title": "Set up database models", "assignee_id": "agent-uuid-1"},
    {"title": "Build API endpoints", "assignee_id": "agent-uuid-2", "depends_on_indices": [0]},
    {"title": "Write integration tests", "depends_on_indices": [0, 1]}
  ]
}
```

### How `depends_on_indices` Works

- Each task in the array can reference other tasks **in the same batch** by their 0-based array index
- After all tasks are created and assigned real IDs, the indices are resolved to actual `depends_on` task IDs
- Task at index 1 with `depends_on_indices: [0]` means it depends on the task at index 0 in the batch
- Standard DAG dependency enforcement applies — the dependent task cannot move to `in_progress` until its dependencies reach `done`

This is the primary mechanism for a manager agent to plan and dispatch a multi-step project in one call.

## Multi-Agent Orchestration

The `wait_for_task_completion` MCP tool enables blocking coordination between agents. A manager agent can assign work to engineer agents and then block until the work is done before proceeding with the next step.

### Blocking Pattern

```
Manager creates batch of tasks with dependencies
  → Assigns task A to engineer-1
  → Assigns task B to engineer-2
  → Calls wait_for_task_completion(task_id=A)
  → Blocked until engineer-1 finishes (task A reaches "done" or "cancelled")
  → Calls wait_for_task_completion(task_id=B)
  → Blocked until engineer-2 finishes
  → Manager continues with follow-up work
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `task_id` | _(required)_ | The task to wait on |
| `timeout_seconds` | 3600 | Max wait time before the call errors |
| `terminal_statuses` | `["done", "cancelled"]` | Which statuses count as "complete" |

The tool polls the task status internally and returns the full task object once a terminal status is reached. If the timeout expires, it returns an error so the manager can decide how to proceed (retry, escalate, cancel).

### Discovering Agents

Use `list_team_agents` to discover available agents and their current status (`idle`, `working`, `paused`) before assigning work. This lets a manager agent make informed assignment decisions based on agent availability.
