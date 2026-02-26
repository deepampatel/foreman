# Task State Machine

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
4. Engineer finishes, submits        → status: in_review
5. Reviewer approves code            → status: in_approval
6. Manager approves for merge        → status: merging
7. Merge worker merges the branch    → status: done
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

## Event Sourcing

Every task state change is recorded as an immutable event in the `events` table.

```
stream_id   type                  data
──────────  ────────────────────  ──────────────────────────────────
task:1      task.created          {"title": "Fix login", "priority": "high"}
task:1      task.status_changed   {"from": "todo", "to": "in_progress"}
task:1      task.assigned         {"from": null, "to": "<agent-uuid>"}
task:1      task.updated          {"priority": "critical"}
task:1      task.status_changed   {"from": "in_progress", "to": "in_review"}
task:1      task.status_changed   {"from": "in_review", "to": "in_approval"}
task:1      task.status_changed   {"from": "in_approval", "to": "merging"}
task:1      task.status_changed   {"from": "merging", "to": "done"}
```

Query the full history: `GET /api/v1/tasks/1/events`

## Event Types

| Type | When | Data |
|------|------|------|
| `task.created` | Task created | title, priority, team_id, assignee_id, depends_on |
| `task.updated` | Fields changed (not status) | Changed fields only |
| `task.status_changed` | Status transition | from, to, actor_id |
| `task.assigned` | Assignee changed | from, to |
| `message.sent` | Message sent | sender_id, recipient_id, task_id |

## Priority Levels

| Priority | Use case |
|----------|----------|
| `low` | Nice to have, no deadline |
| `medium` | Default. Standard work items |
| `high` | Important, should be done soon |
| `critical` | Blocking other work, do immediately |
