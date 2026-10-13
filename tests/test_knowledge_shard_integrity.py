"""Synthetic verification of exact historical shard files before AI review."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from knowledge_analysis.corpus import CorpusError
from knowledge_analysis.routing import verify_pinned_shards


SHARD_NAME = "YouTube_Kennisbron_Master.part-01.zip"
MANIFEST_NAME = "YouTube_Kennisbron_Shards_2026-10-03.json"


def make_case(folder: Path):
    shard = folder / SHARD_NAME
    with zipfile.ZipFile(shard, "w") as archive:
        archive.writestr("fixture.jsonl", '{"_record_type":"youtube_video","video_id":"ABCDEFGHIJK"}\n')
    data = shard.read_bytes()
    manifest = {"schema_version": "1.2", "record_count_total": 1, "parts": [
        {"part": 1, "record_count": 1, "filename": SHARD_NAME,
         "zip_size_bytes": len(data), "zip_sha256": hashlib.sha256(data).hexdigest()}
    ]}
    master = folder / "YouTube_Kennisbron_Master.zip"
    write_manifest(master, manifest)
    return master, shard, manifest


def write_manifest(path, manifest):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest))


class PinnedShardsTests(unittest.TestCase):
    def test_exact_files_and_hashes_succeed(self):
        with tempfile.TemporaryDirectory() as directory:
            master, shard, _ = make_case(Path(directory))
            verify_pinned_shards(master, [shard], 1)

    def test_same_size_tampered_shard_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            master, shard, _ = make_case(Path(directory))
            data = bytearray(shard.read_bytes())
            data[12] ^= 1
            shard.write_bytes(data)
            with self.assertRaisesRegex(CorpusError, "ZIP SHA-256 mismatch"):
                verify_pinned_shards(master, [shard], 1)

    def test_missing_or_extra_shards_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            master, shard, _ = make_case(folder)
            with self.assertRaisesRegex(CorpusError, "shard set differs"):
                verify_pinned_shards(master, [], 1)
            extra = folder / "YouTube_Kennisbron_Master.part-02.zip"
            extra.write_bytes(shard.read_bytes())
            with self.assertRaisesRegex(CorpusError, "shard set differs"):
                verify_pinned_shards(master, [shard, extra], 1)

    def test_missing_shard_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            master, shard, _ = make_case(Path(directory))
            with zipfile.ZipFile(master, "w") as archive:
                archive.writestr("other.json", "{}")
            with self.assertRaisesRegex(CorpusError, "requires one bounded shard manifest"):
                verify_pinned_shards(master, [shard], 1)

    def test_master_count_inconsistent_with_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            master, shard, _ = make_case(Path(directory))
            with self.assertRaisesRegex(CorpusError, "video total mismatch"):
                verify_pinned_shards(master, [shard], 2)

    def test_invalid_shard_manifest_sha_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            master, shard, manifest = make_case(Path(directory))
            manifest["parts"][0]["zip_sha256"] = "0" * 64
            write_manifest(master, manifest)
            with self.assertRaisesRegex(CorpusError, "ZIP SHA-256 mismatch"):
                verify_pinned_shards(master, [shard], 1)

    def test_corrupt_part_numbers_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            master, shard, manifest = make_case(Path(directory))
            manifest["parts"][0]["part"] = 2
            write_manifest(master, manifest)
            with self.assertRaisesRegex(CorpusError, "invalid master shard metadata"):
                verify_pinned_shards(master, [shard], 1)


if __name__ == "__main__":
    unittest.main()
