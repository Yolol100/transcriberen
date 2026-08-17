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
if result.get("content_persisted") is not bool(result.get("reuse_allowed")): errors.append("content persistence mismatch")
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
if result.get("reuse_allowed") and not content.is_file(): errors.append("content.md required when reuse_allowed=true")
if not result.get("reuse_allowed") and content.exists(): errors.append("content.md forbidden when reuse_allowed=false")

if result.get("detected_mode") == "youtube_collection":
    metadata = result.get("metadata", {})
    if not isinstance(metadata.get("items"), list) or not metadata.get("items"):
        errors.append("youtube collection items")
    if metadata.get("scan_status") not in {"captions_collected", "no_usable_captions"}:
        errors.append("youtube collection scan_status")
    targets = metadata.get("collection_targets")
    if not isinstance(targets, list) or not targets:
        errors.append("youtube collection targets")

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
            if not isinstance(register.get("sources"), list): errors.append("source register sources")

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
            expected_status = "review_required" if result.get("reuse_allowed") else "rights_review_required"
            if handoff.get("promotion_status") != expected_status: errors.append("knowledge handoff promotion_status")
            if handoff.get("source_register_path") != "source-register.json": errors.append("knowledge handoff source register")
            if not isinstance(handoff.get("source_items"), list): errors.append("knowledge handoff source_items")

if errors:
    print("result validation failed: " + ", ".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("result contract: OK")
