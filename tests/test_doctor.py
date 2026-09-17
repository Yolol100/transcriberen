import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('doctor', ROOT / 'scripts' / 'doctor.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DoctorTests(unittest.TestCase):
    def test_current_tree_passes(self):
        result = m.run_checks(ROOT)
        self.assertTrue(result['ok'], result['failures'])

    def copied_tree(self):
        td = tempfile.TemporaryDirectory()
        target = pathlib.Path(td.name) / 'repo'
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns('results', 'resolved-request.json', '__pycache__', '*.pyc'))
        return td, target

    def test_policy_drift_is_detected(self):
        td, root = self.copied_tree()
        try:
            path = root / 'toolkit-contract.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            data['fixed_policy']['max_videos'] = 1001
            path.write_text(json.dumps(data), encoding='utf-8')
            result = m.run_checks(root)
            self.assertFalse(result['ok'])
            self.assertTrue(any('fixed channel policy' in item for item in result['failures']))
        finally:
            td.cleanup()

    def test_single_video_workflow_regression_is_detected(self):
        td, root = self.copied_tree()
        try:
            path = root / '.github' / 'workflows' / 'transcribe.yml'
            path.write_text(path.read_text(encoding='utf-8') + '\n# python3 scripts/captions_runtime.py\n', encoding='utf-8')
            result = m.run_checks(root)
            self.assertFalse(result['ok'])
            self.assertTrue(any('old single-video runtime' in item for item in result['failures']))
        finally:
            td.cleanup()

    def test_reply_depth_regression_is_detected(self):
        td, root = self.copied_tree()
        try:
            path = root / 'scripts' / 'captions_runtime.py'
            text = path.read_text(encoding='utf-8').replace('max_comments={limit},{limit},0,0,1', 'max_comments={limit},{limit},7,7,2')
            path.write_text(text, encoding='utf-8')
            result = m.run_checks(root)
            self.assertFalse(result['ok'])
            self.assertTrue(any('comment no-reply depth limit' in item for item in result['failures']))
        finally:
            td.cleanup()

    def test_current_run_index_regression_is_detected(self):
        td, root = self.copied_tree()
        try:
            path = root / 'scripts' / 'cache_runtime.py'
            text = path.read_text(encoding='utf-8').replace('"scope": "current_run"', '"scope": "all_history"')
            path.write_text(text, encoding='utf-8')
            result = m.run_checks(root)
            self.assertFalse(result['ok'])
            self.assertTrue(any('processed index is not scoped' in item for item in result['failures']))
        finally:
            td.cleanup()


if __name__ == '__main__':
    unittest.main()
