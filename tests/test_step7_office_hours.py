"""Step 7 tests: office hour requests — only the targeted advisor responds,
and can't respond twice."""

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


class TestStep7OfficeHours(unittest.TestCase):
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

    def _make_student_and_advisor(self):
        student_email = self._unique_email("student")
        advisor_email = self._unique_email("advisor")
        self._create_user(student_email, "pass1234", "student")
        self._create_user(advisor_email, "pass1234", "advisor")
        return self._login(student_email, "pass1234"), self._login(advisor_email, "pass1234")

    def _make_request(self, student_opener, advisor_id, hours_from_now=24):
        create_req = self._request(
            "POST",
            "/api/office-hours",
            {"advisor_id": advisor_id, "requested_at": self._future(hours_from_now), "reason": "Course planning"},
        )
        with student_opener.open(create_req) as response:
            return json.loads(response.read())["id"]

    def _advisor_id(self, advisor_opener):
        with advisor_opener.open(f"{self.base_url}/api/me") as response:
            return json.loads(response.read())["id"]

    def test_student_can_create_and_see_own_request(self):
        student_opener, advisor_opener = self._make_student_and_advisor()
        advisor_id = self._advisor_id(advisor_opener)
        request_id = self._make_request(student_opener, advisor_id)

        with student_opener.open(f"{self.base_url}/api/office-hours") as response:
            data = json.loads(response.read())
            self.assertEqual(len(data["requests"]), 1)
            self.assertEqual(data["requests"][0]["id"], request_id)
            self.assertEqual(data["requests"][0]["status"], "pending")

    def test_targeted_advisor_sees_the_pending_request(self):
        student_opener, advisor_opener = self._make_student_and_advisor()
        advisor_id = self._advisor_id(advisor_opener)
        self._make_request(student_opener, advisor_id)

        with advisor_opener.open(f"{self.base_url}/api/office-hours") as response:
            data = json.loads(response.read())
            self.assertEqual(len(data["requests"]), 1)
            self.assertEqual(data["requests"][0]["status"], "pending")

    def test_other_advisor_does_not_see_the_request(self):
        student_opener, advisor_opener = self._make_student_and_advisor()
        advisor_id = self._advisor_id(advisor_opener)
        self._make_request(student_opener, advisor_id)

        other_advisor_email = self._unique_email("otheradvisor")
        self._create_user(other_advisor_email, "pass1234", "advisor")
        other_advisor_opener = self._login(other_advisor_email, "pass1234")

        with other_advisor_opener.open(f"{self.base_url}/api/office-hours") as response:
            self.assertEqual(json.loads(response.read())["requests"], [])

    def test_only_the_targeted_advisor_can_accept(self):
        student_opener, advisor_opener = self._make_student_and_advisor()
        advisor_id = self._advisor_id(advisor_opener)
        request_id = self._make_request(student_opener, advisor_id)

        other_advisor_email = self._unique_email("otheradvisor")
        self._create_user(other_advisor_email, "pass1234", "advisor")
        other_advisor_opener = self._login(other_advisor_email, "pass1234")

        accept_req = self._request("POST", f"/api/office-hours/{request_id}/accept", {"comment": ""})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            other_advisor_opener.open(accept_req)
        self.assertEqual(ctx.exception.code, 403)

    def test_advisor_can_accept_with_a_comment_and_student_sees_it(self):
        student_opener, advisor_opener = self._make_student_and_advisor()
        advisor_id = self._advisor_id(advisor_opener)
        request_id = self._make_request(student_opener, advisor_id)

        accept_req = self._request(
            "POST", f"/api/office-hours/{request_id}/accept", {"comment": "See you then"}
        )
        with advisor_opener.open(accept_req) as response:
            data = json.loads(response.read())
            self.assertEqual(data["status"], "accepted")
            self.assertEqual(data["advisor_comment"], "See you then")

        with student_opener.open(f"{self.base_url}/api/office-hours") as response:
            data = json.loads(response.read())["requests"][0]
            self.assertEqual(data["status"], "accepted")
            self.assertEqual(data["advisor_comment"], "See you then")

    def test_advisor_can_reject_a_request(self):
        student_opener, advisor_opener = self._make_student_and_advisor()
        advisor_id = self._advisor_id(advisor_opener)
        request_id = self._make_request(student_opener, advisor_id)

        reject_req = self._request("POST", f"/api/office-hours/{request_id}/reject", {"comment": "Not available"})
        with advisor_opener.open(reject_req) as response:
            self.assertEqual(json.loads(response.read())["status"], "rejected")

    def test_advisor_cannot_respond_to_the_same_request_twice(self):
        student_opener, advisor_opener = self._make_student_and_advisor()
        advisor_id = self._advisor_id(advisor_opener)
        request_id = self._make_request(student_opener, advisor_id)

        with advisor_opener.open(self._request("POST", f"/api/office-hours/{request_id}/accept", {"comment": ""})):
            pass

        second_req = self._request("POST", f"/api/office-hours/{request_id}/reject", {"comment": ""})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            advisor_opener.open(second_req)
        self.assertEqual(ctx.exception.code, 400)

    def test_past_requested_time_is_rejected(self):
        student_opener, advisor_opener = self._make_student_and_advisor()
        advisor_id = self._advisor_id(advisor_opener)

        create_req = self._request(
            "POST",
            "/api/office-hours",
            {"advisor_id": advisor_id, "requested_at": self._future(-1), "reason": "Too late"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            student_opener.open(create_req)
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
