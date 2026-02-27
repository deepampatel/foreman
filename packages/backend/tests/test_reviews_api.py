"""Phase 8: Code review + merge tests.

Learn: Tests cover the full review workflow:
1. Request review → creates review with attempt number
2. Add comments → inline code review comments
3. Submit verdict → approve / request_changes / reject
4. Approve/reject shorthands → convenience endpoints
5. Merge status → readiness check
6. Queue merge → only after approval
7. Multiple review attempts
"""

import uuid

import pytest


# ─── Helper: create org + team + agent + task ────────────


async def _setup(client, slug_suffix=""):
    """Create org → team → agent → task, return IDs."""
    slug = f"review-test-{uuid.uuid4().hex[:8]}{slug_suffix}"

    r = await client.post("/api/v1/orgs", json={"name": "Review Org", "slug": slug})
    assert r.status_code in (200, 201)
    org = r.json()

    r = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Review Team", "slug": f"team-{slug}"},
    )
    assert r.status_code in (200, 201)
    team = r.json()

    # Get auto-provisioned manager agent
    r = await client.get(f"/api/v1/teams/{team['id']}/agents")
    agents = r.json()
    manager = agents[0]

    # Create engineer
    r = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": f"eng-{slug}", "role": "engineer"},
    )
    engineer = r.json()

    # Create task
    r = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": f"Review task {slug}"},
    )
    task = r.json()

    # Register a repo (for merge jobs)
    r = await client.post(
        f"/api/v1/teams/{team['id']}/repos",
        json={"name": f"repo-{slug}", "local_path": f"/tmp/repo-{slug}"},
    )
    repo = r.json()

    return {
        "org_id": org["id"],
        "team_id": team["id"],
        "manager_id": manager["id"],
        "engineer_id": engineer["id"],
        "task_id": task["id"],
        "repo_id": repo["id"],
    }


# ═══════════════════════════════════════════════════════════
# Request Review
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_request_review(client):
    """Request a review creates a review with attempt 1."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    assert r.status_code == 201
    review = r.json()
    assert review["task_id"] == ids["task_id"]
    assert review["attempt"] == 1
    assert review["verdict"] is None
    assert review["comments"] == []


@pytest.mark.asyncio
async def test_request_review_with_reviewer(client):
    """Review can be assigned to a specific reviewer."""
    ids = await _setup(client)

    reviewer_id = str(uuid.uuid4())
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_id": reviewer_id, "reviewer_type": "user"},
    )
    assert r.status_code == 201
    assert r.json()["reviewer_id"] == reviewer_id


@pytest.mark.asyncio
async def test_request_review_increments_attempt(client):
    """Multiple review requests increment the attempt number."""
    ids = await _setup(client)

    r1 = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    assert r1.json()["attempt"] == 1

    r2 = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    assert r2.json()["attempt"] == 2


@pytest.mark.asyncio
async def test_request_review_task_not_found(client):
    """Review request for nonexistent task returns 404."""
    r = await client.post(
        "/api/v1/tasks/99999/reviews",
        json={"reviewer_type": "user"},
    )
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════
# Review Comments
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_add_review_comment(client):
    """Add an inline comment to a review."""
    ids = await _setup(client)

    # Create review
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    review_id = r.json()["id"]

    # Add comment
    r = await client.post(
        f"/api/v1/reviews/{review_id}/comments",
        json={
            "author_id": ids["manager_id"],
            "author_type": "agent",
            "file_path": "src/main.py",
            "line_number": 42,
            "content": "This function is too complex, consider splitting it.",
        },
    )
    assert r.status_code == 201
    comment = r.json()
    assert comment["file_path"] == "src/main.py"
    assert comment["line_number"] == 42
    assert comment["content"] == "This function is too complex, consider splitting it."


@pytest.mark.asyncio
async def test_add_general_comment(client):
    """Add a general comment (no file/line)."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    review_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/reviews/{review_id}/comments",
        json={
            "author_id": ids["manager_id"],
            "author_type": "agent",
            "content": "Overall looks good!",
        },
    )
    assert r.status_code == 201
    assert r.json()["file_path"] is None
    assert r.json()["line_number"] is None


@pytest.mark.asyncio
async def test_comments_appear_in_review(client):
    """Comments are included when fetching the review."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    review_id = r.json()["id"]

    # Add 2 comments
    for content in ["Comment 1", "Comment 2"]:
        await client.post(
            f"/api/v1/reviews/{review_id}/comments",
            json={
                "author_id": ids["manager_id"],
                "author_type": "agent",
                "content": content,
            },
        )

    # Fetch review
    r = await client.get(f"/api/v1/reviews/{review_id}")
    assert r.status_code == 200
    assert len(r.json()["comments"]) == 2


# ═══════════════════════════════════════════════════════════
# Verdicts
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_approve_verdict(client):
    """Submit approve verdict."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    review_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/reviews/{review_id}/verdict",
        json={"verdict": "approve", "summary": "Looks great!"},
    )
    assert r.status_code == 200
    review = r.json()
    assert review["verdict"] == "approve"
    assert review["summary"] == "Looks great!"
    assert review["resolved_at"] is not None


@pytest.mark.asyncio
async def test_reject_verdict(client):
    """Submit reject verdict."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    review_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/reviews/{review_id}/verdict",
        json={"verdict": "reject", "summary": "Needs more work."},
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "reject"


@pytest.mark.asyncio
async def test_request_changes_verdict(client):
    """Submit request_changes verdict."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    review_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/reviews/{review_id}/verdict",
        json={"verdict": "request_changes", "summary": "Fix the tests."},
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "request_changes"


@pytest.mark.asyncio
async def test_request_changes_sends_feedback_and_redispatches(client):
    """request_changes closes the feedback loop: transitions task to in_progress + sends message to agent.

    Learn: This is the core autonomy feature. When a reviewer gives request_changes:
    1. Task transitions from in_review → in_progress
    2. A message with formatted review comments is sent to the assignee agent
    3. The message triggers PG NOTIFY → dispatcher → agent re-runs with feedback
    """
    ids = await _setup(client)

    # Assign task to engineer and move to in_review
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/assign",
        json={"assignee_id": ids["engineer_id"]},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/status",
        json={"status": "in_progress"},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/status",
        json={"status": "in_review"},
    )

    # Create review + add comments
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_id": ids["manager_id"], "reviewer_type": "agent"},
    )
    review_id = r.json()["id"]

    await client.post(
        f"/api/v1/reviews/{review_id}/comments",
        json={
            "author_id": ids["manager_id"],
            "author_type": "agent",
            "file_path": "src/api.py",
            "line_number": 42,
            "content": "Missing error handling for 404 case",
        },
    )
    await client.post(
        f"/api/v1/reviews/{review_id}/comments",
        json={
            "author_id": ids["manager_id"],
            "author_type": "agent",
            "content": "Add unit tests for the new endpoint",
        },
    )

    # Submit request_changes verdict
    r = await client.post(
        f"/api/v1/reviews/{review_id}/verdict",
        json={
            "verdict": "request_changes",
            "summary": "Two things to fix: error handling and tests.",
            "reviewer_id": ids["manager_id"],
            "reviewer_type": "agent",
        },
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "request_changes"

    # ── Verify: task transitioned back to in_progress ──
    r = await client.get(f"/api/v1/tasks/{ids['task_id']}")
    assert r.json()["status"] == "in_progress"

    # ── Verify: message sent to the assignee agent with review feedback ──
    r = await client.get(f"/api/v1/agents/{ids['engineer_id']}/inbox")
    messages = r.json()
    assert len(messages) >= 1
    feedback_msg = messages[0]
    assert "Review Feedback" in feedback_msg["content"]
    assert "src/api.py:42" in feedback_msg["content"]
    assert "Missing error handling" in feedback_msg["content"]
    assert "Add unit tests" in feedback_msg["content"]
    assert "Two things to fix" in feedback_msg["content"]

    # ── Verify: event trail contains review.feedback_sent ──
    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/events")
    events = r.json()
    event_types = [e["type"] for e in events]
    assert "review.feedback_sent" in event_types


@pytest.mark.asyncio
async def test_double_verdict_blocked(client):
    """Can't submit verdict twice on same review."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    review_id = r.json()["id"]

    await client.post(
        f"/api/v1/reviews/{review_id}/verdict",
        json={"verdict": "approve"},
    )

    r = await client.post(
        f"/api/v1/reviews/{review_id}/verdict",
        json={"verdict": "reject"},
    )
    assert r.status_code == 409


# ═══════════════════════════════════════════════════════════
# Approve/Reject Shorthands
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_approve_task_shorthand(client):
    """Approve task via shorthand endpoint."""
    ids = await _setup(client)

    # Must have a review first
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/approve",
        json={"verdict": "approve", "summary": "Ship it!", "reviewer_type": "user"},
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "approve"


@pytest.mark.asyncio
async def test_reject_task_shorthand(client):
    """Reject task via shorthand endpoint."""
    ids = await _setup(client)

    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reject",
        json={"verdict": "reject", "summary": "Not ready.", "reviewer_type": "user"},
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "reject"


@pytest.mark.asyncio
async def test_approve_no_review(client):
    """Approve with no review returns 404."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/approve",
        json={"verdict": "approve", "reviewer_type": "user"},
    )
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════
# List Reviews
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_reviews(client):
    """List all reviews for a task."""
    ids = await _setup(client)

    # Create 2 reviews
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/reviews")
    assert r.status_code == 200
    reviews = r.json()
    assert len(reviews) == 2
    # Newest first
    assert reviews[0]["attempt"] == 2
    assert reviews[1]["attempt"] == 1


# ═══════════════════════════════════════════════════════════
# Merge Status
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_merge_status_no_review(client):
    """Merge status with no review shows can_merge=false."""
    ids = await _setup(client)

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/merge-status")
    assert r.status_code == 200
    status = r.json()
    assert status["can_merge"] is False
    assert status["review_verdict"] is None
    assert status["review_attempt"] == 0


@pytest.mark.asyncio
async def test_merge_status_approved(client):
    """Merge status after approval shows can_merge=true."""
    ids = await _setup(client)

    # Review + approve
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/approve",
        json={"verdict": "approve", "reviewer_type": "user"},
    )

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/merge-status")
    assert r.status_code == 200
    status = r.json()
    assert status["can_merge"] is True
    assert status["review_verdict"] == "approve"


@pytest.mark.asyncio
async def test_merge_status_rejected(client):
    """Merge status after rejection shows can_merge=false."""
    ids = await _setup(client)

    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reject",
        json={"verdict": "reject", "reviewer_type": "user"},
    )

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/merge-status")
    assert r.status_code == 200
    assert r.json()["can_merge"] is False


# ═══════════════════════════════════════════════════════════
# Queue Merge
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_queue_merge_after_approval(client):
    """Queue merge after task is approved."""
    ids = await _setup(client)

    # Review + approve
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/approve",
        json={"verdict": "approve", "reviewer_type": "user"},
    )

    # Queue merge
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/merge",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 201
    job = r.json()
    assert job["task_id"] == ids["task_id"]
    assert job["repo_id"] == ids["repo_id"]
    assert job["status"] == "queued"
    assert job["strategy"] == "rebase"


@pytest.mark.asyncio
async def test_queue_merge_without_approval(client):
    """Can't queue merge without approval."""
    ids = await _setup(client)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/merge",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_merge_job_appears_in_status(client):
    """Merge job appears in merge status."""
    ids = await _setup(client)

    # Review + approve + merge
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/approve",
        json={"verdict": "approve", "reviewer_type": "user"},
    )
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/merge",
        params={"repo_id": ids["repo_id"]},
    )

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/merge-status")
    status = r.json()
    assert len(status["merge_jobs"]) == 1
    assert status["merge_jobs"][0]["status"] == "queued"


# ═══════════════════════════════════════════════════════════
# Full Lifecycle
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_full_review_lifecycle(client):
    """Full lifecycle: request → comment → request_changes → new attempt → approve → merge."""
    ids = await _setup(client)

    # First review attempt
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    review1_id = r.json()["id"]

    # Add comment
    await client.post(
        f"/api/v1/reviews/{review1_id}/comments",
        json={
            "author_id": ids["manager_id"],
            "author_type": "agent",
            "content": "Fix the error handling",
            "file_path": "src/handler.py",
            "line_number": 15,
        },
    )

    # Request changes
    r = await client.post(
        f"/api/v1/reviews/{review1_id}/verdict",
        json={"verdict": "request_changes", "summary": "Needs error handling fixes"},
    )
    assert r.json()["verdict"] == "request_changes"

    # Second review attempt (after fixing)
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/reviews",
        json={"reviewer_type": "user"},
    )
    assert r.json()["attempt"] == 2

    # Approve second attempt
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/approve",
        json={"verdict": "approve", "summary": "LGTM!", "reviewer_type": "user"},
    )
    assert r.json()["verdict"] == "approve"

    # Queue merge
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/merge",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 201

    # Verify final state
    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/merge-status")
    status = r.json()
    assert status["can_merge"] is True
    assert status["review_attempt"] == 2
    assert len(status["merge_jobs"]) == 1
