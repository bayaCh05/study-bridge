"""Step 9 tests: graceful handling of DB errors and oversized request bodies."""

import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from studybridge import config, db
from studybridge.server import StudyBridgeHandler


class TestStep9Resilience(unittest.TestCase):
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

    def test_health_returns_503_when_db_is_unavailable(self):
        with patch.object(db, "get_connection", side_effect=sqlite3.OperationalError("simulated failure")):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"{self.base_url}/health")
            self.assertEqual(ctx.exception.code, 503)
            data = json.loads(ctx.exception.read())
            self.assertEqual(data["database"], "down")

    def test_any_handler_returns_503_on_a_simulated_db_error(self):
        # /api/me needs no request body and no prior state, so it's a clean
        # way to exercise the generic sqlite3.OperationalError -> 503 path
        # that every handler goes through, not just /health's own check.
        with patch.object(db, "get_connection", side_effect=sqlite3.OperationalError("simulated failure")):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"{self.base_url}/api/me")
            self.assertEqual(ctx.exception.code, 503)
            data = json.loads(ctx.exception.read())
            self.assertIn("error", data)

    def test_health_recovers_once_the_db_is_reachable_again(self):
        with patch.object(db, "get_connection", side_effect=sqlite3.OperationalError("simulated failure")):
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(f"{self.base_url}/health")

        with urllib.request.urlopen(f"{self.base_url}/health") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["database"], "ok")

    def test_oversized_request_body_is_413(self):
        huge_password = "x" * (config.MAX_BODY_SIZE + 1000)
        body = json.dumps({"email": "nobody@test.com", "password": huge_password}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request)
        self.assertEqual(ctx.exception.code, 413)

    def test_malformed_json_body_is_400_not_500(self):
        request = urllib.request.Request(
            f"{self.base_url}/api/login",
            data=b"{not valid json!",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request)
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
