#!/usr/bin/env python3
"""
Entourage Code Review Flow Example.

Full review cycle: create task → request review → add comments →
give verdict → approve → merge.

Run with: python examples/code_review_flow.py

Requires: pip install httpx
Backend must be running: http://localhost:8000
"""

import httpx
import uuid

BASE = "http://localhost:8000/api/v1"


def main():
    run_id = uuid.uuid4().hex[:6]
    client = httpx.Client(base_url=BASE, timeout=10)

    # ── Setup ─────────────────────────────────────────────────────
    print("Setting up workspace...\n")

    org = client.post("/orgs", json={"name": "Review Demo", "slug": f"review-{run_id}"}).json()
    team = client.post(f"/orgs/{org['id']}/teams", json={"name": "Backend", "slug": "backend"}).json()

    agents = client.get(f"/teams/{team['id']}/agents").json()
    manager = agents[0]

    eng = client.post(f"/teams/{team['id']}/agents", json={
        "name": "eng-1", "role": "engineer", "model": "claude-sonnet-4-20250514",
        "config": {"description": "Engineer"}
    }).json()

    repo = client.post(f"/teams/{team['id']}/repos", json={
        "name": "api-server",
        "clone_url": "https://github.com/example/api-server.git",
        "default_branch": "main",
        "local_path": "/tmp/api-server"
    }).json()

    # ── Create and assign task ────────────────────────────────────
    task = client.post(f"/teams/{team['id']}/tasks", json={
        "title": "Add rate limiting to API endpoints",
        "description": "Add 100 req/min rate limiting to all public endpoints using Redis",
        "priority": "high",
        "task_type": "feature"
    }).json()

    client.post(f"/tasks/{task['id']}/assign", json={"assignee_id": eng["id"]})
    client.post(f"/tasks/{task['id']}/status", json={"status": "in_progress"})

    print(f"Task #{task['id']}: {task['title']}")
    print(f"Status: in_progress")
    print(f"Branch: {task['branch']}")

    # ── Agent finishes coding, requests review ────────────────────
    print("\n" + "═" * 60)
    print("PHASE 1: Agent requests code review")
    print("═" * 60)

    client.post(f"/tasks/{task['id']}/status", json={"status": "in_review"})

    resp = client.post(f"/tasks/{task['id']}/reviews", json={
        "reviewer_type": "user"
    })
    review = resp.json()
    print(f"\nReview created: #{review['id']}")
    print(f"Attempt: {review['attempt']}")

    # ── Reviewer adds file-anchored comments ──────────────────────
    print("\n" + "═" * 60)
    print("PHASE 2: Reviewer adds comments")
    print("═" * 60)

    # Comment 1: Concern about implementation
    resp = client.post(f"/reviews/{review['id']}/comments", json={
        "file_path": "middleware/rate_limiter.py",
        "line_number": 15,
        "body": "This uses a fixed window counter. Consider using a sliding window algorithm — fixed windows can allow 2x the rate at window boundaries."
    })
    comment1 = resp.json()
    print(f"\nComment on rate_limiter.py:15")
    print(f"  'Fixed window → sliding window concern'")

    # Comment 2: Suggestion
    resp = client.post(f"/reviews/{review['id']}/comments", json={
        "file_path": "middleware/rate_limiter.py",
        "line_number": 42,
        "body": "Good use of Redis MULTI/EXEC for atomicity. But add a TTL to the key to prevent orphaned entries if Redis restarts."
    })
    comment2 = resp.json()
    print(f"\nComment on rate_limiter.py:42")
    print(f"  'Add TTL to Redis key'")

    # Comment 3: Test coverage
    resp = client.post(f"/reviews/{review['id']}/comments", json={
        "file_path": "tests/test_rate_limiter.py",
        "line_number": 1,
        "body": "Tests look solid. Add one more: test behavior when Redis is down (should fail open or return 503?)."
    })
    comment3 = resp.json()
    print(f"\nComment on test_rate_limiter.py:1")
    print(f"  'Add Redis-down test case'")

    # ── Reviewer gives verdict: request changes ───────────────────
    print("\n" + "═" * 60)
    print("PHASE 3: First verdict — request changes")
    print("═" * 60)

    resp = client.post(f"/reviews/{review['id']}/verdict", json={
        "verdict": "request_changes",
        "summary": "Good start. Two things to address:\n1. Switch to sliding window algorithm\n2. Add Redis TTL and failure test"
    })
    print(f"\nVerdict: request_changes")
    print(f"  'Switch to sliding window + add TTL/failure test'")

    # ── Agent addresses feedback ──────────────────────────────────
    print("\n" + "═" * 60)
    print("PHASE 4: Agent addresses feedback")
    print("═" * 60)

    print("\n  (Agent reads review comments via MCP tools...)")
    print("  (Agent updates rate_limiter.py with sliding window...)")
    print("  (Agent adds Redis TTL and failure test...)")
    print("  (Agent requests re-review...)")

    # Request a new review round
    resp = client.post(f"/tasks/{task['id']}/reviews", json={
        "reviewer_type": "user"
    })
    review2 = resp.json()
    print(f"\nNew review round: #{review2['id']}")

    # ── Reviewer approves ─────────────────────────────────────────
    print("\n" + "═" * 60)
    print("PHASE 5: Approved!")
    print("═" * 60)

    resp = client.post(f"/reviews/{review2['id']}/verdict", json={
        "verdict": "approve",
        "summary": "Sliding window looks correct. TTL is in place. Failure test covers the edge case. Ship it."
    })
    print(f"\nVerdict: approve ✓")
    print(f"  'Ship it.'")

    # ── Approve and complete the task ─────────────────────────────
    print("\n" + "═" * 60)
    print("PHASE 6: Task completed")
    print("═" * 60)

    for s in ["in_approval", "merging", "done"]:
        client.post(f"/tasks/{task['id']}/status", json={"status": s})
    final_task = client.get(f"/tasks/{task['id']}").json()
    print(f"\nTask #{final_task['id']}: {final_task['status']}")

    # ── Full event trail ──────────────────────────────────────────
    print("\n" + "═" * 60)
    print("Complete audit trail:")
    print("═" * 60)
    events = client.get(f"/tasks/{task['id']}/events").json()
    for i, event in enumerate(events, 1):
        print(f"  {i}. [{event['type']}]")

    print(f"\n✓ Code review flow complete.")
    print(f"  2 review rounds, 3 file-anchored comments, request_changes → approve.")
    print(f"  Every step is in the audit trail.")


if __name__ == "__main__":
    main()
