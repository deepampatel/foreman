"""Phase 10: Webhooks + Settings tests.

Learn: Tests cover:
1. Webhook CRUD (create, list, get, update, delete)
2. Webhook secret regeneration
3. Incoming webhook receiver (GitHub-style)
4. Webhook deliveries audit trail
5. Team settings (get, update, merge behavior)
6. Org settings
"""

import json
import hashlib
import hmac
import uuid

import pytest


# ═══════════════════════════════════════════════════════════
# Webhook CRUD
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_webhook(client):
    """Create a webhook configuration."""
    r = await client.post("/api/v1/orgs", json={"name": "Webhook Org", "slug": f"wh-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])

    r = await client.post(
        "/api/v1/webhooks",
        json={
            "org_id": org_id,
            "name": "GitHub Webhook",
            "provider": "github",
            "events": ["push", "pull_request", "issues"],
        },
    )
    assert r.status_code == 201
    wh = r.json()
    assert wh["name"] == "GitHub Webhook"
    assert wh["provider"] == "github"
    assert wh["active"] is True
    assert "push" in wh["events"]
    assert wh["secret"]  # auto-generated


@pytest.mark.asyncio
async def test_create_webhook_with_team(client):
    """Create a webhook scoped to a specific team."""
    r = await client.post("/api/v1/orgs", json={"name": "WH Team Org", "slug": f"wht-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Team A", "slug": f"ta-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    r = await client.post(
        "/api/v1/webhooks",
        json={
            "org_id": org_id,
            "team_id": team_id,
            "name": "Team Webhook",
        },
    )
    assert r.status_code == 201
    assert r.json()["team_id"] == team_id


@pytest.mark.asyncio
async def test_list_webhooks(client):
    """List webhooks for an org."""
    r = await client.post("/api/v1/orgs", json={"name": "List WH Org", "slug": f"lwh-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])

    # Create 2 webhooks
    await client.post("/api/v1/webhooks", json={"org_id": org_id, "name": "WH 1"})
    await client.post("/api/v1/webhooks", json={"org_id": org_id, "name": "WH 2"})

    r = await client.get(f"/api/v1/webhooks/orgs/{org_id}")
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_get_webhook(client):
    """Get webhook details by ID."""
    r = await client.post("/api/v1/orgs", json={"name": "Get WH Org", "slug": f"gwh-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post("/api/v1/webhooks", json={"org_id": org_id, "name": "Get Me"})
    wh_id = r.json()["id"]

    r = await client.get(f"/api/v1/webhooks/{wh_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Get Me"


@pytest.mark.asyncio
async def test_get_webhook_not_found(client):
    """Getting a nonexistent webhook returns 404."""
    fake_id = str(uuid.uuid4())
    r = await client.get(f"/api/v1/webhooks/{fake_id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_webhook(client):
    """Update webhook configuration."""
    r = await client.post("/api/v1/orgs", json={"name": "Upd WH Org", "slug": f"uwh-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post("/api/v1/webhooks", json={"org_id": org_id, "name": "Original"})
    wh_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/webhooks/{wh_id}",
        json={"name": "Updated", "active": False, "events": ["push"]},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Updated"
    assert r.json()["active"] is False
    assert r.json()["events"] == ["push"]


@pytest.mark.asyncio
async def test_delete_webhook(client):
    """Delete a webhook."""
    r = await client.post("/api/v1/orgs", json={"name": "Del WH Org", "slug": f"dwh-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post("/api/v1/webhooks", json={"org_id": org_id, "name": "Delete Me"})
    wh_id = r.json()["id"]

    r = await client.delete(f"/api/v1/webhooks/{wh_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    # Verify it's gone
    r = await client.get(f"/api/v1/webhooks/{wh_id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_secret(client):
    """Regenerate webhook secret."""
    r = await client.post("/api/v1/orgs", json={"name": "Regen Org", "slug": f"rg-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post("/api/v1/webhooks", json={"org_id": org_id, "name": "Secret WH"})
    wh_id = r.json()["id"]
    old_secret = r.json()["secret"]

    r = await client.post(f"/api/v1/webhooks/{wh_id}/regenerate-secret")
    assert r.status_code == 200
    new_secret = r.json()["secret"]
    assert new_secret != old_secret


# ═══════════════════════════════════════════════════════════
# Incoming webhook receiver
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_receive_webhook_push(client):
    """Receive a GitHub push webhook."""
    r = await client.post("/api/v1/orgs", json={"name": "Recv Org", "slug": f"rv-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(
        "/api/v1/webhooks",
        json={"org_id": org_id, "name": "Recv WH", "events": ["push"]},
    )
    wh_id = r.json()["id"]
    secret = r.json()["secret"]

    payload = {
        "ref": "refs/heads/main",
        "commits": [{"id": "abc123", "message": "fix bug"}],
    }
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    r = await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert r.status_code == 200
    result = r.json()
    assert result["status"] == "processed"
    assert "push to refs/heads/main" in result["actions"][0]


@pytest.mark.asyncio
async def test_receive_webhook_invalid_signature(client):
    """Invalid signature returns 403."""
    r = await client.post("/api/v1/orgs", json={"name": "Sig Org", "slug": f"sig-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(
        "/api/v1/webhooks",
        json={"org_id": org_id, "name": "Sig WH"},
    )
    wh_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=b'{"test": true}',
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=invalid",
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_receive_webhook_disabled(client):
    """Disabled webhook returns 410."""
    r = await client.post("/api/v1/orgs", json={"name": "Dis Org", "slug": f"dis-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post("/api/v1/webhooks", json={"org_id": org_id, "name": "Dis WH"})
    wh_id = r.json()["id"]

    # Disable it
    await client.patch(f"/api/v1/webhooks/{wh_id}", json={"active": False})

    r = await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=b'{}',
        headers={"Content-Type": "application/json", "X-GitHub-Event": "push"},
    )
    assert r.status_code == 410


@pytest.mark.asyncio
async def test_receive_webhook_unconfigured_event(client):
    """Event type not in webhook.events is ignored."""
    r = await client.post("/api/v1/orgs", json={"name": "Evt Org", "slug": f"evt-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(
        "/api/v1/webhooks",
        json={"org_id": org_id, "name": "Evt WH", "events": ["push"]},
    )
    wh_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=b'{}',
        headers={"Content-Type": "application/json", "X-GitHub-Event": "issues"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_deliveries(client):
    """Deliveries are logged and retrievable."""
    r = await client.post("/api/v1/orgs", json={"name": "Del Org", "slug": f"del-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(
        "/api/v1/webhooks",
        json={"org_id": org_id, "name": "Del WH", "events": ["push"]},
    )
    wh_id = r.json()["id"]
    secret = r.json()["secret"]

    # Send a webhook
    payload = json.dumps({"ref": "refs/heads/main", "commits": []}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )

    # Check deliveries
    r = await client.get(f"/api/v1/webhooks/{wh_id}/deliveries")
    assert r.status_code == 200
    deliveries = r.json()
    assert len(deliveries) == 1
    assert deliveries[0]["event_type"] == "push"
    assert deliveries[0]["status"] == "processed"


# ═══════════════════════════════════════════════════════════
# Team Settings
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_team_settings_default(client):
    """New team has empty settings."""
    r = await client.post("/api/v1/orgs", json={"name": "Set Org", "slug": f"set-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Set Team", "slug": f"st-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    r = await client.get(f"/api/v1/settings/teams/{team_id}")
    assert r.status_code == 200
    assert r.json()["settings"] == {}


@pytest.mark.asyncio
async def test_update_team_settings(client):
    """Update team settings."""
    r = await client.post("/api/v1/orgs", json={"name": "Upd Set Org", "slug": f"us-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Upd Team", "slug": f"ut-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    r = await client.patch(
        f"/api/v1/settings/teams/{team_id}",
        json={
            "daily_cost_limit_usd": 100.0,
            "default_model": "claude-sonnet-4-20250514",
            "auto_merge": True,
        },
    )
    assert r.status_code == 200
    settings = r.json()["settings"]
    assert settings["daily_cost_limit_usd"] == 100.0
    assert settings["default_model"] == "claude-sonnet-4-20250514"
    assert settings["auto_merge"] is True


@pytest.mark.asyncio
async def test_settings_merge_behavior(client):
    """Settings updates merge with existing values, not replace."""
    r = await client.post("/api/v1/orgs", json={"name": "Merge Org", "slug": f"mg-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Merge Team", "slug": f"mt-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    # First update
    await client.patch(
        f"/api/v1/settings/teams/{team_id}",
        json={"daily_cost_limit_usd": 50.0},
    )

    # Second update — should keep daily_cost_limit_usd
    r = await client.patch(
        f"/api/v1/settings/teams/{team_id}",
        json={"default_model": "claude-sonnet-4-20250514"},
    )
    settings = r.json()["settings"]
    assert settings["daily_cost_limit_usd"] == 50.0
    assert settings["default_model"] == "claude-sonnet-4-20250514"


@pytest.mark.asyncio
async def test_team_settings_not_found(client):
    """Settings for nonexistent team returns 404."""
    fake_id = str(uuid.uuid4())
    r = await client.get(f"/api/v1/settings/teams/{fake_id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_org_settings(client):
    """Get org settings."""
    r = await client.post("/api/v1/orgs", json={"name": "Org Set", "slug": f"os-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])

    r = await client.get(f"/api/v1/settings/orgs/{org_id}")
    assert r.status_code == 200
    assert r.json()["org_name"] == "Org Set"
    assert r.json()["settings"] == {}


# ═══════════════════════════════════════════════════════════
# Full lifecycle
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_github_issue_creates_task(client):
    """GitHub issues.opened event auto-creates a task."""
    # Setup org + team + webhook with team_id
    r = await client.post("/api/v1/orgs", json={"name": "Issue Org", "slug": f"io-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Issue Team", "slug": f"it-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    r = await client.post(
        "/api/v1/webhooks",
        json={
            "org_id": org_id,
            "team_id": team_id,
            "name": "Issue WH",
            "events": ["issues"],
        },
    )
    wh_id = r.json()["id"]
    secret = r.json()["secret"]

    # Send issues.opened event
    payload = json.dumps({
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "Bug: login broken",
            "body": "Login page returns 500 after latest deploy",
            "labels": [{"name": "critical"}, {"name": "auth"}],
        },
    }).encode()
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    r = await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": sig,
        },
    )
    assert r.status_code == 200
    result = r.json()
    assert any("created task" in a for a in result["actions"])
    assert any("issue #42" in a for a in result["actions"])

    # Verify task was created in the team
    r = await client.get(f"/api/v1/teams/{team_id}/tasks")
    tasks = r.json()
    assert len(tasks) >= 1
    task = next(t for t in tasks if "[GitHub]" in t["title"])
    assert "Bug: login broken" in task["title"]
    assert task["priority"] == "critical"  # mapped from label


@pytest.mark.asyncio
async def test_github_pr_creates_task(client):
    """GitHub pull_request.opened event auto-creates a task."""
    r = await client.post("/api/v1/orgs", json={"name": "PR Org", "slug": f"po-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "PR Team", "slug": f"pt-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    r = await client.post(
        "/api/v1/webhooks",
        json={
            "org_id": org_id,
            "team_id": team_id,
            "name": "PR WH",
            "events": ["pull_request"],
        },
    )
    wh_id = r.json()["id"]
    secret = r.json()["secret"]

    payload = json.dumps({
        "action": "opened",
        "pull_request": {
            "number": 99,
            "title": "Add rate limiting",
            "body": "Implements rate limiting using Redis",
        },
    }).encode()
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    r = await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sig,
        },
    )
    assert r.status_code == 200
    result = r.json()
    assert any("created task" in a for a in result["actions"])

    # Verify
    r = await client.get(f"/api/v1/teams/{team_id}/tasks")
    tasks = r.json()
    task = next(t for t in tasks if "[GitHub PR]" in t["title"])
    assert "Add rate limiting" in task["title"]
    assert task["priority"] == "medium"


@pytest.mark.asyncio
async def test_github_label_to_priority_mapping(client):
    """GitHub labels map to correct priorities."""
    from openclaw.services.webhook_service import WebhookService

    assert WebhookService._map_github_labels_to_priority(["critical"]) == "critical"
    assert WebhookService._map_github_labels_to_priority(["urgent"]) == "critical"
    assert WebhookService._map_github_labels_to_priority(["P0"]) == "critical"
    assert WebhookService._map_github_labels_to_priority(["high"]) == "high"
    assert WebhookService._map_github_labels_to_priority(["important"]) == "high"
    assert WebhookService._map_github_labels_to_priority(["P1"]) == "high"
    assert WebhookService._map_github_labels_to_priority(["low"]) == "low"
    assert WebhookService._map_github_labels_to_priority(["minor"]) == "low"
    assert WebhookService._map_github_labels_to_priority(["P3"]) == "low"
    assert WebhookService._map_github_labels_to_priority(["enhancement"]) == "medium"
    assert WebhookService._map_github_labels_to_priority([]) == "medium"


@pytest.mark.asyncio
async def test_webhook_auto_assign(client):
    """Webhook with auto_assign creates task and assigns to idle agent."""
    r = await client.post("/api/v1/orgs", json={"name": "Auto Org", "slug": f"ao-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Auto Team", "slug": f"at-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    # Create an idle agent
    r = await client.post(f"/api/v1/teams/{team_id}/agents", json={
        "name": "auto-eng",
        "role": "engineer",
    })
    agent_id = str(r.json()["id"])

    # Create webhook with auto_assign config
    r = await client.post(
        "/api/v1/webhooks",
        json={
            "org_id": org_id,
            "team_id": team_id,
            "name": "Auto WH",
            "events": ["issues"],
            "config": {"auto_assign": True},
        },
    )
    wh_id = r.json()["id"]
    secret = r.json()["secret"]

    payload = json.dumps({
        "action": "opened",
        "issue": {
            "number": 7,
            "title": "Fix typo in README",
            "body": "Small fix",
            "labels": [],
        },
    }).encode()
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    r = await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": sig,
        },
    )
    assert r.status_code == 200
    result = r.json()
    assert any("auto-assigned" in a for a in result["actions"])

    # Verify task is assigned to an agent in the team
    r = await client.get(f"/api/v1/teams/{team_id}/tasks")
    tasks = r.json()
    task = next(t for t in tasks if "[GitHub]" in t["title"])
    # Team auto-creates a manager agent, so assignee could be either
    r = await client.get(f"/api/v1/teams/{team_id}/agents")
    team_agent_ids = {str(a["id"]) for a in r.json()}
    assert task["assignee_id"] in team_agent_ids


# ═══════════════════════════════════════════════════════════
# Team Conventions
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_convention(client):
    """Create a team convention."""
    r = await client.post("/api/v1/orgs", json={"name": "Conv Org", "slug": f"co-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Conv Team", "slug": f"ct-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    r = await client.post(
        f"/api/v1/settings/teams/{team_id}/conventions",
        json={
            "key": "testing",
            "content": "Always write unit tests. Use pytest. Target 80% coverage.",
            "active": True,
        },
    )
    assert r.status_code == 201
    conv = r.json()
    assert conv["key"] == "testing"
    assert "pytest" in conv["content"]
    assert conv["active"] is True


@pytest.mark.asyncio
async def test_list_conventions(client):
    """List all team conventions."""
    r = await client.post("/api/v1/orgs", json={"name": "List Conv Org", "slug": f"lc-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "List Conv Team", "slug": f"lct-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    # Create 2 conventions
    await client.post(
        f"/api/v1/settings/teams/{team_id}/conventions",
        json={"key": "testing", "content": "Use pytest"},
    )
    await client.post(
        f"/api/v1/settings/teams/{team_id}/conventions",
        json={"key": "code_style", "content": "Use ruff for linting"},
    )

    r = await client.get(f"/api/v1/settings/teams/{team_id}/conventions")
    assert r.status_code == 200
    convs = r.json()
    assert len(convs) == 2
    assert {c["key"] for c in convs} == {"testing", "code_style"}


@pytest.mark.asyncio
async def test_update_convention(client):
    """Update a convention by key."""
    r = await client.post("/api/v1/orgs", json={"name": "Upd Conv Org", "slug": f"uc-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Upd Conv Team", "slug": f"uct-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    await client.post(
        f"/api/v1/settings/teams/{team_id}/conventions",
        json={"key": "architecture", "content": "Use hexagonal architecture"},
    )

    r = await client.put(
        f"/api/v1/settings/teams/{team_id}/conventions/architecture",
        json={"content": "Use clean architecture with DDD", "active": False},
    )
    assert r.status_code == 200
    conv = r.json()
    assert conv["content"] == "Use clean architecture with DDD"
    assert conv["active"] is False


@pytest.mark.asyncio
async def test_delete_convention(client):
    """Delete a convention by key."""
    r = await client.post("/api/v1/orgs", json={"name": "Del Conv Org", "slug": f"dc-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Del Conv Team", "slug": f"dct-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    await client.post(
        f"/api/v1/settings/teams/{team_id}/conventions",
        json={"key": "to_delete", "content": "Temporary convention"},
    )

    r = await client.delete(f"/api/v1/settings/teams/{team_id}/conventions/to_delete")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    # Verify it's gone
    r = await client.get(f"/api/v1/settings/teams/{team_id}/conventions")
    assert len(r.json()) == 0


@pytest.mark.asyncio
async def test_create_duplicate_convention_fails(client):
    """Duplicate convention key returns 409."""
    r = await client.post("/api/v1/orgs", json={"name": "Dup Org", "slug": f"dp-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])
    r = await client.post(f"/api/v1/orgs/{org_id}/teams", json={"name": "Dup Team", "slug": f"dpt-{uuid.uuid4().hex[:8]}"})
    team_id = str(r.json()["id"])

    await client.post(
        f"/api/v1/settings/teams/{team_id}/conventions",
        json={"key": "testing", "content": "Use pytest"},
    )

    r = await client.post(
        f"/api/v1/settings/teams/{team_id}/conventions",
        json={"key": "testing", "content": "Use unittest"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_full_webhook_lifecycle(client):
    """Full lifecycle: create → receive → check deliveries → update → delete."""
    # Setup
    r = await client.post("/api/v1/orgs", json={"name": "Full Org", "slug": f"fl-{uuid.uuid4().hex[:8]}"})
    org_id = str(r.json()["id"])

    # Create webhook
    r = await client.post(
        "/api/v1/webhooks",
        json={"org_id": org_id, "name": "Full WH", "events": ["push", "pull_request"]},
    )
    assert r.status_code == 201
    wh_id = r.json()["id"]
    secret = r.json()["secret"]

    # Receive a push event
    push_payload = json.dumps({"ref": "refs/heads/feature", "commits": [{"id": "a1"}]}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), push_payload, hashlib.sha256).hexdigest()
    r = await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=push_payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert r.status_code == 200

    # Receive a PR event
    pr_payload = json.dumps({
        "action": "opened",
        "pull_request": {"title": "Add feature X"},
    }).encode()
    sig = "sha256=" + hmac.new(secret.encode(), pr_payload, hashlib.sha256).hexdigest()
    r = await client.post(
        f"/api/v1/webhooks/{wh_id}/receive",
        content=pr_payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sig,
        },
    )
    assert r.status_code == 200

    # Check deliveries
    r = await client.get(f"/api/v1/webhooks/{wh_id}/deliveries")
    assert len(r.json()) == 2

    # Update webhook
    r = await client.patch(f"/api/v1/webhooks/{wh_id}", json={"name": "Updated WH"})
    assert r.json()["name"] == "Updated WH"

    # Delete webhook
    r = await client.delete(f"/api/v1/webhooks/{wh_id}")
    assert r.json()["deleted"] is True
