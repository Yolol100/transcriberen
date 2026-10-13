#!/usr/bin/env python3
"""Validate a single owner-supplied ZIP containing a complete historical corpus.

Input is a ZIP of ZIP files: one YouTube_Kennisbron_Master.zip and the exact
YouTube_Kennisbron_Master.part-NN.zip shard set. Does not contact YouTube,
publish source bytes, call AI services or change canonical project sources.

A master ZIP by itself is metadata only and MUST NOT be called a full corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_analysis.corpus import CorpusError, _safe_zip
from knowledge_analysis.routing import load_master_routing, verify_pinned_shards

MASTER = "YouTube_Kennisbron_Master.zip"
PART = re.compile(r"^YouTube_Kennisbron_Master\.part-[0-9]{2}\.zip$")
SHA = re.compile(r"^[a-f0-9]{64}$")
MAX_BUNDLE_BYTES = 1_500_000_000


def prepare_bundle(bundle: Path, dest: Path, pinned_master_sha256: str) -> dict:
    """Read exact ZIP membership; fail closed; move only validated files into dest."""
    if not isinstance(pinned_master_sha256, str) or not SHA.fullmatch(pinned_master_sha256):
        raise CorpusError("a 64-digit authorized master SHA-256 is required")
    if (not bundle.is_file() or bundle.is_symlink()
            or bundle.stat().st_size > MAX_BUNDLE_BYTES):
        raise CorpusError("owner-supplied bundle missing or oversized")
    if dest.is_symlink():
        raise CorpusError("destination may not be a symlink")
    dest.mkdir(parents=True, exist_ok=True)
    if not dest.is_dir():
        raise CorpusError("destination is not a directory")
    if (dest / "INPUT-FILES.txt").exists() or (dest / "INPUT-RECEIPT.json").exists():
        raise CorpusError("destination already contains another corpus input")
    try:
        with zipfile.ZipFile(bundle) as outer:
            _safe_zip(outer)
            items = {x.filename: x for x in outer.infolist()}
            members = set(items)
            shards = sorted(x for x in members if PART.fullmatch(x))
            if MASTER not in members or not shards or len(shards) > 99:
                raise CorpusError("single ZIP needs a master index and its transcript shards")
            if members != {MASTER, *shards}:
                raise CorpusError("unexpected member in owner-supplied corpus bundle")
            if any(x.is_dir() for x in outer.infolist()):
                raise CorpusError("bundle contains unexpected directory member")
            for name in members:
                if items[name].file_size == 0:
                    raise CorpusError("empty ZIP member in owner-supplied corpus bundle")
            with tempfile.TemporaryDirectory(prefix="validated-owner-bundle-", dir=dest) as tmp:
                staging = Path(tmp)
                for name in [MASTER, *shards]:
                    with outer.open(name) as src, (staging / name).open("xb") as target:
                        shutil.copyfileobj(src, target, length=1024 * 1024)
                routing = load_master_routing(staging / MASTER, pinned_master_sha256)
                paths = [staging / name for name in shards]
                verify_pinned_shards(staging / MASTER, paths, len(routing))
                for name in [MASTER, *shards]:
                    if (dest / name).exists() or (dest / name).is_symlink():
                        raise CorpusError("refuse to overwrite existing source file: " + name)
                for name in [MASTER, *shards]:
                    (staging / name).rename(dest / name)
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise CorpusError("invalid or unreadable supplied ZIP bundle") from exc
    selected = [dest / name for name in shards]
    (dest / "INPUT-FILES.txt").write_text(
        "".join(str(path) + "\n" for path in selected), encoding="utf-8")
    receipt = {
        "schema_version": "1.0", "scope": "evidence_only",
        "source_type": "owner_supplied_single_zip",
        "master_sha256": pinned_master_sha256,
        "unique_video_ids": len(routing), "shard_count": len(shards),
        "batch_size": 500, "batch_count": (len(routing) + 499) // 500,
        "sources_complete_by_master_manifest": True,
        "ai_reviewed_videos": 0, "human_verified_videos": 0,
        "project_sources_updated": False, "skill_sources_updated": False,
    }
    (dest / "INPUT-RECEIPT.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a validated master+shards single ZIP for offline 500-video review")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--master-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_bundle(args.bundle, args.dest, args.master_sha256),
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CorpusError, ValueError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
