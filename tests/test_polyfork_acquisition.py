"""Acquisition contracts use original tiny GLBs and local/mocked HTTP only."""

from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/polyfork-assets/scripts/polyfork_assets.py"
spec = importlib.util.spec_from_file_location("polyfork_acquisition", SCRIPT)
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)
ASSET_ID = "test-cube"


def glb(document=None):
    """Create an original empty glTF container, never a provider model."""
    raw = json.dumps(document or {"asset": {"version": "2.0"}}).encode()
    raw += b" " * (-len(raw) % 4)
    return struct.pack("<4sIII4s", b"glTF", 2, 20 + len(raw), len(raw), b"JSON") + raw


class PolyforkAcquisitionTests(unittest.TestCase):
    def setUp(self):
        """Only synthetic public catalog fields and our own container are used."""
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name)
        self.body = glb()
        self.info = {"id": ASSET_ID, "free": True, "plan": "free", "price_usd": 0,
                     "license": "synthetic project-use test notice", "published_at": "2026-01-01",
                     "download": {"auth": "none", "glb": f"{assets.ORIGIN}/cdn/{ASSET_ID}.glb"}}

    def replies(self, info=None, body=None):
        """Model exactly one metadata read and one single-asset download."""
        return [(json.dumps(info or self.info).encode(), {}),
                (body if body is not None else self.body, {"etag": '"test-etag"'})]

    def acquire_once(self):
        """Populate one project through a completely mocked public transport."""
        with patch.object(assets, "request", side_effect=self.replies()) as fetch:
            result = assets.acquire(ASSET_ID, self.project)
        self.assertEqual(fetch.call_count, 2)
        return result

    def test_second_fetch_has_zero_http_and_same_verified_bytes(self):
        """Cache reuse must remain useful even when all networking is forbidden."""
        first = self.acquire_once()
        with patch.object(assets, "request", side_effect=AssertionError("network forbidden")) as fetch:
            second = assets.acquire(ASSET_ID, self.project)
        fetch.assert_not_called()
        self.assertFalse(first["cache_hit"])
        self.assertEqual((first["http_requests"], first["asset_downloads"]), (2, 1))
        self.assertTrue(second["cache_hit"])
        self.assertEqual((second["http_requests"], second["asset_downloads"]), (0, 0))
        self.assertEqual(second["asset"]["sha256"], hashlib.sha256(self.body).hexdigest())
        self.assertIsNone(second["asset"]["provider_revision"])
        self.assertEqual(second["asset"]["etag"], '"test-etag"')
        self.assertEqual((self.project / ".polyfork/.gitignore").read_text().strip(), "*")

    def test_paid_auth_required_and_nonofficial_urls_fail_before_download(self):
        """A declared free search result is not permission to assume item entitlement."""
        for change in ("paid", "price", "login", "url", "missing", "license"):
            with self.subTest(change=change):
                info = deepcopy(self.info)
                if change == "paid":
                    info["free"] = False
                elif change == "price":
                    info["price_usd"] = 1
                elif change == "login":
                    info["download"]["auth"] = "bearer"
                elif change == "url":
                    info["download"]["glb"] = "https://unapproved.invalid/asset.glb"
                elif change == "missing":
                    del info["download"]["glb"]
                else:
                    info["license"] = None
                with patch.object(assets, "request", side_effect=self.replies(info)) as fetch:
                    with self.assertRaises(ValueError):
                        assets.acquire(ASSET_ID, self.project)
                self.assertEqual(fetch.call_count, 1)
                self.assertFalse((self.project / ".polyfork" / f"{ASSET_ID}.glb").exists())

    def test_corrupt_cache_is_preserved_without_network_or_overwrite(self):
        """A broken pin needs inspection, not an automatic redownload."""
        receipt = self.acquire_once()
        cached = Path(receipt["path"])
        cached.write_bytes(b"corrupt")
        with patch.object(assets, "request") as fetch:
            with self.assertRaises(ValueError):
                assets.acquire(ASSET_ID, self.project)
        fetch.assert_not_called()
        self.assertEqual(cached.read_bytes(), b"corrupt")

    def test_tampered_provenance_is_not_accepted_as_a_cache_receipt(self):
        """A matching hash must not conceal a changed source or escaped filename."""
        self.acquire_once()
        manifest = self.project / ".polyfork/manifest.json"
        original = json.loads(manifest.read_text())
        for field, value in (("download_url", "https://unapproved.invalid/a.glb"),
                             ("file", "../outside.glb"), ("license_url", "https://unapproved.invalid/terms")):
            with self.subTest(field=field):
                changed = deepcopy(original)
                changed["assets"][ASSET_ID][field] = value
                manifest.write_text(json.dumps(changed))
                with patch.object(assets, "request") as fetch:
                    with self.assertRaises(ValueError):
                        assets.acquire(ASSET_ID, self.project)
                fetch.assert_not_called()

    def test_existing_lock_and_unmanaged_file_are_preserved(self):
        """Unknown ownership is never permission to delete a lock or overwrite a file."""
        cache = self.project / ".polyfork"
        cache.mkdir()
        lock = cache / ".lock"
        lock.write_text("other-writer")
        with patch.object(assets, "request") as fetch:
            with self.assertRaises(FileExistsError):
                assets.acquire(ASSET_ID, self.project)
        fetch.assert_not_called()
        self.assertEqual(lock.read_text(), "other-writer")
        lock.unlink()
        unmanaged = cache / f"{ASSET_ID}.glb"
        unmanaged.write_bytes(self.body)
        with patch.object(assets, "request") as fetch:
            with self.assertRaises(ValueError):
                assets.acquire(ASSET_ID, self.project)
        fetch.assert_not_called()
        self.assertEqual(unmanaged.read_bytes(), self.body)

    def test_invalid_glb_and_external_resources_never_enter_the_cache(self):
        """Importable files must be actual containers without outside dependencies."""
        for body in (b"not-a-model", self.body[:-1],
                     glb({"asset": {"version": "2.0"}, "images": [{"uri": "file:///private.png"}]})):
            with self.subTest(length=len(body)), patch.object(assets, "request", side_effect=self.replies(body=body)):
                with self.assertRaises(ValueError):
                    assets.acquire(ASSET_ID, self.project)
                self.assertFalse((self.project / ".polyfork" / f"{ASSET_ID}.glb").exists())

    def test_skill_folder_and_asset_path_traversal_are_rejected(self):
        """Never place private provider bytes inside an installable Skill."""
        with patch.object(assets, "request") as fetch:
            for asset_id in ("../asset", "a/b", "https://polyfork.dev/a", "A"):
                with self.subTest(asset_id=asset_id), self.assertRaises(ValueError):
                    assets.acquire(asset_id, self.project)
            with self.assertRaises(ValueError):
                assets.acquire(ASSET_ID, assets.SKILL_ROOT)
        fetch.assert_not_called()

    def test_redirect_is_not_followed_and_user_agent_names_the_client(self):
        """Exercise the real stdlib redirect policy against a loopback fixture."""
        seen = []
        agents = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                """A redirect target would expose a second unexpected request."""
                seen.append(self.path)
                agents.append(self.headers.get("User-Agent"))
                self.send_response(302)
                self.send_header("Location", "/unexpected")
                self.end_headers()

            def log_message(self, *args):
                """Keep fixture logging quiet."""

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(urllib.error.HTTPError):
                assets.request(f"http://127.0.0.1:{server.server_port}/first", 100)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(seen, ["/first"])
        self.assertEqual(agents, ["dcc-mcp-polyfork-assets/0.1"])


if __name__ == "__main__":
    unittest.main()
