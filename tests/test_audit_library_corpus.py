"""Synthetic tests for exhaustive, privacy-safe local video coverage accounting."""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.audit_library_corpus import AuditError, audit


class LibraryCorpusAuditTests(unittest.TestCase):
    def make_corpus(self, root, comment_count=0, listed_hash=None, duplicate=False,
                    comment_text="a practical question"):
        root = Path(root)
        master = root / "master.zip"
        shard = root / "part-01.zip"
        video = {"_record_type": "youtube_video", "video_id": "abcdefghijk",
                 "channel": "Example", "transcript": "source data",
                 "comments": [{"text": comment_text}] if comment_count else []}
        data = [video, video] if duplicate else [video]
        with zipfile.ZipFile(shard, "w") as z:
            z.writestr("part-01.jsonl", "\n".join(json.dumps(r) for r in data) + "\n")
        sha = hashlib.sha256(shard.read_bytes()).hexdigest()
        part = {"filename": shard.name, "zip_sha256": listed_hash or sha,
                "record_count": len(data)}
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=[
            "video_id", "comment_count", "domain_routes"])
        writer.writeheader()
        writer.writerow({"video_id": video["video_id"],
                         "comment_count": comment_count, "domain_routes": "seo"})
        with zipfile.ZipFile(master, "w") as z:
            z.writestr("YouTube_Kennisbron_Shards_2026-10-03.json",
                       json.dumps({"record_count_total": 1, "parts": [part]}))
            z.writestr("YouTube_Video_Routing_Index_2026-10-03.csv", buffer.getvalue())
            z.writestr("YouTube_Source_Catalog_2026-10-03.json",
                       json.dumps({"channels": {"Example": {
                           "authority_status": "verified"}}}))
        return master

    def test_complete_local_inventory_does_not_claim_live_comment_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            master = self.make_corpus(d)
            result = audit(master, Path(d), Path(d) / "out")
            self.assertEqual(result["index_coverage_pct"], 100.0)
            self.assertEqual(result["videos_without_saved_top_level_comments"], 1)
            self.assertIsNone(result["live_youtube_comment_coverage_pct"])
            self.assertEqual(result["live_youtube_comment_check_status"], "not_attempted")
            with (Path(d) / "out" / "video_coverage.csv").open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["live_comment_availability"], "not_checked")

    def test_saved_comment_is_not_live_complete_claim(self):
        with tempfile.TemporaryDirectory() as d:
            master = self.make_corpus(d, comment_count=1)
            result = audit(master, Path(d), Path(d) / "out")
            self.assertEqual(result["stored_top_level_comments"], 1)
            self.assertIsNone(result["live_youtube_comment_coverage_pct"])

    def test_reject_blank_saved_comment(self):
        with tempfile.TemporaryDirectory() as d:
            master = self.make_corpus(d, comment_count=1, comment_text="  ")
            with self.assertRaisesRegex(AuditError, "invalid saved comment"):
                audit(master, Path(d), Path(d) / "out")

    def test_reject_wrong_master_sha(self):
        with tempfile.TemporaryDirectory() as d:
            master = self.make_corpus(d)
            with self.assertRaisesRegex(AuditError, "master checksum"):
                audit(master, Path(d), Path(d) / "out",
                      expected_master_sha256="f" * 64)

    def test_reject_modified_shard(self):
        with tempfile.TemporaryDirectory() as d:
            master = self.make_corpus(d, listed_hash="f" * 64)
            with self.assertRaisesRegex(AuditError, "checksum"):
                audit(master, Path(d), Path(d) / "out")

    def test_reject_duplicate_video_ids(self):
        with tempfile.TemporaryDirectory() as d:
            master = self.make_corpus(d, duplicate=True)
            with self.assertRaisesRegex(AuditError, "duplicate video ID"):
                audit(master, Path(d), Path(d) / "out")

    def test_missing_shard_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            master = self.make_corpus(d)
            (Path(d) / "part-01.zip").unlink()
            with self.assertRaisesRegex(AuditError, "missing required shard"):
                audit(master, Path(d), Path(d) / "out")


if __name__ == "__main__":
    unittest.main()
