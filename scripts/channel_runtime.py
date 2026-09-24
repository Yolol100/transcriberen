#!/usr/bin/env python3
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import shutil
import threading
import zipfile
from pathlib import Path

import cache_runtime as cache
import captions_runtime as captions

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
VIDEOS = RESULTS / "videos"
VIDEO_CONCURRENCY = 7
ZIP_COMPRESSLEVEL = 3
POLICY = {
    "year": 2026,
    "max_videos": 1000,
    "comments_per_video": 7,
    "comment_sort": "top",
    "include_replies": False,
    "video_concurrency": VIDEO_CONCURRENCY,
}
COUNT_KEYS = (
    "discovered",
    "checked",
    "matched_2026",
    "metadata_failures",
    "captions_ok",
    "no_captions",
    "caption_failures",
    "comments_ok",
    "comments_unavailable",
    "cache_hits",
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def discover_channel(channel_url: str, max_videos: int) -> tuple[dict, list[str]]:
    command = [
        str(captions.BIN / "yt-dlp"),
        "--no-config",
        "--no-cookies",
        "--skip-download",
        "--flat-playlist",
        "--playlist-end",
        str(max_videos),
        "--extractor-args",
        "youtube:skip=translated_subs",
        "--dump-single-json",
        channel_url,
    ]
    completed = captions.run(command, timeout=300)
    diagnostic = completed.stderr[-2000:]
    if diagnostic and captions.classify_failure(diagnostic) == "access_blocked":
        raise RuntimeError(f"access_blocked::{diagnostic}")
    if completed.returncode != 0 or not completed.stdout.strip():
        detail = diagnostic or "yt-dlp returned no channel listing"
        raise RuntimeError(f"{captions.classify_failure(detail)}::{detail}")
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"error::yt-dlp returned invalid channel JSON: {exc}") from exc
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
    channel = {
        "id": data.get("channel_id") or data.get("uploader_id") or data.get("id"),
        "title": data.get("channel") or data.get("uploader") or data.get("title"),
        "url": channel_url,
    }
    return channel, ids


def clean_results() -> None:
    if RESULTS.exists():
        shutil.rmtree(RESULTS)
    VIDEOS.mkdir(parents=True, exist_ok=True)


def empty_counts(discovered: int = 0) -> dict[str, int]:
    counts = {key: 0 for key in COUNT_KEYS}
    counts["discovered"] = discovered
    return counts


def failure_parts(exc: Exception) -> tuple[str, str]:
    raw = str(exc)
    status, separator, detail = raw.partition("::")
    if not separator or status not in {"access_blocked", "error"}:
        return "error", raw
    return status, detail


def build_zip() -> None:
    target = RESULTS / "channel-corpus.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=ZIP_COMPRESSLEVEL) as zf:
        for path in sorted(RESULTS.rglob("*")):
            if not path.is_file() or path == target or path.name == "SHA256SUMS.txt":
                continue
            rel = path.relative_to(RESULTS).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, path.read_bytes())


def write_failed_discovery(request: dict, provenance: dict, progress: dict, exc: Exception) -> None:
    status, detail = failure_parts(exc)
    counts = empty_counts()
    result = {
        "schema_version": "3.0",
        "request_id": request["request_id"],
        "status": status,
        "source": {"type": "channel", "url": request["url"]},
        "policy": POLICY,
        "counts": counts,
        "runtime_provenance": provenance,
        "media_downloaded": False,
        "error": detail[-2000:],
    }
    manifest = {
        "schema_version": "1.1",
        "request_id": request["request_id"],
        "channel": {"id": None, "title": None, "url": request["url"]},
        "policy": POLICY,
        "counts": counts,
        "partial_reasons": [],
        "unresolved": [],
        "items": [],
    }
    write_json(RESULTS / "result.json", result)
    write_json(RESULTS / "manifest.json", manifest)
    write_json(RESULTS / "processed-index.json", {
        "schema_version": "2.0",
        "scope": "current_run",
        "generated_at": cache.utc_now(),
        "requested_entries": 0,
        "unique_videos": 0,
        "processed_entries": 0,
        "captions_done": 0,
        "status_counts": {},
        "items": [],
    })
    progress.update({"state": "failed"})
    write_json(RESULTS / "progress.json", progress)
    build_zip()
    print(json.dumps({"request_id": request["request_id"], "status": status}))



def process_video(video_id: str, request: dict, access_blocked_event: threading.Event) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    if access_blocked_event.is_set():
        return {
            "kind": "unresolved",
            "unresolved": {
                "video_id": video_id,
                "url": url,
                "status": "access_blocked",
                "reason": "deferred_after_access_block",
                "error": "network acquisition skipped after access-block evidence in the same run",
            },
            "access_blocked": True,
        }

    try:
        meta = captions.load_metadata(url)
    except Exception as exc:
        status, detail = failure_parts(exc)
        if status == "access_blocked":
            access_blocked_event.set()
        return {
            "kind": "unresolved",
            "unresolved": {
                "video_id": video_id,
                "url": url,
                "status": status,
                "reason": "metadata_acquisition_failed",
                "error": detail[-2000:],
            },
            "access_blocked": status == "access_blocked",
        }

    upload_date = str(meta.get("upload_date") or "")
    if not upload_date:
        return {
            "kind": "unresolved",
            "unresolved": {
                "video_id": video_id,
                "url": url,
                "status": "error",
                "reason": "missing_upload_date",
                "error": "video metadata did not contain upload_date; 2026 membership cannot be proven",
            },
            "access_blocked": False,
        }
    if not upload_date.startswith("2026"):
        return {"kind": "ignored", "video_id": video_id, "access_blocked": False}

    title = str(meta.get("title") or video_id)
    video_dir = VIDEOS / video_id
    video_dir.mkdir(parents=True, exist_ok=True)
    transcript_status = "skipped_no_captions"
    caption_meta = None
    transcript_sha = None
    cache_hit = False

    with cache.connect() as conn:
        cached = cache.get_cached_transcript(conn, video_id, request["language"])
        if cached:
            transcript = cached["text"]
            caption_meta = cached["caption"]
            transcript_sha = cached["sha256"]
            transcript_status = "ok"
            cache_hit = True
            (video_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
        else:
            track = captions.choose_caption_track(meta, request["language"])
            if track:
                try:
                    transcript, caption_meta = captions.download_caption(url, track)
                    transcript_sha = captions.sha256_text(transcript)
                    transcript_status = "ok"
                    (video_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
                    cache.store_result(
                        conn,
                        video_id=video_id,
                        language=request["language"],
                        url=url,
                        status="ok",
                        caption=caption_meta,
                        transcript=transcript,
                        upload_date=upload_date,
                        title=title,
                    )
                except Exception as exc:
                    transcript_status, _ = failure_parts(exc)
                    if transcript_status == "access_blocked":
                        access_blocked_event.set()
                    cache.store_result(
                        conn,
                        video_id=video_id,
                        language=request["language"],
                        url=url,
                        status=transcript_status,
                        caption=None,
                        transcript=None,
                        upload_date=upload_date,
                        title=title,
                    )
            else:
                cache.store_result(
                    conn,
                    video_id=video_id,
                    language=request["language"],
                    url=url,
                    status="skipped_no_captions",
                    caption=None,
                    transcript=None,
                    upload_date=upload_date,
                    title=title,
                )

    if access_blocked_event.is_set():
        comments, comments_status = [], "unavailable"
    else:
        try:
            comments, comments_status = captions.load_top_comments(
                url,
                int(request["comments_per_video"]),
            )
        except Exception as exc:
            comments = []
            comments_status, _ = failure_parts(exc)
        if comments_status == "access_blocked":
            access_blocked_event.set()

    write_json(video_dir / "comments.json", {
        "status": comments_status,
        "sort": "top",
        "include_replies": False,
        "count": len(comments),
        "comments": comments,
    })
    metadata = {
        "video_id": video_id,
        "url": url,
        "title": title,
        "upload_date": upload_date,
        "transcript_status": transcript_status,
        "caption": caption_meta,
        "transcript_sha256": transcript_sha,
        "cache_hit": cache_hit,
        "comments_status": comments_status,
        "comments_count": len(comments),
    }
    write_json(video_dir / "metadata.json", metadata)
    return {
        "kind": "matched",
        "metadata": metadata,
        "index_entry": (video_id, request["language"]),
        "access_blocked": (
            transcript_status == "access_blocked"
            or comments_status == "access_blocked"
        ),
    }

def main() -> None:
    request_file = Path(os.environ.get("REQUEST_FILE", "resolved-request.json"))
    request = json.loads(request_file.read_text(encoding="utf-8"))
    clean_results()
    provenance = captions.runtime_provenance()
    progress = {
        "schema_version": "1.1",
        "request_id": request["request_id"],
        "state": "running",
        "discovered": 0,
        "checked": 0,
        "matched_2026": 0,
        "completed": 0,
        "unresolved": 0,
    }
    write_json(RESULTS / "progress.json", progress)
    try:
        channel, video_ids = discover_channel(request["url"], int(request["max_videos"]))
    except Exception as exc:
        write_failed_discovery(request, provenance, progress, exc)
        return

    progress["discovered"] = len(video_ids)
    write_json(RESULTS / "progress.json", progress)
    items = []
    unresolved = []
    index_entries: list[tuple[str, str]] = []
    counts = empty_counts(len(video_ids))
    order = {video_id: index for index, video_id in enumerate(video_ids)}
    access_blocked_event = threading.Event()

    # Initialize the WAL-backed cache schema before worker threads open their own connections.
    with cache.connect():
        pass

    with ThreadPoolExecutor(
        max_workers=VIDEO_CONCURRENCY,
        thread_name_prefix="youtube-video",
    ) as executor:
        for start in range(0, len(video_ids), VIDEO_CONCURRENCY):
            batch = video_ids[start:start + VIDEO_CONCURRENCY]
            futures = [
                executor.submit(process_video, video_id, request, access_blocked_event)
                for video_id in batch
            ]
            for video_id, future in zip(batch, futures):
                counts["checked"] += 1
                try:
                    outcome = future.result()
                except Exception as exc:
                    shutil.rmtree(VIDEOS / video_id, ignore_errors=True)
                    status, detail = failure_parts(exc)
                    if status == "access_blocked":
                        access_blocked_event.set()
                    outcome = {
                        "kind": "unresolved",
                        "unresolved": {
                            "video_id": video_id,
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "status": status,
                            "reason": "video_worker_failed",
                            "error": detail[-2000:],
                        },
                        "access_blocked": status == "access_blocked",
                    }

                if outcome["kind"] == "unresolved":
                    counts["metadata_failures"] += 1
                    unresolved.append(outcome["unresolved"])
                elif outcome["kind"] == "matched":
                    metadata = outcome["metadata"]
                    items.append(metadata)
                    index_entries.append(outcome["index_entry"])
                    counts["matched_2026"] += 1
                    if metadata["transcript_status"] == "ok":
                        counts["captions_ok"] += 1
                    elif metadata["transcript_status"] == "skipped_no_captions":
                        counts["no_captions"] += 1
                    else:
                        counts["caption_failures"] += 1
                    if metadata["comments_status"] == "ok":
                        counts["comments_ok"] += 1
                    else:
                        counts["comments_unavailable"] += 1
                    if metadata["cache_hit"]:
                        counts["cache_hits"] += 1

            progress.update({
                "checked": counts["checked"],
                "matched_2026": counts["matched_2026"],
                "completed": len(items),
                "unresolved": len(unresolved),
            })
            # One durable progress write per bounded batch avoids serial filesystem churn.
            write_json(RESULTS / "progress.json", progress)

    items.sort(key=lambda item: order[item["video_id"]])
    unresolved.sort(key=lambda item: order[item["video_id"]])

    with cache.connect() as conn:
        cache.export_index(
            conn,
            RESULTS / "processed-index.json",
            entries=index_entries,
        )

    partial_reasons = []
    if counts["metadata_failures"]:
        partial_reasons.append("metadata_failures")
    if counts["caption_failures"]:
        partial_reasons.append("caption_failures")
    if counts["comments_unavailable"]:
        partial_reasons.append("comments_unavailable")
    overall = "partial" if partial_reasons else "ok"
    manifest = {
        "schema_version": "1.1",
        "request_id": request["request_id"],
        "channel": channel,
        "policy": POLICY,
        "counts": counts,
        "partial_reasons": partial_reasons,
        "unresolved": unresolved,
        "items": items,
    }
    result = {
        "schema_version": "3.0",
        "request_id": request["request_id"],
        "status": overall,
        "source": {"type": "channel", **channel},
        "policy": manifest["policy"],
        "counts": counts,
        "partial_reasons": partial_reasons,
        "runtime_provenance": provenance,
        "media_downloaded": False,
    }
    write_json(RESULTS / "manifest.json", manifest)
    progress.update({
        "state": "complete",
        "completed": len(items),
        "unresolved": len(unresolved),
    })
    write_json(RESULTS / "progress.json", progress)
    write_json(RESULTS / "result.json", result)
    build_zip()
    print(json.dumps({
        "request_id": request["request_id"],
        "status": overall,
        "matched_2026": counts["matched_2026"],
        "captions_ok": counts["captions_ok"],
        "comments_ok": counts["comments_ok"],
        "unresolved": len(unresolved),
    }))


if __name__ == "__main__":
    main()
