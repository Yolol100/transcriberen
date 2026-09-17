import pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class WorkflowTests(unittest.TestCase):
    def test_channel_only_self_hosted(self):
        text=(ROOT/'.github/workflows/transcribe.yml').read_text(encoding='utf-8')
        self.assertIn('branches: [runtime-requests]',text)
        self.assertIn('runs-on: [self-hosted, linux, x64, webactueel-transcribe]',text)
        self.assertIn('python3 scripts/channel_runtime.py',text)
        self.assertNotIn('python3 scripts/captions_runtime.py',text)
        self.assertIn('timeout-minutes: 360',text)
if __name__=='__main__': unittest.main()
