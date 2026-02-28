#!/usr/bin/env python3
"""
Entourage Context Carryover Example.

Demonstrates how agents persist key findings between task turns so they
don't start cold on re-dispatch:

  1. Task A: Agent investigates a bug, saves root cause + key files
  2. Task B: Depends on Task A, loads saved context automatically
  3. Agent B starts warm — no need to re-investigate

Context is stored in task_metadata.context (JSONB) and injected into
the agent's prompt on dispatch.

Run with: python examples/context_carryover.py

Requires: pip install httpx
Backend must be running: http://localhost:8000
"""

from _common import setup_workspace


def main():
    # ── Setup ──────────────────────────────────────────────────
    ws = setup_workspace(
        "Context Demo",
        engineers=[{"name": "eng-1", "description": "Backend engineer"}],
    )
    client = ws["client"]
    team = ws["team"]
    engineer = ws["engineers"][0]

    # ── Task A: Investigation ──────────────────────────────────
    print("\n" + "═" * 60)
    print("TASK A: Investigate auth timeout bug")
    print("═" * 60)

    task_a = client.post(f"/teams/{team['id']}/tasks", json={
        "title": "Investigate auth timeout in production",
        "description": "Users report intermittent 504 errors on the /login endpoint",
        "priority": "critical",
        "task_type": "bug",
    }).json()

    client.post(f"/tasks/{task_a['id']}/assign", json={"assignee_id": engineer["id"]})
    client.post(f"/tasks/{task_a['id']}/status", json={"status": "in_progress"})

    print(f"\n  Task #{task_a['id']}: {task_a['title']}")
    print(f"  Assigned to: {engineer['name']}")

    # Agent investigates and saves findings via context API
    # (In production, the agent calls save_context via MCP tools)
    print("\n  Agent investigates...")
    print("  → Reads logs, traces requests, identifies root cause")

    # Save root cause
    resp = client.post(f"/tasks/{task_a['id']}/context", json={
        "key": "root_cause",
        "value": "Redis connection pool exhausted under load. "
                 "Pool size is 10, peak concurrent auth requests is 50+.",
    })
    saved = resp.json()
    print(f"\n  Saved context: {saved['key']}")
    print(f"    '{saved['value'][:60]}...'")

    # Save key files
    resp = client.post(f"/tasks/{task_a['id']}/context", json={
        "key": "key_files",
        "value": "auth/session.py (line 42: pool init), "
                 "config/redis.py (line 8: POOL_SIZE=10), "
                 "middleware/auth.py (line 15: session check)",
    })
    saved = resp.json()
    print(f"  Saved context: {saved['key']}")
    print(f"    '{saved['value'][:60]}...'")

    # Save architecture decision
    resp = client.post(f"/tasks/{task_a['id']}/context", json={
        "key": "fix_approach",
        "value": "Increase pool size to 100, add connection retry with backoff, "
                 "add pool exhaustion metric to Prometheus.",
    })
    saved = resp.json()
    print(f"  Saved context: {saved['key']}")
    print(f"    '{saved['value'][:60]}...'")

    # ── Verify: Read back all context ──────────────────────────
    print("\n" + "─" * 40)
    print("  Reading back all saved context:")
    print("─" * 40)

    resp = client.get(f"/tasks/{task_a['id']}/context")
    ctx = resp.json()
    print(f"\n  Task #{ctx['task_id']} has {len(ctx['context'])} context entries:")
    for key, value in ctx["context"].items():
        print(f"    • {key}: {value[:50]}...")

    # Complete Task A
    for status in ["in_review", "in_approval", "merging", "done"]:
        client.post(f"/tasks/{task_a['id']}/status", json={"status": status})
    print(f"\n  Task A completed ✓")

    # ── Task B: Fix based on investigation ─────────────────────
    print("\n" + "═" * 60)
    print("TASK B: Fix auth timeout (depends on investigation)")
    print("═" * 60)

    task_b = client.post(f"/teams/{team['id']}/tasks", json={
        "title": "Fix Redis pool exhaustion in auth",
        "description": "Increase pool size, add retry logic, add monitoring",
        "priority": "critical",
        "task_type": "bug",
    }).json()

    client.post(f"/tasks/{task_b['id']}/assign", json={"assignee_id": engineer["id"]})

    print(f"\n  Task #{task_b['id']}: {task_b['title']}")

    # Copy context from Task A to Task B
    # (In production, the manager or automation copies relevant context)
    print("\n  Copying context from Task A → Task B...")

    resp = client.get(f"/tasks/{task_a['id']}/context")
    source_ctx = resp.json()["context"]

    for key, value in source_ctx.items():
        client.post(f"/tasks/{task_b['id']}/context", json={
            "key": key,
            "value": value,
        })
        print(f"    Copied: {key}")

    # Verify Task B has the context
    resp = client.get(f"/tasks/{task_b['id']}/context")
    ctx_b = resp.json()
    print(f"\n  Task B now has {len(ctx_b['context'])} context entries.")

    client.post(f"/tasks/{task_b['id']}/status", json={"status": "in_progress"})

    # ── Show what the agent prompt looks like ──────────────────
    print("\n" + "═" * 60)
    print("HOW CONTEXT APPEARS IN THE AGENT PROMPT")
    print("═" * 60)

    print("""
  When the runner dispatches Task B to the engineer, the prompt
  includes a context section:

  ┌────────────────────────────────────────────────────┐
  │ ## Previous Context                                │
  │                                                    │
  │ The following findings were saved from prior work   │
  │ on this task. Use them to avoid re-investigation:  │
  │                                                    │
  │ **root_cause**: Redis connection pool exhausted    │
  │   under load. Pool size is 10, peak concurrent...  │
  │                                                    │
  │ **key_files**: auth/session.py (line 42: pool      │
  │   init), config/redis.py (line 8: POOL_SIZE=10)... │
  │                                                    │
  │ **fix_approach**: Increase pool size to 100, add   │
  │   connection retry with backoff, add pool...       │
  └────────────────────────────────────────────────────┘

  The agent starts warm — it knows the root cause, which files to
  edit, and the agreed-upon fix approach. No re-investigation needed.
""")

    # ── Task B: Agent updates context as it works ──────────────
    print("═" * 60)
    print("TASK B: Agent adds new context as it works")
    print("═" * 60)

    resp = client.post(f"/tasks/{task_b['id']}/context", json={
        "key": "changes_made",
        "value": "Increased POOL_SIZE to 100 in config/redis.py, "
                 "added retry_with_backoff() in auth/session.py, "
                 "added pool_connections_active gauge to metrics.py",
    })
    print(f"\n  Saved: changes_made")

    resp = client.post(f"/tasks/{task_b['id']}/context", json={
        "key": "test_results",
        "value": "Load test with 200 concurrent users: 0 timeouts (was 15%). "
                 "Pool utilization peaks at 60%. Retry triggered 3 times in 10min test.",
    })
    print(f"  Saved: test_results")

    # Final context state
    resp = client.get(f"/tasks/{task_b['id']}/context")
    final_ctx = resp.json()
    print(f"\n  Task B final context ({len(final_ctx['context'])} entries):")
    for key in final_ctx["context"]:
        print(f"    • {key}")

    # ── Context isolation check ────────────────────────────────
    print("\n" + "═" * 60)
    print("CONTEXT ISOLATION: Each task has its own context")
    print("═" * 60)

    ctx_a = client.get(f"/tasks/{task_a['id']}/context").json()
    ctx_b = client.get(f"/tasks/{task_b['id']}/context").json()

    print(f"\n  Task A: {len(ctx_a['context'])} entries (original investigation)")
    print(f"  Task B: {len(ctx_b['context'])} entries (investigation + fix details)")
    print(f"  Tasks don't leak context — each has its own namespace.")

    print(f"\n✓ Context carryover demo complete.")
    print(f"  Agents save findings → context persists → next dispatch starts warm.")


if __name__ == "__main__":
    main()
