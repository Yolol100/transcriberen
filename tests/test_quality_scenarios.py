import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


youtube_runtime = load_module("youtube_runtime_quality", ROOT / "scripts" / "youtube_runtime.py")
VALIDATOR = ROOT / "scripts" / "validate_result.py"


class SubtitleNormalizationScenarios(unittest.TestCase):
    def normalize(self, text, suffix=".vtt"):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / f"sample{suffix}"
            path.write_text(text, encoding="utf-8")
            return youtube_runtime.normalize_subtitles(path)

    def test_webvtt_metadata_inline_timestamps_entities_and_rolling_overlap(self):
        text = """WEBVTT\nKind: captions\nLanguage: en\n\n00:00:00.000 --> 00:00:01.000\n<v Speaker>Hello &amp; welcome</v>\n\n00:00:01.000 --> 00:00:02.000\nHello &amp; welcome to <00:00:01.500>Webactueel\n\n00:00:02.000 --> 00:00:03.000\nto Webactueel today\n"""
        self.assertEqual(self.normalize(text), "Hello & welcome\nto Webactueel\ntoday")

    def test_srt_is_normalized_without_sequence_numbers_or_tags(self):
        text = """1\n00:00:00,000 --> 00:00:01,000\n<b>Hello</b> world\n\n2\n00:00:01,000 --> 00:00:02,000\nSecond line\n"""
        self.assertEqual(self.normalize(text, ".srt"), "Hello world\nSecond line")


class CommandSafetyScenarios(unittest.TestCase):
    def test_comment_command_has_retry_pacing_and_no_media(self):
        cmd = youtube_runtime._json_command(
            "https://www.youtube.com/watch?v=abc", comments=True, comment_sort="new", max_comments="20"
        )
        joined = " ".join(cmd)
        self.assertIn("--skip-download", cmd)
        self.assertIn("--sleep-requests", cmd)
        self.assertIn("comment_sort=new", joined)
        self.assertIn("max_comments=20,all,all,all", joined)
        self.assertNotIn("-x", cmd)
        self.assertNotIn("-f", cmd)


class DiscoveryScenarios(unittest.TestCase):
    def test_channel_all_interleaves_three_tabs_before_cutoff(self):
        req = {"url": "https://www.youtube.com/@example", "youtube": {"scope": "channel_all", "max_items": 6, "scan_limit": 6, "sort_by": "relevance"}}
        def fake_json(cmd):
            source = cmd[-1]
            prefix = "V" if source.endswith("/videos") else "S" if source.endswith("/shorts") else "L"
            return {"playlist_count": 2, "entries": [{"id": f"{prefix}{i}", "title": f"{prefix}{i}"} for i in range(1, 3)]}
        with mock.patch.object(youtube_runtime, "load_json", side_effect=fake_json):
            entries, info = youtube_runtime.discover_candidates_detailed(req)
        self.assertEqual([x["id"] for x in entries], ["V1", "S1", "L1", "V2", "S2", "L2"])
        self.assertEqual(info["scan_limit"], 6)

    def test_channel_streams_direct_scope(self):
        req = {"url": "https://www.youtube.com/@example", "youtube": {"scope": "channel_streams"}}
        self.assertTrue(youtube_runtime.discover_source(req)[0].endswith("/streams"))


class PrivacyAndCommentsScenarios(unittest.TestCase):
    def test_comment_identity_fields_are_minimized_and_text_marked_redacted(self):
        raw = [{"id": "c1", "parent": "root", "text": "Useful comment", "author": "Person", "author_id": "UCprivate", "author_url": "https://youtube.example/person", "author_is_uploader": True, "timestamp": 1, "like_count": 2}]
        comments = youtube_runtime.normalized_comments(raw, "all")
        self.assertEqual(len(comments), 1)
        for key in ("author", "author_id", "author_url", "id", "parent"):
            self.assertNotIn(key, comments[0])
        self.assertTrue(comments[0]["text_redacted"])
        self.assertRegex(comments[0]["comment_ref"], r"^sha256:[0-9a-f]{20}$")

    def test_best_effort_all_never_claims_verified_completeness(self):
        payload = {"comment_count": 2, "comments": [{"id": "1", "text": "a"}, {"id": "2", "text": "b"}]}
        req = {"youtube": {"comment_sort": "new", "max_comments": "all"}}
        with mock.patch.object(youtube_runtime, "load_json", return_value=payload):
            _, summary = youtube_runtime.comments_for("https://www.youtube.com/watch?v=x", req, 2)
        self.assertEqual(summary["completeness"], "best_effort_unverified")
        self.assertEqual(summary["reply_completeness"], "best_effort_unverified")


class CollectionRecoveryScenarios(unittest.TestCase):
    def test_no_persistence_uses_minimized_metadata(self):
        req = {"request_id": "x", "language": "auto", "analysis_content_allowed": False, "reuse_allowed": False, "youtube": {"scope": "video", "max_items": 1, "sort_by": "relevance", "include_comments": False}}
        candidate = {"url": "https://www.youtube.com/watch?v=x", "id": "x"}
        meta = {"id": "x", "title": "good", "description": "private-ish description", "uploader": "Person", "webpage_url": candidate["url"], "upload_date": "20260101"}
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(youtube_runtime, "discover_candidates_detailed", return_value=([candidate], {"scan_limit": 1, "candidate_limit": None, "possibly_truncated": False, "sources": []})), \
             mock.patch.object(youtube_runtime, "metadata_for", return_value=meta), \
             mock.patch.object(youtube_runtime, "download_caption", return_value=("hello", {"language": "en", "kind": "manual", "_segments": []})):
            _, index = youtube_runtime.collect(req, tmp)
            root = pathlib.Path(tmp)
            stored = json.loads((root / "items" / "x" / "metadata.json").read_text())
        self.assertNotIn("description", stored)
        self.assertNotIn("uploader", stored)
        self.assertFalse((root / "content.md").exists())
        self.assertEqual(index["comments_disabled_count"], 0)


class ResultValidatorScenarios(unittest.TestCase):
    def make_valid_results(self, root):
        root = pathlib.Path(root)
        item_dir = root / "items" / "v1"
        item_dir.mkdir(parents=True)
        transcript = "hello\n"
        content = "# YouTube collection\n\n## good\n\nhello\n"
        (root / "content.md").write_text(content, encoding="utf-8")
        (item_dir / "transcript.md").write_text(transcript, encoding="utf-8")
        (item_dir / "transcript-cues.json").write_text(json.dumps([{"start":"00:00:00.000","end":"00:00:01.000","text":"hello"}]), encoding="utf-8")
        metadata = {"id": "v1", "title": "good"}
        (item_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        comments = [{"comment_ref": "sha256:abc", "parent_ref":"root", "text": "useful", "text_redacted": True, "like_count": 1}]
        (item_dir / "comments.json").write_text(json.dumps(comments), encoding="utf-8")
        item = {"id": "v1", "artifact_id": "v1", "url": "https://www.youtube.com/watch?v=v1", "metadata": metadata, "metadata_minimized": False, "status": "ok", "caption": {"language": "en", "kind": "manual"}, "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(), "transcript_chars": len(transcript), "comment_status": "ok", "comments_extracted": 1, "comments": {"identity_minimized": True, "completeness": "bounded"}, "comment_review_candidates": 0}
        index = {"schema_version": "webactueel-youtube-collection/1.1", "scope": "video", "query": None, "collection_status": "ok", "candidate_count": 1, "eligible_count": 1, "selected_count": 1, "item_count": 1, "transcript_count": 1, "no_caption_count": 0, "caption_error_count": 0, "comment_error_count": 0, "comments_disabled_count": 0, "comment_review_candidate_count": 0, "include_comments": True, "comment_identity_minimized": True, "comment_text_redaction": "obvious-direct-identifiers", "discovery": {"possibly_truncated": False, "scan_limit": 1, "sources": []}, "items": [item]}
        (root / "youtube-index.json").write_text(json.dumps(index), encoding="utf-8")
        result = {"schema_version": "webactueel-transcription-result/1.1", "request_id": "quality-test", "owner": "webactueel-workflow", "project_id": "project-transcriberen", "source_url": "https://www.youtube.com/watch?v=v1", "requested_mode": "youtube", "detected_mode": "youtube", "language": "auto", "evidence_level": "controlled_runtime", "analysis_content_allowed": True, "reuse_allowed": False, "public_request_acknowledged": False, "usage_mode": "analysis-paraphrase-only", "rights_basis": "analysis-paraphrase-only", "youtube_access_basis": "prior-written-permission", "audio_access_authorized": False, "content_sha256": hashlib.sha256(content.encode()).hexdigest(), "content_chars": len(content), "content_persisted": True, "metadata": {"youtube": {"scope": "video", "media_downloaded": False}}, "tool_versions": {"yt-dlp": "x", "trafilatura": "2.1.0"}, "source_context": {"project_id":"project-transcriberen", "source_set_version":"2.0.0-audit-hardening"}, "runtime_provenance": {"repository":"Yolol100/transcriberen","head_sha":"a"*40,"run_id":"1","run_attempt":"1","workflow_ref":"x","event_name":"workflow_dispatch","repository_visibility":"private","request_sha256":"a"*64}}
        (root / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return root / "result.json"

    def run_validator(self, path):
        return subprocess.run([sys.executable, str(VALIDATOR), str(path)], cwd=ROOT, capture_output=True, text=True)

    def test_valid_result_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_valid_results(tmp)
            proc = self.run_validator(result)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_direct_comment_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_valid_results(tmp)
            comments_path = pathlib.Path(tmp) / "items" / "v1" / "comments.json"
            comments = json.loads(comments_path.read_text())
            comments[0]["author"] = "leak"
            comments_path.write_text(json.dumps(comments))
            proc = self.run_validator(result)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("comment identity field", proc.stderr)


if __name__ == "__main__":
    unittest.main()
