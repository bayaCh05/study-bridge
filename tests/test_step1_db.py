"""Step 1 tests: schema creation and the constraints the data model relies on.

Each test gets its own temporary SQLite file so tests never touch the real
data/studybridge.db and never interfere with each other.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studybridge import config, db


class TestStep1Database(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(config, "DATA_DIR", Path(self.tmp_dir.name)),
            patch.object(config, "DB_PATH", Path(self.tmp_dir.name) / "test.db"),
        ]
        for p in self.patches:
            p.start()
        db.init_db()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp_dir.cleanup()

    @staticmethod
    def _insert_user(conn, email, role):
        conn.execute(
            """
            INSERT INTO users (full_name, email, password_hash, salt, role, is_active, created_at)
            VALUES ('Test User', ?, 'hash', 'salt', ?, 1, '2026-01-01T00:00:00+00:00')
            """,
            (email, role),
        )

    def test_schema_creates_all_tables(self):
        conn = db.get_connection()
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        expected = {
            "users",
            "sessions",
            "availability",
            "bookings",
            "session_reports",
            "office_hour_requests",
            "letters",
        }
        self.assertTrue(expected.issubset(tables))

    def test_bad_role_is_rejected(self):
        conn = db.get_connection()
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_user(conn, "wizard@test.com", "wizard")
        conn.close()

    def test_double_booking_is_rejected(self):
        conn = db.get_connection()
        self._insert_user(conn, "tutor@test.com", "tutor")
        self._insert_user(conn, "student1@test.com", "student")
        self._insert_user(conn, "student2@test.com", "student")
        conn.commit()

        tutor_id = conn.execute("SELECT id FROM users WHERE email = 'tutor@test.com'").fetchone()["id"]
        student1_id = conn.execute("SELECT id FROM users WHERE email = 'student1@test.com'").fetchone()["id"]
        student2_id = conn.execute("SELECT id FROM users WHERE email = 'student2@test.com'").fetchone()["id"]

        conn.execute(
            "INSERT INTO availability (tutor_id, start_at, end_at) VALUES (?, ?, ?)",
            (tutor_id, "2030-01-01T10:00:00+01:00", "2030-01-01T11:00:00+01:00"),
        )
        conn.commit()
        availability_id = conn.execute("SELECT id FROM availability").fetchone()["id"]

        conn.execute(
            """
            INSERT INTO bookings (student_id, availability_id, subject, status, created_at, updated_at)
            VALUES (?, ?, 'Math', 'pending', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """,
            (student1_id, availability_id),
        )
        conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO bookings (student_id, availability_id, subject, status, created_at, updated_at)
                VALUES (?, ?, 'Physics', 'pending', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """,
                (student2_id, availability_id),
            )
        conn.close()


if __name__ == "__main__":
    unittest.main()
