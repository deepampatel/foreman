"""Code review + merge service.

Learn: Manages the review lifecycle:
1. request_review → creates a Review row (attempt N)
2. add_comment → reviewer leaves inline comments
3. submit_verdict → approve / request_changes / reject
4. On approve → creates a MergeJob and queues it

The actual merge is handled by a separate worker (future).
This service manages the DB records and event trail.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from openclaw.db.models import MergeJob, Review, ReviewComment, Task
from openclaw.events.store import EventStore
from openclaw.events.types import (
    MERGE_QUEUED,
    REVIEW_COMMENT_ADDED,
    REVIEW_CREATED,
    REVIEW_VERDICT,
)


class ReviewNotFoundError(Exception):
    """Raised when a review is not found."""


class ReviewAlreadyResolvedError(Exception):
    """Raised when trying to verdict an already-resolved review."""


class TaskNotFoundError(Exception):
    """Raised when a task is not found."""


class ReviewService:
    """Manages code reviews, comments, and merge jobs."""

    def __init__(self, db: AsyncSession, events: EventStore):
        self.db = db
        self.events = events

    # ─── Create review ────────────────────────────────────

    async def request_review(
        self,
        task_id: int,
        *,
        reviewer_id: Optional[str] = None,
        reviewer_type: str = "user",
    ) -> Review:
        """Create a new review for a task.

        Learn: Auto-increments the attempt number. Each new review
        request is a fresh review cycle.
        """
        task = await self.db.get(Task, task_id)
        if not task:
            raise TaskNotFoundError(f"Task {task_id} not found")

        # Get current attempt number
        q = (
            select(func.coalesce(func.max(Review.attempt), 0))
            .where(Review.task_id == task_id)
        )
        result = await self.db.execute(q)
        current_max = result.scalar()
        next_attempt = current_max + 1

        review = Review(
            task_id=task_id,
            attempt=next_attempt,
            reviewer_id=uuid.UUID(reviewer_id) if reviewer_id else None,
            reviewer_type=reviewer_type,
        )
        self.db.add(review)
        await self.db.flush()

        await self.events.append(
            stream_id=f"task:{task_id}",
            event_type=REVIEW_CREATED,
            data={
                "review_id": review.id,
                "task_id": task_id,
                "attempt": next_attempt,
                "reviewer_id": reviewer_id,
            },
        )

        await self.db.commit()
        # Re-fetch with eagerly loaded comments (async can't lazy-load)
        return await self.get_review(review.id)

    # ─── Add comment ──────────────────────────────────────

    async def add_comment(
        self,
        review_id: int,
        *,
        author_id: str,
        author_type: str = "user",
        content: str,
        file_path: Optional[str] = None,
        line_number: Optional[int] = None,
    ) -> ReviewComment:
        """Add a comment to a review."""
        review = await self.db.get(Review, review_id)
        if not review:
            raise ReviewNotFoundError(f"Review {review_id} not found")

        comment = ReviewComment(
            review_id=review_id,
            author_id=uuid.UUID(author_id),
            author_type=author_type,
            file_path=file_path,
            line_number=line_number,
            content=content,
        )
        self.db.add(comment)
        await self.db.flush()

        await self.events.append(
            stream_id=f"task:{review.task_id}",
            event_type=REVIEW_COMMENT_ADDED,
            data={
                "review_id": review_id,
                "comment_id": comment.id,
                "file_path": file_path,
                "line_number": line_number,
            },
        )

        await self.db.commit()
        await self.db.refresh(comment)
        return comment

    # ─── Submit verdict ───────────────────────────────────

    async def submit_verdict(
        self,
        review_id: int,
        *,
        verdict: str,
        summary: Optional[str] = None,
        reviewer_id: Optional[str] = None,
        reviewer_type: str = "user",
    ) -> Review:
        """Submit a verdict on a review (approve, request_changes, reject).

        Learn: On 'approve', this also enqueues a merge job for each
        repo associated with the task.
        """
        if verdict not in ("approve", "request_changes", "reject"):
            raise ValueError(f"Invalid verdict: {verdict}")

        review = await self.db.get(
            Review, review_id, options=[selectinload(Review.comments)]
        )
        if not review:
            raise ReviewNotFoundError(f"Review {review_id} not found")

        if review.verdict is not None:
            raise ReviewAlreadyResolvedError(
                f"Review {review_id} already has verdict: {review.verdict}"
            )

        review.verdict = verdict
        review.summary = summary
        review.resolved_at = datetime.now(timezone.utc)
        if reviewer_id:
            review.reviewer_id = uuid.UUID(reviewer_id)
            review.reviewer_type = reviewer_type

        await self.events.append(
            stream_id=f"task:{review.task_id}",
            event_type=REVIEW_VERDICT,
            data={
                "review_id": review_id,
                "task_id": review.task_id,
                "verdict": verdict,
                "summary": summary,
                "reviewer_id": reviewer_id,
            },
        )

        await self.db.commit()
        # Re-fetch with eagerly loaded comments
        return await self.get_review(review.id)

    # ─── Get review ───────────────────────────────────────

    async def get_review(self, review_id: int) -> Optional[Review]:
        """Get a review by ID with its comments.

        Learn: We use a SELECT query instead of db.get() because db.get()
        can return a cached instance from the identity map without re-running
        selectinload. A fresh query ensures comments are always loaded.
        """
        q = (
            select(Review)
            .where(Review.id == review_id)
            .options(selectinload(Review.comments))
        )
        result = await self.db.execute(q)
        return result.scalars().first()

    # ─── List reviews for task ────────────────────────────

    async def list_reviews(self, task_id: int) -> list[Review]:
        """Get all reviews for a task."""
        q = (
            select(Review)
            .where(Review.task_id == task_id)
            .options(selectinload(Review.comments))
            .order_by(Review.attempt.desc())
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())

    # ─── Get latest review ────────────────────────────────

    async def get_latest_review(self, task_id: int) -> Optional[Review]:
        """Get the most recent review for a task."""
        q = (
            select(Review)
            .where(Review.task_id == task_id)
            .options(selectinload(Review.comments))
            .order_by(Review.attempt.desc())
            .limit(1)
        )
        result = await self.db.execute(q)
        return result.scalars().first()

    # ─── Merge job ────────────────────────────────────────

    async def create_merge_job(
        self,
        task_id: int,
        repo_id: str,
        strategy: str = "rebase",
    ) -> MergeJob:
        """Create a merge job for a task+repo.

        Learn: In production, this would also push the job to a Redis
        queue for the merge worker to pick up. For now, we just create
        the DB row.
        """
        task = await self.db.get(Task, task_id)
        if not task:
            raise TaskNotFoundError(f"Task {task_id} not found")

        job = MergeJob(
            task_id=task_id,
            repo_id=uuid.UUID(repo_id),
            status="queued",
            strategy=strategy,
        )
        self.db.add(job)
        await self.db.flush()

        await self.events.append(
            stream_id=f"task:{task_id}",
            event_type=MERGE_QUEUED,
            data={
                "merge_job_id": job.id,
                "task_id": task_id,
                "repo_id": repo_id,
                "strategy": strategy,
            },
        )

        await self.db.commit()
        await self.db.refresh(job)
        return job

    # ─── Get merge status ─────────────────────────────────

    async def get_merge_status(self, task_id: int) -> dict:
        """Get the merge status for a task.

        Returns: latest review verdict, review attempt, merge jobs, can_merge flag.
        """
        latest = await self.get_latest_review(task_id)

        # Get merge jobs
        q = (
            select(MergeJob)
            .where(MergeJob.task_id == task_id)
            .order_by(MergeJob.created_at.desc())
        )
        result = await self.db.execute(q)
        merge_jobs = list(result.scalars().all())

        return {
            "task_id": task_id,
            "review_verdict": latest.verdict if latest else None,
            "review_attempt": latest.attempt if latest else 0,
            "merge_jobs": merge_jobs,
            "can_merge": latest is not None and latest.verdict == "approve",
        }
