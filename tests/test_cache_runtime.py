import hashlib
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import cache_runtime as m


REQUEST = {
    "schema_version": "2.1",
    "enabled": True,
    "request_id": "request-001",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "video_id": "dQw4w9WgXcQ",
    "source_type": "video",
    "language": "auto",
}


class CacheRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.results = self.root / "results"
        self.results.mkdir()
        self.request_file = self.root / "resolved-request.json"
        self.request_file.write_text(json.dumps(REQUEST), encoding="utf-8")
        self.state = self.root / "state"
        self.env = mock.patch.dict(
            os.environ,
            {
                "REQUEST_FILE": str(self.request_file),
                "TRANSCRIBE_STATE_DIR": str(self.state),
                "TRANSCRIBE_EXECUTION_TARGET": "test",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.old_results = m.RESULTS
        self.old_runtime_results = m.runtime.RESULTS
        m.RESULTS = self.results
        m.runtime.RESULTS = self.results
        self.addCleanup(self.restore_paths)

    def restore_paths(self):
        m.RESULTS = self.old_results
        m.runtime.RESULTS = self.old_runtime_results

    def write_ok_result(self, request=REQUEST, text="hello world\n"):
        result = m.runtime.base_result(request)
        result["status"] = "ok"
        result["caption"] = {
            "language": "en",
            "kind": "manual",
            "format": "vtt",
            "cue_count": 1,
        }
        result["transcript_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        result["transcript_chars"] = len(text)
        m.runtime.write_result(result, text)

    def test_finalize_exports_index_and_precheck_reuses_transcript(self):
        self.write_ok_result()
        self.assertEqual(m.finalize(), 0)
        index = json.loads((self.results / "processed-index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["captions_done"], 1)
        self.assertEqual(index["unique_videos"], 1)
        self.assertEqual(index["processed_entries"], 1)

        for path in self.results.iterdir():
            path.unlink()
        self.assertEqual(m.precheck(), 0)
        result = json.loads((self.results / "result.json").read_text(encoding="utf-8"))
        self.assertTrue(result["cache_hit"])
        self.assertEqual((self.results / "transcript.txt").read_text(encoding="utf-8"), "hello world\n")

    def test_repeated_video_language_is_deduplicated(self):
        self.write_ok_result()
        m.finalize()
        self.write_ok_result()
        m.finalize()
        index = json.loads((self.results / "processed-index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["processed_entries"], 1)
        self.assertEqual(index["items"][0]["attempt_count"], 2)

    def test_same_video_other_language_is_separate_entry(self):
        self.write_ok_result()
        m.finalize()
        other = {**REQUEST, "request_id": "request-002", "language": "nl"}
        self.request_file.write_text(json.dumps(other), encoding="utf-8")
        self.write_ok_result(other, "hallo\n")
        m.finalize()
        index = json.loads((self.results / "processed-index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["unique_videos"], 1)
        self.assertEqual(index["processed_entries"], 2)
        self.assertEqual(index["captions_done"], 2)

    def test_corrupt_cached_transcript_is_not_reused(self):
        self.write_ok_result()
        m.finalize()
        with m.connect() as conn:
            conn.execute(
                "UPDATE processed SET transcript_text = 'tampered' WHERE video_id = ?",
                (REQUEST["video_id"],),
            )
            conn.commit()
        for path in self.results.iterdir():
            path.unlink()
        self.assertEqual(m.precheck(), 0)
        self.assertFalse((self.results / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
