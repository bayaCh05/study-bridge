"""SQLite connection helper and schema setup.

Each request gets its own connection: sqlite3 connections cannot safely be
shared across threads, and ThreadingHTTPServer runs every request in its
own thread, so "one connection per request" is the natural fit.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from studybridge import config

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    # Off by default in sqlite3; without it, deleting a user would silently
    # leave orphaned sessions/bookings behind instead of cascading or erroring.
    conn.execute("PRAGMA foreign_keys = ON")
    # If two requests hit the DB at the same instant, wait up to 5s for the
    # lock instead of failing immediately with "database is locked".
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    """Create any tables that don't exist yet. Safe to call on every startup."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()
    finally:
        conn.close()


@contextmanager
def transaction(conn):
    """Run a block of writes as one transaction: commit on success, roll back on error."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
