import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from person_fields import assign_groups, group_affiliation

X = 'Example University'
PAGE = 'https://lab.example/people'


def person(name, affiliation, role_class, signals, **fields):
    return {'name': name, 'current_affiliation': affiliation, 'role_class': role_class,
            'signals': [{'name_raw': name, 'affiliation_raw': affiliation, 'channel': 'funding-eu', 'date': '2025-05',
                         **s} for s in signals], **fields}


def roster(role='team_member', parent='Vision Lab', **fields):
    """A final-pass roster signal: undated, the lab as parent, the head the page was read for as roster_pi."""
    return {'signal_type': 'lab_member', 'role': role, 'parent': parent, 'channel': 'final-pass', 'date': '',
            'evidence_url': PAGE, **fields}


def grouped(people):
    return {p['name']: p for p in assign_groups(people)}


class RosterHeadTests(unittest.TestCase):
    def setUp(self):
        # The page lists its head and a second professor, who keeps a group of their own.
        self.head = person('Anna Head', X, 'professor', [roster('pi', roster_pi='Anna Head')])
        self.colleague = person('Ben Colleague', X, 'professor', [roster(roster_pi='Anna Head')])

    def test_a_member_ambiguous_between_two_professors_on_the_page_joins_the_head_it_was_read_for(self):
        member = person('Cara Student', X, 'phd_student', [roster(roster_pi='Anna Head')])
        result = grouped([self.head, self.colleague, member])['Cara Student']
        self.assertEqual((result['group'], result['group_link']), (f'Anna Head @ {X}', 'team'))
        self.assertEqual(result['group_evidence'], f'rule 1: roster head Anna Head | {PAGE}')
        self.assertEqual(grouped([self.head, self.colleague, member])['Ben Colleague']['group'], f'Ben Colleague @ {X}')

    def test_without_a_roster_head_the_member_stays_ambiguous(self):
        member = person('Cara Student', X, 'phd_student', [roster()])
        self.assertIn('ambiguous: Anna Head, Ben Colleague', grouped([self.head, self.colleague, member])['Cara Student']['group_evidence'])

    def test_a_group_leader_on_the_page_is_not_attached_to_the_head(self):
        lead = person('Dana Lead', X, 'group_leader', [roster(roster_pi='Anna Head')])
        result = grouped([self.head, self.colleague, lead])['Dana Lead']
        self.assertEqual(result['group'], '')
        self.assertIn('ambiguous', result['group_evidence'])

    def test_a_roster_head_who_is_not_among_the_candidates_changes_nothing(self):
        member = person('Cara Student', X, 'phd_student', [roster(roster_pi='Somebody Else')])
        self.assertIn('ambiguous', grouped([self.head, self.colleague, member])['Cara Student']['group_evidence'])


class PiAtTwoInstitutionsTests(unittest.TestCase):
    def setUp(self):
        # The PI's own page names Karolinska; the roster read for the PI is a group at FIMM, University of Helsinki.
        self.pi = person('Lena Lead', 'Karolinska Institutet', 'professor',
                         [roster('pi', parent='Digital Diagnostics', affiliation_raw='FIMM, University of Helsinki',
                                 roster_pi='Lena Lead')],
                         final_pass_affiliation='Karolinska Institutet', final_pass_country='SE', last_verified='2026-10-19')

    def test_the_final_pass_institution_names_the_group_and_the_roster_institution_goes_to_also_at(self):
        self.assertEqual(group_affiliation(self.pi), ('Karolinska Institutet', ['FIMM, University of Helsinki']))

    def test_the_rosters_members_join_the_group_instead_of_reading_as_moved(self):
        member = person('Mia Member', 'FIMM, University of Helsinki', 'phd_student',
                        [roster(parent='Digital Diagnostics', roster_pi='Lena Lead')],
                        final_pass_affiliation='FIMM, University of Helsinki', final_pass_country='FI', last_verified='2026-10-19')
        result = grouped([self.pi, member])['Mia Member']
        self.assertEqual((result['group'], result['group_link']), ('Lena Lead @ Karolinska Institutet', 'team'))

    def test_a_roster_at_the_same_institution_adds_nothing(self):
        pi = person('Lena Lead', 'Karolinska Institutet', 'professor',
                    [roster('pi', parent='Digital Diagnostics', affiliation_raw='Karolinska Institutet, Department of Oncology')],
                    final_pass_affiliation='Karolinska Institutet', last_verified='2026-10-19')
        self.assertEqual(group_affiliation(pi), ('Karolinska Institutet', []))

    def test_without_a_final_pass_the_roster_institution_is_not_a_second_one(self):
        pi = person('Lena Lead', 'Karolinska Institutet', 'professor',
                    [roster('pi', parent='Digital Diagnostics', affiliation_raw='FIMM, University of Helsinki', roster_pi='Lena Lead')])
        self.assertEqual(group_affiliation(pi)[1], [])


if __name__ == '__main__':
    unittest.main()
