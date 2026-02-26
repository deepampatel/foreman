"""Git API routes — worktree management, diffs, file access.

Learn: These routes let agents (via MCP) and humans (via dashboard)
interact with git. Every task gets its own branch and worktree.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.engine import get_db
from openclaw.services.git_service import GitService

router = APIRouter()


def _git_svc(db: AsyncSession = Depends(get_db)) -> GitService:
    return GitService(db)


# ─── Worktrees ───────────────────────────────────────────

@router.post("/tasks/{task_id}/worktree")
async def create_worktree(
    task_id: int,
    repo_id: uuid.UUID = Query(..., description="Repository UUID"),
    svc: GitService = Depends(_git_svc),
):
    """Create a git worktree for a task. Idempotent — returns existing if already created."""
    try:
        info = await svc.create_worktree(task_id, repo_id)
        return {
            "path": info.path,
            "branch": info.branch,
            "exists": info.exists,
            "repo_path": info.repo_path,
            "repo_name": info.repo_name,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}/worktree")
async def remove_worktree(
    task_id: int,
    repo_id: uuid.UUID = Query(..., description="Repository UUID"),
    svc: GitService = Depends(_git_svc),
):
    """Remove a task's worktree."""
    try:
        removed = await svc.remove_worktree(task_id, repo_id)
        return {"removed": removed}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tasks/{task_id}/worktree")
async def get_worktree_info(
    task_id: int,
    repo_id: uuid.UUID = Query(..., description="Repository UUID"),
    svc: GitService = Depends(_git_svc),
):
    """Get info about a task's worktree."""
    try:
        info = await svc.get_worktree_info(task_id, repo_id)
        return {
            "path": info.path,
            "branch": info.branch,
            "exists": info.exists,
            "repo_path": info.repo_path,
            "repo_name": info.repo_name,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Diffs + Files ───────────────────────────────────────

@router.get("/tasks/{task_id}/diff")
async def get_task_diff(
    task_id: int,
    repo_id: uuid.UUID = Query(..., description="Repository UUID"),
    svc: GitService = Depends(_git_svc),
):
    """Get the full diff of a task's branch vs the default branch."""
    try:
        diff = await svc.get_diff(task_id, repo_id)
        return {"diff": diff}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tasks/{task_id}/files")
async def get_changed_files(
    task_id: int,
    repo_id: uuid.UUID = Query(..., description="Repository UUID"),
    svc: GitService = Depends(_git_svc),
):
    """List files changed on a task's branch."""
    try:
        files = await svc.get_changed_files(task_id, repo_id)
        return [
            {
                "path": f.path,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
            }
            for f in files
        ]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tasks/{task_id}/file")
async def get_file_content(
    task_id: int,
    repo_id: uuid.UUID = Query(..., description="Repository UUID"),
    path: str = Query(..., description="File path relative to repo root"),
    svc: GitService = Depends(_git_svc),
):
    """Read a file from the task's branch."""
    try:
        content = await svc.get_file_content(task_id, repo_id, path)
        return {"path": path, "content": content}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tasks/{task_id}/commits")
async def get_commit_log(
    task_id: int,
    repo_id: uuid.UUID = Query(..., description="Repository UUID"),
    limit: int = Query(20, ge=1, le=100),
    svc: GitService = Depends(_git_svc),
):
    """Get commit log for a task's branch."""
    try:
        return await svc.get_commit_log(task_id, repo_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
