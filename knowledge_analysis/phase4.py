"""Evidence-only phase-4 claim triage. No AI calls or external source writes.

The four labels are REVIEWER PROPOSALS, not accepted knowledge conclusions.
A submitted source URL/hash is untrusted metadata; independent source readback and
owner approval must occur outside this isolated GitHub repository workflow.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from .corpus import VIDEO_ID
from .review import (OWNERS, POLICY_VERSION, STATUS_COMPLETE, STATUS_SOURCE_WARNING,
                     STATUS_NO_TRANSCRIPT_COMMENTS)

CATEGORIES = frozenset({"UPDATE", "ALREADY_COVERED", "REJECTED", "NEEDS_VERIFICATION"})
REVIEWED_STATUSES = frozenset({STATUS_COMPLETE, STATUS_SOURCE_WARNING,
                               STATUS_NO_TRANSCRIPT_COMMENTS})
HEX256 = re.compile(r"^[0-9a-f]{64}$")
ACCEPTANCE = "pending_independent_owner_and_source_verification"


class Phase4Error(ValueError):
    pass


def _digest(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _source_url(value: object) -> bool:
    if not isinstance(value, str) or not (12 <= len(value) <= 2048):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (parsed.scheme == "https" and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
            and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            and not parsed.hostname.endswith((".local", ".internal")))


def _validate_review(video: dict) -> bool:
    if not isinstance(video, dict) or video.get("schema_version") != "1.0":
        raise Phase4Error("unsupported review record")
    if video.get("policy_version") != POLICY_VERSION:
        raise Phase4Error("review policy version mismatch")
    if not VIDEO_ID.fullmatch(str(video.get("video_id", ""))):
        raise Phase4Error("invalid review video ID")
    for key in ("signature", "model_sha256", "transcript_sha256"):
        if not isinstance(video.get(key), str) or not HEX256.fullmatch(video[key]):
            raise Phase4Error("invalid review hash: " + key)
    for key in ("auto_promoted", "human_qa_approved", "project_source_compared",
                "primary_sources_verified"):
        if video.get(key) is not False:
            raise Phase4Error("untrusted review asserts completed external verification")
    if not isinstance(video.get("claims"), list) or len(video["claims"]) > 15_000:
        raise Phase4Error("invalid or oversized review claims collection")
    status = video.get("status")
    if not isinstance(status, str):
        raise Phase4Error("invalid review status")
    complete = status in REVIEWED_STATUSES
    if status == STATUS_SOURCE_WARNING and video.get("source_integrity_warning") is not True:
        raise Phase4Error("source-warning review lost its integrity warning")
    if complete and (video.get("transcript_read_completely") is not True
                     or video.get("comments_read_completely") is not True):
        raise Phase4Error("reviewed status without complete saved chunk coverage")
    if not complete and video["claims"]:
        # Partially reviewed chunks remain useful as raw evidence but are not
        # eligible for knowledge triage until the original source review completes.
        return False
    return complete


def _candidate(video: dict, claim: dict) -> dict:
    if not isinstance(claim, dict) or claim.get("evidence_only") is not True:
        raise Phase4Error("untrusted claim is not evidence-only")
    text, quote = claim.get("claim"), claim.get("quote")
    if not isinstance(text, str) or not 8 <= len(text) <= 900:
        raise Phase4Error("invalid model claim")
    if not isinstance(quote, str) or not 1 <= len(quote) <= 110:
        raise Phase4Error("invalid claim source excerpt")
    start, end = claim.get("evidence_start"), claim.get("evidence_end")
    if type(start) is not int or type(end) is not int or start < 0 or end - start != len(quote):
        raise Phase4Error("invalid anchored excerpt offsets")
    src, idx = claim.get("source"), claim.get("comment_index")
    if src not in ("transcript", "comment"):
        raise Phase4Error("invalid claim evidence source")
    if src == "comment":
        if type(idx) is not int or idx < 0 or claim.get("creator_attribution") is not False:
            raise Phase4Error("a saved comment is not a creator statement")
    elif idx is not None:
        raise Phase4Error("transcript claim has comment index")
    owner = claim.get("owner_candidate")
    if owner not in OWNERS | {"unknown"}:
        raise Phase4Error("unknown owner label in imported claim")
    identity = {
        "review_signature": video["signature"], "video_id": video["video_id"],
        "source": src, "comment_index": idx, "evidence_start": start,
        "evidence_end": end, "quote": quote, "claim": text,
        "owner_candidate": owner, "kind": claim.get("kind", "unknown"),
        "needs_current_verification": claim.get("needs_current_verification") is not False,
    }
    return {
        "claim_id": _digest(identity),
        "literal_dedup_key": sha256(" ".join(text.lower().split()).encode("utf-8")).hexdigest(),
        "video_id": video["video_id"], "source": src, "comment_index": idx,
        "evidence_start": start, "evidence_end": end,
        "quote": quote, "claim": text, "owner_candidate": owner,
        "kind": claim.get("kind", "unknown"),
        "needs_current_verification": claim.get("needs_current_verification") is not False,
        "transcript_hash_warning": video.get("source_integrity_warning") is True,
        "comments_status": video.get("comments_status", "unknown"),
    }


def _validate_decision(decision: dict) -> dict:
    if not isinstance(decision, dict):
        raise Phase4Error("invalid decision")
    category = decision.get("category")
    if category not in CATEGORIES:
        raise Phase4Error("unknown phase-4 category")
    rationale = decision.get("rationale", "")
    if not isinstance(rationale, str) or len(rationale) > 2000:
        raise Phase4Error("invalid review rationale")
    if category != "NEEDS_VERIFICATION" and len(rationale.strip()) < 20:
        raise Phase4Error("non-pending category requires specific rationale")
    if category in ("UPDATE", "ALREADY_COVERED"):
        if not isinstance(decision.get("project_source_id"), str) or not (3 <= len(decision["project_source_id"]) <= 256):
            raise Phase4Error("source comparison requires a project-source identifier")
        if not isinstance(decision.get("project_source_sha256"), str) or not HEX256.fullmatch(decision["project_source_sha256"]):
            raise Phase4Error("source comparison requires a pinned project-source hash")
    if category == "UPDATE":
        if decision.get("owner") not in OWNERS:
            raise Phase4Error("update proposal requires one valid specialist owner")
        if not _source_url(decision.get("official_source_url")):
            raise Phase4Error("update proposal requires an HTTPS official source URL")
        checked = decision.get("official_checked_at")
        try:
            if not isinstance(checked, str) or date.fromisoformat(checked) > date.today():
                raise ValueError("invalid date")
        except ValueError as exc:
            raise Phase4Error("update proposal requires a non-future official check date") from exc
    if decision.get("auto_promoted", False) is not False:
        raise Phase4Error("decision cannot authorize knowledge promotion")
    # Submitted URLs and hashes are pointers, not proof that the source was
    # actually fetched or that the proposed category is factually correct.
    return {
        "proposed_category": category,
        "rationale": rationale,
        "project_source_id": decision.get("project_source_id", ""),
        "project_source_sha256": decision.get("project_source_sha256", ""),
        "official_source_url": decision.get("official_source_url", ""),
        "official_checked_at": decision.get("official_checked_at", ""),
        "owner_proposal": decision.get("owner", ""),
        "acceptance": ACCEPTANCE,
        "auto_promoted": False,
    }


def triage(reviews: list[dict], decisions: list[dict] | None = None) -> dict:
    """Create a bounded, pending-review claim ledger from completed local model evidence."""
    if not isinstance(reviews, list) or len(reviews) > 500:
        raise Phase4Error("review list exceeds one logical batch")
    proposed = {}
    for decision in decisions or []:
        if not isinstance(decision, dict):
            raise Phase4Error("invalid manual decision")
        key = decision.get("claim_id")
        if not isinstance(key, str) or not HEX256.fullmatch(key) or key in proposed:
            raise Phase4Error("invalid or duplicate claim decision ID")
        proposed[key] = _validate_decision(decision)
    items, ids, skipped = [], set(), 0
    videos_seen = set()
    for video in reviews:
        if not isinstance(video, dict):
            raise Phase4Error("non-object review")
        if video.get("video_id") in videos_seen:
            raise Phase4Error("duplicate review video ID")
        videos_seen.add(video.get("video_id"))
        if not _validate_review(video):
            skipped += 1
            continue
        for claim in video["claims"]:
            item = _candidate(video, claim)
            key = item["claim_id"]
            if key in ids:
                raise Phase4Error("duplicate imported claim identity")
            ids.add(key)
            item.update(proposed.get(key, {
                "proposed_category": "NEEDS_VERIFICATION",
                "rationale": "Awaiting project-source, official-source and owner comparison",
                "acceptance": ACCEPTANCE,
                "auto_promoted": False,
            }))
            # A hash conflict cannot be converted into an accepted new rule,
            # even when a reviewer submits a plausible external URL.
            if (item["transcript_hash_warning"] or video.get("status") == STATUS_SOURCE_WARNING) and item["proposed_category"] == "UPDATE":
                raise Phase4Error("legacy transcript digest warning blocks an UPDATE proposal")
            items.append(item)
    if set(proposed) - ids:
        raise Phase4Error("manual decisions reference absent or ineligible claims")
    counts = dict(Counter(x["proposed_category"] for x in items))
    return {
        "schema_version": "1.0", "scope": "evidence_only",
        "status": "requires_external_project_source_readback_and_owner_qa",
        "policy_version": POLICY_VERSION,
        "video_records_provided": len(reviews),
        "incomplete_video_records_excluded": skipped,
        "claim_count": len(items),
        "proposed_category_counts": counts,
        "source_quote_rechecked_against_raw_transcript": False,
        "external_project_sources_fetched": False,
        "official_sources_checked_by_tool": False,
        "human_qa_approved": False,
        "auto_promoted": False,
        "claims": items,
    }
