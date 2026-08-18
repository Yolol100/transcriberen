import importlib.util
import pathlib
import tempfile
import unittest
import sys
import types
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

youtube_runtime = load("youtube_runtime_audit", ROOT / "scripts" / "youtube_runtime.py")
sys.modules["youtube_runtime"] = youtube_runtime
trafilatura_stub = types.SimpleNamespace(__version__="2.1.0", extract=lambda *a, **k: "stub article text " * 10)
sys.modules.setdefault("trafilatura", trafilatura_stub)
runtime = load("runtime_audit", ROOT / "scripts" / "runtime.py")


class CommentHardeningTests(unittest.TestCase):
    def test_comment_text_is_redacted_and_identity_removed(self):
        raw = [{
            "id": "c1", "parent": "root", "author": "Person", "author_id": "U1", "author_url": "https://youtube/a",
            "text": "Mail me at person@example.com or +31 6 12345678 @handle https://example.com/x",
            "author_is_uploader": True, "like_count": 25, "is_pinned": True,
        }]
        comments = youtube_runtime.normalized_comments(raw, "all")
        self.assertEqual(len(comments), 1)
        comment = comments[0]
        for key in ("id", "parent", "author", "author_id", "author_url"):
            self.assertNotIn(key, comment)
        self.assertTrue(comment["text_redacted"])
        self.assertNotIn("person@example.com", comment["text"])
        self.assertIn("email", comment["redactions"])

    def test_knowledge_ranking_prefers_creator_pinned_goal_match(self):
        comments = [
            {"comment_ref": "sha256:a", "text": "generic note", "like_count": 100},
            {"comment_ref": "sha256:b", "text": "WordPress cache invalidation rule explained in detail", "like_count": 2,
             "author_is_uploader": True, "is_pinned": True},
        ]
        ranked = youtube_runtime.rank_comment_candidates(comments, {"goal": "WordPress cache rule", "keywords": ["invalidation"]}, 10)
        self.assertEqual(ranked[0]["comment_ref"], "sha256:b")
        self.assertTrue(ranked[0]["untrusted_source_text"])
        self.assertIn("creator", ranked[0]["signals"])

    def test_comment_disabled_is_distinct(self):
        self.assertEqual(youtube_runtime.classify_comment_error("Comments are disabled for this video"), "comments_disabled")
        self.assertEqual(youtube_runtime.classify_comment_error("temporary socket error"), "error")


class CaptionProvenanceTests(unittest.TestCase):
    def test_subtitle_segments_keep_source_time(self):
        raw = """WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nHello world\n\n00:00:02.500 --> 00:00:04.000\nworld again\n"""
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "x.vtt"
            path.write_text(raw, encoding="utf-8")
            segments = youtube_runtime.subtitle_segments(path)
        self.assertEqual(segments[0]["start"], "00:00:01.000")
        self.assertIn("text", segments[0])


class RobotsAndNetworkTests(unittest.TestCase):
    def test_robots_longest_match_allow_wins_tie(self):
        rules, _ = runtime.parse_robots("User-agent: *\nDisallow: /private\nAllow: /private/public\n")
        self.assertFalse(rules.can_fetch("Webactueel-Transcriberen", "https://example.com/private/x"))
        self.assertTrue(rules.can_fetch("Webactueel-Transcriberen", "https://example.com/private/public/x"))

    def test_robots_5xx_blocks(self):
        runtime._ROBOTS_CACHE.clear()
        with mock.patch.object(runtime, "_fetch_with_redirects", return_value={"status": 503, "data": b"", "headers": {}, "url": "https://example.com/robots.txt"}):
            allowed, _, status = runtime.robots_policy("https://example.com/page")
        self.assertFalse(allowed)
        self.assertEqual(status, "unreachable")

    def test_robots_404_allows(self):
        runtime._ROBOTS_CACHE.clear()
        with mock.patch.object(runtime, "_fetch_with_redirects", return_value={"status": 404, "data": b"", "headers": {}, "url": "https://example.com/robots.txt"}):
            allowed, _, status = runtime.robots_policy("https://example.com/page")
        self.assertTrue(allowed)
        self.assertEqual(status, "unavailable")

    def test_auto_non_youtube_fetches_with_robots_before_media_probe(self):
        req = {"mode": "auto", "url": "https://example.com/page"}
        with mock.patch.object(runtime, "fetch_public", return_value=(b"<html><body>" + b"word " * 50 + b"</body></html>", "https://example.com/page", "text/html", {})), \
             mock.patch.object(runtime, "detect_media") as detect, \
             mock.patch.object(runtime, "article_content", return_value=("text", "article", {}, [])):
            runtime.extract(req)
        detect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
