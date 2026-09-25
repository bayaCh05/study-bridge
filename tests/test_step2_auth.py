"""Step 2 tests: login, logout, /api/me, and the require_roles guard."""

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


class TestStep2Auth(unittest.TestCase):
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
        cls._create_user("active@test.com", "correct-password", "student", is_active=1)
        cls._create_user("inactive@test.com", "correct-password", "student", is_active=0)

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

    def _login_request(self, email, password):
        return urllib.request.Request(
            f"{self.base_url}/api/login",
            data=json.dumps({"email": email, "password": password}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def test_login_with_correct_credentials_succeeds(self):
        jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))
        with opener.open(self._login_request("active@test.com", "correct-password")) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read())
            self.assertEqual(data["role"], "student")
        self.assertTrue(any(c.name == "session_token" for c in jar))

    def test_login_with_wrong_password_fails(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self._login_request("active@test.com", "wrong-password"))
        self.assertEqual(ctx.exception.code, 401)

    def test_wrong_email_and_wrong_password_give_the_same_error(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx_unknown_email:
            urllib.request.urlopen(self._login_request("nobody@test.com", "whatever"))
        unknown_email_error = json.loads(ctx_unknown_email.exception.read())["error"]

        with self.assertRaises(urllib.error.HTTPError) as ctx_wrong_password:
            urllib.request.urlopen(self._login_request("active@test.com", "wrong-password"))
        wrong_password_error = json.loads(ctx_wrong_password.exception.read())["error"]

        self.assertEqual(ctx_unknown_email.exception.code, ctx_wrong_password.exception.code)
        self.assertEqual(unknown_email_error, wrong_password_error)

    def test_inactive_user_cannot_login(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self._login_request("inactive@test.com", "correct-password"))
        self.assertEqual(ctx.exception.code, 401)

    def test_me_without_cookie_is_401(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"{self.base_url}/api/me")
        self.assertEqual(ctx.exception.code, 401)

    def test_login_then_me_then_logout_then_me_again(self):
        jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))

        with opener.open(self._login_request("active@test.com", "correct-password")) as response:
            self.assertEqual(response.status, 200)

        with opener.open(f"{self.base_url}/api/me") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["email"], "active@test.com")

        logout_request = urllib.request.Request(f"{self.base_url}/api/logout", data=b"{}", method="POST")
        with opener.open(logout_request) as response:
            self.assertEqual(response.status, 200)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(f"{self.base_url}/api/me")
        self.assertEqual(ctx.exception.code, 401)

    def test_expired_session_is_401(self):
        conn = db.get_connection()
        user_id = conn.execute("SELECT id FROM users WHERE email = 'active@test.com'").fetchone()["id"]
        expired_token = "e" * 64
        past = (timeutil.now() - timedelta(hours=1)).isoformat()
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (expired_token, user_id, past, past),
        )
        conn.commit()
        conn.close()

        request = urllib.request.Request(
            f"{self.base_url}/api/me", headers={"Cookie": f"session_token={expired_token}"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request)
        self.assertEqual(ctx.exception.code, 401)


class TestRequireRolesGuard(unittest.TestCase):
    """require_roles() is exercised directly here: no role-restricted API
    route exists yet (that arrives in Step 3 with management CRUD), so this
    is the only way to test the 403 branch right now."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(config, "DATA_DIR", Path(self.tmp_dir.name)),
            patch.object(config, "DB_PATH", Path(self.tmp_dir.name) / "test.db"),
        ]
        for p in self.patches:
            p.start()
        db.init_db()

        password_hash, salt = auth.hash_password("secret")
        self.conn = db.get_connection()
        self.conn.execute(
            """
            INSERT INTO users (full_name, email, password_hash, salt, role, is_active, created_at)
            VALUES ('Tutor One', 'tutor@test.com', ?, ?, 'tutor', 1, ?)
            """,
            (password_hash, salt, timeutil.now_iso()),
        )
        self.conn.commit()
        user_id = self.conn.execute("SELECT id FROM users WHERE email = 'tutor@test.com'").fetchone()["id"]
        self.token, _ = auth.create_session(self.conn, user_id)

    def tearDown(self):
        self.conn.close()
        for p in self.patches:
            p.stop()
        self.tmp_dir.cleanup()

    @staticmethod
    def _fake_handler(cookie_value=None):
        class FakeHandler:
            def __init__(self):
                self.headers = {"Cookie": f"session_token={cookie_value}"} if cookie_value else {}
                self.sent = None

            def send_json(self, status, data, headers=None):
                self.sent = (status, data)

        return FakeHandler()

    def test_no_cookie_is_401(self):
        handler = self._fake_handler()
        user = auth.require_roles(handler, self.conn, "tutor")
        self.assertIsNone(user)
        self.assertEqual(handler.sent[0], 401)

    def test_wrong_role_is_403(self):
        handler = self._fake_handler(self.token)
        user = auth.require_roles(handler, self.conn, "management")
        self.assertIsNone(user)
        self.assertEqual(handler.sent[0], 403)

    def test_correct_role_is_allowed(self):
        handler = self._fake_handler(self.token)
        user = auth.require_roles(handler, self.conn, "tutor")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "tutor")


if __name__ == "__main__":
    unittest.main()
