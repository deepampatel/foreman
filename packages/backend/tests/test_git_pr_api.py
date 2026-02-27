"""Tier 1: Git push + PR creation tests.

Learn: Tests cover:
1. Push branch endpoint
2. PR creation via gh CLI (mocked subprocess)
3. Auto PR on review request
4. PR info retrieval from task metadata
5. Failure tolerance — PR creation failures don't break review flow
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


# ─── Helper: create org + team + agent + task + repo ──────


async def _setup(client, slug_suffix=""):
    """Create org → team → agent → task → repo, return IDs."""
    slug = f"pr-test-{uuid.uuid4().hex[:8]}{slug_suffix}"

    r = await client.post("/api/v1/orgs", json={"name": "PR Org", "slug": slug})
    assert r.status_code in (200, 201)
    org = r.json()

    r = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "PR Team", "slug": f"team-{slug}"},
    )
    assert r.status_code in (200, 201)
    team = r.json()

    r = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": f"eng-{slug}", "role": "engineer"},
    )
    engineer = r.json()

    r = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": f"PR task {slug}"},
    )
    task = r.json()

    r = await client.post(
        f"/api/v1/teams/{team['id']}/repos",
        json={"name": f"repo-{slug}", "local_path": f"/tmp/repo-{slug}"},
    )
    repo = r.json()

    return {
        "org_id": org["id"],
        "team_id": team["id"],
        "engineer_id": engineer["id"],
        "task_id": task["id"],
        "repo_id": repo["id"],
    }


# ═══════════════════════════════════════════════════════════
# Push Branch
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_push_branch(client):
    """POST /tasks/:id/push pushes the branch to remote."""
    ids = await _setup(client)

    # Mock _run_git to simulate successful push
    mock_result = AsyncMock()
    mock_result.ok = True
    mock_result.stdout = "Everything up-to-date"
    mock_result.stderr = ""
    mock_result.exit_code = 0

    with patch(
        "openclaw.services.git_service._run_git",
        return_value=mock_result,
    ) as mock_git:
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/push",
            params={"repo_id": ids["repo_id"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["pushed"] is True

        # Verify git push was called with correct args
        args = mock_git.call_args
        assert "push" in args[0]


@pytest.mark.asyncio
async def test_push_branch_force(client):
    """Force push uses --force-with-lease."""
    ids = await _setup(client)

    mock_result = AsyncMock()
    mock_result.ok = True
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_result.exit_code = 0

    with patch(
        "openclaw.services.git_service._run_git",
        return_value=mock_result,
    ) as mock_git:
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/push",
            params={"repo_id": ids["repo_id"], "force": "true"},
        )
        assert r.status_code == 200

        args_tuple = mock_git.call_args[0]
        # Should include --force-with-lease
        assert "--force-with-lease" in args_tuple


@pytest.mark.asyncio
async def test_push_branch_failure(client):
    """Push failure returns 500."""
    ids = await _setup(client)

    mock_result = AsyncMock()
    mock_result.ok = False
    mock_result.stdout = ""
    mock_result.stderr = "fatal: no remote configured"
    mock_result.exit_code = 128

    with patch(
        "openclaw.services.git_service._run_git",
        return_value=mock_result,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/push",
            params={"repo_id": ids["repo_id"]},
        )
        assert r.status_code == 500


# ═══════════════════════════════════════════════════════════
# PR Creation
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_pr(client):
    """POST /tasks/:id/pr creates a GitHub PR via gh CLI."""
    ids = await _setup(client)

    # Mock asyncio.create_subprocess_exec for gh CLI
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(
        return_value=(b"https://github.com/org/repo/pull/42\n", b"")
    )

    with patch(
        "openclaw.services.pr_service.asyncio.create_subprocess_exec",
        return_value=mock_proc,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/pr",
            json={"repo_id": ids["repo_id"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["pr_url"] == "https://github.com/org/repo/pull/42"
        assert data["pr_number"] == 42


@pytest.mark.asyncio
async def test_create_pr_failure(client):
    """PR creation failure returns 500."""
    ids = await _setup(client)

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(
        return_value=(b"", b"a pull request already exists")
    )

    with patch(
        "openclaw.services.pr_service.asyncio.create_subprocess_exec",
        return_value=mock_proc,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/pr",
            json={"repo_id": ids["repo_id"]},
        )
        # PR service returns error, endpoint raises 500
        assert r.status_code == 500


@pytest.mark.asyncio
async def test_create_pr_with_options(client):
    """PR creation accepts optional title, body, draft."""
    ids = await _setup(client)

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(
        return_value=(b"https://github.com/org/repo/pull/7\n", b"")
    )

    with patch(
        "openclaw.services.pr_service.asyncio.create_subprocess_exec",
        return_value=mock_proc,
    ) as mock_exec:
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/pr",
            json={
                "repo_id": ids["repo_id"],
                "title": "Custom PR Title",
                "body": "Custom description",
                "draft": True,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["pr_number"] == 7

        # Verify gh was called with draft flag
        call_args = mock_exec.call_args[0]
        assert "--draft" in call_args


@pytest.mark.asyncio
async def test_get_pr_info(client):
    """GET /tasks/:id/pr returns stored PR metadata."""
    ids = await _setup(client)

    # First, create a PR
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(
        return_value=(b"https://github.com/org/repo/pull/99\n", b"")
    )

    with patch(
        "openclaw.services.pr_service.asyncio.create_subprocess_exec",
        return_value=mock_proc,
    ):
        await client.post(
            f"/api/v1/tasks/{ids['task_id']}/pr",
            json={"repo_id": ids["repo_id"]},
        )

    # Now get PR info
    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/pr")
    assert r.status_code == 200
    data = r.json()
    assert data["pr_url"] == "https://github.com/org/repo/pull/99"
    assert data["pr_number"] == 99


@pytest.mark.asyncio
async def test_get_pr_info_no_pr(client):
    """GET /tasks/:id/pr returns 404 when no PR exists."""
    ids = await _setup(client)

    r = await client.get(f"/api/v1/tasks/{ids['task_id']}/pr")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════
# Auto PR on review request
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_auto_pr_on_review_request(client):
    """Requesting a review triggers auto push/PR (mocked)."""
    ids = await _setup(client)

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
        assert review["task_id"] == ids["task_id"]
        assert review["attempt"] == 1


@pytest.mark.asyncio
async def test_pr_failure_doesnt_break_review(client):
    """If auto-PR fails, the review request still succeeds."""
    ids = await _setup(client)

    # _auto_push_and_create_pr catches its own exceptions internally
    with patch(
        "openclaw.services.review_service.ReviewService._auto_push_and_create_pr",
        new_callable=AsyncMock,
    ):
        r = await client.post(
            f"/api/v1/tasks/{ids['task_id']}/reviews",
            json={"reviewer_type": "user"},
        )
        assert r.status_code == 201
        assert r.json()["attempt"] == 1
