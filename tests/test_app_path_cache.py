"""Regression tests for the consent-preserving local application path cache."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins" / "dcc-mcp" / "skills" / "dcc-mcp" / "scripts" / "app_path_cache.py"


def load_module():
    spec = importlib.util.spec_from_file_location("app_path_cache_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AppPathCacheTests(unittest.TestCase):
    def test_user_path_is_saved_and_prompt_requires_confirmation(self) -> None:
        module = load_module()
        with TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.json"
            executable = Path(directory) / "obs.exe"
            executable.write_text("placeholder", encoding="utf-8")
            old = os.environ.get(module.CACHE_ENV)
            os.environ[module.CACHE_ENV] = str(cache)
            try:
                entry = module.set_path("obs", str(executable))
                self.assertEqual(str(executable.resolve()), entry["path"])
                self.assertFalse(module.get_path("obs")["stale"])
                prompt = module.launch_prompt("obs", "OBS Studio", install_available=True)
                self.assertIn(str(executable.resolve()), prompt)
                self.assertIn("明确回复", prompt)
                self.assertNotIn("启动", json.loads(cache.read_text(encoding="utf-8"))["entries"]["obs"])
            finally:
                if old is None:
                    os.environ.pop(module.CACHE_ENV, None)
                else:
                    os.environ[module.CACHE_ENV] = old

    def test_stale_and_relative_paths_are_guided_without_execution(self) -> None:
        module = load_module()
        with TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.json"
            old = os.environ.get(module.CACHE_ENV)
            os.environ[module.CACHE_ENV] = str(cache)
            try:
                with self.assertRaises(ValueError):
                    module.set_path("obs", "obs.exe")
                module.set_path("obs", str(Path(directory) / "removed.exe"))
                prompt = module.launch_prompt(
                    "obs",
                    "OBS Studio",
                    install_available=True,
                    host_install_url="https://obsproject.com/download",
                )
                self.assertIn("已不存在", prompt)
                self.assertIn("新的软件绝对路径", prompt)
                self.assertIn("是否需要我先提供官方安装方式", prompt)
                self.assertIn("https://obsproject.com/download", prompt)
                self.assertIn("dcc-mcp-cli install --dcc-type obs", prompt)
            finally:
                if old is None:
                    os.environ.pop(module.CACHE_ENV, None)
                else:
                    os.environ[module.CACHE_ENV] = old

    def test_missing_path_asks_before_host_install_or_launch(self) -> None:
        module = load_module()
        with TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.json"
            old = os.environ.get(module.CACHE_ENV)
            os.environ[module.CACHE_ENV] = str(cache)
            try:
                prompt = module.launch_prompt(
                    "blender",
                    "Blender",
                    install_available=True,
                    host_install_url="https://www.blender.org/download/",
                )
                self.assertIn("尚未找到 Blender", prompt)
                self.assertIn("明确告诉我需要安装它", prompt)
                self.assertIn("下载、安装和启动都需要你的明确确认", prompt)
                self.assertIn("https://www.blender.org/download/", prompt)
                self.assertNotIn("启动 Blender", prompt)
            finally:
                if old is None:
                    os.environ.pop(module.CACHE_ENV, None)
                else:
                    os.environ[module.CACHE_ENV] = old

    def test_host_install_url_must_be_https(self) -> None:
        module = load_module()
        with self.assertRaises(ValueError):
            module.launch_prompt("obs", "OBS Studio", host_install_url="http://example.test")

    def test_malformed_cache_fails_closed(self) -> None:
        module = load_module()
        with TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.json"
            cache.write_text('{"schema_version": 99, "entries": {}}', encoding="utf-8")
            old = os.environ.get(module.CACHE_ENV)
            os.environ[module.CACHE_ENV] = str(cache)
            try:
                with self.assertRaises(ValueError):
                    module.get_path("obs")
            finally:
                if old is None:
                    os.environ.pop(module.CACHE_ENV, None)
                else:
                    os.environ[module.CACHE_ENV] = old


if __name__ == "__main__":
    unittest.main()
