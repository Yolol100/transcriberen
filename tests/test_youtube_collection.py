import importlib.util
import json
import pathlib
import sys
import types
import unittest


class CaptionUnavailableError(RuntimeError):
    pass


class CaptionAccessError(RuntimeError):
    pass


runtime = types.SimpleNamespace(
    RESULTS=pathlib.Path("results"),
    BIN=pathlib.Path("tools/bin"),
    CaptionUnavailableError=CaptionUnavailableError,
    CaptionAccessError=CaptionAccessError,
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

    def test_duplicate_prefix_does_not_hide_later_unique_items(self):
        by_target = {
            "/videos": ["aaaaaaaaaaa", "bbbbbbbbbbb"],
            "/shorts": ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd"],
            "/streams": [],
        }

        def fake_run(command, check=False):
            target = command[-1]
            limit = int(command[command.index("--playlist-end") + 1])
            suffix = next(key for key in by_target if target.endswith(key))
            rows = [json.dumps({"id": video_id, "title": video_id}) for video_id in by_target[suffix][:limit]]
            return types.SimpleNamespace(returncode=0, stdout="\n".join(rows), stderr="")

        entrypoint.runtime.run = fake_run
        videos = entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 3)
        self.assertEqual([video["id"] for video in videos], ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"])

    def test_positive_max_items_is_bounded(self):
        captured = []

        def fake_run(command, check=False):
            captured.append(command)
            return types.SimpleNamespace(returncode=0, stdout='{"id":"abcdefghijk","title":"One"}\n', stderr="")

        entrypoint.runtime.run = fake_run
        entrypoint.discover_youtube_videos("https://www.youtube.com/@OpenAI", 25)
        index = captured[0].index("--playlist-end")
        self.assertEqual(captured[0][index + 1], "26")

    def test_caption_failures_are_not_all_called_missing_captions(self):
        self.assertEqual(entrypoint.classify_caption_failure(CaptionUnavailableError("none")), "no_usable_captions")
        self.assertEqual(entrypoint.classify_caption_failure(CaptionAccessError("blocked")), "caption_access_error")
        self.assertEqual(entrypoint.classify_caption_failure(RuntimeError("unexpected")), "processing_error")

    def test_scan_status_reports_source_access_block(self):
        counts, status = entrypoint.summarize_items([
            {"status": "caption_access_error"},
            {"status": "no_usable_captions"},
        ])
        self.assertEqual(counts["caption_access_errors"], 1)
        self.assertEqual(counts["captions_unavailable"], 1)
        self.assertEqual(status, "source_access_blocked")

    def test_scan_status_reports_partial_when_some_captions_succeed(self):
        _, status = entrypoint.summarize_items([
            {"status": "captions_collected"},
            {"status": "caption_access_error"},
        ])
        self.assertEqual(status, "partial")

    def test_promotion_status_does_not_request_content_review_without_content(self):
        req = {"reuse_allowed": True}
        blocked = {"captions_collected": 0, "caption_access_errors": 2, "processing_errors": 0}
        empty = {"captions_collected": 0, "caption_access_errors": 0, "processing_errors": 0}
        available = {"captions_collected": 1, "caption_access_errors": 0, "processing_errors": 0}
        self.assertEqual(entrypoint.promotion_status(req, blocked), "source_access_blocked")
        self.assertEqual(entrypoint.promotion_status(req, empty), "no_content")
        self.assertEqual(entrypoint.promotion_status(req, available), "review_required")


if __name__ == "__main__":
    unittest.main()
