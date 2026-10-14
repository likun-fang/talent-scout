import copy
import datetime
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_affiliation as ca
import merge_persons as mp
from person_fields import assign_groups, topics_for


def signal(**changes):
    return {'kind': 'person', 'name_raw': 'Alex', 'channel': 'funding-eu', 'signal_type': 'paper',
            'date': '2025-01', 'affiliation_raw': 'Example Institute', 'country': 'DE', 'role': 'unknown',
            'evidence_url': 'https://example.org/evidence', **changes}


class RoleTests(unittest.TestCase):
    def classify(self, **changes):
        return ca.classify_role({'signals': [signal(**changes)]}, 2026)

    def test_explicit_title_mapping(self):
        titles = {
            'professor': ['Professor', 'Prof.', 'Chair of Robotics', 'Lehrstuhl', 'Juniorprofessor', 'Assistant Professor',
                          'Associate Professor', 'Faculty', 'Direktor', 'Director'],
            'group_leader': ['Group Leader', 'Head of Lab', 'Head of Group', 'Head of Chair', 'Principal Investigator',
                             'Head of Autonomous Intelligent Systems Group', 'Junior Group Leader (Oberassistent)'],
            'phd_student': ['PhD student', 'Doctoral student', 'Doctoral researcher', 'Doctoral candidate',
                            'Doktorand', 'Dissertation', 'Ph.D. candidate'],
            'researcher': ['Postdoc', 'Postdoctoral researcher', 'Senior Scientist', 'Research Scientist',
                           'Wissenschaftlicher Mitarbeiter', 'Research Associate', 'Staff Scientist', 'Oberassistent'],
        }
        for role, examples in titles.items():
            for title in examples:
                with self.subTest(title=title):
                    result = self.classify(role_title=title)
                    self.assertEqual((result['role_class'], result['role_confidence']), (role, 'high'))
                    self.assertIn(f'| {title} |', result['role_evidence'])
                    self.assertIn('rule 1', result['role_evidence'])
                    self.assertIn('https://example.org/evidence', result['role_evidence'])

    def test_german_researcher_caveat(self):
        self.assertIn('DE: may be PhD student', self.classify(role_title='Wissenschaftlicher Mitarbeiter')['role_evidence'])

    def test_director_requires_research_context_and_word_boundaries(self):
        self.assertEqual(ca.title_class('Director', affiliation='Example Ltd'), '')
        self.assertEqual(ca.title_class('Director', 'research'), 'professor')
        for title in ['professional', 'chairman', 'software engineer']:
            self.assertEqual(ca.title_class(title), '')

    def test_industry_explicit_title_conditions(self):
        for title in ['Engineer', 'Software developer', 'Research Engineer']:
            with self.subTest(title=title):
                self.assertEqual(self.classify(role_title=title, institution_type='company')['role_class'], 'industry')
                self.assertEqual(self.classify(role_title=title)['role_class'], 'unknown')
        for suffix in ['GmbH', 'AG', 'Ltd', 'Inc']:
            result = self.classify(role_title=f'Employee, Example {suffix}')
            self.assertEqual((result['role_class'], result['role_confidence']), ('industry', 'high'))

    def test_rule_precedence(self):
        result = self.classify(role_title='Doctoral student', signal_type='erc_starting', role='pi', affiliation_raw='Example GmbH')
        self.assertEqual(result['role_class'], 'industry')
        result = self.classify(signal_type='dfg_project', role='pi', affiliation_raw='Example GmbH')
        self.assertEqual(result['role_class'], 'industry')
        person = {'first_pub_year': 2023, 'signals': [signal(role='first_author', affiliation_raw='Example GmbH')]}
        self.assertEqual(ca.classify_role(person, 2026)['role_class'], 'industry')

    def test_every_funding_type_and_non_pi(self):
        kinds = ['erc_starting', 'dfg_project', 'dfg_emmy_noether', 'dfg_heisenberg', 'snsf_project',
                 'snsf_starting_grant', 'snsf_professorship', 'snsf_ambizione']
        for kind in kinds:
            with self.subTest(kind=kind):
                result = self.classify(signal_type=kind, role='pi')
                expected = 'researcher' if kind == 'snsf_ambizione' else 'group_leader'
                self.assertEqual((result['role_class'], result['role_confidence']), (expected, 'medium'))
                self.assertIn('rule 2', result['role_evidence'])
                self.assertEqual(self.classify(signal_type=kind, role='team_member')['role_class'], 'unknown')
        for kind in ['graduiertenkolleg_member', 'imprs_member']:
            self.assertEqual(self.classify(signal_type=kind)['role_class'], 'unknown')

    def test_company_type_and_affiliation_fallback(self):
        result = ca.classify_role({'signals': []}, 2026, institution=('Firm', 'DE', '2026', 'company', 'https://example.org/company'))
        self.assertEqual((result['role_class'], result['role_confidence']), ('industry', 'medium'))
        self.assertIn('rule 3', result['role_evidence'])
        for suffix in ['GmbH', 'AG', 'Ltd', 'Inc', 'SA']:
            self.assertEqual(self.classify(affiliation_raw=f'Example {suffix}')['role_class'], 'industry')
        self.assertEqual(self.classify(affiliation_raw='Saarland')['role_class'], 'unknown')

    def test_inference_boundaries_strict_majority_and_invalid_years(self):
        cases = [(2021, ['first_author'], 'phd_student'), (2020, ['first_author'], 'unknown'),
                 (2016, ['last_author', 'pi', 'coauthor'], 'group_leader'), (2017, ['pi'], 'unknown'),
                 (2021, ['first_author', 'coauthor'], 'unknown'), (2016, ['pi', 'unknown'], 'unknown'),
                 (2027, ['first_author'], 'unknown'), ('bad', ['first_author'], 'unknown'),
                 ('', ['pi'], 'unknown'), (-1, ['pi'], 'unknown'), ('0', ['pi'], 'unknown'), (2023, [], 'unknown')]
        for year, roles, expected in cases:
            with self.subTest(year=year, roles=roles):
                result = ca.classify_role({'first_pub_year': year, 'signals': [signal(role=role) for role in roles]}, 2026)
                self.assertEqual((result['role_class'], result['role_confidence']), (expected, 'low'))
                self.assertIn('rule 4', result['role_evidence'])

    def test_title_sources_order_and_no_mutation(self):
        person = {'signals': [signal(role_title='Professor', date='2024'), signal(role_title='Doctoral student', date='2025')],
                  'last_verified': '2026-10-12', 'linkedin_headline': 'Research Scientist', 'linkedin_url': 'https://linkedin.com/in/example'}
        original = copy.deepcopy(person)
        employment = (2025, 'Example Institute', 'DE', 'Postdoc', 'https://orcid.org/example')
        result = ca.classify_role(person, 2026, employment)
        self.assertIn('rule 0: final pass 2026-10-12', result['role_evidence'])
        self.assertEqual(result['role_class'], 'researcher')
        self.assertEqual(person, original)
        result = ca.classify_role({**person, 'last_verified': ''}, 2026, employment)
        self.assertIn('ORCID', result['role_evidence'])
        result = ca.classify_role({**person, 'last_verified': ''}, 2026)
        self.assertEqual(result['role_class'], 'phd_student')

    def test_enrich_uses_provider_titles_and_company_type_without_verifying(self):
        person = {'name': 'A', 'ids': {'orcid': '0000', 'openalex': 'A1'}, 'signals': [signal()]}
        with patch.object(ca, 'orcid_current', return_value=(2025, 'Example Institute', 'DE', 'Doctoral researcher', 'https://orcid.org/0000')), \
             patch.object(ca, 'openalex_current', return_value=('Example Institute', 'DE', '2026', 'company', 'https://openalex.org/I1')), \
             patch.object(ca, 'first_publication_year', return_value=2023):
            result = ca.enrich(person, {'DE'}, run_year=2026)
        self.assertEqual(result['role_class'], 'industry')
        self.assertEqual(result['last_verified'], '')
        self.assertEqual(result['first_pub_year'], 2023)
        self.assertNotIn('role_class', person)

    def test_stale_provider_title_cannot_override_new_evidence(self):
        person = {'ids': {'orcid': '0000', 'openalex': 'A1'}, 'signals': [signal(role_title='Research Scientist')]}
        with patch.object(ca, 'orcid_current', return_value=(1996, 'Old University', 'US', 'Professor', 'https://orcid.org/0000')), \
             patch.object(ca, 'openalex_current', return_value=('Old University', 'DE', '2020', 'company', 'https://openalex.org/I1')), \
             patch.object(ca, 'first_publication_year', return_value=1990):
            result = ca.enrich(person, {'DE'}, run_year=2026)
        self.assertEqual(result['role_class'], 'researcher')
        self.assertEqual(result['current_affiliation'], 'Example Institute')

    def test_enrichment_cli_recomputes_tiers_groups_and_uses_run_year(self):
        people = [{'name': 'Student', 'signals': [signal(role='first_author', parent='Project')],
                   'first_pub_year': 2021, 'tier': 4, 'last_verified': ''},
                  {'name': 'PI', 'signals': [signal(role='pi', role_title='Professor', parent='Project')],
                   'tier': 4, 'last_verified': '2026-10-01'}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'persons.jsonl'
            path.write_text('\n'.join(json.dumps(p) for p in people), encoding='utf-8')
            output = io.StringIO()
            argv = ['current_affiliation.py', str(path), '--date', '2026-10-12', '--workers', '2',
                    '--cache-dir', str(Path(tmp) / 'cache')]
            with patch.object(sys, 'argv', argv), patch('sys.stdout', output), \
                 patch('urllib.request.urlopen', side_effect=AssertionError('offline')):
                ca.main()
            results = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([p['name'] for p in results], ['Student', 'PI'])
        self.assertEqual([p['tier'] for p in results], [2, 1])
        self.assertEqual([p['role_class'] for p in results], ['phd_student', 'professor'])
        self.assertEqual([p['group'] for p in results], ['PI @ Example Institute'] * 2)
        self.assertEqual([p['last_verified'] for p in results], ['', '2026-10-01'])

    def test_provider_payloads_keep_role_and_type(self):
        employments = {'affiliation-group': [{'summaries': [
            {'employment-summary': {'end-date': {'year': {'value': '2020'}}, 'role-title': 'Professor'}},
            {'employment-summary': {'start-date': {'year': {'value': '2025'}}, 'role-title': 'Postdoc',
                                    'organization': {'name': 'Lab', 'address': {'country': 'CH'}}}}]}]}
        with patch.object(ca, 'cached_get', return_value=employments):
            self.assertEqual(ca.orcid_current('https://orcid.org/0000')[3:], ('Postdoc', 'https://orcid.org/0000'))
        with patch.object(ca, 'openalex_get', return_value={'last_known_institutions': [
                {'display_name': 'Firm', 'country_code': 'DE', 'type': 'company', 'id': 'I1'}]}):
            self.assertEqual(ca.openalex_current('A1')[3:], ('company', 'I1'))


class PersonFieldsTests(unittest.TestCase):
    def test_topics_are_verbatim_unique_and_capped(self):
        self.assertEqual(topics_for([signal(topics=['A', 'B', 'A']), signal(topics=['B', 'C', 'D']),
                                     signal(topics=['E', 'F'])]), ['A', 'B', 'C', 'D', 'E'])

    def person(self, name, **changes):
        return {'name': name, 'signals': [signal(name_raw=name, **changes)]}

    def test_pi_self_and_parent_grouping(self):
        people = [self.person('PI', role='pi', parent='Project'), self.person('Student', parent='Project')]
        original = copy.deepcopy(people)
        self.assertEqual([p['group'] for p in assign_groups(people)], ['PI @ Example Institute'] * 2)
        self.assertEqual(people, original)

    def test_paper_last_author_and_missing_parent(self):
        people = [self.person('Lead', role='last_author'), self.person('Student', role='first_author')]
        self.assertEqual([p['group'] for p in assign_groups(people)], ['Lead @ Example Institute'] * 2)
        self.assertEqual(assign_groups([self.person('Alone')])[0]['group'], '')
        self.assertEqual(assign_groups([self.person('Solo last', role='last_author')])[0]['group'], '')

    def test_group_ambiguity_institution_and_current_moves(self):
        people = [self.person('PI1', role='pi', parent='Project'), self.person('PI2', role='pi', parent='Project'),
                  self.person('Student', parent='Project'), self.person('Other', parent='Project', affiliation_raw='Other Institute')]
        self.assertEqual([p['group'] for p in assign_groups(people)][2:], ['', ''])
        moved = {**people[2], 'current_affiliation': 'New Institute'}
        # A unique explicit parent now wins before the same-institution fallback.
        self.assertEqual(assign_groups([people[0], moved])[1]['group'], 'PI1 @ Example Institute')
        self.assertEqual(assign_groups([self.person('PI', role='pi', affiliation_raw='')])[0]['group'], '')

    def test_merge_cli_emits_all_fields_and_preserves_identity_rules(self):
        signals = [signal(role='pi', role_title='Professor', ids={'orcid': '1'}, topics=['Topic']),
                   signal(role='pi', ids={'orcid': '1'}, topics=['Topic']),
                   signal(name_raw='Student', role_title='Doctoral student', parent='Project')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'signals.jsonl'
            path.write_text('\n'.join(json.dumps(s) for s in signals), encoding='utf-8')
            output = io.StringIO()
            with patch.object(sys, 'argv', ['merge_persons.py', str(path), '--date', '2026-10-12']), \
                 patch('sys.stdout', output), patch('urllib.request.urlopen', side_effect=AssertionError('offline')):
                mp.main()
            persons = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(persons), 2)
        for person in persons:
            self.assertTrue({'role_class', 'role_evidence', 'role_confidence', 'tier', 'topics', 'group', 'last_verified'} <= person.keys())
            self.assertEqual(person['last_verified'], '')
        self.assertEqual(persons[0]['tier'], 1)
        self.assertEqual(persons[1]['tier'], 2)
        self.assertEqual(len(mp.cluster([signal(affiliation_raw='Alpha'), signal(affiliation_raw='Beta')])), 2)

    def test_schema_and_column_contract(self):
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / 'assets/signal.schema.json').read_text())
        self.assertEqual(schema['properties']['role_title']['type'], 'string')
        self.assertEqual(schema['properties']['topics']['maxItems'], 3)
        self.assertEqual(schema['properties']['topics']['minItems'], 1)
        examples = schema['properties']['signal_type']['examples']
        for kind in ('dfg_emmy_noether', 'snsf_ambizione', 'snsf_doc_ch', 'dfg_walter_benjamin', 'graduiertenkolleg_member'):
            self.assertIn(kind, examples)
        self.assertEqual(schema['allOf'][0]['then']['properties']['role']['const'], 'pi')
        import table_export
        columns = (root / 'assets/person-table.columns.md').read_text().strip().split(', ')
        self.assertEqual(columns, table_export.COLUMNS)
        self.assertEqual(len(columns), 25)
        self.assertEqual(columns[-6:], ['role_class', 'role_confidence', 'tier', 'topics', 'group', 'role_evidence'])


if __name__ == '__main__':
    unittest.main()
