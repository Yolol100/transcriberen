#!/usr/bin/env python3
"""Safely test OIDC service-account UPDATE of an existing user-owned Drive file.

Service accounts have no My Drive storage quota: do NOT create files with this account.
Only replace the small, explicitly provisioned test JSON in the results folder.
Never emit tokens, Drive IDs, API errors, private source data, or response bodies.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FILE_NAME = 'github-result-write-probe.json'
TEST_NAME = 'transcriberen-oidc-existing-file-write'
MAX_RESPONSE = 1024 * 100
MAX_TEST_FILE = 1024 * 2

class ProbeFailure(Exception):
    pass

def request(url, token, *, method='GET', body=None, max_bytes=MAX_RESPONSE):
    if not token or len(token) > 20000:
        raise ProbeFailure('missing_token')
    headers = {'Authorization': 'Bearer ' + token}
    if body is not None:
        headers['Content-Type'] = 'application/json; charset=UTF-8'
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=40) as resp:
            if resp.status not in (200, 201):
                raise ProbeFailure('unexpected_http_status')
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ProbeFailure('response_oversized')
            return raw
    except ProbeFailure:
        raise
    except Exception:
        raise ProbeFailure('google_drive_api_call_failed') from None

def validate_file_list(result):
    if not isinstance(result, dict) or result.get('nextPageToken') or result.get('incompleteSearch'):
        raise ProbeFailure('incomplete_results_listing')
    files = result.get('files')
    if not isinstance(files, list) or len(files) != 1:
        raise ProbeFailure('missing_or_duplicate_probe_file')
    info = files[0]
    if not isinstance(info, dict) or info.get('name') != FILE_NAME or info.get('mimeType') != 'application/json':
        raise ProbeFailure('probe_file_mismatch')
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', str(info.get('id', ''))):
        raise ProbeFailure('invalid_probe_locator')
    if not info.get('capabilities', {}).get('canEdit'):
        raise ProbeFailure('service_account_has_no_edit_permission')
    if int(info.get('size', '-1')) > MAX_TEST_FILE:
        raise ProbeFailure('probe_file_too_large')
    return info['id']

def parse_test_file(raw, expected_statuses):
    if len(raw) > MAX_TEST_FILE:
        raise ProbeFailure('probe_file_too_large')
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        raise ProbeFailure('invalid_probe_json') from None
    if (not isinstance(data, dict) or data.get('schema_version') != '1.0' or
            data.get('test') != TEST_NAME or data.get('status') not in expected_statuses or
            data.get('sensitive_source_content') is not False):
        raise ProbeFailure('unexpected_probe_content')
    return data

def perform_probe(folder_id, token, run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', folder_id):
        raise ProbeFailure('invalid_results_folder')
    if not re.fullmatch(r'[0-9]{1,20}', run_id):
        raise ProbeFailure('invalid_run_id')
    q = f"'{folder_id}' in parents and name = '{FILE_NAME}' and trashed = false"
    params = urlencode({'q': q, 'fields': 'nextPageToken,incompleteSearch,files(id,name,mimeType,size,capabilities(canEdit))', 'pageSize': 10})
    metadata = json.loads(request('https://www.googleapis.com/drive/v3/files?' + params, token))
    file_id = validate_file_list(metadata)
    content_url = 'https://www.googleapis.com/drive/v3/files/' + file_id + '?alt=media'
    current = request(content_url, token, max_bytes=MAX_TEST_FILE)
    parse_test_file(current, {'awaiting_github_test', 'PASS'})
    payload = {'schema_version': '1.0', 'test': TEST_NAME, 'status': 'PASS',
               'github_run_id': run_id, 'sensitive_source_content': False}
    expected = (json.dumps(payload, sort_keys=True) + '\n').encode('utf-8')
    update_url = 'https://www.googleapis.com/upload/drive/v3/files/' + file_id + '?uploadType=media'
    request(update_url, token, method='PATCH', body=expected)
    readback = request(content_url, token, max_bytes=MAX_TEST_FILE)
    parse_test_file(readback, {'PASS'})
    if readback != expected:
        raise ProbeFailure('write_readback_mismatch')
    return {'status': 'PASS', 'test': TEST_NAME, 'existing_user_owned_file_updated': True,
            'results_written_to_public_github': False, 'bytes_readback': len(readback),
            'sha256': hashlib.sha256(readback).hexdigest(), 'real_corpus_review_complete': False}

def main():
    p = argparse.ArgumentParser(description='Google Drive private existing-file write readback test')
    p.add_argument('--results-folder-id', required=True)
    p.add_argument('--github-run-id', required=True)
    args = p.parse_args()
    token = os.environ.get('DRIVE_ACCESS_TOKEN', '')
    try:
        print(json.dumps(perform_probe(args.results_folder_id, token, args.github_run_id), sort_keys=True))
        return 0
    except ProbeFailure as exc:
        print('BLOCKED: ' + str(exc), file=sys.stderr)
        return 2
    except Exception:
        print('BLOCKED: unverified private results write', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
