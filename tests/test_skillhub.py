import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stage_skillhub import stage


class SkillHubTests(unittest.TestCase):
    def test_stages_metadata_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".github").mkdir()
            source = root / "skills/example"
            source.mkdir(parents=True)
            raw = "---\nname: example\ndescription: 中文 description\nlicense: MIT-0\n---\n# Body\n"
            (source / "SKILL.md").write_text(raw, encoding="utf-8")
            (source / "helper.py").write_text("pass\n")
            (source / "__pycache__").mkdir()
            (source / "__pycache__/helper.pyc").write_bytes(b"cache")
            manifest = root / ".github/clawhub-skills.json"
            manifest.write_text(json.dumps({"skills": [{"path": "skills/example", "slug": "example", "version": "1.2.3"}]}))
            stage(root, root / "output")
            result = (root / "output/example/SKILL.md").read_text(encoding="utf-8")
            metadata = yaml.safe_load(result.split("---", 2)[1])
            self.assertEqual(metadata["version"], "1.2.3")
            self.assertEqual(metadata["slug"], "example")
            self.assertEqual(metadata["summary"], "中文 description")
            self.assertTrue(result.endswith("# Body\n"))
            self.assertTrue((root / "output/example/helper.py").is_file())
            self.assertFalse((root / "output/example/__pycache__").exists())
            self.assertEqual((source / "SKILL.md").read_text(encoding="utf-8"), raw)
            with self.assertRaises(FileExistsError):
                stage(root, root / "output")
            manifest.write_text(json.dumps({"skills": [{"path": "../escape", "slug": "example", "version": "1.2.3"}]}))
            with self.assertRaises(ValueError):
                stage(root, root / "other")

    def test_delimiters_in_values_and_array_manifest(self):
        for array_manifest in (False, True):
            with self.subTest(array_manifest=array_manifest), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / ".github").mkdir()
                source = root / "skills/example"
                source.mkdir(parents=True)
                raw = '---\nname: example\ndescription: "A --- B"\nlicense: MIT-0\n---\n# Body\n---\nPreserved body\n'
                (source / "SKILL.md").write_text(raw, encoding="utf-8")
                entries = [{"path": "skills/example", "slug": "example", "version": "1.2.3"}]
                (root / ".github/clawhub-skills.json").write_text(
                    json.dumps(entries if array_manifest else {"skills": entries}), encoding="utf-8")
                stage(root, root / "output")
                result = (root / "output/example/SKILL.md").read_text(encoding="utf-8")
                lines = result.splitlines()
                closing = lines.index("---", 1)
                metadata = yaml.safe_load("\n".join(lines[1:closing]))
                self.assertEqual(metadata["summary"], "A --- B")
                self.assertTrue(result.endswith("# Body\n---\nPreserved body\n"))
                self.assertEqual((source / "SKILL.md").read_text(encoding="utf-8"), raw)

    def test_workflow_limits_credentials_and_uses_temp_config(self):
        root = Path(__file__).resolve().parents[1]
        release = yaml.safe_load((root / ".github/workflows/release.yml").read_text())
        self.assertEqual(release["jobs"]["publish-skillhub"]["secrets"],
                         {"SKILLHUB_KEY": "${{ secrets.SKILLHUB_KEY }}"})
        workflow = yaml.safe_load((root / ".github/workflows/skillhub.yml").read_text())
        job = workflow["jobs"]["sync"]
        self.assertNotIn("env", job)
        self.assertIn("$RUNNER_TEMP/skillhub-config.json", next(step["run"] for step in job["steps"] if step.get("name") == "Set SkillHub config path"))
        checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
        self.assertIs(checkout["with"]["persist-credentials"], False)
