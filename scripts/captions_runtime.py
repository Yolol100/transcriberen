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
LANG_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-.][A-Za-z0-9]{2,16})*$")
TIMESTAMP_RE = re.compile(r"^(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}\s+-->\s+(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$")
INLINE_TIMESTAMP_RE = re.compile(r"<\d{1,2}:\d{2}:\d{2}[.]\d{3}>")
ACCESS_BLOCK_MARKERS = ("sign in to confirm", "confirm you're not a bot", "confirm you are not a bot", "http error 403", "http error 429", "too many requests")


def run(command: list[str], timeout: int = 240) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(command, 124, stdout=exc.stdout or "", stderr=(exc.stderr or "") + "\ncommand timed out")


def yt_video_base(extractor_args: str = "youtube:skip=translated_subs") -> list[str]:
    return [str(BIN / "yt-dlp"), "--no-config", "--no-cookies", "--skip-download", "--no-playlist", "--retries", "3", "--extractor-retries", "3", "--socket-timeout", "30", "--extractor-args", extractor_args]


def classify_failure(message: str) -> str:
    text = str(message or "").casefold()
    return "access_blocked" if any(marker in text for marker in ACCESS_BLOCK_MARKERS) else "error"


def load_metadata(url: str) -> dict:
    completed = run([*yt_video_base(), "--dump-single-json", url])
    diagnostic = completed.stderr[-2000:]
    if diagnostic and classify_failure(diagnostic) == "access_blocked":
        raise RuntimeError(f"access_blocked::{diagnostic}")
    if completed.returncode != 0 or not completed.stdout.strip():
        detail = diagnostic or "yt-dlp returned no metadata"
        raise RuntimeError(f"{classify_failure(detail)}::{detail}")
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"error::yt-dlp returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("error::yt-dlp returned unexpected metadata")
    return data


def load_top_comments(url: str, limit: int = 7) -> tuple[list[dict], str]:
    args = f"youtube:skip=translated_subs;comment_sort=top;max_comments={limit},{limit},0,0,1"
    completed = run([*yt_video_base(args), "--write-comments", "--dump-single-json", url], timeout=300)
    if completed.returncode != 0 or not completed.stdout.strip():
        return [], classify_failure(completed.stderr[-2000:])
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return [], "error"
    comments = data.get("comments") if isinstance(data, dict) else None
    if not isinstance(comments, list):
        return [], "unavailable"
    out = []
    for item in comments:
        if not isinstance(item, dict) or item.get("parent") not in {None, "root"}:
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        try:
            like_count = int(item.get("like_count") or 0)
        except (TypeError, ValueError):
            like_count = 0
        out.append({
            "id": str(item.get("id") or ""),
            "author": str(item.get("author") or ""),
            "text": text,
            "like_count": like_count,
            "timestamp": item.get("timestamp"),
            "is_pinned": bool(item.get("is_pinned")),
            "author_is_uploader": bool(item.get("author_is_uploader")),
        })
        if len(out) >= limit:
            break
    return out, "ok"


def language_family(code: str) -> str:
    return str(code or "").lower().replace("_", "-").split("-", 1)[0].split(".", 1)[0]


def format_is_translation(item: dict) -> bool:
    url = item.get("url") if isinstance(item, dict) else None
    if not isinstance(url, str) or not url:
        return False
    try:
        return bool(parse_qs(urlsplit(url).query).get("tlang"))
    except Exception:
        return False


def track_codes(mapping: dict | None) -> list[str]:
    codes = []
    for code, formats in (mapping or {}).items():
        if code == "live_chat" or not formats or not LANG_TAG_RE.fullmatch(str(code)):
            continue
        usable = [item for item in formats if isinstance(item, dict)]
        if usable and not all(format_is_translation(item) for item in usable):
            codes.append(str(code))
    return sorted(set(codes))


def choose_caption_track(meta: dict, preferred_language: str = "auto") -> dict | None:
    manual = track_codes(meta.get("subtitles"))
    automatic = track_codes(meta.get("automatic_captions"))
    if not manual and not automatic:
        return None
    preferred = str(preferred_language or "auto").strip().lower()
    kinds = (("manual", manual), ("automatic", automatic))
    if preferred != "auto":
        for kind, codes in kinds:
            exact = next((code for code in codes if code.casefold() == preferred.casefold()), None)
            if exact:
                return {"language": exact, "kind": kind}
        family = language_family(preferred)
        for kind, codes in kinds:
            match = next((code for code in codes if language_family(code) == family), None)
            if match:
                return {"language": match, "kind": kind}
    for family in ("en", "nl"):
        for kind, codes in kinds:
            match = next((code for code in codes if language_family(code) == family), None)
            if match:
                return {"language": match, "kind": kind}
    for kind, codes in kinds:
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
    if not current or not previous:
        return current
    if previous.casefold() == current.casefold():
        return ""
    prev_tokens, curr_tokens = previous.split(), current.split()
    prev_keys = [token_key(token) for token in prev_tokens]
    curr_keys = [token_key(token) for token in curr_tokens]
    for size in range(min(len(prev_keys), len(curr_keys), 40), 1, -1):
        if prev_keys[-size:] == curr_keys[:size]:
            return " ".join(curr_tokens[size:]).strip()
    return current


def subtitle_segments(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    parsed = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        first = lines[0].lstrip("\ufeff")
        upper = first.upper()
        if upper == "WEBVTT" or upper.startswith(("NOTE", "STYLE", "REGION")):
            continue
        timing_index = next((i for i, line in enumerate(lines) if TIMESTAMP_RE.match(line)), None)
        if timing_index is not None:
            text_lines = lines[timing_index + 1:]
        else:
            if any(line.startswith(("Kind:", "Language:", "X-TIMESTAMP-MAP")) for line in lines):
                continue
            text_lines = [line for line in lines if not line.isdigit()]
        cue = clean_caption_text(" ".join(text_lines))
        if cue:
            parsed.append(cue)
    out, previous = [], ""
    for cue in parsed:
        residual = remove_caption_overlap(previous, cue)
        if residual:
            out.append(residual)
        previous = cue
    return [{"text": text} for text in out]


def download_caption(url: str, track: dict) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory(prefix="transcriberen-caption-") as temp_dir:
        output_template = Path(temp_dir) / "source.%(ext)s"
        code = re.escape(track["language"])
        command = yt_video_base()
        command += ["--write-subs", "--no-write-auto-subs"] if track["kind"] == "manual" else ["--write-auto-subs", "--no-write-subs"]
        command += ["--sub-langs", f"^{code}$", "--sub-format", "vtt/srt/best", "-o", str(output_template), url]
        completed = run(command)
        files = sorted([*Path(temp_dir).glob("source*.vtt"), *Path(temp_dir).glob("source*.srt")])
        for subtitle_file in files:
            segments = subtitle_segments(subtitle_file)
            text = "\n".join(item["text"] for item in segments).strip()
            if text:
                return text.rstrip() + "\n", {"language": track["language"], "kind": track["kind"], "format": subtitle_file.suffix.lstrip("."), "cue_count": len(segments)}
        detail = completed.stderr[-2000:] or "caption download produced no usable subtitle file"
        raise RuntimeError(f"{classify_failure(detail)}::{detail}")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tool_version(name: str) -> str:
    completed = run([str(BIN / name), "--version"], timeout=30)
    return completed.stdout.strip().splitlines()[0] if completed.returncode == 0 else "unknown"


def runtime_provenance() -> dict:
    deno = tool_version("deno").split()
    return {
        "repository": os.environ.get("GITHUB_REPOSITORY", "Yolol100/transcriberen"),
        "head_sha": os.environ.get("GITHUB_SHA", "local-unversioned"),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", "local"),
        "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "execution_target": os.environ.get("TRANSCRIBE_EXECUTION_TARGET", "local"),
        "yt_dlp_version": tool_version("yt-dlp"),
        "deno_version": deno[1] if len(deno) >= 2 and deno[0].casefold() == "deno" else "unknown",
    }
