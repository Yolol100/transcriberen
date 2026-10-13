"""Phase 4 categorization is evidence-only and never a knowledge write."""
import tempfile
from pathlib import Path
import json
import subprocess
import sys
import unittest

from knowledge_analysis.phase4 import Phase4Error, triage
from knowledge_analysis.review import POLICY_VERSION, STATUS_COMPLETE, STATUS_SOURCE_WARNING


def fixture():
    quote = "Theme JSON supports documented styles and settings."
    return {
        "schema_version": "1.0", "policy_version": POLICY_VERSION,
        "signature": "a" * 64, "video_id": "ABCDEFGHIJK",
        "model_sha256": "b" * 64, "transcript_sha256": "c" * 64,
        "status": STATUS_COMPLETE, "source_integrity_warning": False,
        "auto_promoted": False, "human_qa_approved": False,
        "project_source_compared": False, "primary_sources_verified": False,
        "transcript_read_completely": True, "comments_read_completely": True,
        "comments_status": "unknown",
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
        with self.assertRaisesRegex(Phase4Error, "offsets"):
            triage([video])

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
