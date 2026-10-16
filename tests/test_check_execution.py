import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_execution as ce
from execution_plan import install_plan, load_plan, validate
from execution_trace import Span, file_ref
from test_run_step import example_plan


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'TALENT_SCOUT_RUN_DIR': str(self.root),
                                         'TALENT_SCOUT_LANGSMITH': 'false'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.plan = example_plan(self.root)
        self.revision = install_plan(self.root, self.plan)

    def attempt(self, count=0, error=False, handoff=True, pending=0):
        with Span('execute_step', task_id='vlm-search', metadata={'plan_hash': self.revision}) as parent:
            with Span('search', metadata={'operation': 'retrieval'}) as search:
                search.status = 'error' if error else 'success'
                search.outputs = {'result_count': count}
            (self.root / 'result.json').write_text(json.dumps({'count': count}))
            parent.outputs = {'exit_code': 0, 'artifacts': [file_ref('result.json', self.root)]}
        if handoff:
            ce.record_handoff(self.root, {'attempt_id': parent.record['span_id'],
                'outcome': 'partial' if pending else 'zero_results' if count == 0 else 'complete',
                'lead_count': pending, 'resolved_count': 0, 'unresolved_count': pending,
                'stop_reason': 'budget_exhausted' if pending else 'sources_exhausted',
                'evidence': ['result.json'], 'gaps': []})
        return parent

    def test_missing_execution_is_not_zero(self):
        report = ce.check(self.root)
        self.assertEqual(report['status'], 'incomplete')
        self.assertIn('not_executed', report['tasks'][0]['issues'])

    def test_genuine_zero_is_complete_with_successful_request(self):
        self.attempt()
        self.assertEqual(ce.check(self.root)['status'], 'complete')

    def test_failed_request_cannot_be_reported_as_zero(self):
        self.attempt(error=True)
        report = ce.check(self.root)
        self.assertEqual(report['status'], 'incomplete')
        self.assertIn('zero_results_without_observed_empty_response', report['tasks'][0]['issues'])

    def test_budget_exhaustion_and_unresolved_author_remain_gaps(self):
        self.attempt(count=2, pending=2)
        report = ce.check(self.root)
        self.assertIn('unresolved_leads_or_coverage_gaps', report['tasks'][0]['issues'])
        self.assertEqual(report['status'], 'incomplete')

    def test_changed_artifact_and_evidence_rejected(self):
        self.attempt()
        (self.root / 'result.json').write_text('changed')
        report = ce.check(self.root)
        self.assertIn('missing_or_changed_artifact:result.json', report['tasks'][0]['issues'])
        self.assertIn('missing_or_invalid_research_handoff', report['tasks'][0]['issues'])

    def test_latest_interrupted_attempt_overrides_prior_success(self):
        self.attempt()
        interrupted = Span('execute_step', task_id='vlm-search', metadata={'plan_hash': self.revision})
        interrupted.__enter__()
        try:
            self.assertIn('interrupted_or_running', ce.check(self.root)['tasks'][0]['issues'])
        finally:
            interrupted.__exit__(None, None, None)

    def test_missing_direction_in_plan_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan['directions'].append('vla')
        with self.assertRaisesRegex(ValueError, 'missing discovery'):
            validate(plan)

    def test_duplicate_ids_and_escape_paths_rejected(self):
        for mutate in (lambda p: p['tasks'].append(copy.deepcopy(p['tasks'][0])),
                       lambda p: p['tasks'][0].update(expected_artifacts=['../outside'])):
            plan = copy.deepcopy(self.plan)
            mutate(plan)
            with self.assertRaises(ValueError):
                validate(plan)

    def test_legacy_without_plan_is_not_certified(self):
        (self.root / 'execution-plan.json').unlink()
        self.assertEqual(ce.check(self.root)['status'], 'not_checked')

    def test_legacy_plan_does_not_claim_direction_check(self):
        self.plan['directions'] = []
        self.plan['tasks'][0]['direction'] = None
        self.revision = install_plan(self.root, self.plan, 'legacy domain')
        self.attempt()
        self.assertEqual(ce.check(self.root)['direction_check'], 'not_checked')

    def test_config_change_invalidates_check(self):
        (self.root / 'domain.json').write_text('{}')
        self.assertEqual(ce.check(self.root)['status'], 'invalid')

    def test_handoff_cannot_be_overwritten_or_attach_to_old_revision(self):
        parent = self.attempt(handoff=False)
        value = {'attempt_id': parent.record['span_id'], 'outcome': 'zero_results',
                 'lead_count': 0, 'resolved_count': 0, 'unresolved_count': 0,
                 'stop_reason': 'exhausted', 'evidence': ['result.json'], 'gaps': []}
        ce.record_handoff(self.root, value)
        with self.assertRaises(FileExistsError):
            ce.record_handoff(self.root, value)
        install_plan(self.root, {**self.plan, 'code_version': 'next'}, 'code update')
        with self.assertRaises(ValueError):
            ce.record_handoff(self.root, value)

    def test_truncated_trace_fails_closed(self):
        self.attempt()
        next((self.root / 'traces').glob('*.jsonl')).write_text('{')
        self.assertEqual(ce.check(self.root)['status'], 'invalid')

    def test_pagination_cursor_requires_followup(self):
        parent = self.attempt()
        from unittest.mock import patch
        with patch.dict(os.environ, parent.child_env()):
            with Span('next-page', inputs={'path': '/works', 'query': {'search': 'vla'}},
                      metadata={'operation': 'retrieval'}) as page:
                page.outputs = {'result_count': 0, 'next_cursor': 'not-yet-fetched'}
        self.assertIn('unprocessed_pagination_cursor', ce.check(self.root)['tasks'][0]['issues'])

    def test_shared_channel_budget_counts_failed_attempts(self):
        self.plan['channel_page_budgets'] = {'open-source': 1}
        self.revision = install_plan(self.root, self.plan, 'explicit budget')
        for _ in range(2):
            parent = self.attempt()
            with patch.dict(os.environ, parent.child_env()):
                with Span('http', metadata={'operation': 'page_attempt'}) as page:
                    page.status = 'error'
        row = ce.check(self.root)['tasks'][0]
        self.assertEqual(row['page_attempts'], 2)
        self.assertIn('shared_channel_page_budget_exceeded', row['issues'])

    def test_unrelated_file_cannot_be_used_as_observed_evidence(self):
        parent = self.attempt(handoff=False)
        (self.root / 'unrelated.json').write_text('{}')
        ce.record_handoff(self.root, {'attempt_id': parent.record['span_id'], 'outcome': 'zero_results',
                'lead_count': 0, 'resolved_count': 0, 'unresolved_count': 0, 'stop_reason': 'sources_exhausted',
                'evidence': ['unrelated.json'], 'gaps': []})
        self.assertIn('evidence_not_linked_to_observed_artifact', ce.check(self.root)['tasks'][0]['issues'])

    def test_control_files_and_config_cannot_be_task_outputs(self):
        for path in ('execution-plan.json', 'run.meta.json', 'traces/fake.jsonl', 'domain.json'):
            plan = copy.deepcopy(self.plan)
            plan['tasks'][0]['expected_artifacts'] = [path]
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate(plan)

    def test_amending_plan_does_not_reset_channel_budget(self):
        self.plan['channel_page_budgets'] = {'open-source': 1}
        self.revision = install_plan(self.root, self.plan, 'explicit budget')
        for version in range(2):
            if version:
                self.revision = install_plan(self.root, {**self.plan, 'code_version': 'next'}, 'new code')
            parent = self.attempt()
            with patch.dict(os.environ, parent.child_env()):
                with Span('http', metadata={'operation': 'page_attempt'}):
                    pass
        report = ce.check(self.root)
        self.assertEqual(report['channel_usage']['open-source']['observed_attempts'], 2)
        self.assertIn('shared_channel_page_budget_exceeded', report['tasks'][0]['issues'])

    def test_successful_query_does_not_hide_another_failed_query(self):
        parent = self.attempt()
        with patch.dict(os.environ, parent.child_env()):
            with Span('search', inputs={'query': 'another query'}, metadata={'operation': 'retrieval'}) as failed:
                failed.status = 'error'
        self.assertIn('unrecovered_retrieval_failure', ce.check(self.root)['tasks'][0]['issues'])
        with patch.dict(os.environ, parent.child_env()):
            with Span('search', inputs={'query': 'another query'}, metadata={'operation': 'retrieval'}) as recovered:
                recovered.outputs = {'result_count': 0}
        self.assertEqual(ce.check(self.root)['status'], 'complete')


if __name__ == '__main__':
    unittest.main()
