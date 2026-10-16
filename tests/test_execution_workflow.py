"""Exercise the documented CLI workflow with synthetic responses and no network."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from execution_trace import file_ref
from test_run_step import example_plan

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


class WorkflowTests(unittest.TestCase):
    def test_documented_cli_plan_execution_handoff_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {**os.environ, 'TALENT_SCOUT_LANGSMITH': 'false'}
            env.pop('TALENT_SCOUT_TRACE_CONTEXT', None)
            env.pop('TALENT_SCOUT_RUN_DIR', None)
            plan = example_plan(root)
            plan['directions'].append('vla')
            plan['tasks'].append({**plan['tasks'][0], 'id': 'vla-search', 'direction': 'vla',
                                  'expected_artifacts': ['vla.json']})
            (root / 'draft.json').write_text(json.dumps(plan))

            def cli(script, *args):
                return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                                      capture_output=True, text=True, env=env, timeout=10)

            init = cli('run_step.py', 'init', '--run-dir', root, '--plan', root / 'draft.json')
            self.assertEqual(init.returncode, 0, init.stderr)
            code = ('import io,json,sys; from unittest.mock import patch; '
                    'sys.path.insert(0,' + repr(str(SCRIPTS)) + '); import openalex_lookup as oa; '
                    '\nwith patch.object(oa,"auth_headers",return_value={}), '
                    'patch.object(oa.urllib.request,"urlopen",return_value=io.BytesIO(b\'{"results": []}\')):'
                    '\n print(json.dumps(oa.get("/works", {"search":"robot reasoning"})))')
            for task_id, artifact in [('vlm-search', 'result.json'), ('vla-search', 'vla.json')]:
                run = cli('run_step.py', 'run', '--run-dir', root, '--task', task_id,
                          '--stdout', artifact, '--', sys.executable, '-c', code)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(json.loads((root / artifact).read_text()), {'results': []})
                spans = [json.loads(line) for p in (root / 'traces').glob('*.jsonl')
                         for line in p.read_text().splitlines()]
                attempt = next(e for e in spans if e['event'] == 'end'
                               and e['name'] == 'execute_step' and e['task_id'] == task_id)
                handoff = {'attempt_id': attempt['span_id'], 'outcome': 'zero_results',
                           'lead_count': 0, 'resolved_count': 0, 'unresolved_count': 0,
                           'stop_reason': 'sources_exhausted', 'evidence': [artifact], 'gaps': []}
                (root / 'handoff.json').write_text(json.dumps(handoff))
                record = cli('check_execution.py', '--run-dir', root, '--record', root / 'handoff.json')
                self.assertEqual(record.returncode, 0, record.stderr)
                check = cli('check_execution.py', '--run-dir', root)
                self.assertEqual(check.returncode, 2 if task_id == 'vlm-search' else 0, check.stderr)
                report = json.loads((root / 'execution-check.json').read_text())
                if task_id == 'vlm-search':
                    self.assertEqual(report['tasks'][1]['issues'], ['not_executed'])
            self.assertEqual(report['direction_check'], 'checked')
            self.assertTrue((root / 'execution-check.md').is_file())
            self.assertEqual(len(list((root / 'task-results').glob('*.json'))), 2)

    def test_all_referenced_execution_files_exist(self):
        # Link validity, not a wording assertion: the workflow must be navigable by a skill host.
        import re
        root = SCRIPTS.parent
        files = ['SKILL.md', 'references/20-execution-tracing.md', 'scripts/README.md']
        for name in files:
            contents = (root / name).read_text()
            for target in re.findall(r'`((?:scripts|assets|references)/(?:[^`\s]+\.(?:py|json|md|txt)))`', contents):
                self.assertTrue((root / target).is_file(), target)


if __name__ == '__main__':
    unittest.main()
