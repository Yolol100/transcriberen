import json
import pathlib
import tempfile
import unittest

from scripts.classify_hybrid_result import classify


class HybridResultTests(unittest.TestCase):
    def write_case(self, status="ok", unresolved=None, items=None):
        temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(temp.name)
        (root / "result.json").write_text(json.dumps({"status": status}), encoding="utf-8")
        (root / "manifest.json").write_text(json.dumps({
            "unresolved": unresolved or [],
            "items": items or [],
        }), encoding="utf-8")
        return temp, root / "result.json"

    def test_channel_access_block_requires_fallback(self):
        temp, result = self.write_case(status="access_blocked")
        self.addCleanup(temp.cleanup)
        decision = classify(result)
        self.assertTrue(decision["fallback_required"])
        self.assertEqual(decision["reason"], "channel_access_blocked")

    def test_partial_metadata_access_block_requires_fallback(self):
        temp, result = self.write_case(status="partial", unresolved=[{"status": "access_blocked"}])
        self.addCleanup(temp.cleanup)
        decision = classify(result)
        self.assertTrue(decision["fallback_required"])
        self.assertEqual(decision["reason"], "metadata_access_blocked")

    def test_caption_or_comment_access_block_requires_fallback(self):
        for field, reason in (("transcript_status", "caption_access_blocked"), ("comments_status", "comments_access_blocked")):
            with self.subTest(field=field):
                temp, result = self.write_case(status="partial", items=[{field: "access_blocked"}])
                try:
                    decision = classify(result)
                    self.assertTrue(decision["fallback_required"])
                    self.assertEqual(decision["reason"], reason)
                finally:
                    temp.cleanup()

    def test_generic_partial_and_error_do_not_use_self_hosted_fallback(self):
        for status in ("partial", "error"):
            with self.subTest(status=status):
                temp, result = self.write_case(status=status, unresolved=[{"status": "error"}])
                try:
                    decision = classify(result)
                    self.assertFalse(decision["fallback_required"])
                    self.assertEqual(decision["reason"], "none")
                finally:
                    temp.cleanup()


if __name__ == "__main__":
    unittest.main()
