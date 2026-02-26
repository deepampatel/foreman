"""Authentication and authorization.

Learn: Phase 9 adds JWT-based user auth and API key auth for agents.
Two authentication paths:
1. Users → email/password → JWT access/refresh tokens
2. Agents/CI → API key in Authorization header

Both resolve to a "current identity" for row-level scoping.
"""
