"""Sync the canonical Agent Skills from a dcc-mcp-core checkout.

The three public Skills are authored in `dcc-mcp-core` and distributed from this
repository. Copying them by hand let the two sides diverge silently, so the copy
is expressed here as a command that CI can also run in `--check` mode.

Only one field is repository-owned: `metadata.dcc-mcp.version` in `SKILL.md`.
Core stamps it from its own release automation; this repository maintains its
own Skill release line, so the field is preserved on sync and ignored on check.

Examples:
    python scripts/sync_core_skills.py --source ../dcc-mcp-core
    python scripts/sync_core_skills.py --source .core --check
"""

from __future__ import annotations

import argparse
import datetime as dt
import filecmp
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
PROVENANCE = ROOT / ".github" / "core-skills-sync.json"
SKILLS_ROOT = ROOT / "plugins" / "dcc-mcp" / "skills"
VERSION_LINE = re.compile(r'^(?P<indent>\s+)version:\s*"(?P<version>[^"]*)"\s*(?P<comment>#.*)?$')


def load_provenance() -> dict:
    return json.loads(PROVENANCE.read_text(encoding="utf-8"))


def source_commit(source: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def skill_version(skill_md: Path) -> str | None:
    """Return the `metadata.dcc-mcp.version` value declared in a SKILL.md."""
    for line in frontmatter_lines(skill_md.read_text(encoding="utf-8")):
        match = VERSION_LINE.match(line)
        if match:
            return match.group("version")
    return None


def frontmatter_lines(text: str) -> list[str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:index]
    return []


def apply_version(text: str, version: str | None) -> str:
    """Rewrite the frontmatter version line, dropping Core's release marker."""
    if version is None:
        return text
    lines = text.splitlines(keepends=True)
    inside = False
    for index, raw in enumerate(lines):
        stripped = raw.rstrip("\r\n")
        if stripped.strip() == "---":
            if inside:
                break
            inside = True
            continue
        if not inside:
            break
        match = VERSION_LINE.match(stripped)
        if match:
            ending = raw[len(stripped) :]
            lines[index] = f'{match.group("indent")}version: "{version}"{ending}'
            break
    return "".join(lines)


def relative_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def same_content(source: Path, target: Path, is_skill_md: bool) -> bool:
    """Compare ignoring line-ending style, and the repo-owned version line."""
    source_text = source.read_text(encoding="utf-8")
    target_text = target.read_text(encoding="utf-8")
    if is_skill_md:
        source_text = apply_version(source_text, skill_version(target))
    return source_text.splitlines() == target_text.splitlines()


def check(source_root: Path, skills: list[str]) -> list[str]:
    problems: list[str] = []
    for skill in skills:
        source_dir = source_root / skill
        target_dir = SKILLS_ROOT / skill
        if not source_dir.is_dir():
            problems.append(f"{skill}: missing in source checkout ({source_dir})")
            continue
        if not target_dir.is_dir():
            problems.append(f"{skill}: missing in this repository ({target_dir})")
            continue
        source_files = relative_files(source_dir)
        target_files = relative_files(target_dir)
        for missing in sorted(source_files - target_files):
            problems.append(f"{skill}/{missing.as_posix()}: present in Core, missing here")
        for extra in sorted(target_files - source_files):
            problems.append(f"{skill}/{extra.as_posix()}: present here, missing in Core")
        for shared in sorted(source_files & target_files):
            is_skill_md = shared.as_posix() == "SKILL.md"
            source_file = source_dir / shared
            target_file = target_dir / shared
            if not is_skill_md and filecmp.cmp(source_file, target_file, shallow=False):
                continue
            try:
                if same_content(source_file, target_file, is_skill_md):
                    continue
            except UnicodeDecodeError:
                pass
            problems.append(f"{skill}/{shared.as_posix()}: content differs from Core")
    return problems


def sync(source_root: Path, skills: list[str]) -> list[str]:
    changed: list[str] = []
    for skill in skills:
        source_dir = source_root / skill
        target_dir = SKILLS_ROOT / skill
        if not source_dir.is_dir():
            raise ValueError(f"missing Skill in source checkout: {source_dir}")
        for relative in sorted(relative_files(target_dir) - relative_files(source_dir)):
            (target_dir / relative).unlink()
            changed.append(f"{skill}/{relative.as_posix()} (removed)")
        for relative in sorted(relative_files(source_dir)):
            source_file = source_dir / relative
            target_file = target_dir / relative
            target_file.parent.mkdir(parents=True, exist_ok=True)
            if relative.as_posix() == "SKILL.md":
                version = skill_version(target_file) if target_file.is_file() else None
                text = apply_version(source_file.read_text(encoding="utf-8"), version)
                previous = target_file.read_text(encoding="utf-8") if target_file.is_file() else None
                if previous is not None and previous.splitlines() == text.splitlines():
                    continue
                target_file.write_text(text, encoding="utf-8")
            else:
                if target_file.is_file() and filecmp.cmp(source_file, target_file, shallow=False):
                    continue
                shutil.copyfile(source_file, target_file)
            changed.append(f"{skill}/{relative.as_posix()}")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="path to a dcc-mcp-core checkout")
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    parser.add_argument(
        "--commit",
        help="commit to record as the sync pin; defaults to the source checkout HEAD. "
        "Set it when syncing from a worktree whose HEAD is not the published ref.",
    )
    args = parser.parse_args(argv)

    provenance = load_provenance()
    skills = list(provenance["skills"])
    source = Path(args.source).resolve()
    source_root = source / provenance["source_root"]
    if not source_root.is_dir():
        print(f"not a dcc-mcp-core checkout: {source_root} does not exist", file=sys.stderr)
        return 1

    commit = source_commit(source)
    recorded = provenance.get("commit", "unknown")
    print(f"source {source} @ {commit}")
    print(f"recorded sync commit {recorded}")

    if args.check:
        problems = check(source_root, skills)
        if problems:
            print(f"\n{len(problems)} difference(s) against Core:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            print(
                "\nRe-sync with: python scripts/sync_core_skills.py --source <core-checkout>",
                file=sys.stderr,
            )
            return 1
        print(f"\n{len(skills)} Skills match Core")
        return 0

    changed = sync(source_root, skills)
    provenance["commit"] = args.commit or commit
    provenance["synced_at"] = dt.date.today().isoformat()
    PROVENANCE.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    if changed:
        print(f"\nupdated {len(changed)} file(s):")
        for entry in changed:
            print(f"  - {entry}")
    else:
        print("\nalready in sync")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
