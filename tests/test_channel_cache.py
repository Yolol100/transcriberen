import os
import pathlib
import tempfile
import unittest
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cache_runtime as cache


class ChannelCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_state = os.environ.get('TRANSCRIBE_STATE_DIR')
        os.environ['TRANSCRIBE_STATE_DIR'] = self.temp.name

    def tearDown(self):
        if self.old_state is None:
            os.environ.pop('TRANSCRIBE_STATE_DIR', None)
        else:
            os.environ['TRANSCRIBE_STATE_DIR'] = self.old_state
        self.temp.cleanup()

    def store(self, conn, video_id, language='auto', text='hello\n'):
        cache.store_result(
            conn,
            video_id=video_id,
            language=language,
            url=f'https://www.youtube.com/watch?v={video_id}',
            status='ok',
            caption={'language':'en','kind':'manual','format':'vtt','cue_count':1},
            transcript=text,
        )

    def test_valid_transcript_is_reused(self):
        with cache.connect() as conn:
            self.store(conn, 'AAAAAAAAAAA')
            hit = cache.get_cached_transcript(conn, 'AAAAAAAAAAA', 'auto')
        self.assertIsNotNone(hit)
        self.assertEqual(hit['text'], 'hello\n')

    def test_corrupt_transcript_is_invalidated(self):
        with cache.connect() as conn:
            self.store(conn, 'BBBBBBBBBBB')
            conn.execute("UPDATE processed SET transcript_text='tampered' WHERE video_id='BBBBBBBBBBB'")
            conn.commit()
            hit = cache.get_cached_transcript(conn, 'BBBBBBBBBBB', 'auto')
            left = conn.execute("SELECT COUNT(*) FROM processed WHERE video_id='BBBBBBBBBBB'").fetchone()[0]
        self.assertIsNone(hit)
        self.assertEqual(left, 0)

    def test_export_index_is_scoped_to_current_run(self):
        with cache.connect() as conn:
            self.store(conn, 'AAAAAAAAAAA')
            self.store(conn, 'BBBBBBBBBBB')
            out = pathlib.Path(self.temp.name) / 'index.json'
            payload = cache.export_index(conn, out, entries=[('AAAAAAAAAAA', 'auto')])
        self.assertEqual(payload['scope'], 'current_run')
        self.assertEqual(payload['requested_entries'], 1)
        self.assertEqual([item['video_id'] for item in payload['items']], ['AAAAAAAAAAA'])


if __name__ == '__main__': unittest.main()
