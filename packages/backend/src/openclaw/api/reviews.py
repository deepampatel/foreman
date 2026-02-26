"""Code review + merge API.

Learn: Routes for the review workflow:
- POST /tasks/:id/reviews → request a review
- POST /reviews/:id/comments → add a comment
- POST /tasks/:id/approve → approve (shorthand for verdict=approve)
- POST /tasks/:id/reject → reject (shorthand for verdict=reject)
- POST /reviews/:id/verdict → submit any verdict
- GET /tasks/:id/reviews → list reviews for a task
- GET /tasks/:id/merge-status → get merge readiness
- POST /tasks/:id/merge → queue a merge job
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.engine import get_db
from openclaw.events.store import EventStore
from openclaw.schemas.review import (
    MergeJobRead,
    MergeStatusRead,
    ReviewCommentCreate,
    ReviewCommentRead,
    ReviewCreate,
    ReviewRead,
    ReviewVerdictRequest,
)
from openclaw.services.review_service import (
    ReviewAlreadyResolvedError,
    ReviewNotFoundError,
    ReviewService,
    TaskNotFoundError,
)

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> ReviewService:
    return ReviewService(db=db, events=EventStore(db))


# ─── Request review ──────────────────────────────────────


@router.post("/tasks/{task_id}/reviews", response_model=ReviewRead, status_code=201)
async def request_review(
    task_id: int,
    body: ReviewCreate,
    svc: ReviewService = Depends(_get_service),
):
    """Request a code review for a task."""
    try:
        review = await svc.request_review(
            task_id,
            reviewer_id=body.reviewer_id,
            reviewer_type=body.reviewer_type,
        )
        return review
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")


# ─── Add comment ─────────────────────────────────────────


@router.post(
    "/reviews/{review_id}/comments",
    response_model=ReviewCommentRead,
    status_code=201,
)
async def add_review_comment(
    review_id: int,
    body: ReviewCommentCreate,
    svc: ReviewService = Depends(_get_service),
):
    """Add a comment to a review."""
    try:
        comment = await svc.add_comment(
            review_id,
            author_id=body.author_id,
            author_type=body.author_type,
            content=body.content,
            file_path=body.file_path,
            line_number=body.line_number,
        )
        return comment
    except ReviewNotFoundError:
        raise HTTPException(status_code=404, detail="Review not found")


# ─── Submit verdict ──────────────────────────────────────


@router.post("/reviews/{review_id}/verdict", response_model=ReviewRead)
async def submit_verdict(
    review_id: int,
    body: ReviewVerdictRequest,
    svc: ReviewService = Depends(_get_service),
):
    """Submit a verdict on a review (approve, request_changes, reject)."""
    try:
        review = await svc.submit_verdict(
            review_id,
            verdict=body.verdict,
            summary=body.summary,
            reviewer_id=body.reviewer_id,
            reviewer_type=body.reviewer_type,
        )
        return review
    except ReviewNotFoundError:
        raise HTTPException(status_code=404, detail="Review not found")
    except ReviewAlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ─── Approve / Reject shorthands ─────────────────────────


@router.post("/tasks/{task_id}/approve", response_model=ReviewRead)
async def approve_task(
    task_id: int,
    body: ReviewVerdictRequest = None,
    svc: ReviewService = Depends(_get_service),
):
    """Approve the latest review for a task (shorthand)."""
    review = await svc.get_latest_review(task_id)
    if not review:
        raise HTTPException(status_code=404, detail="No review found for this task")
    if review.verdict is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Review already has verdict: {review.verdict}",
        )
    try:
        summary = body.summary if body else None
        reviewer_id = body.reviewer_id if body else None
        reviewer_type = body.reviewer_type if body else "user"
        return await svc.submit_verdict(
            review.id,
            verdict="approve",
            summary=summary,
            reviewer_id=reviewer_id,
            reviewer_type=reviewer_type,
        )
    except ReviewAlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/tasks/{task_id}/reject", response_model=ReviewRead)
async def reject_task(
    task_id: int,
    body: ReviewVerdictRequest = None,
    svc: ReviewService = Depends(_get_service),
):
    """Reject the latest review for a task (shorthand)."""
    review = await svc.get_latest_review(task_id)
    if not review:
        raise HTTPException(status_code=404, detail="No review found for this task")
    if review.verdict is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Review already has verdict: {review.verdict}",
        )
    try:
        summary = body.summary if body else None
        reviewer_id = body.reviewer_id if body else None
        reviewer_type = body.reviewer_type if body else "user"
        return await svc.submit_verdict(
            review.id,
            verdict="reject",
            summary=summary,
            reviewer_id=reviewer_id,
            reviewer_type=reviewer_type,
        )
    except ReviewAlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ─── List reviews ────────────────────────────────────────


@router.get("/tasks/{task_id}/reviews", response_model=list[ReviewRead])
async def list_reviews(
    task_id: int,
    svc: ReviewService = Depends(_get_service),
):
    """List all reviews for a task (newest first)."""
    return await svc.list_reviews(task_id)


# ─── Get review ──────────────────────────────────────────


@router.get("/reviews/{review_id}", response_model=ReviewRead)
async def get_review(
    review_id: int,
    svc: ReviewService = Depends(_get_service),
):
    """Get a specific review by ID."""
    review = await svc.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


# ─── Merge status ────────────────────────────────────────


@router.get("/tasks/{task_id}/merge-status", response_model=MergeStatusRead)
async def get_merge_status(
    task_id: int,
    svc: ReviewService = Depends(_get_service),
):
    """Get the merge readiness status for a task."""
    return await svc.get_merge_status(task_id)


# ─── Queue merge ─────────────────────────────────────────


@router.post("/tasks/{task_id}/merge", response_model=MergeJobRead, status_code=201)
async def queue_merge(
    task_id: int,
    repo_id: str = Query(..., description="Repository UUID"),
    strategy: str = Query("rebase", description="Merge strategy: rebase, merge, squash"),
    svc: ReviewService = Depends(_get_service),
):
    """Queue a merge job for a task. Requires approved review."""
    # Check review status
    status = await svc.get_merge_status(task_id)
    if not status["can_merge"]:
        raise HTTPException(
            status_code=409,
            detail="Cannot merge — task not approved",
        )

    try:
        job = await svc.create_merge_job(task_id, repo_id, strategy)
        return job
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
