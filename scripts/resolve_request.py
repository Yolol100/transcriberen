#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
LANG_RE = re.compile(r"^(?:auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,16})?)$")
ALLOWED_INPUT_KEYS = {"enabled", "request_id", "url", "language"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
YEAR = 2026
MAX_VIDEOS = 1000
COMMENTS_PER_VIDEO = 7


def parse_channel_url(raw: str) -> str:
    value = str(raw or "").strip()
    parts = urlsplit(value)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or host not in YOUTUBE_HOSTS:
        raise ValueError("url must be an HTTPS YouTube channel URL")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("URL credentials and custom ports are not allowed")
    if parts.query or parts.fragment:
        raise ValueError("channel URL may not contain query or fragment")
    segments = [segment for segment in parts.path.split("/") if segment]
    if segments and segments[-1].lower() == "videos":
        segments = segments[:-1]
    if not segments:
        raise ValueError("url must point to a YouTube channel")
    valid = False
    if len(segments) == 1 and segments[0].startswith("@") and len(segments[0]) > 1:
        valid = True
    elif len(segments) == 2 and segments[0].lower() in {"channel", "c", "user"} and segments[1]:
        valid = True
    if not valid:
        raise ValueError("url must point to a YouTube channel, not a video, Short or playlist")
    return "https://www.youtube.com/" + "/".join(segments) + "/videos"


def validate_request(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("request must be a JSON object")
    unknown = sorted(set(raw) - ALLOWED_INPUT_KEYS)
    if unknown:
        raise ValueError("unsupported request fields: " + ", ".join(unknown))
    request_id = str(raw.get("request_id") or "").strip()
    if not ID_RE.fullmatch(request_id):
        raise ValueError("invalid request_id")
    if raw.get("enabled") is not True:
        raise ValueError("enabled must be true")
    language = str(raw.get("language") or "auto").strip()
    if not LANG_RE.fullmatch(language):
        raise ValueError("invalid language")
    return {
        "schema_version": "3.0",
        "enabled": True,
        "request_id": request_id,
        "url": parse_channel_url(raw.get("url")),
        "source_type": "channel",
        "language": language,
        "year": YEAR,
        "max_videos": MAX_VIDEOS,
        "comments_per_video": COMMENTS_PER_VIDEO,
        "comment_sort": "top",
        "include_replies": False,
    }


def main() -> None:
    request_file = Path(os.environ.get("REQUEST_FILE", "requests/transcribe.json"))
    raw = json.loads(request_file.read_text(encoding="utf-8"))
    resolved = validate_request(raw)
    output = ROOT / "resolved-request.json"
    output.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write("run=true\n")
            handle.write(f"request_id={resolved['request_id']}\n")
    print(json.dumps({"request_id": resolved["request_id"], "source_type": "channel", "year": YEAR}))


if __name__ == "__main__":
    main()
