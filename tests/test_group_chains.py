import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from person_fields import assign_groups, domain_link, institution_names, institution_name

X = 'Example University'


def person(name, affiliation, role_class, signals, **fields):
    return {'name': name, 'current_affiliation': affiliation, 'role_class': role_class,
            'signals': [{'name_raw': name, 'affiliation_raw': affiliation, 'channel': 'funding-eu', 'date': '2025-05',
                         **s} for s in signals], **fields}


def grouped(people):
    return {p['name']: p for p in assign_groups(people)}


class LeaderChainTests(unittest.TestCase):
    def setUp(self):
        self.professor = person('Anna Prof', X, 'professor',
                                [{'signal_type': 'erc_adg', 'role': 'pi', 'parent': 'GRANT-1', 'evidence_url': 'https://erc.example/1'}])

    def test_a_coauthor_keeps_the_direct_association_when_the_leader_belongs_to_another_group(self):
        lead = person('Ben Lead', X, 'group_leader',
                      [{'signal_type': 'lab_member', 'role': 'team_member', 'parent': 'Anna Prof', 'evidence_url': 'https://lab.example/team'}])
        coauthor = person('Cara Co', X, 'unknown',
                          [{'signal_type': 'pi_coauthor_publication', 'role': 'coauthor', 'parent': 'Ben Lead',
                            'evidence_url': 'https://doi.org/10.1000/co'}])
        result = grouped([self.professor, lead, coauthor])
        self.assertEqual(result['Ben Lead']['group'], f'Anna Prof @ {X}')
        # Sharing a paper with Ben does not place Cara in Anna's team.
        self.assertEqual((result['Cara Co']['group'], result['Cara Co']['group_link']), (f'Ben Lead @ {X}', 'coauthor'))
        self.assertIn('coauthor chain stopped at direct association', result['Cara Co']['group_evidence'])

    def test_a_chain_through_a_project_link_keeps_project_as_its_relation(self):
        lead = person('Ben Lead', X, 'group_leader',
                      [{'signal_type': 'grant_publication', 'role': 'last_author', 'parent': 'GRANT-1',
                        'evidence_url': 'https://doi.org/10.1000/grant'}])
        member = person('Dan Member', X, 'phd_student',
                        [{'signal_type': 'lab_member', 'role': 'team_member', 'parent': 'Ben Lead', 'evidence_url': 'https://lab.example/ben'}])
        result = grouped([self.professor, lead, member])
        self.assertEqual((result['Ben Lead']['group'], result['Ben Lead']['group_link']), (f'Anna Prof @ {X}', 'project'))
        # Dan is on Ben's team; Ben works on Anna's grant. Dan reaches Anna's group only through that project.
        self.assertEqual((result['Dan Member']['group'], result['Dan Member']['group_link']), (f'Anna Prof @ {X}', 'project'))
        self.assertIn('via Ben Lead', result['Dan Member']['group_evidence'])


class HostLinkTests(unittest.TestCase):
    def leader(self, affiliation):
        return person('Anna Prof', affiliation, 'professor', [{'role': 'pi', 'evidence_url': 'https://erc.example/1'}],
                      homepage='https://vision-lab.org/anna')

    def member(self, affiliation):
        return person('Eve Member', affiliation, 'unknown', [{'role': 'unknown'}], homepage='https://vision-lab.org/eve')

    def test_a_shared_host_links_only_people_of_one_employer(self):
        self.assertTrue(domain_link(self.member(X), self.leader(X)).startswith('homepage host vision-lab.org'))
        # A company or consortium site hosts pages for several employers' staff.
        self.assertEqual(domain_link(self.member('Other University'), self.leader(X)), '')
        self.assertEqual(grouped([self.leader(X), self.member('Other University')])['Eve Member']['group'], '')


class CommaSegmentTests(unittest.TestCase):
    def test_a_known_short_alias_counts_as_an_institution_in_any_comma_segment(self):
        kit = institution_name('Karlsruhe Institute of Technology')
        self.assertIn(kit, institution_names('Chair of Robotics, KIT, Karlsruhe')[0])
        self.assertIn(institution_name('Technical University of Munich'), institution_names('Computer Vision Group, TUM')[0])
        # An unknown short token in the middle stays a unit or city name.
        self.assertNotIn('xyz', institution_names('Chair of Robotics, XYZ, Karlsruhe')[0])

    def test_new_aliases_fold_to_their_canonical_names(self):
        for alias, canonical in [('Oxford University', 'University of Oxford'), ('Cambridge University', 'University of Cambridge'),
                                 ('Lappeenranta University of Technology', 'LUT University'), ('TU Ilmenau', 'Technische Universität Ilmenau'),
                                 ('Universität Stuttgart', 'University of Stuttgart')]:
            self.assertEqual(institution_names(alias)[0], {institution_name(canonical)}, alias)


if __name__ == '__main__':
    unittest.main()
