"""Synthetic regression coverage for ZIP-only intake and source comparison."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from knowledge_analysis.corpus import CorpusError
from scripts.intake import intake
from scripts.compare import compare_claims


def make_zip(path):
    text = "Forms must have accessible labels and useful keyboard navigation."
    row = {
        "_record_type": "youtube_video",
        "video_id": "ABCDEFGHIJK",
        "title": "Synthetic testing video", "channel": "Synthetic evidence",
        "transcript": text,
        "transcript_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "comments": ["Example saved comment"], "comments_status": "ok",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("records.jsonl", json.dumps(row) + "\n")


class OwnerZipTests(unittest.TestCase):
    def test_generic_owner_zip_reads_inventory_without_model_claim(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "YouTube_Kennisbron_Bundle.zip"
            make_zip(source)
            result = intake(source, root / "validated")
            self.assertEqual(result["videos"], 1)
            self.assertEqual(result["batches"], 1)
            self.assertEqual(result["ai_reviewed"], 0)
            self.assertFalse(result["auto_promoted"])
            self.assertTrue((root / "validated" / "Owner_Corpus.zip").is_file())

    def test_wrong_master_sha_for_standalone_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "source.zip"
            make_zip(source)
            with self.assertRaisesRegex(CorpusError, "master SHA provided"):
                intake(source, root / "validated", "a"*64)

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "source.zip"
            make_zip(source)
            target = root / "validated"
            target.mkdir()
            (target / "existing.txt").write_text("untouched")
            with self.assertRaisesRegex(CorpusError, "destination must be"):
                intake(source, target)
            self.assertEqual((target / "existing.txt").read_text(), "untouched")

    def test_compare_is_never_automatic_knowledge_promotion(self):
        ledger = {"scope": "evidence_only", "auto_promoted": False,
                  "claims": [{
                      "claim_id": "a"*64, "video_id": "ABCDEFGHIJK",
                      "claim": "Accessible form labels allow better keyboard navigation.",
                      "quote": "Accessible form labels"
                  }]}
        report = compare_claims(ledger, None)
        self.assertEqual(report["proposals"][0]["proposed_category"],
                         "NEEDS_VERIFICATION")
        self.assertFalse(report["auto_promoted"])
        self.assertFalse(report["human_qa_approved"])

    def test_matching_source_stays_unverified(self):
        ledger = {"scope": "evidence_only", "auto_promoted": False,
                  "claims": [{
                      "claim_id": "a"*64, "video_id": "ABCDEFGHIJK",
                      "claim": "Accessible form labels allow better keyboard navigation.",
                      "quote": "Accessible form labels"
                  }]}
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "project_sources.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("design/current.md",
                     "Accessible form labels allow better keyboard navigation. ")
            result = compare_claims(ledger, source)
            self.assertEqual(result["claim_count"], 1)
            self.assertFalse(result["snapshot_currentness_verified"])
            self.assertFalse(result["proposals"][0]["official_source_verified"])


if __name__ == "__main__":
    unittest.main()
