#!/usr/bin/env python3
"""
Entourage Multi-Agent Coordination Example.

Shows two agents working together: a manager creates sub-tasks,
an engineer executes them, with message passing between them.

Run with: python examples/multi_agent.py

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

    # ── Setup workspace ───────────────────────────────────────────
    print("Setting up workspace...\n")

    resp = client.post("/orgs", json={"name": "MultiAgent Demo", "slug": f"multi-agent-{run_id}"})
    org = resp.json()

    resp = client.post(f"/orgs/{org['id']}/teams", json={"name": "Platform", "slug": "platform"})
    team = resp.json()

    # Get auto-created manager
    agents = client.get(f"/teams/{team['id']}/agents").json()
    manager = agents[0]

    # Add two engineers
    resp = client.post(f"/teams/{team['id']}/agents", json={
        "name": "eng-backend", "role": "engineer", "model": "claude-sonnet-4-20250514",
        "config": {"description": "Backend specialist"}
    })
    eng_backend = resp.json()

    resp = client.post(f"/teams/{team['id']}/agents", json={
        "name": "eng-frontend", "role": "engineer", "model": "claude-sonnet-4-20250514",
        "config": {"description": "Frontend specialist"}
    })
    eng_frontend = resp.json()

    print(f"Team: {team['name']}")
    print(f"  manager:      {manager['id'][:8]}...")
    print(f"  eng-backend:  {eng_backend['id'][:8]}...")
    print(f"  eng-frontend: {eng_frontend['id'][:8]}...")

    # ── Manager creates parent task ───────────────────────────────
    print("\n1. Manager creates feature request...")
    resp = client.post(f"/teams/{team['id']}/tasks", json={
        "title": "Add user notifications",
        "description": "Users need push notifications for task updates",
        "priority": "high",
        "task_type": "feature"
    })
    parent_task = resp.json()
    print(f"   Parent task #{parent_task['id']}: {parent_task['title']}")

    # ── Manager decomposes into sub-tasks ─────────────────────────
    print("\n2. Manager decomposes into sub-tasks...")

    resp = client.post(f"/teams/{team['id']}/tasks", json={
        "title": "Create notifications table + API endpoints",
        "description": "Schema: id, user_id, type, message, read, created_at. Endpoints: GET /notifications, PATCH /notifications/:id/read",
        "priority": "high",
        "task_type": "feature"
    })
    task_backend = resp.json()
    print(f"   Sub-task #{task_backend['id']}: {task_backend['title']} → eng-backend")

    resp = client.post(f"/teams/{team['id']}/tasks", json={
        "title": "Build notification bell component",
        "description": "Bell icon in navbar with unread count badge. Dropdown shows recent notifications. Mark as read on click.",
        "priority": "high",
        "task_type": "feature",
        "depends_on": [task_backend['id']]
    })
    task_frontend = resp.json()
    print(f"   Sub-task #{task_frontend['id']}: {task_frontend['title']} → eng-frontend")
    print(f"   (depends on #{task_backend['id']})")

    # ── Assign tasks ──────────────────────────────────────────────
    print("\n3. Assigning tasks...")
    client.post(f"/tasks/{task_backend['id']}/assign", json={"assignee_id": eng_backend["id"]})
    client.post(f"/tasks/{task_frontend['id']}/assign", json={"assignee_id": eng_frontend["id"]})
    print(f"   #{task_backend['id']} → eng-backend")
    print(f"   #{task_frontend['id']} → eng-frontend")

    # ── Manager sends instructions via messages ───────────────────
    print("\n4. Manager sends instructions...")

    resp = client.post(f"/teams/{team['id']}/messages", json={
        "sender_id": manager["id"],
        "recipient_id": eng_backend["id"],
        "body": f"Start on task #{task_backend['id']}. Use the same pagination pattern as GET /tasks. Return 200 with empty array when no notifications exist."
    })
    print(f"   manager → eng-backend: 'Start on task #{task_backend['id']}...'")

    resp = client.post(f"/teams/{team['id']}/messages", json={
        "sender_id": manager["id"],
        "recipient_id": eng_frontend["id"],
        "body": f"Task #{task_frontend['id']} is blocked until the backend API is ready (depends on #{task_backend['id']}). Start reviewing the existing navbar component in the meantime."
    })
    print(f"   manager → eng-frontend: 'Task blocked, review navbar...'")

    # ── Check inboxes ─────────────────────────────────────────────
    print("\n5. Checking agent inboxes...")
    inbox = client.get(f"/agents/{eng_backend['id']}/inbox").json()
    print(f"   eng-backend inbox: {len(inbox)} message(s)")

    inbox = client.get(f"/agents/{eng_frontend['id']}/inbox").json()
    print(f"   eng-frontend inbox: {len(inbox)} message(s)")

    # ── Simulate eng-backend working ──────────────────────────────
    print("\n6. eng-backend works on the backend task...")
    client.post(f"/tasks/{task_backend['id']}/status", json={"status": "in_progress"})
    print(f"   #{task_backend['id']} → in_progress")

    # Try starting frontend task (should still work as the state check is on depends_on completion)
    print("\n7. eng-backend finishes, task goes to review...")
    for s in ["in_review", "in_approval", "merging", "done"]:
        client.post(f"/tasks/{task_backend['id']}/status", json={"status": s})
    print(f"   #{task_backend['id']} → in_review → in_approval → merging → done ✓")

    # ── Now frontend task is unblocked ────────────────────────────
    print(f"\n8. Frontend task #{task_frontend['id']} is now unblocked!")
    client.post(f"/tasks/{task_frontend['id']}/status", json={"status": "in_progress"})
    print(f"   #{task_frontend['id']} → in_progress")

    # eng-frontend sends a message back to manager
    client.post(f"/teams/{team['id']}/messages", json={
        "sender_id": eng_frontend["id"],
        "recipient_id": manager["id"],
        "body": f"Backend API is available. Starting on the notification bell component. ETA: ~15 minutes."
    })
    print(f"   eng-frontend → manager: 'Backend API available, starting...'")

    for s in ["in_review", "in_approval", "merging", "done"]:
        client.post(f"/tasks/{task_frontend['id']}/status", json={"status": s})
    print(f"   #{task_frontend['id']} → in_review → in_approval → merging → done ✓")

    # ── Final state ───────────────────────────────────────────────
    print("\n9. Final state:")
    for tid in [parent_task['id'], task_backend['id'], task_frontend['id']]:
        t = client.get(f"/tasks/{tid}").json()
        print(f"   Task #{t['id']}: [{t['status']}] {t['title']}")

    events_be = client.get(f"/tasks/{task_backend['id']}/events").json()
    events_fe = client.get(f"/tasks/{task_frontend['id']}/events").json()
    print(f"\n   Total events: {len(events_be)} (backend) + {len(events_fe)} (frontend)")
    print(f"\n✓ Multi-agent coordination complete!")


if __name__ == "__main__":
    main()
