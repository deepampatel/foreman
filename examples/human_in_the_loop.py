#!/usr/bin/env python3
"""
Entourage Human-in-the-Loop Example.

Shows an agent asking a question, waiting for human approval,
and continuing after receiving a response. The full interaction
is tracked in the event trail.

Run with: python examples/human_in_the_loop.py

Requires: pip install httpx
Backend must be running: http://localhost:8000
"""

from _common import setup_workspace


def main():
    # ── Setup ─────────────────────────────────────────────────────
    ws = setup_workspace(
        "HITL Demo",
        engineers=[{"name": "eng-1", "description": "Engineer"}],
    )
    client = ws["client"]
    team = ws["team"]
    eng = ws["engineers"][0]

    task = client.post(f"/teams/{team['id']}/tasks", json={
        "title": "Refactor authentication module",
        "description": "Switch from session-based to JWT authentication",
        "priority": "high",
        "task_type": "feature"
    }).json()

    client.post(f"/tasks/{task['id']}/assign", json={"assignee_id": eng["id"]})
    client.post(f"/tasks/{task['id']}/status", json={"status": "in_progress"})

    print(f"\nTask #{task['id']}: {task['title']}")
    print(f"Assigned to: {eng['name']}")
    print(f"Status: in_progress")

    # ── Agent encounters ambiguity and asks human ─────────────────
    print("\n" + "─" * 60)
    print("Agent encounters a design decision it can't make alone...")
    print("─" * 60)

    question_text = (
        "I'm implementing JWT auth and need a decision on token expiry:\n\n"
        "Option A: Short-lived access tokens (15min) + refresh tokens (30 days)\n"
        "Option B: Long-lived access tokens (24h), no refresh tokens\n"
        "Option C: Short-lived (1h) + refresh (7 days)\n\n"
        "Which approach should I take?"
    )

    resp = client.post("/human-requests", json={
        "agent_id": eng["id"],
        "team_id": team["id"],
        "task_id": task["id"],
        "kind": "question",
        "question": question_text,
        "options": ["Option A", "Option B", "Option C"]
    })
    request = resp.json()
    print(f"\nAgent asked: '{request['question'][:60]}...'")
    print(f"Request ID: {request['id']}")
    print(f"Status: {request['status']}")

    # ── Check pending requests (what a human would see) ───────────
    print("\n" + "─" * 60)
    print("Human checks pending requests on the dashboard...")
    print("─" * 60)

    pending = client.get(f"/teams/{team['id']}/human-requests").json()
    print(f"\nPending requests: {len(pending)}")
    for req in pending:
        print(f"  [{req['kind']}] {req['question'][:80]}...")

    # ── Human responds ────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("Human reviews and responds...")
    print("─" * 60)

    resp = client.post(f"/human-requests/{request['id']}/respond", json={
        "response": (
            "Go with Option A (short-lived access + refresh tokens). "
            "Use 60min for access tokens and 30 days for refresh. "
            "We already have refresh logic in our mobile app, so it's not new work. "
            "Security is more important here since we handle payment data."
        )
    })
    resolved = resp.json()
    print(f"\nResponse sent!")
    print(f"Decision: {resolved['status']}")
    print(f"Response: 'Go with Option A...'")

    # ── Agent continues working ───────────────────────────────────
    print("\n" + "─" * 60)
    print("Agent receives response and continues...")
    print("─" * 60)

    # Agent can check its resolved request
    updated_request = client.get(f"/human-requests/{request['id']}").json()
    print(f"\nRequest status: {updated_request['status']}")
    print(f"Human said: {updated_request.get('response', 'N/A')[:80]}...")

    # Agent finishes the task
    for s in ["in_review", "in_approval", "merging", "done"]:
        client.post(f"/tasks/{task['id']}/status", json={"status": s})
        print(f"  Task #{task['id']} → {s}")

    # ── Event trail shows the full story ──────────────────────────
    print("\n" + "─" * 60)
    print("Full event trail:")
    print("─" * 60)
    events = client.get(f"/tasks/{task['id']}/events").json()
    for event in events:
        etype = event['type']
        data = event.get('data', {})
        detail = data.get('status', data.get('request_type', ''))
        print(f"  [{etype}] {detail}")

    print(f"\n✓ Human-in-the-loop cycle complete.")
    print(f"  The agent paused, asked a question, got a human decision,")
    print(f"  and continued — all tracked in the event trail.")


if __name__ == "__main__":
    main()
