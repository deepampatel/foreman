"""FastAPI auth dependencies.

Learn: These are used as Depends() in route handlers to extract
and validate the current user/key identity from the request.

Two auth mechanisms:
1. Bearer JWT token (for users)
2. API key in x-api-key header (for agents/CI)
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openclaw.auth.jwt import TokenError, verify_token
from openclaw.db.engine import get_db
from openclaw.db.models import ApiKey, User


class CurrentIdentity:
    """Represents the authenticated identity making the request.

    Learn: This is the unified auth context. Could be a user (JWT)
    or an API key (programmatic access). All downstream code uses
    this to scope queries by org_id.
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        identity_type: str = "user",  # "user" or "api_key"
    ):
        self.user_id = user_id
        self.org_id = org_id
        self.scopes = scopes or ["all"]
        self.identity_type = identity_type

    def has_scope(self, scope: str) -> bool:
        """Check if this identity has a given scope."""
        return "all" in self.scopes or scope in self.scopes


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[CurrentIdentity]:
    """Extract current identity (optional — returns None if no auth).

    Learn: This is the "soft" auth dependency. Used for endpoints that
    work both authenticated and unauthenticated. For mandatory auth,
    use get_current_user instead.
    """
    # Try API key first
    if x_api_key:
        return await _authenticate_api_key(x_api_key, db)

    # Try JWT Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        return _authenticate_jwt(token)

    return None


async def get_current_user(
    identity: Optional[CurrentIdentity] = Depends(get_current_user_optional),
) -> CurrentIdentity:
    """Extract current identity (required — 401 if no auth).

    Learn: This is the "hard" auth dependency. Used for endpoints
    that require authentication.
    """
    if not identity:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity


def _authenticate_jwt(token: str) -> CurrentIdentity:
    """Authenticate via JWT token."""
    try:
        payload = verify_token(token)
        return CurrentIdentity(
            user_id=payload["sub"],
            org_id=payload.get("org_id"),
            identity_type="user",
        )
    except TokenError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _authenticate_api_key(
    key: str, db: AsyncSession
) -> CurrentIdentity:
    """Authenticate via API key."""
    # Hash the key to compare
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    q = select(ApiKey).where(ApiKey.key_hash == key_hash)
    result = await db.execute(q)
    api_key = result.scalars().first()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check expiry
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="API key has expired")

    # Update last used
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    return CurrentIdentity(
        org_id=str(api_key.org_id),
        scopes=api_key.scopes or ["all"],
        identity_type="api_key",
    )
