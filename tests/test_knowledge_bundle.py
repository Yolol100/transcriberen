"""Single owner-supplied ZIP normalization; only synthetic evidence in CI."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from knowledge_analysis.corpus import CorpusError
from scripts.knowledge_bundle import prepare_bundle


MASTER = "YouTube_Kennisbron_Master.zip"
INDEX = "YouTube_Video_Routing_Index_2026-10-03.csv"
MANIFEST = "YouTube_Kennisbron_Shards_2026-10-03.json"
ROOT = Path(__file__).resolve().parents[1]


def make_owner_zip(folder: Path):
    names = []
    receipts = []
    csv_buffer = io.StringIO(newline="")
    writer = csv.writer(csv_buffer)
    writer.writerow(("video_id", "channel", "title", "date", "domain_routes",
                     "source_authority", "authority_status", "comment_count"))
    for part in (1, 2):
        vid = f"VID{part:08d}"
        name = f"YouTube_Kennisbron_Master.part-{part:02d}.zip"
        writer.writerow((vid, "SampleChannel", f"Example {part}", "2026-10-13",
                         "design", "expert_creator", "verified", "0"))
        row = {"_record_type": "youtube_video", "video_id": vid,
               "channel": "SampleChannel", "title": f"Example {part}",
               "published_date": "20261013", "source_authority": "expert_creator",
               "domain_routes": ["design"], "transcript": "Sample transcript.",
               "transcript_sha256": hashlib.sha256(b"Sample transcript.").hexdigest(),
               "comments": [], "comments_status": "unknown"}
        shard = folder / name
        with zipfile.ZipFile(shard, "w") as archive:
            archive.writestr("records.jsonl", json.dumps(row) + "\n")
        data = shard.read_bytes()
        receipts.append({"part": part, "filename": name, "zip_size_bytes": len(data),
                         "zip_sha256": hashlib.sha256(data).hexdigest(), "record_count": 1})
        names.append(name)
    master = folder / MASTER
    with zipfile.ZipFile(master, "w") as archive:
        archive.writestr(INDEX, csv_buffer.getvalue())
        archive.writestr(MANIFEST, json.dumps({"record_count_total": 2, "parts": receipts}))
    digest = hashlib.sha256(master.read_bytes()).hexdigest()
    bundle = folder / "YouTube_Kennisbron_Bundle.zip"
    pack(bundle, folder, [MASTER, *names])
    return bundle, digest, names


def pack(bundle: Path, folder: Path, names):
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in names:
            archive.write(folder / name, arcname=name)


class OwnerBundleTests(unittest.TestCase):
    def test_single_zip_from_chat_style_bundle_is_complete_and_reviewable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, digest, _ = make_owner_zip(root)
            dest = root / "prepared"
            receipt = prepare_bundle(bundle, dest, digest)
            self.assertEqual(receipt["unique_video_ids"], 2)
            self.assertEqual(receipt["shard_count"], 2)
            self.assertEqual(receipt["batch_count"], 1)
            self.assertEqual(receipt["ai_reviewed_videos"], 0)
            self.assertFalse(receipt["project_sources_updated"])
            inputs = [Path(x) for x in (dest / "INPUT-FILES.txt").read_text().splitlines()]
            self.assertEqual(len(inputs), 2)
            self.assertEqual(inputs[0].name, "YouTube_Kennisbron_Master.part-01.zip")
            proc = subprocess.run([
                sys.executable, str(ROOT / "scripts" / "knowledge_analyze.py"),
                "--source", *(str(x) for x in inputs),
                "--master-routing", str(dest / MASTER), "--master-sha256", digest,
                "--mode", "inventory", "--batch", "1", "--slice", "0",
                "--output-dir", str(root / "inventory")
            ], capture_output=True, text=True, timeout=25)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            inventory = json.loads((root / "inventory" / "inventory.json").read_text())
            self.assertEqual(inventory["total_unique_videos_in_supplied_corpus"], 2)
            self.assertEqual(inventory["selected_video_ids"], ["VID00000001", "VID00000002"])
            self.assertEqual(inventory["status"], "inventory_only")

    def test_master_index_without_transcripts_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            _, digest, _ = make_owner_zip(folder)
            solo = folder / "index-only.zip"
            pack(solo, folder, [MASTER])
            with self.assertRaisesRegex(CorpusError, "needs a master index and its transcript shards"):
                prepare_bundle(solo, folder / "output", digest)

    def test_extra_archive_member_and_zip_slip_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            _, digest, names = make_owner_zip(folder)
            extra = folder / "extra.zip"
            with zipfile.ZipFile(extra, "w") as archive:
                for name in [MASTER, *names]:
                    archive.write(folder / name, arcname=name)
                archive.writestr("unused.txt", "Do not silently accept arbitrary files")
            with self.assertRaisesRegex(CorpusError, "unexpected member"):
                prepare_bundle(extra, folder / "extra-out", digest)
            escape = folder / "escape.zip"
            with zipfile.ZipFile(escape, "w") as archive:
                archive.writestr("../escape.txt", "bad")
            with self.assertRaisesRegex(CorpusError, "unsafe archive"):
                prepare_bundle(escape, folder / "escape-out", digest)

    def test_modified_archive_or_master_hash_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            bundle, digest, names = make_owner_zip(folder)
            with self.assertRaisesRegex(CorpusError, "master routing ZIP SHA-256 mismatch"):
                prepare_bundle(bundle, folder / "wrong-hash", "0" * 64)
            # Repack after changing a shard while retaining the original master.
            with (folder / names[1]).open("ab") as stream:
                stream.write(b"changed")
            modified = folder / "modified.zip"
            pack(modified, folder, [MASTER, *names])
            with self.assertRaisesRegex(CorpusError, "SHA-256 mismatch|wrong size"):
                prepare_bundle(modified, folder / "modified-out", digest)

    def test_missing_shard_is_rejected_by_pinned_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            _, digest, names = make_owner_zip(folder)
            missing = folder / "missing.zip"
            pack(missing, folder, [MASTER, names[0]])
            with self.assertRaisesRegex(CorpusError, "shard set differs"):
                prepare_bundle(missing, folder / "missing-out", digest)

    def test_extraction_refuses_to_overwrite_existing_source_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            bundle, digest, _ = make_owner_zip(folder)
            output = folder / "output"
            output.mkdir()
            (output / MASTER).write_bytes(b"existing master")
            with self.assertRaisesRegex(CorpusError, "refuse to overwrite"):
                prepare_bundle(bundle, output, digest)
            self.assertEqual((output / MASTER).read_bytes(), b"existing master")

    def test_duplicate_zip_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            bundle, digest, names = make_owner_zip(folder)
            duplicate = folder / "duplicate.zip"
            with zipfile.ZipFile(duplicate, "w") as archive:
                archive.write(folder / MASTER, arcname=MASTER)
                for name in names:
                    archive.write(folder / name, arcname=name)
                with __import__("warnings").catch_warnings():
                    __import__("warnings").simplefilter("ignore", UserWarning)
                    archive.write(folder / names[0], arcname=names[0])
            with self.assertRaisesRegex(CorpusError, "duplicate archive member"):
                prepare_bundle(duplicate, folder / "duplicate-out", digest)


if __name__ == "__main__":
    unittest.main()
