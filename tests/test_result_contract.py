import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_result", ROOT / "scripts" / "validate_result.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class ResultContractTests(unittest.TestCase):
    def base(self, status):
        return {
            "schema_version": "2.1",
            "request_id": "request-001",
            "status": status,
            "source": {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "video_id": "dQw4w9WgXcQ",
                "type": "video",
            },
            "caption": None,
            "transcript_sha256": None,
            "transcript_chars": 0,
            "runtime_provenance": {"execution_target": "test"},
            "media_downloaded": False,
        }

    def run_in_temp(self, result, transcript=None):
        with tempfile.TemporaryDirectory() as td:
            old_results = m.RESULTS
            m.RESULTS = pathlib.Path(td)
            try:
                if transcript is not None:
                    (m.RESULTS / "transcript.txt").write_text(transcript, encoding="utf-8")
                path = m.RESULTS / "result.json"
                path.write_text(json.dumps(result), encoding="utf-8")
                m.validate(path)
            finally:
                m.RESULTS = old_results

    def test_skip_without_transcript_is_valid(self):
        self.run_in_temp(self.base("skipped_no_captions"))

    def test_ok_requires_matching_transcript(self):
        text = "hello world\n"
        result = self.base("ok")
        result["caption"] = {"language": "en", "kind": "manual", "format": "vtt", "cue_count": 1}
        result["transcript_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        result["transcript_chars"] = len(text)
        self.run_in_temp(result, text)

    def test_project_truth_is_rejected(self):
        result = self.base("skipped_no_captions")
        result["source_context"] = {"project_id": "example-project", "source_set_version": "example-version"}
        with self.assertRaisesRegex(ValueError, "project truth"):
            self.run_in_temp(result)

    def test_source_url_must_exactly_match_video_id_and_type(self):
        result = self.base("skipped_no_captions")
        result["source"]["url"] = "https://www.youtube.com/watch?v=AAAAAAAAAAA"
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self.run_in_temp(result)

    def test_real_runtime_requires_pinned_tool_versions(self):
        result = self.base("skipped_no_captions")
        result["runtime_provenance"] = {
            "execution_target": "self-hosted",
            "yt_dlp_version": "wrong",
            "deno_version": "2.9.5",
        }
        with self.assertRaisesRegex(ValueError, "yt-dlp version"):
            self.run_in_temp(result)

    def test_invalid_caption_format_is_rejected(self):
        text = "hello world\n"
        result = self.base("ok")
        result["caption"] = {"language": "en", "kind": "manual", "format": "xml", "cue_count": 1}
        result["transcript_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        result["transcript_chars"] = len(text)
        with self.assertRaisesRegex(ValueError, "vtt or srt"):
            self.run_in_temp(result, text)

    def test_skip_rejects_transcript_file(self):
        with self.assertRaises(ValueError):
            self.run_in_temp(self.base("skipped_no_captions"), "should not exist\n")

    def test_access_block_requires_error(self):
        with self.assertRaises(ValueError):
            self.run_in_temp(self.base("access_blocked"))


if __name__ == "__main__":
    unittest.main()
