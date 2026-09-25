"""Step 3 tests: management-only user CRUD."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import HTTPCookieProcessor, build_opener

from studybridge import auth, config, db, timeutil
from studybridge.server import StudyBridgeHandler


class TestStep3Management(unittest.TestCase):
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
        # Fresh users per test so tests don't step on each other's data.
        self.mgmt_email = self._unique_email("mgmt")
        self.student_email = self._unique_email("student")
        self._create_user(self.mgmt_email, "mgmt-pass", "management")
        self._create_user(self.student_email, "student-pass", "student")

    @classmethod
    def _unique_email(cls, prefix):
        cls._counter += 1
        return f"{prefix}{cls._counter}@test.com"

    @staticmethod
    def _create_user(email, password, role, is_active=1):
        password_hash, salt = auth.hash_password(password)
        conn = db.get_connection()
        conn.execute(
            """
            INSERT INTO users (full_name, email, password_hash, salt, role, is_active, created_at)
            VALUES ('Test User', ?, ?, ?, ?, ?, ?)
            """,
            (email, password_hash, salt, role, is_active, timeutil.now_iso()),
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

    def test_anonymous_cannot_list_users(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"{self.base_url}/api/users")
        self.assertEqual(ctx.exception.code, 401)

    def test_student_cannot_list_users(self):
        opener = self._login(self.student_email, "student-pass")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(f"{self.base_url}/api/users")
        self.assertEqual(ctx.exception.code, 403)

    def test_management_can_create_list_update_and_delete_a_user(self):
        opener = self._login(self.mgmt_email, "mgmt-pass")
        new_email = self._unique_email("newtutor")

        create_req = self._request(
            "POST",
            "/api/users",
            {"full_name": "New Tutor", "email": new_email, "password": "tutor-pass", "role": "tutor"},
        )
        with opener.open(create_req) as response:
            self.assertEqual(response.status, 201)
            created = json.loads(response.read())
            self.assertEqual(created["role"], "tutor")
            user_id = created["id"]

        with opener.open(f"{self.base_url}/api/users?role=tutor") as response:
            data = json.loads(response.read())
            self.assertTrue(any(u["email"] == new_email for u in data["users"]))

        update_req = self._request(
            "PUT", f"/api/users/{user_id}", {"full_name": "Renamed Tutor", "email": new_email, "role": "tutor"}
        )
        with opener.open(update_req) as response:
            self.assertEqual(json.loads(response.read())["full_name"], "Renamed Tutor")

        with opener.open(self._request("POST", f"/api/users/{user_id}/deactivate")) as response:
            self.assertFalse(json.loads(response.read())["is_active"])

        with opener.open(self._request("POST", f"/api/users/{user_id}/reactivate")) as response:
            self.assertTrue(json.loads(response.read())["is_active"])

        with opener.open(self._request("DELETE", f"/api/users/{user_id}")) as response:
            self.assertEqual(response.status, 200)

        with opener.open(f"{self.base_url}/api/users?search={new_email}") as response:
            self.assertEqual(json.loads(response.read())["users"], [])

    def test_duplicate_email_on_create_is_409(self):
        opener = self._login(self.mgmt_email, "mgmt-pass")
        create_req = self._request(
            "POST",
            "/api/users",
            {"full_name": "Duplicate", "email": self.student_email, "password": "whatever", "role": "student"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(create_req)
        self.assertEqual(ctx.exception.code, 409)

    def test_duplicate_email_on_update_is_409(self):
        opener = self._login(self.mgmt_email, "mgmt-pass")
        conn = db.get_connection()
        student_id = conn.execute("SELECT id FROM users WHERE email = ?", (self.student_email,)).fetchone()["id"]
        conn.close()

        update_req = self._request(
            "PUT",
            f"/api/users/{student_id}",
            {"full_name": "Renamed", "email": self.mgmt_email, "role": "student"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(update_req)
        self.assertEqual(ctx.exception.code, 409)

    def test_management_cannot_deactivate_self(self):
        opener = self._login(self.mgmt_email, "mgmt-pass")
        conn = db.get_connection()
        my_id = conn.execute("SELECT id FROM users WHERE email = ?", (self.mgmt_email,)).fetchone()["id"]
        conn.close()

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(self._request("POST", f"/api/users/{my_id}/deactivate"))
        self.assertEqual(ctx.exception.code, 400)

    def test_management_cannot_delete_self(self):
        opener = self._login(self.mgmt_email, "mgmt-pass")
        conn = db.get_connection()
        my_id = conn.execute("SELECT id FROM users WHERE email = ?", (self.mgmt_email,)).fetchone()["id"]
        conn.close()

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(self._request("DELETE", f"/api/users/{my_id}"))
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
