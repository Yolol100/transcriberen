import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "transcribe.yml"


class SelfHostedWorkflowTests(unittest.TestCase):
    def test_runtime_requests_is_the_only_queue_branch(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("branches: [runtime-requests]", text)
        self.assertNotIn("runtime-requests-selfhosted", text)
        self.assertNotIn("workflow_dispatch:", text)
        self.assertNotIn("workflow_call:", text)

    def test_runtime_job_is_self_hosted_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("runs-on: [self-hosted, linux, x64, webactueel-transcribe]", text)
        self.assertIn("TRANSCRIBE_EXECUTION_TARGET: self-hosted", text)
        self.assertIn("unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy", text)

    def test_runtime_only_runs_caption_pipeline(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/captions_runtime.py", text)
        self.assertIn("scripts/validate_result.py", text)
        for forbidden in ("runtime_topic_filter.py", "normalize_youtube_result", "ffmpeg", "whisper", "comments"):
            self.assertNotIn(forbidden, text.casefold())

    def test_transport_branch_code_is_not_executed_on_self_hosted_runner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        runtime = text.split("\n  runtime:\n", 1)[1]
        self.assertIn("repository: Yolol100/transcriberen", runtime)
        self.assertIn("ref: main", runtime)
        self.assertNotIn("path: transport", runtime)


if __name__ == "__main__":
    unittest.main()
