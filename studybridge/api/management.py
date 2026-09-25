"""Management-only user CRUD: /api/users and /api/users/{id}[/action]."""

import sqlite3
from urllib.parse import parse_qs, urlparse

from studybridge import auth, db, timeutil
from studybridge.router import router

ROLES = {"student", "tutor", "advisor", "management"}


def _serialize(row):
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


def _parse_id(handler, params):
    try:
        return int(params["id"])
    except (KeyError, ValueError):
        handler.send_json(400, {"error": "Invalid user id"})
        return None


def handle_list_users(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "management")
        if actor is None:
            return

        query = parse_qs(urlparse(handler.path).query)
        role = query.get("role", [None])[0]
        search = query.get("search", [None])[0]

        sql = "SELECT id, full_name, email, role, is_active, created_at FROM users WHERE 1=1"
        args = []
        if role:
            sql += " AND role = ?"
            args.append(role)
        if search:
            sql += " AND (full_name LIKE ? OR email LIKE ?)"
            like = f"%{search}%"
            args += [like, like]
        sql += " ORDER BY id"

        rows = conn.execute(sql, args).fetchall()
        handler.send_json(200, {"users": [_serialize(row) for row in rows]})
    finally:
        conn.close()


def handle_create_user(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "management")
        if actor is None:
            return

        body = handler.read_json()
        full_name = (body.get("full_name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""
        role = body.get("role") or ""

        if not full_name or not email or not password or role not in ROLES:
            handler.send_json(400, {"error": "full_name, email, password and a valid role are required"})
            return

        password_hash, salt = auth.hash_password(password)
        try:
            conn.execute(
                """
                INSERT INTO users (full_name, email, password_hash, salt, role, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (full_name, email, password_hash, salt, role, timeutil.now_iso()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            handler.send_json(409, {"error": "A user with this email already exists"})
            return

        row = conn.execute(
            "SELECT id, full_name, email, role, is_active, created_at FROM users WHERE email = ?", (email,)
        ).fetchone()
        handler.send_json(201, _serialize(row))
    finally:
        conn.close()


def handle_update_user(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "management")
        if actor is None:
            return

        target_id = _parse_id(handler, params)
        if target_id is None:
            return

        target = conn.execute("SELECT id FROM users WHERE id = ?", (target_id,)).fetchone()
        if target is None:
            handler.send_json(404, {"error": "User not found"})
            return

        body = handler.read_json()
        full_name = (body.get("full_name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        role = body.get("role") or ""

        if not full_name or not email or role not in ROLES:
            handler.send_json(400, {"error": "full_name, email and a valid role are required"})
            return

        try:
            conn.execute(
                "UPDATE users SET full_name = ?, email = ?, role = ? WHERE id = ?",
                (full_name, email, role, target_id),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            handler.send_json(409, {"error": "A user with this email already exists"})
            return

        row = conn.execute(
            "SELECT id, full_name, email, role, is_active, created_at FROM users WHERE id = ?", (target_id,)
        ).fetchone()
        handler.send_json(200, _serialize(row))
    finally:
        conn.close()


def _set_active(handler, params, is_active):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "management")
        if actor is None:
            return

        target_id = _parse_id(handler, params)
        if target_id is None:
            return

        if target_id == actor["id"]:
            action = "reactivate" if is_active else "deactivate"
            handler.send_json(400, {"error": f"You cannot {action} your own account"})
            return

        target = conn.execute("SELECT id FROM users WHERE id = ?", (target_id,)).fetchone()
        if target is None:
            handler.send_json(404, {"error": "User not found"})
            return

        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, target_id))
        conn.commit()

        row = conn.execute(
            "SELECT id, full_name, email, role, is_active, created_at FROM users WHERE id = ?", (target_id,)
        ).fetchone()
        handler.send_json(200, _serialize(row))
    finally:
        conn.close()


def handle_deactivate_user(handler, params):
    _set_active(handler, params, is_active=False)


def handle_reactivate_user(handler, params):
    _set_active(handler, params, is_active=True)


def handle_delete_user(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "management")
        if actor is None:
            return

        target_id = _parse_id(handler, params)
        if target_id is None:
            return

        if target_id == actor["id"]:
            handler.send_json(400, {"error": "You cannot delete your own account"})
            return

        target = conn.execute("SELECT id FROM users WHERE id = ?", (target_id,)).fetchone()
        if target is None:
            handler.send_json(404, {"error": "User not found"})
            return

        conn.execute("DELETE FROM users WHERE id = ?", (target_id,))
        conn.commit()
        handler.send_json(200, {"ok": True})
    finally:
        conn.close()


router.add("GET", "/api/users", handle_list_users)
router.add("POST", "/api/users", handle_create_user)
router.add("PUT", "/api/users/{id}", handle_update_user)
router.add("POST", "/api/users/{id}/deactivate", handle_deactivate_user)
router.add("POST", "/api/users/{id}/reactivate", handle_reactivate_user)
router.add("DELETE", "/api/users/{id}", handle_delete_user)
