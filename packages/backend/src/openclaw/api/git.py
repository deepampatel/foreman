"""Git API routes — worktree management, diffs, file access, push, PRs.

Learn: These routes let agents (via MCP) and humans (via dashboard)
interact with git. Every task gets its own branch and worktree.
Push and PR routes use GitService and PRService respectively.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.engine import get_db
from openclaw.events.store import EventStore
from openclaw.services.git_service import GitService
from openclaw.services.pr_service import PRService

router = APIRouter()


def _git_svc(db: AsyncSession = Depends(get_db)) -> GitService:
    return GitService(db)


def _pr_svc(db: AsyncSession = Depends(get_db)) -> PRService:
    return PRService(db, events=EventStore(db))


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


# ─── Push + PR ───────────────────────────────────────────


@router.post("/tasks/{task_id}/push")
async def push_branch(
    task_id: int,
    repo_id: uuid.UUID = Query(..., description="Repository UUID"),
    remote: str = Query("origin", description="Remote name"),
    force: bool = Query(False, description="Force push (with lease)"),
    svc: GitService = Depends(_git_svc),
):
    """Push a task's branch to the remote."""
    try:
        result = await svc.push_branch(task_id, repo_id, remote=remote, force=force)
        if result.ok:
            return {"pushed": True, "branch": result.stdout or "ok"}
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Push failed: {result.stderr}",
            )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class PRCreateRequest(BaseModel):
    """Request body for creating a PR."""
    repo_id: str
    title: Optional[str] = None
    body: Optional[str] = None
    draft: bool = False
    base_branch: Optional[str] = None


@router.post("/tasks/{task_id}/pr")
async def create_pr(
    task_id: int,
    req: PRCreateRequest,
    svc: PRService = Depends(_pr_svc),
):
    """Create a GitHub PR for a task's branch via the gh CLI."""
    result = await svc.create_pr(
        task_id,
        uuid.UUID(req.repo_id),
        title=req.title,
        body=req.body,
        draft=req.draft,
        base_branch=req.base_branch,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/tasks/{task_id}/pr")
async def get_pr_info(
    task_id: int,
    svc: PRService = Depends(_pr_svc),
):
    """Get PR info for a task (from task metadata)."""
    info = await svc.get_pr_info(task_id)
    if not info:
        raise HTTPException(status_code=404, detail="No PR found for this task")
    return info
