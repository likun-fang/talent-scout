import csv
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import table_export as te
from current_affiliation import region_codes

START = datetime.date(2023, 10, 12)
END = datetime.date(2026, 10, 12)


def signal(**changes):
    return {'channel': 'awards-papers', 'signal_type': 'paper', 'date': '2025-01', 'country': 'DE',
            'strength': 'high', 'hop_depth': 0, 'evidence_url': 'https://example.org/paper',
            'affiliation_raw': 'Example Institute', **changes}


def person(name='A', **changes):
    return {'name': name, 'signals': [signal()], 'role_class': 'unknown', 'tier': 4, **changes}


class TierTests(unittest.TestCase):
    def test_all_country_role_tiers(self):
        roles = ['professor', 'researcher', 'phd_student', 'industry', 'unknown']
        for country, expected in [('DE', [1, 2, 2, 4, 4]), ('CH', [1, 2, 2, 4, 4]),
                                  ('FR', [4, 4, 3, 4, 4]), ('GB', [4, 4, 3, 4, 4]),
                                  ('US', [4, 4, 4, 4, 4]), ('', [4, 4, 4, 4, 4])]:
            for role, tier in zip(roles, expected):
                with self.subTest(country=country, role=role):
                    p = person(country=country, role_class=role, signals=[signal(country=country)])
                    self.assertEqual(te.tier_for(p, {'DE', 'CH'}), tier)

    def test_country_specs_accept_literal_codes(self):
        self.assertEqual(region_codes('DE+CH'), {'DE', 'CH'})
        self.assertIn('GB', region_codes('EU27+UK+CH'))
        self.assertEqual(te.tier_for(person(country='US', role_class='phd_student'), {'DE'}, {'US', 'DE'}), 3)

    def test_sort_order_each_tiebreaker(self):
        a = person('A', tier=1, signals=[signal(strength='low', date='2024')])
        b = person('B', tier=2, signals=[signal(), signal(channel='funding-eu')])
        c = person('C', tier=2, signals=[signal(strength='high', date='2024')])
        d = person('D', tier=2, signals=[signal(strength='low', date='2026')])
        e = person('E', tier=2, signals=[signal(strength='low', date='2025')])
        f = person('F', tier=2, signals=[signal(strength='low', date='2025')])
        self.assertEqual([p['name'] for p in sorted([f, e, d, c, b, a], key=te.sort_key)], list('ABCDEF'))

    def test_final_verification_is_preserved_only_when_present(self):
        for verified in ['', '2026-10-01']:
            row = te.row_for(person(last_verified=verified), '', '2026-10-12')
            self.assertEqual(row['last_verified'], verified)
        self.assertEqual(te.row_for(person(), '', '2026-10-12')['last_verified'], '')

    def test_export_columns_topics_and_role_evidence_appendix(self):
        p = person(role_class='researcher', role_confidence='high', group='PI @ Lab',
                   role_evidence='rule 1: lab page | Postdoc | https://example.org/person',
                   signals=[signal(topics=['Exact phrase', 'Second']), signal(topics=['Second', 'Third'])])
        row = te.row_for(p, '', '2026-10-12')
        self.assertEqual(set(row), set(te.COLUMNS))
        self.assertEqual(row['topics'], 'Exact phrase;Second;Third')
        self.assertEqual(row['group'], 'PI @ Lab')
        self.assertNotIn('role_evidence', row)
        self.assertIn(p['role_evidence'], te.evidence_appendix([p]))

    def test_cli_cut_after_tiers_outside_region_and_coverage_disjoint(self):
        people = [person('Cut', role_class='researcher', signals=[signal(), signal(date='2020')]),
                  person('Same name', role_class='professor', role_evidence='rule 1: signal | Professor | https://example.org',
                         group='Same name @ Example Institute', signals=[signal(), signal(date='2020')]),
                  person('Same name', signals=[signal(date='2020')]),
                  person('Outside', country='US', signals=[signal(), signal(date='2020')])]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'persons.jsonl'
            src.write_text('\n'.join(json.dumps(p) for p in people), encoding='utf-8')
            (root / 'channel.coverage.md').write_text('Mock channel: 3 pages read.', encoding='utf-8')
            argv = ['table_export.py', str(src), '--date', '2026-10-12', '--out', str(root / 'roster'),
                    '--max-rows', '1', '--coverage-dir', tmp]
            with patch.object(sys, 'argv', argv), patch('urllib.request.urlopen', side_effect=AssertionError('offline')):
                te.main()
            with (root / 'roster.csv').open(encoding='utf-8-sig', newline='') as source:
                rows = list(csv.DictReader(source))
            md = (root / 'roster.md').read_text()
            groups = (root / 'groups.md').read_text()
            outside = json.loads((root / 'roster.out-of-region.json').read_text())
            self.assertTrue((root / 'groups.csv').read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertEqual([r['name'] for r in rows], ['Same name'])
        self.assertEqual(rows[0]['tier'], '1')
        self.assertEqual([p['name'] for p in outside], ['Outside'])
        self.assertIn('rows cut at --max-rows: 1', md)
        self.assertIn('retained on table persons as evidence but not ranked: 1', md)
        self.assertIn('signals belonging to omitted persons (window, region, missing evidence or row cut): 5', md)
        self.assertIn('Mock channel: 3 pages read.', md)
        self.assertIn('rule 1: signal | Professor', md)
        self.assertIn('groups: 1', groups)
        self.assertNotIn('Cut(', groups)


class GroupTests(unittest.TestCase):
    def test_group_columns_aggregation_dedup_and_window(self):
        funding = signal(signal_type='dfg_project', channel='funding-eu', snippet='F' * 100, date='2026')
        old = signal(signal_type='erc_starting', channel='funding-eu', date='2020', evidence_url='https://example.org/old')
        code = signal(signal_type='repository', channel='open-source', evidence_url='https://example.org/code', strength='medium', date='2025')
        people = [person('Student', tier=2, role_class='phd_student', group='PI @ Lab', signals=[funding, code]),
                  person('PI', tier=1, role_class='professor', group='PI @ Lab',
                         signals=[funding, old, signal(homepage='https://example.org/pi', topics=['Topic'])])]
        row = te.group_rows(people, START, END)[0]
        self.assertEqual(set(row), set(te.GROUP_COLUMNS))
        self.assertEqual(row['members'], 'PI(professor);Student(phd_student)')
        self.assertEqual(row['member_count'], 2)
        self.assertEqual((row['pi_name'], row['institution'], row['country'], row['tier']), ('PI', 'Lab', 'DE', 1))
        self.assertEqual(row['homepage'], 'https://example.org/pi')
        self.assertEqual(row['topics'], 'Topic')
        self.assertEqual(row['recent_outputs'].count('dfg_project@'), 1)
        self.assertIn('F' * 80, row['recent_outputs'])
        self.assertNotIn('F' * 81, row['recent_outputs'])
        self.assertNotIn('2020', row['recent_outputs'])
        self.assertEqual(len(row['recent_outputs'].split(';')), 3)
        self.assertEqual(row['active_funding'], 'dfg_project@2026;erc_starting@2020')
        self.assertEqual(row['open_source'], 'https://example.org/code')
        self.assertIn('https://example.org/old', row['evidence_urls'])

    def test_group_sort_tier_size_pi_and_ungrouped_last(self):
        people = [person('Z', group='Z @ Lab', tier=1), person('A', group='A @ Lab', tier=2),
                  person('B', group='B @ Lab', tier=2), person('B2', group='B @ Lab', tier=2),
                  person('C', group='C @ Lab', tier=2), person('U', group='', tier=1)]
        rows = te.group_rows(people, START, END)
        self.assertEqual([r['group'] for r in rows], ['Z @ Lab', 'B @ Lab', 'A @ Lab', 'C @ Lab', '(ungrouped)'])
        self.assertEqual(rows[-1]['members'], 'U(unknown)')
        self.assertEqual(rows[-1]['pi_name'], '')

    def test_shared_output_keeps_all_members_topics_and_channels(self):
        people = [person('A', group='P @ Lab', signals=[signal(topics=['Alpha'])]),
                  person('B', group='P @ Lab', signals=[signal(topics=['Beta'], channel='open-source')])]
        row = te.group_rows(people, START, END)[0]
        self.assertEqual(row['topics'], 'Alpha;Beta')
        self.assertEqual(row['recent_outputs'].count('paper@'), 1)
        self.assertEqual(row['open_source'], 'https://example.org/paper')

    def test_no_pi_row_does_not_invent_homepage(self):
        rows = te.group_rows([person('Student', group='Absent PI @ Lab', signals=[signal(homepage='https://example.org/student')])], START, END)
        self.assertEqual(rows[0]['pi_name'], 'Absent PI')
        self.assertEqual(rows[0]['homepage'], '')

    def test_empty_roster_still_writes_headers_and_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            te.write_groups([], str(Path(tmp) / 'roster'), START, END)
            md = (Path(tmp) / 'groups.md').read_text()
        self.assertIn('| group | pi_name |', md)
        self.assertIn('groups: 0', md)
        self.assertIn('ungrouped persons: 0', md)

    def test_recent_outputs_top_three_and_members_name_order(self):
        signals = [signal(date=f'202{year}', evidence_url=f'https://example.org/{year}', strength='low') for year in (4, 5, 6)]
        signals += [signal(date='2024', strength='high', snippet='Winner', evidence_url='https://example.org/high')]
        rows = te.group_rows([person('Z', group='P @ Lab', tier=2, signals=signals),
                              person('A', group='P @ Lab', tier=2, signals=[])], START, END)
        outputs = rows[0]['recent_outputs'].split(';')
        self.assertEqual(len(outputs), 3)
        self.assertTrue(outputs[0].endswith('Winner'))
        self.assertTrue(outputs[1].startswith('paper@2026'))
        self.assertEqual(rows[0]['members'], 'A(unknown);Z(unknown)')


if __name__ == '__main__':
    unittest.main()
