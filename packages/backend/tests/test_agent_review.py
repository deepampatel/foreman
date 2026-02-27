"""Tier 1: Agent-to-agent code review tests.

Learn: Tests cover:
1. Reviewer agent prompt is built correctly
2. Auto-assign reviews to reviewer agents
3. Reviewer agent dispatch on review creation
4. Agent approve keeps task in_review for human
5. Agent request_changes triggers feedback loop
6. Two-tier review flow (agent → human)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from openclaw.agent.adapters.claude_code import ClaudeCodeAdapter


# ─── Helper: create org + team + engineer + reviewer + task ──


async def _setup(client, with_reviewer=True, slug_suffix=""):
    """Create org → team → agents → task, return IDs."""
    slug = f"agent-review-{uuid.uuid4().hex[:8]}{slug_suffix}"

    r = await client.post("/api/v1/orgs", json={"name": "Review Org", "slug": slug})
    assert r.status_code in (200, 201)
    org = r.json()

    r = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Review Team", "slug": f"team-{slug}"},
    )
    assert r.status_code in (200, 201)
    team = r.json()

    # Create engineer agent
    r = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": f"eng-{slug}", "role": "engineer"},
    )
    engineer = r.json()

    # Create reviewer agent (optional)
    reviewer = None
    if with_reviewer:
        r = await client.post(
            f"/api/v1/teams/{team['id']}/agents",
            json={"name": f"reviewer-{slug}", "role": "reviewer"},
        )
        reviewer = r.json()

    # Create task assigned to engineer
    r = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": f"Agent review task {slug}"},
    )
    task = r.json()

    # Assign to engineer
    await client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": engineer["id"]},
    )

    # Register a repo
    r = await client.post(
        f"/api/v1/teams/{team['id']}/repos",
        json={"name": f"repo-{slug}", "local_path": f"/tmp/repo-{slug}"},
    )
    repo = r.json()

    result = {
        "org_id": org["id"],
        "team_id": team["id"],
        "engineer_id": engineer["id"],
        "task_id": task["id"],
        "repo_id": repo["id"],
    }
    if reviewer:
        result["reviewer_id"] = reviewer["id"]
    return result


# ═══════════════════════════════════════════════════════════
# Reviewer Prompt
# ═══════════════════════════════════════════════════════════


def test_reviewer_prompt_built_correctly():
    """ClaudeCodeAdapter builds a reviewer prompt when role='reviewer'."""
    adapter = ClaudeCodeAdapter()
    prompt = adapter.build_prompt(
        task_title="Fix login bug",
        task_description="The login page has a bug",
        agent_id="agent-123",
        team_id="team-456",
        task_id=42,
        role="reviewer",
    )

    assert "REVIEWER agent" in prompt
    assert "REVIEW WORKFLOW" in prompt
    assert "get_task_diff" in prompt
    assert "add_review_comment" in prompt
    assert "submit_review_verdict" in prompt
    assert "agent-123" in prompt
    assert "42" in prompt


def test_engineer_prompt_has_save_context():
    """Engineer prompt includes the save_context instruction."""
    adapter = ClaudeCodeAdapter()
    prompt = adapter.build_prompt(
        task_title="Fix login bug",
        task_description="The login page has a bug",
        agent_id="agent-123",
        team_id="team-456",
        task_id=42,
        role="engineer",
    )

    assert "SAVE CONTEXT" in prompt
    assert "save_context" in prompt
    assert "PR will be auto-created" in prompt


def test_reviewer_prompt_includes_conventions():
    """Reviewer prompt includes team conventions when provided."""
    adapter = ClaudeCodeAdapter()
    conventions = [
        {"key": "testing", "content": "Always write tests with pytest"},
        {"key": "style", "content": "Follow PEP 8"},
    ]
    prompt = adapter.build_prompt(
        task_title="Fix bug",
        task_description="Description",
        agent_id="agent-1",
        team_id="team-1",
        task_id=1,
        role="reviewer",
        conventions=conventions,
    )

    assert "TEAM CONVENTIONS" in prompt
    assert "Always write tests with pytest" in prompt
    assert "Follow PEP 8" in prompt


def test_reviewer_prompt_includes_context():
    """Reviewer prompt includes context carryover."""
    adapter = ClaudeCodeAdapter()
    context = {
        "root_cause": "Regex in password.py",
        "key_files": "auth/password.py, auth/login.py",
    }
    prompt = adapter.build_prompt(
        task_title="Fix bug",
        task_description="Description",
        agent_id="agent-1",
        team_id="team-1",
        task_id=1,
        role="reviewer",
        context=context,
    )

    assert "PREVIOUS CONTEXT" in prompt
    assert "Regex in password.py" in prompt


def test_manager_prompt_includes_context():
    """Manager prompt includes context carryover."""
    adapter = ClaudeCodeAdapter()
    context = {"plan": "Break into 3 sub-tasks"}
    prompt = adapter.build_prompt(
        task_title="Feature",
        task_description="Description",
        agent_id="agent-1",
        team_id="team-1",
        task_id=1,
        role="manager",
        context=context,
    )

    assert "PREVIOUS CONTEXT" in prompt
    assert "Break into 3 sub-tasks" in prompt


def test_build_prompt_routes_to_reviewer():
    """build_prompt with role='reviewer' returns reviewer-specific prompt."""
    adapter = ClaudeCodeAdapter()

    eng_prompt = adapter.build_prompt(
        task_title="T", task_description="D",
        agent_id="a", team_id="t", task_id=1,
        role="engineer",
    )
    rev_prompt = adapter.build_prompt(
        task_title="T", task_description="D",
        agent_id="a", team_id="t", task_id=1,
        role="reviewer",
    )

    assert "REVIEWER agent" in rev_prompt
    assert "REVIEWER agent" not in eng_prompt
    assert "engineer agent" in eng_prompt.lower()


# ═══════════════════════════════════════════════════════════
# Auto-assign reviewer agent
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_auto_assign_reviewer_agent(client):
    """Request review without reviewer_id auto-assigns to idle reviewer agent."""
    ids = await _setup(client, with_reviewer=True)

    with patch(
        "openclaw.services.review_service.ReviewService._auto_push_and_create_pr",
        new_callable=AsyncMock,
    ), patch(
        "openclaw.services.review_service.ReviewService._dispatch_reviewer_agent",
        new_callable=AsyncMock,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/reviews",
            json={"reviewer_type": "user"},  # No reviewer_id
        )
        assert r.status_code == 201
        review = r.json()

        # Should be auto-assigned to the reviewer agent
        assert review["reviewer_id"] == ids["reviewer_id"]
        assert review["reviewer_type"] == "agent"


@pytest.mark.asyncio
async def test_no_auto_assign_without_reviewer(client):
    """Request review when no reviewer agents exist keeps reviewer as null."""
    ids = await _setup(client, with_reviewer=False)

    with patch(
        "openclaw.services.review_service.ReviewService._auto_push_and_create_pr",
        new_callable=AsyncMock,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/reviews",
            json={"reviewer_type": "user"},
        )
        assert r.status_code == 201
        review = r.json()

        # No reviewer agent available — reviewer stays null
        assert review["reviewer_id"] is None


# ═══════════════════════════════════════════════════════════
# Reviewer agent dispatch
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_reviewer_agent_dispatched_on_review(client):
    """When review is assigned to reviewer agent, a message is sent to trigger dispatch."""
    ids = await _setup(client, with_reviewer=True)

    with patch(
        "openclaw.services.review_service.ReviewService._auto_push_and_create_pr",
        new_callable=AsyncMock,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/reviews",
            json={"reviewer_type": "user"},
        )
        assert r.status_code == 201

    # Check that a message was sent to the reviewer agent
    r = await client.get(
        f"/api/v1/agents/{ids['reviewer_id']}/inbox",
        params={"unprocessed_only": "true"},
    )
    assert r.status_code == 200
    inbox = r.json()
    assert len(inbox) >= 1

    # Message should contain review request info
    msg = inbox[0]
    assert "Code Review Request" in msg["content"]
    assert str(ids["task_id"]) in msg["content"]


# ═══════════════════════════════════════════════════════════
# Agent approve keeps in_review
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_agent_approve_keeps_in_review(client):
    """Agent approve doesn't auto-transition task — stays in_review for human."""
    ids = await _setup(client, with_reviewer=True)

    # Create review with reviewer agent
    with patch(
        "openclaw.services.review_service.ReviewService._auto_push_and_create_pr",
        new_callable=AsyncMock,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/reviews",
            json={"reviewer_type": "user"},
        )
        assert r.status_code == 201
        review = r.json()

    # Agent submits approve verdict
    r = await client.post(
        f"/api/v1/reviews/{review['id']}/verdict",
        json={
            "verdict": "approve",
            "summary": "Code looks good",
            "reviewer_id": ids["reviewer_id"],
            "reviewer_type": "agent",
        },
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "approve"

    # Task should still be in its current state (not auto-transitioned)
    r = await client.get(f"/api/v1/tasks/{ids['task_id']}")
    task = r.json()
    # Task should NOT have moved to in_approval — it stays for human review
    assert task["status"] != "in_approval"


# ═══════════════════════════════════════════════════════════
# Agent request_changes triggers feedback loop
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_agent_request_changes_sends_feedback(client):
    """Agent request_changes sends feedback to engineer and transitions task back."""
    ids = await _setup(client, with_reviewer=True)

    # Move task to in_progress first
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/status",
        json={"status": "in_progress", "actor_id": ids["engineer_id"]},
    )

    # Move to in_review
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/status",
        json={"status": "in_review", "actor_id": ids["engineer_id"]},
    )

    # Create review
    with patch(
        "openclaw.services.review_service.ReviewService._auto_push_and_create_pr",
        new_callable=AsyncMock,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/reviews",
            json={"reviewer_type": "user"},
        )
        review = r.json()

    # Add a review comment
    r = await client.post(
        f"/api/v1/reviews/{review['id']}/comments",
        json={
            "author_id": ids["reviewer_id"],
            "author_type": "agent",
            "content": "Missing error handling in parse_email()",
            "file_path": "src/auth/password.py",
            "line_number": 42,
        },
    )
    assert r.status_code == 201

    # Agent submits request_changes
    r = await client.post(
        f"/api/v1/reviews/{review['id']}/verdict",
        json={
            "verdict": "request_changes",
            "summary": "Found 1 issue — see comments",
            "reviewer_id": ids["reviewer_id"],
            "reviewer_type": "agent",
        },
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "request_changes"

    # Task should be back to in_progress
    r = await client.get(f"/api/v1/tasks/{ids['task_id']}")
    task = r.json()
    assert task["status"] == "in_progress"

    # Engineer should have received feedback in inbox
    r = await client.get(
        f"/api/v1/agents/{ids['engineer_id']}/inbox",
        params={"unprocessed_only": "true"},
    )
    inbox = r.json()
    assert len(inbox) >= 1

    # Feedback message should contain the review comment
    feedback = inbox[0]
    assert "Review Feedback" in feedback["content"]
    assert "Missing error handling" in feedback["content"]


# ═══════════════════════════════════════════════════════════
# Two-tier review flow
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_two_tier_review_flow(client):
    """Full two-tier flow: agent reviews → agent approves → human reviews."""
    ids = await _setup(client, with_reviewer=True)

    # Move task through states
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/status",
        json={"status": "in_progress", "actor_id": ids["engineer_id"]},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/status",
        json={"status": "in_review", "actor_id": ids["engineer_id"]},
    )

    # Request review — auto-assigns to reviewer agent
    with patch(
        "openclaw.services.review_service.ReviewService._auto_push_and_create_pr",
        new_callable=AsyncMock,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/reviews",
            json={"reviewer_type": "user"},
        )
        review1 = r.json()
        assert review1["reviewer_type"] == "agent"

    # Agent approves
    r = await client.post(
        f"/api/v1/reviews/{review1['id']}/verdict",
        json={
            "verdict": "approve",
            "summary": "Looks good to me",
            "reviewer_id": ids["reviewer_id"],
            "reviewer_type": "agent",
        },
    )
    assert r.status_code == 200

    # Task is still in_review — waiting for human
    r = await client.get(f"/api/v1/tasks/{ids['task_id']}")
    assert r.json()["status"] == "in_review"

    # Human can now do a second review
    human_reviewer_id = str(uuid.uuid4())
    with patch(
        "openclaw.services.review_service.ReviewService._auto_push_and_create_pr",
        new_callable=AsyncMock,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/reviews",
            json={"reviewer_id": human_reviewer_id, "reviewer_type": "user"},
        )
        assert r.status_code == 201
        review2 = r.json()
        assert review2["attempt"] == 2

    # Human approves
    r = await client.post(
        f"/api/v1/reviews/{review2['id']}/verdict",
        json={
            "verdict": "approve",
            "summary": "Ship it!",
            "reviewer_id": human_reviewer_id,
            "reviewer_type": "user",
        },
    )
    assert r.status_code == 200
