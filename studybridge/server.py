"""The HTTP server: request handler, static file serving, JSON helpers.

This module has no framework underneath it — BaseHTTPRequestHandler is a
class from the Python standard library that already knows how to parse an
HTTP request line and headers off the socket and call one of our methods
(do_GET, do_POST, ...). We just fill in what happens next.
"""

import json
import logging
import mimetypes
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from studybridge import config, db
from studybridge.router import MethodNotAllowed, RouteNotFound, router

# Importing this registers every /api/... route on `router` as a side
# effect (each api/*.py module calls router.add(...) at import time).
from studybridge import api  # noqa: F401,E402

logger = logging.getLogger("studybridge")

# Static HTML pages served at a clean path instead of under /static/.
# Role dashboards are added to this list as they're built in later steps.
PAGE_ROUTES = {
    "/login": "login.html",
    "/student": "student.html",
    "/tutor": "tutor.html",
    "/advisor": "advisor.html",
    "/management": "management.html",
}


class StudyBridgeHandler(BaseHTTPRequestHandler):
    # BaseHTTPRequestHandler calls log_message() for every request by
    # default, which prints straight to stderr. We replace that with our
    # own line (method, path, status, duration) via the `logging` module,
    # so we override it here and make it a no-op.
    def log_message(self, format, *args):
        pass

    # send_response() is called by every send_json()/send_file() below.
    # We intercept it just to remember the status code for our request log.
    def send_response(self, code, message=None):
        self._status_code = code
        super().send_response(code)

    # --- HTTP verb entry points -------------------------------------
    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    # --- Response helpers, used by this module and by future API code
    def send_json(self, status, data, headers=None):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers or []:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        """Read and parse a JSON request body. Returns {} if there is none."""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def send_file(self, path):
        content_type, _ = mimetypes.guess_type(str(path))
        content_type = content_type or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # --- Static files, with path traversal protection -----------------
    def _serve_static(self, relative_path):
        if relative_path == "":
            relative_path = "index.html"

        static_root = config.STATIC_DIR.resolve()
        candidate = (static_root / relative_path).resolve()

        # If resolving ".." pushed us outside static/, refuse it.
        try:
            candidate.relative_to(static_root)
        except ValueError:
            self.send_json(404, {"error": "Not found"})
            return

        if not candidate.is_file():
            self.send_json(404, {"error": "Not found"})
            return

        self.send_file(candidate)

    # --- Main dispatch --------------------------------------------------
    def _handle(self):
        start = time.monotonic()
        path = self.path.split("?", 1)[0]

        try:
            if path == "/":
                self._serve_static("")
            elif path.startswith("/static/"):
                self._serve_static(path[len("/static/") :])
            elif path == "/health":
                self._handle_health()
            elif path in PAGE_ROUTES:
                self._serve_static(PAGE_ROUTES[path])
            else:
                self._dispatch_api(path)
        except Exception:
            logger.exception("Unhandled error while serving %s %s", self.command, path)
            self.send_json(500, {"error": "Internal server error"})
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            status = getattr(self, "_status_code", "-")
            logger.info("%s %s %s %.1fms", self.command, path, status, duration_ms)

    def _handle_health(self):
        try:
            conn = db.get_connection()
            try:
                conn.execute("SELECT 1")
            finally:
                conn.close()
            self.send_json(200, {"status": "ok", "database": "ok"})
        except sqlite3.Error:
            logger.exception("Database health check failed")
            self.send_json(503, {"status": "ok", "database": "down"})

    def _dispatch_api(self, path):
        try:
            handler, params = router.resolve(self.command, path)
        except RouteNotFound:
            self.send_json(404, {"error": "Not found"})
            return
        except MethodNotAllowed:
            self.send_json(405, {"error": "Method not allowed"})
            return
        handler(self, params)


def run_server():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    db.init_db()
    server = ThreadingHTTPServer((config.HOST, config.PORT), StudyBridgeHandler)
    logger.info("Study Bridge listening on %s:%s", config.HOST, config.PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server.server_close()
