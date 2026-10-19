import datetime
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_groups
from check_groups import same_pi, recall, stale_groups, sample


def group(pi, institution, last_verified='2026-10-15', homepage='https://lab.example', **extra):
    return {'id': pi.lower().replace(' ', '-'), 'pi': {'name': pi, 'role_class': 'professor', 'homepage': ''},
            'institution': {'name': institution, 'country': 'DE', 'ids': {}}, 'homepage': homepage,
            'last_verified': last_verified, **extra}


KNOWN = [{'pi': 'Matthias Niessner', 'institution': 'Technical University of Munich', 'country': 'DE'},
         {'pi': 'Zeynep Akata', 'institution': 'Technical University of Munich', 'country': 'DE'},
         {'pi': 'Andrew Zisserman', 'institution': 'University of Oxford', 'country': 'GB'},
         {'pi': 'Cordelia Schmid', 'institution': 'Inria', 'country': 'FR'}]
GROUPS = [group('Matthias Nießner', 'TUM'), group('Zeynep Akata', 'Helmholtz Munich')]
PERSONS = [{'name': 'Andrew Zisserman', 'group': '', 'current_affiliation': 'University of Oxford'}]


class NameMatchTests(unittest.TestCase):
    def test_accents_case_umlauts_and_first_initial(self):
        for left, right in (('Matthias Nießner', 'Matthias Niessner'), ('Hilde Kühne', 'Hilde Kuehne'),
                            ('Raquel Fernández', 'raquel fernandez'), ('A. Zisserman', 'Andrew Zisserman'),
                            ('Bernt Schiele', 'Bernd Schiele')):
            with self.subTest(left=left):
                self.assertTrue(same_pi(left, right))
        for left, right in (('Thomas Brox', 'Thomas Fox'), ('Cees Snoek', 'Kees Snoek'), ('', 'Cees Snoek')):
            with self.subTest(left=left):
                self.assertFalse(same_pi(left, right))


class RecallTests(unittest.TestCase):
    def test_hits_need_name_and_institution_and_misses_say_why(self):
        hits, misses = recall(GROUPS, KNOWN, PERSONS)
        self.assertEqual([k['pi'] for k, _ in hits], ['Matthias Niessner'])  # TUM is an alias of the full name
        reasons = {k['pi']: reason for k, reason in misses}
        self.assertIn('group under another institution: Helmholtz Munich', reasons['Zeynep Akata'])
        self.assertIn('PI present in persons but no group', reasons['Andrew Zisserman'])
        self.assertEqual(reasons['Cordelia Schmid'], 'absent')

    def test_without_persons_a_miss_cannot_tell_roster_from_absent(self):
        _, misses = recall(GROUPS, KNOWN, None)
        self.assertEqual(dict((k['pi'], r) for k, r in misses)['Andrew Zisserman'], 'not a group (no --persons to look further)')


class StalenessTests(unittest.TestCase):
    def test_older_than_twelve_months_or_missing_is_stale(self):
        groups = [group('A One', 'X', '2026-10-15'), group('B Two', 'X', '2025-10-15'), group('C Three', 'X', '2025-10-14'),
                  group('D Four', 'X', '2025'), group('E Five', 'X', '2024'), group('F Six', 'X', '')]
        self.assertEqual([g['pi']['name'] for g in stale_groups(groups, datetime.date(2026, 10, 15))],
                         ['C Three', 'E Five', 'F Six'])


class SampleTests(unittest.TestCase):
    def test_the_sample_is_seeded_and_at_most_thirty(self):
        groups = [group(f'P{i} Name', 'X') for i in range(50)]
        first, second = sample(groups, 30, 7), sample(groups, 30, 7)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 30)
        self.assertEqual(len(sample(groups[:5], 30, 7)), 5)


class CommandLineTests(unittest.TestCase):
    def check(self, groups, known, persons=None):
        with tempfile.TemporaryDirectory() as tmp:
            groups_path, known_path = Path(tmp) / 'groups.json', Path(tmp) / 'known.json'
            groups_path.write_text(json.dumps({'meta': {}, 'groups': groups}), encoding='utf-8')
            known_path.write_text(json.dumps({'note': 'draft', 'groups': known}), encoding='utf-8')
            argv = ['check_groups.py', str(groups_path), '--known', str(known_path), '--as-of', '2026-10-15']
            if persons is not None:
                persons_path = Path(tmp) / 'persons.jsonl'
                persons_path.write_text(''.join(json.dumps(p) + '\n' for p in persons), encoding='utf-8')
                argv += ['--persons', str(persons_path)]
            out, old = io.StringIO(), sys.argv
            sys.argv = argv
            try:
                with redirect_stdout(out):
                    code = check_groups.main()
            finally:
                sys.argv = old
            return code, out.getvalue()

    def test_passing_run_exits_zero_and_prints_the_sample_table(self):
        code, out = self.check(GROUPS, KNOWN[:1])
        self.assertEqual(code, 0)
        self.assertIn('| group | PI | institution | homepage |', out)
        self.assertIn('recall: 1/1', out)

    def test_low_recall_stale_groups_or_a_linkedin_url_fail(self):
        code, out = self.check(GROUPS, KNOWN, PERSONS)
        self.assertEqual(code, 1)
        self.assertIn('FAIL recall', out)
        stale = [group(f'P{i} Name', 'X', '2020') for i in range(2)] + [group(f'Q{i} Name', 'X') for i in range(8)]
        code, out = self.check(stale, [], None)
        self.assertEqual(code, 1)
        self.assertIn('FAIL staleness: 2/10', out)
        code, out = self.check([group('A One', 'X', homepage='https://www.linkedin.com/in/a')], [], None)
        self.assertEqual(code, 1)
        self.assertIn('FAIL linkedin: 1', out)


if __name__ == '__main__':
    unittest.main()
