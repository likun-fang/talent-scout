import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_affiliation as ca


def read(title, affiliation, country='DE', **fields):
    """A person whose page the final pass read; a recent first-author paper would otherwise infer phd_student."""
    person = {'name': 'Alex', 'final_pass_title': title, 'final_pass_affiliation': affiliation, 'final_pass_country': country,
              'final_pass_url': 'https://example.org/page', 'last_verified': '2026-10-15', 'first_pub_year': 2025,
              'signals': [{'name_raw': 'Alex', 'affiliation_raw': affiliation, 'channel': 'awards-papers', 'date': '2025-06',
                           'role': 'first_author', 'evidence_url': 'https://doi.org/10.1000/x'}], **fields}
    return ca.classify_role(person, 2026)


class ReadTitleStopsInferenceTests(unittest.TestCase):
    def test_a_title_outside_the_table_is_unknown_not_inferred(self):
        for title in ("Master’s Student", 'Informatics MSc student', 'Guest Scientist', 'Invited guest, Data Science Laboratory',
                      'Project Member', 'Student, Section of Communication Systems - Master Project autumn'):
            with self.subTest(title=title):
                result = read(title, 'ETH Zürich', 'CH')
                self.assertEqual((result['role_class'], result['role_confidence']), ('unknown', 'low'))
                self.assertIn('rule 0: final pass: title not in the title table', result['role_evidence'])
                self.assertIn(title, result['role_evidence'])

    def test_inference_still_runs_without_a_read_title(self):
        person = {'name': 'Alex', 'first_pub_year': 2025, 'signals': [{'role': 'first_author', 'evidence_url': 'https://doi.org/10.1000/x'}]}
        self.assertEqual(ca.classify_role(person, 2026)['role_class'], 'phd_student')

    def test_signal_titles_and_funding_still_win_over_an_unmatched_read_title(self):
        scholars = read('Scholars', '', None, signals=[{'name_raw': 'Alex', 'role_title': 'Scholars', 'parent': 'IMPRS-IS Scholars',
                                                       'affiliation_raw': 'MPI for Intelligent Systems', 'date': '2025-06',
                                                       'evidence_url': 'https://imprs.is.mpg.de/scholars'}])
        self.assertEqual((scholars['role_class'], scholars['role_evidence'][:6]), ('phd_student', 'rule 1'))
        grant = read('Academic staff', 'Ghent University', 'BE', signals=[{'signal_type': 'erc_stg', 'role': 'pi', 'date': '2025-01',
                                                                           'evidence_url': 'https://erc.example/1'}])
        self.assertEqual((grant['role_class'], grant['role_evidence'][:6]), ('group_leader', 'rule 2'))


class ProfessorialTitleTests(unittest.TestCase):
    def test_ius_promovendi_is_a_right_to_supervise(self):
        result = read('Associate Professor with Ius Promovendi', 'University of Groningen, Faculty of Economics', 'NL')
        self.assertEqual(result['role_class'], 'professor')
        self.assertEqual(ca.title_class('Promovendus'), 'phd_student')

    def test_professorship_beats_a_founder_signal_and_profesor_spelling_counts(self):
        result = read('Professorship Visual Computing and Artificial Intelligence', 'Technical University of Munich',
                      signals=[{'name_raw': 'Alex', 'role_title': 'Co-Founder', 'affiliation_raw': 'Synthesia', 'date': '2025-06',
                                'evidence_url': 'https://synthesia.example/team'}])
        self.assertEqual((result['role_class'], result['role_evidence'][:6]), ('professor', 'rule 0'))
        self.assertEqual(read('associate profesor', 'University of Zaragoza', 'ES')['role_class'], 'professor')

    def test_swedish_and_french_permanent_faculty_ranks_are_professor(self):
        for title, affiliation, country in (('Universitetslektor', 'KTH', 'SE'), ('Forskare, Universitetslektor, bitr', 'KTH', 'SE'),
                                            ('Maître de conférences (HDR)', 'Université Lumière Lyon 2', 'FR'),
                                            ('Maitre de Conférences', 'INSA Rouen Normandie', 'FR')):
            with self.subTest(title=title):
                self.assertEqual(read(title, affiliation, country)['role_class'], 'professor')
        for title in ('Biträdande universitetslektor', 'Biträdande lektor', 'Lecturer', 'Chargé de recherche'):
            with self.subTest(title=title):
                self.assertEqual(read(title, 'KTH', 'SE')['role_class'], 'researcher')


class FrenchResearchPostTests(unittest.TestCase):
    def test_directeur_de_recherche_is_the_research_track_professor(self):
        for title, affiliation in (('Directrice de recherche', 'Inria Saclay'), ('Directeur de recherche CNRS', 'CNRS'),
                                   ('research director (DR1)', 'IGN'), ('Research Director DR1', 'INRIA'),
                                   ('Senior Researcher (DR2)', 'Inria'), ('Research Director, DRCE', 'CNRS'),
                                   ('Research Director - DR1', 'CNRS'), ('Senior Researcher (CNRS DR2)', 'CNRS'),
                                   ('Senior Researcher\n(DR2)', 'CNRS'),
                                   ('Senior researcher (Directrice de recherche)', 'CNRS')):
            with self.subTest(title=title):
                self.assertEqual(read(title, affiliation, 'FR')['role_class'], 'professor')

    def test_other_permanent_posts_are_researchers_and_a_bare_research_director_decides_nothing(self):
        for title in ('Chercheur Titulaire', 'Chercheuse titulaire', 'Chargée de recherche',
                      'Research fellow (Chargé de recherche)', 'Senior Researcher'):
            with self.subTest(title=title):
                self.assertEqual(read(title, 'GIPSA-lab', 'FR')['role_class'], 'researcher')
        for title in ('Research Director', 'Junior research director'):
            with self.subTest(title=title):
                self.assertEqual(read(title, 'IGN', 'FR')['role_class'], 'unknown')


class LabManagerTests(unittest.TestCase):
    def test_a_lab_manager_at_an_academic_employer_leads_the_lab_with_a_caveat(self):
        for title, affiliation in (('Lab Manager', 'University of Hamburg'), ('Laboratory Manager', 'Inria Lyon'),
                                   ('Lab Head', 'Max Planck Institute for Intelligent Systems'),
                                   ('Lab Head AI, PostDoc', 'TUM Klinikum Rechts der Isar, Klinik für RadioOnkologie'),
                                   ('Lab Head AI, PostDoc', 'TUM Klinikum Rechts der Isar'),
                                   ('Lab Manager (ancien responsable d’équipe)', 'CNRS')):
            with self.subTest(title=title):
                result = read(title, affiliation)
                self.assertEqual(result['role_class'], 'group_leader')
                self.assertIn('(lab manager: may be administrative)', result['role_evidence'])

    def test_a_lab_manager_elsewhere_decides_nothing(self):
        for affiliation in ('Synthesia', ''):
            with self.subTest(affiliation=affiliation):
                self.assertEqual(read('Lab Manager', affiliation, 'GB')['role_class'], 'unknown')
        # The caveat belongs to the lab-manager reading only, not to another leadership title or a supervisor's.
        for title in ('Professor and Lab Manager', 'Group Leader and Lab Manager',
                      'Group Leader in the lab of Lab Manager Jane Doe'):
            with self.subTest(title=title):
                self.assertNotIn('may be administrative', read(title, 'University of Hamburg')['role_evidence'])


class EngineerTests(unittest.TestCase):
    def test_an_engineer_at_a_non_academic_employer_is_industry(self):
        for title, affiliation, country in (('AI Engineer', 'TKH AI Technology', None), ('CV Engineer', 'DeepScenario', 'DE'),
                                            ('Software Engineer', 'Palantir Technologies (London)', 'GB'),
                                            ('computer vision/ML engineer', 'Hexagon', None),
                                            ('Principal Machine Learning Engineer', 'IXI Eyewear', 'FI')):
            with self.subTest(title=title):
                result = read(title, affiliation, country, institution_type='education')  # provider type is often wrong here
                self.assertEqual(result['role_class'], 'industry')
                self.assertIn('engineer at a non-academic employer', result['role_evidence'])

    def test_research_engineers_at_academic_employers_are_researchers(self):
        for title, affiliation in (('Research Engineer', 'Max Planck Institute for Intelligent Systems'),
                                   ('RESEARCH ENGINEER', 'Barcelona Supercomputing Center'),
                                   ('Research Engineers', 'Barcelona Supercomputing Center (BSC)'),
                                   ('JUNIOR RESEARCH ENGINEER', 'BSC-CNS, AI Institute - Single and Multi Agent Systems')):
            with self.subTest(title=title):
                self.assertEqual(read(title, affiliation, 'ES')['role_class'], 'researcher')
        # An engineer whose employer is unknown is not guessed.
        self.assertEqual(read('Software Engineer', '', None)['role_class'], 'unknown')
        self.assertEqual(read('Research Engineer', 'Hugging Face', 'FR')['role_class'], 'industry')


class GroupLeaderSpellingTests(unittest.TestCase):
    def test_group_manager_and_heads_the_division(self):
        self.assertEqual(read('Group Manager Perceptual User Interfaces', 'Fraunhofer IOSB')['role_class'], 'group_leader')
        self.assertEqual(read('heads the division of Artificial Material Intelligence at the Institute of Energy Technologies',
                              'Forschungszentrum Jülich, Institute of Energy Technologies')['role_class'], 'group_leader')


class UnchangedTests(unittest.TestCase):
    def test_existing_decisions_hold(self):
        mixed = read('PhD candidate / Guest', 'Leiden University', 'NL')
        self.assertEqual((mixed['role_class'], 'mixed heading proves membership only' in mixed['role_evidence']), ('unknown', True))
        self.assertEqual(read('Senior Researcher', 'Microsoft Research (United Kingdom)', 'GB')['role_class'], 'industry')
        self.assertEqual(read('Physician Scientist', 'TUM Klinikum Rechts der Isar')['role_class'], 'researcher')
        self.assertEqual(read('Oberarzt', 'Charité - Universitätsmedizin Berlin')['role_class'], 'researcher')
        for title in ('Wissenschaftliche Mitarbeitende', 'Wissenschaftlicher Mitarbeiter'):
            result = read(title, 'Karlsruhe Institute of Technology')
            self.assertEqual((result['role_class'], '(DE: may be PhD student)' in result['role_evidence']), ('researcher', True))


if __name__ == '__main__':
    unittest.main()
