"""PR service — creates GitHub PRs via the gh CLI.

Learn: Instead of adding PyGithub or octokit as dependencies, we use
the `gh` CLI for PR operations. This keeps the dependency tree light
and works with whatever GitHub auth the user already has configured
(gh auth login, GITHUB_TOKEN env var, etc.).

The PR URL and number are stored in the task's metadata JSONB column
so they can be retrieved later by the dashboard, agents, or API.
"""

import asyncio
import shutil
import uuid
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from openclaw.db.models import Repository, Task
from openclaw.events.store import EventStore
from openclaw.events.types import PR_CREATED, PR_PUSH_COMPLETED, PR_PUSH_FAILED

logger = structlog.get_logger()


class PRService:
    """Creates and manages GitHub PRs via the gh CLI."""

    def __init__(self, db: AsyncSession, events: Optional[EventStore] = None):
        self.db = db
        self.events = events

    @staticmethod
    def gh_available() -> bool:
        """Check if the gh CLI is installed."""
        return shutil.which("gh") is not None

    async def create_pr(
        self,
        task_id: int,
        repo_id: uuid.UUID,
        *,
        title: Optional[str] = None,
        body: Optional[str] = None,
        draft: bool = False,
        base_branch: Optional[str] = None,
    ) -> dict:
        """Create a GitHub PR for a task's branch.

        Learn: Uses `gh pr create` which handles auth, repo detection,
        and formatting. Returns the PR URL on success. The PR URL is
        stored in task_metadata for later retrieval.

        Returns: {"pr_url": "...", "pr_number": N} on success
                 {"error": "..."} on failure
        """
        task = await self.db.get(Task, task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        repo = await self.db.get(Repository, repo_id)
        if not repo:
            return {"error": f"Repository {repo_id} not found"}

        if not self.gh_available():
            return {"error": "gh CLI not found — install from https://cli.github.com"}

        pr_title = title or task.title
        # Truncate description for PR body
        desc = task.description or ""
        pr_body = body or f"Entourage Task #{task.id}\n\n{desc[:1000]}"
        target = base_branch or repo.default_branch

        args = [
            "gh", "pr", "create",
            "--title", pr_title,
            "--body", pr_body,
            "--base", target,
            "--head", task.branch,
        ]
        if draft:
            args.append("--draft")

        log = logger.bind(task_id=task_id, branch=task.branch)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=repo.local_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=30.0
            )
        except asyncio.TimeoutError:
            log.warning("pr.create_timeout")
            return {"error": "gh pr create timed out after 30s"}
        except Exception as e:
            log.warning("pr.create_error", error=str(e))
            return {"error": str(e)}

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0 and stdout:
            pr_url = stdout
            # Extract PR number from URL (e.g. https://github.com/org/repo/pull/42)
            try:
                pr_number = int(pr_url.rstrip("/").split("/")[-1])
            except (ValueError, IndexError):
                pr_number = 0

            # Store PR URL in task metadata
            metadata = task.task_metadata or {}
            metadata["pr_url"] = pr_url
            metadata["pr_number"] = pr_number
            task.task_metadata = metadata
            flag_modified(task, "task_metadata")

            # Record event
            if self.events:
                await self.events.append(
                    stream_id=f"task:{task_id}",
                    event_type=PR_CREATED,
                    data={
                        "task_id": task_id,
                        "pr_url": pr_url,
                        "pr_number": pr_number,
                        "repo_id": str(repo_id),
                        "branch": task.branch,
                    },
                )

            await self.db.commit()
            log.info("pr.created", pr_url=pr_url, pr_number=pr_number)
            return {"pr_url": pr_url, "pr_number": pr_number}
        else:
            error = stderr or f"gh pr create failed (exit code {proc.returncode})"
            log.warning("pr.create_failed", error=error)
            return {"error": error}

    async def get_pr_info(self, task_id: int) -> Optional[dict]:
        """Get PR info from task metadata.

        Returns: {"pr_url": "...", "pr_number": N} or None
        """
        task = await self.db.get(Task, task_id)
        if not task:
            return None

        metadata = task.task_metadata or {}
        pr_url = metadata.get("pr_url")
        if not pr_url:
            return None

        return {
            "pr_url": pr_url,
            "pr_number": metadata.get("pr_number", 0),
        }
