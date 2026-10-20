import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_affiliation as ca
from person_fields import affiliation_for, assign_groups, group_affiliation

MPI = 'Max-Planck-Institut für Informatik'
DFKI = 'German Research Center for Artificial Intelligence (DFKI)'
PAGE = 'https://lab.example/people'


def roster(role_title, role='team_member', **fields):
    return {'signal_type': 'lab_member', 'role': role, 'parent': 'Visual Computing', 'channel': 'final-pass', 'date': '',
            'role_title': role_title, 'affiliation_raw': MPI, 'evidence_url': PAGE, **fields}


def person(name, role_class, signals, **fields):
    return {'name': name, 'current_affiliation': MPI, 'role_class': role_class,
            'signals': [{'name_raw': name, **s} for s in signals], **fields}


class GroupLeaderHeadingTests(unittest.TestCase):
    def test_a_group_leader_heading_beats_a_researcher_title_read_on_the_persons_own_page(self):
        for heading in ('Research Group Leaders', 'Group Leader', 'Independent Group Leader'):
            one = {'name': 'Marc', 'final_pass_title': 'Tenured Senior Researcher / Scientific Manager of the Lab',
                   'final_pass_affiliation': MPI, 'final_pass_url': 'https://own.example', 'last_verified': '2026-10-15',
                   'signals': [{'name_raw': 'Marc', **roster(heading)}]}
            with self.subTest(heading=heading):
                result = ca.classify_role(one, 2026)
                self.assertEqual(result['role_class'], 'group_leader')
                self.assertIn(f'roster heading | {heading} | {PAGE}', result['role_evidence'])

    def test_a_past_deputy_or_mixed_heading_is_not_a_group_leader_heading(self):
        for heading in ('Former Group Leader', 'Deputy Group Leader', 'Group Leaders and PhD Students'):
            one = {'name': 'Marc', 'final_pass_title': 'Senior Researcher', 'final_pass_affiliation': MPI,
                   'final_pass_url': 'https://own.example', 'last_verified': '2026-10-15',
                   'signals': [{'name_raw': 'Marc', **roster(heading)}]}
            with self.subTest(heading=heading):
                self.assertEqual(ca.classify_role(one, 2026)['role_class'], 'researcher')
        lead = person('Rita Lead', 'group_leader', [roster('Group Leaders and PhD Students', roster_pi='Chris Director')])
        head = person('Chris Director', 'professor', [roster('Director', role='pi', roster_pi='Chris Director')])
        self.assertNotIn('leader self', {p['name']: p for p in assign_groups([head, lead])}['Rita Lead']['group_evidence'])

    def test_one_item_of_a_joined_title_can_name_the_group_leader(self):
        one = {'name': 'Seb', 'final_pass_title': 'Scientist', 'final_pass_affiliation': MPI,
               'final_pass_url': 'https://own.example', 'last_verified': '2026-10-15',
               'signals': [{'name_raw': 'Seb', **roster('Scientist, Deputy Head of Department, Group Leader of Surgical Analytics')}]}
        self.assertEqual(ca.classify_role(one, 2026)['role_class'], 'group_leader')

    def test_a_doctoral_title_read_on_the_persons_own_page_still_decides(self):
        one = {'name': 'Mia', 'final_pass_title': 'PhD student', 'final_pass_affiliation': MPI,
               'final_pass_url': 'https://own.example', 'last_verified': '2026-10-15',
               'signals': [{'name_raw': 'Mia', **roster('Research Group Leaders')}]}
        self.assertEqual(ca.classify_role(one, 2026)['role_class'], 'phd_student')

    def test_a_group_leader_named_on_a_roster_keeps_a_group_of_its_own_and_the_heads_members_stay_with_the_head(self):
        head = person('Chris Director', 'professor', [roster('Director', role='pi', roster_pi='Chris Director')])
        lead = person('Rita Lead', 'group_leader', [roster('Research Group Leaders', roster_pi='Chris Director')])
        member = person('Pia Student', 'phd_student', [roster('PhD Candidates', roster_pi='Chris Director')])
        groups = {p['name']: p for p in assign_groups([head, lead, member])}
        self.assertEqual(groups['Rita Lead']['group'], f'Rita Lead @ {MPI}')
        self.assertIn('leader self', groups['Rita Lead']['group_evidence'])
        self.assertEqual(groups['Pia Student']['group'], f'Chris Director @ {MPI}')


class SecondaryPostTests(unittest.TestCase):
    def member(self, title, place='Saarland University', current=DFKI):
        return {'name': 'Richard', 'role_class': 'professor', 'current_affiliation': current, 'country': 'DE',
                'final_pass_title': title, 'final_pass_affiliation': place, 'final_pass_country': 'DE',
                'final_pass_url': 'https://graphics.example/people', 'last_verified': '2026-10-19',
                'signals': [{'name_raw': 'Richard', 'affiliation_raw': current, 'date': '2025-01'}]}

    def test_a_secondary_professorship_elsewhere_goes_to_also_at_and_the_primary_institution_stays(self):
        for title in ('Affiliated Professor', 'Adjunct Professor', 'Honorary Professor', 'Honorarprofessor',
                      'Außerplanmäßiger Professor', 'apl. Professor', 'Privatdozent'):
            one = self.member(title)
            with self.subTest(title=title):
                self.assertEqual(affiliation_for(one), DFKI)
                self.assertEqual(group_affiliation(one), (DFKI, ['Saarland University']))
                applied = ca.apply_final_pass({**one, 'affiliation_source': 'evidence 2025-01'})
                self.assertEqual((applied['current_affiliation'], applied['country']), (DFKI, 'DE'))
                self.assertIn('secondary post', applied['notes'])

    def test_only_a_current_leading_secondary_title_counts(self):
        for title in ('Full Professor (formerly Adjunct Professor)', 'Researcher in the group of Honorary Professor Jane Doe',
                      'Former Honorary Professor'):
            one = self.member(title)
            with self.subTest(title=title):
                self.assertNotEqual(group_affiliation(one)[1], ['Saarland University'])
                applied = ca.apply_final_pass({**one, 'affiliation_source': 'evidence 2025-01'})
                self.assertNotIn('secondary post', applied.get('notes', ''))

    def test_the_export_keeps_the_records_country_and_the_secondary_rosters_members_join(self):
        import table_export
        one = self.member('Honorary Professor', place='Stanford University')
        one['final_pass_country'] = 'US'
        self.assertEqual(table_export.country_for(one), 'DE')
        lead = {**self.member('Adjunct Professor'), 'name': 'Richard',
                'signals': [{'name_raw': 'Richard', 'signal_type': 'lab_member', 'role': 'pi', 'parent': 'Graphics Lab',
                             'channel': 'final-pass', 'date': '', 'affiliation_raw': 'Saarland University', 'roster_pi': 'Richard',
                             'evidence_url': PAGE}]}
        student = {'name': 'Pia', 'role_class': 'phd_student', 'final_pass_title': 'PhD student',
                   'final_pass_affiliation': 'Saarland University', 'final_pass_country': 'DE', 'last_verified': '2026-10-19',
                   'signals': [{'name_raw': 'Pia', 'signal_type': 'lab_member', 'role': 'team_member', 'parent': 'Graphics Lab',
                                'channel': 'final-pass', 'date': '', 'affiliation_raw': 'Saarland University', 'evidence_url': PAGE}]}
        self.assertEqual({p['name']: p for p in assign_groups([lead, student])}['Pia']['group'], f'Richard @ {DFKI}')

    def test_a_secondary_title_at_the_same_institution_or_without_another_record_is_an_ordinary_read(self):
        same = self.member('Adjunct Professor', place='DFKI Saarbrücken')
        self.assertEqual(affiliation_for(same), 'DFKI Saarbrücken')
        alias = self.member('Adjunct Professor', place='École Polytechnique Fédérale de Lausanne', current='EPFL')
        self.assertEqual(group_affiliation(alias), ('École Polytechnique Fédérale de Lausanne', []))
        alone = self.member('Affiliated Professor', current='')
        self.assertEqual(affiliation_for(alone), 'Saarland University')

    def test_an_ordinary_professorship_elsewhere_is_a_move(self):
        moved = self.member('Full Professor')
        self.assertEqual(affiliation_for(moved), 'Saarland University')
        self.assertEqual(group_affiliation(moved), ('Saarland University', []))


if __name__ == '__main__':
    unittest.main()
