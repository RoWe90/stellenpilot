"""Regression tests: Docker browser downloads replace desktop-only xdg-open calls."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

from helpers import Server
from stellenpilot.config import Settings
from stellenpilot.db import DB
from stellenpilot import schedule
from stellenpilot.server import make_handler, find_doc, make_document_archive


class BrowserDocumentsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.folder = self.home / "output" / "2026-10-25" / "Test Company"
        self.folder.mkdir(parents=True)
        self.cv = self.folder / "Test_CV_Company.pdf"
        self.cv.write_bytes(b"%PDF-1.4\nfake cv content")
        self.letter = self.folder / "Test_Cover_Letter_Company.docx"
        self.letter.write_bytes(b"test docx content")
        self.db = DB(self.home / "jobhunt.db")
        self.assertTrue(self.db.insert_job({
            "id": "ba-10001-1003900679-S",
            "source": "test", "title": "Backend developer", "company": "Test Company",
            "folder": str(self.folder),
        }))
        self.settings = Settings(self.home)
        self.server = Server(make_handler(self.settings))
        self.addCleanup(self.server.close)
        self.addCleanup(self.db.conn.close)
        self.id = "ba-10001-1003900679-S"

    def _post(self, path):
        request = urllib.request.Request(
            self.server.base + path,
            headers={"X-Jobhunt": "1"},
            data=b"{}",
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    def _get(self, path):
        with urllib.request.urlopen(self.server.base + path, timeout=5) as response:
            return response.status, response.headers, response.read()

    def _error(self, path):
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self._get(path)
        with exc.exception as response:
            return response.code

    def test_docker_open_doc_returns_download_and_browser_receives_file(self):
        with mock.patch.object(schedule, "in_docker", return_value=True), \
                mock.patch("stellenpilot.server.open_in_file_manager") as opener:
            result = self._post(f"/api/open-doc/{self.id}/cv")
            self.assertEqual(result["downloadUrl"], f"/api/download-doc/{self.id}/cv")
            opener.assert_not_called()
        code, headers, content = self._get(result["downloadUrl"])
        self.assertEqual(code, 200)
        self.assertEqual(content, self.cv.read_bytes())
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_docker_open_folder_downloads_zip_without_host_file_manager(self):
        with mock.patch.object(schedule, "in_docker", return_value=True), \
                mock.patch("stellenpilot.server.open_in_file_manager") as opener:
            result = self._post(f"/api/open-folder/{self.id}")
            opener.assert_not_called()
        code, headers, content = self._get(result["downloadUrl"])
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(set(archive.namelist()), {self.cv.name, self.letter.name})
            self.assertEqual(archive.read(self.letter.name), self.letter.read_bytes())

    def test_unknown_jobs_and_wrong_kinds_not_downloadable(self):
        self.assertEqual(self._error("/api/download-doc/nonexistent/cv"), 404)
        self.assertEqual(self._error("/api/download-doc/" + self.id + "/secrets"), 404)
        self.assertEqual(self._error("/api/download-folder/nonexistent"), 404)

    def test_new_document_layout_downloads_pdf_and_editable_word_files(self):
        self.cv.unlink()
        self.letter.unlink()
        edit = self.folder / "edit"
        edit.mkdir()
        files = {"Test_CV.pdf": b"new pdf", "edit/Test_CV.docx": b"editable cv",
                 "edit/Test_Cover_Letter.docx": b"editable letter"}
        for name, content in files.items():
            (self.folder / name).write_bytes(content)
        self.assertEqual(self._get(f"/api/download-doc/{self.id}/cv")[2], b"new pdf")
        self.assertEqual(self._get(f"/api/download-doc/{self.id}/letter")[2], b"editable letter")
        with zipfile.ZipFile(io.BytesIO(self._get(f"/api/download-folder/{self.id}")[2])) as archive:
            self.assertEqual(set(archive.namelist()), set(files))
            for name, content in files.items():
                self.assertEqual(archive.read(name), content)

    def test_edit_directory_symlink_cannot_expose_private_documents(self):
        other = self.home / "private"
        other.mkdir()
        (other / "Secret_CV.docx").write_bytes(b"secret")
        try:
            (self.folder / "edit").symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.cv.unlink()
        self.assertEqual(self._error(f"/api/download-doc/{self.id}/cv"), 404)
        with zipfile.ZipFile(io.BytesIO(self._get(f"/api/download-folder/{self.id}")[2])) as archive:
            self.assertEqual(archive.namelist(), [self.letter.name])

    def test_outside_output_and_symlinks_are_not_downloaded(self):
        other = self.home / "private"
        other.mkdir()
        (other / "private_CV_file.pdf").write_bytes(b"secret")
        self.db.insert_job({"id": "outside", "source": "test", "title": "Private",
                            "folder": str(other)})
        self.assertEqual(self._error("/api/download-folder/outside"), 404)
        self.assertEqual(self._error("/api/download-doc/outside/cv"), 404)
        try:
            (self.folder / "Test_CV_Secret.pdf").symlink_to(other / "private_CV_file.pdf")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with zipfile.ZipFile(io.BytesIO(self._get(f"/api/download-folder/{self.id}")[2])) as archive:
            self.assertNotIn("Test_CV_Secret.pdf", archive.namelist())

    def test_archive_size_and_count_are_limited(self):
        with mock.patch("pathlib.Path.stat") as stat:
            stat.return_value.st_size = 100_000_001
            with self.assertRaisesRegex(ValueError, "too large"):
                make_document_archive([self.cv])
        with self.assertRaisesRegex(ValueError, "Too many"):
            make_document_archive([self.cv] * 51)

    def test_desktop_still_uses_native_open(self):
        with mock.patch.object(schedule, "in_docker", return_value=False), \
                mock.patch("stellenpilot.server.open_in_file_manager") as opener:
            result = self._post(f"/api/open-doc/{self.id}/cv")
            self.assertEqual(result, {"ok": True})
            opener.assert_called_once_with(str(self.cv))


if __name__ == "__main__":
    unittest.main()
