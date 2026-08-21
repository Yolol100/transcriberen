import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("runtime_topic_filter", SCRIPTS / "runtime_topic_filter.py")
runtime_topic_filter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_topic_filter)

RESOLVER_SPEC = importlib.util.spec_from_file_location("resolve_request_hardened", SCRIPTS / "resolve_request_hardened.py")
resolve_request_hardened = importlib.util.module_from_spec(RESOLVER_SPEC)
RESOLVER_SPEC.loader.exec_module(resolve_request_hardened)


class TopicFilterTests(unittest.TestCase):
    def test_hyphen_underscore_and_space_normalize_equally(self):
        expected = runtime_topic_filter._normalized_tokens("cold email deliverability")
        self.assertEqual(runtime_topic_filter._normalized_tokens("Cold-email deliverability"), expected)
        self.assertEqual(runtime_topic_filter._normalized_tokens("COLD_EMAIL deliverability"), expected)

    def test_keyword_phrase_matches_metadata_tokens(self):
        meta = {
            "title": "Cold Email Deliverability in 2026",
            "description": "How to improve inbox placement.",
            "tags": ["outbound", "email"],
        }
        self.assertTrue(
            runtime_topic_filter.include_keywords_match(meta, {"include_keywords": ["cold-email"]})
        )
        self.assertTrue(
            runtime_topic_filter.include_keywords_match(meta, {"include_keywords": ["COLD_EMAIL"]})
        )
        self.assertFalse(
            runtime_topic_filter.include_keywords_match(meta, {"include_keywords": ["technical seo"]})
        )

    def test_keyword_phrases_are_or_filters(self):
        meta = {"title": "Technical SEO audit", "description": "", "tags": [], "categories": []}
        self.assertTrue(
            runtime_topic_filter.include_keywords_match(
                meta, {"include_keywords": ["cold email", "technical-seo"]}
            )
        )

    def test_topic_filter_forces_full_configured_scan_window(self):
        req = {
            "youtube": {
                "scope": "channel_all",
                "sort_by": "relevance",
                "max_items": 7,
                "scan_limit": 250,
                "include_keywords": ["cold email"],
            }
        }
        self.assertEqual(runtime_topic_filter._topic_aware_playlist_end(req), 250)

    def test_no_topic_filter_preserves_existing_early_limit(self):
        req = {
            "youtube": {
                "scope": "channel_all",
                "sort_by": "relevance",
                "max_items": 7,
                "scan_limit": 250,
                "include_keywords": [],
            }
        }
        self.assertEqual(runtime_topic_filter._topic_aware_playlist_end(req), 7)

    def test_metadata_prefers_innertube_before_ytdlp(self):
        with patch.object(
            runtime_topic_filter.innertube_runtime,
            "metadata_for",
            return_value={"id": "inner", "view_count": 10},
        ) as inner, patch.object(runtime_topic_filter, "_ORIGINAL_METADATA_FOR") as ytdlp:
            result = runtime_topic_filter.metadata_for_with_client_fallback(
                "https://www.youtube.com/watch?v=video-1"
            )
        self.assertEqual(result["id"], "inner")
        inner.assert_called_once()
        ytdlp.assert_not_called()

    def test_metadata_fallback_tries_default_then_anonymous_client(self):
        with patch.object(
            runtime_topic_filter.innertube_runtime,
            "metadata_for",
            side_effect=RuntimeError("innertube unavailable"),
        ), patch.object(
            runtime_topic_filter,
            "_ORIGINAL_METADATA_FOR",
            side_effect=[RuntimeError("confirm you're not a bot"), {"id": "video-1"}],
        ) as mocked:
            result = runtime_topic_filter.metadata_for_with_client_fallback("https://www.youtube.com/watch?v=video-1")
        self.assertEqual(result["id"], "video-1")
        self.assertEqual(mocked.call_args_list[0].kwargs["player_client"], None)
        self.assertEqual(mocked.call_args_list[1].kwargs["player_client"], "tv")

    def test_metadata_missing_required_engagement_falls_back_to_ytdlp(self):
        with patch.object(
            runtime_topic_filter.innertube_runtime,
            "metadata_for",
            return_value={"id": "inner", "view_count": 10},
        ) as inner, patch.object(
            runtime_topic_filter,
            "_ORIGINAL_METADATA_FOR",
            return_value={"id": "yt", "like_count": 4},
        ) as ytdlp:
            result = runtime_topic_filter.metadata_for_with_client_fallback(
                "https://www.youtube.com/watch?v=video-1",
                youtube_options={"sort_by": "likes"},
            )
        self.assertEqual(result["id"], "yt")
        self.assertTrue(inner.call_args.kwargs["include_engagement"])
        self.assertEqual(ytdlp.call_args.kwargs["player_client"], None)

    def test_explicit_metadata_client_does_not_expand_fallbacks(self):
        with patch.object(runtime_topic_filter, "_ORIGINAL_METADATA_FOR", return_value={"id": "x"}) as mocked, \
             patch.object(runtime_topic_filter.innertube_runtime, "metadata_for") as inner:
            result = runtime_topic_filter.metadata_for_with_client_fallback(
                "https://www.youtube.com/watch?v=x", player_client="mweb"
            )
        self.assertEqual(result["id"], "x")
        mocked.assert_called_once_with("https://www.youtube.com/watch?v=x", player_client="mweb")
        inner.assert_not_called()

    def test_caption_prefers_innertube_then_preserves_ytdlp_fallback(self):
        meta = {
            "_innertube_player_client": "ANDROID",
            "automatic_captions": {"en": [{"url": "https://www.youtube.com/api/timedtext?lang=en"}]},
        }
        with patch.object(
            runtime_topic_filter.innertube_runtime,
            "download_caption",
            return_value=("Inner text", {"provider": "innertube"}),
        ), patch.object(runtime_topic_filter, "_ORIGINAL_DOWNLOAD_CAPTION") as ytdlp:
            text, info = runtime_topic_filter.download_caption_with_provider_fallback(
                "https://www.youtube.com/watch?v=x", meta
            )
        self.assertEqual(text, "Inner text")
        self.assertEqual(info["provider"], "innertube")
        ytdlp.assert_not_called()

    def test_comments_prefer_innertube_and_reuse_privacy_normalization(self):
        req = {
            "youtube": {
                "comment_sort": "top",
                "max_comments": "20",
                "include_replies": False,
            }
        }
        payload = {
            "comment_count": 1,
            "comments": [{"id": "c1", "parent": "root", "text": "Useful SEO observation", "like_count": 2}],
        }
        with patch.object(runtime_topic_filter.innertube_runtime, "comments_payload", return_value=payload), \
             patch.object(runtime_topic_filter, "_ORIGINAL_COMMENTS_FOR") as ytdlp:
            comments, summary = runtime_topic_filter.comments_for_with_client_fallback(
                "https://www.youtube.com/watch?v=x", req, 1
            )
        self.assertEqual(len(comments), 1)
        self.assertEqual(summary["stored"], 1)
        ytdlp.assert_not_called()

    def test_comment_fallback_preserves_bounds_and_uses_anonymous_client(self):
        req = {
            "youtube": {
                "comment_sort": "top",
                "max_comments": "20",
                "include_replies": False,
            }
        }
        payload = {
            "comment_count": 1,
            "comments": [{"id": "c1", "parent": "root", "text": "Useful SEO observation", "like_count": 2}],
        }
        with patch.object(runtime_topic_filter.innertube_runtime, "comments_payload", side_effect=RuntimeError("inner bot")), \
             patch.object(runtime_topic_filter, "_ORIGINAL_COMMENTS_FOR", side_effect=RuntimeError("bot")), \
             patch.object(runtime_topic_filter.youtube_runtime, "load_json", return_value=payload) as load_json:
            comments, summary = runtime_topic_filter.comments_for_with_client_fallback(
                "https://www.youtube.com/watch?v=x", req, 1
            )
        self.assertEqual(len(comments), 1)
        self.assertEqual(summary["limit"], 20)
        command = load_json.call_args.args[0]
        self.assertIn("player_client=tv", " ".join(command))
        self.assertIn("max_comments=20,20,0,0,1", " ".join(command))

    def test_resolver_accepts_comma_separated_keywords_and_deduplicates(self):
        req = {"youtube": {"include_keywords": "cold-email, technical seo, COLD_EMAIL, cold email"}}
        result = resolve_request_hardened._normalize_include_keywords(req)
        self.assertEqual(result["youtube"]["include_keywords"], ["cold-email", "technical seo"])

    def test_resolver_rejects_too_many_keywords(self):
        req = {"youtube": {"include_keywords": [f"topic-{i}" for i in range(31)]}}
        with self.assertRaisesRegex(ValueError, "at most 30"):
            resolve_request_hardened._normalize_include_keywords(req)

    def test_resolver_rejects_separator_only_keyword(self):
        req = {"youtube": {"include_keywords": ["---___"]}}
        with self.assertRaisesRegex(ValueError, "searchable characters"):
            resolve_request_hardened._normalize_include_keywords(req)

    def test_workflow_dispatch_prefers_materialized_request_json(self):
        payload = {
            "enabled": False,
            "request_id": "manual-json-test",
            "youtube": {"include_keywords": "cold_email, technical-seo"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            request_file = pathlib.Path(tmp) / "incoming-request.json"
            request_file.write_text(json.dumps(payload), encoding="utf-8")
            with patch.dict(
                os.environ,
                {"GITHUB_EVENT_NAME": "workflow_dispatch", "REQUEST_FILE": str(request_file)},
                clear=False,
            ):
                resolved = resolve_request_hardened._request_from_environment()
        self.assertEqual(resolved["request_id"], "manual-json-test")
        self.assertEqual(resolved["youtube"]["include_keywords"], ["cold_email", "technical-seo"])

    def test_webvtt_bom_and_short_timestamps_are_removed(self):
        payload = (
            "\ufeffWEBVTT\n\n"
            "intro-cue\n"
            "00:01.000 --> 00:02.500\n"
            "<v Speaker>Hello world</v>\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "sample.vtt"
            path.write_text(payload, encoding="utf-8")
            normalized = runtime_topic_filter.normalize_subtitles_hardened(path)
        self.assertEqual(normalized, "Hello world")

    def test_webvtt_note_style_region_and_cue_ids_do_not_leak(self):
        payload = (
            "WEBVTT\n"
            "Kind: captions\n"
            "Language: en\n\n"
            "STYLE\n"
            "::cue { color: lime; }\n\n"
            "REGION\n"
            "id:fred\n"
            "width:40%\n\n"
            "NOTE internal metadata\n"
            "do not emit this\n\n"
            "arbitrary-cue-id\n"
            "00:00:03.000 --> 00:00:04.000 position:50%\n"
            "Visible caption\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "sample.vtt"
            path.write_text(payload, encoding="utf-8")
            normalized = runtime_topic_filter.normalize_subtitles_hardened(path)
        self.assertEqual(normalized, "Visible caption")


if __name__ == "__main__":
    unittest.main()
