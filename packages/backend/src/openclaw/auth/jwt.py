"""JWT token creation and verification.

Learn: JWT (JSON Web Token) provides stateless authentication.
- Access token: short-lived (60min), used for API calls
- Refresh token: long-lived (30 days), used to get new access tokens

The token contains the user_id and org_id for row-level scoping.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from openclaw.config import settings


class TokenError(Exception):
    """Raised when token creation/verification fails."""


def create_access_token(
    user_id: str,
    org_id: Optional[str] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """Create a JWT access token."""
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    if org_id:
        payload["org_id"] = org_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: str,
    expires_days: Optional[int] = None,
) -> str:
    """Create a JWT refresh token."""
    expires = datetime.now(timezone.utc) + timedelta(
        days=expires_days or settings.refresh_token_expire_days
    )
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token.

    Returns the payload dict on success.
    Raises TokenError on failure.
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise TokenError(f"Invalid token: {e}")
