"""Office hour requests. Recommendation letters are added in Step 8."""

from studybridge import auth, db, timeutil
from studybridge.router import router

REQUEST_SELECT = """
    SELECT
        office_hour_requests.id, office_hour_requests.requested_at, office_hour_requests.reason,
        office_hour_requests.status, office_hour_requests.advisor_comment,
        office_hour_requests.created_at, office_hour_requests.updated_at,
        office_hour_requests.student_id, students.full_name AS student_name,
        office_hour_requests.advisor_id, advisors.full_name AS advisor_name
    FROM office_hour_requests
    JOIN users AS students ON students.id = office_hour_requests.student_id
    JOIN users AS advisors ON advisors.id = office_hour_requests.advisor_id
"""


def _fetch_request(conn, request_id):
    return conn.execute(REQUEST_SELECT + " WHERE office_hour_requests.id = ?", (request_id,)).fetchone()


def _serialize(row):
    return {
        "id": row["id"],
        "student_id": row["student_id"],
        "student_name": row["student_name"],
        "advisor_id": row["advisor_id"],
        "advisor_name": row["advisor_name"],
        "requested_at": row["requested_at"],
        "reason": row["reason"],
        "status": row["status"],
        "advisor_comment": row["advisor_comment"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _parse_request_id(handler, params):
    try:
        return int(params["id"])
    except (KeyError, ValueError):
        handler.send_json(400, {"error": "Invalid request id"})
        return None


def handle_list_advisors(handler, params):
    """Student view: every active advisor, so they know who they can ask."""
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "student")
        if actor is None:
            return
        rows = conn.execute(
            "SELECT id, full_name, email FROM users WHERE role = 'advisor' AND is_active = 1 ORDER BY full_name"
        ).fetchall()
        handler.send_json(200, {"advisors": [dict(row) for row in rows]})
    finally:
        conn.close()


def handle_list_office_hour_requests(handler, params):
    """Students see their own requests, advisors see requests sent to them."""
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "student", "advisor")
        if actor is None:
            return

        if actor["role"] == "student":
            rows = conn.execute(
                REQUEST_SELECT
                + " WHERE office_hour_requests.student_id = ? ORDER BY office_hour_requests.requested_at",
                (actor["id"],),
            ).fetchall()
        else:
            rows = conn.execute(
                REQUEST_SELECT
                + " WHERE office_hour_requests.advisor_id = ? ORDER BY office_hour_requests.requested_at",
                (actor["id"],),
            ).fetchall()

        handler.send_json(200, {"requests": [_serialize(row) for row in rows]})
    finally:
        conn.close()


def handle_create_office_hour_request(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "student")
        if actor is None:
            return

        body = handler.read_json()
        reason = (body.get("reason") or "").strip()
        try:
            advisor_id = int(body.get("advisor_id"))
        except (TypeError, ValueError):
            handler.send_json(400, {"error": "advisor_id is required"})
            return
        try:
            requested_at = timeutil.parse_local(body.get("requested_at") or "")
        except ValueError:
            handler.send_json(400, {"error": "requested_at must be a valid datetime"})
            return

        if not reason:
            handler.send_json(400, {"error": "reason is required"})
            return
        if requested_at <= timeutil.now():
            handler.send_json(400, {"error": "requested_at must be in the future"})
            return

        advisor = conn.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'advisor' AND is_active = 1", (advisor_id,)
        ).fetchone()
        if advisor is None:
            handler.send_json(404, {"error": "Advisor not found"})
            return

        now_iso = timeutil.now_iso()
        cursor = conn.execute(
            """
            INSERT INTO office_hour_requests
                (student_id, advisor_id, requested_at, reason, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (actor["id"], advisor_id, requested_at.isoformat(), reason, now_iso, now_iso),
        )
        conn.commit()
        handler.send_json(201, _serialize(_fetch_request(conn, cursor.lastrowid)))
    finally:
        conn.close()


def _respond_to_request(handler, params, verb, new_status):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "advisor")
        if actor is None:
            return

        request_id = _parse_request_id(handler, params)
        if request_id is None:
            return

        row = _fetch_request(conn, request_id)
        if row is None:
            handler.send_json(404, {"error": "Request not found"})
            return
        if row["advisor_id"] != actor["id"]:
            handler.send_json(403, {"error": "You can only respond to your own requests"})
            return
        if row["status"] != "pending":
            handler.send_json(400, {"error": f"Cannot {verb} a request that is {row['status']}"})
            return

        body = handler.read_json()
        comment = (body.get("comment") or "").strip() or None

        conn.execute(
            "UPDATE office_hour_requests SET status = ?, advisor_comment = ?, updated_at = ? WHERE id = ?",
            (new_status, comment, timeutil.now_iso(), request_id),
        )
        conn.commit()
        handler.send_json(200, _serialize(_fetch_request(conn, request_id)))
    finally:
        conn.close()


def handle_accept_request(handler, params):
    _respond_to_request(handler, params, "accept", "accepted")


def handle_reject_request(handler, params):
    _respond_to_request(handler, params, "reject", "rejected")


router.add("GET", "/api/advisors", handle_list_advisors)
router.add("GET", "/api/office-hours", handle_list_office_hour_requests)
router.add("POST", "/api/office-hours", handle_create_office_hour_request)
router.add("POST", "/api/office-hours/{id}/accept", handle_accept_request)
router.add("POST", "/api/office-hours/{id}/reject", handle_reject_request)
