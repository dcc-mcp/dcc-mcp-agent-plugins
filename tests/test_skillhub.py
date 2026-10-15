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
