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

    def test_channel_root_expands_to_all_public_channel_tabs(self):
        self.assertEqual(
            entrypoint.collection_targets("https://www.youtube.com/@OpenAI"),
            [
                "https://www.youtube.com/@OpenAI/videos",
                "https://www.youtube.com/@OpenAI/shorts",
                "https://www.youtube.com/@OpenAI/streams",
            ],
        )

    def test_explicit_channel_tab_is_not_expanded_again(self):
        self.assertEqual(
            entrypoint.collection_targets("https://www.youtube.com/@OpenAI/shorts"),
            ["https://www.youtube.com/@OpenAI/shorts"],
        )

    def test_playlist_url_is_preserved(self):
        url = "https://www.youtube.com/playlist?list=PL123"
        self.assertEqual(entrypoint.collection_targets(url), [url])

    def test_zero_max_items_uses_safety_cap_and_accountless_flags(self):
        captured = []

        def fake_run(command, check=False):
            captured.append(command)
            return types.SimpleNamespace(returncode=0, stdout='{"id":"abcdefghijk","title":"One"}\n', stderr="")

        entrypoint.runtime.run = fake_run
        videos = entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 0)
        self.assertEqual(len(videos), 1)
        self.assertEqual(len(captured), 3)
        first = captured[0]
        index = first.index("--playlist-end")
        self.assertEqual(first[index + 1], str(entrypoint.MAX_COLLECTION_VIDEOS + 1))
        self.assertIn("--skip-download", first)
        self.assertIn("--no-cookies", first)
        self.assertNotIn("--no-netrc", first)
        self.assertNotIn("--no-playlist", first)

    def test_duplicates_across_tabs_are_returned_once(self):
        def fake_run(command, check=False):
            return types.SimpleNamespace(returncode=0, stdout='{"id":"abcdefghijk","title":"One"}\n', stderr="")

        entrypoint.runtime.run = fake_run
        videos = entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 0)
        self.assertEqual([video["id"] for video in videos], ["abcdefghijk"])

    def test_positive_max_items_is_bounded(self):
        captured = []

        def fake_run(command, check=False):
            captured.append(command)
            return types.SimpleNamespace(returncode=0, stdout='{"id":"abcdefghijk","title":"One"}\n', stderr="")

        entrypoint.runtime.run = fake_run
        entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 25)
        index = captured[0].index("--playlist-end")
        self.assertEqual(captured[0][index + 1], "26")


if __name__ == "__main__":
    unittest.main()
