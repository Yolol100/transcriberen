#!/usr/bin/env python3
"""Accountless YouTube discovery/caption/comment collection for Project Transcriberen.

All yt-dlp invocations in this module are metadata/caption/comment-only and include
--skip-download. Public YouTube media is never downloaded.
"""
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "tools" / "bin"
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
TIMING_RE = re.compile(r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d{3}")
LANG_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-.][A-Za-z0-9]{2,16})*$")


def run(command, *, check=True):
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command[:4])}: {completed.stderr[-4000:]}")
    return completed


def yt_base(*, single=False):
    cmd = [
        str(BIN / "yt-dlp"),
        "--no-config", "--no-cookies", "--no-netrc", "--no-warnings",
        "--skip-download",
        "--extractor-args", "youtube:skip=translated_subs",
    ]
    if single:
        cmd.append("--no-playlist")
    return cmd


def is_youtube_url(url):
    try:
        host = (urlsplit(str(url)).hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return host in YOUTUBE_HOSTS or host.endswith(".youtube.com")


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def language_family(code):
    code = str(code or "").lower().replace("_", "-")
    if code == "en" or code.startswith("en-") or code.startswith("en."):
        return "en"
    if code == "nl" or code.startswith("nl-") or code.startswith("nl."):
        return "nl"
    return code.split("-", 1)[0].split(".", 1)[0]


def _format_is_translation(item):
    if not isinstance(item, dict):
        return False
    url = item.get("url")
    if not isinstance(url, str) or not url:
        return False
    try:
        return bool(parse_qs(urlsplit(url).query).get("tlang"))
    except Exception:
        return False


def _track_codes(mapping):
    codes = []
    for code, formats in (mapping or {}).items():
        if code == "live_chat" or not formats or not LANG_TAG_RE.fullmatch(str(code)):
            continue
        usable = [item for item in formats if isinstance(item, dict)]
        # yt-dlp's skip=translated_subs is requested for every YouTube call,
        # but historical edge cases have leaked translated tracks. A YouTube
        # caption URL with `tlang` is a translated target, so never choose a
        # track when every usable format is explicitly translated.
        if usable and all(_format_is_translation(item) for item in usable):
            continue
        codes.append(code)
    return sorted(codes)


def choose_caption_track(meta, preferred_language="auto"):
    """Pick exactly one track.

    Priority is explicit language (when supplied), then English, Dutch, then any
    other language. Within a language, manual subtitles beat automatic captions.
    Auto-translated captions are excluded at extraction time via translated_subs.
    """
    manual = _track_codes(meta.get("subtitles"))
    automatic = _track_codes(meta.get("automatic_captions"))
    if not manual and not automatic:
        return None

    priorities = []
    preferred = str(preferred_language or "auto").strip().lower()
    if preferred != "auto":
        priorities.append(language_family(preferred))
    for family in ("en", "nl"):
        if family not in priorities:
            priorities.append(family)

    for family in priorities:
        for kind, codes in (("manual", manual), ("automatic", automatic)):
            for code in codes:
                if language_family(code) == family:
                    return {"language": code, "kind": kind}

    # For all remaining languages prefer a human/manual track, then automatic.
    used_families = set(priorities)
    for kind, codes in (("manual", manual), ("automatic", automatic)):
        for code in codes:
            if language_family(code) not in used_families:
                return {"language": code, "kind": kind}
    return None


def subtitle_command(url, track, output_template):
    code = re.escape(track["language"])
    cmd = yt_base(single=True)
    if track["kind"] == "manual":
        cmd += ["--write-subs", "--no-write-auto-subs"]
    else:
        cmd += ["--write-auto-subs", "--no-write-subs"]
    cmd += [
        "--sub-langs", f"^{code}$",
        "--sub-format", "vtt/srt/best",
        "-o", str(output_template),
        url,
    ]
    return cmd


def _json_command(source, *, flat=False, comments=False, comment_sort="top", max_comments="200", playlist_end=None):
    cmd = yt_base(single=not flat)
    if flat:
        cmd += ["--flat-playlist"]
        if playlist_end:
            cmd += ["--playlist-end", str(playlist_end)]
    if comments:
        limit = "all" if str(max_comments).lower() == "all" else str(int(max_comments))
        # comment_sort first asks YouTube for the requested ordering. We still
        # slice locally when a finite cap is requested because yt-dlp/YouTube can
        # return slightly more than the requested max in some cases.
        cmd += [
            "--write-comments",
            "--extractor-args", f"youtube:skip=translated_subs;comment_sort={comment_sort};max_comments={limit},all,all,all",
        ]
    cmd += ["--dump-single-json", source]
    return cmd


def load_json(command):
    completed = run(command, check=False)
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError(completed.stderr[-4000:] or "yt-dlp returned no JSON")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"yt-dlp returned invalid JSON: {exc}") from exc


def channel_tab_url(url, tab):
    parts = urlsplit(str(url))
    if not is_youtube_url(url) or (parts.hostname or "").lower().rstrip(".") == "youtu.be":
        raise ValueError("YouTube channel URL required")
    path = re.sub(r"/(videos|shorts|streams|playlists|featured|community)/?$", "", parts.path.rstrip("/"), flags=re.I)
    if not path or path in {"/watch", "/playlist", "/results"}:
        raise ValueError("YouTube channel URL required")
    return urlunsplit((parts.scheme or "https", parts.netloc, f"{path}/{tab}", "", ""))


def video_url(entry):
    candidate = entry.get("webpage_url") or entry.get("url")
    if isinstance(candidate, str) and candidate.startswith(("http://", "https://")) and is_youtube_url(candidate):
        return candidate
    video_id = str(entry.get("id") or "").strip()
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


def discover_source(req):
    yt = req.get("youtube", {})
    scope = yt.get("scope", "video")
    if scope == "search":
        limit = int(yt.get("candidate_limit", 100))
        return [f"ytsearch{limit}:{yt['query']}"]
    if scope in {"video", "short"}:
        return [req["url"]]
    if scope == "playlist":
        return [req["url"]]
    if scope == "channel_videos":
        return [channel_tab_url(req["url"], "videos")]
    if scope == "channel_shorts":
        return [channel_tab_url(req["url"], "shorts")]
    if scope == "channel_all":
        return [channel_tab_url(req["url"], "videos"), channel_tab_url(req["url"], "shorts")]
    raise ValueError(f"unsupported YouTube scope: {scope}")


def discover_candidates(req):
    yt = req.get("youtube", {})
    scope = yt.get("scope", "video")
    max_items = int(yt.get("max_items", 20))
    # Do not pre-limit when local ranking or year filtering needs a wider pool.
    playlist_end = None
    if scope not in {"search"} and max_items > 0 and yt.get("sort_by", "relevance") == "relevance" and not yt.get("year_from") and not yt.get("year_to"):
        playlist_end = max_items

    entries = []
    seen = set()
    for source in discover_source(req):
        if scope in {"video", "short"}:
            raw_entries = [{"url": source}]
        else:
            data = load_json(_json_command(source, flat=True, playlist_end=playlist_end))
            raw_entries = data.get("entries") or []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            url = video_url(entry)
            key = entry.get("id") or url
            if not url or key in seen:
                continue
            seen.add(key)
            entries.append({"url": url, "id": entry.get("id"), "title": entry.get("title")})
    return entries


def metadata_for(url):
    return load_json(_json_command(url))


def selected_metadata(meta):
    keys = (
        "id", "title", "description", "webpage_url", "original_url", "channel", "channel_id", "channel_url",
        "uploader", "uploader_id", "upload_date", "timestamp", "release_date", "duration", "view_count",
        "like_count", "comment_count", "availability", "live_status", "was_live", "age_limit", "tags",
        "categories", "chapters", "language",
    )
    return {key: meta.get(key) for key in keys if meta.get(key) is not None}


def year_matches(meta, yt):
    upload_date = str(meta.get("upload_date") or "")
    if len(upload_date) < 4 or not upload_date[:4].isdigit():
        return not (yt.get("year_from") or yt.get("year_to"))
    year = int(upload_date[:4])
    if yt.get("year_from") and year < int(yt["year_from"]):
        return False
    if yt.get("year_to") and year > int(yt["year_to"]):
        return False
    return True


def thresholds_match(meta, yt):
    for field, key in (("view_count", "min_views"), ("like_count", "min_likes"), ("comment_count", "min_comments")):
        threshold = yt.get(key)
        if threshold is not None and int(meta.get(field) or 0) < int(threshold):
            return False
    return True


def rank_metadata(items, sort_by):
    sort_by = sort_by or "relevance"
    if sort_by == "relevance":
        return items
    field = {
        "views": "view_count",
        "likes": "like_count",
        "comments": "comment_count",
        "newest": "upload_date",
    }[sort_by]
    return sorted(items, key=lambda item: (item["meta"].get(field) is not None, item["meta"].get(field) or 0), reverse=True)


def download_caption(url, meta, preferred_language="auto"):
    track = choose_caption_track(meta, preferred_language)
    if not track:
        return None, None
    with tempfile.TemporaryDirectory(prefix="webactueel-youtube-sub-") as tmpdir:
        tmp = Path(tmpdir)
        output = tmp / "source.%(ext)s"
        completed = run(subtitle_command(url, track, output), check=False)
        files = sorted([*tmp.glob("source*.vtt"), *tmp.glob("source*.srt")])
        for subtitle_file in files:
            text = normalize_subtitles(subtitle_file)
            if text:
                info = {
                    **track,
                    "format": subtitle_file.suffix.lstrip("."),
                    "command_exit": completed.returncode,
                    "sha256": sha256_text(text + "\n"),
                }
                return text, info
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-4000:] or "subtitle download failed")
    return None, track


def normalized_comments(raw_comments, max_comments):
    out = []
    for comment in raw_comments or []:
        if not isinstance(comment, dict):
            continue
        item = {
            key: comment.get(key)
            for key in (
                "id", "parent", "text", "author", "author_id", "author_is_uploader", "timestamp",
                "like_count", "is_favorited", "is_pinned",
            )
            if comment.get(key) is not None
        }
        if item.get("text"):
            out.append(item)
    if str(max_comments).lower() != "all":
        out = out[: int(max_comments)]
    return out


def comments_for(url, req):
    yt = req.get("youtube", {})
    data = load_json(_json_command(
        url,
        comments=True,
        comment_sort=yt.get("comment_sort", "top"),
        max_comments=yt.get("max_comments", 200),
    ))
    return normalized_comments(data.get("comments"), yt.get("max_comments", 200))


def collect_single_transcript(req, media_meta=None):
    meta = metadata_for(req["url"])
    text, caption = download_caption(req["url"], meta, req.get("language", "auto"))
    if not text:
        raise RuntimeError("no usable public YouTube captions found; media download and Whisper fallback are forbidden")
    return text, "subtitle", {
        "media": media_meta or selected_metadata(meta),
        "caption": caption,
        "language_priority": ["en", "nl", "other"],
        "media_downloaded": False,
    }, ["yt-dlp:public-youtube-metadata", "yt-dlp:single-selected-caption", "normalize:subtitle-lines"]


def _safe_item_id(meta, fallback):
    value = str(meta.get("id") or fallback or "unknown")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:100]


def collect(req, results_dir):
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    yt = req.get("youtube", {})
    candidates = discover_candidates(req)
    hydrated = []
    discovery_errors = []
    for index, candidate in enumerate(candidates):
        try:
            meta = metadata_for(candidate["url"])
        except Exception as exc:
            discovery_errors.append({"url": candidate["url"], "error": str(exc)[:1000]})
            continue
        if not year_matches(meta, yt) or not thresholds_match(meta, yt):
            continue
        hydrated.append({"order": index, "url": candidate["url"], "meta": meta})

    hydrated = rank_metadata(hydrated, yt.get("sort_by", "relevance"))
    max_items = int(yt.get("max_items", 20))
    if max_items > 0:
        hydrated = hydrated[:max_items]

    persist_content = bool(req.get("analysis_content_allowed") or req.get("reuse_allowed"))
    item_records = []
    aggregate = ["# YouTube collection", ""]
    for entry in hydrated:
        meta = entry["meta"]
        item_id = _safe_item_id(meta, len(item_records) + 1)
        record = {
            "id": meta.get("id"),
            "url": meta.get("webpage_url") or entry["url"],
            "metadata": selected_metadata(meta),
            "status": "ok",
            "caption": None,
            "transcript_sha256": None,
            "transcript_chars": 0,
            "comments_extracted": 0,
        }
        try:
            transcript, caption = download_caption(entry["url"], meta, req.get("language", "auto"))
            record["caption"] = caption
            if transcript:
                normalized = transcript.strip() + "\n"
                record["transcript_sha256"] = sha256_text(normalized)
                record["transcript_chars"] = len(normalized)
                aggregate += [f"## {meta.get('title') or item_id}", "", f"Source: {record['url']}", f"Caption: {caption['language']} ({caption['kind']})", "", normalized.rstrip(), ""]
                if persist_content:
                    item_dir = results_dir / "items" / item_id
                    item_dir.mkdir(parents=True, exist_ok=True)
                    (item_dir / "transcript.md").write_text(normalized, encoding="utf-8")
            else:
                record["status"] = "no_captions"
        except Exception as exc:
            record["status"] = "caption_error"
            record["caption_error"] = str(exc)[:2000]

        comments = None
        if yt.get("include_comments"):
            try:
                comments = comments_for(entry["url"], req)
                record["comments_extracted"] = len(comments)
            except Exception as exc:
                record["comment_error"] = str(exc)[:2000]

        item_dir = results_dir / "items" / item_id
        item_dir.mkdir(parents=True, exist_ok=True)
        (item_dir / "metadata.json").write_text(json.dumps(record["metadata"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if comments is not None and persist_content:
            (item_dir / "comments.json").write_text(json.dumps(comments, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        item_records.append(record)

    aggregate_text = "\n".join(aggregate).strip() + "\n"
    if persist_content:
        (results_dir / "content.md").write_text(aggregate_text, encoding="utf-8")

    index = {
        "schema_version": "webactueel-youtube-collection/1.0",
        "scope": yt.get("scope", "video"),
        "query": yt.get("query"),
        "language_priority": ["en", "nl", "other"],
        "candidate_count": len(candidates),
        "eligible_count": len(hydrated),
        "item_count": len(item_records),
        "sort_by": yt.get("sort_by", "relevance"),
        "year_from": yt.get("year_from"),
        "year_to": yt.get("year_to"),
        "include_comments": bool(yt.get("include_comments")),
        "ranking_scope_note": "Search ranking is relative to the fetched candidate set, not a claim about all of YouTube." if yt.get("scope") == "search" else None,
        "discovery_errors": discovery_errors,
        "items": item_records,
    }
    (results_dir / "youtube-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return aggregate_text, index
