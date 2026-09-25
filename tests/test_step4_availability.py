"""Step 4 tests: tutor availability — overlap, past slots, ownership."""

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


class TestStep4Availability(unittest.TestCase):
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

    def setUp(self):
        self.tutor1_email = self._unique_email("tutor1")
        self.tutor2_email = self._unique_email("tutor2")
        self._create_user(self.tutor1_email, "pass1234", "tutor")
        self._create_user(self.tutor2_email, "pass1234", "tutor")

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
            VALUES ('Test User', ?, ?, ?, ?, 1, ?)
            """,
            (email, password_hash, salt, role, timeutil.now_iso()),
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
    def _future(hours_from_now, plus_minutes=0):
        dt = timeutil.now() + timedelta(hours=hours_from_now, minutes=plus_minutes)
        return dt.strftime("%Y-%m-%dT%H:%M")

    def test_can_create_and_list_a_future_slot(self):
        opener = self._login(self.tutor1_email, "pass1234")
        create_req = self._request(
            "POST", "/api/availability", {"start_at": self._future(24), "end_at": self._future(25)}
        )
        with opener.open(create_req) as response:
            self.assertEqual(response.status, 201)

        with opener.open(f"{self.base_url}/api/availability") as response:
            data = json.loads(response.read())
            self.assertEqual(len(data["slots"]), 1)

    def test_past_slot_is_rejected(self):
        opener = self._login(self.tutor1_email, "pass1234")
        create_req = self._request(
            "POST", "/api/availability", {"start_at": self._future(-2), "end_at": self._future(-1)}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(create_req)
        self.assertEqual(ctx.exception.code, 400)

    def test_end_before_start_is_rejected(self):
        opener = self._login(self.tutor1_email, "pass1234")
        create_req = self._request(
            "POST", "/api/availability", {"start_at": self._future(25), "end_at": self._future(24)}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(create_req)
        self.assertEqual(ctx.exception.code, 400)

    def test_overlapping_slot_is_rejected(self):
        opener = self._login(self.tutor1_email, "pass1234")
        first = self._request(
            "POST", "/api/availability", {"start_at": self._future(24), "end_at": self._future(26)}
        )
        with opener.open(first):
            pass

        # Overlaps: starts in the middle of the first slot.
        overlapping = self._request(
            "POST", "/api/availability", {"start_at": self._future(25), "end_at": self._future(27)}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(overlapping)
        self.assertEqual(ctx.exception.code, 400)

    def test_non_overlapping_slot_is_accepted(self):
        opener = self._login(self.tutor1_email, "pass1234")
        first = self._request(
            "POST", "/api/availability", {"start_at": self._future(24), "end_at": self._future(25)}
        )
        with opener.open(first):
            pass

        second = self._request(
            "POST", "/api/availability", {"start_at": self._future(26), "end_at": self._future(27)}
        )
        with opener.open(second) as response:
            self.assertEqual(response.status, 201)

    def test_tutor_cannot_delete_another_tutors_slot(self):
        opener1 = self._login(self.tutor1_email, "pass1234")
        create_req = self._request(
            "POST", "/api/availability", {"start_at": self._future(24), "end_at": self._future(25)}
        )
        with opener1.open(create_req) as response:
            slot_id = json.loads(response.read())["id"]

        opener2 = self._login(self.tutor2_email, "pass1234")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener2.open(self._request("DELETE", f"/api/availability/{slot_id}"))
        self.assertEqual(ctx.exception.code, 403)

    def test_tutor_can_delete_own_slot(self):
        opener = self._login(self.tutor1_email, "pass1234")
        create_req = self._request(
            "POST", "/api/availability", {"start_at": self._future(24), "end_at": self._future(25)}
        )
        with opener.open(create_req) as response:
            slot_id = json.loads(response.read())["id"]

        with opener.open(self._request("DELETE", f"/api/availability/{slot_id}")) as response:
            self.assertEqual(response.status, 200)

        with opener.open(f"{self.base_url}/api/availability") as response:
            self.assertEqual(json.loads(response.read())["slots"], [])


if __name__ == "__main__":
    unittest.main()
