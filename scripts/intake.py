#!/usr/bin/env python3
"""Read-only intake of an owner ZIP. No YouTube requests, uploads or canonical writes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge_analysis.corpus import CorpusError, _safe_zip, iter_videos, source_receipt
from knowledge_analysis.routing import load_master_routing, verify_pinned_shards
from scripts.knowledge_bundle import prepare_bundle

MASTER = "YouTube_Kennisbron_Master.zip"
PART = re.compile(r"^YouTube_Kennisbron_Master\.part-[0-9]{2}\.zip$")
SHA = re.compile(r"^[0-9a-f]{64}$")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def intake(bundle: Path, dest: Path, master_sha256: str = "") -> dict:
    bundle, dest = Path(bundle), Path(dest)
    if (not bundle.is_file() or bundle.is_symlink() or bundle.suffix != ".zip"
            or bundle.stat().st_size > 1_500_000_000):
        raise CorpusError("missing, symlinked, oversized or non-ZIP input")
    if dest.is_symlink() or (dest.exists() and any(dest.iterdir())):
        raise CorpusError("destination must be new or empty")
    with zipfile.ZipFile(bundle) as archive:
        _safe_zip(archive)
        names = archive.namelist()
        is_master = MASTER in names
    if is_master:
        if not SHA.fullmatch(master_sha256 or ""):
            raise CorpusError("master/shard bundle requires pinned master SHA-256")
        receipt = prepare_bundle(bundle, dest, master_sha256)
        paths = [Path(v) for v in (dest / "INPUT-FILES.txt").read_text().splitlines()]
        routing = load_master_routing(dest / MASTER, master_sha256)
        verify_pinned_shards(dest / MASTER, paths, len(routing))
        # Reject a master that lists IDs absent from the actual original shards.
        observed = set()
        for part in paths:
            for video in iter_videos(part):
                if video.video_id in observed or video.video_id not in routing:
                    raise CorpusError("duplicate or unknown source ID in shard")
                observed.add(video.video_id)
        if observed != set(routing):
            raise CorpusError("master index does not match original shard video IDs")
        kind = "pinned_master_and_shards"
    else:
        if master_sha256:
            raise CorpusError("master SHA provided but source master missing")
        observed = set()
        for video in iter_videos(bundle):
            if video.video_id in observed:
                raise CorpusError("duplicate video ID in owner ZIP")
            observed.add(video.video_id)
            if len(observed) > 25_000:
                raise CorpusError("owner ZIP exceeds 25,000 videos")
        if not observed:
            raise CorpusError("owner ZIP contains no usable video transcripts or metadata")
        dest.mkdir(parents=True, exist_ok=True)
        output = dest / "Owner_Corpus.zip"
        shutil.copyfile(bundle, output)
        paths = [output]
        receipt = {"source_type": "owner_supplied_single_zip"}
        kind = "standalone_zip"
    receipt = {
        "schema_version": "2.0", "scope": "evidence_only",
        "format": kind, "source_sha256": sha256(bundle),
        "master_sha256": master_sha256,
        "videos": len(observed), "batches": (len(observed) + 499) // 500,
        "shards": len(paths), "batch_size": 500,
        "ai_reviewed": 0, "human_verified": 0, "auto_promoted": False,
    }
    (dest / "INPUT-FILES.txt").write_text(
        "".join(str(p.resolve()) + "\n" for p in paths), encoding="utf-8")
    (dest / "INPUT-RECEIPT.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return receipt


def main():
    p = argparse.ArgumentParser(description="Offline owner ZIP intake; never connects to YouTube")
    p.add_argument("--zip", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--master-sha256", default="")
    args = p.parse_args()
    try:
        print(json.dumps(intake(args.zip, args.out, args.master_sha256), sort_keys=True))
    except (CorpusError, OSError, zipfile.BadZipFile, ValueError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
