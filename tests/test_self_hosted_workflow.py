import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'transcribe-self-hosted.yml'


class SelfHostedWorkflowContractTests(unittest.TestCase):
    def test_only_operational_push_triggers_self_hosted_lane(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('branches: [runtime-requests-selfhosted]', text)
        self.assertIn("requests/queue/*.json", text)
        self.assertNotIn('pull_request:', text)
        self.assertNotIn('pull_request_target:', text)
        self.assertNotIn('workflow_call:', text)

    def test_self_hosted_job_uses_dedicated_linux_x64_label(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('runs-on: [self-hosted, linux, x64, webactueel-transcribe]', text)
        self.assertIn('test "$ACTUAL_ENVIRONMENT" = "$EXPECTED_ENVIRONMENT"', text)
        self.assertIn("test \"$ACTUAL_OS\" = 'Linux'", text)
        self.assertIn("test \"$ACTUAL_ARCH\" = 'X64'", text)

    def test_runtime_executes_trusted_main_not_transport_branch(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        runtime = text.split('\n  runtime:\n', 1)[1]
        self.assertIn('repository: Yolol100/transcriberen', runtime)
        self.assertIn('ref: main', runtime)
        self.assertNotIn('path: transport', runtime)
        self.assertIn('persist-credentials: false', runtime)

    def test_transport_is_append_only_single_request(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("parts[0] == 'A'", text)
        self.assertIn('expected exactly one new queue request', text)
        self.assertIn('queue filename must equal request_id', text)
        self.assertIn('queue request must set enabled=true', text)

    def test_youtube_runtime_drops_proxy_environment(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy', text)
        self.assertNotIn('--cookies', text)
        self.assertNotIn('--proxy', text)

    def test_external_actions_are_sha_pinned(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        for action in (
            'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
            'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97',
            'actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c',
            'actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a',
            'actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d',
        ):
            self.assertIn(action, text)


if __name__ == '__main__':
    unittest.main()
