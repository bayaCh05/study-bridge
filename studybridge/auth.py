"""Password hashing.

Session handling, login/logout endpoints, and the require_roles() guard are
added in Step 2. This file only has what seed.py needs right now: turning a
plain-text demo password into a (hash, salt) pair the same way real user
signup will.
"""

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 200_000


def hash_password(password):
    """Return (password_hash_hex, salt_hex) for a new password."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password, password_hash_hex, salt_hex):
    """Check a plain-text password against a stored hash, in constant time."""
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), password_hash_hex)
