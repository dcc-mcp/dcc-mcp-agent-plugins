"""Sync the canonical Agent Skills from a dcc-mcp-core checkout.

The three public Skills are authored in `dcc-mcp-core` and distributed from this
repository. Copying them by hand let the two sides diverge silently, so the copy
is expressed here as a command that CI can also run in `--check` mode.

Skill versions remain repository-owned. The default `dcc-mcp` Skill also carries
bounded distribution discovery metadata generated from `references/PRODUCTS.json`:
its description, search hint, tags, marked product/UI routing block, and OpenAI
interface. Core continues to own the remainder of the instructional body and
every other Skill file.

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
DISTRIBUTION_OWNED_FILES = {
    ("dcc-mcp", Path("agents/openai.yaml")),
    ("dcc-mcp", Path("references/PRODUCTS.json")),
}
DISTRIBUTION_OWNED_SKILL_FIELDS = {
    "dcc-mcp": (("description", 0), ("search-hint", 4), ("tags", 4)),
}
UI_ROUTE_BEGIN = "<!-- BEGIN GENERATED PRODUCT DISCOVERY ROUTING -->"
UI_ROUTE_END = "<!-- END GENERATED PRODUCT DISCOVERY ROUTING -->"


def is_distribution_owned_file(skill: str, relative: Path) -> bool:
    return (skill, relative) in DISTRIBUTION_OWNED_FILES


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


def _frontmatter_field_range(lines: list[str], name: str, indent: int) -> tuple[int, int]:
    prefix = " " * indent + name + ":"
    frontmatter = False
    for index, line in enumerate(lines):
        if line.strip() == "---":
            if frontmatter:
                break
            frontmatter = True
            continue
        if frontmatter and line.startswith(prefix):
            end = index + 1
            while end < len(lines):
                candidate = lines[end]
                if candidate.strip() == "---":
                    break
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate.strip() and candidate_indent <= indent:
                    break
                end += 1
            return index, end
    raise ValueError(f"missing frontmatter field: {name}")


def _replace_frontmatter_field(source: str, target: str, name: str, indent: int) -> str:
    source_lines = source.splitlines()
    target_lines = target.splitlines()
    source_start, source_end = _frontmatter_field_range(source_lines, name, indent)
    target_start, target_end = _frontmatter_field_range(target_lines, name, indent)
    source_lines[source_start:source_end] = target_lines[target_start:target_end]
    return "\n".join(source_lines) + "\n"


def _extract_marked_block(text: str) -> str:
    if text.count(UI_ROUTE_BEGIN) != 1 or text.count(UI_ROUTE_END) != 1:
        raise ValueError("distributed dcc-mcp SKILL.md needs one generated UI routing block")
    start = text.index(UI_ROUTE_BEGIN)
    end = text.index(UI_ROUTE_END, start) + len(UI_ROUTE_END)
    return text[start:end]


def _apply_marked_block(source: str, target: str) -> str:
    block = _extract_marked_block(target)
    if UI_ROUTE_BEGIN in source or UI_ROUTE_END in source:
        if source.count(UI_ROUTE_BEGIN) != 1 or source.count(UI_ROUTE_END) != 1:
            raise ValueError("Core dcc-mcp SKILL.md has malformed generated routing markers")
        start = source.index(UI_ROUTE_BEGIN)
        end = source.index(UI_ROUTE_END, start) + len(UI_ROUTE_END)
        return source[:start] + block + source[end:]

    lines = source.splitlines()
    try:
        frontmatter_end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("Core dcc-mcp SKILL.md frontmatter is not closed") from error
    body_start = frontmatter_end + 1
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    lines[frontmatter_end + 1 : body_start] = ["", block, ""]
    return "\n".join(lines) + "\n"


def apply_distribution_owned_metadata(source: str, target: str, skill: str) -> str:
    result = apply_version(source, skill_version_from_text(target))
    for name, indent in DISTRIBUTION_OWNED_SKILL_FIELDS.get(skill, ()):
        result = _replace_frontmatter_field(result, target, name, indent)
    if skill == "dcc-mcp":
        result = _apply_marked_block(result, target)
    return result


def skill_version_from_text(text: str) -> str | None:
    for line in frontmatter_lines(text):
        match = VERSION_LINE.match(line)
        if match:
            return match.group("version")
    return None


def relative_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def same_content(source: Path, target: Path, is_skill_md: bool, skill: str | None = None) -> bool:
    """Compare ignoring line endings and bounded distribution-owned metadata."""
    source_text = source.read_text(encoding="utf-8")
    target_text = target.read_text(encoding="utf-8")
    if is_skill_md:
        source_text = apply_distribution_owned_metadata(source_text, target_text, skill or "")
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
            if is_distribution_owned_file(skill, extra):
                continue
            problems.append(f"{skill}/{extra.as_posix()}: present here, missing in Core")
        for shared in sorted(source_files & target_files):
            if is_distribution_owned_file(skill, shared):
                continue
            is_skill_md = shared.as_posix() == "SKILL.md"
            source_file = source_dir / shared
            target_file = target_dir / shared
            if not is_skill_md and filecmp.cmp(source_file, target_file, shallow=False):
                continue
            try:
                if same_content(source_file, target_file, is_skill_md, skill):
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
            if is_distribution_owned_file(skill, relative):
                continue
            (target_dir / relative).unlink()
            changed.append(f"{skill}/{relative.as_posix()} (removed)")
        for relative in sorted(relative_files(source_dir)):
            source_file = source_dir / relative
            target_file = target_dir / relative
            target_file.parent.mkdir(parents=True, exist_ok=True)
            if is_distribution_owned_file(skill, relative):
                if not target_file.is_file():
                    raise ValueError(f"missing distribution-owned file: {skill}/{relative.as_posix()}")
                continue
            if relative.as_posix() == "SKILL.md":
                if not target_file.is_file():
                    raise ValueError(f"missing distributed Skill metadata target: {target_file}")
                previous = target_file.read_text(encoding="utf-8")
                text = apply_distribution_owned_metadata(
                    source_file.read_text(encoding="utf-8"), previous, skill
                )
                if previous.splitlines() == text.splitlines():
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
