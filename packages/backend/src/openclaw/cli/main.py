"""Entourage CLI — dispatch coding agents, track tasks, answer human requests.

Usage:
    entourage run "fix the login bug"           # Create task → assign → run agent
    entourage status                             # Agents, active tasks, pending requests
    entourage tasks                              # List tasks
    entourage requests                           # Pending human-in-the-loop requests
    entourage respond 42 "go with JWT"           # Answer a human request
    entourage costs                              # Cost summary
    entourage adapters                           # Show available adapters
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
import time
from typing import Optional

import click
import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_API_URL = "http://localhost:8000"


def _api_url() -> str:
    return os.environ.get("OPENCLAW_API_URL", DEFAULT_API_URL).rstrip("/")


def _client() -> httpx.AsyncClient:
    """Build an async HTTP client pointed at the Entourage backend."""
    return httpx.AsyncClient(base_url=_api_url(), timeout=30.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine from synchronous Click handler.

    Handles nested event loops (e.g. when invoked via Click CliRunner
    inside an existing async context like tests) by offloading to a thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — normal CLI invocation
        return asyncio.run(coro)
    else:
        # Already inside an event loop (e.g. test runner) — run in a thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()


def _team_id_from_ctx(team_id: Optional[str]) -> str:
    """Resolve team_id from flag or ENTOURAGE_TEAM_ID env var."""
    tid = team_id or os.environ.get("ENTOURAGE_TEAM_ID")
    if not tid:
        click.secho(
            "Error: --team-id required (or set ENTOURAGE_TEAM_ID env var)",
            fg="red",
            err=True,
        )
        sys.exit(1)
    return tid


def _pretty_json(data: dict | list) -> str:
    return json.dumps(data, indent=2, default=str)


def _print_table(rows: list[dict], columns: list[tuple[str, str, int]]):
    """Print a simple ASCII table.

    columns: list of (header, dict_key, width)
    """
    # Header
    header = "  ".join(h.ljust(w) for h, _, w in columns)
    click.secho(header, bold=True)
    click.echo("-" * len(header))
    # Rows
    for row in rows:
        line = "  ".join(str(row.get(k, "—"))[:w].ljust(w) for _, k, w in columns)
        click.echo(line)


def _status_color(status: str) -> str:
    """Map status strings to click colors."""
    colors = {
        "idle": "green",
        "working": "yellow",
        "busy": "yellow",
        "error": "red",
        "todo": "white",
        "in_progress": "yellow",
        "in_review": "cyan",
        "in_approval": "magenta",
        "merging": "blue",
        "done": "green",
        "cancelled": "red",
        "pending": "yellow",
        "resolved": "green",
        "expired": "red",
    }
    return colors.get(status, "white")


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(version="0.1.0", prog_name="entourage")
def main():
    """Entourage — dispatch coding agents and manage human-in-the-loop workflows."""


# ---------------------------------------------------------------------------
# entourage run
# ---------------------------------------------------------------------------


@main.command()
@click.argument("prompt")
@click.option("--team-id", "-t", help="Team UUID (or set ENTOURAGE_TEAM_ID)")
@click.option("--agent-id", "-a", help="Agent UUID (auto-picks idle engineer if omitted)")
@click.option("--adapter", help='Adapter override (e.g. "claude_code")')
@click.option("--no-poll", is_flag=True, help="Return immediately without polling")
def run(prompt: str, team_id: Optional[str], agent_id: Optional[str],
        adapter: Optional[str], no_poll: bool):
    """Create a task and dispatch a coding agent to work on it.

    PROMPT is what you want the agent to do (e.g. "fix the login bug").
    """
    _run(_run_impl(prompt, team_id, agent_id, adapter, no_poll))


async def _run_impl(prompt: str, team_id: Optional[str], agent_id: Optional[str],
                    adapter: Optional[str], no_poll: bool):
    tid = _team_id_from_ctx(team_id)

    async with _client() as c:
        # 1. Find an idle engineer agent (or use the one specified)
        if agent_id:
            aid = agent_id
            click.echo(f"Using agent {aid}")
        else:
            click.echo("Finding idle engineer agent...")
            r = await c.get(f"/api/v1/teams/{tid}/agents")
            r.raise_for_status()
            agents = r.json()
            idle = [a for a in agents if a["role"] == "engineer" and a["status"] == "idle"]
            if not idle:
                click.secho("No idle engineer agents found. Create one or wait.", fg="red")
                sys.exit(1)
            aid = idle[0]["id"]
            click.echo(f"Selected agent: {idle[0]['name']} ({aid})")

        # 2. Create task
        click.echo(f"Creating task: {prompt[:80]}...")
        r = await c.post(f"/api/v1/teams/{tid}/tasks", json={
            "title": prompt[:500],
            "description": prompt,
            "priority": "medium",
            "assignee_id": aid,
        })
        r.raise_for_status()
        task = r.json()
        task_id = task["id"]
        click.echo(f"Task #{task_id} created")

        # 3. Move task to in_progress
        r = await c.post(f"/api/v1/tasks/{task_id}/status", json={
            "status": "in_progress",
            "actor_id": aid,
        })
        r.raise_for_status()

        # 4. Dispatch agent run
        click.echo("Dispatching agent run...")
        body: dict = {"task_id": task_id}
        if adapter:
            body["adapter"] = adapter
        r = await c.post(f"/api/v1/agents/{aid}/run", json=body)
        r.raise_for_status()
        run_resp = r.json()
        click.secho(f"Agent dispatched: {run_resp['message']}", fg="green")

        if no_poll:
            click.echo(f"Task #{task_id} | Agent {aid}")
            return

        # 5. Poll task status
        click.echo()
        start = time.time()
        last_status = "in_progress"

        while True:
            await asyncio.sleep(5)
            elapsed = time.time() - start

            # Check task status
            r = await c.get(f"/api/v1/tasks/{task_id}")
            r.raise_for_status()
            task = r.json()
            status = task["status"]

            # Check for pending human requests
            r = await c.get(f"/api/v1/teams/{tid}/human-requests", params={
                "status": "pending",
                "task_id": task_id,
                "limit": 5,
            })
            r.raise_for_status()
            requests = r.json()

            # Status line
            status_str = click.style(status, fg=_status_color(status))
            elapsed_str = f"{elapsed:.0f}s"

            if requests:
                req_str = click.style(f" | {len(requests)} pending request(s)", fg="yellow")
            else:
                req_str = ""

            click.echo(f"\r  [{elapsed_str}] Task #{task_id}: {status_str}{req_str}    ", nl=False)

            if status != last_status:
                click.echo()  # newline on status change
                last_status = status

            # Terminal states
            if status in ("done", "cancelled", "in_review"):
                click.echo()
                break

            # Timeout after 35 minutes (slightly longer than agent timeout)
            if elapsed > 2100:
                click.echo()
                click.secho("Polling timed out (35 min). Agent may still be running.", fg="yellow")
                break

        # 6. Print summary
        click.echo()
        duration = time.time() - start
        click.secho("--- Run Summary ---", bold=True)
        click.echo(f"  Task:     #{task_id} — {task['title'][:60]}")
        click.echo(f"  Status:   {click.style(task['status'], fg=_status_color(task['status']))}")
        click.echo(f"  Agent:    {aid}")
        click.echo(f"  Duration: {duration:.0f}s")

        # Fetch cost info if available
        try:
            r = await c.get(f"/api/v1/agents/{aid}/sessions", params={
                "task_id": task_id, "limit": 1,
            })
            if r.status_code == 200:
                sessions = r.json()
                if sessions:
                    s = sessions[0]
                    cost = s.get("cost_usd", 0)
                    click.echo(f"  Cost:     ${cost:.4f}")
        except Exception:
            pass  # Cost display is best-effort

        # Show any pending human requests
        if requests:
            click.echo()
            click.secho("Pending human requests:", fg="yellow", bold=True)
            for req in requests:
                click.echo(f"  #{req['id']} [{req['kind']}]: {req['question'][:80]}")
            click.echo(f"\nRespond with: entourage respond <id> \"your answer\"")


# ---------------------------------------------------------------------------
# entourage status
# ---------------------------------------------------------------------------


@main.command()
@click.option("--team-id", "-t", help="Team UUID (or set ENTOURAGE_TEAM_ID)")
def status(team_id: Optional[str]):
    """Show team overview — agents, active tasks, and pending requests."""
    _run(_status_impl(team_id))


async def _status_impl(team_id: Optional[str]):
    tid = _team_id_from_ctx(team_id)

    async with _client() as c:
        # Fetch team detail (includes agents)
        r = await c.get(f"/api/v1/teams/{tid}")
        r.raise_for_status()
        team = r.json()

        click.secho(f"Team: {team['name']}", bold=True)
        click.echo()

        # Agents
        agents = team.get("agents", [])
        click.secho("Agents:", bold=True)
        if agents:
            for a in agents:
                status_str = click.style(a["status"], fg=_status_color(a["status"]))
                adapter = a.get("config", {}).get("adapter", "default")
                click.echo(f"  {a['name']:20s}  {a['role']:10s}  {status_str:20s}  adapter={adapter}")
        else:
            click.echo("  (none)")

        # Active tasks
        click.echo()
        click.secho("Active tasks:", bold=True)
        r = await c.get(f"/api/v1/teams/{tid}/tasks", params={"status": "in_progress", "limit": 20})
        r.raise_for_status()
        tasks = r.json()
        if tasks:
            for t in tasks:
                assignee = t.get("assignee_id", "unassigned")
                click.echo(f"  #{t['id']:5d}  {t['title'][:50]:50s}  → {str(assignee)[:8]}")
        else:
            click.echo("  (none)")

        # Pending human requests
        click.echo()
        click.secho("Pending human requests:", bold=True)
        r = await c.get(f"/api/v1/teams/{tid}/human-requests", params={"status": "pending", "limit": 10})
        r.raise_for_status()
        requests = r.json()
        if requests:
            for req in requests:
                kind_str = click.style(req["kind"], fg="cyan")
                click.echo(f"  #{req['id']:5d}  [{kind_str}]  {req['question'][:60]}")
            click.echo(f"\n  Respond with: entourage respond <id> \"your answer\"")
        else:
            click.echo("  (none)")


# ---------------------------------------------------------------------------
# entourage tasks
# ---------------------------------------------------------------------------


@main.command()
@click.option("--team-id", "-t", help="Team UUID (or set ENTOURAGE_TEAM_ID)")
@click.option("--status", "-s", "status_filter", help="Filter by status")
@click.option("--limit", "-l", default=50, help="Max results")
def tasks(team_id: Optional[str], status_filter: Optional[str], limit: int):
    """List tasks for the team."""
    _run(_tasks_impl(team_id, status_filter, limit))


async def _tasks_impl(team_id: Optional[str], status_filter: Optional[str], limit: int):
    tid = _team_id_from_ctx(team_id)

    async with _client() as c:
        params: dict = {"limit": limit}
        if status_filter:
            params["status"] = status_filter

        r = await c.get(f"/api/v1/teams/{tid}/tasks", params=params)
        r.raise_for_status()
        tasks = r.json()

        if not tasks:
            click.echo("No tasks found.")
            return

        click.secho(f"Tasks ({len(tasks)}):", bold=True)
        click.echo()
        _print_table(tasks, [
            ("ID", "id", 6),
            ("Status", "status", 14),
            ("Priority", "priority", 10),
            ("Title", "title", 60),
        ])


# ---------------------------------------------------------------------------
# entourage requests
# ---------------------------------------------------------------------------


@main.command()
@click.option("--team-id", "-t", help="Team UUID (or set ENTOURAGE_TEAM_ID)")
@click.option("--all", "show_all", is_flag=True, help="Show resolved/expired too")
def requests(team_id: Optional[str], show_all: bool):
    """List human-in-the-loop requests."""
    _run(_requests_impl(team_id, show_all))


async def _requests_impl(team_id: Optional[str], show_all: bool):
    tid = _team_id_from_ctx(team_id)

    async with _client() as c:
        params: dict = {"limit": 50}
        if not show_all:
            params["status"] = "pending"

        r = await c.get(f"/api/v1/teams/{tid}/human-requests", params=params)
        r.raise_for_status()
        reqs = r.json()

        if not reqs:
            click.echo("No pending requests." if not show_all else "No requests found.")
            return

        click.secho(f"Human requests ({len(reqs)}):", bold=True)
        click.echo()
        for req in reqs:
            status_str = click.style(req["status"], fg=_status_color(req["status"]))
            kind_str = click.style(req["kind"], fg="cyan")
            task_str = f" (task #{req['task_id']})" if req.get("task_id") else ""

            click.echo(f"  #{req['id']}  {status_str}  [{kind_str}]{task_str}")
            click.echo(f"    {req['question']}")
            if req.get("options"):
                click.echo(f"    Options: {', '.join(req['options'])}")
            if req.get("response"):
                click.echo(f"    Response: {req['response']}")
            click.echo()


# ---------------------------------------------------------------------------
# entourage respond
# ---------------------------------------------------------------------------


@main.command()
@click.argument("request_id", type=int)
@click.argument("response")
@click.option("--user-id", "-u", help="Your user UUID (optional)")
def respond(request_id: int, response: str, user_id: Optional[str]):
    """Respond to a human-in-the-loop request.

    REQUEST_ID is the request number. RESPONSE is your answer.
    """
    _run(_respond_impl(request_id, response, user_id))


async def _respond_impl(request_id: int, response: str, user_id: Optional[str]):
    async with _client() as c:
        body: dict = {"response": response}
        if user_id:
            body["responded_by"] = user_id

        r = await c.post(f"/api/v1/human-requests/{request_id}/respond", json=body)

        if r.status_code == 404:
            click.secho(f"Request #{request_id} not found.", fg="red")
            sys.exit(1)
        elif r.status_code == 409:
            click.secho(f"Request #{request_id} already resolved.", fg="yellow")
            sys.exit(1)

        r.raise_for_status()
        req = r.json()
        click.secho(f"Responded to #{request_id}: {response}", fg="green")
        if req.get("task_id"):
            click.echo(f"  Related task: #{req['task_id']}")


# ---------------------------------------------------------------------------
# entourage costs
# ---------------------------------------------------------------------------


@main.command()
@click.option("--team-id", "-t", help="Team UUID (or set ENTOURAGE_TEAM_ID)")
@click.option("--days", "-d", default=7, help="Lookback period in days (default: 7)")
def costs(team_id: Optional[str], days: int):
    """Show cost summary for the team."""
    _run(_costs_impl(team_id, days))


async def _costs_impl(team_id: Optional[str], days: int):
    tid = _team_id_from_ctx(team_id)

    async with _client() as c:
        r = await c.get(f"/api/v1/teams/{tid}/costs", params={"days": days})
        r.raise_for_status()
        summary = r.json()

        click.secho(f"Cost Summary (last {summary['period_days']} days)", bold=True)
        click.echo()
        click.echo(f"  Total cost:     ${summary['total_cost_usd']:.4f}")
        click.echo(f"  Sessions:       {summary['session_count']}")
        click.echo(f"  Tokens in:      {summary['total_tokens_in']:,}")
        click.echo(f"  Tokens out:     {summary['total_tokens_out']:,}")

        # Per-agent breakdown
        per_agent = summary.get("per_agent", [])
        if per_agent:
            click.echo()
            click.secho("  Per agent:", bold=True)
            for a in per_agent:
                name = a.get("agent_name", a["agent_id"][:8])
                click.echo(f"    {name:20s}  ${a['cost_usd']:.4f}  ({a['sessions']} sessions)")

        # Per-model breakdown
        per_model = summary.get("per_model", [])
        if per_model:
            click.echo()
            click.secho("  Per model:", bold=True)
            for m in per_model:
                model = m.get("model") or "unknown"
                click.echo(f"    {model:30s}  ${m['cost_usd']:.4f}  ({m['sessions']} sessions)")


# ---------------------------------------------------------------------------
# entourage adapters
# ---------------------------------------------------------------------------


@main.command()
def adapters():
    """List available agent adapters."""
    # Import locally to avoid circular deps and keep CLI fast for other commands
    try:
        from openclaw.agent.adapters import list_adapters, get_adapter

        available = list_adapters()
        click.secho("Available adapters:", bold=True)
        click.echo()

        for name in sorted(available):
            adapter = get_adapter(name)
            ok, msg = adapter.validate_environment()
            if ok:
                status_str = click.style("ready", fg="green")
            else:
                status_str = click.style(f"not ready — {msg}", fg="red")
            click.echo(f"  {name:20s}  {status_str}")

    except ImportError:
        click.secho("Could not import adapter registry. Is openclaw installed?", fg="red")
        sys.exit(1)


# ---------------------------------------------------------------------------
# entourage agents
# ---------------------------------------------------------------------------


@main.command()
@click.option("--team-id", "-t", help="Team UUID (or set ENTOURAGE_TEAM_ID)")
def agents(team_id: Optional[str]):
    """List agents in the team."""
    _run(_agents_impl(team_id))


async def _agents_impl(team_id: Optional[str]):
    tid = _team_id_from_ctx(team_id)

    async with _client() as c:
        r = await c.get(f"/api/v1/teams/{tid}/agents")
        r.raise_for_status()
        agents = r.json()

        if not agents:
            click.echo("No agents found.")
            return

        click.secho(f"Agents ({len(agents)}):", bold=True)
        click.echo()
        for a in agents:
            status_str = click.style(a["status"], fg=_status_color(a["status"]))
            adapter = a.get("config", {}).get("adapter", "—")
            click.echo(
                f"  {a['id'][:8]}  {a['name']:20s}  {a['role']:10s}  "
                f"{status_str:20s}  model={a.get('model', '—')}  adapter={adapter}"
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
