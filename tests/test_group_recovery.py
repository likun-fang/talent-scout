import copy
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import group_recovery as gr
from group_relations import person_ref
from person_fields import assign_groups
import table_export as te
import talent_map as tm
from test_talent_map import args, person, FakeGeocoder

DATE = '2026-10-14'
URL = 'https://university.example/robot-lab/team'


def candidate(name='Ada', **extra):
    return person(name, 'Example University', 'DE', 'researcher', '',
                  ids={'openalex': 'A' + name}, **extra)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'group-recovery'
        self.p = candidate()
        gr.plan(self.root, [self.p], DATE)

    def source(self, text='Ada works at Robot Lab, Example University. Profile A Ada.', status='readable'):
        path = self.root / 'pages/source.json'
        gr.write(path, {'status': status, 'requested_url': URL, 'final_url': URL,
                        'retrieved_at': DATE + 'T12:00:00+00:00', 'text': text})
        return {'url': URL, 'path': 'pages/source.json', 'quote': text,
                'observed_on': DATE, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'status': status}

    def result(self, p=None, group=None, outcome='verified_current'):
        p = p or self.p
        task = gr.read(self.root / 'queue.json')['tasks'][person_ref(p)]
        ev = self.source()
        relation = {'person_ref': person_ref(p), 'relation_type': 'member', 'status': 'current',
                    'observed_on': DATE, 'identity_evidence': [ev], 'evidence': [ev],
                    'identity_reason': 'Institutional profile identifies the same university and research record.',
                    'group': group or {'id': 'robot-lab', 'name': 'Robot Lab',
                       'institution': 'Example University', 'url': URL}}
        return {'task_id': task['id'], 'input_hash': task['input_hash'], 'outcome': outcome,
                'reason': 'Reviewed official roster and member profile', 'sources_checked': [ev],
                'relations': [relation] if outcome in {'verified_current', 'historical_only'} else []}

    def test_all_703_targets_resume_and_stable_ids(self):
        ps = [candidate(str(i)) for i in range(703)]
        root = self.root.parent / 'full'
        gr.plan(root, ps, DATE)
        self.assertEqual(gr.check(root)['target_count'], 703)
        queue = gr.read(root / 'queue.json')
        first = next(iter(queue['tasks']))
        queue['tasks'][first]['state'] = 'running'
        gr.write(root / 'queue.json', queue)
        gr.plan(root, list(reversed(ps)), DATE)
        self.assertEqual(len(gr.read(root / 'queue.json')['tasks']), 703)
        richer = copy.deepcopy(ps[0]); richer['signals'][0]['snippet'] += ' extra evidence'
        self.assertEqual(person_ref(ps[0]), person_ref(richer))
        queue = gr.read(root / 'queue.json'); queue['tasks'].pop(first)
        gr.write(root / 'queue.json', queue)
        self.assertIn('target_manifest_mismatch', gr.check(root)['issues'])

    def test_same_name_different_ids_have_separate_tasks(self):
        other = copy.deepcopy(self.p); other['ids'] = {'openalex': 'AOther'}
        gr.plan(self.root, [self.p, other], DATE)
        self.assertEqual(gr.check(self.root)['target_count'], 2)
        answer = self.result(); answer['relations'][0]['person_ref'] = person_ref(other)
        with self.assertRaises(ValueError): gr.record(self.root, answer)

    def test_current_relation_reaches_csv_and_html_without_pi_or_new_person(self):
        for domain in ['Embodied AI', 'Multimodal AI']:
            with self.subTest(domain=domain):
                gr.record(self.root, self.result())
                a = args(group_recovery=str(self.root), domain=domain, out=str(self.root.parent / 'roster'), coverage_dir=None)
                selected = te.select_persons([self.p], a)[0]
                self.assertEqual(selected[0]['group'], 'Robot Lab @ Example University')
                self.assertEqual(selected[0]['ids'], self.p['ids'])
                self.assertEqual(selected[0]['signals'], self.p['signals'])
                data = tm.build_data([self.p], a, FakeGeocoder({}))
                self.assertEqual(len(data['persons']), 1)
                self.assertEqual(data['groups'][0]['pi_name'], '')
                self.assertEqual(data['groups'][0]['display_name'], 'Robot Lab')
                self.assertEqual(data['groups'][0]['pi_status'], 'not_recorded')
                self.assertIsNone(data['groups'][0]['pi_key'])
                self.assertEqual(data['persons'][0]['group_memberships'][0]['relation_type'], 'member')
                self.assertIn('Robot Lab', tm.render_html(data))
                rows = te.group_rows(selected, datetime.date(2023,10,14), a.date)
                self.assertIn(URL, rows[0]['evidence_urls'])

    def test_reference_pi_does_not_add_or_approve_provider_identity(self):
        answer = self.result()
        answer['relations'][0]['group']['leader'] = {'name': 'Held PI', 'url': 'https://university.example/pi'}
        gr.record(self.root, answer)
        data = tm.build_data([self.p], args(group_recovery=str(self.root)), FakeGeocoder({}))
        self.assertEqual(len(data['persons']), 1)
        self.assertEqual(data['groups'][0]['leader_reference']['name'], 'Held PI')
        self.assertEqual(data['groups'][0]['leader_reference']['status'], 'reviewed_team_reference')
        self.assertIsNone(data['groups'][0]['pi_key'])

    def test_evidence_missing_quote_changed_hash_date_and_path_are_rejected(self):
        answer = self.result()
        changes = [('quote', 'invented sentence'), ('sha256', '0'*64),
                   ('observed_on', '2026-10-13'), ('path', '../outside.json')]
        for key, value in changes:
            bad = copy.deepcopy(answer); bad['relations'][0]['evidence'][0][key] = value
            with self.subTest(key=key), self.assertRaises((ValueError, OSError)):
                gr.record(self.root, bad)
        gr.record(self.root, answer)
        self.source('changed content')
        self.assertEqual(gr.check(self.root)['status'], 'invalid')
        with self.assertRaises(ValueError):
            te.select_persons([self.p], args(group_recovery=str(self.root)))

    def test_name_only_and_coauthor_results_are_not_team_proof(self):
        for change in [{'identity_evidence': []}, {'identity_reason': ''}, {'relation_type': 'coauthor'}]:
            bad = self.result(); bad['relations'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): gr.record(self.root, bad)

    def test_historical_membership_does_not_reappear_through_heuristics(self):
        answer = self.result(outcome='historical_only')
        answer['relations'][0].update(status='historical', valid_to='2024-01-01')
        gr.record(self.root, answer)
        lead = candidate('PI'); lead['role_class'] = 'professor'
        p = copy.deepcopy(self.p); p['signals'][0]['parent'] = 'PI'
        data = te.select_persons([lead, p], args(group_recovery=str(self.root)))[0]
        member = next(x for x in data if x['name'] == 'Ada')
        self.assertEqual(member['group'], '')
        self.assertIn('historical', member['group_evidence'])
        report = gr.check(self.root)
        self.assertEqual(report['coverage_status'], 'complete')
        self.assertEqual(report['status'], 'incomplete')

    def test_multiple_memberships_need_explicit_primary(self):
        answer = self.result(); second = copy.deepcopy(answer['relations'][0])
        second['group']['id'] = 'other'; second['group']['name'] = 'Other Lab'
        answer['relations'].append(second); gr.record(self.root, answer)
        selected = te.select_persons([self.p], args(group_recovery=str(self.root)))[0]
        self.assertEqual(selected[0]['group'], '')
        answer['relations'][0].update(primary=True, primary_reason='Reviewed profile explicitly identifies primary lab')
        gr.record(self.root, answer)
        selected = te.select_persons([self.p], args(group_recovery=str(self.root)))[0]
        self.assertEqual(selected[0]['group'], 'Robot Lab @ Example University')
        self.assertEqual(len(selected[0]['group_memberships']), 2)

    def test_explicit_lab_resolves_multiple_leaders_without_guessing_supervisor(self):
        people = [candidate('Head'), candidate('Subleader'), self.p]
        for p in people[:2]: p['role_class'] = 'professor'
        relations = self.result()['relations']
        output = assign_groups(people, relations, DATE)
        self.assertEqual(output[-1]['group'], 'Robot Lab @ Example University')
        self.assertEqual(output[-1]['group_memberships'][0]['relation_type'], 'member')

    def test_blocked_is_reviewed_but_not_resolved_and_no_source_is_not_a_result(self):
        result = self.result(outcome='blocked'); gr.record(self.root, result)
        check = gr.check(self.root)
        self.assertEqual(check['reviewed_count'], 1)
        self.assertEqual(check['verified_current_count'], 0)
        self.assertEqual(check['status'], 'incomplete')
        result['sources_checked'] = []
        with self.assertRaises(ValueError): gr.record(self.root, result)

    def test_current_affiliation_change_invalidates_previous_binding(self):
        gr.record(self.root, self.result())
        changed = copy.deepcopy(self.p); changed['current_affiliation'] = 'Another University'
        self.assertEqual(gr.load_relations(self.root, [changed], DATE), [])
        gr.plan(self.root, [changed], DATE)
        self.assertEqual(gr.check(self.root)['counts'], {'pending': 1})

    def test_target_disappearance_is_not_silently_complete_and_reappearance_reopens(self):
        gr.record(self.root, self.result())
        gr.plan(self.root, [], DATE)
        self.assertEqual(gr.check(self.root)['counts'], {'binding_missing': 1})
        gr.plan(self.root, [self.p], DATE)
        self.assertEqual(gr.check(self.root)['counts'], {'pending': 1})

    def test_removed_target_cannot_be_reactivated_by_receipt_or_retry(self):
        answer = self.result()
        gr.record(self.root, answer)
        gr.plan(self.root, [], DATE)
        with self.assertRaisesRegex(ValueError, 'current population'):
            gr.record(self.root, answer)
        with patch('visit_page.visit') as visit, patch('group_recovery.subprocess.run') as worker:
            report = gr.run(self.root, ['worker'], retry_unresolved=True)
            visit.assert_not_called()
            worker.assert_not_called()
        self.assertEqual(report['counts'], {'binding_missing': 1})
        self.assertEqual(report['reviewed_count'], 0)

    def test_recent_membership_does_not_qualify_old_research_activity(self):
        gr.record(self.root, self.result())
        old = copy.deepcopy(self.p)
        for signal in old['signals']:
            signal['date'] = '2020-01-01'
        self.assertEqual(te.select_persons([old], args(group_recovery=str(self.root)))[0], [])

    def test_uncapped_export_queues_everyone_and_reuses_receipts(self):
        root = self.root.parent / 'uncapped'
        ps = [candidate(str(i)) for i in range(4)]
        a = args(max_rows=1, group_recovery=str(root), out=str(root.parent/'limited'), coverage_dir=None)
        te.export(ps, a)
        self.assertEqual(gr.check(root)['target_count'], 4)

    def test_worker_failure_resume_and_shared_page_fetch(self):
        other = candidate('Bob'); gr.plan(self.root, [self.p, other], DATE)
        page = {'status': 'readable', 'requested_url': 'https://lab.example/team',
                'final_url': 'https://lab.example/team', 'retrieved_at': DATE+'T00:00:00+00:00', 'text': 'No team evidence.'}
        def worker(argv, **kwargs):
            job = json.loads(kwargs['input'])
            response = {'task_id': job['id'], 'input_hash': job['input_hash'], 'outcome': 'ambiguous',
                        'reason': 'No direct relationship found; still unresolved', 'sources_checked': job['pages'], 'relations': []}
            return subprocess.CompletedProcess(argv, 0, json.dumps(response), '')
        with patch('visit_page.visit', return_value=page) as visit, patch('group_recovery.subprocess.run', side_effect=worker) as execute:
            result = gr.run(self.root, ['test-worker'], page_budget=1)
            self.assertEqual(visit.call_count, 1)
            self.assertEqual(execute.call_count, 2)
            self.assertEqual(result['reviewed_count'], 2)
            gr.run(self.root, ['test-worker'], page_budget=1)
            self.assertEqual(execute.call_count, 2)
        with patch('group_recovery.subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 1)):
            result = gr.run(self.root, ['test-worker'], page_budget=1, retry_unresolved=True)
            self.assertEqual(result['counts'], {'failed': 2})
        with patch('group_recovery.subprocess.run', side_effect=worker):
            self.assertEqual(gr.run(self.root, ['test-worker'], page_budget=1)['reviewed_count'], 2)

    def test_missing_worker_cannot_pretend_to_execute(self):
        with self.assertRaises(ValueError): gr.run(self.root, [])

    def test_concurrent_runner_is_rejected(self):
        with gr.lock(self.root, '.runner.lock'):
            with self.assertRaisesRegex(ValueError, 'coordinator'):
                gr.run(self.root, ['worker'])

    def test_failed_page_can_be_refetched_without_overwriting_old_receipt(self):
        page = {'status': 'blocked', 'requested_url': 'https://lab.example/team',
                'final_url': 'https://lab.example/team', 'retrieved_at': DATE+'T00:00:00+00:00', 'text': ''}
        def worker(argv, **kwargs):
            job = json.loads(kwargs['input'])
            return subprocess.CompletedProcess(argv, 0, json.dumps({'task_id':job['id'],
                'input_hash':job['input_hash'], 'outcome':'blocked', 'reason':'Source refused',
                'sources_checked':job['pages'], 'relations':[]}), '')
        with patch('visit_page.visit', return_value=page), patch('group_recovery.subprocess.run', side_effect=worker):
            gr.run(self.root, ['worker'], page_budget=2)
            old_files = {p: p.read_bytes() for p in (self.root/'pages').glob('*.json')}
            gr.run(self.root, ['worker'], page_budget=2, retry_unresolved=True)
        self.assertEqual(len(list((self.root/'pages').glob('*.json'))), 2)
        self.assertTrue(all(p.read_bytes() == data for p,data in old_files.items()))

    def test_bad_worker_payload_is_a_failed_task_not_a_crash(self):
        with patch('visit_page.visit', return_value={'status':'blocked','retrieved_at':DATE+'T00:00:00','text':''}), \
             patch('group_recovery.subprocess.run', return_value=subprocess.CompletedProcess(['worker'],0,'[]','')):
            self.assertEqual(gr.run(self.root, ['worker'])['counts'], {'failed':1})

    def test_zero_budget_leaves_every_target_pending_and_makes_no_calls(self):
        with patch('visit_page.visit') as visit, patch('group_recovery.subprocess.run') as worker:
            report = gr.run(self.root, ['test-worker'], page_budget=0)
            self.assertEqual(report['counts'], {'budget_exhausted': 1})
            self.assertEqual(report['reviewed_count'], 0)
            visit.assert_not_called(); worker.assert_not_called()

    def test_only_access_failures_cannot_be_not_found(self):
        answer = self.result(outcome='not_found')
        answer['sources_checked'] = [self.source(status='blocked')]
        with self.assertRaisesRegex(ValueError, 'access failures'):
            gr.record(self.root, answer)

    def test_copied_reviewed_fields_without_receipt_do_not_grant_membership(self):
        p = copy.deepcopy(self.p)
        p.update(group='Injected Lab @ Example University', group_rule='reviewed',
                 group_memberships=self.result()['relations'])
        selected = te.select_persons([p], args())[0]
        self.assertEqual(selected[0]['group'], '')
        self.assertNotIn('group_memberships', selected[0])

    def test_real_worker_process_to_csv_and_html_with_shared_evidence(self):
        # Network is deterministic; worker execution, receipts, export and HTML
        # are real. This tests the adapter boundary, not LLM factual accuracy.
        ps = [candidate('Ada'), candidate('Bob')]
        root = self.root.parent / 'e2e'
        a = args(group_recovery=str(root), out=str(root.parent/'roster'), coverage_dir=None)
        te.export(ps, a)
        worker = self.root.parent / 'worker.py'
        worker.write_text('''import json, pathlib, sys
j=json.load(sys.stdin)
p=j['pages'][0]
body=json.loads((pathlib.Path(j['recovery_dir'])/p['path']).read_text())
ev={**p, 'quote':body['text'], 'observed_on':body['retrieved_at'][:10]}
r={'person_ref':j['id'], 'relation_type':'member', 'status':'current',
   'observed_on':j['run_date'], 'identity_reason':'Fixture source explicitly identifies this member.',
   'identity_evidence':[ev], 'evidence':[ev],
   'group':{'id':'robot-lab','name':'Robot Lab','institution':'Example University','url':p['url']}}
json.dump({'task_id':j['id'],'input_hash':j['input_hash'],'outcome':'verified_current',
 'reason':'Fixture roster membership verified','sources_checked':[p],'relations':[r]},sys.stdout)
''')
        page = {'status': 'readable', 'requested_url': 'https://lab.example/team',
                'final_url': 'https://lab.example/team', 'retrieved_at': DATE+'T00:00:00+00:00',
                'text': 'Ada and Bob work at Robot Lab, Example University.'}
        with patch('visit_page.visit', return_value=page) as visit:
            report = gr.run(root, [sys.executable, str(worker)], page_budget=1)
        self.assertEqual(visit.call_count, 1)
        self.assertEqual(report['verified_current_count'], 2)
        te.export(ps, a)
        import csv
        with Path(a.out+'.csv').open(encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
        data = tm.build_data(ps, a, FakeGeocoder({}))
        self.assertEqual([r['group'] for r in rows], [p['group'] for p in data['persons']])
        self.assertEqual({r['group'] for r in rows}, {'Robot Lab @ Example University'})
        self.assertEqual(gr.check(root)['target_count'], 2)
        self.assertEqual(gr.check(root)['status'], 'complete')
        self.assertEqual(len(gr.read(root/'queue.json')['tasks'][person_ref(ps[0])]['attempts']), 1)
        with patch('group_recovery.subprocess.run') as repeat:
            gr.run(root, [sys.executable, str(worker)], page_budget=1)
            repeat.assert_not_called()


if __name__ == '__main__':
    unittest.main()
