import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_channel_only_hybrid_runtime_is_sha_pinned_and_access_block_gated(self):
        text = (ROOT / '.github/workflows/transcribe.yml').read_text(encoding='utf-8')
        self.assertIn('branches: [runtime-requests]', text)
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('runs-on: [self-hosted, linux, x64, webactueel-transcribe]', text)
        self.assertIn('python3 scripts/channel_runtime.py', text)
        self.assertIn('python3 scripts/classify_hybrid_result.py', text)
        self.assertNotIn('python3 scripts/captions_runtime.py', text)
        self.assertIn('timeout-minutes: 360', text)
        self.assertIn('TRANSCRIBE_EXECUTION_TARGET: github-hosted', text)
        self.assertIn('TRANSCRIBE_EXECUTION_TARGET: self-hosted', text)
        self.assertIn("needs.hosted_attempt.outputs.fallback_required == 'true'", text)
        self.assertIn("needs.hosted_attempt.result == 'success'", text)
        self.assertIn('runtime_sha: ${{ steps.runtime_sha.outputs.sha }}', text)
        self.assertIn('ref: ${{ needs.resolve.outputs.runtime_sha }}', text)
        self.assertIn('test "$actual" = "$EXPECTED_RUNTIME_SHA"', text)
        self.assertNotIn('workflow_dispatch:', text)
        self.assertNotIn('workflow_call:', text)


if __name__ == '__main__':
    unittest.main()
