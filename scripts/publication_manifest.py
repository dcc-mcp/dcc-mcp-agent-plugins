"""The canonical Skill-directory to publication-manifest contract."""

from __future__ import annotations

import json
import re
from pathlib import Path

CANONICAL_ROOT = "plugins/dcc-mcp/skills"
MANIFEST_PATH = ".github/clawhub-skills.json"
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def validate_manifest_coverage(entries: object, canonical_paths: set[str]) -> list[dict]:
    """Require each canonical directory to have exactly one named entry."""
    if not isinstance(entries, list) or not entries:
        raise ValueError("ClawHub manifest requires a non-empty skills array")
    paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("ClawHub manifest entries must be objects")
        slug = entry.get("slug")
        if not isinstance(slug, str) or len(slug) > 64 or not SLUG_RE.fullmatch(slug):
            raise ValueError(f"invalid canonical Skill slug: {slug!r}")
        expected_path = f"{CANONICAL_ROOT}/{slug}"
        if entry.get("path") != expected_path:
            raise ValueError(f"Skill {slug} must use canonical path {expected_path}")
        if expected_path in paths:
            raise ValueError(f"duplicate canonical Skill entry: {slug}")
        paths.add(expected_path)
    if paths != canonical_paths:
        raise ValueError(
            "canonical Skill coverage mismatch: "
            f"missing={sorted(canonical_paths - paths)}, extra={sorted(paths - canonical_paths)}"
        )
    return entries


def load_canonical_manifest(root: Path) -> list[dict]:
    """Read the canonical publication entries."""
    for relative in (MANIFEST_PATH, CANONICAL_ROOT):
        path = root
        for part in Path(relative).parts:
            path = path / part
            if path.is_symlink():
                raise ValueError(f"symbolic links are not canonical publication paths: {path}")
    entries = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))["skills"]
    canonical_paths = set()
    for directory in (root / CANONICAL_ROOT).iterdir():
        if directory.is_symlink() or (directory / "SKILL.md").is_symlink():
            raise ValueError(f"symbolic links are not canonical Skills: {directory}")
        if directory.is_dir() and (directory / "SKILL.md").is_file():
            canonical_paths.add(directory.relative_to(root).as_posix())
    return validate_manifest_coverage(entries, canonical_paths)
