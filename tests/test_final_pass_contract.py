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
        leaders = [{**person('A', 'Bonn', 'pi', parent='Vision Lab'), 'role_class': 'professor'},
                   {**person('B', 'Bremen', 'pi', parent='Vision Lab'), 'role_class': 'professor'}]
        result = assign_groups([*leaders, person('Student', '', parent='Vision Lab', signal_type='lab_member')])[-1]
        self.assertEqual(result['group'], '')
        self.assertIn('ambiguous: A, B', result['group_evidence'])
        result = assign_groups([*leaders, person('Student', 'University of Bonn', parent='Vision Lab', signal_type='lab_member')])[-1]
        self.assertEqual(result['group'], 'A @ Bonn')

    def test_personal_homepage_host_and_generic_hosts(self):
        for host, expected in [('dtruhn.github.io', 'Truhn @ RWTH Aachen'),
                               ('aidx-lab.org', 'Truhn @ RWTH Aachen'),
                               ('www.dsme.rwth-aachen.de', 'Truhn @ RWTH Aachen'), ('sites.google.com', ''),
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
        lead = {**person('A', 'Long name', 'pi', parent='Lab'), 'institution_id': 'https://openalex.org/I1', 'role_class': 'professor'}
        other = {**person('B', 'Elsewhere', 'pi', parent='Lab'), 'role_class': 'professor'}
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


class FinalPassTests(unittest.TestCase):
    def test_enrichment_and_export_apply_final_affiliation_before_tier(self):
        import current_affiliation as ca
        import table_export as te
        from argparse import Namespace
        import datetime
        p = {**person('Mover', 'EPFL', role='first_author', country='CH', date='2025', channel='papers'),
             'current_affiliation': 'EPFL', 'country': 'CH', 'affiliation_source': 'openalex old',
             'notes': 'Preserve this note', 'final_pass_affiliation': 'NAVER LABS Europe',
             'final_pass_country': 'FR', 'final_pass_title': 'Research Scientist',
             'final_pass_url': 'https://naver.example/person', 'last_verified': '2026-10-12'}
        original = copy.deepcopy(p)
        enriched = ca.enrich(p, ca.region_codes('EU27+UK+CH+NO'), run_year=2026)
        self.assertEqual((enriched['current_affiliation'], enriched['country']), ('NAVER LABS Europe', 'FR'))
        self.assertEqual(enriched['affiliation_source'], 'final pass 2026-10-12 https://naver.example/person')
        self.assertIn('source affiliation: EPFL (', enriched['notes'])
        self.assertIn('Preserve this note', enriched['notes'])
        args = Namespace(date=datetime.date(2026, 10, 12), window_months=36, region='EU27+UK+CH+NO',
                         region_core='DE+CH', max_rows=0, domain='')
        selected = te.select_persons([p], args)[0][0]
        self.assertEqual((selected['country'], selected['tier'], selected['role_class']), ('FR', 4, 'industry'))
        row = te.row_for(selected, '', '2026-10-12')
        self.assertEqual((row['role'], row['latest_role']), ('first_author', 'first_author'))
        self.assertEqual(p, original)

    def test_final_pass_is_idempotent_and_never_reuses_old_country(self):
        import current_affiliation as ca
        p = {**person('Mover', country='CH'), 'current_affiliation': 'EPFL', 'country': 'CH',
             'final_pass_affiliation': 'New Lab', 'affiliation_source': 'provider', 'notes': 'keep'}
        updated = ca.apply_final_pass(p)
        self.assertEqual(updated['country'], '')
        self.assertEqual(ca.apply_final_pass(updated), updated)


class IndustryTests(unittest.TestCase):
    def test_company_before_title_but_professor_exception(self):
        import current_affiliation as ca
        for employer in ['NAVER LABS Europe', 'DeepMind', 'Sony', 'Bosch', 'Mistral', 'Aleph Alpha',
                         'Example GmbH', 'Example AG', 'Example Ltd', 'Example Inc', 'Example SA',
                         'Example SAS', 'Example B.V.', 'Bell Labs', 'Example Research Europe']:
            with self.subTest(employer=employer):
                p = {**person('Employee', employer, role_title='Research Scientist'),
                     'final_pass_affiliation': employer, 'last_verified': '2026-10-12',
                     'final_pass_title': 'Research Scientist', 'final_pass_url': 'https://company.example/person'}
                result = ca.classify_role(p, 2026)
                self.assertEqual((result['role_class'], result['role_confidence']), ('industry', 'high'))
                self.assertIn('industry | Research Scientist |', result['role_evidence'])
                p['final_pass_title'] = 'Professor'
                self.assertEqual(ca.classify_role(p, 2026)['role_class'], 'professor')
        p = person('Employee', role_title='Research Scientist', institution_type='company')
        self.assertEqual(ca.classify_role(p, 2026)['role_class'], 'industry')
        self.assertEqual(ca.classify_role(p, 2026)['role_confidence'], 'medium')

    def test_current_academic_affiliation_wins_over_old_company(self):
        import current_affiliation as ca
        p = {**person('Mover', 'Example Ltd', role_title='Research Scientist'),
             'final_pass_affiliation': 'EPFL', 'final_pass_country': 'CH', 'last_verified': '2026-10-12',
             'final_pass_title': 'Postdoc', 'final_pass_url': 'https://epfl.example/person'}
        self.assertEqual(ca.classify_role(p, 2026, institution=('Old Ltd', 'GB', '2025', 'company', 'I1'))['role_class'], 'researcher')

    def test_new_titles_and_honorary_annotation(self):
        import current_affiliation as ca
        for title in ['Research Junior Group Lead', 'JRG Leader', 'Junior Research Group Leader',
                      'Site Lead', 'Head of Digital Humanities', 'Nachwuchsgruppenleiterin']:
            self.assertEqual(ca.classify_role(person('A', role_title=title), 2026)['role_class'], 'group_leader', title)
        for title in ['senior researcher and lecturer', 'clinical radiologist and imaging scientist',
                      'clinical scientist', 'chargée de recherche', 'maître de conférences']:
            r = ca.classify_role(person('A', role_title=title), 2026)
            self.assertEqual((r['role_class'], r['role_confidence']), ('researcher', 'high'), title)
        for title in ['Honorarprofessor', 'Honorary Professor']:
            r = ca.classify_role(person('A', role_title=title), 2026)
            self.assertEqual(r['role_class'], 'professor')
            self.assertIn('honorary', r['role_evidence'])

    def test_new_funding_roles_and_schema(self):
        import current_affiliation as ca
        import json, re
        schema = json.loads((Path(__file__).resolve().parents[1] / 'assets/signal.schema.json').read_text())
        pattern = schema['allOf'][0]['if']['properties']['signal_type']['pattern']
        for kind in ['fwf_project', 'swecris_project', 'rcn_project', 'dff_project', 'fris_project', 'aei_project', 'fwf_start', 'fwf_esprit']:
            r = ca.classify_role(person('A', role='pi', signal_type=kind), 2026)
            self.assertEqual((r['role_class'], r['role_confidence']),
                             ('researcher' if kind == 'fwf_esprit' else 'group_leader', 'medium'))
            self.assertTrue(re.match(pattern, kind))


class OfflineTests(unittest.TestCase):
    def test_cli_uses_cached_responses_counts_misses_and_never_fetches(self):
        import current_affiliation as ca
        import tempfile, json, hashlib, io
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'persons.jsonl'
            src.write_text(json.dumps({**person('A'), 'ids': {'openalex': 'A1', 'orcid': '0000'}}) + '\n')
            cached = root / (hashlib.sha256(b'openalex-author/A1').hexdigest() + '.json')
            cached.write_text(json.dumps({'last_known_institutions': [{'display_name': 'EPFL', 'country_code': 'CH', 'type': 'education', 'id': 'I1'}]}))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            out, err = io.StringIO(), io.StringIO()
            with patch.object(sys, 'argv', ['current_affiliation.py', str(src), '--offline', '--cache-dir', tmp, '--date', '2026-10-12']), \
                 patch('sys.stdout', out), patch('sys.stderr', err), \
                 patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
                ca.main()
            self.assertEqual(json.loads(out.getvalue())['country'], 'CH')
            self.assertIn('offline cache misses: 2', err.getvalue())
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)


class ExportContractTests(unittest.TestCase):
    def test_export_defaults_norway_unattached_whitespace_and_evidence(self):
        import table_export as te
        import tempfile, json, csv
        from unittest.mock import patch
        p = person('Norwegian', 'Lab', country='NO', date='2023', channel='papers',
                   snippet='ANR\n  project\t title', topics=['Exact Topic'])
        p.update(group_evidence='unattached', notes='Note\r\n  with\tspaces')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'persons.jsonl'
            src.write_text(json.dumps(p) + '\n')
            with patch.object(sys, 'argv', ['table_export.py', str(src), '--date', '2026-10-12', '--out', str(root/'roster')]):
                te.main()
            with (root / 'roster.csv').open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
            with (root / 'groups.csv').open(encoding='utf-8-sig', newline='') as f:
                groups = list(csv.DictReader(f))
            md = (root / 'roster.md').read_text()
            group_md = (root / 'groups.md').read_text()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['notes'], 'Note with spaces')
        self.assertIn('Note with spaces', md)
        self.assertIn('year-only dates qualify when the year overlaps the window', md)
        self.assertIn('unattached', md)
        self.assertEqual(groups[0]['group'], '(unattached)')
        self.assertEqual(groups[0]['member_count'], '1')
        self.assertIn('ANR project title', groups[0]['recent_outputs'])
        self.assertIn('ANR project title', group_md)
        self.assertEqual(len(rows[0]), 25)

    def test_new_funding_in_group_view_and_raw_topics_unchanged(self):
        import table_export as te
        import datetime
        p = person('A', role='pi', signal_type='fwf_start', date='2025', topics=['Exact  Topic'])
        p.update(tier=1, group='A @ EPFL')
        original = copy.deepcopy(p)
        row = te.group_rows([p], datetime.date(2023, 10, 12), datetime.date(2026, 10, 12))[0]
        self.assertEqual(row['active_funding'], 'fwf_start@2025')
        self.assertEqual(p, original)
        self.assertEqual(row['topics'], 'Exact  Topic')


class GroupResolutionTests(unittest.TestCase):
    def test_mutual_leader_links_are_ambiguous_not_two_inconsistent_groups(self):
        a = {**person('A', parent='Shared team'), 'role_class': 'group_leader'}
        b = {**person('B', parent='Shared team'), 'role_class': 'group_leader'}
        results = assign_groups([a, b, person('Student', parent='A')])
        self.assertTrue(all(not p['group'] for p in results))
        self.assertTrue(all('ambiguous:' in p['group_evidence'] for p in results))

    def test_member_of_nested_leader_uses_resolved_group_with_chain_evidence(self):
        lead = person('PI', role='pi')
        junior = {**person('Junior', parent='PI'), 'role_class': 'group_leader'}
        student = person('Student', parent='Junior')
        results = assign_groups([lead, junior, student])
        self.assertEqual([p['group'] for p in results], ['PI @ EPFL'] * 3)
        self.assertIn('via Junior', results[-1]['group_evidence'])


class ReviewedHeadingTests(unittest.TestCase):
    def test_reviewed_mixed_heading_does_not_fall_back_to_old_professorship(self):
        import current_affiliation as ca
        p = {**person('A', role='pi', role_title='Professor', signal_type='erc_starting'),
             'final_pass_title': 'Staff / PhD Students', 'final_pass_url': 'https://lab.example/team',
             'last_verified': '2026-10-12'}
        self.assertEqual(ca.classify_role(p, 2026)['role_class'], 'unknown')
