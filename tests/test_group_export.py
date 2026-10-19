import argparse
import datetime
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import group_export
from group_export import export, linkedin_hits


def sig(name, affiliation, country, signal_type='lab_member', url='https://lab.example/team', date='2025-06-01',
        channel='funding-de-ch', topics=None, **extra):
    return {'kind': 'person', 'name_raw': name, 'affiliation_raw': affiliation, 'country': country, 'channel': channel,
            'signal_type': signal_type, 'strength': 'medium', 'date': date, 'evidence_url': url, 'hop_depth': 1,
            'snippet': f'{name} on the team page', 'topics': topics or ['vision-language models'], **extra}


def person(name, affiliation, country, role_class, group, link, signals=None, **extra):
    return {'name': name, 'ids': {}, 'channels_hit': ['funding-de-ch'], 'hop_depth': 1, 'merge_confidence': 'high',
            'signals': signals or [sig(name, affiliation, country)], 'current_affiliation': affiliation,
            'country': country, 'role_class': role_class, 'role_confidence': 'high', 'role_evidence': 'rule 1: title',
            'group': group, 'group_evidence': 'rule 1: team page', 'group_link': link, 'tier': 1,
            'notes': 'private note', 'last_verified': '', **extra}


TUM = 'Technical University of Munich'
MEYER = f'Anna Meyer @ {TUM}'
WEISS = 'Jörg Weiß @ University of Amsterdam'


def roster():
    return [
        person('Anna Meyer', TUM, 'DE', 'professor', MEYER, 'team', last_verified='2026-10-14',
               signals=[sig('Anna Meyer', TUM, 'DE', homepage='https://anna.example'),
                        sig('Anna Meyer', TUM, 'DE', signal_type='erc_cog', url='https://erc.example/1', date='2024',
                            channel='funding-eu', role='pi')],
               institution_id='https://openalex.org/I62916508', institution_name=TUM),
        person('Ben Ott', TUM, 'DE', 'phd_student', MEYER, 'team', last_verified='2026-10-15'),
        person('Cara Lin', TUM, 'DE', 'researcher', MEYER, 'project',
               signals=[sig('Cara Lin', TUM, 'DE', signal_type='grant_publication', url='https://doi.org/10.1/c')]),
        person('Dan Roe', 'University of Oslo', 'NO', 'researcher', MEYER, 'coauthor',
               signals=[sig('Dan Roe', 'University of Oslo', 'NO', signal_type='pi_coauthor_publication',
                            url='https://doi.org/10.1/d', topics=['protein folding'], channel='awards-papers')]),
        person('Eve Park', 'ETH Zurich', 'CH', 'researcher', '', ''),
        person('Jörg Weiß', 'University of Amsterdam', 'NL', 'group_leader', WEISS, 'team',
               signals=[sig('Jörg Weiß', 'University of Amsterdam', 'NL', url='https://uva.example/weiss', date='2025-03',
                            homepage='https://weiss.example'),
                        sig('Jörg Weiß', 'University of Amsterdam', 'NL', signal_type='best_paper', url='https://doi.org/10.1/w',
                            date='2027-01-01')]),
    ]


FACETS = [{'id': 'modality', 'label': {'en': 'modality', 'zh': '模态'},
           'tags': [{'id': 'vision-language', 'label': {'en': 'vision-language'}, 'keywords': ['vision-language']},
                    {'id': 'biology', 'label': {'en': 'biology'}, 'keywords': ['protein']}]}]


class NoGeocoder:
    def locate(self, name, country):
        return None


def args(**over):
    ns = argparse.Namespace(date=datetime.date(2026, 10, 15), domain='multimodal AI', region='EU27+UK+CH+NO',
                            window_months=36)
    for key, value in over.items():
        setattr(ns, key, value)
    return ns


def run(persons=None, facets=FACETS):
    return export(roster() if persons is None else persons, args(), NoGeocoder(), facets)


def by_pi(doc):
    return {g['pi']['name']: g for g in doc['groups']}


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def validate(instance, schema, root=None, path='$'):
    """The JSON Schema subset groups.schema.json uses: $ref into $defs, type, enum, pattern, required, properties,
    additionalProperties false, items and minimum. Returns a list of errors."""
    root = root or schema
    if '$ref' in schema:
        schema = root['$defs'][schema['$ref'].rsplit('/', 1)[-1]]
    errors = []
    types = schema.get('type')
    if types:
        names = types if isinstance(types, list) else [types]
        checks = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'null': type(None),
                  'integer': int, 'number': (int, float)}
        if not any(isinstance(instance, checks[n]) and not (n in ('integer', 'number') and isinstance(instance, bool))
                   for n in names):
            return [f'{path}: expected {types}, got {type(instance).__name__}']
    if 'enum' in schema and instance not in schema['enum']:
        errors.append(f'{path}: {instance!r} not in {schema["enum"]}')
    if 'pattern' in schema and isinstance(instance, str) and not re.search(schema['pattern'], instance):
        errors.append(f'{path}: {instance!r} does not match {schema["pattern"]}')
    if 'minimum' in schema and isinstance(instance, (int, float)) and instance < schema['minimum']:
        errors.append(f'{path}: {instance} below {schema["minimum"]}')
    if isinstance(instance, dict):
        errors += [f'{path}: missing {key}' for key in schema.get('required', []) if key not in instance]
        properties = schema.get('properties', {})
        for key, value in instance.items():
            if key in properties:
                errors += validate(value, properties[key], root, f'{path}.{key}')
            elif schema.get('additionalProperties') is False:
                errors.append(f'{path}: unexpected key {key}')
    if isinstance(instance, list) and 'items' in schema:
        for index, item in enumerate(instance):
            errors += validate(item, schema['items'], root, f'{path}[{index}]')
    return errors


class GroupRecordTests(unittest.TestCase):
    def test_one_record_per_group_named_by_pi_institution_and_homepage(self):
        doc = run()
        self.assertEqual(sorted(by_pi(doc)), ['Anna Meyer', 'Jörg Weiß'])
        meyer = by_pi(doc)['Anna Meyer']
        self.assertEqual(meyer['id'], 'anna-meyer-technical-university-of-munich')
        self.assertEqual(by_pi(doc)['Jörg Weiß']['id'], 'jorg-weiss-university-of-amsterdam')
        self.assertEqual(meyer['pi'], {'name': 'Anna Meyer', 'role_class': 'professor', 'homepage': 'https://anna.example'})
        self.assertEqual((meyer['institution']['name'], meyer['institution']['country']), (TUM, 'DE'))
        self.assertEqual(meyer['institution']['ids'], {'openalex': 'https://openalex.org/I62916508'})
        self.assertEqual(meyer['as_of'], '2026-10-15')
        self.assertEqual(doc['meta']['domain'], 'multimodal AI')

    def test_members_are_team_and_project_links_and_coauthors_are_only_counted(self):
        meyer = by_pi(run())['Anna Meyer']
        self.assertEqual(meyer['members'], [{'name': 'Ben Ott', 'role_class': 'phd_student', 'link': 'team'},
                                            {'name': 'Cara Lin', 'role_class': 'researcher', 'link': 'project'}])
        self.assertEqual(meyer['coauthors_count'], 1)
        # Tags come from the PI and members; the coauthor's protein paper says nothing about the group.
        self.assertEqual(meyer['tags'], ['vision-language'])

    def test_homepage_is_the_team_page_two_people_share_else_the_pi_homepage(self):
        doc = run()
        self.assertEqual(by_pi(doc)['Anna Meyer']['homepage'], 'https://lab.example/team')
        self.assertEqual(by_pi(doc)['Jörg Weiß']['homepage'], 'https://weiss.example')

    def test_a_page_read_for_two_members_is_the_team_page_unless_another_group_shares_it(self):
        persons = roster()
        persons[0]['signals'][0]['evidence_url'] = 'https://tum.example/staff'
        for person in persons[:3]:
            person.update(final_pass_url='https://lab.example/people', last_verified='2026-10-15')
        self.assertEqual(by_pi(run(persons))['Anna Meyer']['homepage'], 'https://lab.example/people')
        persons[5]['final_pass_url'] = 'https://lab.example/people'  # a department page lists both groups
        self.assertEqual(by_pi(run(persons))['Anna Meyer']['homepage'], 'https://anna.example')

    def test_the_page_read_for_the_pi_is_the_homepage_unless_it_is_a_news_item(self):
        persons = roster()
        persons[5]['signals'][0].pop('homepage')
        persons[5].update(final_pass_url='https://uva.example/people/weiss', last_verified='2026-10-15')
        self.assertEqual(by_pi(run(persons))['Jörg Weiß']['homepage'], 'https://uva.example/people/weiss')
        for url in ('https://www.uni-saarland.de/aktuell/weiss-erhaelt-medaille-39448.html',
                    'https://www.tu-ilmenau.de/en/news/prof-weiss-in-academy'):
            with self.subTest(url=url):
                persons[5]['final_pass_url'] = url
                weiss = by_pi(run(persons))['Jörg Weiß']
                self.assertEqual((weiss['homepage'], weiss['pi']['homepage']), ('', ''))
                self.assertIn(url, weiss['evidence_urls'])  # still the page that verified the group

    def test_last_verified_is_the_newest_page_read_else_the_newest_record_up_to_as_of(self):
        doc = run()
        meyer, weiss = by_pi(doc)['Anna Meyer'], by_pi(doc)['Jörg Weiß']
        self.assertEqual((meyer['last_verified'], meyer['last_verified_from']), ('2026-10-15', 'final_pass'))
        # The 2027 record lies after the as-of date and does not count.
        self.assertEqual((weiss['last_verified'], weiss['last_verified_from']), ('2025-03', 'record_date'))

    def test_funding_open_source_evidence_and_sources_are_listed(self):
        meyer = by_pi(run())['Anna Meyer']
        self.assertEqual(meyer['active_funding'], [{'type': 'erc_cog', 'date': '2024'}])
        self.assertIn('https://erc.example/1', meyer['evidence_urls'])
        self.assertEqual(meyer['sources'], ['awards-papers', 'funding-de-ch', 'funding-eu'])
        self.assertEqual(meyer['open_source'], [])

    def test_groups_sort_by_institution_then_pi(self):
        doc = run()
        self.assertEqual([g['institution']['name'] for g in doc['groups']], [TUM, 'University of Amsterdam'])


class ExclusionTests(unittest.TestCase):
    def test_no_tier_merge_note_or_evidence_fields_anywhere(self):
        keys = {key for key, _ in walk(run())}
        for banned in ('tier', 'merge_confidence', 'notes', 'role_evidence', 'group_evidence', 'role_confidence'):
            self.assertNotIn(banned, keys)

    def test_a_linkedin_url_in_the_output_stops_the_export(self):
        persons = roster()
        persons[0]['signals'][0]['homepage'] = 'https://de.linkedin.com/in/anna'
        with self.assertRaises(SystemExit) as stop:
            run(persons)
        self.assertIn('linkedin', str(stop.exception))
        self.assertIn('Anna Meyer', str(stop.exception))

    def test_a_linkedin_key_on_an_input_record_stops_the_export(self):
        persons = roster()
        persons[1]['linkedin_headline'] = 'PhD student'
        with self.assertRaises(SystemExit) as stop:
            run(persons)
        self.assertIn('linkedin_headline', str(stop.exception))

    def test_linkedin_data_anywhere_on_a_record_the_map_is_built_from_stops_the_export(self):
        for index, field, value in ((2, 'ids', {'linkedin': 'https://www.linkedin.com/in/cara'}),
                                    (0, 'role_evidence', 'rule 0: final pass | Professor | https://www.linkedin.com/in/anna'),
                                    (3, 'final_pass_url', 'https://uk.linkedin.com/in/dan')):  # a coauthor feeds topics and evidence
            with self.subTest(field=field):
                persons = roster()
                persons[index][field] = value
                with self.assertRaises(SystemExit) as stop:
                    run(persons)
                self.assertIn(persons[index]['name'], str(stop.exception))

    def test_notes_and_people_outside_the_map_do_not_count(self):
        persons = roster()
        persons[0]['notes'] = 'Own page links a LinkedIn profile (https://www.linkedin.com/in/anna), not opened.'
        persons[4]['signals'][0]['homepage'] = 'https://www.linkedin.com/in/eve'  # Eve Park is unattached
        # A namesake of the PI outside the region never reaches the map.
        persons.append(person('Anna Meyer', 'Stanford University', 'US', 'professor', 'Anna Meyer @ Stanford University', 'team',
                              ids={'linkedin': 'https://www.linkedin.com/in/anna-stanford'}))
        self.assertEqual(len(run(persons)['groups']), 2)

    def test_a_linkedin_url_in_the_metadata_stops_the_export(self):
        with self.assertRaises(SystemExit):
            export(roster(), args(domain='https://www.linkedin.com/company/x'), NoGeocoder(), FACETS)

    def test_linkedin_hits_reads_keys_and_url_hosts_only(self):
        self.assertEqual(linkedin_hits({'a': ['https://www.linkedin.com/in/x'], 'linkedin_url': ''}),
                         ['$.a[0]: https://www.linkedin.com/in/x', '$.linkedin_url'])
        self.assertEqual(linkedin_hits({'topics': ['LinkedIn job graph'], 'u': 'https://example.org/linkedin-study'}), [])


class SchemaTests(unittest.TestCase):
    def test_the_export_validates_against_groups_schema(self):
        schema = json.loads((ROOT / 'assets/groups.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(run(), schema), [])
        self.assertEqual(validate(run(facets=[]), schema), [])

    def test_the_validator_rejects_extra_and_missing_fields(self):
        schema = json.loads((ROOT / 'assets/groups.schema.json').read_text(encoding='utf-8'))
        doc = run()
        doc['groups'][0]['tier'] = 1
        del doc['groups'][0]['homepage']
        errors = validate(doc, schema)
        self.assertTrue(any('unexpected key tier' in e for e in errors))
        self.assertTrue(any('missing homepage' in e for e in errors))


class CommandLineTests(unittest.TestCase):
    def test_main_writes_groups_json_into_the_out_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'persons.enriched.jsonl'
            source.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in roster()), encoding='utf-8')
            (Path(tmp) / 'facets.json').write_text(json.dumps({'facets': FACETS}), encoding='utf-8')
            argv = ['group_export.py', str(source), '--domain', 'multimodal AI', '--date', '2026-10-15',
                    '--out', str(Path(tmp) / 'site'), '--offline']
            old, sys.argv = sys.argv, argv
            try:
                group_export.main()
            finally:
                sys.argv = old
            doc = json.loads((Path(tmp) / 'site' / 'groups.json').read_text(encoding='utf-8'))
            self.assertEqual(len(doc['groups']), 2)
            self.assertEqual(doc['meta']['facets'][0]['id'], 'modality')
            # Positions come from the country centroid when nothing else places the institution.
            self.assertEqual(doc['groups'][0]['institution']['location']['source'], 'country centroid')


if __name__ == '__main__':
    unittest.main()
