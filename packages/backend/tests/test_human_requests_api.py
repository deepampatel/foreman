"""Phase 7: Human-in-the-loop tests.

Learn: Tests cover the full request lifecycle:
1. Agent creates a request (question, approval, review)
2. Human responds → request resolved
3. List/filter requests by status, agent, task
4. Error cases: not found, already resolved, invalid agent
5. Timeout handling
"""

import uuid

import pytest


# ─── Helper: create org + team + agent ────────────────────


async def _setup(client, slug_suffix=""):
    """Create org → team → agent, return IDs."""
    slug = f"human-loop-{uuid.uuid4().hex[:8]}{slug_suffix}"

    r = await client.post("/api/v1/orgs", json={"name": "HITL Test Org", "slug": slug})
    assert r.status_code in (200, 201)
    org = r.json()

    r = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "HITL Team", "slug": f"team-{slug}"},
    )
    assert r.status_code in (200, 201)
    team = r.json()

    # Get auto-provisioned manager agent
    r = await client.get(f"/api/v1/teams/{team['id']}/agents")
    assert r.status_code == 200
    agents = r.json()
    manager = agents[0]

    # Create engineer agent
    r = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": f"eng-{slug}", "role": "engineer"},
    )
    assert r.status_code in (200, 201)
    engineer = r.json()

    return {
        "org_id": org["id"],
        "team_id": team["id"],
        "manager_id": manager["id"],
        "engineer_id": engineer["id"],
    }


# ═══════════════════════════════════════════════════════════
# Create Request
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_question_request(client):
    """Agent creates a question request."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "question",
            "question": "Which database should I use for the new feature?",
            "options": ["PostgreSQL", "MongoDB", "SQLite"],
        },
    )
    assert r.status_code == 201
    hr = r.json()
    assert hr["kind"] == "question"
    assert hr["question"] == "Which database should I use for the new feature?"
    assert hr["options"] == ["PostgreSQL", "MongoDB", "SQLite"]
    assert hr["status"] == "pending"
    assert hr["response"] is None
    assert hr["resolved_at"] is None


@pytest.mark.asyncio
async def test_create_approval_request(client):
    """Agent creates an approval request."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "approval",
            "question": "Deploy to production?",
            "options": ["approve", "reject"],
        },
    )
    assert r.status_code == 201
    hr = r.json()
    assert hr["kind"] == "approval"
    assert hr["options"] == ["approve", "reject"]


@pytest.mark.asyncio
async def test_create_request_with_task(client):
    """Request can be linked to a task."""
    ids = await _setup(client)

    # Create a task
    r = await client.post(
        f"/api/v1/teams/{ids['team_id']}/tasks",
        json={"title": "HITL task"},
    )
    task = r.json()

    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "review",
            "question": "Please review my implementation",
            "task_id": task["id"],
        },
    )
    assert r.status_code == 201
    assert r.json()["task_id"] == task["id"]


@pytest.mark.asyncio
async def test_create_request_with_timeout(client):
    """Request with timeout has timeout_at set."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "question",
            "question": "Quick decision needed",
            "timeout_minutes": 30,
        },
    )
    assert r.status_code == 201
    hr = r.json()
    assert hr["timeout_at"] is not None


@pytest.mark.asyncio
async def test_create_request_invalid_agent(client):
    """Request with invalid agent ID returns 404."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": str(uuid.uuid4()),
            "kind": "question",
            "question": "This should fail",
        },
    )
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════
# Respond to Request
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_respond_to_request(client):
    """Human responds to a pending request."""
    ids = await _setup(client)

    # Create request
    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "question",
            "question": "Which approach?",
            "options": ["A", "B"],
        },
    )
    request_id = r.json()["id"]

    # Respond
    r = await client.post(
        f"/api/v1/human-requests/{request_id}/respond",
        json={"response": "Go with approach A"},
    )
    assert r.status_code == 200
    hr = r.json()
    assert hr["status"] == "resolved"
    assert hr["response"] == "Go with approach A"
    assert hr["resolved_at"] is not None


@pytest.mark.asyncio
async def test_respond_with_user_id(client):
    """Response records who responded."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "approval",
            "question": "Approve this?",
        },
    )
    request_id = r.json()["id"]

    user_id = str(uuid.uuid4())
    r = await client.post(
        f"/api/v1/human-requests/{request_id}/respond",
        json={"response": "Approved", "responded_by": user_id},
    )
    assert r.status_code == 200
    assert r.json()["responded_by"] == user_id


@pytest.mark.asyncio
async def test_respond_already_resolved(client):
    """Responding to an already-resolved request returns 409."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "question",
            "question": "Something?",
        },
    )
    request_id = r.json()["id"]

    # First response
    await client.post(
        f"/api/v1/human-requests/{request_id}/respond",
        json={"response": "First answer"},
    )

    # Second response — should fail
    r = await client.post(
        f"/api/v1/human-requests/{request_id}/respond",
        json={"response": "Second answer"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_respond_not_found(client):
    """Responding to nonexistent request returns 404."""
    r = await client.post(
        "/api/v1/human-requests/99999/respond",
        json={"response": "nope"},
    )
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════
# Get Request
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_request(client):
    """Get a specific request by ID."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "question",
            "question": "Fetchable question",
        },
    )
    request_id = r.json()["id"]

    r = await client.get(f"/api/v1/human-requests/{request_id}")
    assert r.status_code == 200
    assert r.json()["id"] == request_id
    assert r.json()["question"] == "Fetchable question"


@pytest.mark.asyncio
async def test_get_request_not_found(client):
    """Getting nonexistent request returns 404."""
    r = await client.get("/api/v1/human-requests/99999")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════
# List Requests
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_requests(client):
    """List all requests for a team."""
    ids = await _setup(client)

    # Create 2 requests
    for q in ["Question 1", "Question 2"]:
        await client.post(
            "/api/v1/human-requests",
            json={
                "team_id": ids["team_id"],
                "agent_id": ids["engineer_id"],
                "kind": "question",
                "question": q,
            },
        )

    r = await client.get(f"/api/v1/teams/{ids['team_id']}/human-requests")
    assert r.status_code == 200
    requests = r.json()
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_list_requests_filter_status(client):
    """Filter requests by status."""
    ids = await _setup(client)

    # Create 2 requests, resolve 1
    r1 = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "question",
            "question": "Resolved one",
        },
    )
    await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "question",
            "question": "Pending one",
        },
    )
    await client.post(
        f"/api/v1/human-requests/{r1.json()['id']}/respond",
        json={"response": "Done"},
    )

    # Filter pending only
    r = await client.get(
        f"/api/v1/teams/{ids['team_id']}/human-requests",
        params={"status": "pending"},
    )
    assert r.status_code == 200
    pending = r.json()
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"

    # Filter resolved only
    r = await client.get(
        f"/api/v1/teams/{ids['team_id']}/human-requests",
        params={"status": "resolved"},
    )
    assert r.status_code == 200
    resolved = r.json()
    assert len(resolved) == 1
    assert resolved[0]["status"] == "resolved"


@pytest.mark.asyncio
async def test_list_requests_filter_agent(client):
    """Filter requests by agent."""
    ids = await _setup(client)

    # Engineer request
    await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "question",
            "question": "Engineer question",
        },
    )
    # Manager request
    await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["manager_id"],
            "kind": "question",
            "question": "Manager question",
        },
    )

    r = await client.get(
        f"/api/v1/teams/{ids['team_id']}/human-requests",
        params={"agent_id": ids["engineer_id"]},
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["question"] == "Engineer question"


@pytest.mark.asyncio
async def test_full_lifecycle(client):
    """Full lifecycle: create → respond → verify resolved."""
    ids = await _setup(client)

    # Agent asks
    r = await client.post(
        "/api/v1/human-requests",
        json={
            "team_id": ids["team_id"],
            "agent_id": ids["engineer_id"],
            "kind": "approval",
            "question": "Should I refactor the auth module?",
            "options": ["approve", "reject", "defer"],
        },
    )
    assert r.status_code == 201
    request_id = r.json()["id"]

    # Verify it's pending
    r = await client.get(
        f"/api/v1/teams/{ids['team_id']}/human-requests",
        params={"status": "pending"},
    )
    assert len(r.json()) == 1

    # Human responds
    r = await client.post(
        f"/api/v1/human-requests/{request_id}/respond",
        json={"response": "approve"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"

    # Verify no more pending
    r = await client.get(
        f"/api/v1/teams/{ids['team_id']}/human-requests",
        params={"status": "pending"},
    )
    assert len(r.json()) == 0

    # Verify resolved
    r = await client.get(
        f"/api/v1/teams/{ids['team_id']}/human-requests",
        params={"status": "resolved"},
    )
    assert len(r.json()) == 1
    assert r.json()[0]["response"] == "approve"
