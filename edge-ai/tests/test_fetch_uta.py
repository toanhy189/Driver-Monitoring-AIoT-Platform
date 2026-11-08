"""Test selective ZIP reads on a local HTTP server, never on real videos."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import re
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import fetch_uta


@contextmanager
def range_server(data, honor_range=True):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request = self.headers.get("Range")
            requests.append(request)
            start, end = map(int, re.fullmatch(r"bytes=(\d+)-(\d+)", request).groups())
            body = data[start:end + 1] if honor_range else data
            self.send_response(206 if honor_range else 200)
            self.send_header("Content-Length", str(len(body)))
            if data.startswith(b"<html"):
                self.send_header("Content-Type", "text/html")
            if honor_range:
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/test.zip", requests
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()


def zip_fixture():
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        for subject in ("01", "02"):
            for label in ("0", "5", "10"):
                archive.writestr(f"Fold1/{subject}/{label}.mp4", (subject + label).encode() * 10000)
        archive.writestr("../../unselected.mp4", b"never extract")
    return target.getvalue()


class FetchTests(unittest.TestCase):
    def test_reader_and_download_only_selected_verified_videos_then_skip(self):
        data = zip_fixture()
        original_reader = fetch_uta.RangeReader
        with range_server(data) as (url, requests), tempfile.TemporaryDirectory() as temporary, \
                patch.object(fetch_uta, "RangeReader", side_effect=lambda *_: original_reader("fixture", url=url)), \
                patch.object(fetch_uta.shutil, "disk_usage", return_value=SimpleNamespace(free=100 * fetch_uta.GIB)):
            catalog = fetch_uta.list_archives({"fixture.zip": "fixture"})
            self.assertEqual(len(catalog["videos"]), 4)
            self.assertEqual({v["label"] for v in catalog["videos"]}, {"0", "10"})
            root = Path(temporary)
            selected = fetch_uta.download(catalog, root, count=1, max_gib=0.1)
            self.assertEqual(len(selected), 2)
            self.assertEqual({p.name for p in (root / "01").iterdir()}, {"0.mp4", "10.mp4"})
            self.assertFalse((root / "02").exists())
            self.assertEqual((root / "01" / "0.mp4").read_bytes(), b"010" * 10000)
            request_count = len(requests)
            fetch_uta.download(catalog, root, count=1, max_gib=0.1)
            self.assertEqual(len(requests), request_count)
            # Reads are ranges; the complete ZIP was never requested.
            self.assertTrue(all(request != f"bytes=0-{len(data) - 1}" for request in requests))

    def test_budget_and_existing_file_protection(self):
        data = zip_fixture()
        with range_server(data) as (url, _), tempfile.TemporaryDirectory() as temporary:
            original_reader = fetch_uta.RangeReader
            with patch.object(fetch_uta, "RangeReader", side_effect=lambda *_: original_reader("fixture", url=url)):
                catalog = fetch_uta.list_archives({"fixture.zip": "fixture"})
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "exceeds"):
                fetch_uta.download(catalog, root, count=1, max_gib=0.000001)
            (root / "01").mkdir()
            (root / "01" / "0.mp4").write_bytes(b"user file")
            with patch.object(fetch_uta.shutil, "disk_usage", return_value=SimpleNamespace(free=100 * fetch_uta.GIB)), \
                    self.assertRaisesRegex(ValueError, "refusing overwrite"):
                fetch_uta.download(catalog, root, count=1, max_gib=0.1)
            self.assertEqual((root / "01" / "0.mp4").read_bytes(), b"user file")
            with self.assertRaises(ValueError):
                fetch_uta.select_videos(catalog, subjects=["missing"])

    def test_server_ignoring_range_is_rejected(self):
        with range_server(zip_fixture(), honor_range=False) as (url, _):
            with self.assertRaisesRegex(ValueError, "Expected HTTP 206"):
                fetch_uta.RangeReader("fixture", url=url)

    def test_quota_stops_without_retrying_or_fetching_full_archive(self):
        with range_server(b"<html><title>Google Drive - Quota exceeded</title></html>", honor_range=False) as (url, requests):
            with self.assertRaises(fetch_uta.DatasetQuotaError):
                fetch_uta.RangeReader("fixture", url=url)
            self.assertEqual(len(requests), 1)

    def test_local_zip_path_needs_no_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "official-copy-fixture.zip"
            archive.write_bytes(zip_fixture())
            with patch.object(fetch_uta, "RangeReader", side_effect=AssertionError("Network attempted")), \
                    patch.object(fetch_uta.shutil, "disk_usage", return_value=SimpleNamespace(free=100 * fetch_uta.GIB)):
                catalog = fetch_uta.list_local_archives([archive])
                fetch_uta.download(catalog, root / "videos", subjects=["02"], max_gib=0.1)
            self.assertEqual((root / "videos" / "02" / "10.mp4").read_bytes(), b"0210" * 10000)
            self.assertFalse((root / "videos" / "01").exists())


if __name__ == "__main__":
    unittest.main()
