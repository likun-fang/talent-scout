import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from person_fields import assign_groups
from current_affiliation import classify_role


def person(name, affiliation='ETH Zurich', role_class='researcher', **signal):
    return {'name': name, 'current_affiliation': affiliation, 'role_class': role_class,
            'signals': [{'name_raw': name, 'affiliation_raw': affiliation, 'role': 'team_member',
                         'evidence_url': 'https://lab.example/team', **signal}]}


class GroupAuthorityTests(unittest.TestCase):
    def test_project_pi_researcher_cannot_anchor_five_lab_members(self):
        for homepage in ['', 'https://srl.ethz.ch/people']:
            with self.subTest(homepage=homepage):
                lead = person('Hinchet', role='pi', signal_type='snsf_project', parent='Soft Robotics Lab', homepage=homepage)
                members = [person(f'Member {i}', signal_type='lab_member', parent='Soft Robotics Lab', homepage=homepage) for i in range(5)]
                results = assign_groups([lead, *members])
                self.assertTrue(all(not p['group'] for p in results[1:]))
                self.assertTrue(all('unattached' in p['group_evidence'] or 'ambiguous' in p['group_evidence'] for p in results[1:]))

    def test_explicit_name_or_homepage_still_links_project_pi(self):
        for parent in ['Hinchet', 'https://srl.ethz.ch/hinchet']:
            lead = person('Hinchet', role='pi', homepage='https://srl.ethz.ch/hinchet')
            member = person('Member', parent=parent)
            self.assertEqual(assign_groups([lead, member])[1]['group'], 'Hinchet @ ETH Zurich')

    def test_professor_coauthors_always_anchor_their_own_groups(self):
        people = [person('Kragic', 'KTH', 'professor', parent='Awarded Paper', channel='awards-papers'),
                  person('Peters', 'TU Darmstadt', 'professor', parent='Awarded Paper', channel='awards-papers')]
        self.assertEqual([p['group'] for p in assign_groups(people)], ['Kragic @ KTH', 'Peters @ TU Darmstadt'])

    def test_cross_institution_paper_parent_is_not_membership(self):
        for channel in ['awards-papers', 'industry', 'competitions', 'funding-de-ch']:
            lead = person('Lead', 'Idiap', 'group_leader', parent='Paper title')
            member = person('Member', 'NVIDIA', parent='Paper title', channel=channel)
            result = assign_groups([lead, member])[1]
            self.assertEqual(result['group'], '')
            self.assertIn('coauthor only, different institution', result['group_evidence'])

    def test_same_institution_paper_and_cross_institution_team_links(self):
        for affiliation, channel, kind in [('ETH Zurich', 'awards-papers', 'paper'), ('Other', 'labs', 'lab_member')]:
            lead = person('Lead', role_class='group_leader', parent='Shared source')
            member = person('Member', affiliation, channel=channel, signal_type=kind, parent='Shared source')
            self.assertEqual(assign_groups([lead, member])[1]['group'], 'Lead @ ETH Zurich')
        # Paper channels remain paper evidence even if a lab_member happens to use the same parent.
        lead['signals'].append({'signal_type': 'lab_member', 'parent': 'Shared source'})
        member['signals'][0]['channel'] = 'awards-papers'
        result = assign_groups([lead, member])[1]
        self.assertEqual(result['group'], '')
        self.assertIn('coauthor only, different institution', result['group_evidence'])

    def test_group_leader_can_still_join_professor(self):
        lead = person('Wermter', 'Hamburg', 'professor')
        member = person('Jae Hee Lee', 'Hamburg', 'group_leader', parent='Wermter')
        self.assertEqual(assign_groups([lead, member])[1]['group'], 'Wermter @ Hamburg')


class CompanyPrecisionTests(unittest.TestCase):
    def classify(self, affiliation):
        return classify_role(person('A', affiliation, role_title='Research Scientist'), 2026)['role_class']

    def test_company_names_and_academic_healthcare_exclusions(self):
        for affiliation in ['Robert Bosch Hospital', 'Bosch Klinik', 'Sony Clinic', 'Google University',
                            'NAVER Universität', 'Mistral Université', 'Microsoft Universiteit',
                            'Bosch Institute of Technology', 'Sony Hochschule', 'Google School', 'Microsoft College',
                            'Meta-Research', 'FAIR data', 'Amazon basin', 'Apple Research', 'Example Labs']:
            with self.subTest(affiliation=affiliation):
                self.assertNotEqual(self.classify(affiliation), 'industry')
        for affiliation in ['Bosch Center for AI', 'NAVER LABS Europe', 'Bell Labs', 'Bosch Hospital GmbH',
                            'Sony University AG', 'Google School Inc', 'Microsoft College Ltd']:
            with self.subTest(affiliation=affiliation):
                self.assertEqual(self.classify(affiliation), 'industry')

    def test_sa_is_case_sensitive_terminal_or_comma_delimited(self):
        for affiliation in ['Example SA', 'Example SA, France']:
            self.assertEqual(self.classify(affiliation), 'industry')
        for affiliation in ['Example sa', 'Example Sa', 'Example SA Research', 'SA Laboratory']:
            self.assertNotEqual(self.classify(affiliation), 'industry')
