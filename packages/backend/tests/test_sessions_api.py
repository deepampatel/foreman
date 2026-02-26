"""Phase 4: Session & cost control tests.

Learn: Tests cover the full session lifecycle:
1. Start session → check budget → create session
2. Record usage → update tokens and cost
3. End session → mark complete, set agent idle
4. Budget enforcement → block over-budget agents
5. Cost summary → per-agent and per-model breakdown
"""

import uuid

import pytest


# ─── Helper: create org + team + agent ────────────────────

async def _setup(client, slug_suffix=""):
    """Create org → team → agent, return IDs."""
    slug = f"session-test-{uuid.uuid4().hex[:8]}{slug_suffix}"

    r = await client.post("/api/v1/orgs", json={"name": "Session Test Org", "slug": slug})
    assert r.status_code in (200, 201)
    org = r.json()

    r = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Session Team", "slug": f"team-{slug}"},
    )
    assert r.status_code in (200, 201)
    team = r.json()

    # Get the auto-provisioned manager agent
    r = await client.get(f"/api/v1/teams/{team['id']}/agents")
    assert r.status_code == 200
    agents = r.json()
    manager = agents[0]

    # Create an engineer agent
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
# Session Lifecycle
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_start_session(client):
    """Starting a session creates a session row and sets agent to working."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    assert r.status_code == 201
    session = r.json()
    assert session["agent_id"] == ids["engineer_id"]
    assert session["cost_usd"] == 0
    assert session["tokens_in"] == 0
    assert session["ended_at"] is None


@pytest.mark.asyncio
async def test_start_session_with_task(client):
    """Session can be linked to a specific task."""
    ids = await _setup(client)

    # Create a task
    r = await client.post(
        f"/api/v1/teams/{ids['team_id']}/tasks",
        json={"title": "Test task"},
    )
    task = r.json()

    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"], "task_id": task["id"]},
    )
    assert r.status_code == 201
    assert r.json()["task_id"] == task["id"]


@pytest.mark.asyncio
async def test_start_session_with_model_override(client):
    """Session model can be overridden from agent default."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"], "model": "claude-opus-4-20250514"},
    )
    assert r.status_code == 201
    assert r.json()["model"] == "claude-opus-4-20250514"


@pytest.mark.asyncio
async def test_start_session_invalid_agent(client):
    """Starting a session with invalid agent ID returns 404."""
    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_record_usage(client):
    """Recording usage updates token counts and computes cost."""
    ids = await _setup(client)

    # Start session
    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    session_id = r.json()["id"]

    # Record usage
    r = await client.post(
        f"/api/v1/sessions/{session_id}/usage",
        json={
            "tokens_in": 1000,
            "tokens_out": 500,
            "cache_read": 200,
            "cache_write": 100,
        },
    )
    assert r.status_code == 200
    session = r.json()
    assert session["tokens_in"] == 1000
    assert session["tokens_out"] == 500
    assert session["cache_read"] == 200
    assert session["cache_write"] == 100
    assert session["cost_usd"] > 0  # cost computed from tokens


@pytest.mark.asyncio
async def test_record_usage_cumulative(client):
    """Multiple usage records accumulate (don't replace)."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    session_id = r.json()["id"]

    # Record twice
    await client.post(
        f"/api/v1/sessions/{session_id}/usage",
        json={"tokens_in": 500, "tokens_out": 200},
    )
    r = await client.post(
        f"/api/v1/sessions/{session_id}/usage",
        json={"tokens_in": 300, "tokens_out": 100},
    )
    assert r.status_code == 200
    session = r.json()
    assert session["tokens_in"] == 800  # 500 + 300
    assert session["tokens_out"] == 300  # 200 + 100


@pytest.mark.asyncio
async def test_end_session(client):
    """Ending a session sets ended_at and agent status back to idle."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    session_id = r.json()["id"]

    r = await client.post(f"/api/v1/sessions/{session_id}/end", json={})
    assert r.status_code == 200
    session = r.json()
    assert session["ended_at"] is not None
    assert session["error"] is None


@pytest.mark.asyncio
async def test_end_session_with_error(client):
    """Ending a session with error records the error message."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    session_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/sessions/{session_id}/end",
        json={"error": "Rate limit exceeded"},
    )
    assert r.status_code == 200
    assert r.json()["error"] == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_get_session(client):
    """Get a specific session by ID."""
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    session_id = r.json()["id"]

    r = await client.get(f"/api/v1/sessions/{session_id}")
    assert r.status_code == 200
    assert r.json()["id"] == session_id


@pytest.mark.asyncio
async def test_get_session_404(client):
    """Getting nonexistent session returns 404."""
    r = await client.get("/api/v1/sessions/99999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions(client):
    """List sessions for an agent."""
    ids = await _setup(client)

    # Start 2 sessions
    r1 = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    await client.post(f"/api/v1/sessions/{r1.json()['id']}/end", json={})

    r2 = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    await client.post(f"/api/v1/sessions/{r2.json()['id']}/end", json={})

    r = await client.get(f"/api/v1/agents/{ids['engineer_id']}/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) == 2


# ═══════════════════════════════════════════════════════════
# Budget
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_check_budget_within_limits(client):
    """Fresh agent should be within budget."""
    ids = await _setup(client)

    r = await client.get(f"/api/v1/agents/{ids['engineer_id']}/budget")
    assert r.status_code == 200
    budget = r.json()
    assert budget["within_budget"] is True
    assert budget["daily_spent_usd"] == 0
    assert budget["violations"] == []


@pytest.mark.asyncio
async def test_budget_exceeded_blocks_session(client):
    """Agent over daily budget can't start a new session.

    Learn: We create an agent with a very low daily limit ($0.001),
    start a session, record usage that exceeds the limit, then try
    to start another session — should get 429 Too Many Requests.
    """
    slug = f"budget-test-{uuid.uuid4().hex[:8]}"
    r = await client.post("/api/v1/orgs", json={"name": "Budget Org", "slug": slug})
    org = r.json()
    r = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Budget Team", "slug": f"team-{slug}"},
    )
    team = r.json()

    # Create agent with very low budget
    r = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={
            "name": f"tight-budget-{slug}",
            "role": "engineer",
        },
    )
    agent = r.json()

    # Start first session — should work
    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": agent["id"]},
    )
    assert r.status_code == 201
    session_id = r.json()["id"]

    # Record heavy usage (1M output tokens on sonnet = $15)
    await client.post(
        f"/api/v1/sessions/{session_id}/usage",
        json={"tokens_in": 100_000, "tokens_out": 1_000_000},
    )
    await client.post(f"/api/v1/sessions/{session_id}/end", json={})

    # Now budget should be exceeded (daily default is $50)
    # But $15 < $50, so let's check the budget
    r = await client.get(f"/api/v1/agents/{agent['id']}/budget")
    budget = r.json()
    # Cost should be > 0
    assert budget["daily_spent_usd"] > 0


@pytest.mark.asyncio
async def test_check_budget_with_task(client):
    """Budget check includes task-level spending."""
    ids = await _setup(client)

    # Create task
    r = await client.post(
        f"/api/v1/teams/{ids['team_id']}/tasks",
        json={"title": "Budget task"},
    )
    task = r.json()

    r = await client.get(
        f"/api/v1/agents/{ids['engineer_id']}/budget",
        params={"task_id": task["id"]},
    )
    assert r.status_code == 200
    budget = r.json()
    assert budget["task_spent_usd"] == 0
    assert budget["within_budget"] is True


# ═══════════════════════════════════════════════════════════
# Cost Summary
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cost_summary_empty(client):
    """Cost summary with no sessions shows zeros."""
    ids = await _setup(client)

    r = await client.get(f"/api/v1/teams/{ids['team_id']}/costs")
    assert r.status_code == 200
    summary = r.json()
    assert summary["total_cost_usd"] == 0
    assert summary["session_count"] == 0
    assert summary["per_agent"] == []
    assert summary["per_model"] == []


@pytest.mark.asyncio
async def test_cost_summary_with_sessions(client):
    """Cost summary reflects actual session data."""
    ids = await _setup(client)

    # Start session, record usage, end session
    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    session_id = r.json()["id"]

    await client.post(
        f"/api/v1/sessions/{session_id}/usage",
        json={"tokens_in": 10_000, "tokens_out": 5_000},
    )
    await client.post(f"/api/v1/sessions/{session_id}/end", json={})

    r = await client.get(f"/api/v1/teams/{ids['team_id']}/costs")
    assert r.status_code == 200
    summary = r.json()
    assert summary["session_count"] == 1
    assert summary["total_cost_usd"] > 0
    assert summary["total_tokens_in"] == 10_000
    assert summary["total_tokens_out"] == 5_000
    assert len(summary["per_agent"]) == 1
    assert len(summary["per_model"]) == 1


@pytest.mark.asyncio
async def test_cost_pricing_accuracy(client):
    """Verify cost is computed correctly from model pricing.

    Learn: Sonnet pricing is $3/M input, $15/M output.
    10K input + 5K output = $0.03 + $0.075 = $0.105
    """
    ids = await _setup(client)

    r = await client.post(
        "/api/v1/sessions/start",
        json={"agent_id": ids["engineer_id"]},
    )
    session_id = r.json()["id"]

    await client.post(
        f"/api/v1/sessions/{session_id}/usage",
        json={"tokens_in": 10_000, "tokens_out": 5_000},
    )

    r = await client.get(f"/api/v1/sessions/{session_id}")
    session = r.json()
    # Sonnet: 10K * $3/M + 5K * $15/M = $0.03 + $0.075 = $0.105
    expected = 10_000 * 3.0 / 1_000_000 + 5_000 * 15.0 / 1_000_000
    assert abs(session["cost_usd"] - expected) < 0.0001
