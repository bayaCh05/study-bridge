"""Authentication endpoints: POST /api/login, POST /api/logout, GET /api/me."""

from studybridge import auth, db
from studybridge.router import router


def handle_login(handler, params):
    body = handler.read_json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    conn = db.get_connection()
    try:
        user = conn.execute(
            "SELECT id, full_name, email, password_hash, salt, role, is_active FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        valid = (
            user is not None
            and user["is_active"]
            and auth.verify_password(password, user["password_hash"], user["salt"])
        )
        if not valid:
            # Same message whether the email doesn't exist or the password is
            # wrong, so a login attempt can't be used to find out which
            # emails are registered.
            handler.send_json(401, {"error": "Invalid email or password"})
            return

        token, _expires_at = auth.create_session(conn, user["id"])
    finally:
        conn.close()

    handler.send_json(
        200,
        {"id": user["id"], "full_name": user["full_name"], "email": user["email"], "role": user["role"]},
        headers=[("Set-Cookie", auth.build_session_cookie_header(token))],
    )


def handle_logout(handler, params):
    token = auth.get_token_from_cookie(handler)
    if token:
        conn = db.get_connection()
        try:
            auth.delete_session(conn, token)
        finally:
            conn.close()
    handler.send_json(200, {"ok": True}, headers=[("Set-Cookie", auth.clear_session_cookie_header())])


def handle_me(handler, params):
    conn = db.get_connection()
    try:
        user = auth.require_roles(handler, conn)
    finally:
        conn.close()
    if user is None:
        return  # require_roles already sent 401
    handler.send_json(
        200,
        {"id": user["id"], "full_name": user["full_name"], "email": user["email"], "role": user["role"]},
    )


router.add("POST", "/api/login", handle_login)
router.add("POST", "/api/logout", handle_logout)
router.add("GET", "/api/me", handle_me)
