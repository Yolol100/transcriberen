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
            self.assertTrue(review_video(video, model=fake, model_sha256="f"*64, out_dir=Path(d))["resumed"])
            self.assertEqual(len(fake.calls), n)

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