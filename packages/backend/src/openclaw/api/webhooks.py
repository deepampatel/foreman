"""Webhooks API — configuration and incoming webhook receiver.

Learn: Two main responsibilities:
1. CRUD for webhook configurations (admin side)
2. POST receiver for incoming webhook payloads from GitHub/etc.

The receiver endpoint verifies HMAC signatures, logs the delivery,
and processes the event (creating/updating tasks as needed).
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.engine import get_db
from openclaw.services.webhook_service import (
    WebhookNotFoundError,
    WebhookService,
    WebhookSignatureError,
)

router = APIRouter(prefix="/webhooks")


# ─── Schemas ─────────────────────────────────────────────


class WebhookCreate(BaseModel):
    org_id: str
    name: str
    team_id: Optional[str] = None
    provider: str = "github"
    events: list[str] = Field(default_factory=lambda: ["push", "pull_request"])
    config: dict = Field(default_factory=dict)


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    events: Optional[list[str]] = None
    active: Optional[bool] = None
    config: Optional[dict] = None


class WebhookRead(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    team_id: Optional[uuid.UUID] = None
    name: str
    provider: str
    secret: str
    events: list[str]
    active: bool
    config: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryRead(BaseModel):
    id: int
    webhook_id: uuid.UUID
    event_type: str
    payload: Optional[dict] = None
    status: str
    error: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Webhook CRUD ────────────────────────────────────────


@router.post("", response_model=WebhookRead, status_code=201)
async def create_webhook(
    body: WebhookCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new webhook configuration."""
    svc = WebhookService(db)
    webhook = await svc.create_webhook(
        org_id=body.org_id,
        name=body.name,
        team_id=body.team_id,
        provider=body.provider,
        events=body.events,
        config=body.config,
    )
    return webhook


@router.get("/orgs/{org_id}", response_model=list[WebhookRead])
async def list_webhooks(
    org_id: str,
    team_id: Optional[str] = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List webhooks for an org."""
    svc = WebhookService(db)
    return await svc.list_webhooks(
        org_id, team_id=team_id, active_only=active_only
    )


@router.get("/{webhook_id}", response_model=WebhookRead)
async def get_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get webhook details."""
    svc = WebhookService(db)
    webhook = await svc.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@router.patch("/{webhook_id}", response_model=WebhookRead)
async def update_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update webhook configuration."""
    svc = WebhookService(db)
    try:
        return await svc.update_webhook(
            webhook_id,
            name=body.name,
            events=body.events,
            active=body.active,
            config=body.config,
        )
    except WebhookNotFoundError:
        raise HTTPException(status_code=404, detail="Webhook not found")


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a webhook."""
    svc = WebhookService(db)
    try:
        await svc.delete_webhook(webhook_id)
        return {"deleted": True}
    except WebhookNotFoundError:
        raise HTTPException(status_code=404, detail="Webhook not found")


@router.post("/{webhook_id}/regenerate-secret", response_model=WebhookRead)
async def regenerate_secret(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Regenerate the webhook secret."""
    svc = WebhookService(db)
    try:
        return await svc.regenerate_secret(webhook_id)
    except WebhookNotFoundError:
        raise HTTPException(status_code=404, detail="Webhook not found")


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryRead])
async def list_deliveries(
    webhook_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List recent deliveries for a webhook."""
    svc = WebhookService(db)
    return await svc.list_deliveries(webhook_id, limit=limit)


# ─── Incoming webhook receiver ────────────────────────────


@router.post("/{webhook_id}/receive")
async def receive_webhook(
    webhook_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive an incoming webhook payload from GitHub/etc.

    Verifies HMAC signature, logs the delivery, processes the event.
    """
    svc = WebhookService(db)
    webhook = await svc.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if not webhook.active:
        raise HTTPException(status_code=410, detail="Webhook is disabled")

    # Read raw body for signature verification
    body = await request.body()

    # Verify signature (GitHub sends X-Hub-Signature-256)
    signature = request.headers.get("X-Hub-Signature-256", "")
    if signature:
        if not svc.verify_signature(webhook.secret, body, signature):
            raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse event type (GitHub sends X-GitHub-Event)
    event_type = request.headers.get(
        "X-GitHub-Event",
        request.headers.get("X-Event-Type", "unknown"),
    )

    # Check if this event type is configured
    if webhook.events and event_type not in webhook.events:
        # Still log it but mark as ignored
        delivery = await svc.receive_delivery(
            str(webhook.id), event_type, {}
        )
        await svc.mark_delivery_failed(delivery.id, f"Event type '{event_type}' not configured")
        return {"status": "ignored", "reason": f"Event type '{event_type}' not configured"}

    # Process the event
    import json
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}

    try:
        result = await svc.process_github_event(webhook, event_type, payload)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing webhook: {str(e)}",
        )
