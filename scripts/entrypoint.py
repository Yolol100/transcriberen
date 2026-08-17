#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import runtime

RESULTS = runtime.RESULTS
YOUTUBE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHANNEL_TABS = {"videos", "shorts", "streams", "featured"}
MAX_COLLECTION_VIDEOS = 10_000


def is_youtube_collection_url(url):
    parts = urlsplit(str(url))
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return False
    query = parse_qs(parts.query)
    if query.get("list"):
        return True
    path = parts.path.rstrip("/")
    if path.startswith("/@") or path.startswith("/channel/") or path.startswith("/c/") or path.startswith("/user/"):
        return True
    return False


def collection_targets(url):
    parts = urlsplit(str(url))
    query = parse_qs(parts.query)
    if query.get("list"):
        return [str(url)]
    stripped = str(url).split("?", 1)[0].rstrip("/")
    last = stripped.rsplit("/", 1)[-1]
    if last in CHANNEL_TABS:
        return [stripped]
    return [stripped + "/videos", stripped + "/shorts", stripped + "/streams"]


def normalize_collection_url(url):
    return collection_targets(url)[0]


def discover_youtube_videos(url, maximum):
    maximum = int(maximum or 0)
    hard_limit = maximum if maximum > 0 else MAX_COLLECTION_VIDEOS
    videos = []
    seen = set()
    errors = []
    truncated = False

    for target in collection_targets(url):
        if len(videos) >= hard_limit:
            truncated = True
            break
        command = [
            str(runtime.BIN / "yt-dlp"),
            "--no-config", "--no-cookies", "--no-warnings",
            "--skip-download", "--flat-playlist", "--dump-json",
            "--playlist-end", str(hard_limit + 1), target,
        ]
        completed = runtime.run(command, check=False)
        if completed.returncode != 0:
            errors.append(f"{target}: {completed.stderr[-1200:].strip() or 'yt-dlp discovery failed'}")
            continue
        for raw_line in completed.stdout.splitlines():
            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            video_id = str(data.get("id") or "").strip()
            if not YOUTUBE_VIDEO_ID.fullmatch(video_id) or video_id in seen:
                continue
            if len(videos) >= hard_limit:
                truncated = True
                break
            seen.add(video_id)
            videos.append({
                "id": video_id,
                "title": str(data.get("title") or video_id),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "source_target": target,
            })
        if truncated:
            break

    if not videos:
        detail = "; ".join(errors) or "no public videos found"
        raise RuntimeError("yt-dlp could not enumerate the YouTube channel/playlist: " + detail)
    if maximum == 0 and truncated:
        raise RuntimeError(
            f"YouTube collection exceeds safety cap of {MAX_COLLECTION_VIDEOS} videos; "
            "set max_items to process a bounded batch"
        )
    return videos


def classify_caption_failure(exc):
    if isinstance(exc, runtime.CaptionUnavailableError):
        return "no_usable_captions"
    if isinstance(exc, runtime.CaptionAccessError):
        return "caption_access_error"
    return "processing_error"


def summarize_items(items):
    counts = {
        "captions_collected": sum(1 for item in items if item["status"] == "captions_collected"),
        "captions_unavailable": sum(1 for item in items if item["status"] == "no_usable_captions"),
        "caption_access_errors": sum(1 for item in items if item["status"] == "caption_access_error"),
        "processing_errors": sum(1 for item in items if item["status"] == "processing_error"),
    }
    if counts["captions_collected"]:
        scan_status = "partial" if counts["caption_access_errors"] or counts["processing_errors"] else "captions_collected"
    elif counts["caption_access_errors"]:
        scan_status = "source_access_blocked"
    elif counts["processing_errors"]:
        scan_status = "processing_error"
    else:
        scan_status = "no_usable_captions"
    return counts, scan_status


def collection_content(req):
    maximum = int(req.get("max_items", 0))
    videos = discover_youtube_videos(req["url"], maximum)
    sections = []
    items = []
    for index, video in enumerate(videos, start=1):
        item_req = dict(req)
        item_req["url"] = video["url"]
        media_meta = {
            "title": video["title"],
            "extractor": "Youtube",
            "webpage_url": video["url"],
            "id": video["id"],
        }
        try:
            text, source_type, metadata, transformations = runtime.media_content(item_req, media_meta)
        except Exception as exc:
            items.append({
                "index": index,
                "video_id": video["id"],
                "title": video["title"],
                "url": video["url"],
                "source_target": video["source_target"],
                "status": classify_caption_failure(exc),
                "detail": str(exc)[-1000:],
            })
            continue
        normalized = text.strip() + "\n"
        sections.append(
            f"# {video['title']}\n\n"
            f"- Video: {video['url']}\n"
            f"- Video-ID: `{video['id']}`\n\n{normalized}"
        )
        items.append({
            "index": index,
            "video_id": video["id"],
            "title": video["title"],
            "url": video["url"],
            "source_target": video["source_target"],
            "status": "captions_collected",
            "caption_source": source_type,
            "content_sha256": runtime.sha256_text(normalized),
            "content_chars": len(normalized),
            "metadata": metadata,
            "transformations": transformations,
        })
    content = "\n\n---\n\n".join(sections).strip() + "\n" if sections else ""
    counts, scan_status = summarize_items(items)
    metadata = {
        "collection_targets": collection_targets(req["url"]),
        "requested_items": "all" if maximum == 0 else maximum,
        "discovered_items": len(videos),
        **counts,
        "scan_status": scan_status,
        "items": items,
    }
    return content, metadata


def promotion_status(req, metadata):
    if not req.get("reuse_allowed"):
        return "rights_review_required"
    if metadata["captions_collected"] > 0:
        return "review_required"
    if metadata["caption_access_errors"] or metadata["processing_errors"]:
        return "source_access_blocked"
    return "no_content"


def write_collection_result(req):
    runtime.validate_public_url(req["url"])
    RESULTS.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    content, metadata = collection_content(req)
    normalized = content.strip() + "\n" if content.strip() else ""
    content_available = metadata["captions_collected"] > 0
    content_persisted = bool(req.get("reuse_allowed")) and content_available
    transformations = ["yt-dlp:collection-discovery"]
    if content_available:
        transformations.extend(["yt-dlp:public-subtitles", "normalize:subtitle-lines"])
    result = {
        "schema_version": "webactueel-transcription-result/1.0",
        "request_id": req["request_id"],
        "owner": "webactueel-workflow",
        "project_id": "project-transcriberen",
        "source_url": req["url"],
        "requested_mode": req["mode"],
        "detected_mode": "youtube_collection",
        "language": req.get("language", "auto"),
        "fetched_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "controlled_runtime",
        "reuse_allowed": bool(req.get("reuse_allowed")),
        "rights_basis": req.get("rights_basis"),
        "audio_access_authorized": False,
        "content_sha256": runtime.sha256_text(normalized),
        "content_chars": len(normalized),
        "content_persisted": content_persisted,
        "metadata": metadata,
        "transformations": transformations,
        "tool_versions": runtime.tool_versions(),
        "source_context": req.get("source_context"),
        "limitations": [
            "Only public captions are collected; videos that expose no usable captions are recorded separately from access/tool failures.",
            "Channel roots are scanned across public videos, Shorts and stream archives and deduplicated by video ID.",
            "The result is review material and is not automatically promoted to project truth or a Skill.",
            "Public YouTube audio/video download and Whisper fallback remain disabled.",
            "The runtime does not bypass login, cookies, DRM, paywalls, CAPTCHA, age controls, or private access.",
        ],
    }
    source_register = {
        "schema_version": "webactueel-source-register/1.0",
        "request_id": req["request_id"],
        "source_url": req["url"],
        "fetched_at": started,
        "sources": metadata["items"],
    }
    handoff = {
        "schema_version": "webactueel-knowledge-handoff/1.0",
        "request_id": req["request_id"],
        "owner": "webactueel-workflow",
        "project_id": "project-transcriberen",
        "source_url": req["url"],
        "source_kind": "youtube_collection",
        "promotion_status": promotion_status(req, metadata),
        "reuse_allowed": bool(req.get("reuse_allowed")),
        "rights_basis": req.get("rights_basis"),
        "content_available": content_available,
        "content_path": "content.md" if content_persisted else None,
        "source_register_path": "source-register.json",
        "source_items": metadata["items"],
        "next_action": (
            "Review, deduplicate and paraphrase accepted insights; route every accepted insight to exactly one "
            "canonical project source or Skill owner, then apply the write only through Webactueel-workflow with "
            "fresh readback/hash, backup, validation and rollback."
        ),
    }
    content_path = RESULTS / "content.md"
    if content_persisted:
        content_path.write_text(normalized, encoding="utf-8")
    elif content_path.exists():
        content_path.unlink()
    (RESULTS / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "source-register.json").write_text(json.dumps(source_register, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "knowledge-handoff.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "tool-versions.txt").write_text("\n".join(f"{key}={value}" for key, value in result["tool_versions"].items()) + "\n", encoding="utf-8")
    print(json.dumps({
        "request_id": req["request_id"],
        "mode": "youtube_collection",
        "items": len(metadata["items"]),
        "captions_collected": metadata["captions_collected"],
        "scan_status": metadata["scan_status"],
    }))


def main():
    request_path = Path(os.environ.get("REQUEST_FILE", "resolved-request.json"))
    req = json.loads(request_path.read_text(encoding="utf-8"))
    if is_youtube_collection_url(req["url"]):
        write_collection_result(req)
    else:
        runtime.main()


if __name__ == "__main__":
    main()
