"""Team service — business logic for teams, agents, and repos.

Learn: Service layer separates business logic from HTTP routing.
API routes call services, services call the database.
This makes the code testable (test services without HTTP)
and reusable (MCP tools and API routes share the same logic).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from openclaw.db.models import Agent, Organization, Repository, Team
from openclaw.events.store import EventStore
from openclaw.events.types import AGENT_CREATED, REPO_REGISTERED, TEAM_CREATED


class TeamService:
    """Business logic for team management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.events = EventStore(db)

    # ─── Organizations ──────────────────────────────────

    async def create_org(self, name: str, slug: str) -> Organization:
        org = Organization(name=name, slug=slug)
        self.db.add(org)
        await self.db.flush()
        return org

    async def list_orgs(self) -> list[Organization]:
        result = await self.db.execute(
            select(Organization).order_by(Organization.name)
        )
        return list(result.scalars().all())

    # ─── Teams ──────────────────────────────────────────

    async def create_team(
        self, org_id: uuid.UUID, name: str, slug: str
    ) -> Team:
        """Create a team and auto-provision a default manager agent.

        Learn: This is a key UX pattern — when you create a team,
        it should be immediately usable. The manager agent coordinates
        work and decomposes tasks for engineer agents.
        """
        team = Team(org_id=org_id, name=name, slug=slug)
        self.db.add(team)
        await self.db.flush()

        # Auto-create manager agent
        manager = Agent(
            team_id=team.id,
            name="manager",
            role="manager",
            model="claude-sonnet-4-20250514",
            config={"description": "Team manager — decomposes tasks and coordinates work"},
        )
        self.db.add(manager)
        await self.db.flush()

        # Record events
        await self.events.append(
            stream_id=f"team:{team.id}",
            event_type=TEAM_CREATED,
            data={"name": name, "slug": slug, "org_id": str(org_id)},
        )
        await self.events.append(
            stream_id=f"agent:{manager.id}",
            event_type=AGENT_CREATED,
            data={
                "name": "manager",
                "role": "manager",
                "team_id": str(team.id),
                "auto_created": True,
            },
        )

        await self.db.commit()
        return team

    async def list_teams(self, org_id: uuid.UUID) -> list[Team]:
        result = await self.db.execute(
            select(Team).where(Team.org_id == org_id).order_by(Team.name)
        )
        return list(result.scalars().all())

    async def get_team(self, team_id: uuid.UUID) -> Team | None:
        result = await self.db.execute(
            select(Team)
            .where(Team.id == team_id)
            .options(
                selectinload(Team.agents),
                selectinload(Team.repositories),
            )
        )
        return result.scalars().first()

    # ─── Agents ─────────────────────────────────────────

    async def create_agent(
        self,
        team_id: uuid.UUID,
        name: str,
        role: str = "engineer",
        model: str = "claude-sonnet-4-20250514",
        config: dict | None = None,
    ) -> Agent:
        agent = Agent(
            team_id=team_id,
            name=name,
            role=role,
            model=model,
            config=config or {},
        )
        self.db.add(agent)
        await self.db.flush()

        await self.events.append(
            stream_id=f"agent:{agent.id}",
            event_type=AGENT_CREATED,
            data={
                "name": name,
                "role": role,
                "model": model,
                "team_id": str(team_id),
            },
        )

        await self.db.commit()
        return agent

    async def list_agents(self, team_id: uuid.UUID) -> list[Agent]:
        result = await self.db.execute(
            select(Agent).where(Agent.team_id == team_id).order_by(Agent.name)
        )
        return list(result.scalars().all())

    async def get_agent(self, agent_id: uuid.UUID) -> Agent | None:
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalars().first()

    # ─── Repositories ───────────────────────────────────

    async def register_repo(
        self,
        team_id: uuid.UUID,
        name: str,
        local_path: str,
        default_branch: str = "main",
        config: dict | None = None,
    ) -> Repository:
        repo = Repository(
            team_id=team_id,
            name=name,
            local_path=local_path,
            default_branch=default_branch,
            config=config or {},
        )
        self.db.add(repo)
        await self.db.flush()

        await self.events.append(
            stream_id=f"repo:{repo.id}",
            event_type=REPO_REGISTERED,
            data={
                "name": name,
                "local_path": local_path,
                "team_id": str(team_id),
            },
        )

        await self.db.commit()
        return repo

    async def list_repos(self, team_id: uuid.UUID) -> list[Repository]:
        result = await self.db.execute(
            select(Repository)
            .where(Repository.team_id == team_id)
            .order_by(Repository.name)
        )
        return list(result.scalars().all())
