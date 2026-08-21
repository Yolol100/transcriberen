import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("runtime_topic_filter_regression", SCRIPTS / "runtime_topic_filter.py")
runtime_topic_filter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime_topic_filter)


class SubtitleNormalizationRegressionTests(unittest.TestCase):
    def test_text_before_blank_cue_boundary_is_preserved(self):
        payload = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "First cue line one\n"
            "First cue line two\n\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "Second cue\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "sample.vtt"
            path.write_text(payload, encoding="utf-8")
            normalized = runtime_topic_filter.normalize_subtitles_hardened(path)
        self.assertEqual(normalized, "First cue line one\nFirst cue line two\nSecond cue")

    def test_numeric_caption_text_is_preserved(self):
        payload = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "2026\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "numeric.vtt"
            path.write_text(payload, encoding="utf-8")
            normalized = runtime_topic_filter.normalize_subtitles_hardened(path)
        self.assertEqual(normalized, "2026")

    def test_metadata_looking_words_inside_cue_are_preserved(self):
        payload = (
            "WEBVTT\n"
            "Kind: captions\n"
            "Language: en\n\n"
            "00:00:00.000 --> 00:00:02.000\n"
            "NOTE this is spoken\n"
            "Language: Dutch\n"
            "STYLE\n"
            "REGION\n\n"
            "NOTE outside-cue metadata\n"
            "this metadata is not caption text\n\n"
            "00:00:02.000 --> 00:00:03.000\n"
            "Final cue\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "context.vtt"
            path.write_text(payload, encoding="utf-8")
            normalized = runtime_topic_filter.normalize_subtitles_hardened(path)
        self.assertEqual(
            normalized,
            "NOTE this is spoken\nLanguage: Dutch\nSTYLE\nREGION\nFinal cue",
        )


if __name__ == "__main__":
    unittest.main()
