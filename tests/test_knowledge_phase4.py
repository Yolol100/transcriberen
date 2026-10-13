"""Phase 4 categorization is evidence-only and never a knowledge write."""
import tempfile
from pathlib import Path
import json
import subprocess
import sys
import unittest

from knowledge_analysis.phase4 import Phase4Error, triage
from knowledge_analysis.review import POLICY_VERSION, STATUS_COMPLETE, STATUS_SOURCE_WARNING, STATUS_NO_TRANSCRIPT_COMMENTS


def fixture():
    quote = "Theme JSON supports documented styles and settings."
    return {
        "schema_version": "1.0", "policy_version": POLICY_VERSION,
        "signature": "a" * 64, "video_id": "ABCDEFGHIJK",
        "model_sha256": "b" * 64, "transcript_sha256": "c" * 64,
        "status": STATUS_COMPLETE, "source_integrity_warning": False,
        "transcript_hash_status": "match",
        "auto_promoted": False, "human_qa_approved": False,
        "project_source_compared": False, "primary_sources_verified": False,
        "transcript_read_completely": True, "comments_read_completely": True,
        "comments_status": "unknown",
        "transcript_characters": 240,
        "transcript_chunks_expected": 1, "comment_chunks_expected": 0,
        "comment_count": 0, "rejected_unanchored_claims": 0,
        "chunks": [{"source": "transcript", "comment_index": None,
                    "start": 0, "end": 240, "sha256": "e" * 64,
                    "model_result": "parsed_and_checked", "valid_claims": 1,
                    "rejected_claims": 0}],
        "claims": [{
            "claim": "Theme JSON supports documented style and setting controls.",
            "quote": quote, "source": "transcript",
            "evidence_start": 120, "evidence_end": 120 + len(quote),
            "owner_candidate": "wordpressqualityarchitect",
            "kind": "fact", "evidence_only": True,
            "needs_current_verification": True,
        }],
    }


def proposed(category, claim_id):
    return {"claim_id": claim_id, "category": category,
            "rationale": "Compared with current official guidance and active project source baseline.",
            "owner": "wordpressqualityarchitect",
            "project_source_id": "project-plugin/10-wordpress-core",
            "project_source_sha256": "d" * 64,
            "official_source_url": "https://developer.wordpress.org/block-editor/",
            "official_checked_at": "2026-10-13"}


class Phase4Tests(unittest.TestCase):
    def test_unclassified_real_claim_is_pending_not_promotion(self):
        report = triage([fixture()])
        self.assertEqual(report["claim_count"], 1)
        self.assertEqual(report["proposed_category_counts"], {"NEEDS_VERIFICATION": 1})
        self.assertEqual(report["claims"][0]["proposed_category"], "NEEDS_VERIFICATION")
        self.assertFalse(report["human_qa_approved"])
        self.assertFalse(report["auto_promoted"])
        self.assertFalse(report["external_project_sources_fetched"])
        self.assertFalse(report["source_quote_rechecked_against_raw_transcript"])

    def test_update_proposal_remains_pending_external_owner_qa(self):
        original = triage([fixture()])
        key = original["claims"][0]["claim_id"]
        report = triage([fixture()], [proposed("UPDATE", key)])
        item = report["claims"][0]
        self.assertEqual(item["proposed_category"], "UPDATE")
        self.assertEqual(item["acceptance"], "pending_independent_owner_and_source_verification")
        self.assertEqual(report["proposed_category_counts"], {"UPDATE": 1})
        self.assertFalse(item["auto_promoted"])
        self.assertFalse(report["human_qa_approved"])

    def test_already_covered_requires_project_source_hash(self):
        key = triage([fixture()])["claims"][0]["claim_id"]
        decision = proposed("ALREADY_COVERED", key)
        report = triage([fixture()], [decision])
        self.assertEqual(report["claims"][0]["proposed_category"], "ALREADY_COVERED")
        del decision["project_source_sha256"]
        with self.assertRaisesRegex(Phase4Error, "pinned project-source hash"):
            triage([fixture()], [decision])

    def test_rejected_candidate_requires_substantive_rationale(self):
        key = triage([fixture()])["claims"][0]["claim_id"]
        decision = {"claim_id": key, "category": "REJECTED",
                    "rationale": "Source excerpt is a mistaken vendor-name match, not plugin advice."}
        self.assertEqual(triage([fixture()], [decision])["proposed_category_counts"],
                         {"REJECTED": 1})
        decision["rationale"] = "No"
        with self.assertRaisesRegex(Phase4Error, "specific rationale"):
            triage([fixture()], [decision])

    def test_owner_project_and_official_necessary_for_update(self):
        key = triage([fixture()])["claims"][0]["claim_id"]
        for field, value in [
            ("owner", "unknown"),
            ("project_source_sha256", "not-a-hash"),
            ("official_source_url", "http://127.0.0.1:8080/"),
            ("official_checked_at", "2099-01-01")
        ]:
            candidate = proposed("UPDATE", key)
            candidate[field] = value
            with self.subTest(field=field), self.assertRaises(Phase4Error):
                triage([fixture()], [candidate])

    def test_false_automatic_promotion_from_source_is_rejected(self):
        video = fixture()
        video["human_qa_approved"] = True
        with self.assertRaisesRegex(Phase4Error, "external verification"):
            triage([video])
        video = fixture()
        video["auto_promoted"] = True
        with self.assertRaisesRegex(Phase4Error, "external verification"):
            triage([video])

    def test_comment_cannot_impersonate_creator(self):
        video = fixture()
        video["claims"][0]["source"] = "comment"
        video["claims"][0]["comment_index"] = 0
        video["claims"][0]["creator_attribution"] = True
        video["chunks"][0]["source"] = "comment"
        video["chunks"][0]["comment_index"] = 0
        video["transcript_characters"] = 0
        video["transcript_chunks_expected"] = 0
        video["comment_chunks_expected"] = 1
        video["comment_count"] = 1
        video["status"] = STATUS_NO_TRANSCRIPT_COMMENTS
        with self.assertRaisesRegex(Phase4Error, "not a creator"):
            triage([video])
        video["claims"][0]["creator_attribution"] = False
        self.assertEqual(triage([video])["claims"][0]["source"], "comment")

    def test_partial_video_excluded_and_not_eligible_for_manual_decision(self):
        video = fixture()
        video["status"] = "blocked_local_model"
        report = triage([video])
        self.assertEqual(report["claim_count"], 0)
        self.assertEqual(report["incomplete_video_records_excluded"], 1)
        key = triage([fixture()])["claims"][0]["claim_id"]
        with self.assertRaisesRegex(Phase4Error, "absent or ineligible"):
            triage([video], [proposed("UPDATE", key)])

    def test_legacy_hash_warning_blocks_update_not_source_review(self):
        video = fixture()
        video["status"] = STATUS_SOURCE_WARNING
        video["source_integrity_warning"] = True
        video["transcript_hash_status"] = "legacy_claim_mismatch"
        key = triage([video])["claims"][0]["claim_id"]
        self.assertEqual(triage([video])["claims"][0]["proposed_category"], "NEEDS_VERIFICATION")
        with self.assertRaisesRegex(Phase4Error, "legacy transcript digest"):
            triage([video], [proposed("UPDATE", key)])

    def test_unknown_or_duplicate_claim_decisions_rejected(self):
        key = triage([fixture()])["claims"][0]["claim_id"]
        with self.assertRaisesRegex(Phase4Error, "unknown phase-4"):
            triage([fixture()], [{"claim_id": key, "category": "VERIFIED"}])
        decision = proposed("UPDATE", key)
        with self.assertRaisesRegex(Phase4Error, "duplicate claim"):
            triage([fixture()], [decision, decision])
        with self.assertRaisesRegex(Phase4Error, "duplicate review"):
            triage([fixture(), fixture()])

    def test_source_excerpt_must_be_short_and_anchored(self):
        video = fixture()
        video["claims"][0]["quote"] = "x" * 111
        with self.assertRaisesRegex(Phase4Error, "source excerpt"):
            triage([video])
        video = fixture()
        video["claims"][0]["evidence_end"] = 9999
        with self.assertRaisesRegex(Phase4Error, "processed source chunk"):
            triage([video])


    def test_missing_historical_transcript_digest_is_a_warning_not_a_false_failure(self):
        video = fixture()
        video["status"] = STATUS_SOURCE_WARNING
        video["transcript_hash_status"] = "missing"
        video["source_integrity_warning"] = False
        item = triage([video])["claims"][0]
        self.assertEqual(item["proposed_category"], "NEEDS_VERIFICATION")
        key = item["claim_id"]
        with self.assertRaisesRegex(Phase4Error, "legacy transcript digest warning"):
            triage([video], [proposed("UPDATE", key)])

    def test_forged_complete_review_without_any_saved_chunks_is_rejected(self):
        video = fixture()
        del video["chunks"]
        with self.assertRaisesRegex(Phase4Error, "chunk coverage"):
            triage([video])
        video["chunks"] = []
        with self.assertRaisesRegex(Phase4Error, "chunk coverage"):
            triage([video])

    def test_complete_review_missing_a_transcript_segment_is_rejected(self):
        video = fixture()
        video["chunks"][0]["end"] = 200
        with self.assertRaisesRegex(Phase4Error, "does not cover"):
            triage([video])

    def test_a_claim_cannot_point_outside_its_processed_source_chunk(self):
        video = fixture()
        quote_len = len(video["claims"][0]["quote"])
        video["claims"][0]["evidence_start"] = 300
        video["claims"][0]["evidence_end"] = 300 + quote_len
        with self.assertRaisesRegex(Phase4Error, "outside its processed"):
            triage([video])

    def test_completed_chunk_claim_counters_are_checked_not_trusted(self):
        video = fixture()
        video["chunks"][0]["valid_claims"] = 0
        with self.assertRaisesRegex(Phase4Error, "claim counters"):
            triage([video])
        video = fixture()
        video["rejected_unanchored_claims"] = 1
        with self.assertRaisesRegex(Phase4Error, "rejection counter"):
            triage([video])

    def test_complete_transcript_cannot_be_replaced_with_only_comment_chunks(self):
        # Regression: previous coverage gate compared reported chunk counts,
        # but never required any transcript span when transcript_characters > 0.
        video = fixture()
        video["transcript_chunks_expected"] = 0
        video["comment_count"] = 1
        video["comment_chunks_expected"] = 1
        video["chunks"][0]["source"] = "comment"
        video["chunks"][0]["comment_index"] = 0
        video["claims"][0]["source"] = "comment"
        video["claims"][0]["comment_index"] = 0
        video["claims"][0]["creator_attribution"] = False
        with self.assertRaisesRegex(Phase4Error, "transcript chunks missing"):
            triage([video])

    def test_empty_video_cannot_claim_comments_only_review_completed(self):
        # review_video classifies this as no_transcript, not comments-reviewed.
        video = fixture()
        video["status"] = STATUS_NO_TRANSCRIPT_COMMENTS
        video["transcript_characters"] = 0
        video["transcript_chunks_expected"] = 0
        video["comment_count"] = 0
        video["comment_chunks_expected"] = 0
        video["chunks"] = []
        video["claims"] = []
        with self.assertRaisesRegex(Phase4Error, "empty comments"):
            triage([video])

    def test_a_missing_saved_comment_chunk_is_not_considered_complete(self):
        video = fixture()
        video["comment_count"] = 1
        video["comment_chunks_expected"] = 1
        with self.assertRaisesRegex(Phase4Error, "chunk coverage"):
            triage([video])

    def test_real_review_video_output_is_accepted_without_fabricated_coverage(self):
        from knowledge_analysis.corpus import Video, sha256 as source_sha
        from knowledge_analysis.review import review_video
        class FakeModel:
            def ask(self, source, text, metadata):
                return {"summary": "reviewed", "claims": [{
                    "claim": "Forms need accessible labels and testing.",
                    "quote": text[:30],
                    "owner": "design", "kind": "pattern",
                    "needs_current_verification": True
                }]}

        transcript = "Accessibly labelled fields allow keyboard navigation for all visitors. " * 5
        video = Video("ABCDEFGHIJK", "QA video", "QA channel", "20261013",
                      "https://www.youtube.com/watch?v=ABCDEFGHIJK", "unknown",
                      ("design",), transcript, ("Comments should not be creator facts.",),
                      source_sha(transcript), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            result = review_video(video, model=FakeModel(), model_sha256="a" * 64,
                                  out_dir=Path(d), chunk_size=510)
            self.assertEqual(result["status"], STATUS_COMPLETE)
            output = triage([result])
            self.assertEqual(output["claim_count"], 2)
            self.assertEqual(output["proposed_category_counts"], {"NEEDS_VERIFICATION": 2})

    def test_cli_reads_fixture_and_writes_only_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            videos = root / "videos"
            videos.mkdir()
            (videos / "ABCDEFGHIJK.json").write_text(json.dumps(fixture()))
            out = root / "phase4.json"
            script = Path(__file__).resolve().parents[1] / "scripts/knowledge_phase4.py"
            proc = subprocess.run([sys.executable, str(script),
                                   "--reviews-dir", str(videos), "--out", str(out)],
                                  capture_output=True, text=True, timeout=15)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(out.read_text())
            self.assertEqual(report["proposed_category_counts"], {"NEEDS_VERIFICATION": 1})
            self.assertFalse(report["auto_promoted"])
            again = subprocess.run([sys.executable, str(script),
                                    "--reviews-dir", str(videos), "--out", str(out)],
                                   capture_output=True, text=True, timeout=15)
            self.assertEqual(again.returncode, 2)
            self.assertIn("refuse to overwrite", again.stderr)


if __name__ == "__main__":
    unittest.main()
