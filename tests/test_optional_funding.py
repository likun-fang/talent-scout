import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from current_affiliation import classify_role
from table_export import group_rows


class OptionalFundingTests(unittest.TestCase):
    def test_new_funding_is_retained_without_inventing_a_role_or_recent_activity(self):
        signals = [
            {'signal_type': kind, 'channel': 'funding-fr-es-nl-be', 'role': 'pi',
             'date': date, 'evidence_url': f'https://example.org/{kind}'}
            for kind, date in [('national_project', '2025'), ('national_fellowship', '2020')]
        ]
        person = {'name': 'A', 'signals': signals, 'tier': 4, 'group': '', 'country': 'FR'}
        self.assertEqual(classify_role(person, 2026)['role_class'], 'unknown')
        row = group_rows([person], datetime.date(2023, 10, 12), datetime.date(2026, 10, 12))[0]
        self.assertIn('national_project@2025', row['active_funding'])
        self.assertIn('national_fellowship@2020', row['active_funding'])
        self.assertIn('national_project@2025', row['recent_outputs'])
        self.assertNotIn('national_fellowship', row['recent_outputs'])


if __name__ == '__main__':
    unittest.main()
