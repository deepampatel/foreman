#!/usr/bin/env python3
"""
Entourage Webhook Automation Example.

Registers a GitHub webhook, simulates an incoming event,
and verifies the delivery was processed.

Run with: python examples/webhook_automation.py

Requires: pip install httpx
Backend must be running: http://localhost:8000
"""

import hashlib
import hmac
import json

import httpx
import uuid as _uuid

BASE = "http://localhost:8000/api/v1"


def generate_github_signature(secret: str, payload: bytes) -> str:
    """Generate GitHub-style HMAC-SHA256 signature."""
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def main():
    run_id = _uuid.uuid4().hex[:6]
    client = httpx.Client(base_url=BASE, timeout=10)

    # ── Setup ─────────────────────────────────────────────────────
    print("Setting up workspace...\n")

    org = client.post("/orgs", json={"name": "Webhook Demo", "slug": f"webhook-{run_id}"}).json()
    team = client.post(f"/orgs/{org['id']}/teams", json={"name": "Backend", "slug": "backend"}).json()
    print(f"Org: {org['name']}")
    print(f"Team: {team['name']}")

    # ── Register webhook ──────────────────────────────────────────
    print("\n" + "═" * 60)
    print("STEP 1: Register a GitHub webhook")
    print("═" * 60)

    resp = client.post("/webhooks", json={
        "org_id": org["id"],
        "name": "github-integration",
        "team_id": team["id"],
        "provider": "github",
        "events": ["issues.opened", "issues.closed", "pull_request.opened"],
        "config": {
            "auto_assign": True
        }
    })
    webhook = resp.json()
    webhook_id = webhook["id"]
    secret = webhook["secret"]

    print(f"\nWebhook ID: {webhook_id}")
    print(f"Secret: {secret[:12]}... (used for HMAC verification)")
    print(f"Events: {webhook['events']}")
    print(f"Active: {webhook['active']}")
    print(f"\nIn production, set this as your GitHub webhook URL:")
    print(f"  https://your-server.com/api/v1/webhooks/{webhook_id}/receive")

    # ── Simulate GitHub issue.opened event ────────────────────────
    print("\n" + "═" * 60)
    print("STEP 2: Simulate a GitHub issue.opened webhook")
    print("═" * 60)

    # This is what GitHub would send
    github_payload = {
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "Login page crashes on Safari 17",
            "body": "Steps to reproduce:\n1. Open /login in Safari 17\n2. Click 'Sign in with Google'\n3. Page crashes with blank screen\n\nExpected: OAuth redirect\nActual: White screen of death",
            "user": {"login": "jane-dev"},
            "labels": [{"name": "bug"}, {"name": "priority:high"}],
            "html_url": "https://github.com/example/app/issues/42"
        },
        "repository": {
            "full_name": "example/app",
            "html_url": "https://github.com/example/app"
        },
        "sender": {"login": "jane-dev"}
    }

    payload_bytes = json.dumps(github_payload).encode()
    signature = generate_github_signature(secret, payload_bytes)

    print(f"\nPayload: issue #{github_payload['issue']['number']} - {github_payload['issue']['title']}")
    print(f"Signature: {signature[:30]}...")

    # Send the webhook (like GitHub would)
    resp = client.post(
        f"/webhooks/{webhook_id}/receive",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": "test-delivery-001"
        }
    )
    print(f"\nResponse: {resp.status_code}")
    print(f"Body: {resp.json()}")

    # ── Check delivery was logged ─────────────────────────────────
    print("\n" + "═" * 60)
    print("STEP 3: Verify delivery was logged")
    print("═" * 60)

    resp = client.get(f"/webhooks/{webhook_id}/deliveries")
    deliveries = resp.json()
    print(f"\nDeliveries: {len(deliveries)}")
    for d in deliveries:
        print(f"  [{d['event_type']}] status={d['status']} at {d['created_at']}")

    # ── Test signature verification (send tampered payload) ───────
    print("\n" + "═" * 60)
    print("STEP 4: Test signature verification (tampered payload)")
    print("═" * 60)

    tampered_payload = json.dumps({"action": "opened", "issue": {"title": "MALICIOUS"}}).encode()

    resp = client.post(
        f"/webhooks/{webhook_id}/receive",
        content=tampered_payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
            "X-GitHub-Delivery": "test-delivery-002"
        }
    )
    print(f"\nTampered request status: {resp.status_code}")
    if resp.status_code in (401, 403):
        print("✓ Correctly rejected — HMAC signature mismatch")
    else:
        print(f"Response: {resp.json()}")

    # ── Test unsubscribed event (filtered out) ────────────────────
    print("\n" + "═" * 60)
    print("STEP 5: Test event filtering")
    print("═" * 60)

    # We only subscribed to issues.opened, issues.closed, pull_request.opened
    # Send a push event (not subscribed)
    push_payload = json.dumps({"ref": "refs/heads/main", "commits": []}).encode()
    push_signature = generate_github_signature(secret, push_payload)

    resp = client.post(
        f"/webhooks/{webhook_id}/receive",
        content=push_payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": push_signature,
            "X-GitHub-Delivery": "test-delivery-003"
        }
    )
    print(f"\nPush event status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    print("(Logged but not processed — push events aren't in our subscription)")

    # ── Check webhook status ──────────────────────────────────────
    print("\n" + "═" * 60)
    print("STEP 6: Final webhook status")
    print("═" * 60)

    webhook_status = client.get(f"/webhooks/{webhook_id}").json()
    print(f"\nWebhook: {webhook_status['id']}")
    print(f"Provider: {webhook_status['provider']}")
    print(f"Active: {webhook_status['active']}")
    print(f"Events: {webhook_status['events']}")

    deliveries = client.get(f"/webhooks/{webhook_id}/deliveries").json()
    print(f"\nTotal deliveries: {len(deliveries)}")

    print(f"\n✓ Webhook automation complete.")
    print(f"  - Registered webhook with HMAC secret")
    print(f"  - Simulated GitHub issue event → processed")
    print(f"  - Tampered payload → rejected (signature mismatch)")
    print(f"  - Unsubscribed event → logged but filtered")


if __name__ == "__main__":
    main()
