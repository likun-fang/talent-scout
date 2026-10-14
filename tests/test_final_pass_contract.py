import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from person_fields import assign_groups, same_institution


def person(name, affiliation='EPFL', role='team_member', **signal):
    return {'name': name, 'signals': [{'name_raw': name, 'affiliation_raw': affiliation,
            'role': role, 'evidence_url': 'https://example.org/team', **signal}]}


class InstitutionTests(unittest.TestCase):
    def test_aliases_accents_and_first_segment(self):
        self.assertTrue(same_institution('EPFL', 'École Polytechnique Fédérale de Lausanne'))
        self.assertTrue(same_institution('Universiteit van Amsterdam||Faculteit der Natuurwetenschappen',
                                         'University of Amsterdam'))
        self.assertFalse(same_institution('University of Bonn', 'University of Bremen'))


class GroupContractTests(unittest.TestCase):
    def test_parent_names_leader_without_literal_institution_match(self):
        leader = person('Élise Meyer', role='pi')
        member = person('Student', affiliation='École Polytechnique Fédérale de Lausanne', parent='Prof. Dr. Elise Meyer')
        people = [leader, member]
        before = copy.deepcopy(people)
        result = assign_groups(people)
        self.assertEqual(result[1]['group'], 'Élise Meyer @ EPFL')
        self.assertEqual(result[1]['group_rule'], 1)
        self.assertIn('parent', result[1]['group_evidence'])
        self.assertIn('https://example.org/team', result[1]['group_evidence'])
        self.assertEqual(people, before)

    def test_same_team_page_and_title_only_leader(self):
        leader = {**person('Lead', parent='https://lab.example/team'), 'role_class': 'professor'}
        member = person('Student', parent='https://lab.example/team')
        result = assign_groups([leader, member])
        self.assertEqual(result[1]['group'], 'Lead @ EPFL')
        self.assertEqual(result[1]['group_rule'], 1)

    def test_namesake_labs_need_unique_institution(self):
        leaders = [person('A', 'Bonn', 'pi', parent='Vision Lab'), person('B', 'Bremen', 'pi', parent='Vision Lab')]
        result = assign_groups([*leaders, person('Student', '', parent='Vision Lab')])[-1]
        self.assertEqual(result['group'], '')
        self.assertIn('ambiguous: A, B', result['group_evidence'])
        result = assign_groups([*leaders, person('Student', 'University of Bonn', parent='Vision Lab')])[-1]
        self.assertEqual(result['group'], 'A @ Bonn')

    def test_personal_homepage_host_and_generic_hosts(self):
        for host, expected in [('dtruhn.github.io', 'Truhn @ RWTH Aachen'), ('sites.google.com', ''),
                               ('github.com', ''), ('people.epfl.ch', ''), ('www.rwth-aachen.de', '')]:
            with self.subTest(host=host):
                result = assign_groups([person('Truhn', 'RWTH Aachen', 'pi', homepage=f'https://{host}/'),
                                        person('Nebelung', 'RWTH Aachen', homepage=f'https://{host}/people')])[-1]
                self.assertEqual(result['group'], expected)
                if expected:
                    self.assertEqual(result['group_rule'], 2)
                    self.assertIn(host, result['group_evidence'])

    def test_repository_org(self):
        result = assign_groups([person('Zamir', role='pi', homepage='https://github.com/EPFL-VILAB'),
                                person('Ye', channel='open-source', evidence_url='https://github.com/epfl-vilab/omnidata')])[-1]
        self.assertEqual(result['group'], 'Zamir @ EPFL')
        self.assertEqual(result['group_rule'], 3)
        self.assertIn('epfl-vilab', result['group_evidence'])

    def test_institution_ids_not_author_ids_disambiguate(self):
        lead = {**person('A', 'Long name', 'pi', parent='Lab'), 'institution_id': 'https://openalex.org/I1'}
        other = person('B', 'Elsewhere', 'pi', parent='Lab')
        student = {**person('S', 'Alias', parent='Lab'), 'institution_id': 'I1'}
        self.assertEqual(assign_groups([lead, other, student])[-1]['group'], 'A @ Long name')
        lead.pop('institution_id'); student.pop('institution_id')
        lead['ids'] = student['ids'] = {'openalex': 'A1'}
        self.assertEqual(assign_groups([lead, other, student])[-1]['group'], '')

    def test_leader_without_pi_can_be_member_and_unattached_has_evidence(self):
        lead = person('PI', role='pi')
        junior = {**person('Junior', parent='PI'), 'role_class': 'group_leader'}
        result = assign_groups([lead, junior, person('Alone')])
        self.assertEqual(result[1]['group'], 'PI @ EPFL')
        self.assertEqual(result[2]['group_evidence'], 'unattached')
