"""Evidence-level recovery must preserve recall without inventing identity proof."""
import copy
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_identity_quality import candidate
from test_talent_map import args, sig, FakeGeocoder
from test_research_topics import paper, person, args as topic_args, START, END, POLICY
from identity_quality import resolve_persons, validate_identity_reviews, reference_leaders
from merge_persons import cluster, to_person
from person_fields import same_institution, facet_texts
from research_topics import publication_problem
from current_affiliation import enrich
import table_export
import talent_map


def review(**overrides):
    return {'entity_id': 'reviewed-ada', 'names': ['Ada Example'],
            'canonical_ids': {'orcid': '0000-0001-1111-1111', 'openalex': 'A1'},
            'id_aliases': {'openalex': ['A2']},
            'evidence': [{'url': 'https://university.example/ada',
                          'quote': 'Ada Example links ORCID O1 and the reviewed author profiles A1 and A2.',
                          'reviewed_on': '2026-10-01'}], **overrides}


def publication(topic='vla', oa='A1', orcid='0000-0001-1111-1111'):
    s = paper(topic)
    s['ids'] = {'openalex': oa, 'orcid': orcid}
    s['publication']['author_ids'] = s['ids'].copy()
    return s


def reviewed_professor(signals):
    return person(signals, ids={'orcid': '0000-0001-1111-1111', 'openalex': 'A1'},
                  final_pass_affiliation='Example University', final_pass_title='Professor',
                  final_pass_country='DE', final_pass_url='https://university.example/ada',
                  last_verified='2026-10-01')


def held_leader():
    p = reviewed_professor([publication(), publication('vlm', oa='A9')])
    p['review_evidence'] = [{'name': p['name'], 'status': 'verified',
                            'final_pass_url': p['final_pass_url'], 'last_verified': p['last_verified'],
                            'final_pass_affiliation': p['final_pass_affiliation'],
                            'excerpt': 'Ada Example is a Professor at Example University.'}]
    return p


class ReviewedIdentityTests(unittest.TestCase):
    def test_ledger_requires_evidence_and_rejects_conflicting_ownership(self):
        for change in [{'evidence': []}, {'canonical_ids': {}}, {'id_aliases': {'github': ['ada']}},
                       {'evidence': [{'url': 'https://u.example', 'quote': 'identity', 'reviewed_on': 'yesterday'}]},
                       {'signal_reviews': [{'decision': 'accept', 'evidence_url': 'https://p.example'}]}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_identity_reviews([review(**change)])
        with self.assertRaises(ValueError):
            validate_identity_reviews([review(), review(entity_id='someone-else')])

    def test_upstream_and_final_gate_share_reviewed_aliases_without_rewriting_raw_sources(self):
        signals = [publication(oa='A1'), publication('vlm', oa='A2')]
        before = copy.deepcopy(signals)
        self.assertEqual(len(cluster(signals, identity_reviews=[])), 2)
        groups = cluster(signals, identity_reviews=[review()])
        self.assertEqual(len(groups), 1)
        p = to_person(groups[0], set(), 2026, identity_reviews=[review()])
        p.update(current_affiliation='Example University', country='DE')
        kept, _ = resolve_persons([p], [], [review()])
        self.assertEqual(kept[0]['ids']['openalex'], 'A1')
        self.assertEqual(kept[0]['signals'], before)
        self.assertEqual(signals, before)
        self.assertEqual(kept[0]['entity_id'], 'reviewed-ada')
        self.assertEqual(resolve_persons(kept, [], [review()])[0], kept)

    def test_review_bridges_funding_and_paper_ids_but_keeps_current_affiliation_check(self):
        r = review(canonical_ids={'orcid': '0000-0001-1111-1111', 'openalex': 'A1', 'gepris': 'G1'})
        a = candidate('Ada Example', {'gepris': 'G1'})
        b = candidate('Ada Example', {'orcid': '0000-0001-1111-1111'}, final_pass_url='https://u.example/ada',
                      last_verified='2026-10-01', final_pass_affiliation='Example University')
        for p in (a, b):
            p['signals'][0]['ids'] = p['ids'].copy()
        kept, _ = resolve_persons([a, b], [], [r])
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(kept[0]['signals']), 2)
        self.assertEqual(kept[0]['ids']['gepris'], 'g1')

    def test_bad_source_is_quarantined_without_losing_good_person_or_safe_topic(self):
        good, bad = publication(), publication('vlm', oa='A9', orcid='0000-0009-9999-9999')
        p = reviewed_professor([good, bad]); original = copy.deepcopy(p)
        p['topics'] = ['VLM contaminated topic']; p['topic_papers'] = [bad['publication']]
        with patch('identity_quality.load_identity_reviews', return_value=[review()]):
            selected = table_export.select_persons([p], topic_args())[0]
            data = talent_map.build_data([p], topic_args(), FakeGeocoder({}))
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['display_topics'], ['VLA'])
        self.assertEqual(data['persons'][0]['topics'], ['VLA'])
        self.assertEqual(data['persons'][0]['signals'][0]['evidence_url'], good['evidence_url'])
        self.assertEqual(selected[0]['identity_status'], 'reviewed_with_held_sources')
        self.assertNotIn(bad['publication']['title'], ' '.join(sum(facet_texts(selected[0]), [])))
        self.assertEqual(p['signals'], original['signals'])
        _, audit = resolve_persons([p], [], [review()])
        held = next(a for a in audit if a['reason'] == 'identity_sources_quarantined')
        self.assertEqual(held['held_signals'][0]['signal'], bad)

    def test_explicit_source_review_can_fix_binding_without_discarding_valid_paper(self):
        bad = publication(oa='A9')
        r = review(signal_reviews=[{'evidence_url': bad['evidence_url'], 'decision': 'accept',
                                    'reason': 'Original author list and profile prove attribution; provider ID is wrong.',
                                    'evidence_refs': [0]}])
        p = reviewed_professor([bad])
        kept, audit = resolve_persons([p], [], [r])
        repaired = kept[0]['signals'][0]
        self.assertEqual(repaired['publication']['author_ids']['openalex'], 'A1')
        self.assertEqual(p['signals'][0]['ids']['openalex'], 'A9')
        event = next(a for a in audit if a['reason'] == 'source_provider_bindings_corrected')
        self.assertEqual(event['corrections'][0]['signal'], bad)
        self.assertIsNone(publication_problem(kept[0], repaired, START, END, POLICY))
        # A general identity review alone cannot make that same correction.
        without_source_review, _ = resolve_persons([p], [], [review()])
        self.assertEqual(without_source_review[0]['signals'], [])

    def test_reviewed_author_alias_qualifies_without_rewriting_original_paper_id(self):
        p = reviewed_professor([publication(oa='A2')])
        kept, _ = resolve_persons([p], [], [review()])
        signal = kept[0]['signals'][0]
        self.assertEqual(signal['publication']['author_ids']['openalex'], 'A2')
        self.assertIsNone(publication_problem(kept[0], signal, START, END, POLICY))

    def test_source_rejection_wins_even_with_good_ids(self):
        s = publication()
        r = review(signal_reviews=[{'evidence_url': s['evidence_url'], 'decision': 'reject',
                                    'reason': 'Author list does not support this attribution', 'evidence_refs': [0]}])
        kept, audit = resolve_persons([reviewed_professor([s])], [], [r])
        self.assertEqual(kept[0]['signals'], [])
        self.assertEqual(audit[-1]['held_signals'][0]['reason'], 'source_rejected_by_identity_review')

    def test_no_profile_or_review_bypasses_recent_professor_paper_requirement(self):
        p = reviewed_professor([publication(oa='A9')])
        with patch('identity_quality.load_identity_reviews', return_value=[review()]):
            self.assertFalse(table_export.select_persons([p], topic_args())[0])
        s = publication(); s['date'] = s['publication']['date'] = '2018-01-01'
        with patch('identity_quality.load_identity_reviews', return_value=[review()]):
            self.assertFalse(table_export.select_persons([reviewed_professor([s])], topic_args())[0])

    def test_wrong_author_name_or_explicit_hold_cannot_be_overridden(self):
        p = reviewed_professor([publication()]); p['signals'][0]['publication']['author_name'] = 'Another Person'
        self.assertFalse(resolve_persons([p], [], [review()])[0][0]['signals'])
        for status in ['pending', 'held', 'deceased']:
            p['identity_status'] = status
            self.assertFalse(resolve_persons([p], [], [review()])[0])

    def test_ambiguous_idless_bridge_does_not_choose_first_person(self):
        ss = [dict(sig('Ada Example', 'Example University', 'DE'), ids=ids)
              for ids in [{'openalex': 'A1'}, {}, {'openalex': 'A2'}]]
        for ordering in itertools.permutations(ss):
            self.assertEqual(len(cluster(list(ordering), identity_reviews=[])), 3)

    def test_same_name_review_status_is_separate_from_source_merge_confidence(self):
        ps = [candidate('Ada Example', {'openalex': key}) for key in ['A1', 'A2']]
        data = talent_map.build_data(ps, args(), FakeGeocoder({}))
        self.assertEqual(len(data['persons']), 2)
        self.assertTrue(all(p['identity_status'] == 'needs_review' for p in data['persons']))
        self.assertTrue(all('Identity status: needs_review' in p['notes'] for p in data['persons']))

    def test_ledger_without_matching_identity_does_not_change_other_domain_records(self):
        p = candidate('Different Researcher', {'openalex': 'A99'})
        before = resolve_persons([p], [], [])[0]
        after = resolve_persons([p], [], [review()])[0]
        self.assertEqual(before, after)

    def test_corrected_top_level_id_cannot_keep_the_wrong_profile_location(self):
        p = person([publication()], role='researcher', ids={'openalex': 'A9'},
                   current_affiliation='Wrong Employer', country='DE', first_pub_year=1990)
        kept, audit = resolve_persons([p], [], [review()])
        self.assertTrue(kept[0]['identity_reenrichment_required'])
        self.assertNotIn('first_pub_year', kept[0])
        self.assertEqual(table_export.country_for(kept[0]), '')
        self.assertNotIn('Wrong Employer', kept[0].get('current_affiliation', ''))
        self.assertTrue(any(a['reason'] == 'identity_reenrichment_required' for a in audit))
        with patch('identity_quality.load_identity_reviews', return_value=[review()]):
            self.assertFalse(table_export.select_persons([p], args())[0])

    def test_reenrichment_hold_clears_only_after_successful_profile_lookup(self):
        p = person([publication()], role='researcher', ids={'openalex': 'A1'}, identity_reenrichment_required=True)
        with patch('current_affiliation.openalex_current', return_value=None), patch('current_affiliation.first_publication_year', return_value=None):
            self.assertTrue(enrich(p, {'DE'}, run_year=2026)['identity_reenrichment_required'])
        with patch('current_affiliation.openalex_current', return_value=('Example University', 'DE', '2026-10-01', 'education', 'I1')), patch('current_affiliation.first_publication_year', return_value=2020):
            result = enrich(p, {'DE'}, run_year=2026)
            self.assertNotIn('identity_reenrichment_required', result)
            self.assertEqual(result['current_affiliation'], 'Example University')

    def test_registry_cannot_merge_conflicting_current_employers_without_current_evidence(self):
        ps = [candidate('Ada Example', {'openalex': oa}, affiliation=aff)
              for oa, aff in [('A1', 'First University'), ('A2', 'Second University')]]
        for p in ps:
            p['signals'][0]['ids'] = p['ids'].copy()
        kept, audit = resolve_persons(ps, [], [review()])
        self.assertFalse(kept)
        self.assertEqual(audit[-1]['reason'], 'current_affiliation_conflict')

    def test_two_reviewed_namesakes_remain_separate_without_false_pending_warning(self):
        other = review(entity_id='another-ada', canonical_ids={'openalex': 'A3'}, id_aliases={})
        ps = [candidate('Ada Example', {'openalex': oa}) for oa in ['A1', 'A3']]
        for p in ps:
            p['signals'][0]['ids'] = p['ids'].copy()
        kept, audit = resolve_persons(ps, [], [review(), other])
        self.assertEqual({p['entity_id'] for p in kept}, {'reviewed-ada', 'another-ada'})
        self.assertTrue(all(p['identity_status'] == 'reviewed' for p in kept))
        self.assertFalse(any(a['reason'] == 'same_name_requires_review' for a in audit))

    def test_unreviewed_other_provider_ids_do_not_become_aliases_or_veto_verified_identity(self):
        r = review(canonical_ids={'orcid': '0000-0001-1111-1111'}, id_aliases={})
        p = reviewed_professor([publication(oa='A1'), publication('vlm', oa='A2')])
        with patch('identity_quality.load_identity_reviews', return_value=[r]):
            selected = table_export.select_persons([p], topic_args())[0]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['ids'], r['canonical_ids'])
        self.assertEqual(selected[0]['identity_status'], 'reviewed_with_pending_ids')
        self.assertEqual(set(selected[0]['display_topics']), {'VLA', 'VLM'})
        _, audit = resolve_persons([p], [], [r])
        warning = next(a for a in audit if a['reason'] == 'unreviewed_provider_annotations')
        self.assertEqual(warning['provider_ids']['openalex'], ['A1', 'A2'])
        merged = to_person(p['signals'], set(), 2026, identity_reviews=[r])
        self.assertEqual(merged['ids'], r['canonical_ids'])

    def test_merge_quarantines_bad_source_before_enrichment_uses_affiliation(self):
        good, bad = publication(), publication('vlm', oa='A9')
        good['affiliation_raw'] = 'Example University'
        bad['affiliation_raw'] = 'Wrong Employer'; bad['date'] = '2026-10-01'
        merged = to_person([good, bad], set(), 2026, identity_reviews=[review()])
        self.assertEqual(merged['signals'], [good])
        self.assertEqual(merged['identity_held_sources'][0]['signal'], bad)
        self.assertEqual(merged['ids'], review()['canonical_ids'])


class IndependentGroupEvidenceTests(unittest.TestCase):
    def test_verified_reference_preserves_direct_team_without_counting_held_pi(self):
        leader = held_leader(); member = candidate('Student')
        member['signals'] = [sig('Student', 'Example University', 'DE', parent=leader['name'])]
        selected = table_export.select_persons([leader, member], args())[0]
        self.assertEqual([p['name'] for p in selected], ['Student'])
        self.assertEqual(selected[0]['group'], 'Ada Example @ Example University')
        self.assertEqual(selected[0]['group_link'], 'team')
        data = talent_map.build_data([leader, member], args(), FakeGeocoder({}))
        self.assertEqual(data['groups'][0]['member_count'], 1)
        self.assertIsNone(data['groups'][0]['pi_key'])
        self.assertEqual(data['groups'][0]['leader_reference']['url'], leader['final_pass_url'])
        with tempfile.TemporaryDirectory() as tmp:
            table_export.export([leader, member], args(out=str(Path(tmp)/'roster'), coverage_dir=None))
            relations = json.loads(Path(tmp, 'groups.relations.json').read_text())
            self.assertFalse(relations[0]['leader_in_selected_roster'])
            self.assertIsNotNone(relations[0]['leader_reference'])

    def test_disputed_paper_cannot_restore_coauthor_relation(self):
        leader = held_leader()
        for s in leader['signals']:
            s['parent'] = 'Disputed Paper'; s['role'] = 'last_author'
        member = candidate('Collaborator'); member['signals'] = [dict(
            sig('Collaborator', 'Example University', 'DE', signal_type='paper_author', parent='Disputed Paper'),
            channel='awards-papers', role='coauthor')]
        selected = table_export.select_persons([leader, member], args())[0]
        self.assertEqual(selected[0]['group'], '')

    def test_profile_url_alone_or_conflicting_employer_cannot_create_reference(self):
        p = held_leader(); p.pop('review_evidence')
        kept, audit = resolve_persons([p], [], [])
        self.assertFalse(reference_leaders(audit, kept))
        p = held_leader(); p['review_evidence'][0]['final_pass_affiliation'] = 'Another University'
        kept, audit = resolve_persons([p], [], [])
        self.assertFalse(reference_leaders(audit, kept))

    def test_abbreviated_university_inside_department_affiliation_matches_without_city_bridge(self):
        for left, right in [
            ('U Lappeenranta of Technology, Department of Mechanical Engineering, FIN', 'LUT University'),
            ('Ilmenau TU, Institute of Mathematics', 'Technische Universität Ilmenau'),
            ('Stuttgart U, Institute of Engineering and Computational Mechanics', 'University of Stuttgart')]:
            self.assertTrue(same_institution(left, right))
        self.assertFalse(same_institution('MPI-IS, Tübingen', 'University of Tübingen, Tübingen'))


if __name__ == '__main__':
    unittest.main()
