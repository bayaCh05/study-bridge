"""The HTTP server: request handler, static file serving, JSON helpers.

This module has no framework underneath it — BaseHTTPRequestHandler is a
class from the Python standard library that already knows how to parse an
HTTP request line and headers off the socket and call one of our methods
(do_GET, do_POST, ...). We just fill in what happens next.
"""

import json
import logging
import logging.handlers
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


class PayloadTooLarge(Exception):
    """Raised by read_json() when Content-Length exceeds config.MAX_BODY_SIZE."""


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
    # socketserver.StreamRequestHandler reads this in setup() and calls
    # self.connection.settimeout(self.timeout) — a client that connects and
    # then goes silent (or trickles bytes forever) gets disconnected instead
    # of tying up one of the server's threads indefinitely.
    timeout = config.REQUEST_TIMEOUT_SECONDS

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
        if length > config.MAX_BODY_SIZE:
            # The client is still writing this body over the same socket we'd
            # send a 413 on. If we respond without reading it, the client's
            # write gets a broken pipe instead of ever seeing our response —
            # so drain it first, then reject.
            self._drain(length)
            raise PayloadTooLarge()
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _drain(self, length):
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

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
        except PayloadTooLarge:
            self.send_json(413, {"error": "Request body is too large"})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Invalid JSON in request body"})
        except sqlite3.OperationalError:
            # e.g. the DB file was moved/renamed, or the disk is briefly
            # locked by another writer for longer than busy_timeout — a
            # real but transient outage, distinct from a bug in our code.
            logger.exception("Database error while serving %s %s", self.command, path)
            self.send_json(503, {"error": "Service temporarily unavailable, please try again"})
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


def _configure_logging():
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Rotate at 1 MB, keep 3 old copies, so logs/ doesn't grow unbounded on
    # a long-running VM deployment.
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_DIR / "server.log", maxBytes=1_000_000, backupCount=3
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def run_server():
    _configure_logging()
    db.init_db()
    server = ThreadingHTTPServer((config.HOST, config.PORT), StudyBridgeHandler)
    logger.info("Study Bridge listening on %s:%s", config.HOST, config.PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server.server_close()
