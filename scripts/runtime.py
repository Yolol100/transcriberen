#!/usr/bin/env python3
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import trafilatura
import youtube_runtime

SECRET_KEY_RE = re.compile(r"(?:token|secret|api[_-]?key|access[_-]?key|password|passwd|authorization|signature|sig|credential)", re.I)
TIMING_RE = re.compile(r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d{3}")
USER_AGENT = "Webactueel-Transcriberen/2.0 (+controlled public-source runtime)"
ROBOTS_PRODUCT = "Webactueel-Transcriberen"
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
MAX_HTTP_BYTES = 10_000_000
MAX_ROBOTS_BYTES = 512_000
MAX_REDIRECTS = 5
MAX_HTTP_RETRIES = 3
MAX_RETRY_AFTER_SECONDS = 60
DEFAULT_HOST_DELAY_SECONDS = 1.0
_LAST_FETCH_BY_ORIGIN = {}
_ROBOTS_CACHE = {}


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


def _public_addrinfo(hostname, port):
    infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError("hostname did not resolve")
    out = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved, ip.is_unspecified)):
            raise ValueError(f"non-public address rejected: {ip}")
        out.append(info)
    return out


def validate_public_url(raw):
    parts = urlsplit(str(raw))
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("public http(s) URL required")
    if parts.username or parts.password:
        raise ValueError("URL credentials forbidden")
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if SECRET_KEY_RE.search(key):
            raise ValueError(f"secret-like query parameter forbidden: {key}")
    _public_addrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    return str(raw)


def _proxy_environment_present():
    keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
    return any(str(os.environ.get(key) or "").strip() for key in keys)


@contextmanager
def pinned_public_dns(hostname, port):
    """Pin the request-time DNS result to the addresses that passed SSRF validation."""
    original = socket.getaddrinfo
    approved = _public_addrinfo(hostname, port)
    normalized = hostname.casefold().rstrip(".")

    def pinned(host, query_port, family=0, type=0, proto=0, flags=0):
        if str(host).casefold().rstrip(".") == normalized and int(query_port or port) == int(port):
            matches = []
            for item in approved:
                af, socktype, protocol, canonname, sockaddr = item
                if family not in (0, af):
                    continue
                if type not in (0, socktype):
                    continue
                if proto not in (0, protocol):
                    continue
                matches.append(item)
            return matches or approved
        return original(host, query_port, family, type, proto, flags)

    socket.getaddrinfo = pinned
    try:
        yield
    finally:
        socket.getaddrinfo = original


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _origin(url):
    parts = urlsplit(url)
    default = 443 if parts.scheme == "https" else 80
    port = parts.port or default
    netloc = parts.hostname if port == default else f"{parts.hostname}:{port}"
    return urlunsplit((parts.scheme, netloc, "", "", ""))


def _sleep_for_host(origin, delay):
    delay = max(float(delay or 0.0), DEFAULT_HOST_DELAY_SECONDS)
    last = _LAST_FETCH_BY_ORIGIN.get(origin)
    if last is not None:
        remaining = delay - (time.monotonic() - last)
        if remaining > 0:
            time.sleep(remaining)
    _LAST_FETCH_BY_ORIGIN[origin] = time.monotonic()


def _retry_after_seconds(value):
    if not value:
        return None
    text = str(value).strip()
    if text.isdigit():
        return min(MAX_RETRY_AFTER_SECONDS, max(0, int(text)))
    try:
        when = parsedate_to_datetime(text)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return min(MAX_RETRY_AFTER_SECONDS, max(0, int((when - datetime.now(timezone.utc)).total_seconds())))
    except Exception:
        return None


def _open_direct_once(url, *, max_bytes, accept, timeout=25):
    if _proxy_environment_present():
        raise RuntimeError("controlled HTTP fetch refuses proxy environment because target-IP binding cannot be proven; use an approved browser/collector route")
    validate_public_url(url)
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    opener = build_opener(ProxyHandler({}), NoRedirects())
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with pinned_public_dns(parts.hostname, port):
        try:
            response = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                return {"status": exc.code, "headers": exc.headers, "redirect": exc.headers.get("Location"), "data": b"", "url": url}
            raise
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"source exceeds {max_bytes} byte fetch limit")
        return {"status": int(response.status), "headers": response.headers, "redirect": None, "data": data, "url": response.geturl()}


def _fetch_with_redirects(url, *, max_bytes, accept, delay=0.0, retry=True):
    current = validate_public_url(url)
    for redirect_count in range(MAX_REDIRECTS + 1):
        origin = _origin(current)
        attempts = MAX_HTTP_RETRIES if retry else 1
        last_error = None
        for attempt in range(attempts):
            _sleep_for_host(origin, delay)
            try:
                result = _open_direct_once(current, max_bytes=max_bytes, accept=accept)
                break
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 >= attempts:
                    raise
                wait = _retry_after_seconds(exc.headers.get("Retry-After"))
                time.sleep(wait if wait is not None else min(8, 2 ** attempt))
            except URLError as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    raise
                time.sleep(min(8, 2 ** attempt))
        else:
            raise last_error or RuntimeError("HTTP fetch failed")
        location = result.get("redirect")
        if not location:
            validate_public_url(result["url"])
            return result
        if redirect_count >= MAX_REDIRECTS:
            raise RuntimeError("too many redirects")
        current = validate_public_url(urljoin(current, location))
    raise RuntimeError("too many redirects")


class RobotsRules:
    def __init__(self, groups):
        self.groups = groups

    def can_fetch(self, user_agent, url):
        ua = user_agent.lower()
        matching = []
        for agents, rules in self.groups:
            best = -1
            for agent in agents:
                token = agent.lower().strip()
                if token == "*":
                    best = max(best, 0)
                elif token and token in ua:
                    best = max(best, len(token))
            if best >= 0:
                matching.append((best, rules))
        if not matching:
            return True
        max_specificity = max(item[0] for item in matching)
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        candidates = []
        for specificity, rules in matching:
            if specificity != max_specificity:
                continue
            for allow, pattern in rules:
                if not pattern:
                    continue
                regex = re.escape(pattern).replace(r"\*", ".*")
                if pattern.endswith("$"):
                    regex = regex[:-2] + "$"
                else:
                    regex += ".*"
                if re.match(regex, path):
                    candidates.append((len(pattern.rstrip("$")), allow))
        if not candidates:
            return True
        longest = max(length for length, _ in candidates)
        return any(allow for length, allow in candidates if length == longest)


def parse_robots(raw):
    groups = []
    agents = []
    rules = []
    delay = 0.0
    request_rate = None
    saw_rule = False

    def flush():
        nonlocal agents, rules, saw_rule
        if agents:
            groups.append((tuple(dict.fromkeys(agents)), tuple(rules)))
        agents, rules, saw_rule = [], [], False

    for raw_line in raw.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if saw_rule:
                flush()
            agents.append(value)
        elif key in {"allow", "disallow"} and agents:
            saw_rule = True
            if value:
                rules.append((key == "allow", value))
        elif key == "crawl-delay" and agents:
            try:
                delay = max(delay, float(value))
            except ValueError:
                pass
        elif key == "request-rate" and agents:
            match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", value)
            if match and int(match.group(1)) > 0:
                request_rate = max(request_rate or 0.0, int(match.group(2)) / int(match.group(1)))
    flush()
    return RobotsRules(tuple(groups)), max(delay, request_rate or 0.0)


def robots_policy(url):
    origin = _origin(url)
    cached = _ROBOTS_CACHE.get(origin)
    if cached:
        rules, delay, status = cached
        return rules.can_fetch(ROBOTS_PRODUCT, url) if rules else status == "unavailable", delay, status
    robots_url = origin + "/robots.txt"
    try:
        result = _fetch_with_redirects(
            robots_url,
            max_bytes=MAX_ROBOTS_BYTES,
            accept="text/plain,*/*;q=0.1",
            delay=DEFAULT_HOST_DELAY_SECONDS,
            retry=False,
        )
        status = int(result["status"])
        if 400 <= status <= 499:
            _ROBOTS_CACHE[origin] = (None, DEFAULT_HOST_DELAY_SECONDS, "unavailable")
            return True, DEFAULT_HOST_DELAY_SECONDS, "unavailable"
        if status >= 500:
            _ROBOTS_CACHE[origin] = (None, DEFAULT_HOST_DELAY_SECONDS, "unreachable")
            return False, DEFAULT_HOST_DELAY_SECONDS, "unreachable"
        raw = result["data"].decode("utf-8", errors="replace")
        rules, delay = parse_robots(raw)
        delay = max(delay, DEFAULT_HOST_DELAY_SECONDS)
        _ROBOTS_CACHE[origin] = (rules, delay, "available")
        return rules.can_fetch(ROBOTS_PRODUCT, url), delay, "available"
    except HTTPError as exc:
        if 400 <= exc.code <= 499:
            wait = _retry_after_seconds(exc.headers.get("Retry-After"))
            if wait:
                time.sleep(wait)
            _ROBOTS_CACHE[origin] = (None, DEFAULT_HOST_DELAY_SECONDS, "unavailable")
            return True, DEFAULT_HOST_DELAY_SECONDS, "unavailable"
        _ROBOTS_CACHE[origin] = (None, DEFAULT_HOST_DELAY_SECONDS, "unreachable")
        return False, DEFAULT_HOST_DELAY_SECONDS, "unreachable"
    except Exception:
        _ROBOTS_CACHE[origin] = (None, DEFAULT_HOST_DELAY_SECONDS, "unreachable")
        return False, DEFAULT_HOST_DELAY_SECONDS, "unreachable"


def fetch_public(url, max_bytes=MAX_HTTP_BYTES):
    validate_public_url(url)
    allowed, delay, robots_status = robots_policy(url)
    if not allowed:
        raise PermissionError(f"robots policy blocks source ({robots_status})")
    result = _fetch_with_redirects(
        url,
        max_bytes=max_bytes,
        accept="text/html,application/xml,text/xml,application/rss+xml,application/atom+xml,*/*;q=0.5",
        delay=delay,
        retry=True,
    )
    final_url = result["url"]
    validate_public_url(final_url)
    return result["data"], final_url, result["headers"].get("content-type", ""), {
        "robots_status": robots_status,
        "host_delay_seconds": delay,
        "retry_policy": "bounded-3-with-retry-after",
        "dns_binding": "request-time-pinned-public-addresses",
    }


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


youtube_runtime.run = youtube_run


def _version_or_missing(command, first_line=False):
    try:
        completed = run(command, timeout=30)
        text = completed.stdout.strip()
        return text.splitlines()[0].strip() if first_line else text
    except (FileNotFoundError, RuntimeError):
        return "not-installed"


def tool_versions():
    return {
        "trafilatura": getattr(trafilatura, "__version__", "2.1.0"),
        "yt-dlp": _version_or_missing([str(BIN / "yt-dlp"), "--version"]),
        "ffmpeg": _version_or_missing(["ffmpeg", "-version"], first_line=True) if shutil.which("ffmpeg") else "not-installed",
        "ffprobe": _version_or_missing(["ffprobe", "-version"], first_line=True) if shutil.which("ffprobe") else "not-installed",
        "whisper.cpp": "v1.9.2" if (BIN / "whisper-cli").exists() else "not-installed",
        "whisper_model": "base@5359861c739e955e79d9a303bcbc70fb988958b1" if MODEL.exists() else "not-installed",
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
        "id": meta.get("id"),
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
    "http error 429",
    "too many requests",
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
        "comments_disabled_count": 0,
        "comment_review_candidate_count": 0,
        "sort_by": yt.get("sort_by", "relevance"),
        "year_from": yt.get("year_from"),
        "year_to": yt.get("year_to"),
        "include_comments": bool(yt.get("include_comments")),
        "comment_selection": yt.get("comment_selection", "platform"),
        "comment_identity_minimized": True,
        "comment_text_redaction": "obvious-direct-identifiers",
        "discovery": {
            "scan_limit": scan_limit,
            "candidate_limit": candidate_limit,
            "possibly_truncated": False,
            "access_blocked": True,
            "sources": [],
        },
        "ranking_scope_note": "No ranking was produced because public accountless YouTube access was blocked by the upstream service.",
        "comments_scope_note": None,
        "discovery_errors": [{"stage": "access", "kind": "access_blocked", "error": str(error)[:1000]}],
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
        if not shutil.which("ffmpeg"):
            raise RuntimeError("authorized audio fallback requires ffmpeg")

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
            "audio_wav_limit_bytes": MAX_AUTHORIZED_WAV_BYTES,
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


def article_content(data, final_url, fetch_meta=None):
    raw_html = data.decode("utf-8", errors="replace")
    text = trafilatura.extract(raw_html, output_format="markdown", include_links=True, include_comments=False, favor_precision=True)
    if not text or len(text.strip()) < 80:
        raise RuntimeError("Trafilatura produced insufficient article text")
    metadata = {"final_url": final_url, "fetched_bytes": len(data)}
    metadata.update(fetch_meta or {})
    return text.strip(), "article", metadata, ["http:rfc9309-public-fetch", "trafilatura:main-text"]


def extract(req):
    mode = req["mode"]
    if mode == "media":
        if not youtube_runtime.is_youtube_url(req["url"]):
            allowed, _, robots_status = robots_policy(req["url"])
            if not allowed:
                raise PermissionError(f"robots policy blocks media source ({robots_status})")
        return media_content(req, detect_media(req["url"]))
    if mode == "auto" and youtube_runtime.is_youtube_url(req["url"]):
        return media_content(req, detect_media(req["url"]))
    data, final_url, content_type, fetch_meta = fetch_public(req["url"])
    if mode in {"feed", "sitemap"}:
        text, detected, metadata, transformations = parse_xml_links(data, final_url, mode)
        metadata.update(fetch_meta)
        return text, detected, metadata, transformations
    if mode == "article":
        return article_content(data, final_url, fetch_meta)
    if "xml" in content_type.lower() or data.lstrip().startswith(b"<?xml"):
        text, detected, metadata, transformations = parse_xml_links(data, final_url, "auto")
        metadata.update(fetch_meta)
        return text, detected, metadata, transformations
    return article_content(data, final_url, fetch_meta)


def runtime_provenance(request_path):
    return {
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "head_sha": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "event_name": os.environ.get("GITHUB_EVENT_NAME"),
        "repository_visibility": os.environ.get("GITHUB_REPOSITORY_VISIBILITY"),
        "request_sha256": sha256_file(request_path),
    }


def common_result(req, started, normalized, detected_mode, metadata, transformations, request_path):
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
        "youtube_access_basis": req.get("youtube_access_basis"),
        "public_request_acknowledged": bool(req.get("public_request_acknowledged")),
        "audio_access_authorized": bool(req.get("audio_access_authorized")),
        "content_sha256": sha256_text(normalized),
        "content_chars": len(normalized),
        "content_persisted": persist,
        "metadata": metadata,
        "transformations": transformations,
        "tool_versions": tool_versions(),
        "source_context": req.get("source_context"),
        "runtime_provenance": runtime_provenance(request_path),
        "limitations": [
            "Transcriptie, captionextractie en metadata-extractie kunnen inhoudelijke fouten bevatten en vereisen bronvergelijking voor belangrijke claims.",
            "controlled_runtime output is geen automatische projectwaarheid; bruikbare kennis vereist inhoudelijke review en deduplicatie door webactueel-workflow.",
            "Publieke YouTube-bronnen zijn uitsluitend captions/metadata/comments; audio/video-download en Whisper-fallback zijn daar geblokkeerd.",
            "YouTube-zoekrangschikking geldt alleen binnen de opgehaalde kandidaatset en is geen globale YouTube-ranking.",
            "Comment review ranking is kandidaatselectie; commenttekst blijft onbetrouwbare brondata en nooit een instructie.",
            "De runtime omzeilt geen login, cookies, DRM, paywalls, CAPTCHA of leeftijdscontrole.",
        ],
    }


def main():
    request_path = Path(os.environ.get("REQUEST_FILE", "resolved-request.json"))
    req = json.loads(request_path.read_text(encoding="utf-8"))
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
                "comment_review_candidate_count": index.get("comment_review_candidate_count", 0),
                "discovery_possibly_truncated": bool(index.get("discovery", {}).get("possibly_truncated")),
                "sort_by": index["sort_by"],
                "year_from": index.get("year_from"),
                "year_to": index.get("year_to"),
                "include_comments": index["include_comments"],
                "comment_selection": index.get("comment_selection", "platform"),
                "index_file": "youtube-index.json",
                "media_downloaded": False,
            }
        }
        result = common_result(
            req, started, normalized, "youtube", metadata,
            ["yt-dlp:youtube-discovery", "yt-dlp:metadata-only", "yt-dlp:single-selected-caption", "normalize:subtitle-cues", "optional:minimized-public-comments"],
            request_path,
        )
    else:
        try:
            content, detected_mode, metadata, transformations = extract(req)
            normalized = content.strip() + "\n"
            result = common_result(req, started, normalized, detected_mode, metadata, transformations, request_path)
            if result["content_persisted"]:
                (RESULTS / "content.md").write_text(normalized, encoding="utf-8")
        except RuntimeError as exc:
            if not (req.get("url") and youtube_runtime.is_youtube_url(req["url"]) and is_youtube_access_blocked_error(exc)):
                raise
            content, index = blocked_youtube_collection(req, exc, RESULTS)
            normalized = content.strip() + "\n"
            metadata = {
                "youtube": {
                    "scope": index["scope"], "query": index.get("query"), "collection_status": "access_blocked",
                    "candidate_count": 0, "eligible_count": 0, "selected_count": 0, "item_count": 0,
                    "transcript_count": 0, "discovery_possibly_truncated": False, "sort_by": index["sort_by"],
                    "year_from": index.get("year_from"), "year_to": index.get("year_to"),
                    "include_comments": index["include_comments"], "comment_selection": index.get("comment_selection", "platform"),
                    "index_file": "youtube-index.json", "media_downloaded": False,
                }
            }
            result = common_result(req, started, normalized, "youtube", metadata, ["yt-dlp:access-blocked-safe-stop"], request_path)

    (RESULTS / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "tool-versions.txt").write_text("\n".join(f"{key}={value}" for key, value in result["tool_versions"].items()) + "\n", encoding="utf-8")
    print(json.dumps({"request_id": req["request_id"], "mode": result["detected_mode"], "content_sha256": result["content_sha256"], "content_persisted": result["content_persisted"]}))


if __name__ == "__main__":
    main()
