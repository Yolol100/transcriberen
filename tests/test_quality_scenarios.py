import hashlib
import importlib.util
import json
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
resolve_request = load_module("resolve_request_quality", ROOT / "scripts" / "resolve_request.py")
VALIDATOR = ROOT / "scripts" / "validate_result.py"


class SubtitleNormalizationScenarios(unittest.TestCase):
    def normalize(self, text, suffix=".vtt"):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / f"sample{suffix}"
            path.write_text(text, encoding="utf-8")
            return youtube_runtime.normalize_subtitles(path)

    def test_webvtt_metadata_inline_timestamps_entities_and_rolling_overlap(self):
        text = """WEBVTT\nKind: captions\nLanguage: en\n\n00:00:00.000 --> 00:00:01.000 align:start position:0%\n<v Speaker>Hello &amp; welcome</v>\n\n00:00:01.000 --> 00:00:02.000\nHello &amp; welcome to <00:00:01.500>Webactueel\n\n00:00:02.000 --> 00:00:03.000\nto Webactueel today\n"""
        self.assertEqual(self.normalize(text), "Hello & welcome\nto Webactueel\ntoday")

    def test_srt_is_normalized_without_sequence_numbers_or_tags(self):
        text = """1\n00:00:00,000 --> 00:00:01,000\n<b>Hello</b> world\n\n2\n00:00:01,000 --> 00:00:02,000\nSecond line\n"""
        self.assertEqual(self.normalize(text, ".srt"), "Hello world\nSecond line")

    def test_note_style_region_blocks_do_not_leak(self):
        text = """WEBVTT\n\nNOTE generated\nignore me\n\nSTYLE\n::cue { color: lime; }\n\nREGION\nid:fred\n\n00:00:00.000 --> 00:00:01.000\nUseful text\n"""
        self.assertEqual(self.normalize(text), "Useful text")


class CommandSafetyScenarios(unittest.TestCase):
    def test_comment_command_has_one_combined_extractor_args_and_no_media(self):
        cmd = youtube_runtime._json_command(
            "https://www.youtube.com/watch?v=abc",
            comments=True,
            comment_sort="new",
            max_comments="20",
        )
        self.assertEqual(cmd.count("--extractor-args"), 1)
        args = cmd[cmd.index("--extractor-args") + 1]
        self.assertIn("skip=translated_subs", args)
        self.assertIn("comment_sort=new", args)
        self.assertIn("max_comments=20,all,all,all", args)
        self.assertIn("--skip-download", cmd)
        self.assertNotIn("-x", cmd)
        self.assertNotIn("-f", cmd)

    def test_flat_discovery_ignores_individual_unavailable_entries_but_not_media_policy(self):
        cmd = youtube_runtime._json_command("https://www.youtube.com/playlist?list=PLX", flat=True, playlist_end=50)
        self.assertIn("--flat-playlist", cmd)
        self.assertIn("--ignore-errors", cmd)
        self.assertIn("--playlist-end", cmd)
        self.assertIn("--skip-download", cmd)


class DiscoveryScenarios(unittest.TestCase):
    def test_channel_all_interleaves_videos_and_shorts_before_cutoff(self):
        req = {
            "url": "https://www.youtube.com/@example",
            "youtube": {"scope": "channel_all", "max_items": 4, "scan_limit": 4, "sort_by": "relevance"},
        }
        def fake_json(cmd):
            source = cmd[-1]
            prefix = "V" if source.endswith("/videos") else "S"
            return {
                "playlist_count": 3,
                "entries": [{"id": f"{prefix}{i}", "title": f"{prefix}{i}"} for i in range(1, 4)],
            }
        with mock.patch.object(youtube_runtime, "load_json", side_effect=fake_json):
            entries, info = youtube_runtime.discover_candidates_detailed(req)
        self.assertEqual([x["id"] for x in entries], ["V1", "S1", "V2", "S2"])
        self.assertTrue(info["possibly_truncated"])
        self.assertEqual(info["scan_limit"], 4)

    def test_search_uses_candidate_limit_not_bulk_scan_limit(self):
        req = {"youtube": {"scope": "search", "query": "wordpress seo", "candidate_limit": 17, "scan_limit": 3}}
        self.assertEqual(youtube_runtime.discover_source(req), ["ytsearch17:wordpress seo"])

    def test_rank_is_stable_for_missing_metrics(self):
        items = [
            {"order": 0, "meta": {"view_count": None}},
            {"order": 1, "meta": {"view_count": 10}},
            {"order": 2, "meta": {"view_count": 10}},
        ]
        ranked = youtube_runtime.rank_metadata(items, "views")
        self.assertEqual([x["order"] for x in ranked], [1, 2, 0])


class PrivacyAndCommentsScenarios(unittest.TestCase):
    def test_comment_identity_fields_are_minimized(self):
        raw = [{
            "id": "c1", "parent": "root", "text": "Useful comment", "author": "Person",
            "author_id": "UCprivate", "author_url": "https://youtube.example/person",
            "author_is_uploader": True, "timestamp": 1, "like_count": 2,
        }]
        comments = youtube_runtime.normalized_comments(raw, "all")
        self.assertEqual(len(comments), 1)
        self.assertNotIn("author", comments[0])
        self.assertNotIn("author_id", comments[0])
        self.assertNotIn("author_url", comments[0])
        self.assertNotIn("id", comments[0])
        self.assertNotIn("parent", comments[0])
        self.assertRegex(comments[0]["comment_ref"], r"^sha256:[0-9a-f]{20}$")
        self.assertEqual(comments[0]["parent_ref"], "root")
        self.assertTrue(comments[0]["author_is_uploader"])

    def test_bounded_comment_summary_reports_possible_truncation(self):
        payload = {"comment_count": 100, "comments": [{"id": str(i), "text": f"c{i}"} for i in range(5)]}
        req = {"youtube": {"comment_sort": "top", "max_comments": "5"}}
        with mock.patch.object(youtube_runtime, "load_json", return_value=payload):
            comments, summary = youtube_runtime.comments_for("https://www.youtube.com/watch?v=x", req, 100)
        self.assertEqual(len(comments), 5)
        self.assertTrue(summary["possibly_truncated"])
        self.assertEqual(summary["completeness"], "bounded")
        self.assertTrue(summary["identity_minimized"])

    def test_best_effort_all_never_claims_verified_completeness(self):
        payload = {"comment_count": 2, "comments": [{"id": "1", "text": "a"}, {"id": "2", "text": "b"}]}
        req = {"youtube": {"comment_sort": "new", "max_comments": "all"}}
        with mock.patch.object(youtube_runtime, "load_json", return_value=payload):
            _, summary = youtube_runtime.comments_for("https://www.youtube.com/watch?v=x", req, 2)
        self.assertEqual(summary["mode"], "best_effort_all")
        self.assertEqual(summary["completeness"], "best_effort_unverified")


class RequestBoundaryScenarios(unittest.TestCase):
    def call_scope(self, url, scope):
        with mock.patch.object(resolve_request, "validate_youtube_url", return_value=url):
            return resolve_request.validate_youtube_scope_url(url, scope)

    def test_video_scope_rejects_channel(self):
        with self.assertRaisesRegex(ValueError, "direct YouTube video"):
            self.call_scope("https://www.youtube.com/@example", "video")

    def test_short_scope_rejects_watch_url(self):
        with self.assertRaisesRegex(ValueError, "shorts"):
            self.call_scope("https://www.youtube.com/watch?v=abc", "short")

    def test_playlist_scope_requires_list_parameter(self):
        with self.assertRaisesRegex(ValueError, "list parameter"):
            self.call_scope("https://www.youtube.com/watch?v=abc", "playlist")
        self.assertEqual(
            self.call_scope("https://www.youtube.com/watch?v=abc&list=PL123", "playlist"),
            "https://www.youtube.com/watch?v=abc&list=PL123",
        )

    def test_unbounded_bulk_scan_requires_explicit_opt_in(self):
        req = {"url": "https://www.youtube.com/@example", "youtube": {"scope": "channel_all", "scan_limit": 0}}
        with mock.patch.object(resolve_request, "validate_youtube_scope_url", return_value=req["url"]):
            with self.assertRaisesRegex(ValueError, "allow_unbounded"):
                resolve_request.validate_youtube(req)

    def test_unbounded_all_comments_requires_explicit_opt_in(self):
        req = {
            "url": "https://www.youtube.com/watch?v=abc",
            "youtube": {"scope": "video", "include_comments": True, "max_comments": "all"},
        }
        with mock.patch.object(resolve_request, "validate_youtube_scope_url", return_value=req["url"]):
            with self.assertRaisesRegex(ValueError, "allow_unbounded"):
                resolve_request.validate_youtube(req)

    def test_explicit_unbounded_mode_is_supported(self):
        req = {
            "url": "https://www.youtube.com/@example",
            "youtube": {
                "scope": "channel_all", "scan_limit": 0, "allow_unbounded": True,
                "include_comments": True, "max_comments": "all",
            },
        }
        with mock.patch.object(resolve_request, "validate_youtube_scope_url", return_value=req["url"]):
            result = resolve_request.validate_youtube(req)
        self.assertEqual(result["youtube"]["scan_limit"], 0)
        self.assertTrue(result["youtube"]["allow_unbounded"])
        self.assertEqual(result["youtube"]["max_comments"], "all")


class CollectionRecoveryScenarios(unittest.TestCase):
    def test_partial_batch_continues_and_reports_counts(self):
        req = {
            "language": "auto", "analysis_content_allowed": False, "reuse_allowed": False,
            "youtube": {"scope": "search", "query": "x", "max_items": 3, "sort_by": "relevance", "include_comments": False},
        }
        candidates = [{"url": f"https://www.youtube.com/watch?v={i}", "id": str(i)} for i in range(3)]
        metas = {
            candidates[0]["url"]: {"id": "0", "title": "good", "webpage_url": candidates[0]["url"], "upload_date": "20260101"},
            candidates[1]["url"]: {"id": "1", "title": "none", "webpage_url": candidates[1]["url"], "upload_date": "20260101"},
            candidates[2]["url"]: {"id": "2", "title": "broken", "webpage_url": candidates[2]["url"], "upload_date": "20260101"},
        }
        def fake_caption(url, meta, language):
            if meta["id"] == "0": return "hello", {"language": "en", "kind": "manual"}
            if meta["id"] == "1": return None, None
            raise RuntimeError("caption outage")
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(youtube_runtime, "discover_candidates_detailed", return_value=(candidates, {"scan_limit": None, "candidate_limit": 3, "possibly_truncated": False, "sources": []})), \
             mock.patch.object(youtube_runtime, "metadata_for", side_effect=lambda url: metas[url]), \
             mock.patch.object(youtube_runtime, "download_caption", side_effect=fake_caption):
            _, index = youtube_runtime.collect(req, tmp)
            root = pathlib.Path(tmp)
            self.assertEqual(index["collection_status"], "partial")
            self.assertEqual(index["transcript_count"], 1)
            self.assertEqual(index["no_caption_count"], 1)
            self.assertEqual(index["caption_error_count"], 1)
            self.assertEqual(index["selected_count"], 3)
            self.assertFalse((root / "content.md").exists())
            self.assertFalse(any(root.rglob("transcript.md")))
            self.assertEqual(len(list(root.rglob("metadata.json"))), 3)


class ResultValidatorScenarios(unittest.TestCase):
    def make_valid_results(self, root):
        root = pathlib.Path(root)
        item_dir = root / "items" / "v1"
        item_dir.mkdir(parents=True)
        transcript = "hello\n"
        content = "# YouTube collection\n\n## good\n\nhello\n"
        (root / "content.md").write_text(content, encoding="utf-8")
        (item_dir / "transcript.md").write_text(transcript, encoding="utf-8")
        metadata = {"id": "v1", "title": "good"}
        (item_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        comments = [{"comment_ref": "sha256:abc", "text": "useful", "like_count": 1}]
        (item_dir / "comments.json").write_text(json.dumps(comments), encoding="utf-8")
        item = {
            "id": "v1", "artifact_id": "v1", "url": "https://www.youtube.com/watch?v=v1", "metadata": metadata,
            "status": "ok", "caption": {"language": "en", "kind": "manual"},
            "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(), "transcript_chars": len(transcript),
            "comment_status": "ok", "comments_extracted": 1,
            "comments": {"identity_minimized": True, "completeness": "bounded"},
        }
        index = {
            "schema_version": "webactueel-youtube-collection/1.1", "scope": "video", "query": None,
            "collection_status": "ok", "candidate_count": 1, "eligible_count": 1, "selected_count": 1, "item_count": 1,
            "transcript_count": 1, "no_caption_count": 0, "caption_error_count": 0, "comment_error_count": 0,
            "include_comments": True, "comment_identity_minimized": True,
            "discovery": {"possibly_truncated": False, "scan_limit": 1, "sources": []}, "items": [item],
        }
        (root / "youtube-index.json").write_text(json.dumps(index), encoding="utf-8")
        result = {
            "schema_version": "webactueel-transcription-result/1.1", "request_id": "quality-test", "owner": "webactueel-workflow",
            "project_id": "project-transcriberen", "source_url": "https://www.youtube.com/watch?v=v1", "requested_mode": "youtube",
            "detected_mode": "youtube", "language": "auto", "evidence_level": "controlled_runtime",
            "analysis_content_allowed": True, "reuse_allowed": False, "usage_mode": "analysis-paraphrase-only",
            "rights_basis": "analysis-paraphrase-only", "audio_access_authorized": False,
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(), "content_chars": len(content), "content_persisted": True,
            "metadata": {"youtube": {"scope": "video", "media_downloaded": False}},
            "tool_versions": {"yt-dlp": "x", "ffmpeg": "x", "ffprobe": "x", "trafilatura": "x"},
            "source_context": {"source_set_version": "quality"},
        }
        result_path = root / "result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        return result_path

    def run_validator(self, result_path):
        return subprocess.run([sys.executable, str(VALIDATOR), str(result_path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_valid_youtube_artifact_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_valid_results(tmp)
            completed = self.run_validator(result)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_media_file_in_results_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_valid_results(tmp)
            (pathlib.Path(tmp) / "leak.mp4").write_bytes(b"not really media")
            completed = self.run_validator(result)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("media artifact forbidden", completed.stderr)

    def test_persisted_comment_author_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_valid_results(tmp)
            comments_path = pathlib.Path(tmp) / "items" / "v1" / "comments.json"
            comments_path.write_text(json.dumps([{"id": "c1", "text": "x", "author": "Person"}]), encoding="utf-8")
            completed = self.run_validator(result)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("comment identity field", completed.stderr)

    def test_content_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_valid_results(tmp)
            (pathlib.Path(tmp) / "content.md").write_text("tampered\n", encoding="utf-8")
            completed = self.run_validator(result)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("SHA-256 mismatch", completed.stderr)


if __name__ == "__main__":
    unittest.main()
