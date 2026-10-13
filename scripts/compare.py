#!/usr/bin/env python3
"""Conservative comparison of video claims to an owner-provided source snapshot.

Never edits project sources or Skills. No remote access or hidden credentials.
Similarity is only a review pointer, never proof a claim is true or current.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge_analysis.corpus import CorpusError, _safe_zip

WORD = re.compile(r"[\w-]{3,}", flags=re.UNICODE)
TEXT_SUFFIX = (".md", ".txt", ".json")
STOP = frozenset("and the with from this that your voor zijn wordt over deze those this can used use een het van met bij door voor".split())


def tokens(text):
    return {t for t in WORD.findall(text.casefold()) if t not in STOP}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_snapshot(path: Path):
    if not path or not path.is_file() or path.stat().st_size > 100_000_000:
        raise CorpusError("missing or oversized project/Skill snapshot")
    snippets = []
    with zipfile.ZipFile(path) as z:
        _safe_zip(z)
        if len(z.infolist()) > 500:
            raise CorpusError("source snapshot exceeds 500 entries")
        for item in sorted(z.infolist(), key=lambda i: i.filename):
            if item.is_dir():
                continue
            if not item.filename.lower().endswith(TEXT_SUFFIX):
                raise CorpusError("non-text file in source snapshot")
            if item.file_size > 1_000_000:
                raise CorpusError("snapshot file too large")
            raw = z.read(item)
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeError as exc:
                raise CorpusError("non-UTF8 project source") from exc
            chunks = re.split(r"\n\s*\n", text)
            for number, paragraph in enumerate(chunks):
                clean = " ".join(paragraph.split())
                if len(clean) < 40:
                    continue
                for start in range(0, len(clean), 1500):
                    piece = clean[start:start+1500]
                    terms = tokens(piece)
                    if len(terms) >= 4:
                        snippets.append({"path": item.filename, "part": number,
                                         "sha256": digest(raw), "text": piece, "tokens": terms})
                        if len(snippets) > 10000:
                            raise CorpusError("snapshot exceeds 10000 paragraphs")
    return snippets


def compare_claims(ledger: dict, snapshot: Path | None):
    if not isinstance(ledger, dict) or ledger.get("scope") != "evidence_only":
        raise CorpusError("not a valid evidence-only claim ledger")
    if ledger.get("auto_promoted") is not False:
        raise CorpusError("untrusted claim ledger claims promotion")
    claims = ledger.get("claims")
    if not isinstance(claims, list) or len(claims) > 15000:
        raise CorpusError("invalid or oversized claim ledger")
    paragraphs = load_snapshot(snapshot) if snapshot else []
    index = defaultdict(list)
    frequencies = Counter()
    for i, p in enumerate(paragraphs):
        for token in p["tokens"]:
            index[token].append(i)
            frequencies[token] += 1
    results = []
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("claim_id"), str):
            raise CorpusError("malformed claim")
        raw = claim.get("claim")
        if not isinstance(raw, str) or len(raw) > 900:
            raise CorpusError("invalid claim text")
        query = tokens(raw)
        score_by_index = Counter()
        for token in sorted(query, key=lambda t: frequencies[t])[:24]:
            if not frequencies[token] or frequencies[token] > 2000:
                continue
            for i in index[token]:
                score_by_index[i] += 1
        top = None
        for idx, hits in score_by_index.most_common(120):
            para = paragraphs[idx]
            overlap = len(query & para["tokens"])
            if overlap < 3:
                continue
            denom = max(1, len(query | para["tokens"]))
            score = overlap / denom
            if top is None or score > top["score"]:
                top = {"score": round(score, 3), "path": para["path"],
                       "sha256": para["sha256"], "excerpt": para["text"][:160]}
        exact = bool(top and top["score"] >= 0.72 and len(query) >= 6)
        results.append({
            "claim_id": claim["claim_id"], "video_id": claim.get("video_id"),
            "owner_candidate": claim.get("owner_candidate", "unknown"),
            "claim": raw, "source_quote": claim.get("quote", ""),
            "proposed_category": "ALREADY_COVERED" if exact else "NEEDS_VERIFICATION",
            "possible_update": bool(paragraphs and not exact),
            "top_source_match": top, "decision": "pending_independent_owner_qa",
            "official_source_verified": False, "skill_updated": False,
        })
    return {
        "schema_version": "1.0", "scope": "evidence_only",
        "snapshot_sha256": digest(snapshot.read_bytes()) if snapshot else None,
        "snapshot_currentness_verified": False,
        "match_method": "lexical_overlap_only_not_semantic_or_factual_verification",
        "claim_count": len(results),
        "proposals": results, "auto_promoted": False,
        "human_qa_approved": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--sources", type=Path, help="Optional supplied project/Skill text snapshot ZIP")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink():
            raise CorpusError("refusing to overwrite comparison")
        if args.ledger.is_symlink() or args.ledger.stat().st_size > 20_000_000:
            raise CorpusError("unsafe claim ledger")
        ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
        report = compare_claims(ledger, args.sources)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n")
        print(json.dumps({"claim_count":report["claim_count"],
                           "snapshot_provided":args.sources is not None,
                           "auto_promoted":False}))
    except (CorpusError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
