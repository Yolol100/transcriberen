#!/usr/bin/env python3
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

path = Path(sys.argv[1] if len(sys.argv) > 1 else "results/result.json")
results_dir = path.parent
result = json.loads(path.read_text(encoding="utf-8"))
errors = []
hex64 = re.compile(r"^[0-9a-f]{64}$")
MEDIA_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_json_file(candidate, label):
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{label}: {exc}")
        return None


if result.get("schema_version") != "webactueel-transcription-result/1.1": errors.append("schema_version")
if result.get("owner") != "webactueel-workflow": errors.append("owner")
if result.get("project_id") != "project-transcriberen": errors.append("project_id")
if result.get("evidence_level") != "controlled_runtime": errors.append("evidence_level")
if not hex64.fullmatch(str(result.get("content_sha256", ""))): errors.append("content_sha256")
if not result.get("rights_basis"): errors.append("rights_basis")
if not isinstance(result.get("audio_access_authorized"), bool): errors.append("audio_access_authorized")
if not isinstance(result.get("analysis_content_allowed"), bool): errors.append("analysis_content_allowed")
if not isinstance(result.get("reuse_allowed"), bool): errors.append("reuse_allowed")
expected_persist = bool(result.get("analysis_content_allowed") or result.get("reuse_allowed"))
if result.get("content_persisted") is not expected_persist: errors.append("content persistence mismatch")
if result.get("reuse_allowed"):
    if result.get("usage_mode") != "reuse-authorized": errors.append("reuse usage_mode")
else:
    if result.get("usage_mode") != "analysis-paraphrase-only": errors.append("analysis usage_mode")
if not result.get("source_context", {}).get("source_set_version"): errors.append("source_context")
versions = result.get("tool_versions", {})
for name in ("yt-dlp", "ffmpeg", "ffprobe", "trafilatura"):
    if not versions.get(name): errors.append(f"tool version {name}")
if result.get("detected_mode") == "whisper" and not result.get("audio_access_authorized"):
    errors.append("whisper requires authorized audio")
host = (urlsplit(str(result.get("source_url") or "")).hostname or "").lower().rstrip(".")
if result.get("detected_mode") == "whisper" and (host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")):
    errors.append("public YouTube may not use whisper")

content = results_dir / "content.md"
if expected_persist:
    if not content.is_file():
        errors.append("content.md required when analysis/reuse persistence is enabled")
    else:
        content_bytes = content.read_bytes()
        if sha256_bytes(content_bytes) != result.get("content_sha256"):
            errors.append("content.md SHA-256 mismatch")
        if len(content_bytes.decode("utf-8", errors="replace")) != int(result.get("content_chars") or -1):
            errors.append("content.md character count mismatch")
elif content.exists():
    errors.append("content.md forbidden when persistence is disabled")

# YouTube must never emit media bytes into the results artifact.
for candidate in results_dir.rglob("*"):
    if candidate.is_file() and candidate.suffix.lower() in MEDIA_EXTENSIONS:
        errors.append(f"YouTube/media artifact forbidden: {candidate.relative_to(results_dir)}")

if result.get("detected_mode") == "youtube":
    yt = result.get("metadata", {}).get("youtube", {})
    if yt.get("media_downloaded") is not False: errors.append("YouTube media_downloaded must be false")
    if not yt.get("scope"): errors.append("youtube scope")
    index_path = results_dir / "youtube-index.json"
    if not index_path.is_file():
        errors.append("youtube-index.json")
    else:
        index = load_json_file(index_path, "youtube-index.json") or {}
        if index.get("schema_version") != "webactueel-youtube-collection/1.1": errors.append("youtube index schema")
        if index.get("scope") != yt.get("scope"): errors.append("youtube index scope mismatch")
        items = index.get("items")
        if not isinstance(items, list):
            errors.append("youtube index items")
            items = []
        counts = {
            "candidate_count": index.get("candidate_count"),
            "eligible_count": index.get("eligible_count"),
            "selected_count": index.get("selected_count"),
            "item_count": index.get("item_count"),
        }
        if not all(isinstance(value, int) and value >= 0 for value in counts.values()):
            errors.append("youtube index counts")
        else:
            if not (counts["candidate_count"] >= counts["eligible_count"] >= counts["selected_count"]):
                errors.append("youtube count ordering")
            if counts["selected_count"] != counts["item_count"] or counts["item_count"] != len(items):
                errors.append("youtube item count mismatch")
        if index.get("collection_status") not in {"empty", "no_usable_captions", "partial", "ok"}:
            errors.append("youtube collection_status")
        if index.get("include_comments") and index.get("comment_identity_minimized") is not True:
            errors.append("youtube comment identity minimization")
        discovery = index.get("discovery")
        if not isinstance(discovery, dict) or not isinstance(discovery.get("possibly_truncated"), bool):
            errors.append("youtube discovery completeness")

        transcript_count = 0
        no_caption_count = 0
        caption_error_count = 0
        comment_error_count = 0
        for pos, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"youtube item {pos} invalid")
                continue
            artifact_id = str(item.get("artifact_id") or "")
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", artifact_id):
                errors.append(f"youtube item {pos} artifact_id")
                continue
            item_dir = results_dir / "items" / artifact_id
            meta_path = item_dir / "metadata.json"
            if not meta_path.is_file():
                errors.append(f"youtube item {artifact_id} metadata.json")
            else:
                stored_meta = load_json_file(meta_path, f"metadata {artifact_id}")
                if stored_meta is not None and stored_meta != item.get("metadata"):
                    errors.append(f"youtube item {artifact_id} metadata mismatch")

            transcript_path = item_dir / "transcript.md"
            if item.get("transcript_chars"):
                transcript_count += 1
                if expected_persist:
                    if not transcript_path.is_file():
                        errors.append(f"youtube item {artifact_id} transcript missing")
                    else:
                        transcript_bytes = transcript_path.read_bytes()
                        if sha256_bytes(transcript_bytes) != item.get("transcript_sha256"):
                            errors.append(f"youtube item {artifact_id} transcript SHA-256 mismatch")
                        if len(transcript_bytes.decode("utf-8", errors="replace")) != item.get("transcript_chars"):
                            errors.append(f"youtube item {artifact_id} transcript chars mismatch")
                elif transcript_path.exists():
                    errors.append(f"youtube item {artifact_id} transcript forbidden")
            elif transcript_path.exists():
                errors.append(f"youtube item {artifact_id} unexpected transcript")
            if item.get("status") == "no_captions": no_caption_count += 1
            if item.get("status") == "caption_error": caption_error_count += 1
            if item.get("comment_status") == "error": comment_error_count += 1

            comments_path = item_dir / "comments.json"
            if comments_path.exists():
                if not expected_persist:
                    errors.append(f"youtube item {artifact_id} comments forbidden")
                comments = load_json_file(comments_path, f"comments {artifact_id}")
                if isinstance(comments, list):
                    if len(comments) != item.get("comments_extracted"):
                        errors.append(f"youtube item {artifact_id} comment count mismatch")
                    for comment in comments:
                        if isinstance(comment, dict) and any(key in comment for key in ("id", "parent", "author", "author_id", "author_url")):
                            errors.append(f"youtube item {artifact_id} comment identity field")
                            break
            elif item.get("comments_extracted") and expected_persist:
                errors.append(f"youtube item {artifact_id} comments missing")

        expected_summary = {
            "transcript_count": transcript_count,
            "no_caption_count": no_caption_count,
            "caption_error_count": caption_error_count,
            "comment_error_count": comment_error_count,
        }
        for key, value in expected_summary.items():
            if index.get(key) != value:
                errors.append(f"youtube {key} mismatch")

if errors:
    print("result validation failed: " + ", ".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("result contract: OK")
