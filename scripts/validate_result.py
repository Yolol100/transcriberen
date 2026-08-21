#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
ALLOWED_STATUSES = {"ok", "skipped_no_captions", "access_blocked", "error"}
MEDIA_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}


def validate(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "2.1":
        raise ValueError("result schema_version must be 2.1")
    if data.get("status") not in ALLOWED_STATUSES:
        raise ValueError("invalid result status")

    source = data.get("source") or {}
    if source.get("type") not in {"video", "short"}:
        raise ValueError("source.type must be video or short")
    if not VIDEO_ID_RE.fullmatch(str(source.get("video_id") or "")):
        raise ValueError("invalid source.video_id")
    if not str(source.get("url") or "").startswith("https://www.youtube.com/"):
        raise ValueError("source.url must be normalized YouTube HTTPS")
    if "source_context" in data or "project_id" in data or "source_set_version" in data:
        raise ValueError("project truth must not be embedded in runtime results")
    if data.get("media_downloaded") is not False:
        raise ValueError("media_downloaded must be false")

    transcript_path = RESULTS / "transcript.txt"
    status = data["status"]
    if status == "ok":
        caption = data.get("caption")
        if not isinstance(caption, dict):
            raise ValueError("ok result requires caption metadata")
        if caption.get("kind") not in {"manual", "automatic"}:
            raise ValueError("invalid caption.kind")
        if not caption.get("language") or not caption.get("format"):
            raise ValueError("caption language and format are required")
        if int(caption.get("cue_count") or 0) <= 0:
            raise ValueError("caption cue_count must be positive")
        if not transcript_path.is_file():
            raise ValueError("ok result requires transcript.txt")
        transcript = transcript_path.read_text(encoding="utf-8")
        if not transcript.strip():
            raise ValueError("transcript.txt must not be empty")
        digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
        if data.get("transcript_sha256") != digest:
            raise ValueError("transcript_sha256 mismatch")
        if data.get("transcript_chars") != len(transcript):
            raise ValueError("transcript_chars mismatch")
        if data.get("error"):
            raise ValueError("ok result may not contain error")
    else:
        if transcript_path.exists():
            raise ValueError("non-ok result may not contain transcript.txt")
        if data.get("caption") is not None:
            raise ValueError("non-ok result must have caption=null")
        if data.get("transcript_sha256") is not None or data.get("transcript_chars") != 0:
            raise ValueError("non-ok result must not claim transcript content")
        if status == "skipped_no_captions" and data.get("error"):
            raise ValueError("skipped_no_captions may not contain error")
        if status in {"access_blocked", "error"} and not str(data.get("error") or "").strip():
            raise ValueError("failed result requires error detail")

    allowed_files = {"result.json", "transcript.txt", "SHA256SUMS.txt"}
    for item in RESULTS.rglob("*"):
        if item.is_dir():
            continue
        if item.suffix.lower() in MEDIA_EXTENSIONS:
            raise ValueError(f"media artifact forbidden: {item.name}")
        if item.relative_to(RESULTS).as_posix() not in allowed_files:
            raise ValueError(f"unexpected result artifact: {item.relative_to(RESULTS)}")


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else RESULTS / "result.json")
    validate(target)
    print("result-contract: OK")


if __name__ == "__main__":
    main()
