import importlib.util
import pathlib
import sys
import unittest

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
    def test_hyphen_and_space_normalize_equally(self):
        self.assertEqual(
            runtime_topic_filter._normalized_tokens("Cold-email deliverability"),
            runtime_topic_filter._normalized_tokens("cold email deliverability"),
        )

    def test_keyword_phrase_matches_metadata_tokens(self):
        meta = {
            "title": "Cold Email Deliverability in 2026",
            "description": "How to improve inbox placement.",
            "tags": ["outbound", "email"],
        }
        self.assertTrue(
            runtime_topic_filter.include_keywords_match(meta, {"include_keywords": ["cold-email"]})
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
        req = {"youtube": {"include_keywords": "cold-email, technical seo, COLD-EMAIL"}}
        result = resolve_request_hardened._normalize_include_keywords(req)
        self.assertEqual(result["youtube"]["include_keywords"], ["cold-email", "technical seo"])

    def test_resolver_rejects_too_many_keywords(self):
        req = {"youtube": {"include_keywords": [f"topic-{i}" for i in range(31)]}}
        with self.assertRaisesRegex(ValueError, "at most 30"):
            resolve_request_hardened._normalize_include_keywords(req)


if __name__ == "__main__":
    unittest.main()
