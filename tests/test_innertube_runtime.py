import json
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import innertube_runtime as m


class FakeResponse:
    def __init__(self, raw, status=200):
        self.raw = raw
        self.status = status

    def read(self, n=-1):
        return self.raw[:n] if n >= 0 else self.raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Tests(unittest.TestCase):
    def setUp(self):
        m.reset_diagnostics()

    def test_video_id_variants(self):
        self.assertEqual(m.video_id_from_url("https://youtu.be/abcDEF_12-3"), "abcDEF_12-3")
        self.assertEqual(m.video_id_from_url("https://www.youtube.com/watch?v=abcDEF_12-3"), "abcDEF_12-3")
        self.assertEqual(m.video_id_from_url("https://www.youtube.com/shorts/abcDEF_12-3"), "abcDEF_12-3")

    def test_player_falls_back_android_to_ios(self):
        player = {
            "playabilityStatus": {"status": "OK"},
            "videoDetails": {"videoId": "abc123xyz00", "title": "T", "author": "A", "lengthSeconds": "12", "viewCount": "34"},
            "microformat": {"playerMicroformatRenderer": {"uploadDate": "2026-08-20", "category": "Education"}},
            "captions": {"playerCaptionsTracklistRenderer": {"captionTracks": [
                {"baseUrl": "https://www.youtube.com/api/timedtext?lang=en", "languageCode": "en", "kind": "asr", "name": {"simpleText": "English"}}
            ]}},
        }
        with patch.object(m, "_post_json", side_effect=[m.InnerTubeError("blocked"), player]) as post:
            meta = m.metadata_for("https://www.youtube.com/watch?v=abc123xyz00")
        self.assertEqual(meta["id"], "abc123xyz00")
        self.assertEqual(meta["upload_date"], "20260820")
        self.assertIn("en", meta["automatic_captions"])
        self.assertEqual(post.call_args_list[0].args[2], "ANDROID")
        self.assertEqual(post.call_args_list[1].args[2], "IOS")

    def test_translated_track_is_excluded(self):
        data = {"captions": {"playerCaptionsTracklistRenderer": {"captionTracks": [
            {"baseUrl": "https://www.youtube.com/api/timedtext?lang=nl&tlang=en", "languageCode": "en", "name": {"simpleText": "English"}},
            {"baseUrl": "https://www.youtube.com/api/timedtext?lang=nl", "languageCode": "nl", "kind": "asr", "name": {"simpleText": "Dutch"}},
        ]}}}
        manual, automatic = m._caption_track_entries(data, "ANDROID")
        self.assertEqual(manual, {})
        self.assertIn("nl", automatic)
        self.assertNotIn("en", automatic)

    def test_json3_caption_download(self):
        meta = {
            "automatic_captions": {"en": [{"url": "https://www.youtube.com/api/timedtext?lang=en", "_innertube_client": "ANDROID"}]},
            "subtitles": {},
        }
        payload = json.dumps({"events": [
            {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "Hello world"}]},
            {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": "Hello world again"}]},
        ]}).encode()
        with patch.object(m, "_request_bytes", return_value=(payload, 200)):
            text, info = m.download_caption(meta, {"language": "en", "kind": "automatic"})
        self.assertEqual(text, "Hello world\nagain")
        self.assertEqual(info["provider"], "innertube")
        self.assertEqual(info["cue_count"], 2)

    def test_comment_pagination_is_bounded(self):
        initial = {
            "contents": {"itemSectionRenderer": {"sectionIdentifier": "comment-item-section", "contents": [
                {"continuationItemRenderer": {"continuationEndpoint": {"continuationCommand": {"token": "p1"}}}}
            ]}}
        }
        page1 = {
            "frameworkUpdates": {"entityBatchUpdate": {"mutations": [
                {"payload": {"commentEntityPayload": {"key": "k1", "properties": {"commentId": "c1", "content": {"content": "One"}}, "toolbar": {"likeCountNotliked": "5"}}}}
            ]}},
            "onResponseReceivedEndpoints": [{"appendContinuationItemsAction": {"continuationItems": [
                {"continuationItemRenderer": {"continuationEndpoint": {"continuationCommand": {"token": "p2"}}}}
            ]}}],
        }
        page2 = {
            "frameworkUpdates": {"entityBatchUpdate": {"mutations": [
                {"payload": {"commentEntityPayload": {"key": "k2", "properties": {"commentId": "c2", "content": {"content": "Two"}}, "toolbar": {"likeCountNotliked": "2"}}}}
            ]}},
            "onResponseReceivedEndpoints": [],
        }
        with patch.object(m, "_post_json", side_effect=[initial, page1, page2]) as post:
            result = m.comments_payload("https://www.youtube.com/watch?v=abc123xyz00", max_comments="2")
        self.assertEqual([x["id"] for x in result["comments"]], ["c1", "c2"])
        self.assertEqual(post.call_count, 3)

    def test_comments_fail_closed_for_replies_or_new_sort(self):
        with self.assertRaises(m.InnerTubeUnsupported):
            m.comments_payload("https://www.youtube.com/watch?v=abc123xyz00", include_replies=True)
        with self.assertRaises(m.InnerTubeUnsupported):
            m.comments_payload("https://www.youtube.com/watch?v=abc123xyz00", comment_sort="new")

    def test_post_request_has_no_cookie(self):
        captured = {}

        def fake_open(request):
            captured["headers"] = dict(request.header_items())
            return FakeResponse(b"{}")

        with patch.object(m, "_open", side_effect=fake_open):
            m._post_json(m.NEXT_ENDPOINT, {"videoId": "abc123xyz00"}, "WEB")
        self.assertNotIn("Cookie", captured["headers"])
        self.assertEqual(captured["headers"].get("Content-type"), "application/json")

    def test_metadata_engagement_is_additive_and_optional(self):
        player = {
            "playabilityStatus": {"status": "OK"},
            "videoDetails": {"videoId": "abc123xyz00", "title": "T", "author": "A", "lengthSeconds": "12", "viewCount": "34"},
            "captions": {"playerCaptionsTracklistRenderer": {"captionTracks": []}},
        }
        next_data = {
            "contents": {"videoViewCountRenderer": {"viewCount": {"simpleText": "1,234 views"}}},
            "segmentedLikeDislikeButtonViewModel": {"title": "56"},
            "engagementPanelSectionListRenderer": {
                "panelIdentifier": "engagement-panel-comments-section",
                "contextualInfo": {"runs": [{"text": "78"}]},
            },
        }
        with patch.object(m, "_post_json", side_effect=[player, next_data]):
            meta = m.metadata_for("https://www.youtube.com/watch?v=abc123xyz00", include_engagement=True)
        self.assertEqual(meta["view_count"], 1234)
        self.assertEqual(meta["like_count"], 56)
        self.assertEqual(meta["comment_count"], 78)

    def test_opener_explicitly_disables_environment_proxies(self):
        proxy_handlers = [h for h in m._OPENER.handlers if isinstance(h, m.urllib.request.ProxyHandler)]
        self.assertEqual(proxy_handlers, [])

    def test_web_next_uses_reviewed_public_client_config(self):
        self.assertEqual(
            m._WEB_API_KEY_B64,
            "QUl6YVN5QU9fRkoyU2xxVThRNFNURUhMR0NpbHdfWTlfMTFxY1c4",
        )
        url = m._endpoint_for_client(m.NEXT_ENDPOINT, "WEB")
        self.assertIn("key=", url)
        self.assertNotIn("key=", m._endpoint_for_client(m.PLAYER_ENDPOINT, "ANDROID"))


if __name__ == "__main__":
    unittest.main()
