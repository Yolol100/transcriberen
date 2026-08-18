#!/usr/bin/env python3
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
path = Path(sys.argv[1] if len(sys.argv) > 1 else "results/result.json")
results_dir = path.parent
result = json.loads(path.read_text(encoding="utf-8"))
contract = json.loads((ROOT / "toolkit-contract.json").read_text(encoding="utf-8"))
errors = []
hex64 = re.compile(r"^[0-9a-f]{64}$")
MEDIA_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
FORBIDDEN_COMMENT_KEYS = {"id", "parent", "author", "author_id", "author_url"}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_json_file(candidate, label):
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{label}: {exc}")
        return None


def expect(condition, label):
    if not condition:
        errors.append(label)


expect(result.get("schema_version") == "webactueel-transcription-result/1.1", "schema_version")
expect(result.get("owner") == "webactueel-workflow", "owner")
expect(result.get("project_id") == "project-transcriberen", "project_id")
expect(result.get("evidence_level") == "controlled_runtime", "evidence_level")
expect(hex64.fullmatch(str(result.get("content_sha256", ""))) is not None, "content_sha256")
expect(bool(result.get("rights_basis")), "rights_basis")
for field in ("audio_access_authorized", "analysis_content_allowed", "reuse_allowed", "public_request_acknowledged"):
    expect(isinstance(result.get(field), bool), field)
expected_persist = bool(result.get("analysis_content_allowed") or result.get("reuse_allowed"))
expect(result.get("content_persisted") is expected_persist, "content persistence mismatch")
expect(result.get("usage_mode") == ("reuse-authorized" if result.get("reuse_allowed") else "analysis-paraphrase-only"), "usage_mode")
source_context = result.get("source_context") or {}
expect(source_context.get("project_id") == "project-transcriberen", "source_context project")
expect(source_context.get("source_set_version") == contract.get("source_set_version"), "source_context current source_set")
provenance = result.get("runtime_provenance") or {}
expect(hex64.fullmatch(str(provenance.get("request_sha256", ""))) is not None, "runtime request hash")
for key in ("repository", "head_sha", "run_id", "run_attempt", "workflow_ref", "event_name", "repository_visibility"):
    expect(key in provenance, f"runtime provenance {key}")
visibility = str(provenance.get("repository_visibility") or "").lower()
if visibility == "public":
    expect(result.get("public_request_acknowledged") is True, "public request acknowledgement")
    expect(expected_persist is False, "public repository content persistence forbidden")

versions = result.get("tool_versions") or {}
for name in ("yt-dlp", "trafilatura"):
    expect(bool(versions.get(name)), f"tool version {name}")
if result.get("detected_mode") == "whisper":
    expect(result.get("audio_access_authorized") is True, "whisper authorized audio")
    host = (urlsplit(str(result.get("source_url") or "")).hostname or "").lower().rstrip(".")
    expect(not (host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")), "public YouTube may not use whisper")

content = results_dir / "content.md"
if expected_persist:
    expect(content.is_file(), "content.md required")
    if content.is_file():
        data = content.read_bytes()
        expect(sha256_bytes(data) == result.get("content_sha256"), "content.md SHA-256 mismatch")
        expect(len(data.decode("utf-8", errors="replace")) == int(result.get("content_chars") or -1), "content.md character count mismatch")
else:
    expect(not content.exists(), "content.md forbidden")

for candidate in results_dir.rglob("*"):
    if candidate.is_file() and candidate.suffix.lower() in MEDIA_EXTENSIONS:
        errors.append(f"media artifact forbidden: {candidate.relative_to(results_dir)}")

if result.get("detected_mode") == "youtube":
    expect(result.get("youtube_access_basis") in {"prior-written-permission", "applicable-law-reviewed"}, "youtube_access_basis")
    yt = (result.get("metadata") or {}).get("youtube") or {}
    expect(yt.get("media_downloaded") is False, "YouTube media_downloaded must be false")
    expect(bool(yt.get("scope")), "youtube scope")
    index_path = results_dir / "youtube-index.json"
    expect(index_path.is_file(), "youtube-index.json")
    index = load_json_file(index_path, "youtube-index.json") if index_path.is_file() else {}
    index = index or {}
    expect(index.get("schema_version") == "webactueel-youtube-collection/1.1", "youtube index schema")
    expect(index.get("scope") == yt.get("scope"), "youtube scope mismatch")
    expect(index.get("comment_identity_minimized") is True, "youtube comment identity minimization")
    expect(index.get("comment_text_redaction") == "obvious-direct-identifiers", "youtube comment text redaction")
    discovery = index.get("discovery") or {}
    expect(isinstance(discovery.get("possibly_truncated"), bool), "youtube discovery completeness")
    items = index.get("items") if isinstance(index.get("items"), list) else []
    if not isinstance(index.get("items"), list):
        errors.append("youtube items")
    counts = [index.get(k) for k in ("candidate_count", "eligible_count", "selected_count", "item_count")]
    expect(all(isinstance(v, int) and v >= 0 for v in counts), "youtube counts")
    if all(isinstance(v, int) and v >= 0 for v in counts):
        expect(counts[0] >= counts[1] >= counts[2], "youtube count ordering")
        expect(counts[2] == counts[3] == len(items), "youtube item count mismatch")

    transcript_count = no_caption_count = caption_error_count = comment_error_count = comments_disabled_count = review_count = 0
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
        expect(meta_path.is_file(), f"youtube item {artifact_id} metadata")
        if meta_path.is_file():
            stored_meta = load_json_file(meta_path, f"metadata {artifact_id}")
            expect(stored_meta == item.get("metadata"), f"youtube item {artifact_id} metadata mismatch")
            if not expected_persist and isinstance(stored_meta, dict):
                for risky in ("description", "uploader", "uploader_id", "tags", "chapters"):
                    expect(risky not in stored_meta, f"youtube minimized metadata leaked {risky}")

        transcript_path = item_dir / "transcript.md"
        cues_path = item_dir / "transcript-cues.json"
        if item.get("transcript_chars"):
            transcript_count += 1
            if expected_persist:
                expect(transcript_path.is_file(), f"youtube item {artifact_id} transcript missing")
                expect(cues_path.is_file(), f"youtube item {artifact_id} cue provenance missing")
                if transcript_path.is_file():
                    data = transcript_path.read_bytes()
                    expect(sha256_bytes(data) == item.get("transcript_sha256"), f"youtube item {artifact_id} transcript hash")
            else:
                expect(not transcript_path.exists(), f"youtube item {artifact_id} transcript forbidden")
                expect(not cues_path.exists(), f"youtube item {artifact_id} cues forbidden")
        else:
            expect(not transcript_path.exists(), f"youtube item {artifact_id} unexpected transcript")
            expect(not cues_path.exists(), f"youtube item {artifact_id} unexpected cues")

        if item.get("status") == "no_captions": no_caption_count += 1
        if item.get("status") == "caption_error": caption_error_count += 1
        if item.get("comment_status") == "error": comment_error_count += 1
        if item.get("comment_status") == "comments_disabled": comments_disabled_count += 1

        comments_path = item_dir / "comments.json"
        review_path = item_dir / "comment-review.json"
        if comments_path.exists():
            expect(expected_persist, f"youtube item {artifact_id} comments forbidden")
            comments = load_json_file(comments_path, f"comments {artifact_id}")
            if isinstance(comments, list):
                expect(len(comments) == item.get("comments_extracted"), f"youtube item {artifact_id} comments count")
                for comment in comments:
                    if isinstance(comment, dict):
                        expect(not FORBIDDEN_COMMENT_KEYS.intersection(comment), f"youtube item {artifact_id} comment identity field")
                        expect(comment.get("text_redacted") is True, f"youtube item {artifact_id} comment redaction marker")
        elif item.get("comments_extracted") and expected_persist:
            errors.append(f"youtube item {artifact_id} comments missing")

        if review_path.exists():
            expect(expected_persist, f"youtube item {artifact_id} comment review forbidden")
            review = load_json_file(review_path, f"comment review {artifact_id}")
            if isinstance(review, dict):
                expect(review.get("source_trust") == "untrusted", f"youtube item {artifact_id} comment review trust")
                candidates = review.get("candidates") if isinstance(review.get("candidates"), list) else []
                review_count += len(candidates)
                for candidate in candidates:
                    expect(candidate.get("untrusted_source_text") is True, f"youtube item {artifact_id} candidate trust marker")

    expected = {
        "transcript_count": transcript_count,
        "no_caption_count": no_caption_count,
        "caption_error_count": caption_error_count,
        "comment_error_count": comment_error_count,
        "comments_disabled_count": comments_disabled_count,
        "comment_review_candidate_count": review_count,
    }
    for key, value in expected.items():
        expect(index.get(key) == value, f"youtube {key} mismatch")

if errors:
    print("result validation failed: " + ", ".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("result contract: OK")
