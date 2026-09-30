import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import captions_runtime as captions


class HostedProviderTests(unittest.TestCase):
    def setUp(self):
        self.old_metadata_for = captions.caption_profiles.metadata_for
        self.old_caption_download = captions.innertube.download_caption
        self.old_run = captions.run

    def tearDown(self):
        captions.caption_profiles.metadata_for = self.old_metadata_for
        captions.innertube.download_caption = self.old_caption_download
        captions.run = self.old_run

    def test_metadata_prefers_caption_first_provider(self):
        captions.caption_profiles.metadata_for = lambda runtime, url, include_engagement=False: {
            "id": "AAAAAAAAAAA",
            "title": "Hosted",
            "upload_date": "20260930",
            "subtitles": {"en": [{"url": "https://video.google.com/timedtext"}]},
            "automatic_captions": {},
        }
        captions.run = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("yt-dlp fallback should not run"))
        meta = captions.load_metadata("https://www.youtube.com/watch?v=AAAAAAAAAAA")
        self.assertEqual(meta["upload_date"], "20260930")
        self.assertEqual(meta["_metadata_provider"], "caption-first-innertube")

    def test_discovery_date_hint_can_survive_blocked_video_metadata(self):
        captions.caption_profiles.metadata_for = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider blocked"))
        captions.run = lambda command, timeout=240: subprocess.CompletedProcess(
            command, 1, stdout="", stderr="Sign in to confirm you're not a bot"
        )
        meta = captions.load_metadata(
            "https://www.youtube.com/watch?v=BBBBBBBBBBB",
            metadata_hint={"id": "BBBBBBBBBBB", "title": "Hinted", "upload_date": "20260815"},
        )
        self.assertEqual(meta["upload_date"], "20260815")
        self.assertEqual(meta["_metadata_provider"], "channel-discovery")
        self.assertIn("blocked", meta["_metadata_warning"].lower())

    def test_metadata_falls_back_to_yt_dlp_when_needed(self):
        captions.caption_profiles.metadata_for = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable"))
        payload = {
            "id": "CCCCCCCCCCC",
            "title": "Fallback",
            "upload_date": "20260704",
            "subtitles": {},
            "automatic_captions": {},
        }
        captions.run = lambda command, timeout=240: subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload), stderr=""
        )
        meta = captions.load_metadata("https://www.youtube.com/watch?v=CCCCCCCCCCC")
        self.assertEqual(meta["_metadata_provider"], "yt-dlp")
        self.assertEqual(meta["upload_date"], "20260704")

    def test_caption_prefers_innertube_when_metadata_is_caption_first(self):
        captions.innertube.download_caption = lambda meta, track: (
            "hello hosted\n",
            {"language": "en", "kind": "manual", "format": "json3", "_segments": [{"text": "hello hosted"}]},
        )
        captions.run = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("yt-dlp caption fallback should not run"))
        text, info = captions.download_caption(
            "https://www.youtube.com/watch?v=DDDDDDDDDDD",
            {"language": "en", "kind": "manual"},
            meta={
                "_metadata_provider": "caption-first-innertube",
                "_innertube_player_client": "ANDROID",
                "subtitles": {"en": [{"url": "https://www.youtube.com/api/timedtext"}]},
            },
        )
        self.assertEqual(text, "hello hosted\n")
        self.assertNotIn("_segments", info)


if __name__ == "__main__":
    unittest.main()
