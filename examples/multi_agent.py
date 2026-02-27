#!/usr/bin/env python3
"""
Entourage Multi-Agent Coordination Example.

Shows two agents working together: a manager decomposes a feature into
sub-tasks using batch creation with DAG dependencies, engineers execute
them, with message passing between agents.

Run with: python examples/multi_agent.py

Requires: pip install httpx
Backend must be running: http://localhost:8000
"""

from _common import setup_workspace


def main():
    # ── Setup workspace with two engineers ──────────────────────────
    ws = setup_workspace(
        "MultiAgent Demo",
        engineers=[
            {"name": "eng-backend", "description": "Backend specialist"},
            {"name": "eng-frontend", "description": "Frontend specialist"},
        ],
    )
    client = ws["client"]
    team = ws["team"]
    manager = ws["manager"]
    eng_backend = ws["engineers"][0]
    eng_frontend = ws["engineers"][1]

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

    # ── Batch create sub-tasks with dependencies ──────────────────
    print("\n2. Manager batch-creates sub-tasks with DAG dependencies...")

    resp = client.post(f"/teams/{team['id']}/tasks/batch", json={
        "tasks": [
            {
                "title": "Create notifications table + API endpoints",
                "description": "Schema: id, user_id, type, message, read, created_at. "
                               "Endpoints: GET /notifications, PATCH /notifications/:id/read",
                "priority": "high",
                "assignee_id": eng_backend["id"],
            },
            {
                "title": "Build notification bell component",
                "description": "Bell icon in navbar with unread count badge. "
                               "Dropdown shows recent notifications. Mark as read on click.",
                "priority": "high",
                "assignee_id": eng_frontend["id"],
                "depends_on_indices": [0],  # Depends on task at index 0 (backend)
            },
        ]
    })
    assert resp.status_code == 201, f"Batch create failed: {resp.text}"
    batch_tasks = resp.json()
    task_backend = batch_tasks[0]
    task_frontend = batch_tasks[1]

    print(f"   Sub-task #{task_backend['id']}: {task_backend['title']}")
    print(f"     → Assigned to: eng-backend")
    print(f"   Sub-task #{task_frontend['id']}: {task_frontend['title']}")
    print(f"     → Assigned to: eng-frontend")
    print(f"     → Depends on: #{task_backend['id']}")

    # ── Manager sends instructions via messages ───────────────────
    print("\n3. Manager sends instructions...")

    client.post(f"/teams/{team['id']}/messages", json={
        "sender_id": manager["id"],
        "recipient_id": eng_backend["id"],
        "body": f"Start on task #{task_backend['id']}. Use the same pagination pattern "
                f"as GET /tasks. Return 200 with empty array when no notifications exist."
    })
    print(f"   manager → eng-backend: 'Start on task #{task_backend['id']}...'")

    client.post(f"/teams/{team['id']}/messages", json={
        "sender_id": manager["id"],
        "recipient_id": eng_frontend["id"],
        "body": f"Task #{task_frontend['id']} is blocked until the backend API is ready "
                f"(depends on #{task_backend['id']}). Start reviewing the existing "
                f"navbar component in the meantime."
    })
    print(f"   manager → eng-frontend: 'Task blocked, review navbar...'")

    # ── Check inboxes ─────────────────────────────────────────────
    print("\n4. Checking agent inboxes...")
    inbox = client.get(f"/agents/{eng_backend['id']}/inbox").json()
    print(f"   eng-backend inbox: {len(inbox)} message(s)")

    inbox = client.get(f"/agents/{eng_frontend['id']}/inbox").json()
    print(f"   eng-frontend inbox: {len(inbox)} message(s)")

    # ── Simulate eng-backend working ──────────────────────────────
    print("\n5. eng-backend works on the backend task...")
    client.post(f"/tasks/{task_backend['id']}/status", json={"status": "in_progress"})
    print(f"   #{task_backend['id']} → in_progress")

    print("\n6. eng-backend finishes, task goes to review...")
    for s in ["in_review", "in_approval", "merging", "done"]:
        client.post(f"/tasks/{task_backend['id']}/status", json={"status": s})
    print(f"   #{task_backend['id']} → in_review → in_approval → merging → done ✓")

    # ── Now frontend task is unblocked ────────────────────────────
    print(f"\n7. Frontend task #{task_frontend['id']} is now unblocked!")
    client.post(f"/tasks/{task_frontend['id']}/status", json={"status": "in_progress"})
    print(f"   #{task_frontend['id']} → in_progress")

    # eng-frontend sends a message back to manager
    client.post(f"/teams/{team['id']}/messages", json={
        "sender_id": eng_frontend["id"],
        "recipient_id": manager["id"],
        "body": "Backend API is available. Starting on the notification bell component. ETA: ~15 minutes."
    })
    print(f"   eng-frontend → manager: 'Backend API available, starting...'")

    for s in ["in_review", "in_approval", "merging", "done"]:
        client.post(f"/tasks/{task_frontend['id']}/status", json={"status": s})
    print(f"   #{task_frontend['id']} → in_review → in_approval → merging → done ✓")

    # ── Final state ───────────────────────────────────────────────
    print("\n8. Final state:")
    for tid in [parent_task['id'], task_backend['id'], task_frontend['id']]:
        t = client.get(f"/tasks/{tid}").json()
        print(f"   Task #{t['id']}: [{t['status']}] {t['title']}")

    events_be = client.get(f"/tasks/{task_backend['id']}/events").json()
    events_fe = client.get(f"/tasks/{task_frontend['id']}/events").json()
    print(f"\n   Total events: {len(events_be)} (backend) + {len(events_fe)} (frontend)")
    print(f"\n✓ Multi-agent coordination complete!")
    print(f"  Used batch task creation with DAG dependencies.")
    print(f"  Agents coordinated via messages and dependency ordering.")


if __name__ == "__main__":
    main()
