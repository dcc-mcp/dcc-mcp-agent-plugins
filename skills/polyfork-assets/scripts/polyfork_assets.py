"""Public single-GLB acquisition with an integrity-checked private project cache."""

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request
import uuid

ORIGIN = "https://polyfork.dev"
MAX_METADATA = 1024 * 1024
MAX_GLB = 32 * 1024 * 1024
SKILL_ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward an asset request or ambient access to another URL."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, maximum):
    """Bound public reads; do not authenticate, retry or execute provider content."""
    req = urllib.request.Request(url, headers={"User-Agent": "dcc-mcp-polyfork-assets/0.1", "Accept": "application/json, model/gltf-binary"})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
        body = response.read(maximum + 1)
        if len(body) > maximum:
            raise ValueError("response exceeds the size limit")
        return body, {key.lower(): value for key, value in response.headers.items()}


def identifier(value):
    """Accept a single catalog slug, never a URL or filesystem path."""
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) or len(value) > 100:
        raise ValueError("invalid asset identifier")
    return value


def plain(path):
    """Reject links and Windows reparse points in cache-managed paths."""
    if path.is_symlink() or (os.name == "nt" and path.exists() and
                             os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("linked cache paths are not supported")


def validate_glb(body):
    """Check the actual GLB container and disallow external file/network resources."""
    if not 20 <= len(body) <= MAX_GLB:
        raise ValueError("invalid GLB size")
    magic, version, size = struct.unpack_from("<4sII", body)
    if magic != b"glTF" or version != 2 or size != len(body):
        raise ValueError("download is not a complete GLB 2 container")
    offset = 12
    document = None
    while offset < size:
        if offset + 8 > size:
            raise ValueError("truncated GLB chunk")
        length, kind = struct.unpack_from("<I4s", body, offset)
        end = offset + 8 + length
        if length % 4 or end > size:
            raise ValueError("invalid GLB chunk length")
        if offset == 12:
            if kind != b"JSON" or length > MAX_METADATA:
                raise ValueError("missing or oversized GLB JSON chunk")
            document = json.loads(body[offset + 8:end])
        elif kind != b"BIN\x00":
            raise ValueError("unsupported GLB chunk")
        offset = end
    if not isinstance(document, dict) or document.get("asset", {}).get("version") != "2.0":
        raise ValueError("invalid glTF document")
    for section in ("images", "buffers"):
        for resource in document.get(section, []):
            uri = resource.get("uri")
            if uri is not None and (not isinstance(uri, str) or not uri.startswith("data:")):
                raise ValueError("external GLB resources are not supported")


def inspect_asset(asset_id, fetch=request):
    """Inspect one current public item; return metadata without fetching an asset."""
    asset_id = identifier(asset_id)
    raw, _ = fetch(f"{ORIGIN}/api/assets/{asset_id}", MAX_METADATA)
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("id") != asset_id:
        raise ValueError("catalog response does not match the requested asset")
    return data, hashlib.sha256(raw).hexdigest()


def search(query, limit=3, max_triangles=5000):
    """Read one bounded compact page; never paginate or download the results."""
    if not isinstance(query, str) or not query.strip() or len(query) > 256 or not 1 <= limit <= 5 or max_triangles <= 0:
        raise ValueError("invalid bounded search")
    params = urllib.parse.urlencode({"q": query, "free": 1, "per_page": limit, "fields": "compact", "max_triangles": max_triangles})
    raw, _ = request(f"{ORIGIN}/api/assets?{params}", MAX_METADATA)
    result = json.loads(raw)
    rows = result.get("assets")
    if not isinstance(rows, list) or len(rows) > limit:
        raise ValueError("unexpected search result inventory")
    fields = ("id", "title", "free", "plan", "triangles", "size_m", "page")
    return {"coverage": result.get("coverage"), "strong_matches": result.get("strong_matches"),
            "assets": [{key: item.get(key) for key in fields} for item in rows]}


def acquire(asset_id, project):
    """Acquire once per authorized project; a valid cache hit performs no HTTP."""
    asset_id = identifier(asset_id)
    project = Path(project).resolve(strict=True)
    if not project.is_dir() or project == SKILL_ROOT or SKILL_ROOT in project.parents:
        raise ValueError("use an existing private project outside the Skill")
    cache = project / ".polyfork"
    plain(cache)
    cache.mkdir(exist_ok=True)
    ignore = cache / ".gitignore"
    plain(ignore)
    if ignore.exists():
        if ignore.read_text(encoding="utf-8").strip() != "*":
            raise ValueError("cache must remain fully ignored by Git")
    else:
        ignore.write_text("*\n", encoding="utf-8")
    lock = cache / ".lock"
    plain(lock)
    token = uuid.uuid4().hex
    with lock.open("x", encoding="utf-8") as output:
        output.write(token)
    temporary = None
    try:
        manifest_path = cache / "manifest.json"
        asset_path = cache / f"{asset_id}.glb"
        plain(manifest_path)
        plain(asset_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"schema_version": 1, "assets": {}}
        if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1 or not isinstance(manifest.get("assets"), dict):
            raise ValueError("invalid project asset manifest")
        entry = manifest["assets"].get(asset_id)
        if entry is not None:
            if not isinstance(entry, dict) or entry.get("file") != asset_path.name or entry.get("asset_id") != asset_id:
                raise ValueError("invalid cached asset receipt")
            if entry.get("provider") != "Polyfork" or entry.get("format") != "glb" or \
                    entry.get("metadata_url") != f"{ORIGIN}/api/assets/{asset_id}" or \
                    entry.get("download_url") != f"{ORIGIN}/cdn/{asset_id}.glb" or \
                    entry.get("license_url") != f"{ORIGIN}/licensing":
                raise ValueError("cached provenance differs from the official source")
            if not asset_path.is_file() or asset_path.stat().st_size > MAX_GLB:
                raise ValueError("cached asset is missing or oversized; inspect before retry")
            body = asset_path.read_bytes()
            if hashlib.sha256(body).hexdigest() != entry.get("sha256") or len(body) != entry.get("bytes"):
                raise ValueError("cached asset integrity mismatch; inspect before retry")
            validate_glb(body)
            return {"cache_hit": True, "http_requests": 0, "asset_downloads": 0,
                    "path": str(asset_path), "asset": entry}
        if asset_path.exists():
            raise ValueError("unmanaged cached asset; inspect before retry")
        calls = 0

        def fetch(url, maximum):
            nonlocal calls
            calls += 1
            return request(url, maximum)

        info, metadata_hash = inspect_asset(asset_id, fetch)
        price = info.get("price_usd")
        if info.get("free") is not True or info.get("plan") != "free" or type(price) not in (int, float) or price != 0:
            raise ValueError("paid or unconfirmed price: separate confirmation required")
        download = info.get("download", {})
        url = f"{ORIGIN}/cdn/{asset_id}.glb"
        if download.get("auth") != "none" or download.get("glb") != url or not isinstance(info.get("license"), str) or not info["license"].strip() or len(info["license"]) > 4096:
            raise ValueError("public GLB URL/auth/license is unconfirmed; inspect before download")
        body, headers = fetch(url, MAX_GLB)
        validate_glb(body)
        entry = {"provider": "Polyfork", "asset_id": asset_id, "edition": "free-low-poly", "format": "glb",
                 "file": asset_path.name, "metadata_url": f"{ORIGIN}/api/assets/{asset_id}", "download_url": url,
                 "license_url": f"{ORIGIN}/licensing", "license_notice": info["license"],
                 "observed_at": datetime.now(timezone.utc).isoformat(), "published_at": info.get("published_at"),
                 "provider_revision": None, "version_pin": "sha256", "metadata_sha256": metadata_hash,
                 "etag": headers.get("etag"), "last_modified": headers.get("last-modified"),
                 "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
        with tempfile.NamedTemporaryFile(dir=cache, suffix=".part", delete=False) as output:
            temporary = Path(output.name)
            output.write(body)
        temporary.replace(asset_path)
        temporary = None
        manifest["assets"][asset_id] = entry
        # An interrupted two-file commit leaves an unmanaged asset and fails closed.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache, suffix=".part", delete=False) as output:
            temporary = Path(output.name)
            json.dump(manifest, output, indent=2)
        temporary.replace(manifest_path)
        temporary = None
        return {"cache_hit": False, "http_requests": calls, "asset_downloads": 1,
                "path": str(asset_path), "asset": entry}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if lock.read_text(encoding="utf-8") == token:
            lock.unlink()


def main():
    """Expose search/inspect/fetch only; no auth, installation, bulk or execution commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    query = commands.add_parser("search")
    query.add_argument("--query", required=True)
    query.add_argument("--limit", type=int, default=3)
    query.add_argument("--max-triangles", type=int, default=5000)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("asset_id")
    get = commands.add_parser("fetch")
    get.add_argument("asset_id")
    get.add_argument("--project-dir", required=True)
    args = parser.parse_args()
    try:
        if args.command == "search":
            result = search(args.query, args.limit, args.max_triangles)
        elif args.command == "inspect":
            info, digest = inspect_asset(args.asset_id)
            result = {key: info.get(key) for key in ("id", "free", "plan", "price_usd", "download", "export_formats", "license", "published_at", "size_m", "triangles", "origin_y", "has_night", "params_url")}
            result["metadata_sha256"] = digest
        else:
            result = acquire(args.asset_id, args.project_dir)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        status = error.code if isinstance(error, urllib.error.HTTPError) else None
        print(json.dumps({"success": False, "error": "asset_acquisition_failed", "http_status": status,
                          "detail": str(error) if isinstance(error, ValueError) else type(error).__name__}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
