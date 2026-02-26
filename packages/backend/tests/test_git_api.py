"""Phase 3: Git integration tests — worktrees, diffs, file access, commits.

Learn: These tests create a real temporary git repo on disk with commits,
then test the full API flow: create worktree, make changes, get diff, etc.

The temp_repo fixture:
1. Creates a temp directory with `git init`
2. Creates an initial commit on main
3. Returns the path (cleaned up after the test)
"""

import os
import subprocess
import tempfile
import uuid

import pytest


# ─── Helper: run git commands synchronously (test setup only) ──────

def _git(cwd: str, *args: str) -> str:
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


# ─── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary git repo with an initial commit on main.

    Learn: We use a real git repo so we can test actual worktree
    creation, real diffs, and real file content reading.
    """
    repo_path = str(tmp_path / "test-repo")
    os.makedirs(repo_path)

    # Init repo with 'main' as default branch
    _git(repo_path, "init", "--initial-branch", "main")
    _git(repo_path, "config", "user.email", "test@test.com")
    _git(repo_path, "config", "user.name", "Test")

    # Create initial file and commit
    readme = os.path.join(repo_path, "README.md")
    with open(readme, "w") as f:
        f.write("# Test Repo\n\nInitial content.\n")

    _git(repo_path, "add", ".")
    _git(repo_path, "commit", "-m", "Initial commit")

    return repo_path


# ─── Helper: full setup (org → team → repo → task) ────────────────

async def _full_setup(client, temp_repo):
    """Create org, team, register repo, create task → returns IDs."""
    slug = f"git-test-{uuid.uuid4().hex[:8]}"

    # Create org
    r = await client.post("/api/v1/orgs", json={"name": "Git Test Org", "slug": slug})
    assert r.status_code in (200, 201), f"Org creation failed: {r.text}"
    org = r.json()

    # Create team
    r = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Git Team", "slug": f"git-team-{slug}"},
    )
    assert r.status_code in (200, 201), f"Team creation failed: {r.text}"
    team = r.json()

    # Register repo (points to our temp git repo on disk)
    r = await client.post(
        f"/api/v1/teams/{team['id']}/repos",
        json={
            "name": "test-repo",
            "local_path": temp_repo,
            "default_branch": "main",
        },
    )
    assert r.status_code in (200, 201), f"Repo creation failed: {r.text}"
    repo = r.json()

    # Create task (auto-generates branch name)
    r = await client.post(
        f"/api/v1/teams/{team['id']}/tasks",
        json={"title": "Fix login bug", "priority": "high"},
    )
    assert r.status_code in (200, 201), f"Task creation failed: {r.text}"
    task = r.json()
    assert task["branch"] != ""  # branch auto-generated

    return {
        "org_id": org["id"],
        "team_id": team["id"],
        "repo_id": repo["id"],
        "task_id": task["id"],
        "branch": task["branch"],
    }


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_worktree(client, temp_repo):
    """Create a worktree for a task — should create branch + directory."""
    ids = await _full_setup(client, temp_repo)

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    data = r.json()

    assert data["branch"] == ids["branch"]
    assert data["exists"] is True
    assert data["repo_name"] == "test-repo"
    assert os.path.isdir(data["path"])  # worktree dir actually exists on disk


@pytest.mark.asyncio
async def test_create_worktree_idempotent(client, temp_repo):
    """Creating the same worktree twice should return the existing one."""
    ids = await _full_setup(client, temp_repo)

    r1 = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    assert r1.status_code == 200

    r2 = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    assert r2.status_code == 200
    assert r2.json()["path"] == r1.json()["path"]


@pytest.mark.asyncio
async def test_get_worktree_info(client, temp_repo):
    """Get worktree info — exists=False before creation, True after."""
    ids = await _full_setup(client, temp_repo)

    # Before creation
    r = await client.get(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    assert r.json()["exists"] is False

    # Create it
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )

    # After creation
    r = await client.get(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    assert r.json()["exists"] is True


@pytest.mark.asyncio
async def test_remove_worktree(client, temp_repo):
    """Remove a worktree — should clean up directory."""
    ids = await _full_setup(client, temp_repo)

    # Create
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    wt_path = r.json()["path"]
    assert os.path.isdir(wt_path)

    # Remove
    r = await client.delete(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    assert r.json()["removed"] is True
    assert not os.path.isdir(wt_path)  # directory gone


@pytest.mark.asyncio
async def test_remove_nonexistent_worktree(client, temp_repo):
    """Removing a worktree that doesn't exist returns removed=False."""
    ids = await _full_setup(client, temp_repo)

    r = await client.delete(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    assert r.json()["removed"] is False


@pytest.mark.asyncio
async def test_get_diff_empty(client, temp_repo):
    """Diff with no changes should be empty."""
    ids = await _full_setup(client, temp_repo)

    # Create worktree (branch starts at same point as main)
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )

    r = await client.get(
        f"/api/v1/tasks/{ids['task_id']}/diff",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    assert r.json()["diff"] == ""


@pytest.mark.asyncio
async def test_get_diff_with_changes(client, temp_repo):
    """Diff after making changes on the task branch should show the changes."""
    ids = await _full_setup(client, temp_repo)

    # Create worktree
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    wt_path = r.json()["path"]

    # Make changes in the worktree
    new_file = os.path.join(wt_path, "fix.py")
    with open(new_file, "w") as f:
        f.write("def fix_login():\n    pass\n")

    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "Fix login bug")

    # Now get diff
    r = await client.get(
        f"/api/v1/tasks/{ids['task_id']}/diff",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    diff = r.json()["diff"]
    assert "fix.py" in diff
    assert "fix_login" in diff


@pytest.mark.asyncio
async def test_get_changed_files(client, temp_repo):
    """Changed files should list added/modified/deleted files with stats."""
    ids = await _full_setup(client, temp_repo)

    # Create worktree
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    wt_path = r.json()["path"]

    # Add a new file
    with open(os.path.join(wt_path, "new_feature.py"), "w") as f:
        f.write("print('hello')\n")

    # Modify README
    with open(os.path.join(wt_path, "README.md"), "w") as f:
        f.write("# Updated\n\nNew content.\n")

    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "Add feature and update readme")

    r = await client.get(
        f"/api/v1/tasks/{ids['task_id']}/files",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    files = r.json()
    assert len(files) == 2

    paths = {f["path"] for f in files}
    assert "new_feature.py" in paths
    assert "README.md" in paths

    # Check stats
    for f in files:
        if f["path"] == "new_feature.py":
            assert f["status"] == "A"  # Added
            assert f["additions"] == 1
        elif f["path"] == "README.md":
            assert f["status"] == "M"  # Modified


@pytest.mark.asyncio
async def test_read_file_from_branch(client, temp_repo):
    """Read a file from the task's branch via git show."""
    ids = await _full_setup(client, temp_repo)

    # Create worktree + commit a file
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    wt_path = r.json()["path"]

    with open(os.path.join(wt_path, "config.json"), "w") as f:
        f.write('{"debug": true}\n')

    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "Add config")

    # Read the file via API
    r = await client.get(
        f"/api/v1/tasks/{ids['task_id']}/file",
        params={"repo_id": ids["repo_id"], "path": "config.json"},
    )
    assert r.status_code == 200
    assert r.json()["path"] == "config.json"
    assert '"debug": true' in r.json()["content"]


@pytest.mark.asyncio
async def test_read_file_not_found(client, temp_repo):
    """Reading a nonexistent file should return 404."""
    ids = await _full_setup(client, temp_repo)

    # Create worktree (no extra commits)
    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )

    r = await client.get(
        f"/api/v1/tasks/{ids['task_id']}/file",
        params={"repo_id": ids["repo_id"], "path": "nonexistent.txt"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_commits(client, temp_repo):
    """Commit log should show commits on the task branch."""
    ids = await _full_setup(client, temp_repo)

    # Create worktree + make 2 commits
    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )
    wt_path = r.json()["path"]

    with open(os.path.join(wt_path, "a.txt"), "w") as f:
        f.write("first\n")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "First change")

    with open(os.path.join(wt_path, "b.txt"), "w") as f:
        f.write("second\n")
    _git(wt_path, "add", ".")
    _git(wt_path, "commit", "-m", "Second change")

    r = await client.get(
        f"/api/v1/tasks/{ids['task_id']}/commits",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    commits = r.json()
    assert len(commits) == 2
    assert commits[0]["message"] == "Second change"  # most recent first
    assert commits[1]["message"] == "First change"
    assert commits[0]["author_name"] == "Test"


@pytest.mark.asyncio
async def test_get_commits_empty(client, temp_repo):
    """Commit log with no changes should be empty."""
    ids = await _full_setup(client, temp_repo)

    await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": ids["repo_id"]},
    )

    r = await client.get(
        f"/api/v1/tasks/{ids['task_id']}/commits",
        params={"repo_id": ids["repo_id"]},
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_worktree_invalid_task(client, temp_repo):
    """Worktree operations with invalid task ID should return 404."""
    r = await client.post(
        "/api/v1/tasks/99999/worktree",
        params={"repo_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_worktree_invalid_repo(client, temp_repo):
    """Worktree operations with invalid repo ID should return 404."""
    ids = await _full_setup(client, temp_repo)
    fake_repo = str(uuid.uuid4())

    r = await client.post(
        f"/api/v1/tasks/{ids['task_id']}/worktree",
        params={"repo_id": fake_repo},
    )
    assert r.status_code == 404
