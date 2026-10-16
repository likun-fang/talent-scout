import copy
import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from identity_quality import resolve_persons, normalize_id, assert_unique_identities
from merge_persons import cluster, to_person, weak_match
from person_fields import assign_groups
import table_export
import talent_map
from test_talent_map import args, person, sig, FakeGeocoder


def candidate(name='Dieter Büchler', ids=None, affiliation='Example University', **extra):
    return person(name, affiliation, 'DE', 'researcher', name + ' @ ' + affiliation,
                  ids=ids or {}, group_link='team', **extra)


class IdentityGateTests(unittest.TestCase):
    def test_normalize_only_the_correct_provider_host_and_preserve_dblp_paths(self):
        self.assertEqual(normalize_id('orcid', 'https://orcid.org/0000-0002-2493-0101/'), '0000-0002-2493-0101')
        self.assertEqual(normalize_id('openalex', 'https://openalex.org/a5055226918'), 'A5055226918')
        self.assertEqual(normalize_id('orcid', 'https://evil.example/0000-0002-2493-0101'), '')
        self.assertNotEqual(normalize_id('dblp', 'https://dblp.org/pid/12/345.html'),
                            normalize_id('dblp', 'https://dblp.org/pid/67/345.html'))

    def test_identical_identity_merges_evidence_and_preserves_inputs(self):
        a = candidate(ids={'orcid': '0000-0002-2493-0101', 'openalex': 'A5055226918'})
        b = copy.deepcopy(a); b['ids']['openalex'] = 'https://openalex.org/A5055226918'
        b['signals'].append(sig(a['name'], 'Example University', 'DE', url='https://lab.example/other'))
        before = copy.deepcopy([a, b])
        kept, audit = resolve_persons([a, b], [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(kept[0]['signals']), 2)
        self.assertEqual(audit[0]['reason'], 'duplicate_identity_merged')
        self.assertEqual([a, b], before)
        self.assertEqual(resolve_persons(kept, [])[0], kept)

    def test_same_orcid_different_openalex_is_held_not_arbitrarily_merged(self):
        records = [candidate('Jan Peters', {'orcid': '0000-0002-5266-8091', 'openalex': oa}) for oa in ['A1', 'A2']]
        # This tests an unreviewed conflict, independently of the live registry.
        kept, audit = resolve_persons(records, [], identity_reviews=[])
        self.assertEqual(kept, [])
        self.assertEqual(audit[0]['conflicts']['openalex'], ['A1', 'A2'])
        self.assertEqual(audit[0]['records'], records)

    def test_raw_signal_conflicts_cannot_be_hidden_by_empty_canonical_ids(self):
        p = candidate('Jan Peters')
        p['signals'] = [dict(p['signals'][0], ids={'orcid': i}) for i in ['orcid-one', 'orcid-two']]
        kept, audit = resolve_persons([p], [])
        self.assertFalse(kept)
        self.assertEqual(audit[0]['reason'], 'conflicting_provider_ids')

    def test_transitive_id_bridge_is_held_as_a_whole(self):
        records = [candidate(ids={'orcid': '1', 'openalex': 'A1'}), candidate(ids={'orcid': '1'}),
                   candidate(ids={'orcid': '1', 'openalex': 'A2'})]
        self.assertEqual(resolve_persons(records, [])[0], [])
        signals = [dict(p['signals'][0], ids=p['ids']) for p in records]
        self.assertEqual(sorted(len(g) for g in cluster(signals)), [1, 2])
        merged = to_person(signals, set(), 2026)
        self.assertNotIn('openalex', merged['ids'])
        self.assertEqual(merged['identity_status'], 'conflict')

    def test_namesakes_are_not_merged_and_unrelated_names_sharing_id_are_held(self):
        a, b = candidate('Same Name', {'openalex': 'A1'}), candidate('Same Name', {'openalex': 'A2'})
        kept, _ = resolve_persons([a, b], [])
        self.assertEqual(len(kept), 2)
        self.assertNotEqual(kept[0]['entity_id'], kept[1]['entity_id'])
        b['name'] = 'Different Person'; b['ids'] = a['ids']
        self.assertEqual(resolve_persons([a, b], [])[1][0]['reason'], 'strong_id_name_conflict')

    def test_shared_university_word_does_not_merge_people(self):
        self.assertFalse(weak_match({'name_raw': 'A B', 'affiliation_raw': 'Oxford University'},
                                    {'name_raw': 'A B', 'affiliation_raw': 'Cambridge University'}))

    def test_affiliation_conflict_is_held_until_current_source_exists(self):
        a = candidate(ids={'orcid': '1'}, affiliation='Old University')
        b = candidate(ids={'orcid': '1'}, affiliation='New University')
        self.assertEqual(resolve_persons([a, b], [])[1][0]['reason'], 'current_affiliation_conflict')
        b.update(final_pass_affiliation='New University', final_pass_url='https://new.example/people/a', last_verified='2026-10-16')
        kept, _ = resolve_persons([a, b], [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]['current_affiliation'], 'New University')
        self.assertEqual({r['affiliation'] for r in kept[0]['identity_records']}, {'Old University', 'New University'})

    def test_source_hold_uses_publication_not_name_and_keeps_other_evidence(self):
        review = {'doi': '10.67228/30716357/ijmrse-2024pii8t1v', 'reason': 'authorship unresolved',
                  'evidence_urls': ['https://www.jot.fm/issues/issue_2002_09/eulogy/']}
        p = candidate('Kristen Nygaard')
        p['signals'][0]['evidence_url'] = 'https://doi.org/' + review['doi'].upper()
        kept, audit = resolve_persons([p], [review])
        self.assertFalse(kept); self.assertEqual(audit[-1]['reason'], 'no_safe_source')
        p['signals'].append(sig(p['name'], 'Example University', 'DE'))
        kept, audit = resolve_persons([p], [review])
        self.assertEqual(len(kept[0]['signals']), 1)
        self.assertEqual(audit[0]['held_signals'][0]['signal'], p['signals'][0])
        self.assertTrue(resolve_persons([candidate('Kristen Nygaard')], [review])[0])

    def test_deceased_or_unresolved_identity_cannot_enter_roster(self):
        for status in ['deceased', 'conflict', 'pending', 'held']:
            p = candidate(identity_status=status)
            self.assertFalse(table_export.select_persons([p], args())[0])

    def test_both_exporters_deduplicate_and_group_guard_rejects_raw_duplicates(self):
        p = candidate(ids={'openalex': 'A123'})
        records = [p, copy.deepcopy(p)]
        self.assertEqual(len(table_export.select_persons(records, args())[0]), 1)
        data = talent_map.build_data(records, args(), FakeGeocoder({}))
        self.assertEqual(len(data['persons']), 1)
        self.assertEqual(data['groups'][0]['member_count'], 1)
        with self.assertRaises(ValueError):
            table_export.group_row(p['group'], records, datetime.date(2023, 1, 1), datetime.date(2026, 10, 16))

    def test_export_writes_lossless_identity_audit_and_relation_counts(self):
        p = candidate(ids={'openalex': 'A1'})
        with tempfile.TemporaryDirectory() as tmp:
            ns = args(out=str(Path(tmp) / 'roster'), coverage_dir=None)
            table_export.export([p, copy.deepcopy(p)], ns)
            audit = json.loads(Path(tmp, 'roster.identity-audit.json').read_text())
            self.assertEqual(audit[0]['input_records'], 2)
            rel = json.loads(Path(tmp, 'groups.relations.json').read_text())[0]
            self.assertEqual(rel['linked_person_count'], 1)
            self.assertEqual(rel['team_count'], 1)


class GroupAndMapRegressionTests(unittest.TestCase):
    def test_same_name_leaders_keep_their_own_group_institution_and_links(self):
        people = [candidate('Jan Peters', {'openalex': 'A1'}, 'TU Darmstadt'),
                  candidate('Jan Peters', {'openalex': 'A2'}, 'DFKI')]
        data = talent_map.build_data(people, args(), FakeGeocoder({}))
        groups = {g['institution']: g for g in data['groups']}
        self.assertEqual(groups['TU Darmstadt']['institution_key'], 'Technical University of Darmstadt')
        self.assertEqual(groups['DFKI']['institution_key'], 'DFKI')
        self.assertNotEqual(groups['TU Darmstadt']['pi_key'], groups['DFKI']['pi_key'])

    def test_absent_pi_is_not_replaced_by_a_namesake_or_member(self):
        p = candidate('Emma Murphy'); p.update(group='Robert J. Ross @ Example University', group_link='coauthor')
        data = talent_map.build_data([p], args(), FakeGeocoder({}))
        g = data['groups'][0]
        self.assertIsNone(g['pi_key']); self.assertEqual(g['pi_status'], 'not_in_selected_roster')
        self.assertEqual(g['relationship_counts'], {'coauthor': 1})

    def test_oxford_and_cambridge_aliases_share_real_cached_location(self):
        people = [candidate(str(i), affiliation=aff) for i, aff in enumerate([
            'Oxford University', 'University of Oxford', 'Department of Engineering, University of Oxford',
            'Cambridge University', 'University of Cambridge'])]
        geo = FakeGeocoder({'University of Oxford': (51.75222, -1.25596, 'Oxford', 'openalex:I40120149'),
                            'University of Cambridge': (52.2, 0.11667, 'Cambridge', 'openalex:I241749')})
        data = talent_map.build_data(people, args(), geo)
        self.assertEqual(len(data['institutions']), 2)
        self.assertTrue(all(i['geo_source'] != 'country centroid' for i in data['institutions']))
        self.assertEqual(data['persons'][2]['current_affiliation'], people[2]['current_affiliation'])

    def test_shared_company_homepage_does_not_imply_academic_supervision(self):
        lead = candidate('Academic Advisor', affiliation='Sorbonne'); lead.update(role_class='professor', homepage='https://uma.bot/')
        member = candidate('Industry Member', affiliation='UMA'); member['homepage'] = 'https://uma.bot/'
        self.assertNotEqual(assign_groups([lead, member])[1]['group'], 'Academic Advisor @ Sorbonne')

    def test_team_to_coauthor_chain_cannot_be_promoted_to_team(self):
        professor = candidate('Professor'); professor['role_class'] = 'professor'
        professor['signals'] = [dict(professor['signals'][0], signal_type='paper_author', channel='awards-papers', role='last_author', parent='Paper')]
        lead = candidate('Lead'); lead['role_class'] = 'group_leader'
        lead['signals'] = [dict(lead['signals'][0], signal_type='paper_author', channel='awards-papers', role='coauthor', parent='Paper')]
        member = candidate('Member')
        member['signals'] = [dict(member['signals'][0], signal_type='team_member', parent='Lead')]
        result = assign_groups([professor, lead, member])
        self.assertEqual(result[2]['group_link'], 'team')
        self.assertTrue(result[2]['group'].startswith('Lead @ '))
        self.assertIn('coauthor chain stopped', result[2]['group_evidence'])


if __name__ == '__main__':
    unittest.main()
