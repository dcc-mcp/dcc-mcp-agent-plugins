"""Stage canonical Skills with SkillHub metadata, without changing sources."""

import json
from pathlib import Path
import re
import tempfile

import yaml

from package_openclaw_skill import iter_skill_files, resolve_manifest_skills

ROOT = Path(__file__).resolve().parent.parent


def stage(repo_root: Path, output: Path) -> None:
    manifest = repo_root / ".github/clawhub-skills.json"
    releases = resolve_manifest_skills(manifest, repo_root.resolve())
    data = json.loads(manifest.read_text(encoding="utf-8"))
    entries = data.get("skills") if isinstance(data, dict) else data
    for entry, (source, version) in zip(entries, releases, strict=True):
        slug = entry["slug"]
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError(f"invalid SkillHub slug: {slug!r}")
        raw = (source / "SKILL.md").read_text(encoding="utf-8")
        parts = re.split(r"(?m)^---[ \t]*$", raw, maxsplit=2)
        if len(parts) != 3 or parts[0].strip():
            raise ValueError(f"missing frontmatter: {source}")
        metadata = yaml.safe_load(parts[1])
        if metadata.get("name") != slug:
            raise ValueError(f"Skill name does not match slug: {slug}")
        metadata.update(slug=slug, version=version, displayName=slug,
                        summary=metadata["description"])
        target = output / slug
        target.mkdir(parents=True, exist_ok=False)
        for path in iter_skill_files(source):
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
        (target / "SKILL.md").write_text(
            "---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
            + "---" + parts[2], encoding="utf-8")


if __name__ == "__main__":
    output = ROOT / "dist/skillhub"
    output.mkdir(parents=True, exist_ok=True)
    # Each invocation uses a fresh directory so stale files never enter a release.
    destination = Path(tempfile.mkdtemp(prefix="skills-", dir=output))
    stage(ROOT, destination)
    print(destination)
