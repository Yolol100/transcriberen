"""Volume regression for the existing 500-video/20-video review layout.

Uses entirely fabricated video IDs, titles and empty captions. This is NOT the
18,875-video Library corpus and does not authorize a public source release.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch
import sys
import tempfile
import unittest
import zipfile

from knowledge_analysis.corpus import CorpusError
from scripts import knowledge_analyze


TOTAL = 18_875
PARTS = 15
BATCH = 500
SLICE = 20
MASTER_NAME = "YouTube_Kennisbron_Master.zip"
ROUTING_NAME = "YouTube_Video_Routing_Index_2026-10-03.csv"
MANIFEST_NAME = "YouTube_Kennisbron_Shards_2026-10-03.json"


def fake_id(n: int) -> str:
    return f"V{n:010d}"


class FullSizeSyntheticPlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.sources = []
        shard_receipts = []
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("video_id", "channel", "title", "date",
                         "domain_routes", "source_authority",
                         "authority_status", "comment_count"))
        empty_digest = hashlib.sha256(b"").hexdigest()
        cursor = 0
        for part in range(1, PARTS + 1):
            count = 1250 if part < PARTS else TOTAL - cursor
            self_rows = []
            for i in range(cursor, cursor + count):
                vid = fake_id(i)
                title = f"Artificial test video {i}"
                writer.writerow((vid, "Synthetic channel", title, "2026-10-03",
                                 "design", "expert_creator", "verified", "0"))
                self_rows.append(json.dumps({
                    "_record_type": "youtube_video",
                    "video_id": vid, "title": title, "channel": "Synthetic channel",
                    "published_date": "20261003", "domain_routes": ["design"],
                    "source_authority": "expert_creator",
                    "transcript": "", "transcript_sha256": empty_digest,
                    "comments": [], "comments_status": "unknown",
                }, separators=(",", ":")))
            filename = f"YouTube_Kennisbron_Master.part-{part:02d}.zip"
            path = cls.root / filename
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("synthetic-records.jsonl", "\n".join(self_rows) + "\n")
            data = path.read_bytes()
            cls.sources.append(path)
            shard_receipts.append({
                "part": part, "filename": filename, "record_count": count,
                "zip_size_bytes": len(data),
                "zip_sha256": hashlib.sha256(data).hexdigest(),
            })
            cursor += count
        assert cursor == TOTAL
        cls.master = cls.root / MASTER_NAME
        with zipfile.ZipFile(cls.master, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(ROUTING_NAME, output.getvalue())
            archive.writestr(MANIFEST_NAME, json.dumps({
                "record_count_total": TOTAL, "parts": shard_receipts,
            }, separators=(",", ":")))
        cls.master_sha256 = hashlib.sha256(cls.master.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def inventory(self, batch: int, slice_index: int, output_tag: str):
        out = self.root / output_tag
        argv = [
            "knowledge_analyze.py", "--source", *(str(p) for p in self.sources),
            "--master-routing", str(self.master),
            "--master-sha256", self.master_sha256,
            "--mode", "inventory", "--batch", str(batch),
            "--slice", str(slice_index), "--slice-size", str(SLICE),
            "--output-dir", str(out),
        ]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            rc = knowledge_analyze.main()
        self.assertEqual(rc, 0)
        result = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(result["total_unique_videos_in_supplied_corpus"], TOTAL)
        self.assertEqual(result["master_routing_sha256"], self.master_sha256)
        self.assertEqual(len(result["source_files"]), PARTS)
        self.assertEqual(result["status"], "inventory_only")
        self.assertFalse(result["source_partial"])
        return result

    def test_first_mid_and_last_slice_exact_id_boundaries(self):
        scenarios = (
            (1, 0, 0, 19, 500),
            (1, 24, 480, 499, 500),
            (37, 24, 18_480, 18_499, 500),
            (38, 0, 18_500, 18_519, 375),
            (38, 18, 18_860, 18_874, 375),
        )
        for batch, slice_index, first, last, count in scenarios:
            with self.subTest(batch=batch, slice=slice_index):
                inventory = self.inventory(batch, slice_index,
                                           f"batch-{batch}-slice-{slice_index}")
                self.assertEqual(inventory["actual_batch_count"], count)
                self.assertEqual(inventory["selected_video_ids"],
                                 [fake_id(i) for i in range(first, last + 1)])

    def test_38_batches_cover_synthetic_inventory_without_gaps_or_duplicates(self):
        # Independently calculate the full accepted logical partition for
        # every batch/slice; the CLI samples the real parser at boundaries.
        spans = []
        for batch in range(1, 39):
            start = (batch - 1) * BATCH
            end = min(TOTAL, start + BATCH)
            for offset in range(start, end, SLICE):
                spans.append((offset, min(end, offset + SLICE)))
        self.assertEqual(len(spans), (37 * 25) + 19)
        self.assertEqual(sum(b - a for a, b in spans), TOTAL)
        self.assertEqual(spans[0], (0, 20))
        self.assertEqual(spans[-1], (18_860, 18_875))
        self.assertTrue(all(left[1] == right[0]
                            for left, right in zip(spans, spans[1:])))
        self.assertEqual((spans[-1][1] - spans[-1][0]), 15)

    def test_out_of_range_last_slice_and_39th_batch_fail_closed(self):
        for batch, slice_index, error in (
            (38, 19, "selected slice outside selected batch"),
            (39, 0, "selected batch outside supplied corpus"),
        ):
            with self.subTest(batch=batch, slice=slice_index):
                argv = [
                    "knowledge_analyze.py", "--source", *(str(p) for p in self.sources),
                    "--master-routing", str(self.master),
                    "--master-sha256", self.master_sha256,
                    "--mode", "inventory", "--batch", str(batch),
                    "--slice", str(slice_index),
                    "--output-dir", str(self.root / f"invalid-{batch}-{slice_index}"),
                ]
                with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(CorpusError, error):
                        knowledge_analyze.main()


if __name__ == "__main__":
    unittest.main()
