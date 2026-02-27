"""Password hashing utilities.

Learn: Uses bcrypt for secure password hashing. bcrypt automatically
handles salting and is resistant to rainbow table attacks.
The work factor (rounds=12) takes ~100ms per hash on modern hardware.

Legacy SHA-256 hashes are still verified for backward compatibility,
and auto-upgraded to bcrypt on successful login.
"""

import hashlib
import secrets

import bcrypt


def hash_password(password: str) -> str:
    """Hash a password with bcrypt.

    Learn: bcrypt includes a random salt automatically and produces
    hashes starting with "$2b$". The work factor defaults to 12
    (~100ms per hash on modern hardware). Passwords are truncated
    to 72 bytes (bcrypt's limit).
    """
    pw_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash.

    Supports both bcrypt ($2b$...) and legacy SHA-256 (salt$hash) formats.
    Use needs_upgrade() to check if a hash should be re-hashed.
    """
    if _is_legacy_hash(password_hash):
        return _verify_legacy(password, password_hash)
    try:
        pw_bytes = password.encode("utf-8")[:72]
        hash_bytes = password_hash.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except (ValueError, TypeError):
        return False


def needs_upgrade(password_hash: str) -> bool:
    """Check if a password hash should be upgraded to bcrypt."""
    return _is_legacy_hash(password_hash)


def _is_legacy_hash(password_hash: str) -> bool:
    """Detect legacy SHA-256 hashes (format: salt$hex_digest)."""
    return not password_hash.startswith("$2")


def _verify_legacy(password: str, password_hash: str) -> bool:
    """Verify a legacy SHA-256 salted hash."""
    try:
        salt, hashed = password_hash.split("$", 1)
        expected = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return secrets.compare_digest(hashed, expected)
    except (ValueError, AttributeError):
        return False
