"""Event type constants.

Learn: Centralizing event types as constants prevents typos and
makes it easy to discover all event types in the system.
Each phase adds its own event types here.
"""

# ─── Phase 1: Team/Agent/Repo lifecycle ──────────────────

TEAM_CREATED = "team.created"
AGENT_CREATED = "agent.created"
AGENT_STATUS_CHANGED = "agent.status_changed"
REPO_REGISTERED = "repo.registered"

# ─── Phase 2: Task lifecycle ─────────────────────────────

TASK_CREATED = "task.created"
TASK_UPDATED = "task.updated"
TASK_STATUS_CHANGED = "task.status_changed"
TASK_ASSIGNED = "task.assigned"
TASK_COMMENT_ADDED = "task.comment_added"
MESSAGE_SENT = "message.sent"

# ─── Phase 4: Agent execution ────────────────────────────

SESSION_STARTED = "session.started"
SESSION_ENDED = "session.ended"
SESSION_USAGE_RECORDED = "session.usage_recorded"
AGENT_BUDGET_EXCEEDED = "agent.budget_exceeded"

# ─── Phase 7: Human-in-the-loop ──────────────────────────

HUMAN_REQUEST_CREATED = "human_request.created"
HUMAN_REQUEST_RESOLVED = "human_request.resolved"
HUMAN_REQUEST_EXPIRED = "human_request.expired"
