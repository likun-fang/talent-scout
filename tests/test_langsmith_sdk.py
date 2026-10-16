"""Optional real-SDK contract test. All HTTP is intercepted; no live account is used."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import execution_trace as et


@unittest.skipUnless(importlib.util.find_spec('langsmith'), 'optional LangSmith SDK not installed')
class SDKTests(unittest.TestCase):
    def test_real_client_serializes_parent_child_and_error_payload(self):
        from langsmith import Client
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {'TALENT_SCOUT_LANGSMITH': 'true',
                                       'TALENT_SCOUT_RUN_DIR': tmp}, clear=True), \
                patch.object(Client, 'request_with_retries') as request:
            client = Client(api_url='https://api.smith.langchain.com', api_key='test-only-not-a-real-key',
                            auto_batch_tracing=False)
            with patch.object(et, '_client', client):
                with et.Span('parent', task_id='vla') as parent:
                    with et.Span('child') as child:
                        child.status = 'error'
                        child.outputs = {'status': 'blocked'}
                et.flush()
            payloads = [json.loads(c.kwargs['request_kwargs']['data']) for c in request.call_args_list
                        if c.args[0] == 'POST' and c.args[1].endswith('/runs')]
            self.assertEqual(len(payloads), 2)
            self.assertEqual(payloads[0]['parent_run_id'], parent.record['span_id'])
            self.assertEqual(payloads[0]['trace_id'], payloads[1]['trace_id'])
            self.assertEqual(payloads[0]['error'], 'error')
            self.assertEqual(payloads[0]['extra']['metadata']['task_id'], 'vla')
            self.assertNotIn('test-only-not-a-real-key', json.dumps(payloads))
            events = [json.loads(line) for p in Path(tmp, 'traces').glob('*.jsonl')
                      for line in p.read_text().splitlines()]
            self.assertFalse(any(e['event'] == 'upload_error' for e in events))


if __name__ == '__main__':
    unittest.main()
