#!/usr/bin/env python3
"""Download the private immutable v15 YouTube corpus to the ephemeral runner.

Only the trusted main runner may call this with a short-lived OIDC token.
No source bytes, file locators, or private API response bodies go to logs or Git.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen

from scripts.drive_preflight import (
    MASTER, MASTER_SHA, EXPECTED_BYTES, verify_inventory, list_folder,
)
from knowledge_analysis.routing import load_master_routing, verify_pinned_shards

MAX_ZIPS = 16
EXPECTED_VIDEOS = 18_875

class PrivateSourceFailure(Exception):
    pass


def download_one(file_id: str, destination: Path, expected_size: int, token: str) -> None:
    if destination.exists() or destination.is_symlink():
        raise PrivateSourceFailure('nonempty_source_destination')
    tmp = destination.with_suffix('.zip.partial')
    if tmp.exists() or tmp.is_symlink():
        raise PrivateSourceFailure('stale_temporary_source')
    url = 'https://www.googleapis.com/drive/v3/files/' + file_id + '?alt=media'
    size = 0
    try:
        request = Request(url, headers={'Authorization': 'Bearer ' + token})
        with urlopen(request, timeout=120) as reader, tmp.open('xb') as writer:
            if reader.status != 200:
                raise PrivateSourceFailure('source_http_status')
            for block in iter(lambda: reader.read(1024 * 1024), b''):
                size += len(block)
                if size > expected_size:
                    raise PrivateSourceFailure('source_oversized')
                writer.write(block)
        if size != expected_size:
            raise PrivateSourceFailure('source_short_download')
        tmp.rename(destination)
    finally:
        if tmp.exists():
            tmp.unlink()


def get_sources(folder_id: str, token: str, destination: Path) -> dict:
    if not token or len(token) > 20_000:
        raise PrivateSourceFailure('missing_private_credential')
    if destination.is_symlink() or (destination.exists() and any(destination.iterdir())):
        raise PrivateSourceFailure('private_source_directory_not_empty')
    # Reuse the previously proven exact 16-file pinned metadata contract.
    entries = list_folder(folder_id, token)
    verify_inventory(entries)
    by_name = {entry['name']: entry for entry in entries}
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    master = destination / MASTER
    download_one(by_name[MASTER]['id'], master, EXPECTED_BYTES[MASTER], token)
    routing = load_master_routing(master, MASTER_SHA)
    if len(routing) != EXPECTED_VIDEOS:
        raise PrivateSourceFailure('unexpected_routing_count')
    paths: list[Path] = []
    for index in range(1, MAX_ZIPS):
        name = f'YouTube_Kennisbron_Master.part-{index:02}.zip'
        path = destination / name
        download_one(by_name[name]['id'], path, EXPECTED_BYTES[name], token)
        paths.append(path)
    verify_pinned_shards(master, paths, EXPECTED_VIDEOS)
    return {'status': 'PASS', 'master_sha256': MASTER_SHA,
            'shards_verified': len(paths), 'source_videos': len(routing),
            'total_zip_bytes': sum(EXPECTED_BYTES.values()),
            'private_corpus_published_to_github': False}


def main() -> int:
    parser = argparse.ArgumentParser(description='Read-only validated private Drive v15 source download')
    parser.add_argument('--folder-id', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(get_sources(args.folder_id, os.environ.get('DRIVE_ACCESS_TOKEN', ''), args.destination), sort_keys=True))
        return 0
    except Exception:
        print('BLOCKED: private corpus source download or verification failed', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
