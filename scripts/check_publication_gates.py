"""Read publication contracts from immutable Git objects, never candidate code.

CI executes this file and its helpers from a trusted baseline checkout. Only
fixed trusted dependencies are installed; candidate requirements are not read.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

if __package__ in {None, ""}:
    # -I excludes cwd/PYTHONPATH. Restore only this trusted checker's helpers.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from package_openclaw_skill import is_packable_path
    from publication_manifest import (
        CANONICAL_ROOT,
        MANIFEST_PATH,
        validate_manifest_coverage,
    )
else:
    from .package_openclaw_skill import is_packable_path
    from .publication_manifest import (
        CANONICAL_ROOT,
        MANIFEST_PATH,
        validate_manifest_coverage,
    )


SHA_RE = re.compile(r"[0-9a-f]{40}")
VERSION_RE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
MAX_METADATA_BYTES = 2 * 1024 * 1024
PLUGIN_ROOT = "plugins/dcc-mcp"
PLUGIN_MANIFESTS = (
    f"{PLUGIN_ROOT}/plugin.json",
    f"{PLUGIN_ROOT}/.codex-plugin/plugin.json",
    f"{PLUGIN_ROOT}/.claude-plugin/plugin.json",
    f"{PLUGIN_ROOT}/.codebuddy-plugin/plugin.json",
)
MARKETPLACE_MANIFESTS = (".claude-plugin/marketplace.json", ".codebuddy-plugin/marketplace.json")
PACKAGING_POLICY_PATHS = (
    "scripts/package_openclaw_skill.py",
    ".gitattributes",
    "plugins/.gitattributes",
    "plugins/dcc-mcp/.gitattributes",
    "plugins/dcc-mcp/skills/.gitattributes",
)


def unique_mapping(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate metadata mapping key")
        result[key] = value
    return result


class MetadataLoader(yaml.SafeLoader):
    """Safe YAML with unambiguous metadata keys."""


def yaml_mapping(loader: MetadataLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    return unique_mapping(loader.construct_pairs(node))


MetadataLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, yaml_mapping)


def stable_version(value: object) -> tuple[int, int, int]:
    if not isinstance(value, str) or len(value) > 64 or not VERSION_RE.fullmatch(value):
        raise ValueError("publication versions must be stable semantic-version strings")
    return tuple(int(part) for part in value.split("."))


class GitObjects:
    """Read a repository without checking out, importing, or executing its files."""

    def __init__(self, repository: Path):
        self.repository = repository.resolve()
        self.text_cache: dict[str, str] = {}

    def run(self, *arguments: str) -> bytes:
        result = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(self.repository), *arguments],
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode:
            raise ValueError(f"Git object/revision check failed ({arguments[0]})")
        return result.stdout

    def require_commit(self, sha: str) -> None:
        if not SHA_RE.fullmatch(sha) or sha == "0" * 40:
            raise ValueError("revision must be an exact nonzero 40-hex commit SHA")
        if self.run("cat-file", "-t", sha).strip() != b"commit":
            raise ValueError("revision does not identify a commit")

    def tree(self, sha: str) -> dict[str, tuple[str, str]]:
        result = {}
        for row in self.run("ls-tree", "-rz", "--full-tree", sha).split(b"\0"):
            if row:
                header, path = row.split(b"\t", 1)
                mode, _kind, oid = header.decode("ascii").split()
                result[path.decode("utf-8")] = (mode, oid)
        return result

    def text(self, tree: dict, path: str) -> str:
        item = tree.get(path)
        if item is None or item[0] not in {"100644", "100755"}:
            raise ValueError(f"missing or non-regular publication metadata: {path}")
        if item[1] in self.text_cache:
            return self.text_cache[item[1]]
        if int(self.run("cat-file", "-s", item[1])) > MAX_METADATA_BYTES:
            raise ValueError(f"publication metadata exceeds byte limit: {path}")
        self.text_cache[item[1]] = self.run("cat-file", "blob", item[1]).decode("utf-8")
        return self.text_cache[item[1]]

    def json(self, tree: dict, path: str) -> dict:
        value = json.loads(self.text(tree, path), object_pairs_hook=unique_mapping)
        if not isinstance(value, dict):
            raise ValueError(f"publication metadata must be an object: {path}")
        return value


@dataclass
class Snapshot:
    version: str
    files: dict[str, dict[str, str]]
    packaging_policy: dict[str, tuple[str, str] | None]


def snapshot(git: GitObjects, sha: str) -> Snapshot:
    tree = git.tree(sha)
    for path, (mode, _) in tree.items():
        if (path == CANONICAL_ROOT or path.startswith(CANONICAL_ROOT + "/")) and mode not in {
            "100644",
            "100755",
        }:
            raise ValueError(f"non-regular entry under canonical Skill root: {path}")
    canonical_paths = {
        str(PurePosixPath(path).parent)
        for path in tree
        if path.startswith(CANONICAL_ROOT + "/")
        and len(PurePosixPath(path).parts) == 5
        and PurePosixPath(path).name == "SKILL.md"
    }
    entries = validate_manifest_coverage(
        git.json(tree, MANIFEST_PATH).get("skills"), canonical_paths
    )
    version = git.json(tree, PLUGIN_MANIFESTS[0]).get("version")
    stable_version(version)
    for path in PLUGIN_MANIFESTS:
        if git.json(tree, path).get("version") != version:
            raise ValueError(f"plugin manifest differs from suite version: {path}")
    for path in MARKETPLACE_MANIFESTS:
        plugins = git.json(tree, path).get("plugins")
        if (
            not isinstance(plugins, list)
            or len(plugins) != 1
            or not isinstance(plugins[0], dict)
            or plugins[0].get("version") != version
        ):
            raise ValueError(f"marketplace differs from suite version: {path}")
    files = {}
    for entry in entries:
        slug, relative = entry["slug"], entry["path"]
        if entry.get("version") != version:
            raise ValueError(f"ClawHub manifest differs from suite version: {slug}")
        lines = git.text(tree, relative + "/SKILL.md").splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError(f"missing Skill frontmatter: {slug}")
        closing = next(
            (index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None
        )
        if closing is None:
            raise ValueError(f"unterminated Skill frontmatter: {slug}")
        metadata = yaml.load("\n".join(lines[1:closing]), Loader=MetadataLoader)
        try:
            matches = (
                metadata["name"] == slug and metadata["metadata"]["dcc-mcp"]["version"] == version
            )
        except (KeyError, TypeError):
            matches = False
        if not matches:
            raise ValueError(f"SKILL.md differs from canonical manifest/suite version: {slug}")
        selected = {}
        for path, (mode, oid) in tree.items():
            if path.startswith(relative + "/"):
                child = PurePosixPath(path).relative_to(relative)
                if is_packable_path(child):
                    selected[str(child)] = oid
        files[slug] = selected
    return Snapshot(version, files, {path: tree.get(path) for path in PACKAGING_POLICY_PATHS})


def check(repository: Path, base_sha: str, candidate_sha: str, head_sha: str | None = None) -> dict:
    git = GitObjects(repository)
    git.require_commit(base_sha)
    git.require_commit(candidate_sha)
    if head_sha is not None:
        git.require_commit(head_sha)
        parents = (
            git.run("rev-list", "--parents", "-n", "1", candidate_sha).decode("ascii").split()[1:]
        )
        if parents != [base_sha, head_sha]:
            raise ValueError("PR merge parents do not match the trusted base and event head")
    else:
        git.run("merge-base", "--is-ancestor", base_sha, candidate_sha)
    base = snapshot(git, base_sha)
    candidate = snapshot(git, candidate_sha)
    changed = sorted(
        slug
        for slug in base.files.keys() | candidate.files.keys()
        if base.files.get(slug) != candidate.files.get(slug)
    )
    if stable_version(candidate.version) < stable_version(base.version):
        raise ValueError("suite version must not decrease")
    policy_changed = base.packaging_policy != candidate.packaging_policy
    if policy_changed and stable_version(candidate.version) <= stable_version(base.version):
        raise ValueError(
            "packaging policy changed without a suite version increase; candidate policy is never executed"
        )
    if changed and stable_version(candidate.version) <= stable_version(base.version):
        raise ValueError(
            "published content changed without a suite version increase: "
            + ", ".join(changed)
            + "; run scripts/bump_version.py and regenerate distribution metadata"
        )
    return {
        "base": base_sha,
        "candidate": candidate_sha,
        "suite_version": candidate.version,
        "changed_skills": changed,
        "packaging_policy_changed": policy_changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--head-sha")
    args = parser.parse_args()
    try:
        report = check(args.repository, args.base_sha, args.candidate_sha, args.head_sha)
    except (ValueError, TypeError, OSError, yaml.YAMLError, subprocess.SubprocessError) as error:
        print(f"Publication contract rejected: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
