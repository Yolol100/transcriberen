import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "caption_client_profiles", ROOT / "scripts" / "caption_client_profiles.py"
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class FakeRuntime:
    class InnerTubeError(RuntimeError):
        pass

    class InnerTubeUnsupported(InnerTubeError):
        pass

    WEB_API_KEY = "public-key"
    PLAYER_ENDPOINT = "https://original.invalid/player"
    CLIENTS = {"ANDROID": {"clientName": "ANDROID", "clientVersion": "1", "userAgent": "ua"}}
    PLAYER_CLIENT_ORDER = ("ANDROID",)
    YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com"}

    def __init__(self, track_list=b"<transcript_list />", player_success=True):
        self.calls = []
        self.track_list = track_list
        self.player_success = player_success
        self.records = []

    def video_id_from_url(self, url):
        return "abc123xyz00"

    def _request_bytes(self, url, client_name="WEB"):
        self.calls.append(("http", url, client_name))
        return self.track_list, 200

    def _record(self, *args):
        self.records.append(args)

    def metadata_for(self, url, include_engagement=False):
        self.calls.append(("player", self.PLAYER_ENDPOINT, url, include_engagement))
        if not self.player_success or "youtubei.googleapis.com" in self.PLAYER_ENDPOINT:
            raise RuntimeError("player blocked")
        return {"id": "abc123xyz00", "subtitles": {"en": [{"url": "https://www.youtube.com/api/timedtext"}]}}


class CaptionClientProfilesTests(unittest.TestCase):
    def test_client_order_is_caption_first(self):
        self.assertEqual(
            m.PLAYER_CLIENT_ORDER,
            ("ANDROID_VR", "IOS", "TVHTML5_SIMPLY_EMBEDDED_PLAYER", "MWEB", "ANDROID"),
        )

    def test_profiles_do_not_contain_cookie_proxy_or_token_fields(self):
        text = (ROOT / "scripts" / "caption_client_profiles.py").read_text(encoding="utf-8").casefold()
        self.assertNotIn("cookie\"", text)
        self.assertNotIn("proxy_url", text)
        self.assertNotIn("po_token", text)

    def test_public_key_is_added_without_replacing_existing_query(self):
        url = m._with_public_key("https://x.test/player?prettyPrint=false", "abc")
        self.assertIn("prettyPrint=false", url)
        self.assertIn("key=abc", url)

    def test_metadata_falls_back_between_public_hosts_and_restores_endpoint(self):
        runtime = FakeRuntime()
        result = m.metadata_for(runtime, "https://youtu.be/abc123xyz00")
        self.assertEqual(result["id"], "abc123xyz00")
        player_calls = [call for call in runtime.calls if call[0] == "player"]
        self.assertEqual(len(player_calls), 2)
        self.assertIn("youtubei.googleapis.com", player_calls[0][1])
        self.assertIn("www.youtube.com", player_calls[1][1])
        self.assertEqual(runtime.PLAYER_ENDPOINT, "https://original.invalid/player")

    def test_timedtext_track_list_builds_compatible_caption_metadata(self):
        xml = (
            b'<transcript_list><track id="0" name="Automatic" lang_code="en" '
            b'lang_original="English" kind="asr" /></transcript_list>'
        )
        runtime = FakeRuntime(track_list=xml, player_success=False)
        result = m.metadata_for(runtime, "https://youtu.be/abc123xyz00")
        self.assertTrue(result["_timedtext_direct"])
        self.assertIn("en", result["automatic_captions"])
        entry = result["automatic_captions"]["en"][0]
        self.assertIn("video.google.com/timedtext", entry["url"])
        self.assertIn("type=track", entry["url"])
        self.assertEqual(entry["_innertube_client"], "WEB")

    def test_timedtext_xml_rejects_dtd(self):
        runtime = FakeRuntime()
        with self.assertRaises(runtime.InnerTubeError):
            m._parse_track_list(runtime, b'<!DOCTYPE x><transcript_list />')

    def test_example_request_is_caption_only(self):
        sample = ROOT / "requests" / "transcribe.json"
        data = json.loads(sample.read_text(encoding="utf-8"))
        yt = data["youtube"]
        self.assertFalse(yt["include_comments"])
        self.assertEqual(yt["max_comments"], "0")
        self.assertEqual(yt["max_items"], 1)
        self.assertNotIn("knowledge_context", data)

    def test_apply_adds_profiles_and_timedtext_host(self):
        runtime = FakeRuntime()
        m.apply(runtime)
        self.assertIn("ANDROID", runtime.CLIENTS)
        self.assertIn("ANDROID_VR", runtime.CLIENTS)
        self.assertIn("video.google.com", runtime.YOUTUBE_HOSTS)
        self.assertEqual(runtime.PLAYER_CLIENT_ORDER[0], "ANDROID_VR")


if __name__ == "__main__":
    unittest.main()
