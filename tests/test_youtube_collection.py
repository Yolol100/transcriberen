import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


class YoutubeAccessBlocked(RuntimeError):
    pass


def _unpatched(*args, **kwargs):
    raise AssertionError("runtime stub was called without a test patch")


runtime = types.SimpleNamespace(
    RESULTS=pathlib.Path("results"),
    BIN=pathlib.Path("tools/bin"),
    YoutubeAccessBlocked=YoutubeAccessBlocked,
    youtube_access_blocked=lambda stderr: "not a bot" in str(stderr).lower(),
    run=_unpatched,
    media_content=_unpatched,
)
sys.modules.setdefault("runtime", runtime)
MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "entrypoint.py"
spec = importlib.util.spec_from_file_location("entrypoint", MODULE_PATH)
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


class YoutubeCollectionTests(unittest.TestCase):
    def test_channel_handle_is_collection(self):
        self.assertTrue(entrypoint.is_youtube_collection_url("https://www.youtube.com/@OpenAI"))

    def test_playlist_is_collection(self):
        self.assertTrue(entrypoint.is_youtube_collection_url("https://www.youtube.com/playlist?list=PL123"))

    def test_single_video_is_youtube_but_not_collection(self):
        url = "https://www.youtube.com/watch?v=abcdefghijk"
        self.assertTrue(entrypoint.is_youtube_url(url))
        self.assertFalse(entrypoint.is_youtube_collection_url(url))
        self.assertEqual(entrypoint.video_id_from_url(url), "abcdefghijk")

    def test_short_youtube_url_extracts_video_id(self):
        url = "https://youtu.be/abcdefghijk"
        self.assertTrue(entrypoint.is_youtube_url(url))
        self.assertEqual(entrypoint.video_id_from_url(url), "abcdefghijk")

    def test_channel_normalizes_to_videos_tab(self):
        self.assertEqual(entrypoint.normalize_collection_url("https://www.youtube.com/@OpenAI"), "https://www.youtube.com/@OpenAI/videos")

    def test_playlist_url_is_preserved(self):
        url = "https://www.youtube.com/playlist?list=PL123"
        self.assertEqual(entrypoint.normalize_collection_url(url), url)

    def test_zero_max_items_enumerates_complete_collection(self):
        captured = {}

        def fake_run(command, check=False):
            captured["command"] = command
            return types.SimpleNamespace(returncode=0, stdout='{"id":"abcdefghijk","title":"One"}\n', stderr="")

        with patch.object(entrypoint.runtime, "run", fake_run):
            videos = entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 0)
        self.assertEqual(len(videos), 1)
        self.assertNotIn("--playlist-end", captured["command"])
        self.assertIn("--skip-download", captured["command"])

    def test_positive_max_items_is_bounded(self):
        captured = {}

        def fake_run(command, check=False):
            captured["command"] = command
            return types.SimpleNamespace(returncode=0, stdout='{"id":"abcdefghijk","title":"One"}\n', stderr="")

        with patch.object(entrypoint.runtime, "run", fake_run):
            entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 25)
        index = captured["command"].index("--playlist-end")
        self.assertEqual(captured["command"][index + 1], "25")

    def test_collection_discovery_classifies_antibot_block(self):
        def fake_run(command, check=False):
            return types.SimpleNamespace(returncode=1, stdout="", stderr="Sign in to confirm you're not a bot")

        with patch.object(entrypoint.runtime, "run", fake_run):
            with self.assertRaises(YoutubeAccessBlocked):
                entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 10)

    def test_all_blocked_videos_mark_scan_as_access_blocked(self):
        videos = [{
            "id": "abcdefghijk",
            "title": "One",
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
        }]

        def blocked(*args, **kwargs):
            raise YoutubeAccessBlocked("blocked")

        with patch.object(entrypoint, "discover_youtube_videos", return_value=videos), patch.object(entrypoint.runtime, "media_content", blocked):
            _, metadata = entrypoint.collection_content({"url": "https://www.youtube.com/@OpenAI", "max_items": 0})
        self.assertEqual(metadata["scan_status"], "access_blocked")
        self.assertEqual(metadata["access_blocked_items"], 1)
        self.assertEqual(metadata["captions_collected"], 0)

    def test_promotion_status_requires_content_or_blocks(self):
        self.assertEqual(entrypoint.promotion_status("captions_collected"), "review_required")
        self.assertEqual(entrypoint.promotion_status("partial_captions_access_blocked"), "review_required")
        self.assertEqual(entrypoint.promotion_status("no_usable_captions"), "no_content")
        self.assertEqual(entrypoint.promotion_status("access_blocked"), "blocked")


if __name__ == "__main__":
    unittest.main()
