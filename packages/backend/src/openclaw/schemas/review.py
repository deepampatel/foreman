"""Pydantic schemas for code reviews and merge jobs.

Learn: Reviews track the approval workflow:
1. request_review → creates Review (verdict=null)
2. Reviewer comments + renders verdict (approve/request_changes/reject)
3. On approve → task moves to 'in_approval' / 'merging'
4. MergeJob tracks the async merge process
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Review comments ─────────────────────────────────────


class ReviewCommentCreate(BaseModel):
    """Create a comment on a review."""
    author_id: str = Field(..., description="Author UUID (user or agent)")
    author_type: str = Field("user", description="Author type: user or agent")
    file_path: Optional[str] = Field(None, description="File path the comment refers to")
    line_number: Optional[int] = Field(None, description="Line number in the file")
    content: str = Field(..., description="Comment text")


class ReviewCommentRead(BaseModel):
    """A review comment."""
    id: int
    review_id: int
    author_id: uuid.UUID
    author_type: str
    file_path: Optional[str]
    line_number: Optional[int]
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Reviews ─────────────────────────────────────────────


class ReviewCreate(BaseModel):
    """Request a review for a task."""
    reviewer_id: Optional[str] = Field(None, description="Reviewer UUID (user or agent)")
    reviewer_type: str = Field("user", description="Reviewer type: user or agent")


class ReviewVerdictRequest(BaseModel):
    """Submit a verdict on a review."""
    verdict: str = Field(..., description="Verdict: approve, request_changes, reject")
    summary: Optional[str] = Field(None, description="Review summary")
    reviewer_id: Optional[str] = Field(None, description="Reviewer UUID")
    reviewer_type: str = Field("user", description="Reviewer type")


class ReviewRead(BaseModel):
    """A code review with its comments."""
    id: int
    task_id: int
    attempt: int
    reviewer_id: Optional[uuid.UUID]
    reviewer_type: str
    verdict: Optional[str]
    summary: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]
    comments: list[ReviewCommentRead] = []

    model_config = {"from_attributes": True}


# ─── Merge jobs ──────────────────────────────────────────


class MergeJobRead(BaseModel):
    """Status of a merge job."""
    id: int
    task_id: int
    repo_id: uuid.UUID
    status: str
    strategy: str
    error: Optional[str]
    merge_commit: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class MergeStatusRead(BaseModel):
    """Aggregate merge status for a task."""
    task_id: int
    review_verdict: Optional[str]
    review_attempt: int
    merge_jobs: list[MergeJobRead]
    can_merge: bool
