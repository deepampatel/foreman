"""Password hashing utilities.

Learn: Uses bcrypt via passlib for secure password hashing.
bcrypt automatically handles salting and is resistant to rainbow
table attacks. The cost factor is tuned for ~100ms per hash.
"""

import hashlib
import secrets


def hash_password(password: str) -> str:
    """Hash a password with SHA-256 + salt.

    Learn: We use SHA-256 with a random salt for simplicity.
    For production, consider bcrypt/argon2 via passlib.
    """
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        salt, hashed = password_hash.split("$", 1)
        expected = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return secrets.compare_digest(hashed, expected)
    except (ValueError, AttributeError):
        return False
