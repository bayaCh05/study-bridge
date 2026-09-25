"""Tutor availability. Bookings and session reports are added in Steps 5-6."""

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


router.add("GET", "/api/availability", handle_list_slots)
router.add("POST", "/api/availability", handle_create_slot)
router.add("DELETE", "/api/availability/{id}", handle_delete_slot)
