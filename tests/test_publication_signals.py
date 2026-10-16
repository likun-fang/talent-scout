import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from publication_signals import author_role, publication_signal, inference_signals
from current_affiliation import inferred_role


class PublicationSignalTests(unittest.TestCase):
    def test_filtered_list_never_changes_original_author_position(self):
        self.assertEqual(author_role({'name': 'Only European author', 'position': 'middle'}), 'coauthor')
        self.assertEqual(author_role({'name': 'Only verified author'}), 'unknown')
        self.assertEqual(publication_signal({'name': 'Last', 'position': 'last'}, {})['role'], 'last_author')

    def test_merge_uses_shared_position_contract_without_mutating_raw_signal(self):
        from merge_persons import to_person
        signal = publication_signal({'name': 'Last', 'position': 'last', 'ids': {'openalex': 'A42'}}, {},
            channel='awards-papers', hop_depth=1, signal_type='research_publication',
            evidence_url='https://arxiv.org/abs/2606.20104')
        signal['role'] = 'coauthor'  # old adapter error, original position survives
        p = to_person([signal], set(), 2026, identity_reviews=[])
        self.assertEqual(p['signals'][0]['role'], 'last_author')
        self.assertEqual(p['signals'][0]['original_role'], 'coauthor')
        self.assertEqual(signal['role'], 'coauthor')

    def test_duplicate_work_urls_do_not_dilute_explicit_position(self):
        signals = [{'signal_type': 'research_publication', 'role': 'last_author', 'author_position': 'last',
                    'evidence_url': 'https://arxiv.org/abs/2606.20104v2'},
                   {'signal_type': 'paper_author', 'role': 'coauthor',
                    'evidence_url': 'https://doi.org/10.48550/arXiv.2606.20104'}]
        before = copy.deepcopy(signals)
        self.assertEqual(len(inference_signals(signals)), 1)
        self.assertEqual(inferred_role({'first_pub_year': 1989, 'signals': signals}, 2026)['role_class'], 'group_leader')
        self.assertEqual(signals, before)

    def test_conflicting_positions_do_not_silently_choose_last(self):
        a = {'publication': {}, 'signal_type': 'paper_author', 'role': 'coauthor', 'author_position': 'last',
             'evidence_url': 'https://arxiv.org/abs/2606.20104'}
        b = {**a, 'author_position': 'first'}
        self.assertEqual(inference_signals([a, b])[0]['role'], 'unknown')

    def test_legacy_model_author_duplicates_cannot_create_student_inference(self):
        canonical = {'signal_type': 'research_publication', 'role': 'last_author', 'author_position': 'last',
                     'evidence_url': 'https://arxiv.org/abs/2606.20104'}
        legacy = {'signal_type': 'model_paper_author', 'role': 'first_author',
                  'evidence_url': 'https://doi.org/10.48550/arXiv.2606.20104'}
        signals = [canonical, *[dict(legacy) for _ in range(3)]]
        self.assertEqual(len(inference_signals(signals)), 1)
        self.assertEqual(inference_signals(signals)[0]['role'], 'last_author')
        self.assertEqual(inferred_role({'first_pub_year': 2024, 'signals': signals}, 2026)['role_class'], 'unknown')

    def test_distinct_papers_are_not_deduplicated_by_title(self):
        a = {'signal_type': 'paper_author', 'parent': 'Same Title', 'role': 'last_author', 'evidence_url': 'https://a.example/1'}
        b = {**a, 'evidence_url': 'https://a.example/2'}
        self.assertEqual(len(inference_signals([a,b])), 2)

    def test_doi_alias_bridge_is_order_independent(self):
        from itertools import permutations
        a = {'signal_type': 'paper_author', 'role': 'last_author', 'evidence_url': 'https://doi.org/10.1234/paper'}
        b = {**a, 'evidence_url': 'https://arxiv.org/abs/2606.20104'}
        bridge = {**a, 'publication': {'doi': '10.1234/paper', 'url': b['evidence_url']}}
        for values in permutations([a, b, bridge]):
            self.assertEqual(len(inference_signals(list(values))), 1)
