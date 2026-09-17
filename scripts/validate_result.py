#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
MEDIA_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
FIXED_POLICY = {"year": 2026, "max_videos": 1000, "comments_per_video": 7, "comment_sort": "top", "include_replies": False}
COUNT_KEYS = {
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
}


def expected_tool_versions() -> dict[str, str]:
    contract = json.loads((ROOT / "toolkit-contract.json").read_text(encoding="utf-8"))
    return {str(tool["id"]): str(tool["version"]) for tool in contract.get("tools", [])}


def require_nonnegative_counts(counts: dict) -> None:
    if not COUNT_KEYS.issubset(counts):
        missing = sorted(COUNT_KEYS.difference(counts))
        raise ValueError("missing count fields: " + ", ".join(missing))
    for key in COUNT_KEYS:
        value = counts.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"count {key} must be a non-negative integer")


def validate(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    status = data.get("status")
    if data.get("schema_version") != "3.0":
        raise ValueError("result schema_version must be 3.0")
    if status not in {"ok", "partial", "access_blocked", "error"}:
        raise ValueError("invalid result status")
    source = data.get("source") or {}
    if source.get("type") != "channel" or not str(source.get("url") or "").endswith("/videos"):
        raise ValueError("source must be a normalized YouTube channel /videos URL")
    if data.get("policy") != FIXED_POLICY:
        raise ValueError("fixed channel policy mismatch")
    if data.get("media_downloaded") is not False:
        raise ValueError("media_downloaded must be false")
    if any(key in data for key in ("project_id", "source_set_version", "owner_skill")):
        raise ValueError("project truth must not be embedded in runtime results")
    if status in {"access_blocked", "error"} and not str(data.get("error") or "").strip():
        raise ValueError("failed channel result requires error detail")

    provenance = data.get("runtime_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("runtime_provenance is required")
    target = str(provenance.get("execution_target") or "")
    if target not in {"github-hosted", "self-hosted", "local", "test"}:
        raise ValueError("invalid runtime_provenance.execution_target")
    if target != "test":
        versions = expected_tool_versions()
        if provenance.get("yt_dlp_version") != versions.get("yt-dlp"):
            raise ValueError("runtime yt-dlp version does not match capability contract")
        if provenance.get("deno_version") != versions.get("deno-ejs-runtime"):
            raise ValueError("runtime Deno version does not match capability contract")

    manifest_path = RESULTS / "manifest.json"
    progress_path = RESULTS / "progress.json"
    index_path = RESULTS / "processed-index.json"
    for required in (manifest_path, progress_path, index_path):
        if not required.is_file():
            raise ValueError(f"missing required output: {required.name}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.1":
        raise ValueError("manifest schema_version must be 1.1")
    if manifest.get("policy") != FIXED_POLICY:
        raise ValueError("manifest policy mismatch")
    items = manifest.get("items") or []
    unresolved = manifest.get("unresolved") or []
    partial_reasons = manifest.get("partial_reasons") or []
    if not isinstance(items, list) or len(items) > 1000:
        raise ValueError("manifest items must contain at most 1000 videos")
    if not isinstance(unresolved, list):
        raise ValueError("manifest unresolved must be a list")
    if not isinstance(partial_reasons, list):
        raise ValueError("manifest partial_reasons must be a list")
    counts = manifest.get("counts") or {}
    require_nonnegative_counts(counts)
    if data.get("counts") != counts:
        raise ValueError("result counts must equal manifest counts")
    if int(counts["discovered"]) > 1000:
        raise ValueError("discovered count exceeds 1000")
    if counts["checked"] != counts["discovered"]:
        raise ValueError("completed run must check every discovered video")
    if counts["matched_2026"] != len(items):
        raise ValueError("matched_2026 must equal manifest item count")
    if counts["metadata_failures"] != len(unresolved):
        raise ValueError("metadata_failures must equal unresolved count")
    if counts["captions_ok"] + counts["no_captions"] + counts["caption_failures"] != len(items):
        raise ValueError("caption counts do not reconcile with manifest items")
    if counts["comments_ok"] + counts["comments_unavailable"] != len(items):
        raise ValueError("comment counts do not reconcile with manifest items")

    expected_partial = any((counts["metadata_failures"], counts["caption_failures"], counts["comments_unavailable"]))
    if status == "ok" and expected_partial:
        raise ValueError("incomplete corpus may not report status ok")
    if status == "partial" and not expected_partial:
        raise ValueError("partial corpus requires an incomplete count")
    if status in {"ok", "partial"}:
        if progress.get("state") != "complete":
            raise ValueError("completed corpus must have progress state complete")
        if int(progress.get("completed") or 0) != len(items):
            raise ValueError("progress completed must equal manifest item count")
        if int(progress.get("unresolved") or 0) != len(unresolved):
            raise ValueError("progress unresolved must equal manifest unresolved count")
        if bool(partial_reasons) != (status == "partial"):
            raise ValueError("partial_reasons must match result status")
        if data.get("partial_reasons") != partial_reasons:
            raise ValueError("result partial_reasons must equal manifest partial_reasons")
    else:
        if progress.get("state") != "failed":
            raise ValueError("failed channel result must have progress state failed")
        if items or unresolved:
            raise ValueError("channel discovery failure may not claim video items")

    unresolved_ids = set()
    for item in unresolved:
        video_id = str(item.get("video_id") or "")
        if len(video_id) != 11 or video_id in unresolved_ids:
            raise ValueError("invalid or duplicate unresolved video id")
        unresolved_ids.add(video_id)
        if item.get("status") not in {"access_blocked", "error"}:
            raise ValueError("invalid unresolved status")
        if not str(item.get("reason") or "").strip():
            raise ValueError("unresolved video requires reason")

    item_ids = set()
    comments_unavailable = 0
    caption_status_counts = {"ok": 0, "skipped_no_captions": 0, "access_blocked": 0, "error": 0}
    for item in items:
        video_id = str(item.get("video_id") or "")
        if len(video_id) != 11 or video_id in item_ids or video_id in unresolved_ids:
            raise ValueError("invalid or duplicate video id")
        item_ids.add(video_id)
        if not str(item.get("upload_date") or "").startswith("2026"):
            raise ValueError("manifest contains a video outside 2026")
        video_dir = RESULTS / "videos" / video_id
        metadata_path = video_dir / "metadata.json"
        comments_path = video_dir / "comments.json"
        if not metadata_path.is_file() or not comments_path.is_file():
            raise ValueError("manifest item missing metadata/comments artifact")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata != item:
            raise ValueError("metadata.json must exactly match manifest item")
        comments = json.loads(comments_path.read_text(encoding="utf-8"))
        if comments.get("sort") != "top" or comments.get("include_replies") is not False:
            raise ValueError("comments policy mismatch")
        comment_items = comments.get("comments") or []
        if int(comments.get("count") or 0) != len(comment_items):
            raise ValueError("comments count does not match stored comments")
        if int(comments.get("count") or 0) > 7 or len(comment_items) > 7:
            raise ValueError("more than 7 comments stored")
        if item.get("comments_status") != comments.get("status") or item.get("comments_count") != len(comment_items):
            raise ValueError("manifest comment metadata mismatch")
        if comments.get("status") != "ok":
            comments_unavailable += 1
        for comment in comment_items:
            if not str(comment.get("text") or "").strip():
                raise ValueError("empty comment stored")

        transcript_status = item.get("transcript_status")
        if transcript_status not in caption_status_counts:
            raise ValueError("invalid transcript status")
        caption_status_counts[transcript_status] += 1
        transcript_path = video_dir / "transcript.txt"
        if transcript_status == "ok":
            if not transcript_path.is_file():
                raise ValueError("ok transcript item missing transcript.txt")
            transcript = transcript_path.read_text(encoding="utf-8")
            digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
            if item.get("transcript_sha256") != digest:
                raise ValueError("transcript_sha256 mismatch")
        elif transcript_path.exists():
            raise ValueError("non-ok transcript item may not contain transcript.txt")
    if comments_unavailable != counts["comments_unavailable"]:
        raise ValueError("comments_unavailable count mismatch")
    if caption_status_counts["ok"] != counts["captions_ok"]:
        raise ValueError("captions_ok count mismatch")
    if caption_status_counts["skipped_no_captions"] != counts["no_captions"]:
        raise ValueError("no_captions count mismatch")
    if caption_status_counts["access_blocked"] + caption_status_counts["error"] != counts["caption_failures"]:
        raise ValueError("caption_failures count mismatch")

    if index.get("schema_version") != "2.0" or index.get("scope") != "current_run":
        raise ValueError("processed-index must be schema 2.0 current_run")
    index_items = index.get("items") or []
    index_ids = [str(item.get("video_id") or "") for item in index_items]
    if set(index_ids) != item_ids or len(index_ids) != len(item_ids):
        raise ValueError("processed-index must contain exactly the current run video ids")
    if int(index.get("requested_entries") or 0) != len(items):
        raise ValueError("processed-index requested_entries mismatch")

    archive = RESULTS / "channel-corpus.zip"
    if not archive.is_file():
        raise ValueError("channel-corpus.zip missing")
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        for required in ("manifest.json", "result.json", "progress.json", "processed-index.json"):
            if required not in names:
                raise ValueError(f"zip missing {required}")
        if any(name.startswith("../") or "/../" in name for name in names):
            raise ValueError("unsafe path in ZIP")
        expected_names = {
            item.relative_to(RESULTS).as_posix()
            for item in RESULTS.rglob("*")
            if item.is_file() and item != archive and item.name != "SHA256SUMS.txt"
        }
        if names != expected_names:
            raise ValueError("zip contents must exactly match current result artifacts")

    for item in RESULTS.rglob("*"):
        if item.is_file() and item.suffix.lower() in MEDIA_EXTENSIONS:
            raise ValueError(f"media artifact forbidden: {item.name}")


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else RESULTS / "result.json")
    validate(target)
    print("channel-result-contract: OK")


if __name__ == "__main__":
    main()
