"""Webhook management + incoming payload processing.

Learn: WebhookService handles two responsibilities:
1. CRUD for webhook configurations (create, list, update, delete)
2. Processing incoming webhook payloads from GitHub/GitLab/etc.

When a webhook payload arrives:
1. Verify HMAC signature (GitHub uses SHA-256)
2. Log the delivery in webhook_deliveries
3. Process the event (e.g., create/update tasks based on GitHub events)
4. Update delivery status
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.models import Webhook, WebhookDelivery
from openclaw.events.store import EventStore
from openclaw.events.types import (
    WEBHOOK_CREATED,
    WEBHOOK_DELETED,
    WEBHOOK_DELIVERY_FAILED,
    WEBHOOK_DELIVERY_PROCESSED,
    WEBHOOK_DELIVERY_RECEIVED,
    WEBHOOK_UPDATED,
)


class WebhookNotFoundError(Exception):
    pass


class WebhookSignatureError(Exception):
    pass


class WebhookService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.events = EventStore(db)

    # ─── CRUD ──────────────────────────────────────────────

    async def create_webhook(
        self,
        org_id: str,
        name: str,
        *,
        team_id: Optional[str] = None,
        provider: str = "github",
        events: Optional[list[str]] = None,
        config: Optional[dict] = None,
    ) -> Webhook:
        """Create a new webhook configuration. Auto-generates a secret."""
        secret = secrets.token_urlsafe(32)

        webhook = Webhook(
            org_id=uuid.UUID(org_id),
            team_id=uuid.UUID(team_id) if team_id else None,
            name=name,
            provider=provider,
            secret=secret,
            events=events or ["push", "pull_request"],
            active=True,
            config=config or {},
        )
        self.db.add(webhook)
        await self.db.commit()
        await self.db.refresh(webhook)

        await self.events.append(
            stream_id=f"webhook:{webhook.id}",
            event_type=WEBHOOK_CREATED,
            data={
                "webhook_id": str(webhook.id),
                "org_id": org_id,
                "team_id": team_id,
                "name": name,
                "provider": provider,
            },
        )

        return webhook

    async def get_webhook(self, webhook_id: str) -> Optional[Webhook]:
        return await self.db.get(Webhook, uuid.UUID(webhook_id))

    async def list_webhooks(
        self,
        org_id: str,
        *,
        team_id: Optional[str] = None,
        active_only: bool = False,
    ) -> list[Webhook]:
        q = select(Webhook).where(Webhook.org_id == uuid.UUID(org_id))
        if team_id:
            q = q.where(Webhook.team_id == uuid.UUID(team_id))
        if active_only:
            q = q.where(Webhook.active.is_(True))
        q = q.order_by(Webhook.created_at.desc())
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def update_webhook(
        self,
        webhook_id: str,
        *,
        name: Optional[str] = None,
        events: Optional[list[str]] = None,
        active: Optional[bool] = None,
        config: Optional[dict] = None,
    ) -> Webhook:
        webhook = await self.db.get(Webhook, uuid.UUID(webhook_id))
        if not webhook:
            raise WebhookNotFoundError(f"Webhook {webhook_id} not found")

        changes = {}
        if name is not None:
            webhook.name = name
            changes["name"] = name
        if events is not None:
            webhook.events = events
            changes["events"] = events
        if active is not None:
            webhook.active = active
            changes["active"] = active
        if config is not None:
            webhook.config = config
            changes["config"] = config

        await self.db.commit()
        await self.db.refresh(webhook)

        if changes:
            await self.events.append(
                stream_id=f"webhook:{webhook_id}",
                event_type=WEBHOOK_UPDATED,
                data={"webhook_id": webhook_id, "changes": changes},
            )

        return webhook

    async def delete_webhook(self, webhook_id: str) -> bool:
        webhook = await self.db.get(Webhook, uuid.UUID(webhook_id))
        if not webhook:
            raise WebhookNotFoundError(f"Webhook {webhook_id} not found")

        # Delete deliveries first (FK constraint)
        from sqlalchemy import delete as sa_delete
        await self.db.execute(
            sa_delete(WebhookDelivery).where(
                WebhookDelivery.webhook_id == uuid.UUID(webhook_id)
            )
        )
        await self.db.delete(webhook)
        await self.db.commit()

        await self.events.append(
            stream_id=f"webhook:{webhook_id}",
            event_type=WEBHOOK_DELETED,
            data={"webhook_id": webhook_id},
        )

        return True

    async def regenerate_secret(self, webhook_id: str) -> Webhook:
        """Regenerate the webhook secret."""
        webhook = await self.db.get(Webhook, uuid.UUID(webhook_id))
        if not webhook:
            raise WebhookNotFoundError(f"Webhook {webhook_id} not found")

        webhook.secret = secrets.token_urlsafe(32)
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    # ─── Incoming webhook processing ───────────────────────

    def verify_signature(
        self, secret: str, payload: bytes, signature: str
    ) -> bool:
        """Verify GitHub HMAC-SHA256 signature."""
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        # GitHub sends "sha256=<hex>"
        if signature.startswith("sha256="):
            signature = signature[7:]
        return hmac.compare_digest(expected, signature)

    async def receive_delivery(
        self,
        webhook_id: str,
        event_type: str,
        payload: dict,
    ) -> WebhookDelivery:
        """Log an incoming webhook delivery."""
        delivery = WebhookDelivery(
            webhook_id=uuid.UUID(webhook_id),
            event_type=event_type,
            payload=payload,
            status="received",
        )
        self.db.add(delivery)
        await self.db.commit()
        await self.db.refresh(delivery)

        await self.events.append(
            stream_id=f"webhook:{webhook_id}",
            event_type=WEBHOOK_DELIVERY_RECEIVED,
            data={
                "delivery_id": delivery.id,
                "webhook_id": webhook_id,
                "event_type": event_type,
            },
        )

        return delivery

    async def mark_delivery_processed(self, delivery_id: int) -> None:
        await self.db.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .values(status="processed")
        )
        await self.db.commit()

    async def mark_delivery_failed(
        self, delivery_id: int, error: str
    ) -> None:
        await self.db.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .values(status="failed", error=error)
        )
        await self.db.commit()

    async def list_deliveries(
        self,
        webhook_id: str,
        *,
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        q = (
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == uuid.UUID(webhook_id))
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def process_github_event(
        self,
        webhook: Webhook,
        event_type: str,
        payload: dict,
    ) -> dict:
        """Process a GitHub webhook event and return summary of actions taken.

        Currently handles:
        - push: logs the push event
        - pull_request: logs PR actions
        - issues: logs issue actions
        """
        delivery = await self.receive_delivery(
            str(webhook.id), event_type, payload
        )

        actions = []

        try:
            if event_type == "push":
                ref = payload.get("ref", "")
                commits = payload.get("commits", [])
                actions.append(f"push to {ref}: {len(commits)} commit(s)")

            elif event_type == "pull_request":
                action = payload.get("action", "unknown")
                pr = payload.get("pull_request", {})
                title = pr.get("title", "untitled")
                actions.append(f"PR {action}: {title}")

            elif event_type == "issues":
                action = payload.get("action", "unknown")
                issue = payload.get("issue", {})
                title = issue.get("title", "untitled")
                actions.append(f"issue {action}: {title}")

            else:
                actions.append(f"received {event_type} event")

            await self.mark_delivery_processed(delivery.id)

            await self.events.append(
                stream_id=f"webhook:{webhook.id}",
                event_type=WEBHOOK_DELIVERY_PROCESSED,
                data={
                    "delivery_id": delivery.id,
                    "event_type": event_type,
                    "actions": actions,
                },
            )

        except Exception as e:
            await self.mark_delivery_failed(delivery.id, str(e))
            await self.events.append(
                stream_id=f"webhook:{webhook.id}",
                event_type=WEBHOOK_DELIVERY_FAILED,
                data={
                    "delivery_id": delivery.id,
                    "event_type": event_type,
                    "error": str(e),
                },
            )
            raise

        return {
            "delivery_id": delivery.id,
            "event_type": event_type,
            "actions": actions,
            "status": "processed",
        }
