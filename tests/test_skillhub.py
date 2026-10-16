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



class SkillHubPublishTests(unittest.TestCase):
    def test_selection_is_exact_and_unknown_or_path_input_fails(self):
        from publish_skillhub import selected_skills
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for slug in ('dcc-cua', 'dcc-mcp', 'dcc-mcp-creator', 'dcc-mcp-skills-creator'):
                (root / slug).mkdir()
            self.assertEqual([p.name for p in selected_skills(root)],
                             ['dcc-cua', 'dcc-mcp', 'dcc-mcp-creator', 'dcc-mcp-skills-creator'])
            self.assertEqual([p.name for p in selected_skills(root, 'dcc-mcp-skills-creator')],
                             ['dcc-mcp-skills-creator'])
            for value in ('unknown', '../dcc-mcp', '*', 'dcc-mcp,dcc-cua'):
                with self.assertRaises(ValueError):
                    selected_skills(root, value)

    def test_retry_after_header_and_body_use_longest_delay(self):
        from datetime import datetime, timezone
        from publish_skillhub import retry_delay
        self.assertEqual(retry_delay({}, {}, 0), 60)
        self.assertEqual(retry_delay({}, {}, 1), 120)
        self.assertEqual(retry_delay({}, {'retryAfter': 70.9}, 0), 71)
        self.assertIsNone(retry_delay({}, {'retryAfter': float('inf')}, 0))
        self.assertEqual(retry_delay({'Retry-After': '180'}, {'retryAfter': 240}, 0), 240)
        self.assertEqual(retry_delay({'Retry-After': 'Fri, 16 Oct 2026 03:03:00 GMT'}, {}, 0,
                                    datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)), 180)
        self.assertIsNone(retry_delay({'Retry-After': '301'}, {}, 0))
        self.assertIsNone(retry_delay({'Retry-After': 'invalid'}, {}, 0))

    def test_retry_only_explicit_publish_429_and_preserve_final_error(self):
        import io
        import urllib.error
        import urllib.request
        from unittest.mock import Mock
        from publish_skillhub import PUBLISH_URL, with_rate_limit_retry
        request = urllib.request.Request(PUBLISH_URL, data=b'payload', method='POST')
        def failure(code=429, headers=None):
            return urllib.error.HTTPError(PUBLISH_URL, code, 'rejected', headers or {},
                                          io.BytesIO(b'{"retryAfter": 70}'))
        sleep = Mock()
        success = object()
        opener = Mock(side_effect=[failure(), success])
        self.assertIs(with_rate_limit_retry(opener, sleep)(request), success)
        sleep.assert_called_once_with(70)
        opener = Mock(side_effect=[failure(), failure(), failure()])
        sleep = Mock()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            with_rate_limit_retry(opener, sleep)(request)
        self.assertEqual(caught.exception.read(), b'{"retryAfter": 70}')
        self.assertEqual(opener.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        for error in (failure(409), failure(500), failure(headers={'Retry-After': '3600'}),
                      urllib.error.URLError('timeout')):
            opener, sleep = Mock(side_effect=error), Mock()
            with self.assertRaises(Exception):
                with_rate_limit_retry(opener, sleep)(request)
            self.assertEqual(opener.call_count, 1)
            sleep.assert_not_called()
        opener, sleep = Mock(side_effect=failure()), Mock()
        with self.assertRaises(urllib.error.HTTPError):
            with_rate_limit_retry(opener, sleep)(urllib.request.Request('https://api.skillhub.cn/login'))
        sleep.assert_not_called()

    def test_runner_spacing_and_no_replay_after_ambiguous_failure(self):
        from unittest.mock import patch
        from publish_skillhub import run
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for slug in ('a', 'b', 'c'):
                (root / slug).mkdir()
                (root / slug / 'SKILL.md').write_text('---\nversion: 1.2.3\n---\nbody')
            with patch('publish_skillhub.runpy.run_path') as cli, patch('publish_skillhub.time.sleep') as sleep:
                run(root / 'cli.py', root)
                self.assertEqual(cli.call_count, 3)
                self.assertEqual(sleep.call_args_list, [((60,),), ((60,),)])
            with patch('publish_skillhub.runpy.run_path') as cli, patch('publish_skillhub.time.sleep') as sleep:
                run(root / 'cli.py', root, 'b', dry_run=True)
                self.assertEqual(cli.call_count, 1)
                sleep.assert_not_called()
            with patch('publish_skillhub.runpy.run_path', side_effect=[None, RuntimeError('timeout')]) as cli:
                with patch('publish_skillhub.time.sleep'), self.assertRaises(RuntimeError):
                    run(root / 'cli.py', root)
                self.assertEqual(cli.call_count, 2)

    def test_workflow_selection_is_env_only_and_not_a_clawhub_trigger(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/skillhub.yml').read_text())
        events = workflow[True]
        self.assertEqual(events['workflow_call']['inputs']['slug']['default'], '')
        self.assertEqual(events['workflow_dispatch']['inputs']['slug']['options'],
                         ['', 'dcc-cua', 'dcc-mcp', 'dcc-mcp-creator', 'dcc-mcp-skills-creator'])
        for step in workflow['jobs']['sync']['steps']:
            self.assertNotIn('${{ inputs.slug }}', step.get('run', ''))
        clawhub = yaml.safe_load((root / '.github/workflows/publish-clawhub.yml').read_text())
        import fnmatch
        for changed in ('.github/workflows/skillhub.yml', 'scripts/publish_skillhub.py', 'scripts/product_discovery.py', 'tests/test_skillhub.py'):
            self.assertFalse(any(fnmatch.fnmatch(changed, pattern)
                                 for pattern in clawhub[True]['push']['paths']))

    def test_publish_uses_ephemeral_token_not_login(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/skillhub.yml').read_text())
        step = next(s for s in workflow['jobs']['sync']['steps'] if s.get('name') == 'Publish selected Skills')
        self.assertEqual(step['env']['SKILLHUB_TOKEN'], '${{ secrets.SKILLHUB_KEY }}')
        self.assertNotIn(' login ', step['run'])
        self.assertNotIn('--token', step['run'])
        self.assertIn("github.event_name != 'pull_request'", step['if'])
