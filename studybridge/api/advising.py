"""Office hour requests and recommendation letters."""

import base64
import binascii
import re
import secrets

from studybridge import auth, config, db, timeutil
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


# --- Recommendation letters ------------------------------------------
#
# The browser reads the PDF with FileReader and sends it as base64 JSON
# instead of a multipart upload, so we never need to hand-parse multipart
# bodies with http.server. See static/js/advisor.js.

LETTER_SELECT = """
    SELECT
        letters.id, letters.title, letters.original_filename, letters.stored_filename,
        letters.size_bytes, letters.uploaded_at,
        letters.advisor_id, advisors.full_name AS advisor_name,
        letters.student_id, students.full_name AS student_name
    FROM letters
    JOIN users AS advisors ON advisors.id = letters.advisor_id
    JOIN users AS students ON students.id = letters.student_id
"""


def _fetch_letter(conn, letter_id):
    return conn.execute(LETTER_SELECT + " WHERE letters.id = ?", (letter_id,)).fetchone()


def _serialize_letter(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "original_filename": row["original_filename"],
        "size_bytes": row["size_bytes"],
        "uploaded_at": row["uploaded_at"],
        "advisor_id": row["advisor_id"],
        "advisor_name": row["advisor_name"],
        "student_id": row["student_id"],
        "student_name": row["student_name"],
    }


def _safe_download_filename(name):
    # The name is client-supplied and lands in a response header
    # (Content-Disposition): strip quotes/CR/LF so it can't break out of the
    # header value or inject an extra header line.
    cleaned = re.sub(r'[\r\n"]', "", name).strip()
    return cleaned or "letter.pdf"


def handle_list_students(handler, params):
    """Advisor view: every active student, so they know who they can write for."""
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "advisor")
        if actor is None:
            return
        rows = conn.execute(
            "SELECT id, full_name, email FROM users WHERE role = 'student' AND is_active = 1 ORDER BY full_name"
        ).fetchall()
        handler.send_json(200, {"students": [dict(row) for row in rows]})
    finally:
        conn.close()


def handle_list_letters(handler, params):
    """Students and advisors see their own letters; management sees all."""
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "student", "advisor", "management")
        if actor is None:
            return

        if actor["role"] == "student":
            rows = conn.execute(
                LETTER_SELECT + " WHERE letters.student_id = ? ORDER BY letters.uploaded_at DESC", (actor["id"],)
            ).fetchall()
        elif actor["role"] == "advisor":
            rows = conn.execute(
                LETTER_SELECT + " WHERE letters.advisor_id = ? ORDER BY letters.uploaded_at DESC", (actor["id"],)
            ).fetchall()
        else:
            rows = conn.execute(LETTER_SELECT + " ORDER BY letters.uploaded_at DESC").fetchall()

        handler.send_json(200, {"letters": [_serialize_letter(row) for row in rows]})
    finally:
        conn.close()


def handle_upload_letter(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "advisor")
        if actor is None:
            return

        body = handler.read_json()
        title = (body.get("title") or "").strip()
        filename = (body.get("filename") or "").strip()
        content_b64 = body.get("content_base64") or ""
        try:
            student_id = int(body.get("student_id"))
        except (TypeError, ValueError):
            handler.send_json(400, {"error": "student_id is required"})
            return

        if not title:
            handler.send_json(400, {"error": "title is required"})
            return
        if not filename:
            handler.send_json(400, {"error": "filename is required"})
            return

        student = conn.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'student' AND is_active = 1", (student_id,)
        ).fetchone()
        if student is None:
            handler.send_json(404, {"error": "Student not found"})
            return

        try:
            content = base64.b64decode(content_b64, validate=True)
        except (binascii.Error, ValueError):
            handler.send_json(400, {"error": "content_base64 is not valid base64"})
            return

        if len(content) > config.MAX_LETTER_SIZE:
            handler.send_json(413, {"error": "File is too large (max 5 MB)"})
            return
        if content[:4] != b"%PDF":
            handler.send_json(400, {"error": "File must be a PDF"})
            return

        letters_dir = config.DATA_DIR / "letters"
        letters_dir.mkdir(parents=True, exist_ok=True)
        stored_filename = secrets.token_hex(16) + ".pdf"
        (letters_dir / stored_filename).write_bytes(content)

        cursor = conn.execute(
            """
            INSERT INTO letters
                (advisor_id, student_id, title, stored_filename, original_filename, size_bytes, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (actor["id"], student_id, title, stored_filename, filename, len(content), timeutil.now_iso()),
        )
        conn.commit()
        handler.send_json(201, _serialize_letter(_fetch_letter(conn, cursor.lastrowid)))
    finally:
        conn.close()


def handle_download_letter(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "student", "advisor", "management")
        if actor is None:
            return

        try:
            letter_id = int(params["id"])
        except (KeyError, ValueError):
            handler.send_json(400, {"error": "Invalid letter id"})
            return

        row = _fetch_letter(conn, letter_id)
        if row is None:
            handler.send_json(404, {"error": "Letter not found"})
            return

        is_owner = (
            (actor["role"] == "student" and row["student_id"] == actor["id"])
            or (actor["role"] == "advisor" and row["advisor_id"] == actor["id"])
            or actor["role"] == "management"
        )
        if not is_owner:
            handler.send_json(403, {"error": "You cannot access this letter"})
            return

        file_path = config.DATA_DIR / "letters" / row["stored_filename"]
        if not file_path.is_file():
            handler.send_json(404, {"error": "File not found"})
            return

        data = file_path.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/pdf")
        handler.send_header("Content-Length", str(len(data)))
        safe_name = _safe_download_filename(row["original_filename"])
        handler.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        handler.end_headers()
        handler.wfile.write(data)
    finally:
        conn.close()


router.add("GET", "/api/students", handle_list_students)
router.add("GET", "/api/letters", handle_list_letters)
router.add("POST", "/api/letters", handle_upload_letter)
router.add("GET", "/api/letters/{id}/download", handle_download_letter)
