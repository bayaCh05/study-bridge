"""Step 5 tests: booking, accept/decline/cancel, and the concurrency guarantee."""

import json
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


class TestStep5Booking(unittest.TestCase):
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

    @staticmethod
    def _future(hours_from_now):
        dt = timeutil.now() + timedelta(hours=hours_from_now)
        return dt.strftime("%Y-%m-%dT%H:%M")

    def _make_tutor_with_slot(self):
        tutor_email = self._unique_email("tutor")
        self._create_user(tutor_email, "pass1234", "tutor")
        tutor_opener = self._login(tutor_email, "pass1234")
        create_req = self._request(
            "POST", "/api/availability", {"start_at": self._future(24), "end_at": self._future(25)}
        )
        with tutor_opener.open(create_req) as response:
            slot_id = json.loads(response.read())["id"]
        return tutor_opener, slot_id

    def _make_student(self):
        email = self._unique_email("student")
        self._create_user(email, "pass1234", "student")
        return self._login(email, "pass1234")

    def test_student_sees_tutor_with_free_slot(self):
        _tutor_opener, slot_id = self._make_tutor_with_slot()
        student_opener = self._make_student()

        with student_opener.open(f"{self.base_url}/api/tutors") as response:
            data = json.loads(response.read())
            slot_ids = [slot["id"] for tutor in data["tutors"] for slot in tutor["slots"]]
            self.assertIn(slot_id, slot_ids)

    def test_student_can_book_a_free_slot(self):
        _tutor_opener, slot_id = self._make_tutor_with_slot()
        student_opener = self._make_student()

        book_req = self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Algebra"})
        with student_opener.open(book_req) as response:
            self.assertEqual(response.status, 201)
            booking = json.loads(response.read())
            self.assertEqual(booking["status"], "pending")

    def test_booked_slot_disappears_from_free_slots(self):
        _tutor_opener, slot_id = self._make_tutor_with_slot()
        student_opener = self._make_student()
        with student_opener.open(
            self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Algebra"})
        ):
            pass

        with student_opener.open(f"{self.base_url}/api/tutors") as response:
            data = json.loads(response.read())
            slot_ids = [slot["id"] for tutor in data["tutors"] for slot in tutor["slots"]]
            self.assertNotIn(slot_id, slot_ids)

    def test_booking_an_already_booked_slot_is_409(self):
        _tutor_opener, slot_id = self._make_tutor_with_slot()
        student1 = self._make_student()
        student2 = self._make_student()

        with student1.open(self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})):
            pass

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            student2.open(self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"}))
        self.assertEqual(ctx.exception.code, 409)

    def test_tutor_can_accept_a_pending_booking(self):
        tutor_opener, slot_id = self._make_tutor_with_slot()
        student_opener = self._make_student()
        with student_opener.open(
            self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})
        ) as response:
            booking_id = json.loads(response.read())["id"]

        with tutor_opener.open(self._request("POST", f"/api/bookings/{booking_id}/accept")) as response:
            self.assertEqual(json.loads(response.read())["status"], "confirmed")

    def test_declined_slot_can_be_rebooked(self):
        tutor_opener, slot_id = self._make_tutor_with_slot()
        student1 = self._make_student()
        student2 = self._make_student()

        with student1.open(
            self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})
        ) as response:
            booking_id = json.loads(response.read())["id"]

        with tutor_opener.open(self._request("POST", f"/api/bookings/{booking_id}/decline")) as response:
            self.assertEqual(json.loads(response.read())["status"], "declined")

        # The slot must be bookable again now that the only booking on it is declined.
        rebook_req = self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Physics"})
        with student2.open(rebook_req) as response:
            self.assertEqual(response.status, 201)

    def test_tutor_cannot_respond_to_someone_elses_booking(self):
        _tutor1_opener, slot_id = self._make_tutor_with_slot()
        other_tutor_email = self._unique_email("othertutor")
        self._create_user(other_tutor_email, "pass1234", "tutor")
        other_tutor_opener = self._login(other_tutor_email, "pass1234")

        student_opener = self._make_student()
        with student_opener.open(
            self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})
        ) as response:
            booking_id = json.loads(response.read())["id"]

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            other_tutor_opener.open(self._request("POST", f"/api/bookings/{booking_id}/accept"))
        self.assertEqual(ctx.exception.code, 403)

    def test_cannot_accept_a_booking_that_is_not_pending(self):
        tutor_opener, slot_id = self._make_tutor_with_slot()
        student_opener = self._make_student()
        with student_opener.open(
            self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})
        ) as response:
            booking_id = json.loads(response.read())["id"]

        with tutor_opener.open(self._request("POST", f"/api/bookings/{booking_id}/accept")):
            pass

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            tutor_opener.open(self._request("POST", f"/api/bookings/{booking_id}/accept"))
        self.assertEqual(ctx.exception.code, 400)

    def test_student_can_cancel_own_pending_booking(self):
        _tutor_opener, slot_id = self._make_tutor_with_slot()
        student_opener = self._make_student()
        with student_opener.open(
            self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})
        ) as response:
            booking_id = json.loads(response.read())["id"]

        with student_opener.open(self._request("POST", f"/api/bookings/{booking_id}/cancel")) as response:
            self.assertEqual(json.loads(response.read())["status"], "cancelled")

    def test_student_cannot_cancel_someone_elses_booking(self):
        _tutor_opener, slot_id = self._make_tutor_with_slot()
        student1 = self._make_student()
        student2 = self._make_student()
        with student1.open(
            self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})
        ) as response:
            booking_id = json.loads(response.read())["id"]

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            student2.open(self._request("POST", f"/api/bookings/{booking_id}/cancel"))
        self.assertEqual(ctx.exception.code, 403)

    def test_cannot_cancel_a_declined_booking(self):
        tutor_opener, slot_id = self._make_tutor_with_slot()
        student_opener = self._make_student()
        with student_opener.open(
            self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})
        ) as response:
            booking_id = json.loads(response.read())["id"]

        with tutor_opener.open(self._request("POST", f"/api/bookings/{booking_id}/decline")):
            pass

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            student_opener.open(self._request("POST", f"/api/bookings/{booking_id}/cancel"))
        self.assertEqual(ctx.exception.code, 400)

    def test_concurrent_booking_only_one_request_succeeds(self):
        _tutor_opener, slot_id = self._make_tutor_with_slot()
        student1 = self._make_student()
        student2 = self._make_student()

        results = []
        barrier = threading.Barrier(2)

        def attempt_booking(opener):
            barrier.wait()
            request = self._request("POST", "/api/bookings", {"availability_id": slot_id, "subject": "Math"})
            try:
                with opener.open(request) as response:
                    results.append(response.status)
            except urllib.error.HTTPError as err:
                results.append(err.code)

        threads = [
            threading.Thread(target=attempt_booking, args=(student1,)),
            threading.Thread(target=attempt_booking, args=(student2,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(results), [201, 409])


if __name__ == "__main__":
    unittest.main()
