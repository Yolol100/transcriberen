import importlib.util
import pathlib
import sys
import types
import unittest

runtime = types.SimpleNamespace(RESULTS=pathlib.Path("results"), BIN=pathlib.Path("tools/bin"))
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

    def test_single_video_is_not_collection(self):
        self.assertFalse(entrypoint.is_youtube_collection_url("https://www.youtube.com/watch?v=abcdefghijk"))

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

        entrypoint.runtime.run = fake_run
        videos = entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 0)
        self.assertEqual(len(videos), 1)
        self.assertNotIn("--playlist-end", captured["command"])
        self.assertIn("--skip-download", captured["command"])

    def test_positive_max_items_is_bounded(self):
        captured = {}

        def fake_run(command, check=False):
            captured["command"] = command
            return types.SimpleNamespace(returncode=0, stdout='{"id":"abcdefghijk","title":"One"}\n', stderr="")

        entrypoint.runtime.run = fake_run
        entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 25)
        index = captured["command"].index("--playlist-end")
        self.assertEqual(captured["command"][index + 1], "25")


if __name__ == "__main__":
    unittest.main()
