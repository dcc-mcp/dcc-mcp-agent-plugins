"""Run the pinned SkillHub CLI with explicit selection and bounded 429 retries.

No remote existence check is assumed: after partial success, an operator must
select only a confirmed failed slug. Never retry ambiguous transport failures.
"""

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import io
import json
import math
from pathlib import Path
import re
import runpy
import sys
import time
import urllib.error
import urllib.request
from unittest.mock import patch

import yaml

PUBLISH_URL = "https://api.skillhub.cn/api/v1/community/skills/publish"
INTERVAL = 60
MAX_WAIT = 300
MAX_RETRIES = 2


def retry_delay(headers, body, attempt, now=None):
    """Respect both HTTP Retry-After and SkillHub's JSON retryAfter, or stop."""
    delays = [INTERVAL * (2 ** attempt)]
    for value in (headers.get("Retry-After"), body.get("retryAfter")):
        if value is None:
            continue
        try:
            seconds = float(value)
            if not math.isfinite(seconds):
                return None
            seconds = math.ceil(seconds)
        except (ValueError, TypeError):
            try:
                date = parsedate_to_datetime(str(value))
                seconds = (date - (now or datetime.now(timezone.utc))).total_seconds()
            except (ValueError, TypeError, OverflowError):
                return None
        if seconds < 0:
            seconds = 0
        delays.append(seconds)
    delay = max(delays)
    return delay if delay <= MAX_WAIT else None


def with_rate_limit_retry(opener, sleep=time.sleep):
    def open_request(request, *args, **kwargs):
        for attempt in range(MAX_RETRIES + 1):
            try:
                return opener(request, *args, **kwargs)
            except urllib.error.HTTPError as error:
                if (request.full_url != PUBLISH_URL or request.get_method() != "POST"
                        or error.code != 429):
                    raise
                raw = error.read()
                error.close()
                restored = urllib.error.HTTPError(
                    error.url, error.code, error.msg, error.headers, io.BytesIO(raw))
                try:
                    body = json.loads(raw)
                except (ValueError, UnicodeError):
                    body = {}
                delay = retry_delay(error.headers, body if isinstance(body, dict) else {}, attempt)
                if attempt == MAX_RETRIES or delay is None:
                    raise restored from None
                print(f"SkillHub rejected upload (HTTP 429); retry {attempt + 1}/{MAX_RETRIES} in {delay}s", flush=True)
                sleep(delay)
    return open_request


def selected_skills(staged, slug=""):
    paths = sorted(path for path in staged.iterdir() if path.is_dir())
    if slug:
        paths = [path for path in paths if path.name == slug]
    if not paths:
        raise ValueError("No staged Skill matches the explicit selection")
    return paths


def run(cli, staged, slug="", dry_run=False, changelog=""):
    paths = selected_skills(staged, slug)
    for index, path in enumerate(paths):
        if index and not dry_run:
            time.sleep(INTERVAL)
        metadata = yaml.safe_load(re.split(r"(?m)^---[ \t]*$", (path / "SKILL.md").read_text(encoding="utf-8"), maxsplit=2)[1])
        print(f"SkillHub {'preflight' if dry_run else 'upload'}: {path.name}@{metadata['version']}", flush=True)
        argv = [str(cli), "publish", str(path), "--host", "https://api.skillhub.cn", "--changelog", changelog]
        if dry_run:
            argv.append("--dry-run")
        with patch.object(sys, "argv", argv), patch.object(sys, "path", [str(cli.parent), *sys.path]), patch.object(
            urllib.request, "urlopen", with_rate_limit_retry(urllib.request.urlopen)
        ):
            runpy.run_path(str(cli), run_name="__main__")
        if not dry_run:
            print(f"SkillHub accepted: {path.name}@{metadata['version']}; public review status is separate", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--staged", type=Path, required=True)
    parser.add_argument("--slug", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--changelog", default="")
    args = parser.parse_args()
    run(args.cli, args.staged, args.slug, args.dry_run, args.changelog)
