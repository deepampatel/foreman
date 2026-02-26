"""Phase 1 API tests — Organizations, Teams, Agents, Repos.

Learn: Each test creates its own data via the API and verifies the response.
Thanks to the rollback-per-test fixture in conftest.py, tests are isolated.

Pattern: test_<verb>_<noun>_<scenario>
"""

import pytest


# ═══════════════════════════════════════════════════════════
# Organizations
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_org(client):
    """POST /api/v1/orgs should create an organization."""
    resp = await client.post("/api/v1/orgs", json={"name": "Acme Corp", "slug": "acme"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_org_validates_slug(client):
    """Slug must be lowercase alphanumeric with hyphens only."""
    resp = await client.post("/api/v1/orgs", json={"name": "Bad", "slug": "Bad Slug!"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_orgs(client):
    """GET /api/v1/orgs should return all organizations."""
    # Create two orgs
    await client.post("/api/v1/orgs", json={"name": "Alpha", "slug": "alpha"})
    await client.post("/api/v1/orgs", json={"name": "Beta", "slug": "beta"})

    resp = await client.get("/api/v1/orgs")
    assert resp.status_code == 200
    orgs = resp.json()
    slugs = [o["slug"] for o in orgs]
    assert "alpha" in slugs
    assert "beta" in slugs


# ═══════════════════════════════════════════════════════════
# Teams
# ═══════════════════════════════════════════════════════════


@pytest.fixture
async def org(client):
    """Create an org and return its data."""
    resp = await client.post("/api/v1/orgs", json={"name": "Test Org", "slug": "test-org"})
    return resp.json()


@pytest.mark.asyncio
async def test_create_team(client, org):
    """POST /orgs/:id/teams should create a team with a default manager agent."""
    resp = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Backend Team", "slug": "backend"},
    )
    assert resp.status_code == 201
    team = resp.json()
    assert team["name"] == "Backend Team"
    assert team["slug"] == "backend"
    assert team["org_id"] == org["id"]


@pytest.mark.asyncio
async def test_create_team_auto_provisions_manager(client, org):
    """Creating a team should auto-create a 'manager' agent."""
    resp = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "AI Team", "slug": "ai-team"},
    )
    team = resp.json()

    # List agents — should have the auto-created manager
    agents_resp = await client.get(f"/api/v1/teams/{team['id']}/agents")
    assert agents_resp.status_code == 200
    agents = agents_resp.json()
    assert len(agents) == 1
    assert agents[0]["name"] == "manager"
    assert agents[0]["role"] == "manager"


@pytest.mark.asyncio
async def test_list_teams(client, org):
    """GET /orgs/:id/teams should return all teams for an org."""
    await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Team A", "slug": "team-a"},
    )
    await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Team B", "slug": "team-b"},
    )

    resp = await client.get(f"/api/v1/orgs/{org['id']}/teams")
    assert resp.status_code == 200
    teams = resp.json()
    slugs = [t["slug"] for t in teams]
    assert "team-a" in slugs
    assert "team-b" in slugs


@pytest.mark.asyncio
async def test_get_team_detail(client, org):
    """GET /teams/:id should return team with nested agents and repos."""
    # Create team
    team_resp = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Detail Team", "slug": "detail-team"},
    )
    team = team_resp.json()

    # Add an engineer agent
    await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": "coder", "role": "engineer"},
    )

    # Register a repo
    await client.post(
        f"/api/v1/teams/{team['id']}/repos",
        json={"name": "my-app", "local_path": "/home/dev/my-app"},
    )

    # Get team detail
    resp = await client.get(f"/api/v1/teams/{team['id']}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["name"] == "Detail Team"
    assert len(detail["agents"]) == 2  # manager + coder
    assert len(detail["repositories"]) == 1
    assert detail["repositories"][0]["name"] == "my-app"


@pytest.mark.asyncio
async def test_get_team_404(client):
    """GET /teams/:id for a non-existent team should return 404."""
    resp = await client.get("/api/v1/teams/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════
# Agents
# ═══════════════════════════════════════════════════════════


@pytest.fixture
async def team(client, org):
    """Create a team and return its data."""
    resp = await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Agent Test Team", "slug": "agent-test"},
    )
    return resp.json()


@pytest.mark.asyncio
async def test_create_agent(client, team):
    """POST /teams/:id/agents should create an agent."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": "reviewer-1", "role": "reviewer", "model": "claude-sonnet-4-20250514"},
    )
    assert resp.status_code == 201
    agent = resp.json()
    assert agent["name"] == "reviewer-1"
    assert agent["role"] == "reviewer"
    assert agent["status"] == "idle"
    assert agent["team_id"] == team["id"]


@pytest.mark.asyncio
async def test_create_agent_defaults(client, team):
    """Agent should default to engineer role and Claude Sonnet model."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": "worker"},
    )
    assert resp.status_code == 201
    agent = resp.json()
    assert agent["role"] == "engineer"
    assert "claude-sonnet" in agent["model"]


@pytest.mark.asyncio
async def test_create_agent_invalid_role(client, team):
    """Agent role must be one of: manager, engineer, reviewer."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": "bad", "role": "hacker"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_agents(client, team):
    """GET /teams/:id/agents should include auto-created manager + new agents."""
    await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": "eng-1", "role": "engineer"},
    )
    await client.post(
        f"/api/v1/teams/{team['id']}/agents",
        json={"name": "eng-2", "role": "engineer"},
    )

    resp = await client.get(f"/api/v1/teams/{team['id']}/agents")
    assert resp.status_code == 200
    agents = resp.json()
    # manager (auto-created) + eng-1 + eng-2
    assert len(agents) == 3
    names = [a["name"] for a in agents]
    assert "manager" in names
    assert "eng-1" in names
    assert "eng-2" in names


# ═══════════════════════════════════════════════════════════
# Repositories
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_register_repo(client, team):
    """POST /teams/:id/repos should register a repository."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/repos",
        json={
            "name": "frontend",
            "local_path": "/home/dev/frontend",
            "default_branch": "develop",
            "config": {"test_cmd": "npm test"},
        },
    )
    assert resp.status_code == 201
    repo = resp.json()
    assert repo["name"] == "frontend"
    assert repo["local_path"] == "/home/dev/frontend"
    assert repo["default_branch"] == "develop"
    assert repo["config"]["test_cmd"] == "npm test"
    assert repo["team_id"] == team["id"]


@pytest.mark.asyncio
async def test_register_repo_defaults(client, team):
    """Repo default_branch should default to 'main'."""
    resp = await client.post(
        f"/api/v1/teams/{team['id']}/repos",
        json={"name": "backend", "local_path": "/home/dev/backend"},
    )
    assert resp.status_code == 201
    assert resp.json()["default_branch"] == "main"


@pytest.mark.asyncio
async def test_list_repos(client, team):
    """GET /teams/:id/repos should list all repos for a team."""
    await client.post(
        f"/api/v1/teams/{team['id']}/repos",
        json={"name": "repo-a", "local_path": "/a"},
    )
    await client.post(
        f"/api/v1/teams/{team['id']}/repos",
        json={"name": "repo-b", "local_path": "/b"},
    )

    resp = await client.get(f"/api/v1/teams/{team['id']}/repos")
    assert resp.status_code == 200
    repos = resp.json()
    assert len(repos) == 2
    names = [r["name"] for r in repos]
    assert "repo-a" in names
    assert "repo-b" in names


# ═══════════════════════════════════════════════════════════
# Event sourcing verification
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_team_creation_emits_events(client, org, db_session):
    """Creating a team should emit team.created and agent.created events."""
    from sqlalchemy import select
    from openclaw.db.models import Event

    await client.post(
        f"/api/v1/orgs/{org['id']}/teams",
        json={"name": "Events Team", "slug": "events-team"},
    )

    # Query events directly from the test session
    result = await db_session.execute(
        select(Event).order_by(Event.id)
    )
    events = list(result.scalars().all())

    # Should have at least team.created and agent.created
    event_types = [e.type for e in events]
    assert "team.created" in event_types
    assert "agent.created" in event_types

    # Verify event data
    team_event = next(e for e in events if e.type == "team.created")
    assert team_event.data["name"] == "Events Team"
    assert team_event.data["slug"] == "events-team"
    assert team_event.stream_id.startswith("team:")
