import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_affiliation as ca
import merge_persons as mp
from publication_signals import author_role, inference_signals, normalize_authorship, work_keys


def paper(role, url='https://doi.org/10.1000/one', **changes):
    return {'kind': 'person', 'name_raw': 'Alex', 'channel': 'awards-papers', 'signal_type': 'paper', 'date': '2025-01',
            'affiliation_raw': 'Example Institute', 'country': 'DE', 'role': role, 'evidence_url': url, **changes}


class AuthorRoleTests(unittest.TestCase):
    def test_position_in_the_full_author_list_outranks_the_recorded_role(self):
        # The regional shortlist put this author first, but the paper lists them last.
        self.assertEqual(author_role(paper('first_author', author_position='last')), 'last_author')
        self.assertEqual(author_role(paper('coauthor', author_position='first')), 'first_author')
        self.assertEqual(author_role(paper('first_author', author_position='middle')), 'coauthor')

    def test_without_a_position_the_recorded_role_stands(self):
        self.assertEqual(author_role(paper('first_author')), 'first_author')
        self.assertEqual(author_role(paper('pi', author_position='')), 'pi')
        self.assertEqual(author_role({'name_raw': 'Alex'}), 'unknown')

    def test_normalize_keeps_the_original_role_only_when_it_changes(self):
        unchanged = paper('first_author', author_position='first')
        self.assertIs(normalize_authorship(unchanged), unchanged)
        changed = normalize_authorship(paper('first_author', author_position='last'))
        self.assertEqual((changed['role'], changed['original_role']), ('last_author', 'first_author'))

    def test_merge_applies_the_position_before_role_inference(self):
        person = mp.to_person([paper('first_author', author_position='last')], set(), 2026)
        self.assertEqual(person['signals'][0]['role'], 'last_author')


class WorkKeyTests(unittest.TestCase):
    def test_doi_arxiv_and_openalex_forms_normalise_to_one_key(self):
        self.assertEqual(work_keys(paper('coauthor', 'https://doi.org/10.1000/One')), {'doi:10.1000/one'})
        self.assertEqual(work_keys(paper('coauthor', 'https://arxiv.org/pdf/2401.01234v2')), {'arxiv:2401.01234'})
        self.assertEqual(work_keys(paper('coauthor', 'arXiv:2401.01234')), {'arxiv:2401.01234'})
        self.assertEqual(work_keys(paper('coauthor', 'https://openalex.org/W123')), {'openalex:w123'})
        # A publication-list page is the evidence for many works, so a bare URL identifies none of them.
        self.assertEqual(work_keys(paper('coauthor', 'https://lab.example/publications/')), set())
        self.assertEqual(work_keys(paper('coauthor', '')), set())


class InferenceSignalTests(unittest.TestCase):
    def test_one_work_seen_through_two_channels_counts_once(self):
        signals = [paper('first_author', 'https://doi.org/10.1000/one'),
                   paper('first_author', 'https://arxiv.org/abs/2401.01234', channel='open-source'),
                   paper('first_author', 'https://doi.org/10.1000/one', channel='funding-eu'),
                   paper('last_author', 'https://doi.org/10.1000/two')]
        roles = [s['role'] for s in inference_signals(signals)]
        self.assertEqual(sorted(roles), ['first_author', 'first_author', 'last_author'])

    def test_conflicting_positions_for_one_work_become_unknown(self):
        signals = [paper('first_author', author_position='first'), paper('coauthor', author_position='middle')]
        self.assertEqual([s['role'] for s in inference_signals(signals)], ['unknown'])

    def test_grants_and_undated_memberships_pass_through_untouched(self):
        grant = {**paper('pi', 'https://erc.example/grant'), 'signal_type': 'erc_stg', 'channel': 'funding-eu'}
        roster = {**paper('team_member', 'https://lab.example/team'), 'signal_type': 'lab_member'}
        self.assertEqual(inference_signals([grant, roster, grant]), [grant, roster, grant])

    def test_role_inference_uses_distinct_works(self):
        # Three copies of one first-author paper must not outvote two genuine last-author papers.
        person = {'first_pub_year': 2010, 'signals': [
            paper('first_author', 'https://doi.org/10.1000/one'), paper('first_author', 'https://doi.org/10.1000/one'),
            paper('first_author', 'https://doi.org/10.1000/one'),
            paper('last_author', 'https://doi.org/10.1000/two'), paper('last_author', 'https://doi.org/10.1000/three')]}
        self.assertEqual(ca.inferred_role(person, 2026)['role_class'], 'group_leader')


if __name__ == '__main__':
    unittest.main()
