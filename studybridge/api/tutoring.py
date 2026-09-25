"""Tutor availability, and student/tutor bookings. Session reports are added in Step 6."""

import sqlite3
from datetime import datetime

from studybridge import auth, db, timeutil
from studybridge.router import router


def _serialize(row):
    return {
        "id": row["id"],
        "tutor_id": row["tutor_id"],
        "start_at": row["start_at"],
        "end_at": row["end_at"],
    }


def _parse_id(handler, params):
    try:
        return int(params["id"])
    except (KeyError, ValueError):
        handler.send_json(400, {"error": "Invalid slot id"})
        return None


def handle_list_slots(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "tutor")
        if actor is None:
            return

        rows = conn.execute(
            """
            SELECT id, tutor_id, start_at, end_at FROM availability
            WHERE tutor_id = ? AND start_at > ?
            ORDER BY start_at
            """,
            (actor["id"], timeutil.now_iso()),
        ).fetchall()
        handler.send_json(200, {"slots": [_serialize(row) for row in rows]})
    finally:
        conn.close()


def handle_create_slot(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "tutor")
        if actor is None:
            return

        body = handler.read_json()
        try:
            start_at = timeutil.parse_local(body.get("start_at") or "")
            end_at = timeutil.parse_local(body.get("end_at") or "")
        except ValueError:
            handler.send_json(400, {"error": "start_at and end_at must be valid datetimes"})
            return

        if start_at <= timeutil.now():
            handler.send_json(400, {"error": "Slots must be in the future"})
            return
        if end_at <= start_at:
            handler.send_json(400, {"error": "end_at must be after start_at"})
            return

        # Two ranges [a, b) and [c, d) overlap exactly when a < d and c < b.
        overlap = conn.execute(
            "SELECT id FROM availability WHERE tutor_id = ? AND start_at < ? AND end_at > ?",
            (actor["id"], end_at.isoformat(), start_at.isoformat()),
        ).fetchone()
        if overlap is not None:
            handler.send_json(400, {"error": "This slot overlaps one of your existing slots"})
            return

        cursor = conn.execute(
            "INSERT INTO availability (tutor_id, start_at, end_at) VALUES (?, ?, ?)",
            (actor["id"], start_at.isoformat(), end_at.isoformat()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, tutor_id, start_at, end_at FROM availability WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        handler.send_json(201, _serialize(row))
    finally:
        conn.close()


def handle_delete_slot(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "tutor")
        if actor is None:
            return

        slot_id = _parse_id(handler, params)
        if slot_id is None:
            return

        slot = conn.execute("SELECT id, tutor_id FROM availability WHERE id = ?", (slot_id,)).fetchone()
        if slot is None:
            handler.send_json(404, {"error": "Slot not found"})
            return
        if slot["tutor_id"] != actor["id"]:
            handler.send_json(403, {"error": "You can only delete your own slots"})
            return

        active_booking = conn.execute(
            "SELECT id FROM bookings WHERE availability_id = ? AND status NOT IN ('declined', 'cancelled')",
            (slot_id,),
        ).fetchone()
        if active_booking is not None:
            handler.send_json(400, {"error": "Cannot delete a slot that has a booking"})
            return

        conn.execute("DELETE FROM availability WHERE id = ?", (slot_id,))
        conn.commit()
        handler.send_json(200, {"ok": True})
    finally:
        conn.close()


# --- Booking ---------------------------------------------------------

BOOKING_SELECT = """
    SELECT
        bookings.id, bookings.subject, bookings.status, bookings.created_at, bookings.updated_at,
        bookings.student_id, students.full_name AS student_name,
        availability.id AS availability_id, availability.start_at, availability.end_at,
        availability.tutor_id, tutors.full_name AS tutor_name
    FROM bookings
    JOIN availability ON availability.id = bookings.availability_id
    JOIN users AS students ON students.id = bookings.student_id
    JOIN users AS tutors ON tutors.id = availability.tutor_id
"""


def _fetch_booking(conn, booking_id):
    return conn.execute(BOOKING_SELECT + " WHERE bookings.id = ?", (booking_id,)).fetchone()


def _serialize_booking(row):
    return {
        "id": row["id"],
        "subject": row["subject"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "student_id": row["student_id"],
        "student_name": row["student_name"],
        "tutor_id": row["tutor_id"],
        "tutor_name": row["tutor_name"],
        "availability_id": row["availability_id"],
        "start_at": row["start_at"],
        "end_at": row["end_at"],
    }


def _parse_booking_id(handler, params):
    try:
        return int(params["id"])
    except (KeyError, ValueError):
        handler.send_json(400, {"error": "Invalid booking id"})
        return None


def handle_list_tutors(handler, params):
    """Student view: every active tutor, with their free future slots."""
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "student")
        if actor is None:
            return

        rows = conn.execute(
            """
            SELECT users.id AS tutor_id, users.full_name AS tutor_name, users.email AS tutor_email,
                   availability.id AS slot_id, availability.start_at, availability.end_at
            FROM users
            LEFT JOIN availability
                ON availability.tutor_id = users.id
                AND availability.start_at > ?
                AND NOT EXISTS (
                    SELECT 1 FROM bookings
                    WHERE bookings.availability_id = availability.id
                      AND bookings.status IN ('pending', 'confirmed')
                )
            WHERE users.role = 'tutor' AND users.is_active = 1
            ORDER BY users.full_name, availability.start_at
            """,
            (timeutil.now_iso(),),
        ).fetchall()

        tutors_by_id = {}
        for row in rows:
            tutor = tutors_by_id.setdefault(
                row["tutor_id"],
                {"id": row["tutor_id"], "full_name": row["tutor_name"], "email": row["tutor_email"], "slots": []},
            )
            if row["slot_id"] is not None:
                tutor["slots"].append({"id": row["slot_id"], "start_at": row["start_at"], "end_at": row["end_at"]})

        handler.send_json(200, {"tutors": list(tutors_by_id.values())})
    finally:
        conn.close()


def handle_list_bookings(handler, params):
    """Students see their own bookings, tutors see bookings on their slots,
    and management sees everything."""
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "student", "tutor", "management")
        if actor is None:
            return

        if actor["role"] == "student":
            rows = conn.execute(
                BOOKING_SELECT + " WHERE bookings.student_id = ? ORDER BY availability.start_at", (actor["id"],)
            ).fetchall()
        elif actor["role"] == "tutor":
            rows = conn.execute(
                BOOKING_SELECT + " WHERE availability.tutor_id = ? ORDER BY availability.start_at", (actor["id"],)
            ).fetchall()
        else:
            rows = conn.execute(BOOKING_SELECT + " ORDER BY availability.start_at").fetchall()

        handler.send_json(200, {"bookings": [_serialize_booking(row) for row in rows]})
    finally:
        conn.close()


def handle_create_booking(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "student")
        if actor is None:
            return

        body = handler.read_json()
        subject = (body.get("subject") or "").strip()
        try:
            availability_id = int(body.get("availability_id"))
        except (TypeError, ValueError):
            handler.send_json(400, {"error": "availability_id is required"})
            return
        if not subject:
            handler.send_json(400, {"error": "subject is required"})
            return

        slot = conn.execute("SELECT id, start_at FROM availability WHERE id = ?", (availability_id,)).fetchone()
        if slot is None:
            handler.send_json(404, {"error": "Slot not found"})
            return
        if datetime.fromisoformat(slot["start_at"]) <= timeutil.now():
            handler.send_json(400, {"error": "This slot is no longer in the future"})
            return

        now_iso = timeutil.now_iso()
        try:
            cursor = conn.execute(
                """
                INSERT INTO bookings (student_id, availability_id, subject, status, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (actor["id"], availability_id, subject, now_iso, now_iso),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # The partial unique index caught a race: someone else's booking
            # for this same slot committed a moment before ours.
            handler.send_json(409, {"error": "This slot was just taken"})
            return

        handler.send_json(201, _serialize_booking(_fetch_booking(conn, cursor.lastrowid)))
    finally:
        conn.close()


def _respond_to_booking(handler, params, verb, new_status):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "tutor")
        if actor is None:
            return

        booking_id = _parse_booking_id(handler, params)
        if booking_id is None:
            return

        row = _fetch_booking(conn, booking_id)
        if row is None:
            handler.send_json(404, {"error": "Booking not found"})
            return
        if row["tutor_id"] != actor["id"]:
            handler.send_json(403, {"error": "You can only respond to your own bookings"})
            return
        if row["status"] != "pending":
            handler.send_json(400, {"error": f"Cannot {verb} a booking that is {row['status']}"})
            return

        conn.execute(
            "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, timeutil.now_iso(), booking_id),
        )
        conn.commit()
        handler.send_json(200, _serialize_booking(_fetch_booking(conn, booking_id)))
    finally:
        conn.close()


def handle_accept_booking(handler, params):
    _respond_to_booking(handler, params, "accept", "confirmed")


def handle_decline_booking(handler, params):
    _respond_to_booking(handler, params, "decline", "declined")


def handle_cancel_booking(handler, params):
    conn = db.get_connection()
    try:
        actor = auth.require_roles(handler, conn, "student", "tutor")
        if actor is None:
            return

        booking_id = _parse_booking_id(handler, params)
        if booking_id is None:
            return

        row = _fetch_booking(conn, booking_id)
        if row is None:
            handler.send_json(404, {"error": "Booking not found"})
            return

        is_owner = (actor["role"] == "student" and row["student_id"] == actor["id"]) or (
            actor["role"] == "tutor" and row["tutor_id"] == actor["id"]
        )
        if not is_owner:
            handler.send_json(403, {"error": "You can only cancel your own bookings"})
            return
        if row["status"] not in ("pending", "confirmed"):
            handler.send_json(400, {"error": f"Cannot cancel a booking that is {row['status']}"})
            return
        if datetime.fromisoformat(row["start_at"]) <= timeutil.now():
            handler.send_json(400, {"error": "Cannot cancel a session that has already started"})
            return

        conn.execute(
            "UPDATE bookings SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (timeutil.now_iso(), booking_id),
        )
        conn.commit()
        handler.send_json(200, _serialize_booking(_fetch_booking(conn, booking_id)))
    finally:
        conn.close()


router.add("GET", "/api/availability", handle_list_slots)
router.add("POST", "/api/availability", handle_create_slot)
router.add("DELETE", "/api/availability/{id}", handle_delete_slot)

router.add("GET", "/api/tutors", handle_list_tutors)
router.add("GET", "/api/bookings", handle_list_bookings)
router.add("POST", "/api/bookings", handle_create_booking)
router.add("POST", "/api/bookings/{id}/accept", handle_accept_booking)
router.add("POST", "/api/bookings/{id}/decline", handle_decline_booking)
router.add("POST", "/api/bookings/{id}/cancel", handle_cancel_booking)
