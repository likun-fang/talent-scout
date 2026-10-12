import datetime
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import table_export
from table_export import filter_window, ranked_channels, sort_key, window_start


def sig(channel, date, strength='high', hop=0, url=None):
    return {'kind': 'person', 'name_raw': 'X', 'channel': channel, 'signal_type': f'{channel}_sig', 'strength': strength,
            'date': date, 'evidence_url': url or f'https://{channel}.example/{date}', 'country': 'DE',
            'affiliation_raw': 'TUM', 'hop_depth': hop}


class WindowTests(unittest.TestCase):
    def test_window_start_is_36_months_back_same_day(self):
        cases = {'2026-10-12': '2023-10-12', '2027-01-05': '2024-01-05', '2028-02-29': '2025-02-28', '2026-03-31': '2023-03-31'}
        for end, start in cases.items():
            with self.subTest(end=end):
                self.assertEqual(window_start(datetime.date.fromisoformat(end), 36), datetime.date.fromisoformat(start))
        self.assertEqual(window_start(datetime.date(2026, 10, 12), 12), datetime.date(2025, 10, 12))

    def test_old_and_undated_signals_stay_as_evidence_but_do_not_rank(self):
        person = {'name': 'Anna', 'ids': {}, 'signals': [sig('awards-papers', '2025-06'), sig('funding-eu', '2022'),
                                                          {**sig('open-source', ''), 'date': None}]}
        kept, rejected = filter_window([person], datetime.date(2023, 10, 12), datetime.date(2026, 10, 12))
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(kept[0]['signals']), 3)          # evidence retained
        self.assertEqual(len(kept[0]['qualifying']), 1)       # ranking input
        self.assertEqual(kept[0]['channels_hit'], ['awards-papers'])
        self.assertEqual(ranked_channels(kept[0]), 1)
        self.assertEqual(sorted(r['reason'] for r in rejected), ['missing_or_invalid_date', 'outside_window'])

    def test_person_without_qualifying_signal_is_dropped(self):
        person = {'name': 'Cara', 'ids': {}, 'signals': [sig('national-prizes', '2023-10-11')]}
        kept, rejected = filter_window([person], datetime.date(2023, 10, 12), datetime.date(2026, 10, 12))
        self.assertEqual(kept, [])
        self.assertEqual(rejected[0]['name'], 'Cara')

    def test_boundary_days_are_inclusive(self):
        person = {'name': 'B', 'ids': {}, 'signals': [sig('a', '2023-10-12'), sig('b', '2026-10-12'), sig('c', '2026-10-13')]}
        kept, rejected = filter_window([person], datetime.date(2023, 10, 12), datetime.date(2026, 10, 12))
        self.assertEqual(kept[0]['channels_hit'], ['a', 'b'])
        self.assertEqual(rejected[0]['signal']['channel'], 'c')

    def test_sort_uses_qualifying_signals_only(self):
        recent_weak = {'name': 'R', 'signals': [sig('a', '2025-01', 'low')], 'qualifying': [sig('a', '2025-01', 'low')]}
        old_strong = {'name': 'O', 'signals': [sig('a', '2025-02', 'low'), sig('b', '2020', 'high')],
                      'qualifying': [sig('a', '2025-02', 'low')]}
        self.assertEqual(sort_key(old_strong)[:2], sort_key(recent_weak)[:2])

    def test_cli_writes_outputs_and_coverage(self):
        persons = [
            {'name': 'Anna', 'ids': {'orcid': '0000-0001'}, 'merge_confidence': 'high',
             'signals': [sig('awards-papers', '2025-06'), sig('funding-eu', '2022')]},
            {'name': 'Ben', 'ids': {}, 'merge_confidence': 'low', 'signals': [{**sig('open-source', ''), 'date': None}]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'persons.jsonl'
            src.write_text('\n'.join(json.dumps(p) for p in persons), encoding='utf-8')
            out = str(Path(tmp) / 'roster')
            argv = ['table_export.py', str(src), '--date', '2026-10-12', '--out', out]
            with patch.object(sys, 'argv', argv):
                table_export.main()
            csv_bytes = Path(out + '.csv').read_bytes()
            md = Path(out + '.md').read_text(encoding='utf-8')
            excluded = json.loads(Path(out + '.excluded-signals.json').read_text(encoding='utf-8'))
        self.assertTrue(csv_bytes.startswith(b'\xef\xbb\xbf'))
        self.assertIn('| Anna |', md)
        self.assertNotIn('| Ben |', md)
        self.assertIn('https://funding-eu.example/2022', md)   # old evidence still shown
        self.assertIn('signal window: 2023-10-12 to 2026-10-12', md)
        self.assertIn('persons without a qualifying signal, not in table: 1', md)
        self.assertEqual({r['name'] for r in excluded}, {'Anna', 'Ben'})


if __name__ == '__main__':
    unittest.main()
