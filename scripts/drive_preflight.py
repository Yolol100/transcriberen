"""Readonly, fail-closed validation of private Drive source ZIP metadata and master SHA."""
import argparse
import hashlib
import json
import os
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MASTER = 'YouTube_Kennisbron_Master.zip'
ZIP_MIME = 'application/zip'
MASTER_SHA = '2aa93bbe7b1db1d872c9d8614240dbbdf0f0c061e0de5c6e0e753a2954763e59'
SIZES = [17090078,17753939,17266221,16801517,18022981,17427576,17900852,17901878,18131208,15294892,6146858,15574138,5288889,1368341,3283959]
EXPECTED_BYTES = {MASTER: 2161500, **{f'YouTube_Kennisbron_Master.part-{i:02}.zip': n for i,n in enumerate(SIZES,1)}}

class DrivePreflightError(Exception): pass

def verify_inventory(files):
    if not isinstance(files,list) or len(files)!=16: raise DrivePreflightError('wrong_file_count')
    found={}
    for f in files:
        if not isinstance(f,dict) or f.get('name') not in EXPECTED_BYTES or f['name'] in found:
            raise DrivePreflightError('unexpected_or_duplicate_file')
        if f.get('mimeType') not in (ZIP_MIME,'application/x-zip-compressed'):
            raise DrivePreflightError('wrong_type')
        if not re.fullmatch('[A-Za-z0-9_-]{10,200}', str(f.get('id',''))):
            raise DrivePreflightError('bad_file_id')
        if str(f.get('size')) != str(EXPECTED_BYTES[f['name']]):
            raise DrivePreflightError('source_drift')
        found[f['name']]=f
    if set(found)!=set(EXPECTED_BYTES): raise DrivePreflightError('missing_file')
    return {'count':16,'total_bytes':sum(EXPECTED_BYTES.values()),'master_id':found[MASTER]['id']}

def get(url,token,maxbytes):
    with urlopen(Request(url,headers={'Authorization':'Bearer '+token}),timeout=90) as resp:
        if resp.status != 200: raise DrivePreflightError('bad_http_status')
        return resp.read(maxbytes+1)

def list_folder(folder,token):
    if not re.fullmatch('[A-Za-z0-9_-]{10,200}',folder): raise DrivePreflightError('bad_folder_id')
    params=urlencode({'q':f"'{folder}' in parents and trashed = false",'fields':'nextPageToken,incompleteSearch,files(id,name,mimeType,size)','pageSize':'1000'})
    data=json.loads(get('https://www.googleapis.com/drive/v3/files?'+params,token,500000))
    if data.get('nextPageToken') or data.get('incompleteSearch'): raise DrivePreflightError('incomplete_listing')
    return data.get('files')

def check(folder,token):
    master_id=verify_inventory(list_folder(folder,token))['master_id']
    raw=get('https://www.googleapis.com/drive/v3/files/'+master_id+'?alt=media',token,4000000)
    if len(raw)!=2161500 or hashlib.sha256(raw).hexdigest()!=MASTER_SHA:
        raise DrivePreflightError('master_checksum_drift')
    return {'status':'PASS','verified_zip_files':16,'source_bytes':sum(EXPECTED_BYTES.values()),'master_hash_match':True,'transcripts_uploaded_to_public_github':False,'full_review_complete':False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--folder-id',required=True)
    args=p.parse_args()
    token=os.environ.get('DRIVE_ACCESS_TOKEN','')
    if not token: print('BLOCKED: no credential',file=sys.stderr);return 2
    try: print(json.dumps(check(args.folder_id,token),sort_keys=True));return 0
    except Exception: print('BLOCKED: private Drive preflight failed (no private details logged)',file=sys.stderr);return 2

if __name__=='__main__': sys.exit(main())
