import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from execution_plan import install_plan, load_plan
from execution_trace import file_ref
from run_step import execute

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def example_plan(root):
    (root / 'domain.json').write_text('{"directions":["vlm"]}')
    return {'schema_version': 1, 'run_id': root.name, 'domain': 'embodied-ai',
            'code_version': 'test', 'directions': ['vlm'],
            'config_refs': [file_ref('domain.json', root)],
            'tasks': [{'id': 'vlm-search', 'kind': 'discovery', 'direction': 'vlm',
                       'channel': 'open-source', 'input': 'embodied reasoning',
                       'expected_artifacts': ['result.json']}]}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'TALENT_SCOUT_LANGSMITH': 'false'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.plan = example_plan(self.root)
        install_plan(self.root, self.plan)

    def events(self):
        return [json.loads(line) for f in (self.root / 'traces').glob('*.jsonl')
                for line in f.read_text().splitlines()]

    def test_cli_stdout_and_exit_code_remain_usable(self):
        command = [sys.executable, str(SCRIPTS / 'run_step.py'), 'run', '--run-dir', str(self.root),
                   '--task', 'vlm-search', '--', sys.executable, '-c', 'print("jsonl"); raise SystemExit(7)']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, 'jsonl\n')
        self.assertEqual(self.events()[-1]['status'], 'error')

    def test_subprocess_inherits_trace_and_task_context(self):
        code = ('import sys; sys.path.insert(0, ' + repr(str(SCRIPTS)) + '); '
                'from execution_trace import Span; '
                '\nwith Span("child") as s: s.outputs={"result_count": 0}\nprint("{}")')
        self.assertEqual(execute(self.root, 'vlm-search', [sys.executable, '-c', code], 'result.json'), 0)
        end = {e['name']: e for e in self.events() if e['event'] == 'end'}
        self.assertEqual(end['child']['parent_span_id'], end['execute_step']['span_id'])
        self.assertEqual(end['child']['task_id'], 'vlm-search')
        self.assertEqual(end['child']['metadata']['plan_hash'], end['execute_step']['metadata']['plan_hash'])
        self.assertEqual(end['execute_step']['outputs']['artifacts'][0]['path'], 'result.json')
        self.assertNotIn(code, json.dumps(self.events()))

    def test_stale_artifact_does_not_count_as_new_delivery(self):
        (self.root / 'result.json').write_text('{}')
        execute(self.root, 'vlm-search', [sys.executable, '-c', 'pass'])
        self.assertEqual(self.events()[-1]['status'], 'incomplete')
        self.assertEqual(self.events()[-1]['outputs']['unchanged_artifacts'], ['result.json'])

    def test_missing_command_records_error(self):
        with self.assertRaises(FileNotFoundError):
            execute(self.root, 'vlm-search', ['/nonexistent/talent-scout-command'])
        self.assertEqual(self.events()[-1]['error_type'], 'FileNotFoundError')

    def test_unknown_task_and_escaped_output_rejected_before_launch(self):
        for task, output in [('unknown', None), ('vlm-search', '../escape')]:
            with self.subTest(task=task), self.assertRaises(ValueError):
                execute(self.root, task, [sys.executable, '-c', 'pass'], output)
        self.assertFalse((self.root / 'traces').exists())

    def test_plan_overwrite_and_tampering_rejected(self):
        with self.assertRaises(ValueError):
            install_plan(self.root, self.plan)
        (self.root / 'execution-plan.json').write_text(json.dumps({**self.plan, 'domain': 'changed'}))
        with self.assertRaises(ValueError):
            load_plan(self.root)

    def test_amendment_keeps_previous_plan(self):
        old_hash = load_plan(self.root)[1]
        new_hash = install_plan(self.root, {**self.plan, 'code_version': 'new'}, 'refresh code')
        revised, _ = load_plan(self.root)
        self.assertEqual(revised['previous_hash'], old_hash)
        self.assertNotEqual(new_hash, old_hash)
        self.assertEqual(len(list((self.root / 'plans').glob('*.json'))), 2)


if __name__ == '__main__':
    unittest.main()
