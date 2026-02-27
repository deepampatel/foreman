"""Tier 1: Context carryover tests.

Learn: Tests cover:
1. Save context key-value pair to task metadata
2. Get context returns all saved pairs
3. Multiple context saves accumulate (don't overwrite)
4. Context injected into agent prompt
5. Context persists across simulated re-dispatch
6. Empty context returns empty dict
"""

import uuid

import pytest

from openclaw.agent.adapters.claude_code import ClaudeCodeAdapter


# ─── Helper: create org + team + task ─────────────────────


async def _setup(client, slug_suffix=""):
    """Create org → team → task, return IDs."""
    slug = f"ctx-test-{uuid.uuid4().hex[:8]}{slug_suffix}"

    r = await client.post("/api/v1/orgs", json={"name": "Ctx Org", "slug": slug})
    assert r.status_code in (200, 201)
    org = r.json()

    r = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Ctx Team", "slug": f"team-{slug}"},
    )
    assert r.status_code in (200, 201)
    team = r.json()

    r = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": f"Context task {slug}"},
    )
    task = r.json()

    return {
        "org_id": org["id"],
        "team_id": team["id"],
        "task_id": task["id"],
    }


# ═══════════════════════════════════════════════════════════
# Save Context
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_save_context(client):
    """POST /tasks/:id/context saves a key-value pair."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "root_cause", "value": "Regex in password.py doesn't handle + symbol"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["key"] == "root_cause"
    assert data["saved"] is True


@pytest.mark.asyncio
async def test_save_multiple_context_keys(client):
    """Multiple saves accumulate — don't overwrite each other."""
    ids = await _setup(client)

    # Save first key
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "root_cause", "value": "Regex bug"},
    )

    # Save second key
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "key_files", "value": "auth/password.py, auth/login.py"},
    )

    # Save third key
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "fix_approach", "value": "Use email-validator library"},
    )

    # Get all context
    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/context")
    assert r.status_code == 200
    data = r.json()
    ctx = data["context"]
    assert ctx["root_cause"] == "Regex bug"
    assert ctx["key_files"] == "auth/password.py, auth/login.py"
    assert ctx["fix_approach"] == "Use email-validator library"


@pytest.mark.asyncio
async def test_save_context_overwrites_same_key(client):
    """Saving the same key again overwrites the value."""
    ids = await _setup(client)

    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "status", "value": "investigating"},
    )

    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "status", "value": "fix implemented"},
    )

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/context")
    data = r.json()
    assert data["context"]["status"] == "fix implemented"


# ═══════════════════════════════════════════════════════════
# Get Context
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_context_empty(client):
    """GET /tasks/:id/context returns empty dict when no context saved."""
    ids = await _setup(client)

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/context")
    assert r.status_code == 200
    data = r.json()
    assert data["task_id"] == ids["task_id"]
    assert data["context"] == {}


@pytest.mark.asyncio
async def test_get_context_returns_all_saved(client):
    """GET /tasks/:id/context returns all previously saved pairs."""
    ids = await _setup(client)

    # Save some context
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "root_cause", "value": "Missing input validation"},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "architecture", "value": "Add middleware for validation"},
    )

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/context")
    assert r.status_code == 200
    data = r.json()
    assert len(data["context"]) == 2
    assert "root_cause" in data["context"]
    assert "architecture" in data["context"]


@pytest.mark.asyncio
async def test_get_context_404_for_missing_task(client):
    """GET /tasks/:id/context returns 404 for non-existent task."""
    r = await client.get("/api/v1/tasks/99999/context")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_save_context_404_for_missing_task(client):
    """POST /tasks/:id/context returns 404 for non-existent task."""
    r = await client.post(
        "/api/v1/tasks/99999/context",
        json={"key": "test", "value": "test"},
    )
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════
# Context in Prompt
# ═══════════════════════════════════════════════════════════


def test_context_injected_in_engineer_prompt():
    """Context carryover data appears in the engineer prompt."""
    adapter = ClaudeCodeAdapter()
    context = {
        "root_cause": "Regex in password.py doesn't handle + symbol",
        "key_files": "auth/password.py, auth/login.py",
    }
    prompt = adapter.build_prompt(
        task_title="Fix login bug",
        task_description="Login fails for emails with + symbol",
        agent_id="agent-1",
        team_id="team-1",
        task_id=42,
        role="engineer",
        context=context,
    )

    assert "PREVIOUS CONTEXT" in prompt
    assert "root_cause" in prompt
    assert "Regex in password.py" in prompt
    assert "key_files" in prompt
    assert "auth/password.py, auth/login.py" in prompt


def test_no_context_section_when_empty():
    """No PREVIOUS CONTEXT section when context is None or empty."""
    adapter = ClaudeCodeAdapter()

    prompt_none = adapter.build_prompt(
        task_title="T", task_description="D",
        agent_id="a", team_id="t", task_id=1,
        role="engineer",
        context=None,
    )
    prompt_empty = adapter.build_prompt(
        task_title="T", task_description="D",
        agent_id="a", team_id="t", task_id=1,
        role="engineer",
        context={},
    )

    assert "PREVIOUS CONTEXT" not in prompt_none
    assert "PREVIOUS CONTEXT" not in prompt_empty


def test_context_injected_in_reviewer_prompt():
    """Context carryover data appears in the reviewer prompt too."""
    adapter = ClaudeCodeAdapter()
    context = {"previous_review": "Tests need updating"}
    prompt = adapter.build_prompt(
        task_title="T", task_description="D",
        agent_id="a", team_id="t", task_id=1,
        role="reviewer",
        context=context,
    )

    assert "PREVIOUS CONTEXT" in prompt
    assert "Tests need updating" in prompt


# ═══════════════════════════════════════════════════════════
# Context persists across simulated re-dispatch
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_context_persists_across_runs(client):
    """Save context → read it back → still there (simulates re-dispatch)."""
    ids = await _setup(client)

    # Agent discovers root cause on run 1
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "root_cause", "value": "Missing input sanitization in auth flow"},
    )

    # Agent discovers key files
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "key_files", "value": "src/auth/password.py:42, src/auth/login.py:15"},
    )

    # Simulate re-dispatch — agent reads context on run 2
    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/context")
    data = r.json()
    ctx = data["context"]

    # All discoveries from run 1 should be available
    assert ctx["root_cause"] == "Missing input sanitization in auth flow"
    assert ctx["key_files"] == "src/auth/password.py:42, src/auth/login.py:15"

    # Agent can add more context on run 2
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "fix_verified", "value": "Tests passing after fix"},
    )

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/context")
    data = r.json()
    # All context from both runs should be present
    assert len(data["context"]) == 3


# ═══════════════════════════════════════════════════════════
# Context doesn't bleed between tasks
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_context_isolated_per_task(client):
    """Context saved on one task doesn't appear on another."""
    ids = await _setup(client)

    # Create a second task
    r = await client.post(
        f"/api/v1/teams/{ids['team_id']}/tasks",
        json={"title": "Another task"},
    )
    task2 = r.json()

    # Save context on task 1
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/context",
        json={"key": "secret", "value": "task1-only"},
    )

    # Task 2 should have no context
    r = await client.get(f"/api/v1/tasks/{task2['id']}/context")
    data = r.json()
    assert data["context"] == {}
