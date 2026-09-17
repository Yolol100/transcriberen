import json
import os
import pathlib
import tempfile
import unittest
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import channel_runtime as channel
import captions_runtime as captions
import cache_runtime as cache
import validate_result as validator


REQUEST = {
    "schema_version": "3.0",
    "enabled": True,
    "request_id": "bulk-001",
    "url": "https://www.youtube.com/@Example/videos",
    "source_type": "channel",
    "language": "auto",
    "year": 2026,
    "max_videos": 1000,
    "comments_per_video": 7,
    "comment_sort": "top",
    "include_replies": False,
}


class ChannelRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_state = os.environ.get('TRANSCRIBE_STATE_DIR')
        os.environ['TRANSCRIBE_STATE_DIR'] = self.temp.name
        self.old_request_file = os.environ.get('REQUEST_FILE')
        os.environ['REQUEST_FILE'] = str(ROOT / 'resolved-request.json')
        (ROOT / 'resolved-request.json').write_text(json.dumps(REQUEST), encoding='utf-8')
        self.originals = (
            channel.discover_channel,
            captions.runtime_provenance,
            captions.load_metadata,
            captions.choose_caption_track,
            captions.download_caption,
            captions.load_top_comments,
        )
        captions.runtime_provenance = lambda: {
            'execution_target': 'test',
            'yt_dlp_version': 'test',
            'deno_version': 'test',
        }

    def tearDown(self):
        (
            channel.discover_channel,
            captions.runtime_provenance,
            captions.load_metadata,
            captions.choose_caption_track,
            captions.download_caption,
            captions.load_top_comments,
        ) = self.originals
        if self.old_request_file is None:
            os.environ.pop('REQUEST_FILE', None)
        else:
            os.environ['REQUEST_FILE'] = self.old_request_file
        if self.old_state is None:
            os.environ.pop('TRANSCRIBE_STATE_DIR', None)
        else:
            os.environ['TRANSCRIBE_STATE_DIR'] = self.old_state
        (ROOT / 'resolved-request.json').unlink(missing_ok=True)
        self.temp.cleanup()

    def valid_video(self, vid='AAAAAAAAAAA', upload_date='20260304'):
        return {
            'id': vid,
            'title': vid,
            'upload_date': upload_date,
            'subtitles': {'en': [{'url':'https://x'}]},
            'automatic_captions': {},
        }

    def use_happy_caption_stubs(self):
        captions.choose_caption_track = lambda meta, language: {'language':'en','kind':'manual'}
        captions.download_caption = lambda url, track: ('hello world\n', {'language':'en','kind':'manual','format':'vtt','cue_count':1})
        captions.load_top_comments = lambda url, limit: ([{'id':'1','author':'a','text':'top','like_count':1,'timestamp':None,'is_pinned':False,'author_is_uploader':False}], 'ok')

    def test_only_2026_videos_enter_manifest(self):
        ids = ['AAAAAAAAAAA', 'BBBBBBBBBBB']
        channel.discover_channel = lambda url, limit: ({'id':'UC1','title':'Example','url':url}, ids)
        captions.load_metadata = lambda url: self.valid_video(url[-11:], '20260304' if url.endswith(ids[0]) else '20251231')
        self.use_happy_caption_stubs()
        channel.main()
        manifest = json.loads((ROOT / 'results/manifest.json').read_text())
        self.assertEqual(len(manifest['items']), 1)
        self.assertEqual(manifest['items'][0]['video_id'], ids[0])
        self.assertEqual(manifest['counts']['matched_2026'], 1)
        validator.validate(ROOT / 'results/result.json')

    def test_no_caption_still_keeps_comments(self):
        vid = 'CCCCCCCCCCC'
        channel.discover_channel = lambda url, limit: ({'id':'UC1','title':'Example','url':url}, [vid])
        captions.load_metadata = lambda url: {**self.valid_video(vid, '20260101'), 'subtitles': {}, 'automatic_captions': {}}
        captions.choose_caption_track = lambda meta, language: None
        captions.load_top_comments = lambda url, limit: ([{'id':str(i),'author':'a','text':str(i),'like_count':0,'timestamp':None,'is_pinned':False,'author_is_uploader':False} for i in range(7)], 'ok')
        channel.main()
        comments = json.loads((ROOT / 'results/videos' / vid / 'comments.json').read_text())
        self.assertEqual(comments['count'], 7)
        self.assertFalse((ROOT / 'results/videos' / vid / 'transcript.txt').exists())
        validator.validate(ROOT / 'results/result.json')

    def test_metadata_failure_is_visible_and_partial(self):
        ids = ['DDDDDDDDDDD', 'EEEEEEEEEEE']
        channel.discover_channel = lambda url, limit: ({'id':'UC1','title':'Example','url':url}, ids)
        def metadata(url):
            if url.endswith(ids[0]):
                raise RuntimeError('access_blocked::blocked')
            return self.valid_video(ids[1])
        captions.load_metadata = metadata
        self.use_happy_caption_stubs()
        channel.main()
        result = json.loads((ROOT / 'results/result.json').read_text())
        manifest = json.loads((ROOT / 'results/manifest.json').read_text())
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(manifest['counts']['metadata_failures'], 1)
        self.assertEqual(manifest['unresolved'][0]['video_id'], ids[0])
        validator.validate(ROOT / 'results/result.json')

    def test_missing_comments_marks_corpus_partial(self):
        vid = 'FFFFFFFFFFF'
        channel.discover_channel = lambda url, limit: ({'id':'UC1','title':'Example','url':url}, [vid])
        captions.load_metadata = lambda url: self.valid_video(vid)
        self.use_happy_caption_stubs()
        captions.load_top_comments = lambda url, limit: ([], 'unavailable')
        channel.main()
        result = json.loads((ROOT / 'results/result.json').read_text())
        self.assertEqual(result['status'], 'partial')
        self.assertIn('comments_unavailable', result['partial_reasons'])
        validator.validate(ROOT / 'results/result.json')

    def test_processed_index_does_not_export_prior_channel_state(self):
        unrelated = 'GGGGGGGGGGG'
        with cache.connect() as conn:
            cache.store_result(
                conn,
                video_id=unrelated,
                language='auto',
                url=f'https://www.youtube.com/watch?v={unrelated}',
                status='ok',
                caption={'language':'en','kind':'manual','format':'vtt','cue_count':1},
                transcript='old channel\n',
            )
        vid = 'HHHHHHHHHHH'
        channel.discover_channel = lambda url, limit: ({'id':'UC1','title':'Example','url':url}, [vid])
        captions.load_metadata = lambda url: self.valid_video(vid)
        self.use_happy_caption_stubs()
        channel.main()
        index = json.loads((ROOT / 'results/processed-index.json').read_text())
        self.assertEqual([item['video_id'] for item in index['items']], [vid])
        validator.validate(ROOT / 'results/result.json')

    def test_channel_discovery_failure_still_has_valid_readback_contract(self):
        channel.discover_channel = lambda url, limit: (_ for _ in ()).throw(RuntimeError('access_blocked::blocked'))
        channel.main()
        result = json.loads((ROOT / 'results/result.json').read_text())
        self.assertEqual(result['status'], 'access_blocked')
        validator.validate(ROOT / 'results/result.json')


if __name__ == '__main__':
    unittest.main()
