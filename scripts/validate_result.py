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
content = Path("results/content.md")
if expected_persist and not content.is_file(): errors.append("content.md required when analysis/reuse persistence is enabled")
if not expected_persist and content.exists(): errors.append("content.md forbidden when persistence is disabled")

if result.get("detected_mode") == "youtube":
    yt = result.get("metadata", {}).get("youtube", {})
    if yt.get("media_downloaded") is not False: errors.append("YouTube media_downloaded must be false")
    if not Path("results/youtube-index.json").is_file(): errors.append("youtube-index.json")
    if not yt.get("scope"): errors.append("youtube scope")

if errors:
    print("result validation failed: " + ", ".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("result contract: OK")
