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


def normalize_collection_url(url):
    parts = urlsplit(str(url))
    query = parse_qs(parts.query)
    if query.get("list"):
        return str(url)
    stripped = str(url).split("?", 1)[0].rstrip("/")
    if stripped.endswith(("/videos", "/streams", "/shorts", "/featured")):
        return stripped
    return stripped + "/videos"


def discover_youtube_videos(url, maximum):
    collection_url = normalize_collection_url(url)
    command = [
        str(runtime.BIN / "yt-dlp"),
        "--no-config", "--no-cookies", "--no-netrc", "--no-warnings",
        "--skip-download", "--flat-playlist", "--playlist-end", str(maximum), "--dump-json",
        collection_url,
    ]
    completed = runtime.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError("yt-dlp could not enumerate the YouTube channel/playlist: " + completed.stderr[-3000:])
    videos = []
    seen = set()
    for raw_line in completed.stdout.splitlines():
        try:
            data = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        video_id = str(data.get("id") or "").strip()
        if not YOUTUBE_VIDEO_ID.fullmatch(video_id) or video_id in seen:
            continue
        seen.add(video_id)
        videos.append({
            "id": video_id,
            "title": str(data.get("title") or video_id),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
    if not videos:
        raise RuntimeError("No public videos found for the YouTube channel/playlist")
    return videos


def collection_content(req):
    maximum = int(req.get("max_items", 50))
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
                "status": "no_usable_captions",
                "detail": str(exc)[-1000:],
            })
            continue
        normalized = text.strip() + "\n"
        sections.append(f"# {video['title']}\n\n- Video: {video['url']}\n- Video-ID: `{video['id']}`\n\n{normalized}")
        items.append({
            "index": index,
            "video_id": video["id"],
            "title": video["title"],
            "url": video["url"],
            "status": "captions_collected",
            "caption_source": source_type,
            "content_sha256": runtime.sha256_text(normalized),
            "content_chars": len(normalized),
            "metadata": metadata,
            "transformations": transformations,
        })
    if not sections:
        raise RuntimeError("No usable public captions found in the selected YouTube channel/playlist range")
    content = "\n\n---\n\n".join(sections).strip() + "\n"
    metadata = {
        "collection_url": normalize_collection_url(req["url"]),
        "requested_items": maximum,
        "discovered_items": len(videos),
        "captions_collected": sum(1 for item in items if item["status"] == "captions_collected"),
        "captions_unavailable": sum(1 for item in items if item["status"] != "captions_collected"),
        "items": items,
    }
    return content, metadata


def write_collection_result(req):
    runtime.validate_public_url(req["url"])
    RESULTS.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    content, metadata = collection_content(req)
    normalized = content.strip() + "\n"
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
        "content_persisted": bool(req.get("reuse_allowed")),
        "metadata": metadata,
        "transformations": ["yt-dlp:collection-discovery", "yt-dlp:public-subtitles", "normalize:subtitle-lines"],
        "tool_versions": runtime.tool_versions(),
        "source_context": req.get("source_context"),
        "limitations": [
            "Only public captions are collected; videos without usable captions are recorded as unavailable.",
            "The result is review material and is not automatically promoted to project truth or a Skill.",
            "Public YouTube audio/video download and Whisper fallback remain disabled.",
            "The runtime does not bypass login, cookies, DRM, paywalls, CAPTCHA, age controls, or private access.",
        ],
    }
    handoff = {
        "schema_version": "webactueel-knowledge-handoff/1.0",
        "request_id": req["request_id"],
        "owner": "webactueel-workflow",
        "project_id": "project-transcriberen",
        "source_url": req["url"],
        "source_kind": "youtube_collection",
        "promotion_status": "review_required",
        "reuse_allowed": bool(req.get("reuse_allowed")),
        "rights_basis": req.get("rights_basis"),
        "content_available": bool(req.get("reuse_allowed")),
        "content_path": "content.md" if req.get("reuse_allowed") else None,
        "source_items": metadata["items"],
        "next_action": "Review, deduplicate, paraphrase, and route accepted insights to exactly one canonical project source or Skill owner before any write.",
    }
    if req.get("reuse_allowed"):
        (RESULTS / "content.md").write_text(normalized, encoding="utf-8")
    (RESULTS / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "knowledge-handoff.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "tool-versions.txt").write_text("\n".join(f"{key}={value}" for key, value in result["tool_versions"].items()) + "\n", encoding="utf-8")
    print(json.dumps({"request_id": req["request_id"], "mode": "youtube_collection", "items": len(metadata["items"]), "captions_collected": metadata["captions_collected"]}))


def main():
    request_path = Path(os.environ.get("REQUEST_FILE", "resolved-request.json"))
    req = json.loads(request_path.read_text(encoding="utf-8"))
    if is_youtube_collection_url(req["url"]):
        write_collection_result(req)
    else:
        runtime.main()


if __name__ == "__main__":
    main()
