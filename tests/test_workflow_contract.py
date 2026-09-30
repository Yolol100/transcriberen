import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_channel_runtime_is_sha_pinned_and_github_hosted_only(self):
        text = (ROOT / '.github/workflows/transcribe.yml').read_text(encoding='utf-8')
        self.assertIn('branches: [runtime-requests]', text)
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('python3 scripts/channel_runtime.py', text)
        self.assertIn('timeout-minutes: 360', text)
        self.assertIn('TRANSCRIBE_EXECUTION_TARGET: github-hosted', text)
        self.assertIn('Attest hosted checksum receipt', text)
        self.assertIn('Upload hosted result', text)
        self.assertIn('Fail on hosted access block or acquisition error', text)
        self.assertIn('runtime_sha: ${{ steps.runtime_sha.outputs.sha }}', text)
        self.assertIn('ref: ${{ needs.resolve.outputs.runtime_sha }}', text)
        self.assertIn('test "$actual" = "$EXPECTED_RUNTIME_SHA"', text)
        self.assertNotIn('runs-on: [self-hosted', text)
        self.assertNotIn('webactueel-transcribe', text)
        self.assertNotIn('fallback_required', text)
        self.assertNotIn('classify_hybrid_result.py', text)
        self.assertNotIn('TRANSCRIBE_EXECUTION_TARGET: self-hosted', text)
        self.assertNotIn('workflow_dispatch:', text)
        self.assertNotIn('workflow_call:', text)


if __name__ == '__main__':
    unittest.main()
