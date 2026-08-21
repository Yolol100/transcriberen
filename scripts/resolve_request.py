#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
LANG_RE = re.compile(r"^(?:auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,16})?)$")
ALLOWED_INPUT_KEYS = {"enabled", "request_id", "url", "language"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def current_contract() -> dict:
    data = json.loads((ROOT / "toolkit-contract.json").read_text(encoding="utf-8"))
    if data.get("project_id") != "project-transcriberen":
        raise ValueError("toolkit contract project_id mismatch")
    version = str(data.get("source_set_version") or "").strip()
    if not version:
        raise ValueError("toolkit contract source_set_version is required")
    return data


def parse_youtube_url(raw: str) -> tuple[str, str, str]:
    value = str(raw or "").strip()
    parts = urlsplit(value)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or host not in YOUTUBE_HOSTS:
        raise ValueError("url must be a direct HTTPS YouTube video or Short URL")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("URL credentials and custom ports are not allowed")

    video_id = ""
    source_type = "video"
    if host == "youtu.be":
        video_id = parts.path.strip("/").split("/", 1)[0]
    elif parts.path == "/watch":
        video_id = (parse_qs(parts.query).get("v") or [""])[0]
    else:
        segments = [segment for segment in parts.path.split("/") if segment]
        if len(segments) == 2 and segments[0].lower() == "shorts":
            video_id = segments[1]
            source_type = "short"

    if not VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError("url must point to one YouTube video or Short")

    if source_type == "short":
        normalized = f"https://www.youtube.com/shorts/{video_id}"
    else:
        normalized = f"https://www.youtube.com/watch?v={video_id}"
    return video_id, source_type, normalized


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

    video_id, source_type, normalized_url = parse_youtube_url(raw.get("url"))
    contract = current_contract()
    return {
        "schema_version": "2.0",
        "enabled": True,
        "request_id": request_id,
        "url": normalized_url,
        "video_id": video_id,
        "source_type": source_type,
        "language": language,
        "project_id": contract["project_id"],
        "source_set_version": contract["source_set_version"],
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

    print(json.dumps({
        "request_id": resolved["request_id"],
        "source_type": resolved["source_type"],
        "video_id": resolved["video_id"],
        "source_set_version": resolved["source_set_version"],
    }))


if __name__ == "__main__":
    main()
