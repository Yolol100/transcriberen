#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path

import cache_runtime as cache
import captions_runtime as captions

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
VIDEOS = RESULTS / "videos"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def discover_channel(channel_url: str, max_videos: int) -> tuple[dict, list[str]]:
    command = [str(captions.BIN / "yt-dlp"), "--no-config", "--no-cookies", "--skip-download", "--flat-playlist", "--playlist-end", str(max_videos), "--extractor-args", "youtube:skip=translated_subs", "--dump-single-json", channel_url]
    completed = captions.run(command, timeout=300)
    diagnostic = completed.stderr[-2000:]
    if diagnostic and captions.classify_failure(diagnostic) == "access_blocked":
        raise RuntimeError(f"access_blocked::{diagnostic}")
    if completed.returncode != 0 or not completed.stdout.strip():
        detail = diagnostic or "yt-dlp returned no channel listing"
        raise RuntimeError(f"{captions.classify_failure(detail)}::{detail}")
    data = json.loads(completed.stdout)
    if not isinstance(data, dict):
        raise RuntimeError("error::invalid channel metadata")
    ids = []
    for entry in data.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "")
        if len(video_id) == 11 and video_id not in ids:
            ids.append(video_id)
        if len(ids) >= max_videos:
            break
    channel = {"id": data.get("channel_id") or data.get("uploader_id") or data.get("id"), "title": data.get("channel") or data.get("uploader") or data.get("title"), "url": channel_url}
    return channel, ids


def clean_results() -> None:
    if RESULTS.exists():
        shutil.rmtree(RESULTS)
    VIDEOS.mkdir(parents=True, exist_ok=True)


def build_zip() -> None:
    target = RESULTS / "channel-corpus.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(RESULTS.rglob("*")):
            if not path.is_file() or path == target or path.name == "SHA256SUMS.txt":
                continue
            rel = path.relative_to(RESULTS).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, path.read_bytes())


def main() -> None:
    request_file = Path(os.environ.get("REQUEST_FILE", "resolved-request.json"))
    request = json.loads(request_file.read_text(encoding="utf-8"))
    clean_results()
    provenance = captions.runtime_provenance()
    progress = {"schema_version": "1.0", "request_id": request["request_id"], "state": "running", "discovered": 0, "checked": 0, "matched_2026": 0, "completed": 0}
    write_json(RESULTS / "progress.json", progress)
    try:
        channel, video_ids = discover_channel(request["url"], int(request["max_videos"]))
    except Exception as exc:
        raw = str(exc)
        status, _, detail = raw.partition("::")
        if status not in {"access_blocked", "error"}:
            status, detail = "error", raw
        result = {"schema_version": "3.0", "request_id": request["request_id"], "status": status, "source": {"type": "channel", "url": request["url"]}, "policy": {"year": 2026, "max_videos": 1000, "comments_per_video": 7, "comment_sort": "top", "include_replies": False}, "counts": {}, "runtime_provenance": provenance, "media_downloaded": False, "error": detail[-2000:]}
        write_json(RESULTS / "result.json", result)
        write_json(RESULTS / "manifest.json", {"schema_version": "1.0", "items": []})
        progress.update({"state": "failed"})
        write_json(RESULTS / "progress.json", progress)
        build_zip()
        print(json.dumps({"request_id": request["request_id"], "status": status}))
        return
    progress["discovered"] = len(video_ids)
    write_json(RESULTS / "progress.json", progress)
    items = []
    counts = {"discovered": len(video_ids), "checked": 0, "matched_2026": 0, "captions_ok": 0, "no_captions": 0, "caption_failures": 0, "comments_ok": 0, "comments_unavailable": 0, "cache_hits": 0}
    with cache.connect() as conn:
        for video_id in video_ids:
            counts["checked"] += 1
            progress["checked"] = counts["checked"]
            url = f"https://www.youtube.com/watch?v={video_id}"
            try:
                meta = captions.load_metadata(url)
            except Exception:
                write_json(RESULTS / "progress.json", progress)
                continue
            upload_date = str(meta.get("upload_date") or "")
            if not upload_date.startswith("2026"):
                write_json(RESULTS / "progress.json", progress)
                continue
            counts["matched_2026"] += 1
            progress["matched_2026"] = counts["matched_2026"]
            title = str(meta.get("title") or video_id)
            video_dir = VIDEOS / video_id
            video_dir.mkdir(parents=True, exist_ok=True)
            transcript_status = "skipped_no_captions"
            caption_meta = None
            transcript_sha = None
            cache_hit = False
            cached = cache.get_cached_transcript(conn, video_id, request["language"])
            if cached:
                transcript = cached["text"]
                caption_meta = cached["caption"]
                transcript_sha = cached["sha256"]
                transcript_status = "ok"
                cache_hit = True
                counts["cache_hits"] += 1
                (video_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
            else:
                track = captions.choose_caption_track(meta, request["language"])
                if track:
                    try:
                        transcript, caption_meta = captions.download_caption(url, track)
                        transcript_sha = captions.sha256_text(transcript)
                        transcript_status = "ok"
                        (video_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
                        cache.store_result(conn, video_id=video_id, language=request["language"], url=url, status="ok", caption=caption_meta, transcript=transcript, upload_date=upload_date, title=title)
                    except Exception as exc:
                        raw = str(exc)
                        transcript_status = raw.split("::", 1)[0] if "::" in raw else "error"
                        if transcript_status not in {"access_blocked", "error"}:
                            transcript_status = "error"
                        cache.store_result(conn, video_id=video_id, language=request["language"], url=url, status=transcript_status, caption=None, transcript=None, upload_date=upload_date, title=title)
                else:
                    cache.store_result(conn, video_id=video_id, language=request["language"], url=url, status="skipped_no_captions", caption=None, transcript=None, upload_date=upload_date, title=title)
            if transcript_status == "ok":
                counts["captions_ok"] += 1
            elif transcript_status == "skipped_no_captions":
                counts["no_captions"] += 1
            else:
                counts["caption_failures"] += 1
            comments, comments_status = captions.load_top_comments(url, int(request["comments_per_video"]))
            if comments_status == "ok":
                counts["comments_ok"] += 1
            else:
                counts["comments_unavailable"] += 1
            write_json(video_dir / "comments.json", {"status": comments_status, "sort": "top", "include_replies": False, "count": len(comments), "comments": comments})
            metadata = {"video_id": video_id, "url": url, "title": title, "upload_date": upload_date, "transcript_status": transcript_status, "caption": caption_meta, "transcript_sha256": transcript_sha, "cache_hit": cache_hit, "comments_status": comments_status, "comments_count": len(comments)}
            write_json(video_dir / "metadata.json", metadata)
            items.append(metadata)
            progress["completed"] = len(items)
            write_json(RESULTS / "progress.json", progress)
        cache.export_index(conn, RESULTS / "processed-index.json")
    overall = "partial" if counts["caption_failures"] else "ok"
    manifest = {"schema_version": "1.0", "request_id": request["request_id"], "channel": channel, "policy": {"year": 2026, "max_videos": 1000, "comments_per_video": 7, "comment_sort": "top", "include_replies": False}, "counts": counts, "items": items}
    result = {"schema_version": "3.0", "request_id": request["request_id"], "status": overall, "source": {"type": "channel", **channel}, "policy": manifest["policy"], "counts": counts, "runtime_provenance": provenance, "media_downloaded": False}
    write_json(RESULTS / "manifest.json", manifest)
    progress.update({"state": "complete", "completed": len(items)})
    write_json(RESULTS / "progress.json", progress)
    write_json(RESULTS / "result.json", result)
    build_zip()
    print(json.dumps({"request_id": request["request_id"], "status": overall, "matched_2026": counts["matched_2026"], "captions_ok": counts["captions_ok"]}))


if __name__ == "__main__":
    main()
