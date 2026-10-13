import unittest
from scripts.drive_write_probe import (
    ProbeFailure, validate_file_list, parse_test_file, FILE_NAME, TEST_NAME,
)
import json


def valid():
    return {'files': [{'id': 'safe_test_file_identifier', 'name': FILE_NAME,
                       'mimeType': 'application/json', 'size': '155',
                       'capabilities': {'canEdit': True}}]}


class ResultWriteProbeTests(unittest.TestCase):
    def test_known_file(self):
        self.assertEqual(validate_file_list(valid()), 'safe_test_file_identifier')

    def test_missing(self):
        with self.assertRaises(ProbeFailure):
            validate_file_list({'files': []})

    def test_duplicate(self):
        f = valid()['files'][0]
        with self.assertRaises(ProbeFailure):
            validate_file_list({'files': [f, f]})

    def test_cannot_edit(self):
        v = valid()
        v['files'][0]['capabilities']['canEdit'] = False
        with self.assertRaises(ProbeFailure):
            validate_file_list(v)

    def test_traversal_id(self):
        v = valid()
        v['files'][0]['id'] = '../private'
        with self.assertRaises(ProbeFailure):
            validate_file_list(v)

    def test_pagination_rejected(self):
        v = valid()
        v['nextPageToken'] = 'other'
        with self.assertRaises(ProbeFailure):
            validate_file_list(v)

    def test_json_contract(self):
        raw = json.dumps({'schema_version': '1.0', 'test': TEST_NAME,
                          'status': 'awaiting_github_test',
                          'sensitive_source_content': False}).encode()
        parse_test_file(raw, {'awaiting_github_test'})

    def test_reject_sensitive_content(self):
        raw = json.dumps({'schema_version': '1.0', 'test': TEST_NAME,
                          'status': 'awaiting_github_test',
                          'sensitive_source_content': True}).encode()
        with self.assertRaises(ProbeFailure):
            parse_test_file(raw, {'awaiting_github_test'})


if __name__ == '__main__':
    unittest.main()
