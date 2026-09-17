import json
import os
import pathlib
import tempfile
import unittest
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'; sys.path.insert(0,str(SCRIPTS))
import channel_runtime as channel
import captions_runtime as captions
import validate_result as validator

class ChannelRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.old_state=os.environ.get('TRANSCRIBE_STATE_DIR'); os.environ['TRANSCRIBE_STATE_DIR']=self.temp.name
        self.old_request_file=os.environ.get('REQUEST_FILE'); os.environ['REQUEST_FILE']=str(ROOT/'resolved-request.json')
        request={"schema_version":"3.0","enabled":True,"request_id":"bulk-001","url":"https://www.youtube.com/@Example/videos","source_type":"channel","language":"auto","year":2026,"max_videos":1000,"comments_per_video":7,"comment_sort":"top","include_replies":False}
        (ROOT/'resolved-request.json').write_text(json.dumps(request),encoding='utf-8')
        self.originals=(channel.discover_channel,captions.runtime_provenance,captions.load_metadata,captions.choose_caption_track,captions.download_caption,captions.load_top_comments)
    def tearDown(self):
        channel.discover_channel,captions.runtime_provenance,captions.load_metadata,captions.choose_caption_track,captions.download_caption,captions.load_top_comments=self.originals
        if self.old_request_file is None: os.environ.pop('REQUEST_FILE',None)
        else: os.environ['REQUEST_FILE']=self.old_request_file
        if self.old_state is None: os.environ.pop('TRANSCRIBE_STATE_DIR',None)
        else: os.environ['TRANSCRIBE_STATE_DIR']=self.old_state
        self.temp.cleanup()
    def test_only_2026_videos_enter_manifest(self):
        ids=['AAAAAAAAAAA','BBBBBBBBBBB']
        channel.discover_channel=lambda url,limit: ({'id':'UC1','title':'Example','url':url},ids)
        captions.runtime_provenance=lambda: {'execution_target':'test','yt_dlp_version':'test','deno_version':'test'}
        captions.load_metadata=lambda url: {'id':url[-11:],'title':url[-11:],'upload_date':'20260304' if url.endswith(ids[0]) else '20251231','subtitles':{'en':[{'url':'https://x'}]},'automatic_captions':{}}
        captions.choose_caption_track=lambda meta,language: {'language':'en','kind':'manual'}
        captions.download_caption=lambda url,track: ('hello world\n',{'language':'en','kind':'manual','format':'vtt','cue_count':1})
        captions.load_top_comments=lambda url,limit: ([{'id':'1','author':'a','text':'top','like_count':1,'timestamp':None,'is_pinned':False,'author_is_uploader':False}],'ok')
        channel.main(); manifest=json.loads((ROOT/'results/manifest.json').read_text())
        self.assertEqual(len(manifest['items']),1); self.assertEqual(manifest['items'][0]['video_id'],ids[0]); self.assertEqual(manifest['counts']['matched_2026'],1)
        validator.validate(ROOT/'results/result.json')
    def test_no_caption_still_keeps_comments(self):
        vid='CCCCCCCCCCC'
        channel.discover_channel=lambda url,limit: ({'id':'UC1','title':'Example','url':url},[vid])
        captions.runtime_provenance=lambda: {'execution_target':'test','yt_dlp_version':'test','deno_version':'test'}
        captions.load_metadata=lambda url: {'id':vid,'title':'No captions','upload_date':'20260101','subtitles':{},'automatic_captions':{}}
        captions.choose_caption_track=lambda meta,language: None
        captions.load_top_comments=lambda url,limit: ([{'id':str(i),'author':'a','text':str(i),'like_count':0,'timestamp':None,'is_pinned':False,'author_is_uploader':False} for i in range(7)],'ok')
        channel.main(); comments=json.loads((ROOT/'results/videos'/vid/'comments.json').read_text())
        self.assertEqual(comments['count'],7); self.assertFalse((ROOT/'results/videos'/vid/'transcript.txt').exists())

if __name__ == '__main__': unittest.main()
