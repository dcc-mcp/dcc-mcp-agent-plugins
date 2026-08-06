"""Validate and publish GitHub-backed Skills to Smithery."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / ".github" / "smithery-skills.json"
API_BASE = "https://api.smithery.ai"
SLUG_RE = re.compile(r"^[a-z0-9-]+$")
NAME_RE = re.compile(r"^name:\s*[\"']?([a-z0-9-]+)[\"']?\s*$", re.MULTILINE)


def validate_manifest(path: Path = MANIFEST, repo_root: Path = REPO_ROOT) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    namespace = data.get("namespace")
    skills = data.get("skills")
    if not isinstance(namespace, str) or not namespace:
        raise ValueError("Smithery manifest requires a namespace")
    if not isinstance(skills, list) or not skills:
        raise ValueError("Smithery manifest requires a non-empty skills array")

    validated = []
    for entry in skills:
        if not isinstance(entry, dict):
            raise ValueError("Smithery skill entries must be objects")
        slug = entry.get("slug")
        relative_path = entry.get("path")
        git_url = entry.get("git_url")
        if not all(isinstance(value, str) and value for value in (slug, relative_path, git_url)):
            raise ValueError("Smithery skill entries require slug, path, and git_url")
        if not SLUG_RE.fullmatch(slug):
            raise ValueError(f"invalid Smithery slug: {slug}")
        if not git_url.startswith("https://github.com/"):
            raise ValueError(f"Smithery git_url must point to GitHub: {git_url}")

        skill_dir = (repo_root / relative_path).resolve()
        try:
            skill_dir.relative_to(repo_root.resolve())
        except ValueError as error:
            raise ValueError(f"Smithery Skill path escapes repository: {relative_path}") from error
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            raise ValueError(f"Smithery Skill is missing SKILL.md: {relative_path}")
        frontmatter = skill_file.read_text(encoding="utf-8").split("---", 2)
        match = NAME_RE.search(frontmatter[1] if len(frontmatter) > 1 else "")
        if not match or match.group(1) != slug:
            raise ValueError(f"Smithery slug does not match SKILL.md name: {slug}")
        validated.append({"slug": slug, "git_url": git_url})
    return validated


def publish(namespace: str, skill: dict[str, str], api_key: str) -> dict:
    url = f"{API_BASE}/skills/{namespace}/{skill['slug']}"
    request = Request(
        url,
        data=json.dumps({"gitUrl": skill["git_url"]}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="PUT",
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Skills to Smithery's GitHub-backed Skills Registry")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--publish", action="store_true", help="publish changes; default is read-only dry-run")
    args = parser.parse_args()

    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        skills = validate_manifest(args.manifest)
        namespace = data["namespace"]
        if not args.publish:
            for skill in skills:
                print(f"PUT {API_BASE}/skills/{namespace}/{skill['slug']} gitUrl={skill['git_url']}")
            return 0

        api_key = os.environ.get("SMITHERY_API_KEY")
        if not api_key:
            raise ValueError("--publish requires SMITHERY_API_KEY")
        for skill in skills:
            result = publish(namespace, skill, api_key)
            print(f"Published {result.get('namespace', namespace)}/{result.get('slug', skill['slug'])}")
        return 0
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        print(f"Smithery request failed ({error.code}): {detail}", file=sys.stderr)
        return 1
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
