"""Step 0 tests: bare server, static files, health check, 404, path traversal.

We start the real ThreadingHTTPServer on a random free port (port 0 tells
the OS to pick one) in a background thread, then hit it with plain
urllib.request calls, just like a browser would.
"""

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from studybridge.server import StudyBridgeHandler


class TestStep0Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StudyBridgeHandler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_index_page_returns_html(self):
        with urllib.request.urlopen(f"{self.base_url}/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers.get("Content-Type", ""))
            body = response.read().decode()
            self.assertIn("Study Bridge", body)

    def test_static_css_file_served(self):
        with urllib.request.urlopen(f"{self.base_url}/static/css/style.css") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/css", response.headers.get("Content-Type", ""))

    def test_health_returns_ok(self):
        with urllib.request.urlopen(f"{self.base_url}/health") as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read())
            self.assertEqual(data["status"], "ok")

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"{self.base_url}/this-does-not-exist")
        self.assertEqual(ctx.exception.code, 404)

    def test_path_traversal_is_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"{self.base_url}/static/../run.py")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
