import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_affiliation as ca


def read(title, affiliation, country='DE', **fields):
    """A person whose page the final pass read; a recent first-author paper would otherwise infer phd_student."""
    person = {'name': 'Alex', 'final_pass_title': title, 'final_pass_affiliation': affiliation, 'final_pass_country': country,
              'final_pass_url': 'https://example.org/page', 'last_verified': '2026-10-15', 'first_pub_year': 2025,
              'signals': [{'name_raw': 'Alex', 'affiliation_raw': affiliation, 'channel': 'awards-papers', 'date': '2025-06',
                           'role': 'first_author', 'evidence_url': 'https://doi.org/10.1000/x'}], **fields}
    return ca.classify_role(person, 2026)


class ReadTitleStopsInferenceTests(unittest.TestCase):
    def test_a_title_outside_the_table_is_unknown_not_inferred(self):
        for title in ("Master’s Student", 'Informatics MSc student', 'Guest Scientist', 'Invited guest, Data Science Laboratory',
                      'Project Member', 'Student, Section of Communication Systems - Master Project autumn'):
            with self.subTest(title=title):
                result = read(title, 'ETH Zürich', 'CH')
                self.assertEqual((result['role_class'], result['role_confidence']), ('unknown', 'low'))
                self.assertIn('rule 0: final pass: title not in the title table', result['role_evidence'])
                self.assertIn(title, result['role_evidence'])

    def test_inference_still_runs_without_a_read_title(self):
        person = {'name': 'Alex', 'first_pub_year': 2025, 'signals': [{'role': 'first_author', 'evidence_url': 'https://doi.org/10.1000/x'}]}
        self.assertEqual(ca.classify_role(person, 2026)['role_class'], 'phd_student')

    def test_signal_titles_and_funding_still_win_over_an_unmatched_read_title(self):
        scholars = read('Scholars', '', None, signals=[{'name_raw': 'Alex', 'role_title': 'Scholars', 'parent': 'IMPRS-IS Scholars',
                                                       'affiliation_raw': 'MPI for Intelligent Systems', 'date': '2025-06',
                                                       'evidence_url': 'https://imprs.is.mpg.de/scholars'}])
        self.assertEqual((scholars['role_class'], scholars['role_evidence'][:6]), ('phd_student', 'rule 1'))
        grant = read('Academic staff', 'Ghent University', 'BE', signals=[{'signal_type': 'erc_stg', 'role': 'pi', 'date': '2025-01',
                                                                           'evidence_url': 'https://erc.example/1'}])
        self.assertEqual((grant['role_class'], grant['role_evidence'][:6]), ('group_leader', 'rule 2'))


if __name__ == '__main__':
    unittest.main()
