"""Source-bound, negative-first proof before a next 500-video batch starts."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from knowledge_analysis.corpus import iter_videos
from knowledge_analysis.review import review_video, STATUS_COMPLETE
from scripts import chain, knowledge_analyze


class FakeModel:
    def ask(self, source, text, metadata):
        return {"claims": [], "uncertainty": "synthetic evidence"}


class VerifiedBatchCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.model = self.root / "synthetic.gguf"
        self.model.write_bytes(b"synthetic model hash input, not Qwen weights")
        self.model_sha = hashlib.sha256(self.model.read_bytes()).hexdigest()
        self.source = self.root / "Corpus.zip"
        self.videos = []
        for i in range(22):
            vid = f"V{i:010d}"
            text = f"Synthetic accessible content for review {vid}. " * 15
            row = {"_record_type": "youtube_video", "video_id": vid,
                   "title": f"Synthetic {i}", "channel": "Synthetic",
                   "published_date": "20261013", "transcript": text,
                   "transcript_sha256": hashlib.sha256(text.encode()).hexdigest(),
                   "comments": [f"Saved synthetic community comment {i}."],
                   "comments_status": "ok"}
            self.videos.append(row)
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("videos.jsonl", "\n".join(json.dumps(v) for v in self.videos) + "\n")
        self.raw = {v.video_id: v for v in iter_videos(self.source)}
        self.plan = self._inventory(0, "plan")

    def _inventory(self, slice_index, folder):
        result_dir = self.root / folder
        args = ["knowledge_analyze.py", "--source", str(self.source),
                "--mode", "inventory", "--batch", "1", "--slice", str(slice_index),
                "--slice-size", "20", "--output-dir", str(result_dir)]
        with patch.object(sys, "argv", args), redirect_stdout(io.StringIO()):
            self.assertEqual(knowledge_analyze.main(), 0)
        return json.loads((result_dir / "inventory.json").read_text())

    def _completed(self, index):
        tag = f"slice-{index}"
        inv = self._inventory(index, tag)
        root = self.root / tag
        for vid in inv["selected_video_ids"]:
            review = review_video(self.raw[vid], model=FakeModel(), model_sha256=self.model_sha,
                                  out_dir=root, chunk_size=5600)
            self.assertEqual(review["status"], STATUS_COMPLETE)
        inv.update({"status": "evidence_only_pending_external_qa",
                    "model_sha256": self.model_sha,
                    "statuses": {STATUS_COMPLETE: len(inv["selected_video_ids"])},
                    "ai_reviewed_videos": len(inv["selected_video_ids"])})
        (root / "inventory.json").write_text(json.dumps(inv))
        return root

    def _verify(self, roots):
        return chain.verified_advance(self.plan, 1, sources=[self.source],
                                      review_dirs=roots, model_path=self.model)

    def test_two_slices_complete_all_22_reviews_and_44_chunks(self):
        roots = [self._completed(0), self._completed(1)]
        report = self._verify(roots)
        self.assertTrue(report["completion_verified"])
        self.assertEqual(report["verified_review_videos"], 22)
        self.assertEqual(report["verified_model_chunks"], 44)
        self.assertTrue(report["terminal"])
        self.assertEqual(report["transport_status"], "not_dispatched_requires_private_transport")

    def test_partial_slice_cannot_advance_even_if_other_slice_is_done(self):
        root = self._completed(0)
        with self.assertRaisesRegex(chain.ChainError, "missing slices"):
            self._verify([root])

    def test_missing_video_json_blocks_completion(self):
        root, other = self._completed(0), self._completed(1)
        (root / "videos" / (self.videos[0]["video_id"] + ".json")).unlink()
        with self.assertRaisesRegex(chain.ChainError, "missing, duplicate or extra"):
            self._verify([root, other])

    def test_damaged_comment_chunk_is_detected_using_original_source(self):
        root, other = self._completed(0), self._completed(1)
        path = root / "videos" / (self.videos[0]["video_id"] + ".json")
        record = json.loads(path.read_text())
        record["chunks"][1]["sha256"] = "0" * 64
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(chain.ChainError, "altered video review"):
            self._verify([root, other])

    def test_forged_success_receipt_without_source_chunks_fails(self):
        root, other = self._completed(0), self._completed(1)
        path = root / "videos" / (self.videos[0]["video_id"] + ".json")
        record = json.loads(path.read_text())
        record["chunks"] = []
        record["transcript_read_completely"] = True
        record["comments_read_completely"] = True
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(chain.ChainError, "altered video review"):
            self._verify([root, other])

    def test_duplicate_slice_is_rejected(self):
        root = self._completed(0)
        with self.assertRaisesRegex(chain.ChainError, "duplicate slice"):
            self._verify([root, root])

    def test_different_model_hash_blocks_reused_evidence(self):
        root, other = self._completed(0), self._completed(1)
        self.model.write_bytes(b"different GGUF bytes")
        with self.assertRaisesRegex(chain.ChainError, "model-review counter mismatch|slice receipt does not match"):
            self._verify([root, other])

    def test_mutated_source_bytes_fail_before_model_review_is_trusted(self):
        root, other = self._completed(0), self._completed(1)
        with self.source.open("ab") as file:
            file.write(b"x")
        with self.assertRaisesRegex(chain.ChainError, "source hashes differ"):
            self._verify([root, other])

    def test_wrong_or_partial_status_blocks_automatic_next_batch(self):
        root, other = self._completed(0), self._completed(1)
        path = root / "inventory.json"
        inv = json.loads(path.read_text())
        inv["status"] = "blocked_time_budget"
        path.write_text(json.dumps(inv))
        with self.assertRaisesRegex(chain.ChainError, "slice receipt does not match"):
            self._verify([root, other])

    def test_cli_all_scope_refuses_inventory_only_progression(self):
        path = self.root / "plan" / "inventory.json"
        args = ["chain.py", "--inventory", str(path), "--batch", "1", "--scope", "all"]
        with patch.object(sys, "argv", args), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(chain.main(), 2)


if __name__ == "__main__":
    unittest.main()