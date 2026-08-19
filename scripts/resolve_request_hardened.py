#!/usr/bin/env python3
"""Transport-aware request resolver layered on the canonical request contract.

This keeps scripts/resolve_request.py as the policy authority while adding the
new include_replies/include_keywords inputs and workflow_call/request-queue
transport support.
"""
import json
import os
from pathlib import Path

import resolve_request as base


def _normalize_include_keywords(req):
    """Normalize optional per-video topic filters without changing base policy."""
    yt = req.setdefault("youtube", {})
    raw = yt.get("include_keywords", [])
    if raw in (None, ""):
        raw = []
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",") if item.strip()]
    if not isinstance(raw, list) or len(raw) > 30:
        raise ValueError("youtube.include_keywords must be a list of at most 30 values")
    clean = []
    seen = set()
    for value in raw:
        text = str(value).strip()
        if not text or len(text) > 80:
            raise ValueError("youtube.include_keywords values must be 1..80 characters")
        folded = text.casefold()
        if folded not in seen:
            seen.add(folded)
            clean.append(text)
    yt["include_keywords"] = clean
    return req


def _request_from_environment():
    event = os.environ.get("GITHUB_EVENT_NAME", "push")
    request_file = Path(os.environ.get("REQUEST_FILE", "requests/transcribe.json"))
    if event == "workflow_dispatch":
        req = base.from_dispatch()
        req.setdefault("youtube", {})["include_replies"] = base.as_bool(
            os.environ.get("INPUT_YOUTUBE_INCLUDE_REPLIES"), False
        )
        req["youtube"]["include_keywords"] = os.environ.get("INPUT_YOUTUBE_INCLUDE_KEYWORDS", "")
        return _normalize_include_keywords(req)
    return _normalize_include_keywords(json.loads(request_file.read_text(encoding="utf-8")))


def main():
    req = _request_from_environment()
    run = bool(req.get("enabled"))
    if run:
        req.setdefault("youtube", {})["include_replies"] = base.as_bool(
            (req.get("youtube") or {}).get("include_replies"), False
        )
        req = _normalize_include_keywords(req)
        req = base.validate_request(req)

    Path("resolved-request.json").write_text(
        json.dumps(req, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    out = os.environ.get("GITHUB_OUTPUT")
    values = {
        "run": str(run).lower(),
        "request_id": str(req.get("request_id", "none")),
        "install_whisper": str(bool(req.get("allow_audio_fallback") and req.get("audio_access_authorized"))).lower(),
        "reuse_allowed": str(bool(req.get("reuse_allowed"))).lower(),
        "persist_content": str(bool(req.get("analysis_content_allowed") or req.get("reuse_allowed"))).lower(),
    }
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    else:
        print(json.dumps(values))


if __name__ == "__main__":
    main()
