"""Private per-video checkpoints for a ten-video v15 Qwen run.
Stored in a pre-created, user-owned Drive file; never uploaded to public GitHub.
Prior saved reviews are UNTRUSTED: review_video rechecks every source chunk before reuse.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from scripts.drive_pilot_result import api, PilotError, MASTER_SHA, MODEL_SHA, LIMIT
from scripts.drive_slice10_result import FILE_NAME, PURPOSE

COMPLETE = {'ai_reviewed_pending_independent_verification',
            'ai_reviewed_unverified_legacy_source_hash',
            'no_transcript_comments_reviewed', 'no_transcript'}

def slot(folder, token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', folder):
        raise PilotError('invalid folder')
    q=urlencode({'q':f"'{folder}' in parents and name = '{FILE_NAME}' and trashed = false",
                 'fields':'nextPageToken,incompleteSearch,files(id,name,mimeType,capabilities(canEdit))','pageSize':10})
    meta=json.loads(api('https://www.googleapis.com/drive/v3/files?'+q,token,max_bytes=200000))
    files=meta.get('files')
    if (meta.get('nextPageToken') or meta.get('incompleteSearch') or
        not isinstance(files,list) or len(files)!=1 or
        files[0].get('mimeType')!='application/json' or
        files[0].get('name')!=FILE_NAME or
        files[0].get('capabilities',{}).get('canEdit') is not True or
        not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',str(files[0].get('id','')))):
        raise PilotError('missing private writable slot')
    fid=files[0]['id']
    raw=api('https://www.googleapis.com/drive/v3/files/'+fid+'?alt=media',token,max_bytes=LIMIT)
    return fid,json.loads(raw)

def prior_records(obj):
    if not isinstance(obj,dict) or obj.get('purpose')!=PURPOSE or obj.get('source_master_sha256')!=MASTER_SHA or obj.get('batch')!=1 or obj.get('slice')!=0 or obj.get('slice_size')!=10:
        raise PilotError('wrong private checkpoint scope')
    if obj.get('status')=='awaiting_review' and obj.get('reviews') is None:
        return []
    if obj.get('status')!='partial_private_checkpoint' or obj.get('model_sha256')!=MODEL_SHA:
        raise PilotError('private result already finished or untrusted')
    records=obj.get('reviews')
    if not isinstance(records,list) or len(records)>10:
        raise PilotError('invalid checkpoint record count')
    seen=set()
    for row in records:
        if (not isinstance(row,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',str(row.get('video_id',''))) or
            row['video_id'] in seen or row.get('model_sha256')!=MODEL_SHA or
            row.get('policy_version')!='knowledge-review-v5' or row.get('auto_promoted') is not False):
            raise PilotError('unsafe prior review')
        seen.add(row['video_id'])
    return records

def restore(folder,token,dest):
    _,obj=slot(folder,token)
    records=prior_records(obj)
    folder=Path(dest)
    folder.mkdir(parents=True,exist_ok=True)
    for r in records:
        p=folder/(r['video_id']+'.json')
        if p.exists() or p.is_symlink():raise PilotError('unexpected review overwrite')
        p.write_text(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
    return len(records)

def persist(folder,token,dest):
    fid,prior=slot(folder,token)
    prior_ids={x['video_id'] for x in prior_records(prior)}
    records=[]
    for p in sorted(Path(dest).glob('*.json')):
        if p.is_symlink() or p.stat().st_size>2_000_000 or len(records)>=10:raise PilotError('unsafe review size')
        row=json.loads(p.read_text(encoding='utf-8'))
        if (not isinstance(row,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',str(row.get('video_id',''))) or
            p.name!=row['video_id']+'.json' or row.get('model_sha256')!=MODEL_SHA or
            row.get('policy_version')!='knowledge-review-v5' or row.get('auto_promoted') is not False):
            raise PilotError('malformed review')
        records.append(row)
    ids=[r['video_id'] for r in records]
    if not ids or len(set(ids))!=len(ids) or not prior_ids.issubset(ids):
        raise PilotError('checkpoint removed previous data')
    obj={'schema_version':'1.0','purpose':PURPOSE,'source_master_sha256':MASTER_SHA,
         'model_sha256':MODEL_SHA,'batch':1,'slice':0,'slice_size':10,
         'status':'partial_private_checkpoint','reviews':records,
         'independent_qa_complete':False,'auto_promoted':False}
    payload=(json.dumps(obj,sort_keys=True,ensure_ascii=False)+'\n').encode('utf-8')
    if len(payload)>LIMIT:raise PilotError('checkpoint too large')
    api('https://www.googleapis.com/upload/drive/v3/files/'+fid+'?uploadType=media',
        token,method='PATCH',body=payload,max_bytes=250000)
    if api('https://www.googleapis.com/drive/v3/files/'+fid+'?alt=media',token,max_bytes=LIMIT)!=payload:
        raise PilotError('private checkpoint readback mismatch')
    return len(records)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=('restore','persist'))
    p.add_argument('--folder-id',required=True)
    p.add_argument('--reviews-dir',required=True)
    args=p.parse_args()
    try:
        n=(restore if args.mode=='restore' else persist)(args.folder_id,os.environ.get('DRIVE_ACCESS_TOKEN',''),args.reviews_dir)
        print(json.dumps({'checkpoint_saved_or_restored':n,'all_ten_verified':False}))
        return 0
    except Exception:
        print('BLOCKED: private checkpoint validation/write/readback failed',file=sys.stderr)
        return 2

if __name__=='__main__':sys.exit(main())
