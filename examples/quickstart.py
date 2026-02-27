#!/usr/bin/env python3
"""
Entourage Quickstart — Full lifecycle in one script.

Creates an org → team → agent → repo → task → assign → status transitions.
Run with: python examples/quickstart.py

Requires: pip install httpx
Backend must be running: http://localhost:8000
"""

import httpx
import sys
import uuid

BASE = "http://localhost:8000/api/v1"


def main():
    run_id = uuid.uuid4().hex[:6]
    client = httpx.Client(base_url=BASE, timeout=10)

    # ── Health check ──────────────────────────────────────────────
    print("Checking backend health...")
    resp = client.get("/health")
    if resp.status_code != 200:
        print(f"Backend not reachable at {BASE}")
        sys.exit(1)
    health = resp.json()
    print(f"  Postgres: {'✓' if health['postgres'] else '✗'}")
    print(f"  Redis:    {'✓' if health['redis'] else '✗'}")

    # ── Create org ────────────────────────────────────────────────
    print("\n1. Creating organization...")
    resp = client.post("/orgs", json={"name": "Demo Corp", "slug": f"demo-corp-{run_id}"})
    assert resp.status_code == 201, f"Failed: {resp.text}"
    org = resp.json()
    print(f"   Org: {org['name']} ({org['id'][:8]}...)")

    # ── Create team (auto-creates manager agent) ──────────────────
    print("\n2. Creating team...")
    resp = client.post(f"/orgs/{org['id']}/teams", json={"name": "Engineering", "slug": "engineering"})
    assert resp.status_code == 201, f"Failed: {resp.text}"
    team = resp.json()
    print(f"   Team: {team['name']} ({team['id'][:8]}...)")

    # ── List agents (should have auto-created manager) ────────────
    resp = client.get(f"/teams/{team['id']}/agents")
    agents = resp.json()
    manager = agents[0]
    print(f"   Manager auto-created: {manager['name']} ({manager['role']})")

    # ── Add engineer ──────────────────────────────────────────────
    print("\n3. Adding engineer agent...")
    resp = client.post(f"/teams/{team['id']}/agents", json={
        "name": "eng-1",
        "role": "engineer",
        "model": "claude-sonnet-4-20250514",
        "config": {"description": "General-purpose engineer"}
    })
    assert resp.status_code == 201, f"Failed: {resp.text}"
    engineer = resp.json()
    print(f"   Agent: {engineer['name']} ({engineer['id'][:8]}...)")

    # ── Register repo ─────────────────────────────────────────────
    print("\n4. Registering repository...")
    resp = client.post(f"/teams/{team['id']}/repos", json={
        "name": "demo-app",
        "clone_url": "https://github.com/example/demo-app.git",
        "default_branch": "main",
        "local_path": "/tmp/demo-app"
    })
    assert resp.status_code == 201, f"Failed: {resp.text}"
    repo = resp.json()
    print(f"   Repo: {repo['name']}")

    # ── Create task ───────────────────────────────────────────────
    print("\n5. Creating task...")
    resp = client.post(f"/teams/{team['id']}/tasks", json={
        "title": "Add health check to API",
        "description": "Add a /healthz endpoint that returns 200 when the service is ready",
        "priority": "medium",
        "task_type": "feature"
    })
    assert resp.status_code == 201, f"Failed: {resp.text}"
    task = resp.json()
    print(f"   Task #{task['id']}: {task['title']}")
    print(f"   Status: {task['status']}")
    print(f"   Branch: {task['branch']}")

    # ── Assign to engineer ────────────────────────────────────────
    print("\n6. Assigning task to eng-1...")
    resp = client.post(f"/tasks/{task['id']}/assign", json={
        "assignee_id": engineer["id"]
    })
    assert resp.status_code == 200, f"Failed: {resp.text}"
    print(f"   Assigned to: {engineer['name']}")

    # ── Move through states ───────────────────────────────────────
    print("\n7. Walking through task lifecycle...")

    for status in ["in_progress", "in_review", "in_approval", "merging", "done"]:
        resp = client.post(f"/tasks/{task['id']}/status", json={"status": status})
        assert resp.status_code == 200, f"Failed transition to {status}: {resp.text}"
        print(f"   → {status}")

    # ── Check event trail ─────────────────────────────────────────
    print("\n8. Event trail:")
    resp = client.get(f"/tasks/{task['id']}/events")
    events = resp.json()
    for event in events:
        print(f"   [{event['type']}] {event.get('data', {}).get('status', '')}")

    # ── Done ──────────────────────────────────────────────────────
    print(f"\n✓ Complete lifecycle finished. Task #{task['id']} is done.")
    print(f"  {len(events)} events recorded in the audit trail.")


if __name__ == "__main__":
    main()
