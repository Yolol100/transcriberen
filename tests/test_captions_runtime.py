import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("captions_runtime", ROOT / "scripts" / "captions_runtime.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class CaptionsRuntimeTests(unittest.TestCase):
    def test_manual_english_beats_automatic_english(self):
        meta = {
            "subtitles": {"en": [{"url": "https://www.youtube.com/api/timedtext?lang=en"}]},
            "automatic_captions": {"en": [{"url": "https://www.youtube.com/api/timedtext?lang=en&kind=asr"}]},
        }
        self.assertEqual(m.choose_caption_track(meta), {"language": "en", "kind": "manual"})

    def test_automatic_english_beats_manual_dutch(self):
        meta = {
            "subtitles": {"nl": [{"url": "https://www.youtube.com/api/timedtext?lang=nl"}]},
            "automatic_captions": {"en": [{"url": "https://www.youtube.com/api/timedtext?lang=en&kind=asr"}]},
        }
        self.assertEqual(m.choose_caption_track(meta), {"language": "en", "kind": "automatic"})

    def test_translated_tracks_are_not_selected(self):
        meta = {
            "automatic_captions": {
                "en": [{"url": "https://www.youtube.com/api/timedtext?lang=nl&tlang=en"}],
                "nl": [{"url": "https://www.youtube.com/api/timedtext?lang=nl"}],
            }
        }
        self.assertEqual(m.choose_caption_track(meta), {"language": "nl", "kind": "automatic"})

    def test_no_tracks_returns_none(self):
        self.assertIsNone(m.choose_caption_track({"subtitles": {}, "automatic_captions": {}}))

    def test_access_block_is_classified(self):
        self.assertEqual(m.classify_failure("Sign in to confirm you're not a bot"), "access_blocked")

    def test_vtt_parser_removes_rolling_overlap(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "sample.vtt"
            path.write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello world\n\n"
                "00:00:02.000 --> 00:00:04.000\nhello world again\n",
                encoding="utf-8",
            )
            segments = m.subtitle_segments(path)
        self.assertEqual([item["text"] for item in segments], ["hello world", "again"])

    def test_no_captions_is_clean_skip_without_project_truth(self):
        request = {
            "request_id": "request-001",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "video_id": "dQw4w9WgXcQ",
            "source_type": "video",
            "language": "auto",
        }
        with tempfile.TemporaryDirectory() as td:
            request_file = pathlib.Path(td) / "resolved.json"
            request_file.write_text(json.dumps(request), encoding="utf-8")
            old_results = m.RESULTS
            m.RESULTS = pathlib.Path(td) / "results"
            try:
                with mock.patch.object(m, "load_metadata", return_value={"subtitles": {}, "automatic_captions": {}}), \
                     mock.patch.object(m, "runtime_provenance", return_value={"execution_target": "test"}), \
                     mock.patch.dict(m.os.environ, {"REQUEST_FILE": str(request_file)}, clear=False):
                    m.main()
                result = json.loads((m.RESULTS / "result.json").read_text(encoding="utf-8"))
                self.assertEqual(result["status"], "skipped_no_captions")
                self.assertNotIn("source_context", result)
                self.assertFalse((m.RESULTS / "transcript.txt").exists())
            finally:
                m.RESULTS = old_results


if __name__ == "__main__":
    unittest.main()
