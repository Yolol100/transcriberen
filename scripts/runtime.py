#!/usr/bin/env python3
import hashlib
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import trafilatura

SECRET_KEY_RE = re.compile(r"(?:token|secret|api[_-]?key|access[_-]?key|password|passwd|authorization|signature|sig|credential)", re.I)
TIMING_RE = re.compile(r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d{3}")
USER_AGENT = "Webactueel-Transcriberen/1.0 (+controlled public-source runtime)"
ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd()))
BIN = ROOT / "tools" / "bin"
MODEL = ROOT / "tools" / "models" / "ggml-base.bin"
RESULTS = ROOT / "results"
DEFAULT_COMMAND_TIMEOUT_SECONDS = 180
MEDIA_METADATA_TIMEOUT_SECONDS = 90
SUBTITLE_TIMEOUT_SECONDS = 180
AUDIO_DOWNLOAD_TIMEOUT_SECONDS = 900
WHISPER_TIMEOUT_SECONDS = 5400
MAX_AUTHORIZED_AUDIO_DURATION_SECONDS = 7200
MAX_AUTHORIZED_AUDIO_SOURCE_BYTES = 256 * 1024 * 1024
MAX_AUTHORIZED_WAV_BYTES = 320 * 1024 * 1024


class CaptionUnavailableError(RuntimeError):
    """The public source was reachable, but no usable caption track was exposed."""


class CaptionAccessError(RuntimeError):
    """Caption retrieval failed before availability could be determined reliably."""


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


def canonical_request_sha256(req):
    encoded = json.dumps(req, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(encoded)


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
    opener = build_opener(ProxyHandler({}), SafeRedirects())
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


def _existing_digest(path):
    if not path:
        return None
    candidate = Path(path)
    return sha256_file(candidate) if candidate.is_file() else None


def tool_digests():
    candidates = {
        "yt-dlp": BIN / "yt-dlp.bin",
        "deno": BIN / "deno",
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "whisper.cpp": BIN / "whisper-cli",
        "whisper_model": MODEL,
    }
    return {name: digest for name, path in candidates.items() if (digest := _existing_digest(path))}


def tool_versions():
    return {
        "trafilatura": getattr(trafilatura, "__version__", "2.1.0"),
        "yt-dlp": run([str(BIN / "yt-dlp"), "--version"], timeout=30).stdout.strip(),
        "ffmpeg": run(["ffmpeg", "-version"], timeout=30).stdout.splitlines()[0].strip(),
        "ffprobe": run(["ffprobe", "-version"], timeout=30).stdout.splitlines()[0].strip(),
        "whisper.cpp": "v1.9.2" if (BIN / "whisper-cli").exists() else "not-installed",
        "whisper_model": "base@5359861c739e955e79d9a303bcbc70fb988958b1" if MODEL.exists() else "not-installed",
    }


def runtime_provenance(req):
    return {
        "request_sha256": canonical_request_sha256(req),
        "repository_commit": os.environ.get("GITHUB_SHA", "local"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_ref": os.environ.get("GITHUB_REF"),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "tool_sha256": tool_digests(),
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
    return [
        str(BIN / "yt-dlp"),
        "--no-config", "--no-cookies", "--no-playlist", "--no-warnings",
        "--proxy", "", "--socket-timeout", "30", "--retries", "3", "--extractor-retries", "3",
    ]


def detect_media(url):
    cmd = yt_base() + ["--simulate", "--dump-single-json", url]
    completed = run(cmd, check=False, timeout=MEDIA_METADATA_TIMEOUT_SECONDS)
    if completed.returncode != 0 or not completed.stdout.strip():
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
        "id": meta.get("id"),
    }


def is_public_youtube(url, media_meta=None):
    extractor = str((media_meta or {}).get("extractor") or "").lower()
    if "youtube" in extractor:
        return True
    host = (urlsplit(str((media_meta or {}).get("webpage_url") or url)).hostname or "").lower().rstrip(".")
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def media_content(req, media_meta=None):
    language = req.get("language", "auto")
    lang_selector = "all,-live_chat" if language == "auto" else f"{language},{language}.*"
    media_meta = media_meta or detect_media(req["url"])
    with tempfile.TemporaryDirectory(prefix="webactueel-transcribe-") as tmpdir:
        tmp = Path(tmpdir)
        subtitle_cmd = yt_base() + [
            "--write-subs", "--write-auto-subs", "--sub-langs", lang_selector,
            "--sub-format", "srt/vtt/best", "--skip-download",
            "-o", str(tmp / "source.%(ext)s"), req["url"],
        ]
        subtitle_run = run(subtitle_cmd, check=False, timeout=SUBTITLE_TIMEOUT_SECONDS)
        subtitle_files = sorted([*tmp.glob("source*.srt"), *tmp.glob("source*.vtt")])
        for subtitle_file in subtitle_files:
            text = normalize_subtitles(subtitle_file)
            if text:
                return text, "subtitle", {
                    "media": media_meta,
                    "subtitle_file_type": subtitle_file.suffix.lstrip("."),
                    "subtitle_command_exit": subtitle_run.returncode,
                }, ["yt-dlp:public-subtitles", "normalize:subtitle-lines"]

        if is_public_youtube(req["url"], media_meta):
            if subtitle_run.returncode != 0:
                detail = (subtitle_run.stderr or subtitle_run.stdout).strip()[-1600:] or f"yt-dlp exit {subtitle_run.returncode}"
                raise CaptionAccessError(
                    "public YouTube caption access failed before availability could be determined: " + detail
                )
            raise CaptionUnavailableError(
                "public YouTube source is captions/metadata only and exposed no usable public captions"
            )
        if not req.get("allow_audio_fallback"):
            raise RuntimeError("no usable public subtitles found and allow_audio_fallback=false")
        if not req.get("audio_access_authorized"):
            raise RuntimeError("audio fallback requires explicit audio_access_authorized=true")
        duration = (media_meta or {}).get("duration")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise RuntimeError("authorized audio fallback requires positive media duration metadata")
        if duration > MAX_AUTHORIZED_AUDIO_DURATION_SECONDS:
            raise RuntimeError(
                f"authorized audio duration exceeds {MAX_AUTHORIZED_AUDIO_DURATION_SECONDS}s safety limit"
            )
        if not (BIN / "whisper-cli").exists() or not MODEL.exists():
            raise RuntimeError("whisper.cpp runtime/model not installed")

        audio_cmd = yt_base() + [
            "-f", "bestaudio/best", "--max-filesize", "256M", "-x", "--audio-format", "wav",
            "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",
            "-o", str(tmp / "audio.%(ext)s"), req["url"],
        ]
        run(audio_cmd, timeout=AUDIO_DOWNLOAD_TIMEOUT_SECONDS)
        audio_files = sorted(tmp.glob("audio*.wav"))
        if not audio_files:
            raise RuntimeError("yt-dlp/ffmpeg produced no WAV")
        audio = audio_files[0]
        if audio.stat().st_size > MAX_AUTHORIZED_WAV_BYTES:
            raise RuntimeError(f"normalized WAV exceeds {MAX_AUTHORIZED_WAV_BYTES} byte safety limit")
        prefix = tmp / "whisper"
        whisper_cmd = [
            str(BIN / "whisper-cli"), "-m", str(MODEL), "-f", str(audio),
            "-l", language, "-otxt", "-of", str(prefix),
        ]
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
            "audio_source_limit_bytes": MAX_AUTHORIZED_AUDIO_SOURCE_BYTES,
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
        if mode == "media" or media_meta or (mode == "auto" and is_public_youtube(req["url"])):
            return media_content(req, media_meta)
    data, final_url, content_type = fetch_public(req["url"])
    if mode in {"feed", "sitemap"}:
        return parse_xml_links(data, final_url, mode)
    if mode == "article":
        return article_content(data, final_url)
    if "xml" in content_type.lower() or data.lstrip().startswith(b"<?xml"):
        return parse_xml_links(data, final_url, "auto")
    return article_content(data, final_url)


def main():
    req = json.loads(Path(os.environ.get("REQUEST_FILE", "resolved-request.json")).read_text(encoding="utf-8"))
    validate_public_url(req["url"])
    RESULTS.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    content, detected_mode, metadata, transformations = extract(req)
    normalized = content.strip() + "\n"
    result = {
        "schema_version": "webactueel-transcription-result/1.0",
        "request_id": req["request_id"],
        "owner": "webactueel-workflow",
        "project_id": "project-transcriberen",
        "source_url": req["url"],
        "requested_mode": req["mode"],
        "detected_mode": detected_mode,
        "language": req.get("language", "auto"),
        "fetched_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "controlled_runtime",
        "reuse_allowed": bool(req.get("reuse_allowed")),
        "rights_basis": req.get("rights_basis"),
        "audio_access_authorized": bool(req.get("audio_access_authorized")),
        "content_sha256": sha256_text(normalized),
        "content_chars": len(normalized),
        "content_persisted": bool(req.get("reuse_allowed")),
        "metadata": metadata,
        "transformations": transformations,
        "tool_versions": tool_versions(),
        "provenance": runtime_provenance(req),
        "source_context": req.get("source_context"),
        "limitations": [
            "Transcriptie en extractie kunnen inhoudelijke fouten bevatten en vereisen bronvergelijking voor belangrijke claims.",
            "controlled_runtime output is geen automatische projectwaarheid.",
            "Publieke YouTube-bronnen zijn uitsluitend captions/metadata; audio/video-download en Whisper-fallback zijn daar geblokkeerd.",
            "De runtime omzeilt geen login, cookies, DRM, paywalls of systeemproxy's.",
        ],
    }
    content_path = RESULTS / "content.md"
    if req.get("reuse_allowed"):
        content_path.write_text(normalized, encoding="utf-8")
    elif content_path.exists():
        content_path.unlink()
    (RESULTS / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "tool-versions.txt").write_text("\n".join(f"{key}={value}" for key, value in result["tool_versions"].items()) + "\n", encoding="utf-8")
    print(json.dumps({"request_id": req["request_id"], "mode": detected_mode, "content_sha256": result["content_sha256"], "content_persisted": result["content_persisted"]}))


if __name__ == "__main__":
    main()
