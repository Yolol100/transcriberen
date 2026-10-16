#!/usr/bin/env python3
"""Fail-closed real saved-comment Qwen canary; never publish source text."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from knowledge_analysis.corpus import Video, iter_videos
from knowledge_analysis.routing import apply_master_routing, load_master_routing, verify_pinned_shards
from knowledge_analysis.review import (
    STATUS_COMPLETE, STATUS_SOURCE_WARNING, _valid_prior, signature, split_exact,
)
from scripts.drive_pilot_result import MODEL_SHA
from scripts.drive_preflight import MASTER_SHA

SOURCE_COUNT = 18875
COMMENT_SLICE = 11
STORED_COMMENTS = 4

class CanaryError(ValueError):
    pass

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def private_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 5000000:
        raise CanaryError("missing_or_oversized_private_result")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CanaryError("malformed_private_result")
    return data

def validate_saved_comments(video: Video, review: dict, model_sha: str) -> dict:
    if len(video.comments) != STORED_COMMENTS or not video.transcript:
        raise CanaryError("positive_comment_sample_unavailable")
    expected = STATUS_SOURCE_WARNING if video.transcript_hash_status != "match" else STATUS_COMPLETE
    transcript_tasks = [("transcript", None, a, b, t)
                        for a,b,t in split_exact(video.transcript, 5600)]
    comment_tasks = [("comment", i, a, b, t)
                     for i,c in enumerate(video.comments)
                     for a,b,t in split_exact(c, 5600)]
    tasks = transcript_tasks + comment_tasks
    if not transcript_tasks or not comment_tasks or len({c[1] for c in comment_tasks}) != STORED_COMMENTS:
        raise CanaryError("missing_real_comment_segments")
    if (review.get("video_id") != video.video_id
            or review.get("signature") != signature(video, model_sha, 5600)
            or review.get("model_sha256") != model_sha
            or review.get("status") != expected
            or review.get("comment_count") != STORED_COMMENTS
            or review.get("comment_chunks_expected") != len(comment_tasks)
            or review.get("comments_read_completely") is not True
            or review.get("transcript_read_completely") is not True
            or review.get("human_qa_approved") is not False
            or review.get("auto_promoted") is not False
            or not _valid_prior(review, tasks, expected_status=expected,
                                video=video, model_sha256=model_sha)):
        raise CanaryError("real_qwen_comments_incomplete_or_unanchored")
    processed = [c for c in review["chunks"] if c.get("source") == "comment"]
    if len(processed) != len(comment_tasks):
        raise CanaryError("comment_inference_segment_count_mismatch")
    return {
        "status": "PASS", "scope": "stored_comment_qwen_canary",
        "transcript_segments_checked": len(transcript_tasks),
        "stored_comments_checked": STORED_COMMENTS,
        "comment_segments_checked": len(comment_tasks),
        "historical_transcript_hash_warning": video.transcript_hash_status != "match",
        "source_promoted": False, "human_domain_qa_approved": False,
        "new_public_youtube_acquisition": False, "private_data_published": False,
    }

def run(source_dir: Path, output_dir: Path, model_path: Path) -> dict:
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise CanaryError("bad_private_source_directory")
    if model_path.is_symlink() or not model_path.is_file() or sha(model_path) != MODEL_SHA:
        raise CanaryError("incorrect_local_qwen_model")
    master = source_dir / "YouTube_Kennisbron_Master.zip"
    parts = [source_dir / f"YouTube_Kennisbron_Master.part-{n:02}.zip" for n in range(1,16)]
    routing = load_master_routing(master, MASTER_SHA)
    if len(routing) != SOURCE_COUNT:
        raise CanaryError("wrong_master_record_count")
    verify_pinned_shards(master, parts, SOURCE_COUNT)
    ordered = sorted(routing)
    if (routing[ordered[COMMENT_SLICE]]["comment_count"] != STORED_COMMENTS
            or any(routing[vid]["comment_count"] for vid in ordered[:COMMENT_SLICE])):
        raise CanaryError("pinned_positive_comment_sample_drift")
    target_id = ordered[COMMENT_SLICE]
    selected = [apply_master_routing(v, routing) for v in iter_videos(parts[0])
                if v.video_id == target_id]
    if len(selected) != 1:
        raise CanaryError("selected_video_missing_or_duplicated")
    video = selected[0]
    inventory = private_json(output_dir / "inventory.json")
    checks = {
        "schema_version": "1.0", "scope": "evidence_only", "batch": 1,
        "batch_size": 500, "slice_index": COMMENT_SLICE, "slice_size": 1,
        "total_unique_videos_in_supplied_corpus": SOURCE_COUNT,
        "selected_video_ids": [target_id], "master_routing_sha256": MASTER_SHA,
        "model_sha256": MODEL_SHA, "status": "evidence_only_pending_external_qa",
        "policy_promotions": 0, "human_verified_videos": 0, "source_partial": False,
        "ai_reviewed_videos": 1,
    }
    if any(inventory.get(k) != v for k,v in checks.items()):
        raise CanaryError("canary_inventory_drift")
    if inventory.get("source_files") != [
        {"name": p.name, "sha256": sha(p)} for p in parts
    ]:
        raise CanaryError("original_shard_receipt_drift")
    review = private_json(output_dir / "videos" / (target_id + ".json"))
    return validate_saved_comments(video, review, MODEL_SHA)

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dir",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--model-path",type=Path,required=True)
    args=p.parse_args()
    try:
        result=run(args.source_dir,args.output_dir,args.model_path)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("BLOCKED: private saved-comment canary: "+type(exc).__name__,file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
