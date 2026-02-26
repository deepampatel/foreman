"""Phase 6: Multi-agent dispatch tests.

Learn: Tests cover:
1. PG LISTEN/NOTIFY triggers fire on message insert
2. Dispatch status API (pending messages, idle agents)
3. Task status change triggers
4. Human request resolution triggers
"""

import uuid

import pytest
from sqlalchemy import text


# ─── Helper: create org + team + agents ────────────────────


async def _setup(client, slug_suffix=""):
    """Create org → team → 2 agents, return IDs."""
    slug = f"dispatch-{uuid.uuid4().hex[:8]}{slug_suffix}"

    r = await client.post("/api/v1/orgs", json={"name": "Dispatch Org", "slug": slug})
    assert r.status_code in (200, 201)
    org = r.json()

    r = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Dispatch Team", "slug": f"team-{slug}"},
    )
    assert r.status_code in (200, 201)
    team = r.json()

    r = await client.get(f"/api/v1/teams/{team['id']}/agents")
    manager = r.json()[0]

    r = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": f"eng-{slug}", "role": "engineer"},
    )
    engineer = r.json()

    return {
        "org_id": org["id"],
        "team_id": team["id"],
        "manager_id": manager["id"],
        "engineer_id": engineer["id"],
    }


# ═══════════════════════════════════════════════════════════
# Dispatch Status API
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dispatch_status_empty(client):
    """Dispatch status with no messages shows zeros."""
    ids = await _setup(client)

    r = await client.get(f"/api/v1/teams/{ids['team_id']}/dispatch-status")
    assert r.status_code == 200
    status = r.json()
    assert status["total_pending"] == 0
    assert status["total_idle"] >= 1  # At least manager + engineer


@pytest.mark.asyncio
async def test_dispatch_status_with_messages(client):
    """Dispatch status shows pending messages per agent."""
    ids = await _setup(client)

    # Send a message to the engineer
    await client.post(
        f"/api/v1/teams/{ids['team_id']}/messages",
        json={
            "sender_id": ids["manager_id"],
            "sender_type": "agent",
            "recipient_id": ids["engineer_id"],
            "recipient_type": "agent",
            "content": "Work on the task please",
        },
    )

    r = await client.get(f"/api/v1/teams/{ids['team_id']}/dispatch-status")
    assert r.status_code == 200
    status = r.json()
    assert status["total_pending"] == 1
    assert len(status["pending_messages"]) == 1
    assert status["pending_messages"][0]["agent_id"] == ids["engineer_id"]
    assert status["pending_messages"][0]["pending_messages"] == 1


@pytest.mark.asyncio
async def test_dispatch_status_multiple_agents(client):
    """Dispatch status tracks messages for multiple agents."""
    ids = await _setup(client)

    # Send message to engineer
    await client.post(
        f"/api/v1/teams/{ids['team_id']}/messages",
        json={
            "sender_id": ids["manager_id"],
            "sender_type": "agent",
            "recipient_id": ids["engineer_id"],
            "recipient_type": "agent",
            "content": "Engineer task",
        },
    )

    # Send message to manager
    await client.post(
        f"/api/v1/teams/{ids['team_id']}/messages",
        json={
            "sender_id": ids["engineer_id"],
            "sender_type": "agent",
            "recipient_id": ids["manager_id"],
            "recipient_type": "agent",
            "content": "Done with the task",
        },
    )

    r = await client.get(f"/api/v1/teams/{ids['team_id']}/dispatch-status")
    status = r.json()
    assert status["total_pending"] == 2
    assert len(status["pending_messages"]) == 2


@pytest.mark.asyncio
async def test_dispatch_status_idle_agents(client):
    """Dispatch status shows idle agents."""
    ids = await _setup(client)

    r = await client.get(f"/api/v1/teams/{ids['team_id']}/dispatch-status")
    status = r.json()
    # Both manager and engineer should be idle
    assert status["total_idle"] == 2
    agent_ids = {a["id"] for a in status["idle_agents"]}
    assert ids["manager_id"] in agent_ids
    assert ids["engineer_id"] in agent_ids


# ═══════════════════════════════════════════════════════════
# PG Trigger Verification
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_message_trigger_exists(raw_db):
    """Verify the message insert trigger is installed."""
    result = await raw_db.execute(
        text("""
            SELECT tgname FROM pg_trigger
            WHERE tgrelid = 'messages'::regclass
            AND tgname = 'message_insert_notify'
        """)
    )
    triggers = result.fetchall()
    assert len(triggers) == 1
    assert triggers[0][0] == "message_insert_notify"


@pytest.mark.asyncio
async def test_human_request_trigger_exists(raw_db):
    """Verify the human request resolution trigger is installed."""
    result = await raw_db.execute(
        text("""
            SELECT tgname FROM pg_trigger
            WHERE tgrelid = 'human_requests'::regclass
            AND tgname = 'human_request_status_notify'
        """)
    )
    triggers = result.fetchall()
    assert len(triggers) == 1


@pytest.mark.asyncio
async def test_task_status_trigger_exists(raw_db):
    """Verify the task status change trigger is installed."""
    result = await raw_db.execute(
        text("""
            SELECT tgname FROM pg_trigger
            WHERE tgrelid = 'tasks'::regclass
            AND tgname = 'task_status_change_notify'
        """)
    )
    triggers = result.fetchall()
    assert len(triggers) == 1


@pytest.mark.asyncio
async def test_notify_functions_exist(raw_db):
    """Verify all NOTIFY functions are installed."""
    for func_name in [
        "notify_new_message",
        "notify_human_request_resolved",
        "notify_task_status_changed",
    ]:
        result = await raw_db.execute(
            text("""
                SELECT proname FROM pg_proc
                WHERE proname = :name
            """),
            {"name": func_name},
        )
        rows = result.fetchall()
        assert len(rows) == 1, f"Function {func_name} not found"
