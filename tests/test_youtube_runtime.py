import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "youtube_runtime.py"
spec = importlib.util.spec_from_file_location("youtube_runtime", MODULE_PATH)
youtube_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(youtube_runtime)


class YoutubeRuntimeTests(unittest.TestCase):
    def test_english_manual_beats_dutch_manual(self):
        meta = {"subtitles": {"nl": [{}], "en": [{}]}, "automatic_captions": {}}
        self.assertEqual(youtube_runtime.choose_caption_track(meta), {"language": "en", "kind": "manual"})

    def test_english_auto_beats_dutch_manual_due_language_priority(self):
        meta = {"subtitles": {"nl": [{}]}, "automatic_captions": {"en": [{}]}}
        self.assertEqual(youtube_runtime.choose_caption_track(meta), {"language": "en", "kind": "automatic"})

    def test_dutch_auto_beats_other_manual(self):
        meta = {"subtitles": {"de": [{}]}, "automatic_captions": {"nl-NL": [{}]}}
        self.assertEqual(youtube_runtime.choose_caption_track(meta), {"language": "nl-NL", "kind": "automatic"})

    def test_first_other_manual_is_fallback(self):
        meta = {"subtitles": {"fr": [{}], "de": [{}]}, "automatic_captions": {"es": [{}]}}
        self.assertEqual(youtube_runtime.choose_caption_track(meta), {"language": "de", "kind": "manual"})

    def test_explicit_language_can_override_default_priority(self):
        meta = {"subtitles": {"en": [{}], "fr": [{}]}, "automatic_captions": {}}
        self.assertEqual(youtube_runtime.choose_caption_track(meta, "fr"), {"language": "fr", "kind": "manual"})

    def test_translated_tlang_track_is_not_selected(self):
        meta = {
            "subtitles": {},
            "automatic_captions": {
                "en": [{"url": "https://www.youtube.com/api/timedtext?lang=nl&tlang=en"}],
                "nl": [{"url": "https://www.youtube.com/api/timedtext?lang=nl"}],
            },
        }
        self.assertEqual(youtube_runtime.choose_caption_track(meta), {"language": "nl", "kind": "automatic"})

    def test_subtitle_command_never_downloads_media(self):
        cmd = youtube_runtime.subtitle_command("https://www.youtube.com/watch?v=abc", {"language": "en", "kind": "manual"}, "/tmp/x.%(ext)s")
        self.assertIn("--skip-download", cmd)
        self.assertIn("--no-playlist", cmd)
        self.assertNotIn("-f", cmd)
        self.assertNotIn("-x", cmd)

    def test_comment_command_never_downloads_media(self):
        cmd = youtube_runtime._json_command("https://www.youtube.com/watch?v=abc", comments=True, comment_sort="top", max_comments="200")
        self.assertIn("--skip-download", cmd)
        self.assertIn("--write-comments", cmd)
        joined = " ".join(cmd)
        self.assertIn("comment_sort=top", joined)
        self.assertIn("max_comments=200", joined)

    def test_channel_tab_switches_existing_tab(self):
        self.assertEqual(
            youtube_runtime.channel_tab_url("https://www.youtube.com/@example/videos", "shorts"),
            "https://www.youtube.com/@example/shorts",
        )

    def test_search_source_uses_candidate_limit(self):
        req = {"youtube": {"scope": "search", "query": "seo", "candidate_limit": 123}}
        self.assertEqual(youtube_runtime.discover_source(req), ["ytsearch123:seo"])

    def test_year_and_threshold_filters(self):
        yt = {"year_from": 2025, "year_to": 2026, "min_views": 1000}
        self.assertTrue(youtube_runtime.year_matches({"upload_date": "20251231"}, yt))
        self.assertTrue(youtube_runtime.thresholds_match({"view_count": 1000}, yt))
        self.assertFalse(youtube_runtime.year_matches({"upload_date": "20240101"}, yt))
        self.assertFalse(youtube_runtime.thresholds_match({"view_count": 999}, yt))

    def test_rank_views(self):
        items = [{"meta": {"view_count": 10}}, {"meta": {"view_count": 30}}, {"meta": {}}]
        ranked = youtube_runtime.rank_metadata(items, "views")
        self.assertEqual([x["meta"].get("view_count") for x in ranked], [30, 10, None])


if __name__ == "__main__":
    unittest.main()
