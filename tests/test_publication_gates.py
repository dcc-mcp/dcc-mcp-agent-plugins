"""Read-only publication contracts against real directories and Git commits."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/check_publication_gates.py"


class GitPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "loonghao")
        self.git("config", "user.email", "hal.long@outlook.com")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.autocrlf", "false")
        self.names = ("dcc-mcp", "dcc-mcp-creator", "dcc-mcp-skills-creator", "dcc-cua")
        self.version("1.0.0")
        self.write("plugins/dcc-mcp/skills/dcc-mcp/scripts/example.py", "print('original')\n")
        self.base = self.commit()

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def version(self, version: str) -> None:
        entries = []
        for name in self.names:
            relative = f"plugins/dcc-mcp/skills/{name}"
            self.write(
                f"{relative}/SKILL.md",
                f'---\nname: {name}\nmetadata:\n  dcc-mcp:\n    version: "{version}"\n---\nInstructions.\n',
            )
            entries.append(
                {"path": relative, "slug": name, "owner": "loonghao", "version": version}
            )
        self.write(".github/clawhub-skills.json", json.dumps({"skills": entries}))
        for relative in (
            "plugin.json",
            ".codex-plugin/plugin.json",
            ".claude-plugin/plugin.json",
            ".codebuddy-plugin/plugin.json",
        ):
            self.write(f"plugins/dcc-mcp/{relative}", json.dumps({"version": version}))
        for vendor in (".claude-plugin", ".codebuddy-plugin"):
            self.write(
                f"{vendor}/marketplace.json", json.dumps({"plugins": [{"version": version}]})
            )

    def commit(self) -> str:
        self.git("add", ".")
        self.git("commit", "-qm", "test: publication fixture")
        return self.git("rev-parse", "HEAD")

    def check(self, candidate: str, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "-I",
                str(CHECKER),
                "--repository",
                str(self.root),
                "--base-sha",
                self.base,
                "--candidate-sha",
                candidate,
                *extra,
            ],
            capture_output=True,
            text=True,
            cwd=self.root,
            check=False,
        )

    def test_changed_published_script_requires_a_suite_bump(self) -> None:
        self.write("plugins/dcc-mcp/skills/dcc-mcp/scripts/example.py", "print('changed')\n")
        candidate = self.commit()
        result = self.check(candidate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content changed without a suite version increase", result.stderr)
        self.version("1.0.1")
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_git_snapshot_ignores_uncommitted_version_bump(self) -> None:
        self.write("plugins/dcc-mcp/skills/dcc-mcp/scripts/example.py", "print('changed')\n")
        candidate = self.commit()
        self.version("1.0.1")
        result = self.check(candidate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content changed without a suite version increase", result.stderr)

    def test_packager_only_change_requires_a_suite_bump_without_execution(self) -> None:
        self.write("scripts/package_openclaw_skill.py", "# Original trusted packaging policy.\n")
        self.base = self.commit()
        self.write(
            "scripts/package_openclaw_skill.py",
            "raise RuntimeError('candidate must never execute')\n",
        )
        result = self.check(self.commit())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("packaging policy changed without a suite version increase", result.stderr)
        self.version("1.0.1")
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["packaging_policy_changed"])

    def test_checkout_attributes_cannot_change_archive_bytes_at_old_version(self) -> None:
        self.write(".gitattributes", "plugins/dcc-mcp/skills/** text eol=crlf\n")
        result = self.check(self.commit())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("packaging policy changed without a suite version increase", result.stderr)
        self.version("1.0.1")
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["packaging_policy_changed"])

    def test_fifth_committed_skill_requires_manifest_and_suite_bump(self) -> None:
        self.write("plugins/dcc-mcp/skills/new-skill/SKILL.md", "---\nname: new-skill\n---\n")
        result = self.check(self.commit())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing=['plugins/dcc-mcp/skills/new-skill']", result.stderr)
        self.names += ("new-skill",)
        self.version("1.0.1")
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ignored_archive_files_and_readme_do_not_require_a_bump(self) -> None:
        for relative in (
            "__pycache__/example.pyc",
            ".pytest_cache/state",
            "Thumbs.db",
            "scripts/stale.pyo",
        ):
            self.write(f"plugins/dcc-mcp/skills/dcc-mcp/{relative}", "ignored")
        self.write("README.md", "Repository-only documentation.\n")
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["changed_skills"], [])

    def test_reference_deletion_requires_a_bump(self) -> None:
        self.write("plugins/dcc-mcp/skills/dcc-mcp/references/guide.md", "Published reference.\n")
        self.base = self.commit()
        (self.root / "plugins/dcc-mcp/skills/dcc-mcp/references/guide.md").unlink()
        result = self.check(self.commit())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content changed without a suite version increase", result.stderr)

    def test_same_version_reference_rename_requires_a_bump(self) -> None:
        self.write("plugins/dcc-mcp/skills/dcc-mcp/references/guide.md", "Same bytes.\n")
        self.base = self.commit()
        source = self.root / "plugins/dcc-mcp/skills/dcc-mcp/references/guide.md"
        source.rename(source.with_name("renamed.md"))
        result = self.check(self.commit())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content changed without a suite version increase", result.stderr)

    def test_suite_version_must_not_decrease(self) -> None:
        self.version("0.9.9")
        result = self.check(self.commit())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("suite version must not decrease", result.stderr)

    def test_manifest_and_skill_must_match_suite_version(self) -> None:
        path = self.root / "plugins/dcc-mcp/skills/dcc-mcp/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace('"1.0.0"', '"1.0.1"'), encoding="utf-8"
        )
        result = self.check(self.commit())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SKILL.md differs from canonical manifest/suite version", result.stderr)

    def test_candidate_code_and_cwd_modules_are_never_executed(self) -> None:
        hostile = "from pathlib import Path\nPath('candidate-executed').touch()\nraise RuntimeError('candidate executed')\n"
        for relative in ("scripts/check_publication_gates.py", "yaml.py", "sitecustomize.py"):
            self.write(relative, hostile)
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "candidate-executed").exists())

    def test_pr_merge_must_match_both_trusted_event_parents(self) -> None:
        self.version("1.0.1")
        head = self.commit()
        tree = self.git("rev-parse", "HEAD^{tree}")
        merged = self.git(
            "commit-tree", tree, "-p", self.base, "-p", head, "-m", "test: synthetic merge"
        )
        result = self.check(merged, "--head-sha", head)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.check(merged, "--head-sha", self.base)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PR merge parents do not match", result.stderr)

    def test_main_rejects_non_ancestor_before_commit(self) -> None:
        tree = self.git("rev-parse", "HEAD^{tree}")
        unrelated = self.git("commit-tree", tree, "-m", "test: unrelated history")
        result = self.check(unrelated)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("revision check failed", result.stderr)

    def test_git_symlink_is_rejected_even_when_filename_is_ignored(self) -> None:
        oid = self.git("rev-parse", "HEAD:plugins/dcc-mcp/skills/dcc-mcp/SKILL.md")
        self.git(
            "update-index",
            "--add",
            "--cacheinfo",
            f"120000,{oid},plugins/dcc-mcp/skills/dcc-mcp/stale.pyc",
        )
        self.git("commit", "-qm", "test: symbolic link fixture")
        result = self.check(self.git("rev-parse", "HEAD"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-regular entry under canonical Skill root", result.stderr)

    def test_unlisted_canonical_symlink_without_skill_md_is_rejected(self) -> None:
        oid = self.git("rev-parse", "HEAD:plugins/dcc-mcp/skills/dcc-mcp/SKILL.md")
        self.git(
            "update-index", "--add", "--cacheinfo", f"120000,{oid},plugins/dcc-mcp/skills/unlisted"
        )
        self.git("commit", "-qm", "test: unlisted symbolic link fixture")
        result = self.check(self.git("rev-parse", "HEAD"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-regular entry under canonical Skill root", result.stderr)

    def test_unlisted_canonical_gitlink_is_rejected(self) -> None:
        self.git(
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{self.base},plugins/dcc-mcp/skills/unlisted",
        )
        self.git("commit", "-qm", "test: unlisted gitlink fixture")
        result = self.check(self.git("rev-parse", "HEAD"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-regular entry under canonical Skill root", result.stderr)

    def test_duplicate_yaml_metadata_is_rejected(self) -> None:
        path = self.root / "plugins/dcc-mcp/skills/dcc-mcp/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                '    version: "1.0.0"', '    version: "1.0.0"\n    version: "1.0.1"'
            ),
            encoding="utf-8",
        )
        result = self.check(self.commit())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate metadata mapping key", result.stderr)


class ManifestCoverageTests(unittest.TestCase):
    def test_duplicates_and_noncanonical_paths_are_rejected(self) -> None:
        from scripts.publication_manifest import validate_manifest_coverage

        canonical = "plugins/dcc-mcp/skills/dcc-mcp"
        entry = {"slug": "dcc-mcp", "path": canonical}
        with self.assertRaisesRegex(ValueError, "duplicate canonical Skill entry"):
            validate_manifest_coverage([entry, dict(entry)], {canonical})
        for path in (canonical + "/../dcc-mcp", "other/dcc-mcp", "/" + canonical):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "canonical path"):
                validate_manifest_coverage([{**entry, "path": path}], {canonical})

    def test_fifth_canonical_skill_cannot_be_omitted_from_manifest(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            entries = []
            for name in (
                "dcc-mcp",
                "dcc-mcp-creator",
                "dcc-mcp-skills-creator",
                "dcc-cua",
                "new-skill",
            ):
                relative = f"plugins/dcc-mcp/skills/{name}"
                directory = root / relative
                directory.mkdir(parents=True)
                (directory / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
                if name != "new-skill":
                    entries.append(
                        {"path": relative, "slug": name, "owner": "loonghao", "version": "1.0.0"}
                    )
            manifest = root / ".github/clawhub-skills.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"skills": entries}), encoding="utf-8")
            contract = importlib.import_module("scripts.publication_manifest")
            with self.assertRaisesRegex(ValueError, "missing=.*new-skill"):
                contract.load_canonical_manifest(root)
            entries.append(
                {
                    "path": "plugins/dcc-mcp/skills/new-skill",
                    "slug": "new-skill",
                    "owner": "loonghao",
                    "version": "1.0.0",
                }
            )
            manifest.write_text(json.dumps({"skills": entries}), encoding="utf-8")
            self.assertEqual(len(contract.load_canonical_manifest(root)), 5)


if __name__ == "__main__":
    unittest.main()
