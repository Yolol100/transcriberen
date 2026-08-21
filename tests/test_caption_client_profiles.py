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

    WEB_API_KEY = "public-key"
    PLAYER_ENDPOINT = "https://original.invalid/player"
    CLIENTS = {"ANDROID": {"clientName": "ANDROID", "clientVersion": "1", "userAgent": "ua"}}
    PLAYER_CLIENT_ORDER = ("ANDROID",)

    def __init__(self):
        self.calls = []

    def metadata_for(self, url, include_engagement=False):
        self.calls.append((self.PLAYER_ENDPOINT, url, include_engagement))
        if "youtubei.googleapis.com" in self.PLAYER_ENDPOINT:
            raise RuntimeError("first host blocked")
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
        self.assertEqual(len(runtime.calls), 2)
        self.assertIn("youtubei.googleapis.com", runtime.calls[0][0])
        self.assertIn("www.youtube.com", runtime.calls[1][0])
        self.assertEqual(runtime.PLAYER_ENDPOINT, "https://original.invalid/player")

    def test_example_request_is_caption_only(self):
        sample = ROOT / "requests" / "transcribe.json"
        data = json.loads(sample.read_text(encoding="utf-8"))
        yt = data["youtube"]
        self.assertFalse(yt["include_comments"])
        self.assertEqual(yt["max_comments"], "0")
        self.assertEqual(yt["max_items"], 1)
        self.assertNotIn("knowledge_context", data)

    def test_apply_adds_profiles_without_removing_existing_android(self):
        runtime = FakeRuntime()
        m.apply(runtime)
        self.assertIn("ANDROID", runtime.CLIENTS)
        self.assertIn("ANDROID_VR", runtime.CLIENTS)
        self.assertEqual(runtime.PLAYER_CLIENT_ORDER[0], "ANDROID_VR")


if __name__ == "__main__":
    unittest.main()
