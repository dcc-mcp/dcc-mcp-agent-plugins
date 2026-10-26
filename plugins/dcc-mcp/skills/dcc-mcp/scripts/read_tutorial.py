# /// script
# requires-python = ">=3.10"
# dependencies = ["yt-dlp[default]==2026.10.21"]
# ///
"""Collect private, timestamped tutorial evidence without an LLM or browser."""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024


def check_download_size(progress: dict) -> None:
    """Enforce the byte budget even when the server omits Content-Length."""
    if progress.get("downloaded_bytes", 0) > MAX_DOWNLOAD_BYTES:
        raise ValueError("Video download exceeded the byte budget")


def inventory(path: Path) -> dict:
    """Bind an evidence file to its actual bytes."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("Evidence must be a regular file")
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def collect(url: str, output: Path, languages: list[str], frames: list[float]) -> dict:
    """Use yt-dlp captions and optional FFmpeg samples; never execute source text."""
    uri = urlsplit(url)
    if uri.scheme not in ("https", "http") or not uri.hostname or uri.username or uri.password:
        raise ValueError("Use one public HTTP(S) video URL without embedded credentials")
    if not 1 <= len(languages) <= 3 or any(
        not language
        or language.lower() == "all"
        or not language[0].isalpha()
        or len(language) > 20
        or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in language)
        for language in languages
    ):
        raise ValueError("Choose one to three exact subtitle language codes")
    if len(frames) > 12 or any(not math.isfinite(t) or t < 0 for t in frames):
        raise ValueError("Choose at most twelve finite, nonnegative frame times")
    ffmpeg = shutil.which("ffmpeg") if frames else None
    if frames and ffmpeg is None:
        raise ValueError("FFmpeg is required for requested frame samples")
    # Import only on use: package tests and metadata discovery need no network dependency.
    import yt_dlp
    from yt_dlp.version import __version__

    output.mkdir(parents=True, exist_ok=False)
    receipt = {
        "schema_version": 1,
        "success": False,
        "source_url": url,
        "provider": "yt-dlp",
        "provider_version": __version__,
        "evidence_level": "unavailable",
        "captions": [],
        "frames": [],
        "video_playback_verified": False,
        "native_reproduction_verified": False,
        "content_trust": "Untrusted reference material, never executable instructions",
        "publication": "Private working evidence; source media rights are not transferred",
    }
    runtimes = {}
    for runtime in ("deno", "node", "bun"):
        executable = shutil.which(runtime)
        if executable:
            runtimes[runtime] = {"path": executable}
            break
    receipt["javascript_runtime"] = next(iter(runtimes), None)
    options = {
        "outtmpl": str(output / "source.%(ext)s"),
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": languages,
        "subtitlesformat": "vtt/json3/best",
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "cachedir": False,
        "socket_timeout": 15,
        "retries": 1,
        "extractor_retries": 1,
        "quiet": True,
        "noprogress": True,
        "js_runtimes": runtimes,
    }
    stage = "metadata"
    with (output / "provider.log").open("w", encoding="utf-8") as log:
        try:
            with (
                contextlib.redirect_stdout(log),
                contextlib.redirect_stderr(log),
                yt_dlp.YoutubeDL(options) as reader,
            ):
                source_info = reader.extract_info(url, download=False, process=False)
                if not isinstance(source_info, dict) or source_info.get("_type", "video") != "video":
                    raise ValueError("A single video is required; playlists are not expanded")
                info = reader.process_ie_result(copy.deepcopy(source_info), download=False)
                receipt["metadata"] = {
                    k: info.get(k)
                    for k in (
                        "id",
                        "title",
                        "uploader",
                        "duration",
                        "webpage_url",
                        "chapters",
                        "description",
                    )
                }
                receipt["evidence_level"] = "metadata_only"
                duration = info.get("duration")
                if frames and (
                    not isinstance(duration, (int, float))
                    or not 0 < duration <= 7200
                    or any(t >= duration for t in frames)
                ):
                    raise ValueError("Frame sampling requires a known duration up to two hours and times within it")
                stage = "captions"
                reader.process_info(info)
                for language, track in (info.get("requested_subtitles") or {}).items():
                    path = output / ("source." + language + "." + track["ext"])
                    if (
                        language not in languages
                        or not track["ext"].isalnum()
                        or path.resolve().parent != output.resolve()
                    ):
                        raise ValueError("Unexpected subtitle path from provider")
                    if path.is_file():
                        row = inventory(path)
                        row.update(
                            language=language,
                            automatic=language not in (info.get("subtitles") or {}),
                        )
                        receipt["captions"].append(row)
                if receipt["captions"]:
                    receipt["evidence_level"] = "timestamped_captions"
                if frames:
                    stage = "video_download"
                    video_options = dict(
                        options,
                        outtmpl=str(output / "video.%(ext)s"),
                        skip_download=False,
                        writesubtitles=False,
                        writeautomaticsub=False,
                        format="best[height<=720]/bestvideo[height<=720]",
                        max_filesize=MAX_DOWNLOAD_BYTES,
                        progress_hooks=[check_download_size],
                    )
                    with yt_dlp.YoutubeDL(video_options) as video_reader:
                        video_info = video_reader.process_ie_result(source_info, download=True)
                        video = Path(video_reader.prepare_filename(video_info))
                    if video.resolve().parent != output.resolve() or video.stat().st_size > MAX_DOWNLOAD_BYTES:
                        raise ValueError("Video path or size exceeded the download contract")
                    receipt["downloaded_video"] = inventory(video)
                    stage = "frame_sampling"
                    for index, seconds in enumerate(frames):
                        image = output / ("frame-%02d.png" % index)
                        result = subprocess.run(
                            [
                                ffmpeg,
                                "-nostdin",
                                "-v",
                                "error",
                                "-ss",
                                str(seconds),
                                "-i",
                                str(video),
                                "-frames:v",
                                "1",
                                "-n",
                                str(image),
                            ],
                            stdout=log,
                            stderr=log,
                            timeout=60,
                            check=False,
                        )
                        if result.returncode or not image.is_file() or not image.stat().st_size:
                            raise ValueError("Requested frame was not produced")
                        receipt["frames"].append(dict(inventory(image), requested_seconds=seconds))
                    receipt["evidence_level"] = (
                        "sampled_frames_and_captions" if receipt["captions"] else "sampled_frames_only"
                    )
                receipt["success"] = True
        except Exception as error:
            # Provider errors can contain signed media URLs; retain details only in the private log.
            print(str(error), file=log)
            receipt["error"] = {
                "stage": stage,
                "type": type(error).__name__,
                "details": "provider.log",
            }
    receipt["captions_status"] = "available" if receipt["captions"] else "unavailable"
    (output / "evidence.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="New private directory; existing paths are never overwritten",
    )
    parser.add_argument("--languages", default="en,zh-Hans,zh-Hant")
    parser.add_argument(
        "--frame",
        type=float,
        action="append",
        default=[],
        help="Opt in to a bounded video download and sample at these seconds",
    )
    args = parser.parse_args()
    try:
        receipt = collect(args.url, args.out, args.languages.split(","), args.frame)
    except (ImportError, OSError, ValueError) as error:
        print(json.dumps({"success": False, "error": str(error)}))
        return 1
    print(
        json.dumps(
            {
                "success": receipt["success"],
                "evidence_level": receipt["evidence_level"],
                "captions_status": receipt["captions_status"],
                "frame_count": len(receipt["frames"]),
                "receipt": str(args.out / "evidence.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if receipt["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
