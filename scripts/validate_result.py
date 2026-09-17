#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
MEDIA_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
FIXED_POLICY = {"year": 2026, "max_videos": 1000, "comments_per_video": 7, "comment_sort": "top", "include_replies": False}


def expected_tool_versions() -> dict[str, str]:
    contract = json.loads((ROOT / "toolkit-contract.json").read_text(encoding="utf-8"))
    return {str(tool["id"]): str(tool["version"]) for tool in contract.get("tools", [])}


def validate(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "3.0":
        raise ValueError("result schema_version must be 3.0")
    if data.get("status") not in {"ok", "partial", "access_blocked", "error"}:
        raise ValueError("invalid result status")
    source = data.get("source") or {}
    if source.get("type") != "channel" or not str(source.get("url") or "").endswith("/videos"):
        raise ValueError("source must be a normalized YouTube channel /videos URL")
    if data.get("policy") != FIXED_POLICY:
        raise ValueError("fixed channel policy mismatch")
    if data.get("media_downloaded") is not False:
        raise ValueError("media_downloaded must be false")
    if any(key in data for key in ("project_id", "source_set_version", "owner_skill")):
        raise ValueError("project truth must not be embedded in runtime results")

    provenance = data.get("runtime_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("runtime_provenance is required")
    target = str(provenance.get("execution_target") or "")
    if target not in {"self-hosted", "local", "test"}:
        raise ValueError("invalid runtime_provenance.execution_target")
    if target != "test":
        versions = expected_tool_versions()
        if provenance.get("yt_dlp_version") != versions.get("yt-dlp"):
            raise ValueError("runtime yt-dlp version does not match capability contract")
        if provenance.get("deno_version") != versions.get("deno-ejs-runtime"):
            raise ValueError("runtime Deno version does not match capability contract")

    manifest_path = RESULTS / "manifest.json"
    progress_path = RESULTS / "progress.json"
    index_path = RESULTS / "processed-index.json"
    for required in (manifest_path, progress_path):
        if not required.is_file():
            raise ValueError(f"missing required output: {required.name}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("policy") != FIXED_POLICY:
        raise ValueError("manifest policy mismatch")
    items = manifest.get("items") or []
    if not isinstance(items, list) or len(items) > 1000:
        raise ValueError("manifest items must contain at most 1000 videos")
    counts = manifest.get("counts") or {}
    if int(counts.get("discovered") or 0) > 1000:
        raise ValueError("discovered count exceeds 1000")

    for item in items:
        video_id = str(item.get("video_id") or "")
        if len(video_id) != 11:
            raise ValueError("invalid video id")
        if not str(item.get("upload_date") or "").startswith("2026"):
            raise ValueError("manifest contains a video outside 2026")
        video_dir = RESULTS / "videos" / video_id
        comments = json.loads((video_dir / "comments.json").read_text(encoding="utf-8"))
        if comments.get("sort") != "top" or comments.get("include_replies") is not False:
            raise ValueError("comments policy mismatch")
        if int(comments.get("count") or 0) > 7 or len(comments.get("comments") or []) > 7:
            raise ValueError("more than 7 comments stored")
        for comment in comments.get("comments") or []:
            if not str(comment.get("text") or "").strip():
                raise ValueError("empty comment stored")
        if item.get("transcript_status") == "ok" and not (video_dir / "transcript.txt").is_file():
            raise ValueError("ok transcript item missing transcript.txt")

    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if index.get("schema_version") != "2.0":
            raise ValueError("processed-index schema_version must be 2.0")

    archive = RESULTS / "channel-corpus.zip"
    if not archive.is_file():
        raise ValueError("channel-corpus.zip missing")
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        for required in ("manifest.json", "result.json", "progress.json"):
            if required not in names:
                raise ValueError(f"zip missing {required}")
        if any(name.startswith("../") or "/../" in name for name in names):
            raise ValueError("unsafe path in ZIP")

    for item in RESULTS.rglob("*"):
        if item.is_file() and item.suffix.lower() in MEDIA_EXTENSIONS:
            raise ValueError(f"media artifact forbidden: {item.name}")


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else RESULTS / "result.json")
    validate(target)
    print("channel-result-contract: OK")


if __name__ == "__main__":
    main()
