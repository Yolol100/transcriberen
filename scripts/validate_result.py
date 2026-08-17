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
    expected_persisted = bool(result.get("reuse_allowed")) and int(metadata.get("captions_collected", 0)) > 0
else:
    expected_persisted = bool(result.get("reuse_allowed"))
if result.get("content_persisted") is not expected_persisted: errors.append("content persistence mismatch")
if expected_persisted and not content.is_file(): errors.append("content.md required when content_persisted=true")
if not expected_persisted and content.exists(): errors.append("content.md forbidden when content_persisted=false")

if result.get("detected_mode") == "youtube_collection":
    metadata = result.get("metadata", {})
    if not isinstance(metadata.get("items"), list) or not metadata.get("items"):
        errors.append("youtube collection items")
    valid_scan_statuses = {"captions_collected", "partial_captions_access_blocked", "no_usable_captions", "access_blocked"}
    if metadata.get("scan_status") not in valid_scan_statuses:
        errors.append("youtube collection scan_status")
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
            expected_promotion = "blocked" if metadata.get("scan_status") == "access_blocked" else "review_required"
            if handoff.get("promotion_status") != expected_promotion: errors.append("knowledge handoff promotion_status")
            if not isinstance(handoff.get("source_items"), list): errors.append("knowledge handoff source_items")
            if handoff.get("content_available") is not expected_persisted: errors.append("knowledge handoff content_available")
            if metadata.get("scan_status") == "access_blocked" and handoff.get("content_path") is not None:
                errors.append("blocked handoff may not expose content_path")

if errors:
    print("result validation failed: " + ", ".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("result contract: OK")
