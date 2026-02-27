"""Settings API — team and organization configuration.

Learn: Settings use the existing JSONB config columns on teams/orgs.
No new tables needed — we leverage the flexible JSONB for settings.

Team settings include:
- Budget limits (daily, per-task)
- Default agent model
- Notification preferences
- Git workflow settings (branch naming, auto-merge)
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.db.engine import get_db
from openclaw.db.models import Organization, Team
from openclaw.events.store import EventStore
from openclaw.events.types import SETTINGS_UPDATED

router = APIRouter(prefix="/settings")


# ─── Schemas ─────────────────────────────────────────────


class TeamSettings(BaseModel):
    """Team-level configuration stored in teams.config JSONB."""
    daily_cost_limit_usd: Optional[float] = Field(
        None, description="Daily cost limit for all agents in the team"
    )
    task_cost_limit_usd: Optional[float] = Field(
        None, description="Per-task cost limit"
    )
    default_model: Optional[str] = Field(
        None, description="Default model for new agent sessions"
    )
    auto_merge: Optional[bool] = Field(
        None, description="Auto-merge after approval"
    )
    branch_prefix: Optional[str] = Field(
        None, description="Branch naming prefix (e.g. 'openclaw/')"
    )
    require_review: Optional[bool] = Field(
        None, description="Require review before merge"
    )
    notifications: Optional[dict] = Field(
        None, description="Notification preferences"
    )


class ConventionCreate(BaseModel):
    """A team convention — coding standard, architecture decision, etc."""
    key: str = Field(..., description="Convention identifier (e.g. 'testing', 'code_style')")
    content: str = Field(..., description="The convention text")
    active: bool = Field(True, description="Whether the convention is active")


class ConventionUpdate(BaseModel):
    content: Optional[str] = None
    active: Optional[bool] = None


class ConventionRead(BaseModel):
    key: str
    content: str
    active: bool


class OrgSettings(BaseModel):
    """Organization-level configuration."""
    billing_email: Optional[str] = None
    global_cost_limit_usd: Optional[float] = None
    allowed_models: Optional[list[str]] = None


class TeamSettingsRead(BaseModel):
    team_id: uuid.UUID
    team_name: str
    settings: dict

    model_config = {"from_attributes": True}


class OrgSettingsRead(BaseModel):
    org_id: uuid.UUID
    org_name: str
    settings: dict

    model_config = {"from_attributes": True}


# ─── Team settings ────────────────────────────────────────


@router.get("/teams/{team_id}", response_model=TeamSettingsRead)
async def get_team_settings(
    team_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get team configuration."""
    team = await db.get(Team, uuid.UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    return {
        "team_id": team.id,
        "team_name": team.name,
        "settings": team.config or {},
    }


@router.patch("/teams/{team_id}", response_model=TeamSettingsRead)
async def update_team_settings(
    team_id: str,
    body: TeamSettings,
    db: AsyncSession = Depends(get_db),
):
    """Update team configuration. Only provided fields are changed."""
    team = await db.get(Team, uuid.UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Merge new settings into existing config
    current = dict(team.config or {})
    updates = body.model_dump(exclude_none=True)
    current.update(updates)
    team.config = current

    await db.commit()
    await db.refresh(team)

    # Record the change
    events = EventStore(db)
    await events.append(
        stream_id=f"team:{team_id}",
        event_type=SETTINGS_UPDATED,
        data={"team_id": team_id, "changes": updates},
    )

    return {
        "team_id": team.id,
        "team_name": team.name,
        "settings": team.config or {},
    }


# ─── Org settings ─────────────────────────────────────────


@router.get("/orgs/{org_id}", response_model=OrgSettingsRead)
async def get_org_settings(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get organization settings."""
    org = await db.get(Organization, uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Org doesn't have a config column yet — we can use a pattern
    # where we store org-level settings elsewhere or add it later.
    # For now, return empty settings.
    return {
        "org_id": org.id,
        "org_name": org.name,
        "settings": {},
    }


# ─── Team conventions ────────────────────────────────────


@router.get(
    "/teams/{team_id}/conventions",
    response_model=list[ConventionRead],
)
async def list_conventions(
    team_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List team coding conventions."""
    team = await db.get(Team, uuid.UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    conventions = (team.config or {}).get("conventions", [])
    return conventions


@router.post(
    "/teams/{team_id}/conventions",
    response_model=ConventionRead,
    status_code=201,
)
async def create_convention(
    team_id: str,
    body: ConventionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new team convention."""
    team = await db.get(Team, uuid.UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    config = dict(team.config or {})
    conventions = list(config.get("conventions", []))

    # Check for duplicate key
    if any(c["key"] == body.key for c in conventions):
        raise HTTPException(
            status_code=409,
            detail=f"Convention with key '{body.key}' already exists",
        )

    convention = {"key": body.key, "content": body.content, "active": body.active}
    conventions.append(convention)
    config["conventions"] = conventions
    team.config = config

    await db.commit()
    await db.refresh(team)

    events = EventStore(db)
    await events.append(
        stream_id=f"team:{team_id}",
        event_type=SETTINGS_UPDATED,
        data={
            "team_id": team_id,
            "changes": {"convention_added": body.key},
        },
    )

    return convention


@router.put(
    "/teams/{team_id}/conventions/{key}",
    response_model=ConventionRead,
)
async def update_convention(
    team_id: str,
    key: str,
    body: ConventionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a team convention by key."""
    team = await db.get(Team, uuid.UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    config = dict(team.config or {})
    conventions = list(config.get("conventions", []))

    for i, c in enumerate(conventions):
        if c["key"] == key:
            if body.content is not None:
                conventions[i]["content"] = body.content
            if body.active is not None:
                conventions[i]["active"] = body.active
            config["conventions"] = conventions
            team.config = config
            await db.commit()
            await db.refresh(team)

            events = EventStore(db)
            await events.append(
                stream_id=f"team:{team_id}",
                event_type=SETTINGS_UPDATED,
                data={
                    "team_id": team_id,
                    "changes": {"convention_updated": key},
                },
            )

            return conventions[i]

    raise HTTPException(status_code=404, detail=f"Convention '{key}' not found")


@router.delete("/teams/{team_id}/conventions/{key}")
async def delete_convention(
    team_id: str,
    key: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a team convention by key."""
    team = await db.get(Team, uuid.UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    config = dict(team.config or {})
    conventions = list(config.get("conventions", []))

    original_len = len(conventions)
    conventions = [c for c in conventions if c["key"] != key]

    if len(conventions) == original_len:
        raise HTTPException(status_code=404, detail=f"Convention '{key}' not found")

    config["conventions"] = conventions
    team.config = config
    await db.commit()
    await db.refresh(team)

    events = EventStore(db)
    await events.append(
        stream_id=f"team:{team_id}",
        event_type=SETTINGS_UPDATED,
        data={
            "team_id": team_id,
            "changes": {"convention_deleted": key},
        },
    )

    return {"deleted": True, "key": key}
