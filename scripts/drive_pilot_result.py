#!/usr/bin/env python3
"""Verified private Qwen pilot result: update one pre-owned Drive JSON, never create files.

Only real, chunk-complete, SHA-bound evidence from the original v15 shards is
permitted. The public GitHub workflow logs only aggregate status and SHA-256.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from knowledge_analysis.corpus import iter_videos
from knowledge_analysis.routing import apply_master_routing, load_master_routing, verify_pinned_shards
from knowledge_analysis.review import (
    STATUS_COMPLETE, STATUS_SOURCE_WARNING, _valid_prior, signature, split_exact,
)
from scripts.drive_preflight import MASTER_SHA

FILE_NAME = 'qwen-pilot-b001-s00.json'
PURPOSE = 'v15-real-qwen-review-pilot'
MODEL_SHA = 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'
LIMIT = 5_000_000
EXPECTED_VIDEOS = 18_875

class PilotError(Exception):
    pass


def read_json(path: Path, limit: int = LIMIT) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise PilotError('missing_or_oversized_review_evidence')
    try:
        data = json.loads(path.read_bytes())
    except (OSError, UnicodeError, ValueError):
        raise PilotError('unreadable_review_evidence') from None
    if not isinstance(data, dict):
        raise PilotError('nonobject_review_evidence')
    return data


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def validate_seed(data: dict) -> None:
    if (not isinstance(data,dict) or data.get('schema_version')!='1.0' or
        data.get('purpose') != PURPOSE or data.get('source_master_sha256') != MASTER_SHA or
        data.get('status') != 'awaiting_review' or data.get('batch') != 1 or
        data.get('slice') != 0 or data.get('slice_size') != 1 or
        data.get('review') is not None):
        raise PilotError('invalid_or_already_consumed_private_slot')


def validate_private_review(source_dir: Path, output_dir: Path, model_path: Path, run_id: str) -> dict:
    if not re.fullmatch(r'[0-9]{1,20}', run_id):
        raise PilotError('invalid_run_id')
    if not source_dir.is_dir() or source_dir.is_symlink():
        raise PilotError('invalid_private_sources')
    if model_path.is_symlink() or not model_path.is_file() or sha_file(model_path) != MODEL_SHA:
        raise PilotError('unverified_qwen_model')
    master = source_dir / 'YouTube_Kennisbron_Master.zip'
    parts = [source_dir / f'YouTube_Kennisbron_Master.part-{idx:02}.zip' for idx in range(1,16)]
    routing = load_master_routing(master, MASTER_SHA)
    if len(routing) != EXPECTED_VIDEOS:
        raise PilotError('wrong_master_video_count')
    verify_pinned_shards(master, parts, EXPECTED_VIDEOS)
    inventory = read_json(output_dir / 'inventory.json', 2_000_000)
    if (inventory.get('schema_version')!='1.0' or inventory.get('scope') != 'evidence_only' or
        inventory.get('batch') != 1 or inventory.get('batch_size') != 500 or
        inventory.get('slice_index') != 0 or inventory.get('slice_size') != 1 or
        inventory.get('total_unique_videos_in_supplied_corpus') != EXPECTED_VIDEOS or
        inventory.get('model_sha256') != MODEL_SHA or
        inventory.get('master_routing_sha256') != MASTER_SHA or
        inventory.get('status') != 'evidence_only_pending_external_qa' or
        inventory.get('policy_promotions') != 0 or inventory.get('human_verified_videos') != 0):
        raise PilotError('invalid_pilot_inventory')
    sha_sources = [{'name':p.name, 'sha256':sha_file(p)} for p in parts]
    if inventory.get('source_files') != sha_sources:
        raise PilotError('review_source_receipt_drift')
    video_ids = inventory.get('selected_video_ids')
    if not isinstance(video_ids,list) or len(video_ids)!=1 or video_ids[0]!=min(routing):
        raise PilotError('wrong_first_video')
    vid = video_ids[0]
    review = read_json(output_dir / 'videos' / (vid+'.json'))
    if review.get('video_id') != vid:
        raise PilotError('wrong_video_review')
    video = None
    for part in parts:
        for v in iter_videos(part):
            if v.video_id==vid:
                if video is not None:
                    raise PilotError('duplicate_selected_video')
                video=apply_master_routing(v, routing)
    if video is None:
        raise PilotError('source_video_not_found')
    expected_status = STATUS_SOURCE_WARNING if video.transcript_hash_status!='match' else STATUS_COMPLETE
    tasks = [('transcript',None,s,e,t) for s,e,t in split_exact(video.transcript, 5600)]
    for idx, comment in enumerate(video.comments):
        tasks.extend(('comment',idx,s,e,t) for s,e,t in split_exact(comment,5600))
    if (not video.transcript or review.get('status')!=expected_status or
        review.get('model_sha256')!=MODEL_SHA or
        review.get('signature')!=signature(video,MODEL_SHA,5600) or
        not _valid_prior(review,tasks,expected_status=expected_status,video=video,model_sha256=MODEL_SHA)):
        raise PilotError('incomplete_or_unanchored_real_qwen_review')
    statuses=inventory.get('statuses',{})
    if (statuses!={expected_status:1} or inventory.get('ai_reviewed_videos')!=1 or
        inventory.get('actual_batch_count')!=500):
        raise PilotError('review_status_summary_mismatch')
    ledger=read_json(output_dir/'ledger.json',LIMIT)
    if (ledger.get('video_records_provided')!=1 or ledger.get('auto_promoted') is not False):
        raise PilotError('invalid_phase4_ledger')
    return {
        'schema_version':'1.0', 'purpose':PURPOSE, 'source_master_sha256':MASTER_SHA,
        'model_sha256':MODEL_SHA, 'run_id':run_id, 'batch':1, 'slice':0, 'slice_size':1,
        'status':'ai_reviewed_pending_independent_verification',
        'verified_full_source_chunks':len(tasks),
        'review':review, 'ledger':ledger,
        'source_verified':True, 'independent_qa_complete':False,
        'source_updates_applied':False, 'skills_updated':False,
        'sensitive_content_uploaded_to_github':False,
    }


def api(url: str, token: str, *, method='GET', body=None, max_bytes=LIMIT) -> bytes:
    if not token or len(token)>20000:
        raise PilotError('missing_writer_credential')
    headers={'Authorization':'Bearer '+token}
    if body is not None:
        headers['Content-Type']='application/json; charset=utf-8'
    req=Request(url,data=body,method=method,headers=headers)
    with urlopen(req,timeout=95) as response:
        if response.status!=200:
            raise PilotError('unexpected_private_drive_status')
        blob=response.read(max_bytes+1)
        if len(blob)>max_bytes:
            raise PilotError('private_drive_response_oversized')
        return blob


def write_existing(folder_id: str, token: str, payload: dict) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',folder_id):
        raise PilotError('invalid_destination_folder')
    query=f"'{folder_id}' in parents and name = '{FILE_NAME}' and trashed = false"
    params=urlencode({'q':query,'fields':'nextPageToken,incompleteSearch,files(id,name,mimeType,size,capabilities(canEdit))','pageSize':10})
    result=json.loads(api('https://www.googleapis.com/drive/v3/files?'+params,token,max_bytes=200000))
    files=result.get('files')
    if (result.get('nextPageToken') or result.get('incompleteSearch') or not isinstance(files,list) or
        len(files)!=1 or files[0].get('name')!=FILE_NAME or files[0].get('mimeType')!='application/json' or
        files[0].get('capabilities',{}).get('canEdit') is not True):
        raise PilotError('invalid_private_result_slot')
    fid=files[0].get('id')
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',str(fid)):
        raise PilotError('invalid_result_file_id')
    current=api('https://www.googleapis.com/drive/v3/files/'+fid+'?alt=media',token,max_bytes=4000)
    validate_seed(json.loads(current))
    encoded=(json.dumps(payload,sort_keys=True,ensure_ascii=False)+'\n').encode('utf-8')
    if len(encoded)>LIMIT:
        raise PilotError('review_exceeds_private_slot_budget')
    api('https://www.googleapis.com/upload/drive/v3/files/'+fid+'?uploadType=media', token,
        method='PATCH',body=encoded,max_bytes=250000)
    readback=api('https://www.googleapis.com/drive/v3/files/'+fid+'?alt=media',token,max_bytes=LIMIT)
    if readback!=encoded:
        raise PilotError('private_result_readback_drift')
    return {'status':'PASS','real_video_reviews_privately_written':1,'batch':1,'slice':0,
            'chunk_count':payload['verified_full_source_chunks'],
            'private_result_sha256':hashlib.sha256(readback).hexdigest(),
            'public_github_review_artifacts':0, 'independent_qa_complete':False}


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--model-path',type=Path,required=True)
    parser.add_argument('--results-folder-id',required=True)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    try:
        payload=validate_private_review(args.source_dir,args.output_dir,args.model_path,args.run_id)
        print(json.dumps(write_existing(args.results_folder_id,os.environ.get('DRIVE_ACCESS_TOKEN',''),payload),sort_keys=True))
        return 0
    except Exception:
        print('BLOCKED: private pilot result validation or write/readback failed',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
