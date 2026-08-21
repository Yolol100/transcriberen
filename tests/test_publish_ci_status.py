import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "publish_ci_status.py"
spec = importlib.util.spec_from_file_location("publish_ci_status", MODULE_PATH)
publish_ci_status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_ci_status)


class PublishCIStatusTests(unittest.TestCase):
    def test_result_mapping(self):
        self.assertEqual(publish_ci_status.normalize_result("success"), "success")
        self.assertEqual(publish_ci_status.normalize_result("failure"), "failure")
        self.assertEqual(publish_ci_status.normalize_result("pending"), "pending")
        self.assertEqual(publish_ci_status.normalize_result("cancelled"), "error")
        self.assertEqual(publish_ci_status.normalize_result("skipped"), "error")

    def test_payload_is_bound_to_repository_run_and_context(self):
        payload = publish_ci_status.build_payload(
            "post-merge/Toolkit Contract",
            "success",
            "Yolol100/transcriberen",
            "12345",
        )
        self.assertEqual(payload["state"], "success")
        self.assertEqual(payload["context"], "post-merge/Toolkit Contract")
        self.assertEqual(
            payload["target_url"],
            "https://github.com/Yolol100/transcriberen/actions/runs/12345",
        )
        self.assertLessEqual(len(payload["description"]), 140)


if __name__ == "__main__":
    unittest.main()
