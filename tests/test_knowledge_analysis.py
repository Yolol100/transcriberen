from __future__ import annotations

import bz2
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from knowledge_analysis.corpus import CorpusError, iter_videos, sha256, Video, source_receipt
from knowledge_analysis.review import (split_exact, review_video, signature,
                                        STATUS_COMPLETE, InferenceError, LocalModel)


def record(id="ABCDEFGHIJK", transcript="Fact example: prefer simple responsive layouts.", comments=None):
    return {"_record_type": "youtube_video", "video_id": id,
            "transcript": transcript, "transcript_sha256": sha256(transcript),
            "title": "Test", "domain_routes": ["design"], "comments": comments or []}


def write_shard(path, records):
    content = b"".join(json.dumps(x).encode() + b"\n" for x in records)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("archive.jsonl.bz2", bz2.compress(content))


class FakeModel:
    def __init__(self, errors=False):
        self.calls = []
        self.errors = errors

    def ask(self, source, text, metadata):
        self.calls.append((source, text))
        if self.errors:
            raise InferenceError("expected test failure")
        return {"summary": "observed", "uncertainty": "needs verification", "claims": [
            {"claim": "Usability should be tested on real screens", "quote": text[:30],
             "owner": "design", "kind": "pattern", "needs_current_verification": True}
        ] if len(text) >= 30 else []}


class CorpusTests(unittest.TestCase):
    def test_realistic_full_course_transcript_is_not_silently_dropped(self):
        # Previous 2 MB cap blocked eight videos in the existing v15 corpus,
        # aborting the whole 18,875-video inventory.
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "full-course.zip"
            write_shard(z, [record(transcript="G" * 2_600_000)])
            entry, = list(iter_videos(z))
            self.assertEqual(len(entry.transcript), 2_600_000)
            self.assertEqual(entry.transcript_sha256, sha256(entry.transcript))

    def test_transcript_safety_limit_is_still_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "too-large.zip"
            write_shard(z, [record(transcript="G" * 3_000_001)])
            with self.assertRaisesRegex(CorpusError, "invalid transcript"):
                list(iter_videos(z))

    def test_full_shard_and_comments(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "part.zip"
            data = record(comments=[{"text": "Question about implementation"}, {"body": "Works on mobile"}])
            write_shard(z, [data])
            result = list(iter_videos(z))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].comments, ("Question about implementation", "Works on mobile"))
            self.assertEqual(result[0].routes, ("design",))

    def test_rejects_conflicting_transcript_digest(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "part.zip"
            data = record()
            data["transcript_sha256"] = "0" * 64
            write_shard(z, [data])
            with self.assertRaisesRegex(CorpusError, "SHA mismatch"):
                list(iter_videos(z))

    def test_legacy_library_hash_mismatch_is_downgraded_not_silent(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "part.zip"
            data = record()
            data["transcript_sha256"] = "a" * 64
            data["source_member"] = "legacy_original_caption.txt"
            write_shard(z, [data])
            video, = list(iter_videos(z))
            self.assertEqual(video.transcript_hash_status, "legacy_claim_mismatch")
            self.assertEqual(video.transcript_hash_claim, "a" * 64)
            fake = FakeModel()
            reviewed = review_video(video, model=fake, model_sha256="b"*64,
                                    out_dir=Path(d), chunk_size=510)
            self.assertEqual(reviewed["status"], "ai_reviewed_unverified_legacy_source_hash")
            self.assertTrue(reviewed["source_integrity_warning"])
            self.assertFalse(reviewed["auto_promoted"])

    def test_no_transcript_comments_still_get_reviewed(self):
        video = Video("ABCDEFGHIJK", "T", "C", "", "", "unknown", (), "",
                      ("This item has a broken keyboard navigation state.",),
                      sha256(""), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            fake = FakeModel()
            reviewed = review_video(video, model=fake, model_sha256="c"*64, out_dir=Path(d))
            self.assertEqual(reviewed["status"], "no_transcript_comments_reviewed")
            self.assertTrue(reviewed["comments_read_completely"])
            self.assertEqual(len(fake.calls), 1)

    def test_rejects_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "evil.zip"
            with zipfile.ZipFile(z, "w") as out:
                out.writestr("../evil.jsonl", "{}\n")
            with self.assertRaises(CorpusError):
                list(iter_videos(z))

    def test_channel_partial_manifest_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "channel.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("manifest.json", json.dumps({"items": [], "unresolved": [
                    {"video_id": "ABCDEFGHIJK", "status": "access_blocked"}],
                    "partial_reasons": ["access_blocked"]}))
                z.writestr("result.json", json.dumps({"status": "partial"}))
            info = source_receipt(path)
            self.assertTrue(info["source_partial"])
            self.assertEqual(info["unresolved_count"], 1)
            self.assertEqual(info["status"], "partial")

    def test_rejects_unreadable_wrapped_comments(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "part.zip"
            data = record()
            data["comments"] = {"comments": [{"unknown_field": "text"}]}
            write_shard(z, [data])
            with self.assertRaisesRegex(CorpusError, "nontext or empty comment"):
                list(iter_videos(z))

    def test_long_verbatim_claim_is_rejected(self):
        from knowledge_analysis.review import _clean_claims
        raw = "You should always compare the final recorded state against independent evidence, not merely trust the tool output. " * 2
        quote = raw[:60]
        claims, rejected = _clean_claims({"claims": [{"claim": raw[:130], "quote": quote}]}, raw, 0, "transcript")
        self.assertEqual((claims, rejected), ([], 1))

    def test_nested_decompression_budget_rejects_too_many_records(self):
        from knowledge_analysis import corpus
        previous = corpus.MAX_RECORDS_PER_ARCHIVE
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"many.zip"
            write_shard(path, [record(), record(id="LMNOPQRSTUV")])
            try:
                corpus.MAX_RECORDS_PER_ARCHIVE = 1
                with self.assertRaisesRegex(CorpusError, "expanded corpus exceeds"):
                    list(iter_videos(path))
            finally:
                corpus.MAX_RECORDS_PER_ARCHIVE = previous

    def test_channel_format(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "channel-corpus.zip"
            data = record()
            meta = {k: v for k, v in data.items() if k not in ("transcript", "comments", "_record_type")}
            meta["transcript_status"] = "ok"
            with zipfile.ZipFile(z, "w") as out:
                out.writestr("manifest.json", json.dumps({"items": [meta]}))
                out.writestr("videos/ABCDEFGHIJK/metadata.json", json.dumps(meta))
                out.writestr("videos/ABCDEFGHIJK/comments.json", json.dumps({"comments": [], "status": "ok"}))
                out.writestr("videos/ABCDEFGHIJK/transcript.txt", data["transcript"])
            self.assertEqual([x.video_id for x in iter_videos(z)], ["ABCDEFGHIJK"])

    def test_chunk_coverage_all_characters(self):
        text = ("One two three four five six\n" * 500) + "fin"
        pieces = split_exact(text, 517)
        self.assertEqual("".join(x[2] for x in pieces), text)
        self.assertEqual(pieces[0][0], 0)
        self.assertEqual(pieces[-1][1], len(text))
        self.assertTrue(all(a < b for a,b,_ in pieces))

    def test_ai_review_completeness_comments_and_resume(self):
        video = Video("ABCDEFGHIJK", "Example", "Sample", "20261013",
                      "https://www.youtube.com/watch?v=ABCDEFGHIJK", "expert_creator",
                      ("design",), "Alpha valid details and responsive observations. " * 60,
                      ("I am confused by sizing controls",), "", "ok", "fixture")
        video = Video(**{**video.__dict__, "transcript_sha256": sha256(video.transcript)})
        with tempfile.TemporaryDirectory() as d:
            fake = FakeModel()
            first = review_video(video, model=fake, model_sha256="f"*64, out_dir=Path(d), chunk_size=510)
            self.assertEqual(first["status"], STATUS_COMPLETE)
            self.assertTrue(first["transcript_read_completely"])
            self.assertTrue(first["comments_read_completely"])
            self.assertEqual(len([c for c in first["chunks"] if c["source"] == "comment"]), 1)
            self.assertTrue(first["claims"])
            self.assertTrue(all("evidence_start" in c for c in first["claims"]))
            self.assertFalse(first["auto_promoted"])
            n = len(fake.calls)
            self.assertTrue(review_video(video, model=fake, model_sha256="f"*64, out_dir=Path(d), chunk_size=510)["resumed"])
            self.assertEqual(len(fake.calls), n)

    def test_changed_chunk_size_forces_new_review(self):
        t = "Important source context about item categories and test cases. " * 20
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t,
                      (), sha256(t), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            fake = FakeModel()
            review_video(video, model=fake, model_sha256="a"*64,
                         out_dir=Path(d), chunk_size=510)
            prev = len(fake.calls)
            result = review_video(video, model=fake, model_sha256="a"*64,
                                  out_dir=Path(d), chunk_size=560)
            self.assertEqual(result["status"], STATUS_COMPLETE)
            self.assertFalse(result.get("resumed", False))
            self.assertGreater(len(fake.calls), prev)

    def test_imported_tampered_completed_result_cannot_bypass_review(self):
        t = "Relevant source evidence about accessible controls. " * 15
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t,
                      (), sha256(t), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            fake = FakeModel()
            original = review_video(video, model=fake, model_sha256="a"*64,
                                    out_dir=Path(d), chunk_size=510)
            path = Path(d) / "videos" / "ABCDEFGHIJK.json"
            original["chunks"] = []
            path.write_text(json.dumps(original))
            prev = len(fake.calls)
            result = review_video(video, model=fake, model_sha256="a"*64,
                                  out_dir=Path(d), chunk_size=510)
            self.assertFalse(result.get("resumed", False))
            self.assertEqual(result["status"], STATUS_COMPLETE)
            self.assertGreater(len(fake.calls), prev)

    def test_imported_claim_without_valid_quote_is_rejected(self):
        t = "Significant and verifiable source text about form error handling. " * 20
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t,
                      (), sha256(t), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            fake = FakeModel()
            original = review_video(video, model=fake, model_sha256="a"*64,
                                    out_dir=Path(d), chunk_size=510)
            path = Path(d) / "videos" / "ABCDEFGHIJK.json"
            original["claims"][0]["quote"] = "invented evidence"
            path.write_text(json.dumps(original))
            prev = len(fake.calls)
            result = review_video(video, model=fake, model_sha256="a"*64,
                                  out_dir=Path(d), chunk_size=510)
            self.assertFalse(result.get("resumed", False))
            self.assertEqual(result["status"], STATUS_COMPLETE)
            self.assertGreater(len(fake.calls), prev)

    def test_imported_partial_checkpoint_cannot_skip_unprocessed_source(self):
        t = "Verifiable long transcript with advice about keyboard accessible form fields. " * 30
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t,
                      ("Helpful but questionable comment text about checkout forms",),
                      sha256(t), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            fake = FakeModel()
            initial = review_video(video, model=fake, model_sha256="a"*64,
                                   out_dir=Path(d), chunk_size=510)
            path = Path(d)/"videos"/"ABCDEFGHIJK.json"
            # A partial artifact claims progress from another offset; a bare
            # matching source signature is not sufficient to skip work.
            initial["status"] = "blocked_time_budget"
            initial["chunks"][0]["start"] += 1
            path.write_text(json.dumps(initial))
            fresh = FakeModel()
            actual = review_video(video, model=fresh, model_sha256="a"*64,
                                  out_dir=Path(d), chunk_size=510)
            self.assertEqual(actual["status"], STATUS_COMPLETE)
            self.assertEqual(len(fresh.calls), len(actual["chunks"]))
            self.assertNotIn("resumed", actual)

    def test_corrupted_rejection_counter_cannot_crash_resumed_review(self):
        t = "A meaningful discussion of responsive forms and accessibility. " * 28
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t,
                      (), sha256(t), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"videos"/"ABCDEFGHIJK.json"
            prior = review_video(video, model=FakeModel(), model_sha256="d"*64,
                                 out_dir=Path(d), chunk_size=510)
            prior["status"] = "review_in_progress"
            prior["chunks"] = prior["chunks"][:1]
            prior["claims"] = prior["claims"][:1]
            prior["rejected_unanchored_claims"] = "invalid"
            path.write_text(json.dumps(prior))
            fake = FakeModel()
            actual = review_video(video, model=fake, model_sha256="d"*64,
                                  out_dir=Path(d), chunk_size=510)
            self.assertEqual(actual["status"], STATUS_COMPLETE)
            self.assertEqual(len(fake.calls), len(actual["chunks"]))
            self.assertNotIn("resumed", actual)

    def test_missing_saved_claim_for_processed_chunk_forces_rereview(self):
        t = "A concrete explanation of accessible mobile controls for real users. " * 24
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t,
                      (), sha256(t), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            result = review_video(video, model=FakeModel(), model_sha256="c"*64,
                                  out_dir=Path(d), chunk_size=510)
            self.assertGreater(len(result["claims"]), 0)
            result["claims"].pop()
            path = Path(d)/"videos"/"ABCDEFGHIJK.json"
            path.write_text(json.dumps(result))
            model = FakeModel()
            actual = review_video(video, model=model, model_sha256="c"*64,
                                  out_dir=Path(d), chunk_size=510)
            self.assertEqual(actual["status"], STATUS_COMPLETE)
            self.assertGreater(len(model.calls), 0)
            self.assertNotIn("resumed", actual)

    def test_forged_completion_flags_force_new_review(self):
        t = "Some facts about navigation keyboard and touch devices. " * 20
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t,
                      (), sha256(t), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            record = review_video(video, model=FakeModel(), model_sha256="d"*64,
                                  out_dir=Path(d), chunk_size=510)
            record["comments_read_completely"] = False
            path = Path(d)/"videos"/"ABCDEFGHIJK.json"
            path.write_text(json.dumps(record))
            fake = FakeModel()
            rerun = review_video(video, model=fake, model_sha256="d"*64,
                                 out_dir=Path(d), chunk_size=510)
            self.assertFalse(rerun.get("resumed", False))
            self.assertGreater(len(fake.calls), 0)

    def test_changed_metadata_invalidates_previous_inference(self):
        t = "Explain concrete consent categories and users. " * 20
        video = Video("ABCDEFGHIJK", "Original", "Original Channel", "20261001", "", "unknown",
                      ("seo",), t, (), sha256(t), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            model = FakeModel()
            review_video(video, model=model, model_sha256="a"*64,
                         out_dir=Path(d), chunk_size=510)
            prior_count = len(model.calls)
            revised = Video(**{**video.__dict__, "title": "Changed Source Title"})
            result = review_video(revised, model=model, model_sha256="a"*64,
                                  out_dir=Path(d), chunk_size=510)
            self.assertEqual(result["status"], STATUS_COMPLETE)
            self.assertGreater(len(model.calls), prior_count)
            self.assertFalse(result.get("resumed", False))

    def test_malformed_checkpoint_list_is_not_accepted(self):
        t = "Description of accessibility and validation patterns. " * 20
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t,
                      (), sha256(t), "ok", "fixture")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"videos"/"ABCDEFGHIJK.json"
            path.parent.mkdir(parents=True)
            path.write_text("[]")
            actual = review_video(video, model=FakeModel(), model_sha256="a"*64,
                                  out_dir=Path(d), chunk_size=510)
            self.assertEqual(actual["status"], STATUS_COMPLETE)

    def test_untrusted_model_malformed_owner_and_boolean_fail_safe(self):
        from knowledge_analysis.review import _clean_claims
        piece = "A specific user-facing contrast instruction should be verified."
        candidate = {"claims":[{"claim":"Contrast statements require verification",
                                "quote":piece[:30], "owner":["seo"],
                                "kind":[], "needs_current_verification":"false"}]}
        claims, rejected = _clean_claims(candidate, piece, 0, "transcript")
        self.assertEqual(rejected, 0)
        self.assertEqual(claims[0]["owner_candidate"], "unknown")
        self.assertEqual(claims[0]["kind"], "unknown")
        self.assertTrue(claims[0]["needs_current_verification"])

    def test_restored_video_metadata_forgery_cannot_pass_as_complete(self):
        t = "Accessible input controls should give users comprehensible errors. " * 20
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t, (), sha256(t), "ok", "fixture")
        for key, value in (("video_id", "LMNOPQRSTUV"), ("model_sha256", "1" * 64),
                           ("source_integrity_warning", True), ("policy_version", "knowledge-review-v0")):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as d:
                fake = FakeModel()
                prior = review_video(video, model=fake, model_sha256="a" * 64, out_dir=Path(d), chunk_size=510)
                prior[key] = value
                path = Path(d) / "videos" / "ABCDEFGHIJK.json"
                path.write_text(json.dumps(prior))
                old = len(fake.calls)
                resumed = review_video(video, model=fake, model_sha256="a" * 64,
                                       out_dir=Path(d), chunk_size=510)
                self.assertFalse(resumed.get("resumed", False))
                self.assertEqual(resumed["status"], STATUS_COMPLETE)
                self.assertGreater(len(fake.calls), old)

    def test_unhashable_restored_chunk_identity_is_rejected_without_crash(self):
        t = "Form feedback should remain understandable on a small screen. " * 20
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t, (), sha256(t), "ok", "fixture")
        for field, value in (("source", ["transcript"]), ("comment_index", [0]),
                             ("sha256", {"digest": "bogus"})):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                fake = FakeModel()
                prior = review_video(video, model=fake, model_sha256="a" * 64, out_dir=Path(d), chunk_size=510)
                prior["chunks"][0][field] = value
                path = Path(d) / "videos" / "ABCDEFGHIJK.json"
                path.write_text(json.dumps(prior))
                old = len(fake.calls)
                res = review_video(video, model=fake, model_sha256="a" * 64,
                                   out_dir=Path(d), chunk_size=510)
                self.assertEqual(res["status"], STATUS_COMPLETE)
                self.assertGreater(len(fake.calls), old)

    def test_untrusted_restored_claim_owner_and_verification_are_not_reused(self):
        t = "Field labels and validation messages must be clear on mobile. " * 25
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t, (), sha256(t), "ok", "fixture")
        for field, value in (("owner_candidate", ["design"]), ("kind", {"type": "fact"}),
                             ("needs_current_verification", "false")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                fake = FakeModel()
                prior = review_video(video, model=fake, model_sha256="a" * 64, out_dir=Path(d), chunk_size=510)
                self.assertTrue(prior["claims"])
                prior["claims"][0][field] = value
                path = Path(d) / "videos" / "ABCDEFGHIJK.json"
                path.write_text(json.dumps(prior))
                old = len(fake.calls)
                res = review_video(video, model=fake, model_sha256="a" * 64,
                                   out_dir=Path(d), chunk_size=510)
                self.assertEqual(res["status"], STATUS_COMPLETE)
                self.assertGreater(len(fake.calls), old)

    def test_errors_do_not_mark_complete_and_retry(self):
        t = "Enough explanatory text for evidence review! " * 15
        video = Video("ABCDEFGHIJK", "A", "B", "", "", "unknown", (), t, (), sha256(t), "unknown", "fixture")
        with tempfile.TemporaryDirectory() as d:
            fail = review_video(video, model=FakeModel(errors=True), model_sha256="1"*64,
                                out_dir=Path(d), chunk_size=510)
            self.assertEqual(fail["status"], "blocked_local_model")
            self.assertFalse(fail["transcript_read_completely"])
            good = review_video(video, model=FakeModel(), model_sha256="1"*64,
                                out_dir=Path(d), chunk_size=510)
            self.assertEqual(good["status"], STATUS_COMPLETE)

    def test_contract_and_workflow_never_mutate_existing_acquisition(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads((root / "knowledge-analysis-contract.json").read_text())
        self.assertEqual(contract["batch_size"], 500)
        self.assertEqual(contract["slice_size"], 20)
        for flag in ("requires_user_api_key", "requires_added_account", "requires_mcp",
                     "requires_self_hosted_runner", "uses_external_inference"):
            self.assertFalse(contract[flag])
        wf = (root / ".github/workflows/knowledge-analysis.yml").read_text()
        self.assertIn("workflow_dispatch:", wf)
        self.assertIn("runs-on: ubuntu-24.04", wf)
        self.assertIn("if: inputs.scope != 'inventory'", wf)
        self.assertNotIn("models: read", wf)
        self.assertNotIn("OPENAI_API_KEY", wf)
        self.assertNotIn("self-hosted", wf)
        tool = (root / "scripts/knowledge_model.sh").read_text()
        self.assertIn(contract["engine"]["sha256"], tool)
        self.assertIn(contract["weights"]["sha256"], tool)
        self.assertIn("--host 127.0.0.1", tool)

    def test_local_endpoint_is_strict(self):
        with self.assertRaises(InferenceError):
            LocalModel("https://external.example.com/inference")

    def test_unanchored_claim_is_rejected(self):
        from knowledge_analysis.review import _clean_claims
        out, rejected = _clean_claims({"claims": [{"claim": "An invented finding that lacks source proof", "quote": "nowhere"}]}, "hello", 0, "transcript")
        self.assertEqual((out, rejected), ([], 1))


if __name__ == "__main__":
    unittest.main()
