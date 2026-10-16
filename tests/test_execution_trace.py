import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import execution_trace as et


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'TALENT_SCOUT_RUN_DIR': str(self.root),
                              'TALENT_SCOUT_LANGSMITH': 'false'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def events(self):
        return [json.loads(line) for p in (self.root / 'traces').glob('*.jsonl')
                for line in p.read_text().splitlines()]

    def test_nested_spans_and_exception_preserve_identity(self):
        with et.Span('root', task_id='vla', metadata={'direction': 'vla'}) as root:
            with self.assertRaisesRegex(ValueError, 'secret'):
                with et.Span('fetch'):
                    raise ValueError('secret')
        end = {e['name']: e for e in self.events() if e['event'] == 'end'}
        self.assertEqual(end['fetch']['parent_span_id'], root.record['span_id'])
        self.assertEqual(end['fetch']['trace_id'], root.record['trace_id'])
        self.assertEqual(end['fetch']['task_id'], 'vla')
        self.assertEqual(end['fetch']['status'], 'error')
        self.assertEqual(end['fetch']['metadata']['direction'], 'vla')
        self.assertNotIn('secret', json.dumps(self.events()))

    def test_upload_failure_keeps_local_result(self):
        with patch.object(et, 'export_record', side_effect=RuntimeError('private')):
            with et.Span('work') as span:
                span.outputs = {'result_count': 3}
        self.assertEqual(self.events()[-1]['event'], 'upload_error')
        self.assertEqual(self.events()[-2]['outputs']['result_count'], 3)
        self.assertNotIn('private', json.dumps(self.events()))

    def test_no_sdk_required_when_upload_disabled(self):
        with patch.dict(sys.modules, {'langsmith': None}):
            with et.Span('local'):
                pass
        self.assertEqual(len(self.events()), 2)

    def test_redaction_and_no_input_mutation(self):
        with patch.dict(os.environ, {'OPENALEX_API_KEY': 'very-private'}):
            data = {'url': 'https://user:pwd@example.org/x?api_key=very-private&search=vla',
                    'headers': {'Authorization': 'Bearer other-secret'}, 'note': 'very-private'}
            clean = et.sanitize(data)
        encoded = json.dumps(clean)
        for secret in ('very-private', 'other-secret', 'user:pwd'):
            self.assertNotIn(secret, encoded)
        self.assertIn('search=vla', encoded)
        self.assertEqual(data['note'], 'very-private')

    def test_file_reference_rejects_escape_and_detects_changes(self):
        p = self.root / 'result.json'
        p.write_text('{}')
        old = et.file_ref(p, self.root)
        p.write_text('{"changed": true}')
        self.assertNotEqual(old['sha256'], et.file_ref(p, self.root)['sha256'])
        with self.assertRaises(ValueError):
            et.file_ref('../escape', self.root)

    def test_disabled_decorator_preserves_outputs(self):
        with patch.dict(os.environ, {}, clear=True):
            @et.traced('tool', inputs=lambda: self.fail('disabled tracing ran'))
            def tool():
                return {'private': 'not logged'}
            self.assertEqual(tool(), {'private': 'not logged'})
        self.assertFalse((self.root / 'traces').exists())

    def test_exporter_sends_parent_metadata_without_page_body(self):
        client = Mock()
        with patch.dict(os.environ, {'TALENT_SCOUT_LANGSMITH': 'true'}), patch.object(et, '_client', client):
            with et.Span('parent'):
                with et.Span('child') as child:
                    child.outputs = {'chars': 12}
            et.flush()
        args = client.create_run.call_args_list[0].kwargs
        self.assertIsNotNone(args['parent_run_id'])
        self.assertEqual(args['outputs'], {'chars': 12})
        client.flush.assert_called_once()

    def test_unwritable_local_trace_prevents_operation(self):
        invoked = Mock()
        @et.traced('write-required')
        def operation():
            invoked()
        with patch.object(et.Span, '_write', side_effect=OSError('storage unavailable')):
            with self.assertRaises(OSError):
                operation()
        invoked.assert_not_called()

    def test_nested_context_without_environment_and_flush_failure(self):
        with patch.dict(os.environ, {}, clear=True):
            with et.Span('parent', run_dir=self.root) as parent:
                with et.Span('child') as child:
                    self.assertEqual(child.record['parent_span_id'], parent.record['span_id'])
        client = Mock()
        client.flush.side_effect = RuntimeError('private')
        with patch.object(et, '_client', client):
            et.flush()  # Remote failure must not raise during process shutdown.


if __name__ == '__main__':
    unittest.main()
