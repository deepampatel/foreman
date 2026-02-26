"""Phase 2 API tests — Tasks, state machine, dependencies, messages.

Learn: These tests verify the DAG-enforced state machine, which is
the most important business logic in the system. We test:
1. Task CRUD
2. Valid and invalid status transitions
3. Dependency enforcement (can't start blocked tasks)
4. Event sourcing (every change recorded)
5. Messages (inter-agent communication)

Pattern: Build up test data using the API (org → team → agents → tasks).
"""

import pytest


# ═══════════════════════════════════════════════════════════
# Shared fixtures
# ═══════════════════════════════════════════════════════════


@pytest.fixture
async def org(client):
    resp = await client.post("/api/v1/orgs", json={"name": "Task Org", "slug": "task-org"})
    return resp.json()


@pytest.fixture
async def team(client, org):
    resp = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Task Team", "slug": "task-team"},
    )
    return resp.json()


@pytest.fixture
async def agents(client, team):
    """Create two agents and return them as (manager, engineer)."""
    # The team auto-creates a manager, so list to find it
    agents_resp = await client.get(f"/api/v1/teams/{team['id']}/agents")
    manager = agents_resp.json()[0]

    # Create an engineer
    eng_resp = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": "eng-1", "role": "engineer"},
    )
    engineer = eng_resp.json()
    return manager, engineer


# ═══════════════════════════════════════════════════════════
# Task CRUD
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_task(client, team):
    """POST /teams/:id/tasks should create a task in 'todo' status."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Fix login bug", "priority": "high", "tags": ["bug", "auth"]},
    )
    assert resp.status_code == 201
    task = resp.json()
    assert task["title"] == "Fix login bug"
    assert task["status"] == "todo"
    assert task["priority"] == "high"
    assert task["tags"] == ["bug", "auth"]
    assert task["branch"].startswith("task-")
    assert "fix-login-bug" in task["branch"]


@pytest.mark.asyncio
async def test_create_task_with_assignment(client, team, agents):
    """Task can be created with an assignee."""
    _, engineer = agents
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Build API", "assignee_id": engineer["id"]},
    )
    assert resp.status_code == 201
    assert resp.json()["assignee_id"] == engineer["id"]


@pytest.mark.asyncio
async def test_list_tasks(client, team):
    """GET /teams/:id/tasks should list all tasks."""
    await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Task A"},
    )
    await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Task B"},
    )

    resp = await client.get(f"/api/v1/teams/{team['id']}/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 2


@pytest.mark.asyncio
async def test_list_tasks_filter_by_status(client, team):
    """Tasks can be filtered by status."""
    # Create two tasks, move one to in_progress
    resp_a = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Still todo"},
    )
    resp_b = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Started"},
    )
    task_b = resp_b.json()
    await client.post(
        f"/api/v1/tasks/{task_b['id']}/status",
        json={"status": "in_progress"},
    )

    # Filter by in_progress
    resp = await client.get(
        f"/api/v1/teams/{team['id']}/tasks",
        params={"status": "in_progress"},
    )
    tasks = resp.json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Started"


@pytest.mark.asyncio
async def test_get_task(client, team):
    """GET /tasks/:id should return task details."""
    create_resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Get me"},
    )
    task_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Get me"


@pytest.mark.asyncio
async def test_get_task_404(client):
    """GET /tasks/:id for non-existent task returns 404."""
    resp = await client.get("/api/v1/tasks/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_task(client, team):
    """PATCH /tasks/:id should partially update task fields."""
    create_resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Original"},
    )
    task_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Updated", "priority": "critical"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"
    assert resp.json()["priority"] == "critical"


@pytest.mark.asyncio
async def test_assign_task(client, team, agents):
    """POST /tasks/:id/assign should set the assignee."""
    _, engineer = agents
    create_resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Assign me"},
    )
    task_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assign",
        json={"assignee_id": engineer["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["assignee_id"] == engineer["id"]


# ═══════════════════════════════════════════════════════════
# State Machine — valid transitions
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_status_todo_to_in_progress(client, team):
    """todo → in_progress is a valid transition."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Start me"},
    )
    task_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_full_workflow(client, team):
    """Task can go through the complete workflow: todo → done."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Full workflow"},
    )
    task_id = resp.json()["id"]

    # todo → in_progress → in_review → in_approval → merging → done
    for status in ["in_progress", "in_review", "in_approval", "merging", "done"]:
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/status",
            json={"status": status},
        )
        assert resp.status_code == 200, f"Failed at transition to {status}: {resp.json()}"
        assert resp.json()["status"] == status

    # Verify completed_at is set
    assert resp.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_cancel_from_any_active_state(client, team):
    """Tasks can be cancelled from any non-terminal state."""
    for start_status in ["todo", "in_progress", "in_review", "in_approval"]:
        resp = await client.post(
            f"/api/v1/teams/{team['id']}/tasks",
            json={"title": f"Cancel from {start_status}"},
        )
        task_id = resp.json()["id"]

        # Move to start_status
        if start_status != "todo":
            transitions = {
                "in_progress": ["in_progress"],
                "in_review": ["in_progress", "in_review"],
                "in_approval": ["in_progress", "in_review", "in_approval"],
            }
            for s in transitions[start_status]:
                await client.post(
                    f"/api/v1/tasks/{task_id}/status",
                    json={"status": s},
                )

        # Cancel
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/status",
            json={"status": "cancelled"},
        )
        assert resp.status_code == 200, f"Failed to cancel from {start_status}"
        assert resp.json()["status"] == "cancelled"


# ═══════════════════════════════════════════════════════════
# State Machine — INVALID transitions
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_invalid_transition_skip_steps(client, team):
    """Can't skip from 'todo' directly to 'in_review' (must go through in_progress)."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Skip steps"},
    )
    task_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "in_review"},
    )
    assert resp.status_code == 409  # Conflict


@pytest.mark.asyncio
async def test_invalid_transition_from_done(client, team):
    """Can't transition out of 'done' (terminal state)."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Terminal state"},
    )
    task_id = resp.json()["id"]

    # Move through to done
    for s in ["in_progress", "in_review", "in_approval", "merging", "done"]:
        await client.post(f"/api/v1/tasks/{task_id}/status", json={"status": s})

    # Try to go back
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_invalid_transition_from_cancelled(client, team):
    """Can't transition out of 'cancelled' (terminal state)."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Cancelled task"},
    )
    task_id = resp.json()["id"]

    await client.post(f"/api/v1/tasks/{task_id}/status", json={"status": "cancelled"})

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": "todo"},
    )
    assert resp.status_code == 409


# ═══════════════════════════════════════════════════════════
# DAG Dependency Enforcement
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dependency_blocks_start(client, team):
    """Can't start a task if its dependencies aren't done.

    Learn: This is the DAG enforcement — task B depends on task A,
    so B can't move to in_progress until A is done.
    """
    # Create task A (no deps)
    resp_a = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Task A (dependency)"},
    )
    task_a_id = resp_a.json()["id"]

    # Create task B (depends on A)
    resp_b = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Task B (blocked)", "depends_on": [task_a_id]},
    )
    task_b_id = resp_b.json()["id"]

    # Try to start B — should fail (A is still 'todo')
    resp = await client.post(
        f"/api/v1/tasks/{task_b_id}/status",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 409
    assert "dependencies" in resp.json()["detail"].lower() or "blocked" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_dependency_unblocks_after_done(client, team):
    """Once dependency is done, the blocked task can start."""
    # Create task A
    resp_a = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Task A"},
    )
    task_a_id = resp_a.json()["id"]

    # Create task B (depends on A)
    resp_b = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Task B", "depends_on": [task_a_id]},
    )
    task_b_id = resp_b.json()["id"]

    # Complete A
    for s in ["in_progress", "in_review", "in_approval", "merging", "done"]:
        await client.post(f"/api/v1/tasks/{task_a_id}/status", json={"status": s})

    # Now B should be able to start
    resp = await client.post(
        f"/api/v1/tasks/{task_b_id}/status",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


# ═══════════════════════════════════════════════════════════
# Event Sourcing
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_task_events_trail(client, team):
    """Every task change should create events in the event log."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Event trail"},
    )
    task_id = resp.json()["id"]

    # Move through states
    await client.post(f"/api/v1/tasks/{task_id}/status", json={"status": "in_progress"})
    await client.patch(f"/api/v1/tasks/{task_id}", json={"priority": "high"})

    # Get events
    resp = await client.get(f"/api/v1/tasks/{task_id}/events")
    assert resp.status_code == 200
    events = resp.json()

    types = [e["type"] for e in events]
    assert "task.created" in types
    assert "task.status_changed" in types
    assert "task.updated" in types

    # Verify status change event has from/to
    status_event = next(e for e in events if e["type"] == "task.status_changed")
    assert status_event["data"]["from"] == "todo"
    assert status_event["data"]["to"] == "in_progress"


# ═══════════════════════════════════════════════════════════
# Messages
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_send_message(client, team, agents):
    """POST /teams/:id/messages should send a message."""
    manager, engineer = agents

    resp = await client.post(
        f"/api/v1/teams/{team['id']}/messages",
        json={
            "sender_id": manager["id"],
            "sender_type": "agent",
            "recipient_id": engineer["id"],
            "recipient_type": "agent",
            "content": "Please work on the login bug.",
        },
    )
    assert resp.status_code == 201
    msg = resp.json()
    assert msg["content"] == "Please work on the login bug."
    assert msg["sender_id"] == manager["id"]
    assert msg["recipient_id"] == engineer["id"]


@pytest.mark.asyncio
async def test_get_inbox(client, team, agents):
    """GET /agents/:id/inbox should return unprocessed messages."""
    manager, engineer = agents

    # Send two messages to the engineer
    await client.post(
        f"/api/v1/teams/{team['id']}/messages",
        json={
            "sender_id": manager["id"],
            "sender_type": "agent",
            "recipient_id": engineer["id"],
            "recipient_type": "agent",
            "content": "Message 1",
        },
    )
    await client.post(
        f"/api/v1/teams/{team['id']}/messages",
        json={
            "sender_id": manager["id"],
            "sender_type": "agent",
            "recipient_id": engineer["id"],
            "recipient_type": "agent",
            "content": "Message 2",
        },
    )

    # Check inbox
    resp = await client.get(f"/api/v1/agents/{engineer['id']}/inbox")
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) == 2
    contents = [m["content"] for m in messages]
    assert "Message 1" in contents
    assert "Message 2" in contents
