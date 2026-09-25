"""Step 8 tests: recommendation letters — access control, PDF check, size limit."""

import base64
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

VALID_PDF_BYTES = b"%PDF-1.4\n%mock pdf content for tests\n%%EOF"


class TestStep8Letters(unittest.TestCase):
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
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (email.split("@")[0], email, password_hash, salt, role, timeutil.now_iso()),
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

    def _make_advisor_and_student(self):
        advisor_email = self._unique_email("advisor")
        student_email = self._unique_email("student")
        self._create_user(advisor_email, "pass1234", "advisor")
        self._create_user(student_email, "pass1234", "student")
        return self._login(advisor_email, "pass1234"), self._login(student_email, "pass1234")

    def _student_id(self, student_opener):
        with student_opener.open(f"{self.base_url}/api/me") as response:
            return json.loads(response.read())["id"]

    def test_advisor_can_upload_a_pdf_letter(self):
        advisor_opener, student_opener = self._make_advisor_and_student()
        student_id = self._student_id(student_opener)

        upload_req = self._request(
            "POST",
            "/api/letters",
            {
                "student_id": student_id,
                "title": "Grad school reference",
                "filename": "letter.pdf",
                "content_base64": base64.b64encode(VALID_PDF_BYTES).decode(),
            },
        )
        with advisor_opener.open(upload_req) as response:
            self.assertEqual(response.status, 201)
            letter = json.loads(response.read())
            self.assertEqual(letter["title"], "Grad school reference")

        with student_opener.open(f"{self.base_url}/api/letters") as response:
            letters = json.loads(response.read())["letters"]
            self.assertEqual(len(letters), 1)

    def test_non_pdf_content_is_rejected(self):
        advisor_opener, student_opener = self._make_advisor_and_student()
        student_id = self._student_id(student_opener)

        upload_req = self._request(
            "POST",
            "/api/letters",
            {
                "student_id": student_id,
                "title": "Not a PDF",
                "filename": "letter.txt",
                "content_base64": base64.b64encode(b"just plain text, not a pdf").decode(),
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            advisor_opener.open(upload_req)
        self.assertEqual(ctx.exception.code, 400)

    def test_oversized_upload_is_413(self):
        advisor_opener, student_opener = self._make_advisor_and_student()
        student_id = self._student_id(student_opener)

        oversized = b"%PDF-1.4\n" + (b"a" * (config.MAX_LETTER_SIZE + 1))
        upload_req = self._request(
            "POST",
            "/api/letters",
            {
                "student_id": student_id,
                "title": "Too big",
                "filename": "big.pdf",
                "content_base64": base64.b64encode(oversized).decode(),
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            advisor_opener.open(upload_req)
        self.assertEqual(ctx.exception.code, 413)

    def test_another_student_cannot_download_the_letter(self):
        advisor_opener, student_opener = self._make_advisor_and_student()
        student_id = self._student_id(student_opener)

        upload_req = self._request(
            "POST",
            "/api/letters",
            {
                "student_id": student_id,
                "title": "Reference",
                "filename": "letter.pdf",
                "content_base64": base64.b64encode(VALID_PDF_BYTES).decode(),
            },
        )
        with advisor_opener.open(upload_req) as response:
            letter_id = json.loads(response.read())["id"]

        other_student_email = self._unique_email("otherstudent")
        self._create_user(other_student_email, "pass1234", "student")
        other_student_opener = self._login(other_student_email, "pass1234")

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            other_student_opener.open(f"{self.base_url}/api/letters/{letter_id}/download")
        self.assertEqual(ctx.exception.code, 403)

    def test_owning_student_can_download_the_letter(self):
        advisor_opener, student_opener = self._make_advisor_and_student()
        student_id = self._student_id(student_opener)

        upload_req = self._request(
            "POST",
            "/api/letters",
            {
                "student_id": student_id,
                "title": "Reference",
                "filename": "letter.pdf",
                "content_base64": base64.b64encode(VALID_PDF_BYTES).decode(),
            },
        )
        with advisor_opener.open(upload_req) as response:
            letter_id = json.loads(response.read())["id"]

        with student_opener.open(f"{self.base_url}/api/letters/{letter_id}/download") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Content-Type"), "application/pdf")
            self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
            self.assertEqual(response.read(), VALID_PDF_BYTES)

    def test_management_can_see_and_download_any_letter(self):
        advisor_opener, student_opener = self._make_advisor_and_student()
        student_id = self._student_id(student_opener)

        upload_req = self._request(
            "POST",
            "/api/letters",
            {
                "student_id": student_id,
                "title": "Reference",
                "filename": "letter.pdf",
                "content_base64": base64.b64encode(VALID_PDF_BYTES).decode(),
            },
        )
        with advisor_opener.open(upload_req) as response:
            letter_id = json.loads(response.read())["id"]

        management_email = self._unique_email("mgmt")
        self._create_user(management_email, "pass1234", "management")
        management_opener = self._login(management_email, "pass1234")

        with management_opener.open(f"{self.base_url}/api/letters") as response:
            letter_ids = [letter["id"] for letter in json.loads(response.read())["letters"]]
            self.assertIn(letter_id, letter_ids)

        with management_opener.open(f"{self.base_url}/api/letters/{letter_id}/download") as response:
            self.assertEqual(response.status, 200)

    def test_only_advisors_can_upload(self):
        _advisor_opener, student_opener = self._make_advisor_and_student()
        student_id = self._student_id(student_opener)

        upload_req = self._request(
            "POST",
            "/api/letters",
            {
                "student_id": student_id,
                "title": "Self-written reference",
                "filename": "letter.pdf",
                "content_base64": base64.b64encode(VALID_PDF_BYTES).decode(),
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            student_opener.open(upload_req)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
