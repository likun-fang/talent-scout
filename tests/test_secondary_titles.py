import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_affiliation as ca
from person_fields import affiliation_for, assign_groups, group_affiliation, leader_heading

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

    def test_a_mixed_or_qualified_heading_is_not_a_group_leader_heading(self):
        for heading in ('Group Leaders / PhD Students', 'Group Leaders, Postdocs and PhD Students', 'Postdocs; Group Leaders',
                        'Group Leader (former)', 'Group Leader (until 2022)', 'Group Leader (Deputy)',
                        'Group Leader (2015-2019)'):
            with self.subTest(heading=heading):
                self.assertFalse(leader_heading(heading))
        for heading in ('Research Group Leaders (W2)', 'Group Leader of Surgical Analytics', 'Scientist / Group Leader'):
            with self.subTest(heading=heading):
                self.assertTrue(leader_heading(heading))

    def test_a_dated_or_other_institution_roster_heading_does_not_outrank_the_final_pass(self):
        for heading_roster in (roster('Research Group Leaders', affiliation_raw='University of Oldtown'),
                               roster('Group Leaders', date='2017-03', channel='lab-pages')):
            one = {'name': 'Marc', 'final_pass_title': 'Senior Researcher', 'final_pass_affiliation': MPI,
                   'final_pass_url': 'https://own.example', 'last_verified': '2026-10-15',
                   'signals': [{'name_raw': 'Marc', **heading_roster}]}
            with self.subTest(roster=heading_roster['affiliation_raw'], date=heading_roster['date']):
                self.assertEqual(ca.classify_role(one, 2026)['role_class'], 'researcher')
        unit = {'name': 'Marc', 'final_pass_title': 'Senior Researcher', 'final_pass_affiliation': 'Max Planck Institute for Informatics',
                'final_pass_url': 'https://own.example', 'last_verified': '2026-10-15',
                'signals': [{'name_raw': 'Marc', **roster('Research Group Leaders', affiliation_raw=f'{MPI}, Visual Computing')}]}
        self.assertEqual(ca.classify_role(unit, 2026)['role_class'], 'group_leader')

    def test_a_roster_dated_before_the_read_day_or_without_an_institution_does_not_outrank_the_final_pass(self):
        for heading_roster in (roster('Group Leaders', date='2026-10-01', channel='lab-pages'),
                               roster('Group Leaders', affiliation_raw='')):
            one = {'name': 'Marc', 'final_pass_title': 'Senior Researcher', 'final_pass_affiliation': MPI,
                   'final_pass_url': 'https://own.example', 'last_verified': '2026-10-19',
                   'signals': [{'name_raw': 'Marc', **heading_roster}]}
            with self.subTest(date=heading_roster['date'], institution=heading_roster['affiliation_raw']):
                self.assertEqual(ca.classify_role(one, 2026)['role_class'], 'researcher')
        month = {'name': 'Marc', 'final_pass_title': 'Senior Researcher', 'final_pass_affiliation': MPI,
                 'final_pass_url': 'https://own.example', 'last_verified': '2026-10-19',
                 'signals': [{'name_raw': 'Marc', **roster('Group Leaders', date='2026-10', channel='lab-pages')}]}
        self.assertEqual(ca.classify_role(month, 2026)['role_class'], 'group_leader')

    def test_a_group_leader_named_only_on_an_old_roster_does_not_anchor_a_group(self):
        head = person('Chris Director', 'professor', [roster('Director', role='pi', roster_pi='Chris Director')])
        lead = person('Rita Lead', 'group_leader', [roster('Group Leaders', date='2017-03', channel='lab-pages',
                                                           roster_pi='Chris Director')],
                      final_pass_affiliation=MPI, final_pass_title='Group Leader', last_verified='2026-10-15')
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
                      'Außerplanmäßiger Professor', 'apl. Professor', 'Privatdozent', 'Adjunct Associate Professor',
                      'Adjunct Assistant Professor', 'Honorary Associate Professor', 'Affiliate Professor', 'PD Dr.',
                      'apl. Prof. Dr.'):
            one = self.member(title)
            with self.subTest(title=title):
                self.assertEqual(affiliation_for(one), DFKI)
                self.assertEqual(group_affiliation(one), (DFKI, ['Saarland University']))
                applied = ca.apply_final_pass({**one, 'affiliation_source': 'evidence 2025-01'})
                self.assertEqual((applied['current_affiliation'], applied['country']), (DFKI, 'DE'))
                self.assertIn('secondary post', applied['notes'])
                self.assertIn('https://graphics.example/people', applied['notes'])

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

    def secondary_leader(self):
        return {**self.member('Adjunct Professor'),
                'signals': [{'name_raw': 'Richard', 'signal_type': 'lab_member', 'role': 'pi', 'parent': 'Graphics Lab',
                             'channel': 'final-pass', 'date': '', 'affiliation_raw': 'Saarland University',
                             'roster_pi': 'Richard', 'evidence_url': PAGE}]}

    def test_a_roster_member_who_also_coauthored_with_a_professor_at_the_secondary_institution_stays_with_the_roster_head(self):
        anna = {'name': 'Anna Prof', 'role_class': 'professor', 'current_affiliation': 'Saarland University',
                'signals': [{'name_raw': 'Anna Prof', 'signal_type': 'lab_publication', 'role': 'last_author',
                             'parent': 'Anna Prof', 'channel': 'awards-papers', 'date': '2025-06',
                             'affiliation_raw': 'Saarland University', 'evidence_url': 'https://paper'}]}
        pia = {'name': 'Pia', 'role_class': 'phd_student', 'final_pass_title': 'PhD student',
               'final_pass_affiliation': 'Saarland University', 'final_pass_country': 'DE', 'last_verified': '2026-10-19',
               'current_affiliation': 'Saarland University',
               'signals': [{'name_raw': 'Pia', 'signal_type': 'lab_member', 'role': 'team_member', 'parent': 'Graphics Lab',
                            'channel': 'final-pass', 'date': '', 'affiliation_raw': 'Saarland University',
                            'evidence_url': PAGE, 'roster_pi': 'Richard'},
                           {'name_raw': 'Pia', 'signal_type': 'lab_publication', 'role': 'first_author', 'parent': 'Anna Prof',
                            'channel': 'awards-papers', 'date': '2025-06', 'affiliation_raw': 'Saarland University',
                            'evidence_url': 'https://paper'}]}
        groups = {p['name']: p for p in assign_groups([self.secondary_leader(), anna, pia])}
        self.assertEqual(groups['Pia']['group'], f'Richard @ {DFKI}')
        self.assertIn('roster head Richard', groups['Pia']['group_evidence'])

    def test_a_coauthor_at_the_secondary_institution_is_not_at_a_different_institution(self):
        max_ = {'name': 'Max', 'role_class': 'researcher', 'current_affiliation': 'Saarland University',
                'final_pass_affiliation': 'Saarland University', 'final_pass_title': 'Postdoc', 'last_verified': '2026-10-19',
                'signals': [{'name_raw': 'Max', 'signal_type': 'lab_publication', 'role': 'first_author', 'parent': 'Richard',
                             'channel': 'awards-papers', 'date': '2025-06', 'affiliation_raw': 'Saarland University',
                             'evidence_url': 'https://paper2'}]}
        groups = {p['name']: p for p in assign_groups([self.secondary_leader(), max_])}
        self.assertEqual(groups['Max']['group'], f'Richard @ {DFKI}')

    def test_two_institutions_of_one_city_are_two_institutions(self):
        for current, place in (('DFKI Kaiserslautern', 'Saarland University, Saarbrücken'),
                               ('German Research Center for Artificial Intelligence (DFKI), Saarbrücken', 'Saarland University'),
                               ('Technical University of Munich', 'Munich Center for Machine Learning')):
            one = self.member('Adjunct Professor', place=place, current=current)
            with self.subTest(current=current, place=place):
                self.assertEqual(affiliation_for(one), current)
                self.assertEqual(group_affiliation(one), (current, [place]))

    def test_an_honorary_professorship_beside_a_company_record_leaves_the_person_in_industry(self):
        one = self.member('Honorary Professor', place='Technical University of Munich', current='Siemens AG')
        result = ca.classify_role(one, 2026)
        self.assertEqual(result['role_class'], 'industry')
        self.assertIn('Honorary Professor', result['role_evidence'])
        self.assertEqual(group_affiliation(one), ('Siemens AG', ['Technical University of Munich']))

    def test_a_secondary_post_at_an_institution_named_by_its_acronym_is_still_a_secondary_post(self):
        for place in ('TUM', 'KIT', 'NCT/UCC Dresden', 'TUM, Munich', 'KU Leuven'):
            one = self.member('Honorary Professor', place=place, current='Siemens AG')
            with self.subTest(place=place):
                self.assertEqual(group_affiliation(one), ('Siemens AG', [place]))
                self.assertEqual(ca.classify_role(one, 2026)['role_class'], 'industry')

    def test_a_roster_at_the_records_own_institution_is_not_a_second_post(self):
        lead = {**self.member('Adjunct Professor', current='DFKI'),
                'signals': [{'name_raw': 'Richard', 'signal_type': 'lab_member', 'role': 'pi', 'parent': 'Agents Lab',
                             'channel': 'final-pass', 'date': '', 'affiliation_raw': 'DFKI', 'roster_pi': 'Richard',
                             'evidence_url': PAGE}]}
        self.assertEqual(group_affiliation(lead), ('DFKI', ['Saarland University']))

    def test_a_record_institution_named_by_its_acronym_keeps_a_roster_backed_second_post(self):
        lead = {**self.member('Honorary Professor', place='EPFL', current='TUM'),
                'signals': [{'name_raw': 'Richard', 'signal_type': 'lab_member', 'role': 'pi', 'parent': 'Zurich Lab',
                             'channel': 'final-pass', 'date': '', 'affiliation_raw': 'University of Zurich',
                             'roster_pi': 'Richard', 'evidence_url': PAGE}]}
        self.assertEqual(group_affiliation(lead), ('TUM', ['EPFL', 'University of Zurich']))

    def test_a_secondary_title_at_the_same_institution_or_without_another_record_is_an_ordinary_read(self):
        for place, current in (('Universität des Saarlandes', 'Saarland University'), ('DFKI Saarbrücken', DFKI),
                               ('NCT/UCC Dresden', 'National Center for Tumor Diseases Dresden (NCT/UCC)')):
            same = self.member('Adjunct Professor', place=place, current=current)
            with self.subTest(place=place):
                self.assertEqual(affiliation_for(same), place)
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
