from concurrent.futures import ThreadPoolExecutor
from email.message import Message
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_affiliation as ca
import openalex_lookup as oa
import visit_page as vp
from execution_trace import Span


class Response(io.BytesIO):
    def __init__(self, content, status=200):
        super().__init__(content)
        self.status = status
        self.headers = Message()
        self.headers['Content-Type'] = 'text/html; charset=utf-8'

    def geturl(self):
        return 'https://example.org/team'


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {'TALENT_SCOUT_RUN_DIR': str(self.root),
                                     'TALENT_SCOUT_LANGSMITH': 'false'}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def ended(self):
        return [json.loads(line) for p in (self.root / 'traces').glob('*.jsonl')
                for line in p.read_text().splitlines() if json.loads(line)['event'] == 'end']

    def test_page_attempt_read_save_and_no_body_in_trace(self):
        body = b'<html><body>PRIVATE_PAGE_TEXT PhD student</body></html>'
        opener = Mock()
        opener.open.return_value = Response(body)
        with patch.object(vp.urllib.request, 'build_opener', return_value=opener):
            result = vp.visit('https://example.org/team', ladder=('http',))
            vp.save(result, self.root / 'page.json')
        events = {e['name']: e for e in self.ended()}
        self.assertEqual(events['web.http']['metadata']['operation'], 'page_attempt')
        self.assertEqual(events['web.http']['parent_span_id'], events['web.visit']['span_id'])
        self.assertEqual(events['web.visit']['status'], 'success')
        self.assertEqual(events['web.save']['outputs']['artifact']['path'], 'page.json')
        self.assertNotIn('PRIVATE_PAGE_TEXT', json.dumps(events))
        self.assertIn('PRIVATE_PAGE_TEXT', (self.root / 'page.json').read_text())
        self.assertFalse(result['role_verified'])

    def test_blocked_page_is_a_failed_retrieval_even_without_exception(self):
        opener = Mock()
        opener.open.return_value = Response(b'Forbidden', 403)
        with patch.object(vp.urllib.request, 'build_opener', return_value=opener):
            result = vp.visit('https://example.org/team', ladder=('http',))
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(all(e['status'] == 'error' for e in self.ended()))

    def test_openalex_records_query_cursor_and_zero_count(self):
        response = io.BytesIO(b'{"results": [], "meta": {"next_cursor": "next-page"}}')
        with patch.object(oa, 'auth_headers', return_value={'Authorization': 'Bearer not-in-env'}), \
                patch.object(oa.urllib.request, 'urlopen', return_value=response):
            value = oa.get('/works', {'search': 'robot VLM', 'cursor': '*'})
        event = self.ended()[0]
        self.assertEqual(event['inputs']['query']['search'], 'robot VLM')
        self.assertEqual(event['outputs']['result_count'], 0)
        self.assertEqual(event['outputs']['next_cursor'], 'next-page')
        self.assertNotIn('not-in-env', json.dumps(event))
        self.assertEqual(value['results'], [])

    def test_openalex_system_exit_is_logged_and_propagated(self):
        with patch.object(oa, 'auth_headers', return_value={}), \
                patch.object(oa.urllib.request, 'urlopen', side_effect=OSError('private-detail')):
            with self.assertRaises(SystemExit):
                oa.get('/works', {'search': 'VLA'})
        self.assertEqual(self.ended()[0]['status'], 'error')
        self.assertNotIn('private-detail', json.dumps(self.ended()))

    def test_cache_hit_and_offline_miss_are_distinct(self):
        cache = ca.ResponseCache(str(self.root / 'cache'))
        response = io.BytesIO(b'{"works_count": 1}')
        with patch.object(ca.urllib.request, 'urlopen', return_value=response) as request:
            one = ca.cached_get('author', 'https://api.openalex.org/authors/A1', cache)
            two = ca.cached_get('author', 'https://api.openalex.org/authors/A1', cache)
        self.assertEqual(one, two)
        request.assert_called_once()
        cache.offline = True
        with patch.object(ca.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            self.assertIsNone(ca.cached_get('missing', 'https://example.org/missing', cache))
        statuses = [e['outputs']['status'] for e in self.ended() if e['name'] == 'affiliation.cache']
        self.assertCountEqual(statuses, ['success', 'cache_hit', 'offline_miss'])

    def test_concurrent_cache_users_keep_trace_context_and_fetch_once(self):
        cache = ca.ResponseCache(str(self.root / 'cache'))
        with Span('execute_step', task_id='affiliations') as parent:
            with patch.dict(os.environ, parent.child_env()), \
                    patch.object(ca, 'get', return_value={'works_count': 2}) as fetch:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    results = list(executor.map(lambda _: ca.cached_get('shared', 'https://example.org/a', cache), range(8)))
        fetch.assert_called_once()
        self.assertEqual(len(results), 8)
        children = [e for e in self.ended() if e['name'] == 'affiliation.lookup']
        self.assertEqual(len(children), 8)
        self.assertTrue(all(e['parent_span_id'] == parent.record['span_id'] for e in children))
        self.assertTrue(all(e['task_id'] == 'affiliations' for e in children))


if __name__ == '__main__':
    unittest.main()
