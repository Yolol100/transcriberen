#!/usr/bin/env python3
import hashlib
import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import trafilatura
import youtube_runtime

SECRET_KEY_RE = re.compile(r"(?:token|secret|api[_-]?key|access[_-]?key|password|passwd|authorization|signature|sig|credential)", re.I)
TIMING_RE = re.compile(r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d{3}")
USER_AGENT = "Webactueel-Transcriberen/1.1 (+controlled public-source runtime)"
ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd()))
BIN = ROOT / "tools" / "bin"
MODEL = ROOT / "tools" / "models" / "ggml-base.bin"
RESULTS = ROOT / "results"
DEFAULT_COMMAND_TIMEOUT_SECONDS = 180
YOUTUBE_COMMAND_TIMEOUT_SECONDS = 300
YOUTUBE_COMMENT_TIMEOUT_SECONDS = 900
MEDIA_METADATA_TIMEOUT_SECONDS = 90
SUBTITLE_TIMEOUT_SECONDS = 180
AUDIO_DOWNLOAD_TIMEOUT_SECONDS = 900
WHISPER_TIMEOUT_SECONDS = 5400
MAX_AUTHORIZED_AUDIO_DURATION_SECONDS = 7200
MAX_AUTHORIZED_WAV_BYTES = 320 * 1024 * 1024


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_text(text):
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_public_url(raw):
    parts = urlsplit(str(raw))
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("public http(s) URL required")
    if parts.username or parts.password:
        raise ValueError("URL credentials forbidden")
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if SECRET_KEY_RE.search(key):
            raise ValueError(f"secret-like query parameter forbidden: {key}")
    infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError("hostname did not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved, ip.is_unspecified)):
            raise ValueError(f"non-public address rejected: {ip}")
    return str(raw)


class SafeRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url, max_bytes=10_000_000):
    validate_public_url(url)
    opener = build_opener(SafeRedirects())
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml,text/xml,application/rss+xml,application/atom+xml,*/*;q=0.5"})
    with opener.open(request, timeout=25) as response:
        validate_public_url(response.geturl())
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"source exceeds {max_bytes} byte fetch limit")
        return data, response.geturl(), response.headers.get("content-type", "")


def _timeout_output(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run(command, *, cwd=None, check=True, timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS):
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _timeout_output(exc.stdout)
        stderr = _timeout_output(exc.stderr)
        detail = f"command timed out after {timeout}s"
        if check:
            raise RuntimeError(f"{detail}: {' '.join(map(str, command[:3]))}: {stderr[-2000:]}") from exc
        return subprocess.CompletedProcess(command, 124, stdout, (stderr + "\n" + detail).strip())
    if check and completed.returncode != 0:
        stderr = completed.stderr[-4000:]
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(map(str, command[:3]))}: {stderr}")
    return completed


def youtube_run(command, *, check=True):
    timeout = YOUTUBE_COMMENT_TIMEOUT_SECONDS if "--write-comments" in command else YOUTUBE_COMMAND_TIMEOUT_SECONDS
    return run(command, check=check, timeout=timeout)


# youtube_runtime resolves its module-level run() dynamically, so production
# YouTube discovery/caption/comment commands inherit the same bounded process
# runner without changing their accountless/media-free command contract.
youtube_runtime.run = youtube_run


def tool_versions():
    return {
        "trafilatura": getattr(trafilatura, "__version__", "2.1.0"),
        "yt-dlp": run([str(BIN / "yt-dlp"), "--version"], timeout=30).stdout.strip(),
        "ffmpeg": run(["ffmpeg", "-version"], timeout=30).stdout.splitlines()[0].strip(),
        "ffprobe": run(["ffprobe", "-version"], timeout=30).stdout.splitlines()[0].strip(),
        "whisper.cpp": "v1.9.2" if (BIN / "whisper-cli").exists() else "not-installed",
        "whisper_model": "base@5359861c739e955e79d9a303bcbc70fb988958b1" if MODEL.exists() else "not-installed"
    }


def normalize_subtitles(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    previous = None
    for raw in lines:
        line = raw.strip()
        if not line or line == "WEBVTT" or line.isdigit() or TIMING_RE.search(line) or line.startswith("NOTE "):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line and line != previous:
            out.append(line)
            previous = line
    return "\n".join(out).strip()


def yt_base():
    # Netrc authentication is opt-in in yt-dlp. Do not pass the removed
    # --no-netrc option; omission is the accountless/default-safe behavior.
    # This base is intentionally single-item only. Playlist/channel/search
    # discovery is isolated in youtube_runtime and never inherits --no-playlist.
    return [str(BIN / "yt-dlp"), "--no-config", "--no-cookies", "--no-playlist", "--no-warnings"]


def detect_media(url):
    cmd = yt_base() + ["--simulate", "--dump-single-json", url]
    completed = run(cmd, check=False, timeout=MEDIA_METADATA_TIMEOUT_SECONDS)
    if completed.returncode != 0 or not completed.stdout.strip():
        if youtube_runtime.is_youtube_url(url) and is_youtube_access_blocked_error(completed.stderr):
            raise RuntimeError("youtube_access_blocked: " + completed.stderr[-2000:])
        return None
    try:
        meta = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    final = meta.get("webpage_url") or meta.get("original_url") or url
    validate_public_url(final)
    return {
        "title": meta.get("title"),
        "extractor": meta.get("extractor_key") or meta.get("extractor"),
        "duration": meta.get("duration"),
        "webpage_url": final,
        "id": meta.get("id")
    }


def is_public_youtube(url, media_meta=None):
    extractor = str((media_meta or {}).get("extractor") or "").lower()
    if "youtube" in extractor:
        return True
    return youtube_runtime.is_youtube_url((media_meta or {}).get("webpage_url") or url)


YOUTUBE_ACCESS_BLOCK_PATTERNS = (
    "sign in to confirm you’re not a bot",
    "sign in to confirm you're not a bot",
    "confirm you’re not a bot",
    "confirm you're not a bot",
)


def is_youtube_access_blocked_error(value):
    message = str(value or "").casefold()
    return any(pattern in message for pattern in YOUTUBE_ACCESS_BLOCK_PATTERNS)


def blocked_youtube_collection(req, error, results_dir=None):
    results_dir = Path(results_dir or RESULTS)
    results_dir.mkdir(parents=True, exist_ok=True)
    yt = req.get("youtube") or {}
    scope = yt.get("scope", "video")
    scan_limit = None if scope == "search" else int(yt.get("scan_limit", 500))
    candidate_limit = int(yt.get("candidate_limit", 100)) if scope == "search" else None
    index = {
        "schema_version": "webactueel-youtube-collection/1.1",
        "scope": scope,
        "query": yt.get("query"),
        "collection_status": "access_blocked",
        "language_priority": ["en", "nl", "other"],
        "candidate_count": 0,
        "eligible_count": 0,
        "selected_count": 0,
        "item_count": 0,
        "transcript_count": 0,
        "no_caption_count": 0,
        "caption_error_count": 0,
        "comment_error_count": 0,
        "sort_by": yt.get("sort_by", "relevance"),
        "year_from": yt.get("year_from"),
        "year_to": yt.get("year_to"),
        "include_comments": bool(yt.get("include_comments")),
        "comment_identity_minimized": True,
        "discovery": {
            "scan_limit": scan_limit,
            "candidate_limit": candidate_limit,
            "possibly_truncated": False,
            "access_blocked": True,
            "sources": [],
        },
        "ranking_scope_note": "No ranking was produced because public accountless YouTube access was blocked by the upstream service.",
        "comments_scope_note": None,
        "discovery_errors": [{
            "stage": "access",
            "kind": "access_blocked",
            "error": str(error)[:1000],
        }],
        "items": [],
    }
    content = "# YouTube collection\n\nCollection status: access_blocked\n"
    (results_dir / "youtube-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if req.get("analysis_content_allowed") or req.get("reuse_allowed"):
        (results_dir / "content.md").write_text(content, encoding="utf-8")
    return content, index


def normalize_youtube_access_status(index, results_dir=None):
    errors = index.get("discovery_errors") or []
    if any(is_youtube_access_blocked_error(error.get("error")) for error in errors if isinstance(error, dict)):
        index["collection_status"] = "access_blocked"
        discovery = index.setdefault("discovery", {})
        discovery["access_blocked"] = True
        results_dir = Path(results_dir or RESULTS)
        (results_dir / "youtube-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def media_content(req, media_meta=None):
    media_meta = media_meta or detect_media(req["url"])
    if is_public_youtube(req["url"], media_meta):
        return youtube_runtime.collect_single_transcript(req, media_meta)

    language = req.get("language", "auto")
    lang_selector = "all,-live_chat" if language == "auto" else f"{language},{language}.*"
    with tempfile.TemporaryDirectory(prefix="webactueel-transcribe-") as tmpdir:
        tmp = Path(tmpdir)
        subtitle_cmd = yt_base() + [
            "--write-subs", "--write-auto-subs", "--sub-langs", lang_selector,
            "--sub-format", "srt/vtt/best", "--skip-download",
            "-o", str(tmp / "source.%(ext)s"), req["url"]
        ]
        subtitle_run = run(subtitle_cmd, check=False, timeout=SUBTITLE_TIMEOUT_SECONDS)
        subtitle_files = sorted([*tmp.glob("source*.srt"), *tmp.glob("source*.vtt")])
        for subtitle_file in subtitle_files:
            text = normalize_subtitles(subtitle_file)
            if text:
                return text, "subtitle", {
                    "media": media_meta,
                    "subtitle_file_type": subtitle_file.suffix.lstrip("."),
                    "subtitle_command_exit": subtitle_run.returncode
                }, ["yt-dlp:public-subtitles", "normalize:subtitle-lines"]

        if not req.get("allow_audio_fallback"):
            raise RuntimeError("no usable public subtitles found and allow_audio_fallback=false")
        if not req.get("audio_access_authorized"):
            raise RuntimeError("audio fallback requires explicit audio_access_authorized=true")
        duration = (media_meta or {}).get("duration")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise RuntimeError("authorized audio fallback requires positive media duration metadata")
        if duration > MAX_AUTHORIZED_AUDIO_DURATION_SECONDS:
            raise RuntimeError(f"authorized audio duration exceeds {MAX_AUTHORIZED_AUDIO_DURATION_SECONDS}s safety limit")
        if not (BIN / "whisper-cli").exists() or not MODEL.exists():
            raise RuntimeError("whisper.cpp runtime/model not installed")

        audio_cmd = yt_base() + [
            "-f", "bestaudio/best", "--max-filesize", "256M", "-x", "--audio-format", "wav",
            "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",
            "-o", str(tmp / "audio.%(ext)s"), req["url"]
        ]
        run(audio_cmd, timeout=AUDIO_DOWNLOAD_TIMEOUT_SECONDS)
        audio_files = sorted(tmp.glob("audio*.wav"))
        if not audio_files:
            raise RuntimeError("yt-dlp/ffmpeg produced no WAV")
        audio = audio_files[0]
        if audio.stat().st_size > MAX_AUTHORIZED_WAV_BYTES:
            raise RuntimeError(f"normalized WAV exceeds {MAX_AUTHORIZED_WAV_BYTES} byte safety limit")
        prefix = tmp / "whisper"
        whisper_cmd = [str(BIN / "whisper-cli"), "-m", str(MODEL), "-f", str(audio), "-l", language, "-otxt", "-of", str(prefix)]
        completed = run(whisper_cmd, timeout=WHISPER_TIMEOUT_SECONDS)
        transcript_path = Path(f"{prefix}.txt")
        text = transcript_path.read_text(encoding="utf-8", errors="replace").strip() if transcript_path.exists() else completed.stdout.strip()
        if not text:
            raise RuntimeError("whisper.cpp produced empty transcript")
        return text, "whisper", {
            "media": media_meta,
            "audio_sha256": sha256_file(audio),
            "audio_bytes": audio.stat().st_size,
            "model_sha256": sha256_file(MODEL),
            "audio_access_authorized": True,
            "audio_duration_limit_seconds": MAX_AUTHORIZED_AUDIO_DURATION_SECONDS,
            "audio_wav_limit_bytes": MAX_AUTHORIZED_WAV_BYTES
        }, ["yt-dlp:authorized-audio", "ffmpeg:16khz-mono-wav", "whisper.cpp:base"]


def parse_xml_links(data, base_url, mode):
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("XML DTD/entity declarations are forbidden")
    root = ET.fromstring(data)
    links = []
    if mode == "sitemap" or root.tag.lower().endswith("sitemapindex") or root.tag.lower().endswith("urlset"):
        for element in root.iter():
            if element.tag.lower().endswith("loc") and element.text:
                links.append(element.text.strip())
        detected = "sitemap"
    else:
        for element in root.iter():
            tag = element.tag.lower()
            candidate = None
            if tag.endswith("link"):
                candidate = element.attrib.get("href") or (element.text.strip() if element.text else None)
            if candidate:
                links.append(urljoin(base_url, candidate))
        detected = "feed"
    clean = []
    seen = set()
    for link in links:
        try:
            parts = urlsplit(link)
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                continue
            normalized = link.split("#", 1)[0]
            if normalized not in seen:
                seen.add(normalized)
                clean.append(normalized)
        except Exception:
            continue
    text = "\n".join(f"- {link}" for link in clean[:1000])
    return text, detected, {"discovered_links": len(clean), "stored_links": min(len(clean), 1000)}, [f"xml:{detected}-discovery"]


def article_content(data, final_url):
    html = data.decode("utf-8", errors="replace")
    text = trafilatura.extract(html, output_format="markdown", include_links=True, include_comments=False, favor_precision=True)
    if not text or len(text.strip()) < 80:
        raise RuntimeError("Trafilatura produced insufficient article text")
    return text.strip(), "article", {"final_url": final_url, "fetched_bytes": len(data)}, ["http:public-fetch", "trafilatura:main-text"]


def extract(req):
    mode = req["mode"]
    if mode in {"media", "auto"}:
        media_meta = detect_media(req["url"])
        if mode == "media" or media_meta:
            return media_content(req, media_meta)
    data, final_url, content_type = fetch_public(req["url"])
    if mode in {"feed", "sitemap"}:
        return parse_xml_links(data, final_url, mode)
    if mode == "article":
        return article_content(data, final_url)
    if "xml" in content_type.lower() or data.lstrip().startswith(b"<?xml"):
        return parse_xml_links(data, final_url, "auto")
    return article_content(data, final_url)


def common_result(req, started, normalized, detected_mode, metadata, transformations):
    persist = bool(req.get("analysis_content_allowed") or req.get("reuse_allowed"))
    return {
        "schema_version": "webactueel-transcription-result/1.1",
        "request_id": req["request_id"],
        "owner": "webactueel-workflow",
        "project_id": "project-transcriberen",
        "source_url": req.get("url"),
        "requested_mode": req["mode"],
        "detected_mode": detected_mode,
        "language": req.get("language", "auto"),
        "fetched_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "controlled_runtime",
        "analysis_content_allowed": bool(req.get("analysis_content_allowed")),
        "reuse_allowed": bool(req.get("reuse_allowed")),
        "usage_mode": "reuse-authorized" if req.get("reuse_allowed") else "analysis-paraphrase-only",
        "rights_basis": req.get("rights_basis"),
        "audio_access_authorized": bool(req.get("audio_access_authorized")),
        "content_sha256": sha256_text(normalized),
        "content_chars": len(normalized),
        "content_persisted": persist,
        "metadata": metadata,
        "transformations": transformations,
        "tool_versions": tool_versions(),
        "source_context": req.get("source_context"),
        "limitations": [
            "Transcriptie, captionextractie en metadata-extractie kunnen inhoudelijke fouten bevatten en vereisen bronvergelijking voor belangrijke claims.",
            "controlled_runtime output is geen automatische projectwaarheid; bruikbare kennis vereist inhoudelijke review en deduplicatie door webactueel-workflow.",
            "Publieke YouTube-bronnen zijn uitsluitend captions/metadata/comments; audio/video-download en Whisper-fallback zijn daar geblokkeerd.",
            "YouTube-zoekrangschikking geldt alleen binnen de opgehaalde kandidaatset en is geen globale YouTube-ranking.",
            "Publieke comments kunnen persoonsgegevens bevatten en mogen alleen taakgericht voor analyse worden gebruikt.",
            "De runtime omzeilt geen login, cookies, DRM, paywalls, CAPTCHA of leeftijdscontrole."
        ]
    }


def main():
    req = json.loads(Path(os.environ.get("REQUEST_FILE", "resolved-request.json")).read_text(encoding="utf-8"))
    if req.get("url"):
        validate_public_url(req["url"])
    RESULTS.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()

    if req["mode"] == "youtube":
        try:
            content, index = youtube_runtime.collect(req, RESULTS)
            index = normalize_youtube_access_status(index, RESULTS)
        except RuntimeError as exc:
            if not is_youtube_access_blocked_error(exc):
                raise
            content, index = blocked_youtube_collection(req, exc, RESULTS)
        normalized = content.strip() + "\n"
        metadata = {
            "youtube": {
                "scope": index["scope"],
                "query": index.get("query"),
                "collection_status": index["collection_status"],
                "candidate_count": index["candidate_count"],
                "eligible_count": index["eligible_count"],
                "selected_count": index["selected_count"],
                "item_count": index["item_count"],
                "transcript_count": index["transcript_count"],
                "discovery_possibly_truncated": bool(index.get("discovery", {}).get("possibly_truncated")),
                "sort_by": index["sort_by"],
                "year_from": index.get("year_from"),
                "year_to": index.get("year_to"),
                "include_comments": index["include_comments"],
                "index_file": "youtube-index.json",
                "media_downloaded": False,
            }
        }
        result = common_result(
            req, started, normalized, "youtube", metadata,
            ["yt-dlp:youtube-discovery", "yt-dlp:metadata-only", "yt-dlp:single-selected-caption", "normalize:subtitle-cues", "optional:public-comments"]
        )
    else:
        try:
            content, detected_mode, metadata, transformations = extract(req)
            normalized = content.strip() + "\n"
            result = common_result(req, started, normalized, detected_mode, metadata, transformations)
            if result["content_persisted"]:
                (RESULTS / "content.md").write_text(normalized, encoding="utf-8")
        except RuntimeError as exc:
            if not (req.get("url") and youtube_runtime.is_youtube_url(req["url"]) and is_youtube_access_blocked_error(exc)):
                raise
            content, index = blocked_youtube_collection(req, exc, RESULTS)
            normalized = content.strip() + "\n"
            metadata = {
                "youtube": {
                    "scope": index["scope"],
                    "query": index.get("query"),
                    "collection_status": "access_blocked",
                    "candidate_count": 0,
                    "eligible_count": 0,
                    "selected_count": 0,
                    "item_count": 0,
                    "transcript_count": 0,
                    "discovery_possibly_truncated": False,
                    "sort_by": index["sort_by"],
                    "year_from": index.get("year_from"),
                    "year_to": index.get("year_to"),
                    "include_comments": index["include_comments"],
                    "index_file": "youtube-index.json",
                    "media_downloaded": False,
                }
            }
            result = common_result(req, started, normalized, "youtube", metadata, ["yt-dlp:access-blocked-safe-stop"])

    (RESULTS / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "tool-versions.txt").write_text("\n".join(f"{key}={value}" for key, value in result["tool_versions"].items()) + "\n", encoding="utf-8")
    print(json.dumps({"request_id": req["request_id"], "mode": result["detected_mode"], "content_sha256": result["content_sha256"], "content_persisted": result["content_persisted"]}))


if __name__ == "__main__":
    main()