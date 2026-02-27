#!/usr/bin/env python3
"""
Entourage Quickstart — Full lifecycle in one script.

Creates an org → team → agent → repo → task → assign → status transitions.
Demonstrates authentication, workspace setup, and the task state machine.

Run with: python examples/quickstart.py

Requires: pip install httpx
Backend must be running: http://localhost:8000
"""

from _common import setup_workspace


def main():
    # ── Authenticate + create workspace ─────────────────────────────
    ws = setup_workspace(
        "Demo Corp",
        engineers=[{"name": "eng-1", "description": "General-purpose engineer"}],
        repo={"name": "demo-app"},
    )
    client = ws["client"]
    team = ws["team"]
    engineer = ws["engineers"][0]

    # ── Create task ───────────────────────────────────────────────
    print("\n1. Creating task...")
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
    print("\n2. Assigning task to eng-1...")
    resp = client.post(f"/tasks/{task['id']}/assign", json={
        "assignee_id": engineer["id"]
    })
    assert resp.status_code == 200, f"Failed: {resp.text}"
    print(f"   Assigned to: {engineer['name']}")

    # ── Move through states ───────────────────────────────────────
    print("\n3. Walking through task lifecycle...")

    for status in ["in_progress", "in_review", "in_approval", "merging", "done"]:
        resp = client.post(f"/tasks/{task['id']}/status", json={"status": status})
        assert resp.status_code == 200, f"Failed transition to {status}: {resp.text}"
        print(f"   → {status}")

    # ── Check event trail ─────────────────────────────────────────
    print("\n4. Event trail:")
    resp = client.get(f"/tasks/{task['id']}/events")
    events = resp.json()
    for event in events:
        print(f"   [{event['type']}] {event.get('data', {}).get('status', '')}")

    # ── Done ──────────────────────────────────────────────────────
    print(f"\n✓ Complete lifecycle finished. Task #{task['id']} is done.")
    print(f"  {len(events)} events recorded in the audit trail.")


if __name__ == "__main__":
    main()
