import argparse
import copy
import csv
import datetime as dt
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_topics as topics
import table_export
import talent_map

POLICY = {'version': 1, 'include_preprints': True, 'topics': [
    {'id': 'vlm', 'label': 'VLM', 'facet_ids': ['vlm']},
    {'id': 'vla', 'label': 'VLA', 'facet_ids': ['vla']},
    {'id': 'agentic', 'label': 'Agentic', 'facet_ids': ['agentic']}]}
START, END = dt.date(2023, 10, 16), dt.date(2026, 10, 16)


def paper(topic='vla', date='2025-06-01', name='Ada Example'):
    title = f'A contribution to {topic.upper()} for robot reasoning and control'
    return {'kind': 'person', 'name_raw': name, 'signal_type': 'paper_author', 'channel': 'awards-papers',
            'role': 'coauthor', 'date': date, 'evidence_url': f'https://papers.example/{topic}',
            'strength': 'medium', 'hop_depth': 1, 'topics': [title], 'snippet': title,
            'topic_evidence': [{'topic_id': topic, 'quote': title, 'relation': 'contribution'}],
            'publication': {'title': title, 'date': date, 'status': 'published',
                            'url': f'https://papers.example/{topic}', 'author_name': name,
                            'authorship_verified': True, 'authorship_evidence_url': 'https://papers.example/authors'}}


def person(signals=None, name='Ada Example', role='professor', **extra):
    return {'name': name, 'role_class': role, 'role_confidence': 'high', 'country': 'DE',
            'current_affiliation': 'Example University', 'merge_confidence': 'high', 'ids': {},
            'group': 'Ada Example @ Example University', 'signals': signals if signals is not None else [paper(name=name)],
            **extra}


def args(**extra):
    return argparse.Namespace(**{'date': END, 'window_months': 36, 'region': 'EU27+UK+CH+NO',
                                 'region_core': 'DE+CH', 'max_rows': 0, 'domain': 'robotics',
                                 'topic_policy': copy.deepcopy(POLICY), **extra})


def selected(record, policy=POLICY):
    return table_export.select_persons([record], args(topic_policy=policy))


class TopicPolicyTests(unittest.TestCase):
    def test_templates_validate_and_labels_remain_short(self):
        for path in (ROOT / 'assets').glob('**/*topic*.json'):
            if 'schema' not in path.name:
                topics.load_policy(path)
        p = topics.load_policy(ROOT / 'assets/topics/embodied-ai.json')
        self.assertEqual([t['label'] for t in p['topics']], ['VLA', 'VLM', 'Policy', 'World Model', 'WAM'])

    def test_invalid_config_fails_closed(self):
        for change in ({'version': 2}, {'include_preprints': 'false'}, {'topics': []},
                       {'topics': [{'id': 'vla', 'label': 'A very long research topic covering all robotics'}]},
                       {'topics': [POLICY['topics'][0], POLICY['topics'][0]]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                topics.validate_policy({**POLICY, **change})

    def test_missing_explicit_policy_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit):
            topics.policy_for(args(topic_policy=str(Path(tmp) / 'missing.json')))

    def test_discovery_is_beside_input_not_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'topic-policy.json'
            ns = args(topic_policy=None, persons=str(Path(tmp) / 'persons.enriched.jsonl'))
            self.assertIsNone(topics.policy_for(ns))
            path.write_text(json.dumps(POLICY))
            self.assertEqual(topics.policy_for(ns), POLICY)
            path.write_text('broken')
            with self.assertRaises(SystemExit):
                topics.policy_for(ns)

    def test_arbitrary_domain_supported(self):
        policy = {'version': 1, 'include_preprints': False, 'topics': [{'id': 'quantum', 'label': 'Quantum'}]}
        kept, *_ = selected(person([paper('quantum')]), policy)
        self.assertEqual(kept[0]['display_topics'], ['Quantum'])

    def test_source_contract_and_skill_require_the_runtime_policy(self):
        schema = json.loads((ROOT / 'assets/signal.schema.json').read_text())
        self.assertIn('authorship_evidence_url', schema['properties']['publication']['required'])
        self.assertIn('relation', schema['properties']['topic_evidence']['items']['required'])
        self.assertIn('--topic-policy RUN_DIR/topic-policy.json', (ROOT / 'SKILL.md').read_text())
        self.assertIn('topic_policy_file: assets/topics/embodied-ai.json', (ROOT / 'domain-cache/embodied-ai.yaml').read_text())


class ProfessorPaperTests(unittest.TestCase):
    def test_recent_vla_does_not_validate_old_vlm_and_source_unchanged(self):
        p = person([paper('vla'), paper('vlm', '2020-03-01')])
        before = copy.deepcopy(p)
        kept, _, audit, _, _ = selected(p)
        self.assertEqual(p, before)
        self.assertEqual(kept[0]['display_topics'], ['VLA'])
        self.assertEqual(table_export.row_for(kept[0], 'robotics', str(END))['topics'], 'VLA')
        self.assertEqual(kept[0]['topic_papers'][0]['topic_ids'], ['vla'])
        self.assertEqual(len(kept[0]['signals']), 2)
        self.assertIn('publication_outside_window', [a['reason'] for a in audit])

    def test_recent_grant_or_verified_roster_is_not_a_paper(self):
        for kind in ('dfg_project', 'lab_member'):
            s = paper()
            s.pop('publication')
            s.update(signal_type=kind, date='' if kind == 'lab_member' else '2025-01-01')
            kept, _, audit, _, _ = selected(person([s], last_verified=str(END)))
            self.assertEqual(kept, [])
            self.assertIn('professor_pending_recent_topic_paper', [a['reason'] for a in audit])

    def test_dates_are_publication_dates_not_award_or_fetch_dates(self):
        s = paper(date='2020-01-01')
        s.update(date='2025-01-01', signal_type='workshop_award')
        self.assertEqual(selected(person([s]))[0], [])
        s = paper()
        s['date'] = '2020-01-01'
        self.assertEqual(selected(person([s]))[0][0]['qualifying'][0]['date'], '2025-06-01')

    def test_precise_dates_and_conservative_partial_dates(self):
        for date, passes in [('2023-10-16', True), ('2026-10-16', True), ('2023-10-15', False),
                             ('2026-10-17', False), ('2024', True), ('2023', False),
                             ('2026', False), ('2023-10', False), ('2023-11', True),
                             ('2026-09', True), ('2026-10', False), ('2025-13', False),
                             ('2025-02-30', False), ('', False)]:
            with self.subTest(date=date):
                self.assertEqual(bool(selected(person([paper(date=date)]))[0]), passes)

    def test_preprint_policy_and_label(self):
        s = paper()
        s['publication']['status'] = 'preprint'
        self.assertEqual(selected(person([s]))[0][0]['topic_papers'][0]['status'], 'preprint')
        self.assertEqual(selected(person([s]), {**POLICY, 'include_preprints': False})[0], [])

    def test_authorship_required_but_any_author_position_qualifies(self):
        for role in ('first_author', 'last_author', 'coauthor'):
            s = paper()
            s['role'] = role
            self.assertTrue(selected(person([s]))[0])
        for change in ({'authorship_verified': False}, {'author_name': 'Someone Else'},
                       {'authorship_evidence_url': ''}, {'status': 'unknown'}, {'url': 'javascript:foo'}):
            s = paper()
            s['publication'].update(change)
            with self.subTest(change=change):
                self.assertEqual(selected(person([s]))[0], [])

    def test_author_id_match_and_conflicting_id_rejects_namesake(self):
        s = paper()
        s['publication'].update(author_name='A. Example', author_ids={'openalex': 'https://openalex.org/A123'})
        self.assertTrue(selected(person([s], ids={'openalex': 'A123'}))[0])
        s['publication']['author_name'] = 'Ada Example'
        self.assertFalse(selected(person([s], ids={'openalex': 'A999'}))[0])
        self.assertFalse(selected(person([s], merge_confidence='ambiguous'))[0])

    def test_empty_or_wrong_host_author_ids_cannot_establish_authorship(self):
        for identifier in ('', 'https://unrelated.example/A123'):
            s = paper()
            s['publication'].update(author_name='Someone Else', author_ids={'openalex': identifier})
            self.assertFalse(selected(person([s], ids={'openalex': 'A123'}))[0])

    def test_unreviewed_or_unknown_or_background_topics_do_not_qualify(self):
        for evidence in ([], [{'topic_id': 'vla', 'quote': 'not in the paper', 'relation': 'contribution'}],
                         [{'topic_id': 'vla', 'quote': paper()['snippet'], 'relation': 'background'}],
                         [{'topic_id': 'unknown', 'quote': paper()['snippet'], 'relation': 'contribution'}]):
            s = paper()
            s['topic_evidence'] = evidence
            with self.subTest(evidence=evidence):
                self.assertFalse(selected(person([s]))[0])

    def test_old_topic_in_person_or_grant_does_not_supply_paper_evidence(self):
        s = paper()
        s['topic_evidence'][0]['quote'] = 'A vision-language modelling grant'
        s['topics'] = [s['topic_evidence'][0]['quote']]
        s['snippet'] = s['topics'][0]
        self.assertFalse(selected(person([s], topics=['VLA', 'VLM']))[0])

    def test_nonprofessors_keep_existing_eligibility_without_borrowing_topics(self):
        s = paper()
        s.pop('publication')
        s.pop('topic_evidence')
        p = person([s], role='phd_student')
        kept, _, audit, _, _ = selected(p)
        self.assertEqual(kept[0]['display_topics'], [])
        self.assertIn('unmapped_topics', [a['reason'] for a in audit])
        self.assertFalse(selected(person([paper(date='2020-01-01')], role='industry'))[0])

    def test_recent_grant_still_contributes_to_ranking_after_paper_gate(self):
        grant = {**paper('vlm'), 'channel': 'funding-eu', 'signal_type': 'erc_stg'}
        grant.pop('publication')
        kept = selected(person([paper(), grant]))[0][0]
        self.assertEqual(kept['channels_hit'], ['awards-papers', 'funding-eu'])
        self.assertEqual(kept['display_topics'], ['VLA'])


class TopicExportTests(unittest.TestCase):
    class Geo:
        def locate(self, *args):
            return None

    def test_map_group_topics_and_facets_exclude_old_topics_and_coauthors(self):
        records = [person([paper(), paper('vlm', '2020-01-01')]),
                   person([paper('agentic', name='Coauthor')], name='Coauthor', role='researcher', group_link='coauthor')]
        facets = [{'id': 'approach', 'tags': [{'id': t, 'keywords': [t]} for t in ['vla', 'vlm', 'agentic']]}]
        data = talent_map.build_data(records, args(), self.Geo(), facets=facets)
        self.assertEqual(data['persons'][0]['topics'], ['VLA'])
        self.assertEqual(data['persons'][0]['tags'], ['vla'])
        self.assertEqual(data['groups'][0]['topics'], ['VLA'])
        self.assertEqual(data['groups'][0]['tags'], [['vla', 1]])
        self.assertEqual(data['meta']['topic_policy'], 'checked')
        self.assertIn('topic_papers.map', talent_map.render_html(data))
        self.assertIn('支持研究方向的近期论文', talent_map.render_html(data))

    def test_both_clis_autoload_policy_and_retain_same_people_with_audit(self):
        records = [person(), person([paper(date='2020-01-01', name='Old Professor')], name='Old Professor')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'persons.jsonl'
            src.write_text('\n'.join(map(json.dumps, records)))
            (root / 'topic-policy.json').write_text(json.dumps(POLICY))
            for script, output in [('table_export.py', 'roster'), ('talent_map.py', 'map.html')]:
                cmd = [sys.executable, str(ROOT / 'scripts' / script), str(src), '--date', str(END), '--out', str(root / output)]
                if script == 'talent_map.py':
                    cmd += ['--offline']
                result = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            with (root / 'roster.csv').open(encoding='utf-8-sig') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([(r['name'], r['topics']) for r in rows], [('Ada Example', 'VLA')])
            html = (root / 'map.html').read_text()
            payload = html.split('<script id="talent-data" type="application/json">', 1)[1].split('</script>', 1)[0]
            data = json.loads(payload)
            self.assertEqual([p['name'] for p in data['persons']], ['Ada Example'])
            self.assertEqual(data['meta']['professors_pending_evidence'], 1)
            audit = json.loads((root / 'roster.topic-audit.json').read_text())
            self.assertIn('professor_pending_recent_topic_paper', [r['reason'] for r in audit])
            self.assertIn('Topic qualification [vla]', (root / 'roster.md').read_text())
            self.assertIn('A contribution to VLA', src.read_text())

    def test_no_policy_preserves_historical_export_and_labels_status(self):
        p = person([paper('vlm')])
        p['signals'][0].pop('publication')
        data = talent_map.build_data([p], args(topic_policy=None), self.Geo())
        self.assertEqual(data['persons'][0]['topics'], p['signals'][0]['topics'])
        self.assertEqual(data['meta']['topic_policy'], 'not_checked')

    @unittest.skipUnless(shutil.which('node'), 'Node required for HTML JavaScript syntax check')
    def test_inline_javascript_with_paper_evidence_card_parses(self):
        data = talent_map.build_data([person()], args(), self.Geo())
        script = talent_map.render_html(data).split('<script>', 1)[1].split('</script>', 1)[0]
        result = subprocess.run(['node', '--check'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
