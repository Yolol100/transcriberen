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
