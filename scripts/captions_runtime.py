#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "tools" / "bin"
RESULTS = ROOT / "results"
LANG_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-.][A-Za-z0-9]{2,16})*$")
TIMESTAMP_RE = re.compile(
    r"^(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}\s+-->\s+"
    r"(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)
TIMESTAMP_PARSE_RE = re.compile(
    r"^((?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3})\s+-->\s+"
    r"((?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3})"
)
INLINE_TIMESTAMP_RE = re.compile(r"<\d{1,2}:\d{2}:\d{2}[.]\d{3}>")
ACCESS_BLOCK_MARKERS = (
    "sign in to confirm",
    "confirm you're not a bot",
    "confirm you are not a bot",
    "http error 403",
    "http error 429",
    "too many requests",
)


def run(command: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + "\ncommand timed out",
        )


def yt_base() -> list[str]:
    return [
        str(BIN / "yt-dlp"),
        "--no-config",
        "--no-cookies",
        "--no-warnings",
        "--skip-download",
        "--no-playlist",
        "--retries",
        "3",
        "--extractor-retries",
        "3",
        "--socket-timeout",
        "30",
        "--extractor-args",
        "youtube:skip=translated_subs",
    ]


def classify_failure(message: str) -> str:
    text = str(message or "").casefold()
    if any(marker in text for marker in ACCESS_BLOCK_MARKERS):
        return "access_blocked"
    return "error"


def load_metadata(url: str) -> dict:
    completed = run([*yt_base(), "--dump-single-json", url])
    if completed.returncode != 0 or not completed.stdout.strip():
        detail = completed.stderr[-2000:] or "yt-dlp returned no metadata"
        raise RuntimeError(f"{classify_failure(detail)}::{detail}")
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"error::yt-dlp returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("error::yt-dlp returned unexpected metadata")
    return data


def language_family(code: str) -> str:
    value = str(code or "").lower().replace("_", "-")
    return value.split("-", 1)[0].split(".", 1)[0]


def format_is_translation(item: dict) -> bool:
    url = item.get("url") if isinstance(item, dict) else None
    if not isinstance(url, str) or not url:
        return False
    try:
        return bool(parse_qs(urlsplit(url).query).get("tlang"))
    except Exception:
        return False


def track_codes(mapping: dict | None) -> list[str]:
    codes: list[str] = []
    for code, formats in (mapping or {}).items():
        if code == "live_chat" or not formats or not LANG_TAG_RE.fullmatch(str(code)):
            continue
        usable = [item for item in formats if isinstance(item, dict)]
        if not usable or all(format_is_translation(item) for item in usable):
            continue
        codes.append(str(code))
    return sorted(set(codes))


def choose_caption_track(meta: dict, preferred_language: str = "auto") -> dict | None:
    manual = track_codes(meta.get("subtitles"))
    automatic = track_codes(meta.get("automatic_captions"))
    if not manual and not automatic:
        return None

    preferred = str(preferred_language or "auto").strip().lower()
    priorities: list[str] = []
    if preferred != "auto":
        priorities.append(language_family(preferred))
    for family in ("en", "nl"):
        if family not in priorities:
            priorities.append(family)

    for family in priorities:
        for kind, codes in (("manual", manual), ("automatic", automatic)):
            exact = next((code for code in codes if code.casefold() == preferred.casefold()), None)
            if preferred != "auto" and exact:
                return {"language": exact, "kind": kind}
            family_match = next((code for code in codes if language_family(code) == family), None)
            if family_match:
                return {"language": family_match, "kind": kind}

    for kind, codes in (("manual", manual), ("automatic", automatic)):
        if codes:
            return {"language": codes[0], "kind": kind}
    return None


def clean_caption_text(text: str) -> str:
    value = INLINE_TIMESTAMP_RE.sub("", text)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value).replace("\u00a0", " ").replace("\u200b", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", " ", value)
    return value.strip()


def token_key(token: str) -> str:
    return re.sub(r"\W+", "", token, flags=re.UNICODE).casefold()


def remove_caption_overlap(previous: str, current: str) -> str:
    if not current:
        return ""
    if not previous:
        return current
    if previous.casefold() == current.casefold():
        return ""
    prev_tokens = previous.split()
    curr_tokens = current.split()
    prev_keys = [token_key(token) for token in prev_tokens]
    curr_keys = [token_key(token) for token in curr_tokens]
    for size in range(min(len(prev_keys), len(curr_keys), 40), 1, -1):
        if prev_keys[-size:] == curr_keys[:size]:
            return " ".join(curr_tokens[size:]).strip()
    return current


def subtitle_segments(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", raw)
    parsed: list[dict] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        first = lines[0].lstrip("\ufeff")
        upper = first.upper()
        if upper == "WEBVTT" or upper.startswith(("NOTE", "STYLE", "REGION")):
            continue
        if all(line.startswith(("Kind:", "Language:", "X-TIMESTAMP-MAP")) for line in lines):
            continue

        timing_index = next((i for i, line in enumerate(lines) if TIMESTAMP_RE.match(line)), None)
        start = end = None
        if timing_index is not None:
            match = TIMESTAMP_PARSE_RE.match(lines[timing_index])
            if match:
                start, end = match.groups()
            text_lines = lines[timing_index + 1 :]
        else:
            if any(line.startswith(("Kind:", "Language:", "X-TIMESTAMP-MAP")) for line in lines):
                continue
            text_lines = [line for line in lines if not line.isdigit()]

        cue = clean_caption_text(" ".join(text_lines))
        if cue:
            parsed.append({"start": start, "end": end, "text": cue})

    out: list[dict] = []
    previous = ""
    for item in parsed:
        residual = remove_caption_overlap(previous, item["text"])
        if residual:
            out.append({"start": item["start"], "end": item["end"], "text": residual})
        previous = item["text"]
    return out


def download_caption(url: str, track: dict) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory(prefix="transcriberen-caption-") as temp_dir:
        output_template = Path(temp_dir) / "source.%(ext)s"
        code = re.escape(track["language"])
        command = yt_base()
        if track["kind"] == "manual":
            command += ["--write-subs", "--no-write-auto-subs"]
        else:
            command += ["--write-auto-subs", "--no-write-subs"]
        command += [
            "--sub-langs",
            f"^{code}$",
            "--sub-format",
            "vtt/srt/best",
            "-o",
            str(output_template),
            url,
        ]
        completed = run(command)
        files = sorted([*Path(temp_dir).glob("source*.vtt"), *Path(temp_dir).glob("source*.srt")])
        for subtitle_file in files:
            segments = subtitle_segments(subtitle_file)
            text = "\n".join(item["text"] for item in segments).strip()
            if text:
                return text, {
                    "language": track["language"],
                    "kind": track["kind"],
                    "format": subtitle_file.suffix.lstrip("."),
                    "cue_count": len(segments),
                }
        detail = completed.stderr[-2000:] or "caption download produced no usable subtitle file"
        raise RuntimeError(f"{classify_failure(detail)}::{detail}")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def yt_dlp_version() -> str:
    completed = run([str(BIN / "yt-dlp"), "--version"], timeout=30)
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def runtime_provenance() -> dict:
    return {
        "repository": os.environ.get("GITHUB_REPOSITORY", "Yolol100/transcriberen"),
        "head_sha": os.environ.get("GITHUB_SHA", "local-unversioned"),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", "local"),
        "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "execution_target": os.environ.get("TRANSCRIBE_EXECUTION_TARGET", "local"),
        "yt_dlp_version": yt_dlp_version(),
    }


def base_result(request: dict) -> dict:
    return {
        "schema_version": "2.1",
        "request_id": request["request_id"],
        "status": "error",
        "source": {
            "url": request["url"],
            "video_id": request["video_id"],
            "type": request["source_type"],
        },
        "caption": None,
        "transcript_sha256": None,
        "transcript_chars": 0,
        "runtime_provenance": runtime_provenance(),
        "media_downloaded": False,
    }


def write_result(result: dict, transcript: str | None = None) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    for child in RESULTS.iterdir():
        if child.is_file():
            child.unlink()
    if transcript is not None:
        (RESULTS / "transcript.txt").write_text(transcript.rstrip() + "\n", encoding="utf-8")
    (RESULTS / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    request_file = Path(os.environ.get("REQUEST_FILE", "resolved-request.json"))
    request = json.loads(request_file.read_text(encoding="utf-8"))
    result = base_result(request)

    try:
        metadata = load_metadata(request["url"])
        track = choose_caption_track(metadata, request.get("language", "auto"))
        if not track:
            result["status"] = "skipped_no_captions"
            write_result(result)
            print(json.dumps({"request_id": request["request_id"], "status": result["status"]}))
            return

        transcript, caption = download_caption(request["url"], track)
        normalized = transcript.rstrip() + "\n"
        result["status"] = "ok"
        result["caption"] = caption
        result["transcript_sha256"] = sha256_text(normalized)
        result["transcript_chars"] = len(normalized)
        write_result(result, normalized)
    except Exception as exc:
        raw = str(exc)
        status, _, detail = raw.partition("::")
        if status not in {"access_blocked", "error"}:
            status, detail = "error", raw
        result["status"] = status
        result["error"] = detail[-2000:]
        write_result(result)

    print(json.dumps({"request_id": request["request_id"], "status": result["status"]}))


if __name__ == "__main__":
    main()
