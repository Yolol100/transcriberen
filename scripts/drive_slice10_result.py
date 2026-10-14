#!/usr/bin/env python3
"""Privately persist a complete real 10-video Qwen sample; no GitHub artifacts.

Designed as a bounded first slice before any 1,000-video automatic rollout.
Each video is independently rechecked against original source chunks and SHA.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlencode

from knowledge_analysis.corpus import iter_videos
from knowledge_analysis.routing import apply_master_routing, load_master_routing, verify_pinned_shards
from knowledge_analysis.review import (
    STATUS_COMPLETE, STATUS_SOURCE_WARNING, _valid_prior, signature, split_exact,
)
from scripts.drive_pilot_result import MODEL_SHA, MASTER_SHA, LIMIT, PilotError, api, read_json, sha_file

FILE_NAME = 'qwen-b001-s00-10.json'
PURPOSE = 'v15-real-qwen-slice10'
EXPECTED_VIDEOS = 10
SOURCE_TOTAL = 18_875


def validate_seed(data: dict) -> None:
    if (not isinstance(data,dict) or data.get('schema_version')!='1.0' or
        data.get('purpose')!=PURPOSE or data.get('source_master_sha256')!=MASTER_SHA or
        data.get('status')!='awaiting_review' or data.get('batch')!=1 or
        data.get('slice')!=0 or data.get('slice_size')!=10 or data.get('reviews') is not None):
        raise PilotError('invalid_or_consumed_slice10_slot')


def validate_slice(source_dir: Path, output_dir: Path, model_path: Path, run_id: str) -> dict:
    if not re.fullmatch('[0-9]{1,20}',run_id):
        raise PilotError('invalid_run_id')
    if model_path.is_symlink() or not model_path.is_file() or sha_file(model_path)!=MODEL_SHA:
        raise PilotError('unverified_model_sha')
    master=source_dir/'YouTube_Kennisbron_Master.zip'
    parts=[source_dir/f'YouTube_Kennisbron_Master.part-{i:02}.zip' for i in range(1,16)]
    routing=load_master_routing(master,MASTER_SHA)
    if len(routing)!=SOURCE_TOTAL:
        raise PilotError('wrong_routing_count')
    verify_pinned_shards(master,parts,SOURCE_TOTAL)
    inventory=read_json(output_dir/'inventory.json',2_000_000)
    expected_ids=sorted(routing)[:EXPECTED_VIDEOS]
    if (inventory.get('schema_version')!='1.0' or inventory.get('scope')!='evidence_only' or
        inventory.get('batch')!=1 or inventory.get('batch_size')!=500 or
        inventory.get('slice_index')!=0 or inventory.get('slice_size')!=EXPECTED_VIDEOS or
        inventory.get('selected_video_ids')!=expected_ids or
        inventory.get('total_unique_videos_in_supplied_corpus')!=SOURCE_TOTAL or
        inventory.get('model_sha256')!=MODEL_SHA or
        inventory.get('master_routing_sha256')!=MASTER_SHA or
        inventory.get('status')!='evidence_only_pending_external_qa' or
        inventory.get('policy_promotions')!=0 or inventory.get('human_verified_videos')!=0 or
        inventory.get('source_files')!=[{'name':p.name,'sha256':sha_file(p)} for p in parts]):
        raise PilotError('untrusted_slice_inventory')
    wanted=set(expected_ids)
    observed={}
    for p in parts:
        for v in iter_videos(p):
            if v.video_id in wanted:
                if v.video_id in observed: raise PilotError('duplicate_video')
                observed[v.video_id]=apply_master_routing(v,routing)
    if set(observed)!=wanted:
        raise PilotError('missing_selected_video')
    reviews=[]
    counts=Counter()
    chunks=0
    for video_id in expected_ids:
        video=observed[video_id]
        review=read_json(output_dir/'videos'/(video_id+'.json'))
        expected_status=STATUS_SOURCE_WARNING if video.transcript_hash_status!='match' else STATUS_COMPLETE
        tasks=[('transcript',None,s,e,t) for s,e,t in split_exact(video.transcript,5600)]
        for i,comment in enumerate(video.comments):
            tasks.extend(('comment',i,s,e,t) for s,e,t in split_exact(comment,5600))
        if (not video.transcript or review.get('video_id')!=video_id or
            review.get('status')!=expected_status or
            review.get('signature')!=signature(video,MODEL_SHA,5600) or
            not _valid_prior(review,tasks,expected_status=expected_status,
                             video=video,model_sha256=MODEL_SHA)):
            raise PilotError('incomplete_or_unanchored_review')
        counts[expected_status]+=1
        chunks+=len(tasks)
        reviews.append(review)
    if (dict(counts)!=inventory.get('statuses') or
        inventory.get('ai_reviewed_videos')!=EXPECTED_VIDEOS):
        raise PilotError('status_or_video_count_drift')
    ledger=read_json(output_dir/'ledger.json',LIMIT)
    if (ledger.get('video_records_provided')!=EXPECTED_VIDEOS or
        ledger.get('incomplete_video_records_excluded')!=0 or
        ledger.get('auto_promoted') is not False):
        raise PilotError('invalid_evidence_ledger')
    return {'schema_version':'1.0','purpose':PURPOSE,
            'source_master_sha256':MASTER_SHA,'model_sha256':MODEL_SHA,'run_id':run_id,
            'batch':1,'slice':0,'slice_size':EXPECTED_VIDEOS,
            'status':'ai_reviewed_pending_independent_verification',
            'verified_video_count':EXPECTED_VIDEOS,'verified_full_source_chunks':chunks,
            'reviews':reviews,'ledger':ledger,'independent_qa_complete':False,
            'sources_or_skills_updated':False,'sensitive_content_uploaded_to_github':False}


def store(folder_id: str, token: str, result: dict) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',folder_id):
        raise PilotError('bad_folder_locator')
    query=f"'{folder_id}' in parents and name = '{FILE_NAME}' and trashed = false"
    params=urlencode({'q':query,'fields':'nextPageToken,incompleteSearch,files(id,name,mimeType,size,capabilities(canEdit))','pageSize':10})
    meta=json.loads(api('https://www.googleapis.com/drive/v3/files?'+params,token,max_bytes=200000))
    files=meta.get('files')
    if (meta.get('nextPageToken') or meta.get('incompleteSearch') or
        not isinstance(files,list) or len(files)!=1 or
        files[0].get('name')!=FILE_NAME or files[0].get('mimeType')!='application/json' or
        files[0].get('capabilities',{}).get('canEdit') is not True):
        raise PilotError('missing_private_slice10_slot')
    fid=files[0].get('id')
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',str(fid)):
        raise PilotError('invalid_slot_file_id')
    url='https://www.googleapis.com/drive/v3/files/'+fid+'?alt=media'
    existing=json.loads(api(url,token,max_bytes=LIMIT))
    from scripts.drive_slice10_checkpoint import valid_checkpoint
    prior=valid_checkpoint(existing)
    if prior:
        verified_by_id={row['video_id']:row for row in result['reviews']}
        if any(row['video_id'] not in verified_by_id or verified_by_id[row['video_id']]!=row for row in prior):
            raise PilotError('checkpoint_disagrees_with_source_verified_final_reviews')
    data=(json.dumps(result,sort_keys=True,ensure_ascii=False)+'\n').encode('utf-8')
    if len(data)>LIMIT:
        raise PilotError('private_result_too_large')
    api('https://www.googleapis.com/upload/drive/v3/files/'+fid+'?uploadType=media',
        token,method='PATCH',body=data,max_bytes=250000)
    if api(url,token,max_bytes=LIMIT)!=data:
        raise PilotError('private_result_readback_mismatch')
    return {'status':'PASS','complete_real_video_reviews':EXPECTED_VIDEOS,
            'verified_chunks':result['verified_full_source_chunks'],
            'private_result_sha256':hashlib.sha256(data).hexdigest(),
            'claims_for_external_qa':result['ledger']['claim_count'],
            'auto_promoted':False,'public_private_artifacts':0}


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--model-path',type=Path,required=True)
    parser.add_argument('--results-folder-id',required=True)
    parser.add_argument('--run-id',required=True)
    a=parser.parse_args()
    try:
        result=validate_slice(a.source_dir,a.output_dir,a.model_path,a.run_id)
        print(json.dumps(store(a.results_folder_id,os.environ.get('DRIVE_ACCESS_TOKEN',''),result),sort_keys=True))
        return 0
    except Exception:
        print('BLOCKED: slice10 review incomplete or private result readback failed',file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
