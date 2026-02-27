"""Auth API — registration, login, API key management.

Learn: Routes for user authentication and API key lifecycle:
- POST /auth/register → create a new user account
- POST /auth/login → email/password → JWT tokens
- POST /auth/refresh → refresh token → new access token
- GET /auth/me → current user info
- POST /orgs/:id/api-keys → create API key (returns key once!)
- GET /orgs/:id/api-keys → list API keys
- DELETE /api-keys/:id → revoke an API key
"""

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.auth.dependencies import CurrentIdentity, get_current_user
from openclaw.auth.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    verify_token,
)
from openclaw.auth.password import hash_password, needs_upgrade, verify_password
from openclaw.db.engine import get_db
from openclaw.db.models import ApiKey, User

router = APIRouter(prefix="/auth")


# ─── Schemas ─────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["all"])
    expires_days: Optional[int] = Field(None, description="Expire in N days (None = never)")


class ApiKeyCreated(BaseModel):
    """Response for API key creation — key is only shown ONCE."""
    id: uuid.UUID
    name: str
    key: str  # Full key — only returned on creation
    prefix: str
    scopes: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyRead(BaseModel):
    """API key info (without the actual key)."""
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: Optional[datetime] = None
    created_at: datetime
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Register ────────────────────────────────────────────


@router.post("/register", response_model=UserRead, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user account."""
    # Check email uniqueness
    q = select(User).where(User.email == body.email)
    result = await db.execute(q)
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ─── Login ───────────────────────────────────────────────


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email and password → JWT tokens."""
    q = select(User).where(User.email == body.email)
    result = await db.execute(q)
    user = result.scalars().first()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Auto-upgrade legacy SHA-256 hashes to bcrypt on successful login
    if needs_upgrade(user.password_hash):
        user.password_hash = hash_password(body.password)
        await db.commit()

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


# ─── Refresh ────────────────────────────────────────────


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    """Exchange a refresh token for a new access token."""
    try:
        payload = verify_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Not a refresh token")

        access_token = create_access_token(payload["sub"])
        refresh_token = create_refresh_token(payload["sub"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )
    except TokenError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ─── Current user ───────────────────────────────────────


@router.get("/me")
async def get_me(
    identity: CurrentIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current authenticated user's info."""
    if identity.identity_type == "api_key":
        return {
            "type": "api_key",
            "org_id": identity.org_id,
            "scopes": identity.scopes,
        }

    user = await db.get(User, uuid.UUID(identity.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "type": "user",
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
    }


# ─── API Key management ─────────────────────────────────


@router.post("/orgs/{org_id}/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    org_id: str,
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. The full key is only returned ONCE."""
    # Generate the key: oc_ prefix + random bytes
    raw_key = f"oc_{secrets.token_urlsafe(32)}"
    prefix = raw_key[:10]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    from datetime import timedelta, timezone
    expires_at = None
    if body.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    api_key = ApiKey(
        org_id=uuid.UUID(org_id),
        name=body.name,
        key_hash=key_hash,
        prefix=prefix,
        scopes=body.scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,  # Only time the full key is returned!
        "prefix": api_key.prefix,
        "scopes": api_key.scopes,
        "created_at": api_key.created_at,
    }


@router.get("/orgs/{org_id}/api-keys", response_model=list[ApiKeyRead])
async def list_api_keys(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List API keys for an org (without the actual key values)."""
    q = (
        select(ApiKey)
        .where(ApiKey.org_id == uuid.UUID(org_id))
        .order_by(ApiKey.created_at.desc())
    )
    result = await db.execute(q)
    keys = result.scalars().all()

    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "scopes": k.scopes,
            "last_used_at": k.last_used_at,
            "created_at": k.created_at,
            "expires_at": k.expires_at,
        }
        for k in keys
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Revoke (delete) an API key."""
    api_key = await db.get(ApiKey, uuid.UUID(key_id))
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    await db.delete(api_key)
    await db.commit()
    return {"deleted": True}
