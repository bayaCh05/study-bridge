"""Step 6 tests: session reports — timing, ownership, one report per booking."""

import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import timedelta
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import HTTPCookieProcessor, build_opener

from studybridge import auth, config, db, timeutil
from studybridge.server import StudyBridgeHandler


class TestStep6Reports(unittest.TestCase):
    _counter = 0

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.db_patches = [
            patch.object(config, "DATA_DIR", Path(cls.tmp_dir.name)),
            patch.object(config, "DB_PATH", Path(cls.tmp_dir.name) / "test.db"),
        ]
        for p in cls.db_patches:
            p.start()
        db.init_db()

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StudyBridgeHandler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        for p in cls.db_patches:
            p.stop()
        cls.tmp_dir.cleanup()

    @classmethod
    def _unique_email(cls, prefix):
        cls._counter += 1
        return f"{prefix}{cls._counter}@test.com"

    @staticmethod
    def _create_user(email, password, role):
        password_hash, salt = auth.hash_password(password)
        conn = db.get_connection()
        conn.execute(
            """
            INSERT INTO users (full_name, email, password_hash, salt, role, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (email.split("@")[0], email, password_hash, salt, role, timeutil.now_iso()),
        )
        conn.commit()
        conn.close()

    def _login(self, email, password):
        jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))
        request = urllib.request.Request(
            f"{self.base_url}/api/login",
            data=json.dumps({"email": email, "password": password}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(request):
            pass
        return opener

    def _request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        return urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)

    def _make_confirmed_booking(self, start_hours_from_now, end_hours_from_now):
        """Create a tutor + slot + student booking, tutor-accepted, returns
        (tutor_opener, student_opener, booking_id)."""
        tutor_email = self._unique_email("tutor")
        student_email = self._unique_email("student")
        self._create_user(tutor_email, "pass1234", "tutor")
        self._create_user(student_email, "pass1234", "student")
        tutor_opener = self._login(tutor_email, "pass1234")
        student_opener = self._login(student_email, "pass1234")

        start = (timeutil.now() + timedelta(hours=start_hours_from_now)).strftime("%Y-%m-%dT%H:%M")
        end = (timeutil.now() + timedelta(hours=end_hours_from_now)).strftime("%Y-%m-%dT%H:%M")
        create_slot_req = self._request("POST", "/api/availability", {"start_at": start, "end_at": end})
        with tutor_opener.open(create_slot_req) as response:
            slot_id = json.loads(response.read())["id"]

        book_req = self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})
        with student_opener.open(book_req) as response:
            booking_id = json.loads(response.read())["id"]

        with tutor_opener.open(self._request("POST", f"/api/bookings/{booking_id}/accept")):
            pass

        return tutor_opener, student_opener, booking_id

    def _force_confirmed_booking_in_the_past(self):
        """Same as _make_confirmed_booking, but the slot is already over —
        created directly in the DB since the API won't let a tutor add a
        past slot."""
        tutor_email = self._unique_email("tutor")
        student_email = self._unique_email("student")
        self._create_user(tutor_email, "pass1234", "tutor")
        self._create_user(student_email, "pass1234", "student")
        tutor_opener = self._login(tutor_email, "pass1234")
        student_opener = self._login(student_email, "pass1234")

        conn = db.get_connection()
        tutor_id = conn.execute("SELECT id FROM users WHERE email = ?", (tutor_email,)).fetchone()["id"]
        student_id = conn.execute("SELECT id FROM users WHERE email = ?", (student_email,)).fetchone()["id"]
        start = (timeutil.now() - timedelta(hours=2)).isoformat()
        end = (timeutil.now() - timedelta(hours=1)).isoformat()
        cursor = conn.execute(
            "INSERT INTO availability (tutor_id, start_at, end_at) VALUES (?, ?, ?)", (tutor_id, start, end)
        )
        slot_id = cursor.lastrowid
        now_iso = timeutil.now_iso()
        cursor = conn.execute(
            """
            INSERT INTO bookings (student_id, availability_id, subject, status, created_at, updated_at)
            VALUES (?, ?, 'Math', 'confirmed', ?, ?)
            """,
            (student_id, slot_id, now_iso, now_iso),
        )
        booking_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return tutor_opener, student_opener, booking_id

    def test_cannot_report_a_future_session(self):
        tutor_opener, _student_opener, booking_id = self._make_confirmed_booking(24, 25)
        complete_req = self._request(
            "POST", f"/api/bookings/{booking_id}/complete", {"attended": True, "notes": "Went well"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            tutor_opener.open(complete_req)
        self.assertEqual(ctx.exception.code, 400)

    def test_tutor_can_report_a_finished_session(self):
        tutor_opener, student_opener, booking_id = self._force_confirmed_booking_in_the_past()
        complete_req = self._request(
            "POST", f"/api/bookings/{booking_id}/complete", {"attended": True, "notes": "Covered chapter 3"}
        )
        with tutor_opener.open(complete_req) as response:
            data = json.loads(response.read())
            self.assertEqual(data["status"], "completed")
            self.assertEqual(data["report"]["attended"], True)
            self.assertEqual(data["report"]["notes"], "Covered chapter 3")

        # The student sees the completed status and the report notes.
        with student_opener.open(f"{self.base_url}/api/bookings") as response:
            booking = json.loads(response.read())["bookings"][0]
            self.assertEqual(booking["status"], "completed")
            self.assertEqual(booking["report"]["notes"], "Covered chapter 3")

    def test_only_the_owning_tutor_can_report(self):
        _tutor_opener, _student_opener, booking_id = self._force_confirmed_booking_in_the_past()
        other_tutor_email = self._unique_email("othertutor")
        self._create_user(other_tutor_email, "pass1234", "tutor")
        other_tutor_opener = self._login(other_tutor_email, "pass1234")

        complete_req = self._request(
            "POST", f"/api/bookings/{booking_id}/complete", {"attended": True, "notes": "Notes"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            other_tutor_opener.open(complete_req)
        self.assertEqual(ctx.exception.code, 403)

    def test_cannot_report_the_same_booking_twice(self):
        tutor_opener, _student_opener, booking_id = self._force_confirmed_booking_in_the_past()
        complete_req = self._request(
            "POST", f"/api/bookings/{booking_id}/complete", {"attended": True, "notes": "First report"}
        )
        with tutor_opener.open(complete_req):
            pass

        second_req = self._request(
            "POST", f"/api/bookings/{booking_id}/complete", {"attended": True, "notes": "Second report"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            tutor_opener.open(second_req)
        self.assertEqual(ctx.exception.code, 400)

    def test_session_reports_booking_id_is_unique_at_the_db_level(self):
        _tutor_opener, _student_opener, booking_id = self._force_confirmed_booking_in_the_past()
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO session_reports (booking_id, attended, notes, created_at) VALUES (?, 1, 'a', ?)",
            (booking_id, timeutil.now_iso()),
        )
        conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO session_reports (booking_id, attended, notes, created_at) VALUES (?, 0, 'b', ?)",
                (booking_id, timeutil.now_iso()),
            )
        conn.close()


if __name__ == "__main__":
    unittest.main()
