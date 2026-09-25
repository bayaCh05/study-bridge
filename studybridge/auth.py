"""Password hashing, sessions, and the require_roles() access guard."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from http.cookies import SimpleCookie

from studybridge import config, timeutil

PBKDF2_ITERATIONS = 200_000
SESSION_COOKIE_NAME = "session_token"


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


# --- Sessions -----------------------------------------------------------
#
# HTTP itself has no memory: every request is a fresh connection with no
# idea who sent the last one. A session bridges that gap — after login we
# hand the browser a random, unguessable token; the browser stores it as a
# cookie and resends it automatically on every later request; we look it up
# in the `sessions` table to find out who's asking.


def create_session(conn, user_id):
    """Insert a new session row and return (token, expires_at)."""
    token = secrets.token_hex(32)
    created_at = timeutil.now()
    expires_at = created_at + timedelta(hours=config.SESSION_LIFETIME_HOURS)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, created_at.isoformat(), expires_at.isoformat()),
    )
    conn.commit()
    return token, expires_at


def get_user_for_token(conn, token):
    """Return the user row for a valid, non-expired, active session token."""
    if not token:
        return None
    row = conn.execute(
        """
        SELECT users.id, users.full_name, users.email, users.role, users.is_active,
               sessions.expires_at
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        """,
        (token,),
    ).fetchone()
    if row is None or not row["is_active"]:
        return None
    if datetime.fromisoformat(row["expires_at"]) <= timeutil.now():
        return None
    return row


def delete_session(conn, token):
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


# --- Cookie helpers -------------------------------------------------------


def build_session_cookie_header(token, max_age_seconds=None):
    if max_age_seconds is None:
        max_age_seconds = config.SESSION_LIFETIME_HOURS * 3600
    cookie = SimpleCookie()
    cookie[SESSION_COOKIE_NAME] = token
    morsel = cookie[SESSION_COOKIE_NAME]
    morsel["httponly"] = True
    morsel["path"] = "/"
    morsel["samesite"] = "Strict"
    morsel["max-age"] = max_age_seconds
    return morsel.OutputString()


def clear_session_cookie_header():
    return build_session_cookie_header("", max_age_seconds=0)


def get_token_from_cookie(handler):
    cookie_header = handler.headers.get("Cookie")
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(SESSION_COOKIE_NAME)
    return morsel.value if morsel else None


# --- Access guard ---------------------------------------------------------


def require_roles(handler, conn, *roles):
    """Return the current user row, or send 401/403 to the client and return None.

    With no roles given, any logged-in user is accepted (used by GET
    /api/me). With roles given, the user must have one of them.
    """
    token = get_token_from_cookie(handler)
    user = get_user_for_token(conn, token)
    if user is None:
        handler.send_json(401, {"error": "Not authenticated"})
        return None
    if roles and user["role"] not in roles:
        handler.send_json(403, {"error": "Forbidden"})
        return None
    return user
