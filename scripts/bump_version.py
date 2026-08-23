"""Bump the Skill suite version across every manifest and SKILL.md.

The suite version is this repository's own release line, decoupled from
`dcc-mcp-core` release numbers. Published Skill versions are immutable, so any
content change needs a bump before the next `v<version>` tag.

Examples:
    python scripts/bump_version.py --patch
    python scripts/bump_version.py --set 0.20.0
    python scripts/bump_version.py --patch --print-only
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from sync_core_skills import VERSION_LINE, frontmatter_lines


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "dcc-mcp"
SEMVER = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")

PLUGIN_MANIFESTS = (
    PLUGIN / "plugin.json",
    PLUGIN / ".codex-plugin" / "plugin.json",
    PLUGIN / ".claude-plugin" / "plugin.json",
    PLUGIN / ".codebuddy-plugin" / "plugin.json",
)
MARKETPLACE_MANIFESTS = (
    ROOT / ".claude-plugin" / "marketplace.json",
    ROOT / ".codebuddy-plugin" / "marketplace.json",
)
CLAWHUB_MANIFEST = ROOT / ".github" / "clawhub-skills.json"


def current_version(root: Path = ROOT) -> str:
    return json.loads((root / "plugins" / "dcc-mcp" / "plugin.json").read_text(encoding="utf-8"))["version"]


def next_version(version: str, part: str) -> str:
    match = SEMVER.fullmatch(version)
    if not match:
        raise ValueError(f"not a semantic version: {version}")
    major, minor, patch = (int(match.group(name)) for name in ("major", "minor", "patch"))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _bump_skill_md(path: Path, version: str) -> bool:
    """Rewrite metadata.dcc-mcp.version in the frontmatter, leaving the body alone."""
    text = path.read_text(encoding="utf-8")
    if not frontmatter_lines(text):
        raise ValueError(f"SKILL.md has no frontmatter: {path}")
    lines = text.splitlines(keepends=True)
    inside = False
    for index, raw in enumerate(lines):
        stripped = raw.rstrip("\r\n")
        if stripped.strip() == "---":
            if inside:
                break
            inside = True
            continue
        match = VERSION_LINE.match(stripped) if inside else None
        if match:
            if match.group("version") == version:
                return False
            lines[index] = f'{match.group("indent")}version: "{version}"{raw[len(stripped):]}'
            path.write_text("".join(lines), encoding="utf-8")
            return True
    raise ValueError(f"SKILL.md declares no metadata.dcc-mcp.version: {path}")


def bump(version: str, root: Path = ROOT) -> list[Path]:
    if not SEMVER.fullmatch(version):
        raise ValueError(f"not a semantic version: {version}")
    changed: list[Path] = []

    for path in PLUGIN_MANIFESTS:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["version"] != version:
            data["version"] = version
            _write_json(path, data)
            changed.append(path)

    for path in MARKETPLACE_MANIFESTS:
        data = json.loads(path.read_text(encoding="utf-8"))
        touched = False
        for plugin in data["plugins"]:
            if plugin.get("version") != version:
                plugin["version"] = version
                touched = True
        if touched:
            _write_json(path, data)
            changed.append(path)

    clawhub = json.loads(CLAWHUB_MANIFEST.read_text(encoding="utf-8"))
    touched = False
    for entry in clawhub["skills"]:
        if entry["version"] != version:
            entry["version"] = version
            touched = True
    if touched:
        _write_json(CLAWHUB_MANIFEST, clawhub)
        changed.append(CLAWHUB_MANIFEST)

    for entry in clawhub["skills"]:
        skill_md = root / entry["path"] / "SKILL.md"
        if _bump_skill_md(skill_md, version):
            changed.append(skill_md)

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--major", action="store_const", const="major", dest="part")
    group.add_argument("--minor", action="store_const", const="minor", dest="part")
    group.add_argument("--patch", action="store_const", const="patch", dest="part")
    group.add_argument("--set", dest="explicit", help="set an exact version")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="print the resolved version without writing any file",
    )
    args = parser.parse_args(argv)

    try:
        version = args.explicit or next_version(current_version(), args.part)
        if args.print_only:
            print(version)
            return 0
        changed = bump(version)
        print(f"Bumped the Skill suite to {version} across {len(changed)} file(s)")
        for path in changed:
            print(f"  - {path.relative_to(ROOT).as_posix()}")
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
