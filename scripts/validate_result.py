#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

path = Path(sys.argv[1] if len(sys.argv) > 1 else "results/result.json")
result = json.loads(path.read_text(encoding="utf-8"))
errors = []
hex64 = re.compile(r"^[0-9a-f]{64}$")

if result.get("schema_version") != "webactueel-transcription-result/1.0": errors.append("schema_version")
if result.get("owner") != "webactueel-workflow": errors.append("owner")
if result.get("project_id") != "project-transcriberen": errors.append("project_id")
if result.get("evidence_level") != "controlled_runtime": errors.append("evidence_level")
if not hex64.fullmatch(str(result.get("content_sha256", ""))): errors.append("content_sha256")
if not result.get("rights_basis"): errors.append("rights_basis")
if not isinstance(result.get("audio_access_authorized"), bool): errors.append("audio_access_authorized")
if not result.get("source_context", {}).get("source_set_version"): errors.append("source_context")
versions = result.get("tool_versions", {})
for name in ("yt-dlp", "ffmpeg", "ffprobe", "trafilatura"):
    if not versions.get(name): errors.append(f"tool version {name}")
if result.get("detected_mode") == "whisper" and not result.get("audio_access_authorized"):
    errors.append("whisper requires authorized audio")
host = (urlsplit(str(result.get("source_url", ""))).hostname or "").lower().rstrip(".")
if result.get("detected_mode") == "whisper" and (host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")):
    errors.append("public YouTube may not use whisper")
content = Path("results/content.md")

if result.get("detected_mode") == "youtube_collection":
    metadata = result.get("metadata", {})
    items = metadata.get("items")
    if not isinstance(items, list) or not items:
        errors.append("youtube collection items")
        items = []
    allowed_statuses = {"captions_collected", "no_usable_captions", "caption_access_error", "processing_error"}
    if any(item.get("status") not in allowed_statuses for item in items if isinstance(item, dict)):
        errors.append("youtube collection item status")
    expected_counts = {
        "captions_collected": sum(1 for item in items if isinstance(item, dict) and item.get("status") == "captions_collected"),
        "captions_unavailable": sum(1 for item in items if isinstance(item, dict) and item.get("status") == "no_usable_captions"),
        "caption_access_errors": sum(1 for item in items if isinstance(item, dict) and item.get("status") == "caption_access_error"),
        "processing_errors": sum(1 for item in items if isinstance(item, dict) and item.get("status") == "processing_error"),
    }
    for key, value in expected_counts.items():
        if metadata.get(key) != value:
            errors.append(f"youtube collection {key}")
    if expected_counts["captions_collected"]:
        expected_scan_status = "partial" if expected_counts["caption_access_errors"] or expected_counts["processing_errors"] else "captions_collected"
    elif expected_counts["caption_access_errors"]:
        expected_scan_status = "source_access_blocked"
    elif expected_counts["processing_errors"]:
        expected_scan_status = "processing_error"
    else:
        expected_scan_status = "no_usable_captions"
    if metadata.get("scan_status") != expected_scan_status:
        errors.append("youtube collection scan_status")
    targets = metadata.get("collection_targets")
    if not isinstance(targets, list) or not targets:
        errors.append("youtube collection targets")

    expected_persisted = bool(result.get("reuse_allowed")) and expected_counts["captions_collected"] > 0
    if result.get("content_persisted") is not expected_persisted:
        errors.append("content persistence mismatch")
    if expected_persisted and not content.is_file():
        errors.append("content.md required when reusable captions exist")
    if not expected_persisted and content.exists():
        errors.append("content.md forbidden without reusable captions")
    if not expected_counts["captions_collected"] and result.get("content_chars") != 0:
        errors.append("empty collection content_chars")

    register_path = Path("results/source-register.json")
    if not register_path.is_file():
        errors.append("source-register.json required for youtube_collection")
    else:
        try:
            register = json.loads(register_path.read_text(encoding="utf-8"))
        except Exception:
            errors.append("source register json")
        else:
            if register.get("schema_version") != "webactueel-source-register/1.0": errors.append("source register schema")
            if register.get("request_id") != result.get("request_id"): errors.append("source register request_id")
            if register.get("sources") != items: errors.append("source register sources")

    handoff_path = Path("results/knowledge-handoff.json")
    if not handoff_path.is_file():
        errors.append("knowledge-handoff.json required for youtube_collection")
    else:
        try:
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        except Exception:
            errors.append("knowledge handoff json")
        else:
            if handoff.get("schema_version") != "webactueel-knowledge-handoff/1.0": errors.append("knowledge handoff schema")
            if handoff.get("request_id") != result.get("request_id"): errors.append("knowledge handoff request_id")
            if not result.get("reuse_allowed"):
                expected_status = "rights_review_required"
            elif expected_counts["captions_collected"]:
                expected_status = "review_required"
            elif expected_counts["caption_access_errors"] or expected_counts["processing_errors"]:
                expected_status = "source_access_blocked"
            else:
                expected_status = "no_content"
            if handoff.get("promotion_status") != expected_status: errors.append("knowledge handoff promotion_status")
            expected_available = expected_counts["captions_collected"] > 0
            if handoff.get("content_available") is not expected_available: errors.append("knowledge handoff content_available")
            expected_path = "content.md" if expected_persisted else None
            if handoff.get("content_path") != expected_path: errors.append("knowledge handoff content_path")
            if handoff.get("source_register_path") != "source-register.json": errors.append("knowledge handoff source register")
            if handoff.get("source_items") != items: errors.append("knowledge handoff source_items")
else:
    if result.get("content_persisted") is not bool(result.get("reuse_allowed")): errors.append("content persistence mismatch")
    if result.get("reuse_allowed") and not content.is_file(): errors.append("content.md required when reuse_allowed=true")
    if not result.get("reuse_allowed") and content.exists(): errors.append("content.md forbidden when reuse_allowed=false")

if errors:
    print("result validation failed: " + ", ".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("result contract: OK")
