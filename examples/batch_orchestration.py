#!/usr/bin/env python3
"""
Entourage Batch Orchestration Example.

Demonstrates how a manager agent decomposes a large feature into a DAG
of sub-tasks using batch creation, assigns them to specialists, tracks
costs via sessions, and monitors team progress.

Run with: python examples/batch_orchestration.py

Requires: pip install httpx
Backend must be running: http://localhost:8000
"""

import time

from _common import setup_workspace


def main():
    # ── Setup workspace with specialist agents ────────────────────
    ws = setup_workspace(
        "Orchestration Demo",
        engineers=[
            {"name": "eng-api", "description": "API design specialist"},
            {"name": "eng-db", "description": "Database/schema specialist"},
            {"name": "eng-ui", "description": "Frontend UI specialist"},
            {"name": "eng-test", "description": "Testing/QA specialist"},
        ],
        repo={"name": "saas-platform"},
    )
    client = ws["client"]
    team = ws["team"]
    manager = ws["manager"]
    eng_api, eng_db, eng_ui, eng_test = ws["engineers"]

    # ── Create parent epic ────────────────────────────────────────
    print("\n" + "═" * 60)
    print("PHASE 1: Manager creates parent epic")
    print("═" * 60)

    epic = client.post(f"/teams/{team['id']}/tasks", json={
        "title": "Implement billing module",
        "description": "Complete billing system: database schema, API endpoints, "
                       "Stripe integration, UI components, and end-to-end tests.",
        "priority": "critical",
        "task_type": "feature",
    }).json()
    print(f"\nEpic #{epic['id']}: {epic['title']}")
    print(f"Branch: {epic['branch']}")

    # ── Batch create DAG of sub-tasks ─────────────────────────────
    print("\n" + "═" * 60)
    print("PHASE 2: Batch-create task DAG (5 tasks, 4 dependencies)")
    print("═" * 60)

    resp = client.post(f"/teams/{team['id']}/tasks/batch", json={
        "tasks": [
            {
                # Index 0: Database schema (no deps, first to start)
                "title": "Design billing database schema",
                "description": "Tables: subscriptions, invoices, payments, plans. "
                               "Include indexes, constraints, and migration script.",
                "priority": "critical",
                "assignee_id": eng_db["id"],
                "tags": ["database", "schema"],
            },
            {
                # Index 1: API endpoints (depends on schema)
                "title": "Build billing API endpoints",
                "description": "REST endpoints: POST /subscriptions, GET /invoices, "
                               "POST /payments/checkout-session, webhooks from Stripe.",
                "priority": "critical",
                "assignee_id": eng_api["id"],
                "depends_on_indices": [0],  # Needs schema first
                "tags": ["api", "billing"],
            },
            {
                # Index 2: Stripe integration (depends on schema)
                "title": "Integrate Stripe payment processing",
                "description": "Stripe SDK setup, webhook handler, idempotency keys, "
                               "retry logic, and error mapping.",
                "priority": "high",
                "assignee_id": eng_api["id"],
                "depends_on_indices": [0],  # Needs schema first
                "tags": ["api", "stripe"],
            },
            {
                # Index 3: UI components (depends on API + Stripe)
                "title": "Build billing UI components",
                "description": "Plan selector, checkout form, invoice history, "
                               "subscription management page.",
                "priority": "high",
                "assignee_id": eng_ui["id"],
                "depends_on_indices": [1, 2],  # Needs API and Stripe
                "tags": ["frontend", "billing"],
            },
            {
                # Index 4: E2E tests (depends on everything)
                "title": "Write billing end-to-end tests",
                "description": "Test full flow: select plan → checkout → payment → "
                               "invoice generated → subscription active.",
                "priority": "medium",
                "assignee_id": eng_test["id"],
                "depends_on_indices": [1, 2, 3],  # Needs API + Stripe + UI
                "tags": ["testing", "e2e"],
            },
        ]
    })
    assert resp.status_code == 201, f"Batch create failed: {resp.text}"
    tasks = resp.json()

    print(f"\nCreated {len(tasks)} tasks in one request:")
    print()
    print("  Task DAG:")
    print("  ┌─────────────────────┐")
    print(f"  │ #{tasks[0]['id']:>3} Schema (eng-db)  │")
    print("  └──────┬───────┬──────┘")
    print("         │       │")
    print("         ▼       ▼")
    print(f"  ┌──────────┐ ┌──────────┐")
    print(f"  │#{tasks[1]['id']:>3} API   │ │#{tasks[2]['id']:>3} Stripe│")
    print(f"  │(eng-api) │ │(eng-api) │")
    print(f"  └────┬─────┘ └─────┬────┘")
    print("       │              │")
    print("       └──────┬───────┘")
    print("              ▼")
    print(f"       ┌──────────────┐")
    print(f"       │#{tasks[3]['id']:>3} UI (eng-ui)│")
    print(f"       └──────┬───────┘")
    print("              │")
    print("              ▼")
    print(f"       ┌──────────────┐")
    print(f"       │#{tasks[4]['id']:>3} E2E tests │")
    print(f"       │(eng-test)    │")
    print(f"       └──────────────┘")

    # ── Start agent work sessions (cost tracking) ─────────────────
    print("\n" + "═" * 60)
    print("PHASE 3: Agents start work sessions (cost tracking)")
    print("═" * 60)

    # eng-db starts working on schema
    session_resp = client.post("/sessions/start", json={
        "agent_id": eng_db["id"],
        "task_id": tasks[0]["id"],
        "model": "claude-sonnet-4-20250514",
    })
    if session_resp.status_code == 200:
        session = session_resp.json()
        print(f"\n  eng-db session started: {session['id'][:8]}...")

        # Record some token usage
        client.post(f"/sessions/{session['id']}/usage", json={
            "input_tokens": 1500,
            "output_tokens": 800,
        })
        print(f"  Recorded usage: 1500 input + 800 output tokens")

        # End session
        client.post(f"/sessions/{session['id']}/end")
        print(f"  Session ended")
    else:
        print(f"  (Sessions API returned {session_resp.status_code}, continuing...)")

    # ── Execute tasks in dependency order ──────────────────────────
    print("\n" + "═" * 60)
    print("PHASE 4: Execute tasks in dependency order")
    print("═" * 60)

    # Task 0: Schema (no deps)
    print(f"\n  Starting #{tasks[0]['id']} (Schema)...")
    client.post(f"/tasks/{tasks[0]['id']}/status", json={"status": "in_progress"})
    time.sleep(0.1)
    for s in ["in_review", "in_approval", "merging", "done"]:
        client.post(f"/tasks/{tasks[0]['id']}/status", json={"status": s})
    print(f"  ✓ #{tasks[0]['id']} Schema → done")

    # Tasks 1 + 2: API + Stripe (parallel, depend on schema)
    print(f"\n  Starting #{tasks[1]['id']} (API) and #{tasks[2]['id']} (Stripe) in parallel...")
    client.post(f"/tasks/{tasks[1]['id']}/status", json={"status": "in_progress"})
    client.post(f"/tasks/{tasks[2]['id']}/status", json={"status": "in_progress"})
    time.sleep(0.1)

    for tid in [tasks[1]['id'], tasks[2]['id']]:
        for s in ["in_review", "in_approval", "merging", "done"]:
            client.post(f"/tasks/{tid}/status", json={"status": s})
    print(f"  ✓ #{tasks[1]['id']} API → done")
    print(f"  ✓ #{tasks[2]['id']} Stripe → done")

    # Task 3: UI (depends on API + Stripe)
    print(f"\n  Starting #{tasks[3]['id']} (UI) — API and Stripe are done...")
    client.post(f"/tasks/{tasks[3]['id']}/status", json={"status": "in_progress"})
    time.sleep(0.1)
    for s in ["in_review", "in_approval", "merging", "done"]:
        client.post(f"/tasks/{tasks[3]['id']}/status", json={"status": s})
    print(f"  ✓ #{tasks[3]['id']} UI → done")

    # Task 4: E2E tests (depends on everything)
    print(f"\n  Starting #{tasks[4]['id']} (E2E Tests) — all deps satisfied...")
    client.post(f"/tasks/{tasks[4]['id']}/status", json={"status": "in_progress"})
    time.sleep(0.1)
    for s in ["in_review", "in_approval", "merging", "done"]:
        client.post(f"/tasks/{tasks[4]['id']}/status", json={"status": s})
    print(f"  ✓ #{tasks[4]['id']} E2E Tests → done")

    # ── Check costs ───────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("PHASE 5: Cost summary")
    print("═" * 60)

    costs = client.get(f"/teams/{team['id']}/costs").json()
    print(f"\n  Total cost (7d): ${costs.get('total_cost_usd', 0):.4f}")
    if costs.get("per_agent"):
        for a in costs["per_agent"]:
            print(f"    {a['agent_name']}: {a['sessions']} session(s) — ${a['cost_usd']:.4f}")

    # ── Check team settings ───────────────────────────────────────
    print("\n" + "═" * 60)
    print("PHASE 6: Team settings")
    print("═" * 60)

    settings = client.get(f"/settings/teams/{team['id']}").json()
    print(f"\n  Daily cost limit: ${settings.get('daily_cost_limit_usd', 'N/A')}")
    print(f"  Auto-merge: {settings.get('auto_merge', False)}")
    print(f"  Require review: {settings.get('require_review', True)}")

    # ── Final state ───────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("FINAL: All tasks complete")
    print("═" * 60)

    for t in tasks:
        final = client.get(f"/tasks/{t['id']}").json()
        assignee_name = "unassigned"
        if final.get("assignee_id"):
            for eng in ws["engineers"]:
                if eng["id"] == final["assignee_id"]:
                    assignee_name = eng["name"]
                    break
        events = client.get(f"/tasks/{t['id']}/events").json()
        print(f"  #{final['id']} [{final['status']}] {final['title']}")
        print(f"    → {assignee_name} | {len(events)} events")

    print(f"\n✓ Batch orchestration complete!")
    print(f"  - Created 5 tasks in a single batch request with DAG dependencies")
    print(f"  - 4 specialist agents executed tasks in dependency order")
    print(f"  - Work sessions tracked cost per agent")
    print(f"  - Full event trail preserved for every task")


if __name__ == "__main__":
    main()
