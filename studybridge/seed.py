"""Create one demo user per role and print their credentials.

Run: python3 -m studybridge.seed
Safe to run more than once: existing emails are skipped.
"""

from studybridge import db, timeutil
from studybridge.auth import hash_password

DEMO_USERS = [
    # (full_name, email, password, role)
    ("Sara Student", "student@studybridge.test", "student123", "student"),
    ("Tariq Tutor", "tutor@studybridge.test", "tutor123", "tutor"),
    ("Amina Advisor", "advisor@studybridge.test", "advisor123", "advisor"),
    ("Malik Management", "management@studybridge.test", "management123", "management"),
]


def seed():
    db.init_db()
    conn = db.get_connection()
    try:
        now = timeutil.now_iso()
        for full_name, email, password, role in DEMO_USERS:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                print(f"skip   {role:<10} {email} (already exists)")
                continue
            password_hash, salt = hash_password(password)
            conn.execute(
                """
                INSERT INTO users (full_name, email, password_hash, salt, role, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (full_name, email, password_hash, salt, role, now),
            )
            print(f"create {role:<10} {email} / {password}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
