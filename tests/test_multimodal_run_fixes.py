"""Defects found by the multimodal run of 2026-10-14 (REPORT.md, "卡住的地方")."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import visit_page
from current_affiliation import classify_role, title_class
from merge_persons import inst_tokens, weak_match
from unittest.mock import patch
from person_fields import assign_groups, same_institution
from visit_page import classify, visit


class WeakKeyTests(unittest.TestCase):
    def test_institution_tokens_split_on_semicolons_and_brackets(self):
        self.assertIn('klinikum', inst_tokens('TUM Klinikum; Technical University of Munich'))
        self.assertIn('tubingen', inst_tokens('MPI-IS (Tübingen)'))

    def test_same_name_same_hospital_merges_across_affiliation_lists(self):
        a = {'name_raw': 'Anna Beispiel', 'affiliation_raw': 'TUM Klinikum; Technical University of Munich'}
        b = {'name_raw': 'Anna Beispiel', 'affiliation_raw': 'TUM Klinikum Rechts der Isar'}
        self.assertTrue(weak_match(a, b))


class PageReaderTests(unittest.TestCase):
    SHELL = 'Program\nScholars\n' + 'IMPRS-IS is a community of doctoral researchers. ' * 4
    ROSTER = 'Scholars\n' + '\n'.join(f'Person {i}\nMachine Learning' for i in range(60))

    def test_render_with_http_only_ladder_still_reaches_the_browser(self):
        with patch('visit_page.http_read', return_value={'http_status': 200, 'final_url': 'https://imprs.example/scholars', 'text': self.SHELL}), \
                patch('visit_page.browser_read', return_value={'http_status': 200, 'final_url': 'https://imprs.example/scholars', 'text': self.ROSTER}):
            record = visit('https://imprs.example/scholars', ladder=('http',), render=True)
        self.assertEqual(record['fetch_via'], 'browser')
        self.assertEqual([a['via'] for a in record['attempts']], ['http', 'browser'])

    def test_bot_checks_are_challenges_not_readable_pages(self):
        pages = [{'http_status': 200, 'title': 'Bot Detection',
                  'text': 'Bot Detection\nPlease wait while we check if you are a Human\nThis website is protected with BunkerWeb'},
                 {'http_status': 200, 'title': 'Verifying...', 'text': "Please verify you're not a robot\nI'm not a robot"},
                 {'http_status': 200, 'title': 'Verifying your browser | OpenReview',
                  'text': 'Verifying your browser\nComplete the check below to continue to OpenReview\nHave an OpenReview account? Sign in to skip this check.'}]
        for page in pages:
            with self.subTest(title=page['title']):
                self.assertEqual(classify(page), 'challenge')
        self.assertEqual(classify({'http_status': 200, 'title': 'Simon Buchholz | MPI-IS',
                                   'text': 'Simon Buchholz\nEMPIRICAL INFERENCE POSTDOCTORAL RESEARCHER\n72076 Tübingen'}), 'readable')

    def test_channel_is_accepted_without_browser_flag(self):
        readable = {'status': 'readable', 'text': 'x' * 300, 'source_type': 'webpage', 'fetch_via': 'browser'}
        with patch('visit_page.visit', return_value=readable) as read, patch('visit_page.save'), \
                patch.object(sys, 'argv', ['visit_page.py', 'https://lab.example/people', '--render', '--channel', 'chrome', '--out', 'x.json']), \
                patch('sys.stderr'):
            self.assertEqual(visit_page.main(), 0)
        self.assertEqual(read.call_args.kwargs['channel'], 'chrome')
        self.assertTrue(read.call_args.kwargs['render'])


class TitleRuleTests(unittest.TestCase):
    def test_titles_the_multimodal_run_left_unclassified(self):
        cases = {'Post Doc': 'researcher', 'Post-Docs': 'researcher', 'post-doc': 'researcher',
                 'Advanced Researcher': 'researcher', 'Researcher': 'researcher', 'Researchers': 'researcher',
                 'Forskare': 'researcher', 'Ricercatore a tempo determinato': 'researcher',
                 'Ricercatrice a tempo determinato': 'researcher', 'Oberarzt': 'researcher', 'Oberärztin': 'researcher',
                 'Lecturer in Autonomous Systems': 'researcher', 'Senior Lecturer': 'researcher',
                 'Universitetslektor': 'professor', 'Biträdande universitetslektor': 'researcher', 'Physician Scientist': 'researcher',
                 'Research Students': 'phd_student', 'Doctoral Assistant': 'phd_student',
                 'MSc; PhD-student': 'phd_student', 'Medical Doctoral Thesis': 'phd_student',
                 'Chairholder': 'professor', 'Hochschullehrer*in': 'professor', 'Hochschullehrerin': 'professor',
                 'Group Head': 'group_leader', 'Head': 'group_leader', 'Principal Researchers': 'group_leader'}
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(title_class(title), expected)

    def test_stage_titles_on_people_the_run_left_unknown(self):
        cases = {'PhD Fellow': 'phd_student', 'Industridoktorand': 'phd_student', 'Postdoktor': 'researcher',
                 'Postdoktorand': 'researcher', 'Research and Teaching Associate': 'researcher',
                 'Faculty (W2)': 'professor', 'Profesor Agregado': 'professor', 'Team Lead': 'group_leader',
                 'tenure senior lecturer (Titular de Universidad)': 'professor',
                 'Research associate / Doctoral student': 'mixed'}
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(title_class(title), expected)

    def test_job_titles_and_ambiguous_words_stay_unclassified(self):
        for title in ('PhD', 'Dr.', 'Research Assistant', 'Research Assistants', 'Research Engineer', 'Scientist',
                      'Stipendiat', 'Technical Staff', 'Consultant', 'Intern', 'Teaching Fellow', 'Amazon Scholar',
                      'Applied Scientist', 'Resident', 'Team members',
                      # A research director often leads a team: a title rule would demote a funding or head-of evidence.
                      'Research Director', 'Junior research director'):
            with self.subTest(title=title):
                self.assertEqual(title_class(title), '')
        self.assertEqual(title_class('Director', affiliation='Technical University of Munich'), '')

    def test_institute_and_doctoral_school_context_comes_from_the_page(self):
        self.assertEqual(title_class('Scientific Director', affiliation='MPI Informatics'), 'professor')
        # A research institute in a GmbH shell (DFKI, Fraunhofer) is an institute, whatever its name says.
        self.assertEqual(title_class('Scientific Director', affiliation='German Research Center for Artificial Intelligence (DFKI GmbH)'),
                         'professor')
        self.assertEqual(title_class('Scientific Director', affiliation='Siemens Healthineers GmbH'), '')
        imprs = {'role_title': 'Scholars', 'parent': 'International Max Planck Research School for Intelligent Systems',
                 'affiliation_raw': 'MPI for Intelligent Systems / University of Tübingen / University of Stuttgart',
                 'evidence_url': 'https://imprs.is.mpg.de/scholars', 'signal_type': 'imprs_member'}
        self.assertEqual(classify_role({'signals': [imprs]}, 2026)['role_class'], 'phd_student')
        fellows = {**imprs, 'parent': 'ELLIS Society', 'evidence_url': 'https://ellis.example/scholars'}
        self.assertEqual(classify_role({'signals': [fellows]}, 2026)['role_class'], 'unknown')

    def test_uk_and_irish_lecturer_ranks_are_faculty(self):
        for country in ('GB', 'IE'):
            for title in ('Lecturer', 'Lecturer in Autonomous Systems', 'Senior Lecturer', 'University Lecturer',
                          'Reader', 'Reader in Machine Learning', 'Associate Professor'):
                with self.subTest(country=country, title=title):
                    self.assertEqual(title_class(title, country=country), 'professor')
        for title in ('Lecturer', 'Senior Lecturer', 'Lecturer in Autonomous Systems'):
            with self.subTest(country='DE', title=title):
                self.assertEqual(title_class(title, country='DE'), 'researcher')
                self.assertEqual(title_class(title), 'researcher')
        self.assertEqual(title_class('Reader', country='NL'), '')
        self.assertEqual(title_class('Lecturers and PhD Students', country='GB'), 'mixed')

    def test_external_and_guest_lecturers_are_never_professors(self):
        for country in ('GB', 'IE', 'DE', ''):
            for title in ('External Lecturer', 'Guest Lecturer', 'Visiting Lecturer', 'Associate Lecturer', 'Research Lecturer',
                          'Lehrbeauftragte', 'Lehrbeauftragter', 'Lehrbeauftragte*r'):
                with self.subTest(country=country, title=title):
                    self.assertNotEqual(title_class(title, country=country), 'professor')

    def test_classify_role_reads_the_country_of_the_person(self):
        signals = [{'role_title': 'Senior Lecturer', 'evidence_url': 'https://e/1'}]
        self.assertEqual(classify_role({'country': 'GB', 'signals': signals}, 2026)['role_class'], 'professor')
        self.assertEqual(classify_role({'country': 'SE', 'signals': signals}, 2026)['role_class'], 'researcher')
        moved = {'country': 'DE', 'final_pass_country': 'IE', 'final_pass_title': 'Lecturer', 'final_pass_url': 'https://e/2',
                 'last_verified': '2026-10-15', 'signals': []}
        self.assertEqual(classify_role(moved, 2026)['role_class'], 'professor')

    def test_scholars_means_doctoral_only_at_a_doctoral_school(self):
        self.assertEqual(title_class('Scholars', affiliation='IMPRS-IS, Tübingen'), 'phd_student')
        self.assertEqual(title_class('Scholars', affiliation='International Max Planck Research School for Intelligent Systems'), 'phd_student')
        self.assertEqual(title_class('Scholars'), '')
        self.assertEqual(title_class('Visiting Scholars', affiliation='University of Example'), '')

    def test_scientific_staff_is_a_researcher_with_the_german_caveat(self):
        self.assertEqual(title_class('Scientific Staff'), 'researcher')
        result = classify_role({'signals': [{'role_title': 'Scientific Staff', 'evidence_url': 'https://e/1'}]}, 2026)
        self.assertIn('(DE: may be PhD student)', result['role_evidence'])

    def test_swiss_postdoctoral_fellowship_names_a_researcher(self):
        person = {'name': 'X', 'signals': [{'signal_type': 'snsf_swiss_postdoc', 'role': 'pi', 'date': '2025', 'evidence_url': 'https://e/1'}]}
        self.assertEqual(classify_role(person, 2026)['role_class'], 'researcher')

    def test_final_pass_title_uses_the_final_pass_affiliation(self):
        person = {'final_pass_title': 'Scholars', 'final_pass_url': 'https://imprs.is.mpg.de/scholars', 'last_verified': '2026-10-15',
                  'final_pass_affiliation': 'IMPRS-IS', 'current_affiliation': 'IMPRS-IS', 'signals': []}
        self.assertEqual(classify_role(person, 2026)['role_class'], 'phd_student')


def person(name, affiliation, role_class, signals, **fields):
    return {'name': name, 'current_affiliation': affiliation, 'role_class': role_class,
            'signals': [{'name_raw': name, 'affiliation_raw': affiliation, 'channel': 'funding-eu', **s} for s in signals], **fields}


INRIA = 'Institut national de recherche en sciences et technologies du numérique'
GRANT = 'NERPHYS — Empowering Neural Rendering Methods with Physically-Based Capabilities'


class GrantParentTests(unittest.TestCase):
    def setUp(self):
        self.pi = person('Georges Drettakis', 'INRIA Sophia-Antipolis', 'group_leader',
                         [{'signal_type': 'erc_adg', 'role': 'pi', 'parent': GRANT, 'evidence_url': 'https://erc.example/adg'}])
        # An ex-postdoc of the grant, now a professor elsewhere; the provider institution id is the old one.
        self.franke = person('Linus Franke', 'Julius-Maximilians-Universität Würzburg', 'professor',
                             [{'signal_type': 'grant_publication', 'role': 'last_author', 'parent': GRANT,
                               'affiliation_raw': INRIA, 'evidence_url': 'https://doi.org/10.1016/j.cag.2026.104637'},
                              {'signal_type': 'pi_coauthor_publication', 'role': 'coauthor', 'parent': 'George Drettakis',
                               'affiliation_raw': INRIA, 'evidence_url': 'https://doi.org/10.1145/3799902.3811167'}],
                             final_pass_affiliation='Julius-Maximilians-Universität Würzburg', final_pass_country='DE',
                             last_verified='2026-10-15', ids={'openalex_institution': 'I1326498283'})
        self.member = person('Alexandre Lanvin', INRIA, 'phd_student',
                             [{'signal_type': 'grant_publication', 'role': 'first_author', 'parent': GRANT,
                               'evidence_url': 'https://doi.org/10.1145/3730913'}], ids={'openalex_institution': 'I1326498283'})
        self.coauthor = person('Simon Lucas', INRIA, 'unknown',
                               [{'signal_type': 'pi_coauthor_publication', 'role': 'coauthor', 'parent': 'George Drettakis',
                                 'evidence_url': 'https://doi.org/10.1111/cgf.70542'}])

    def test_grant_publication_parent_maps_to_the_grant_pi(self):
        results = assign_groups([self.pi, self.franke, self.member, self.coauthor])
        by_name = {p['name']: p for p in results}
        self.assertEqual(by_name['Alexandre Lanvin']['group'], 'Georges Drettakis @ INRIA Sophia-Antipolis')
        self.assertEqual(by_name['Linus Franke']['group'], 'Linus Franke @ Julius-Maximilians-Universität Würzburg')
        self.assertNotEqual(by_name['Simon Lucas']['group'], by_name['Linus Franke']['group'])

    def test_a_coauthor_of_the_grant_cannot_anchor_its_members(self):
        results = assign_groups([self.franke, self.member])
        self.assertEqual(results[1]['group'], '')

    def test_final_pass_affiliation_beats_a_stale_institution_id(self):
        self.assertFalse(same_institution(self.member, self.franke))
        self.assertTrue(same_institution(self.member, {**self.franke, 'final_pass_affiliation': INRIA, 'current_affiliation': INRIA}))
        # A final pass that confirms the provider institution keeps the provider id usable.
        stayed = {**self.franke, 'final_pass_affiliation': 'Inria Sophia Antipolis', 'current_affiliation': 'Inria Sophia Antipolis',
                  'institution_name': INRIA}
        self.assertTrue(same_institution({'ids': {'openalex_institution': 'I1326498283'}, 'current_affiliation': 'GraphDeco'}, stayed))


class GroupLinkTests(unittest.TestCase):
    def setUp(self):
        self.pi = person('Georges Drettakis', 'INRIA Sophia-Antipolis', 'group_leader',
                         [{'signal_type': 'erc_adg', 'role': 'pi', 'parent': GRANT, 'evidence_url': 'https://erc.example/adg'}],
                         homepage='https://graphdeco.inria.fr/drettakis')

    def coauthor(self, name, affiliation, parent):
        return person(name, affiliation, 'unknown', [{'signal_type': 'pi_coauthor_publication', 'role': 'coauthor',
                                                       'parent': parent, 'evidence_url': f'https://doi.org/{name}'}])

    def group_of(self, member):
        return assign_groups([self.pi, member])[1]

    def test_parent_name_variant_matches_a_leader_at_the_same_institution(self):
        result = self.group_of(self.coauthor('Simon Lucas', INRIA, 'George Drettakis'))
        self.assertEqual(result['group'], 'Georges Drettakis @ INRIA Sophia-Antipolis')
        self.assertIn('name variant', result['group_evidence'])
        self.assertEqual(result['group_link'], 'coauthor')

    def test_name_variants_never_cross_institutions_or_initials(self):
        self.assertEqual(self.group_of(self.coauthor('Ana Other', 'University of Bonn', 'George Drettakis'))['group'], '')
        self.assertEqual(self.group_of(self.coauthor('Simon Lucas', INRIA, 'Peter Drettakis'))['group'], '')
        self.assertEqual(self.group_of(self.coauthor('Simon Lucas', INRIA, 'George Drettakides'))['group'], '')

    def test_exact_parent_keeps_the_plain_evidence(self):
        result = self.group_of(self.coauthor('Simon Lucas', INRIA, 'Georges Drettakis'))
        self.assertEqual(result['group'], 'Georges Drettakis @ INRIA Sophia-Antipolis')
        self.assertNotIn('name variant', result['group_evidence'])

    def test_every_grouped_person_records_how_it_is_linked(self):
        members = [
            person('Team Member', INRIA, 'phd_student', [{'signal_type': 'lab_member', 'role': 'team_member',
                                                           'parent': 'Georges Drettakis', 'evidence_url': 'https://graphdeco.inria.fr/team'}]),
            person('Grant Member', INRIA, 'phd_student', [{'signal_type': 'grant_publication', 'role': 'first_author',
                                                            'parent': GRANT, 'evidence_url': 'https://doi.org/10.1145/3730913'}]),
            self.coauthor('Simon Lucas', INRIA, 'Georges Drettakis'),
            person('Host Member', INRIA, 'researcher', [{'signal_type': 'personal_role', 'evidence_url': 'https://e/host'}],
                   homepage='https://graphdeco.inria.fr/host-member'),
            person('Repo Member', 'Elsewhere GmbH', 'unknown', [{'signal_type': 'code_contribution', 'channel': 'open-source',
                                                                  'evidence_url': 'https://github.com/graphdeco-inria/gaussian-splatting'}]),
            person('Nobody', 'University of Bonn', 'unknown', [{'signal_type': 'best_paper', 'evidence_url': 'https://e/x'}]),
        ]
        pi = {**self.pi, 'signals': self.pi['signals'] + [{'signal_type': 'repository_activity', 'channel': 'open-source',
                                                           'evidence_url': 'https://github.com/graphdeco-inria'}]}
        links = {p['name']: (p['group_rule'], p['group_link']) for p in assign_groups([pi, *members])}
        self.assertEqual(links, {'Georges Drettakis': (4, 'team'), 'Team Member': (1, 'team'), 'Grant Member': (1, 'project'),
                                 'Simon Lucas': (1, 'coauthor'), 'Host Member': (2, 'team'), 'Repo Member': (3, 'team'),
                                 'Nobody': (None, '')})

    def test_same_paper_rule_is_a_coauthor_link_and_team_beats_coauthor(self):
        paper = 'https://doi.org/10.1/paper'
        leader = person('Lead Author', 'University of Bonn', 'professor', [{'signal_type': 'best_paper', 'role': 'last_author',
                                                                           'evidence_url': paper, 'channel': 'awards-papers'}])
        student = person('First Author', 'University of Bonn', 'unknown', [{'signal_type': 'best_paper', 'role': 'first_author',
                                                                           'evidence_url': paper, 'channel': 'awards-papers'}])
        result = assign_groups([leader, student])[1]
        self.assertEqual((result['group_rule'], result['group_link']), (4, 'coauthor'))
        both = person('First Author', 'University of Bonn', 'unknown', [
            {'signal_type': 'pi_coauthor_publication', 'role': 'coauthor', 'parent': 'Lead Author', 'evidence_url': paper},
            {'signal_type': 'lab_member', 'role': 'team_member', 'parent': 'Lead Author', 'evidence_url': 'https://bonn.example/team'}])
        self.assertEqual(assign_groups([leader, both])[1]['group_link'], 'team')


class AffiliationListTests(unittest.TestCase):
    def test_lists_and_unit_prefixes_name_the_institution(self):
        self.assertTrue(same_institution('Chair of Ecosystem Physiology, University of Freiburg',
                                         'Chair of Sensor-based Geoinformatics, University of Freiburg'))
        self.assertTrue(same_institution('Tübingen AI Center; Czech Technical University in Prague; University of Tübingen',
                                         'University of Tübingen'))
        self.assertTrue(same_institution('MPI for Intelligent Systems / University of Tübingen / University of Stuttgart',
                                         'Universität Tübingen'))
        self.assertTrue(same_institution('LMB, University of Freiburg', 'University of Freiburg'))

    def test_translations_of_university_of_compare_equal(self):
        for left, right in [('Università di Cagliari', 'University of Cagliari'), ('Universiteit Utrecht', 'Utrecht University'),
                            ("Université Côte d'Azur", "University of Côte d'Azur"), ('Universität des Saarlandes', 'Saarland University'),
                            ('CISPA Helmholtz-Zentrum für Informationssicherheit', 'CISPA Helmholtz Center for Information Security')]:
            with self.subTest(left=left):
                self.assertTrue(same_institution(left, right))
        self.assertFalse(same_institution('University of Bonn', 'University of Bern'))

    def test_an_umbrella_only_affiliation_is_compatible_with_its_institutes(self):
        self.assertTrue(same_institution('Max Planck Society', 'Max-Planck-Institut für Informatik'))
        self.assertTrue(same_institution('Max Planck Institute for Intelligent Systems', 'Max Planck Society'))
        self.assertFalse(same_institution('Max Planck Society', 'University of Tübingen'))
        self.assertFalse(same_institution('Max Planck Institute for Intelligent Systems', 'Max-Planck-Institut für Informatik'))

    def test_countries_cities_and_umbrella_bodies_do_not_join_institutions(self):
        self.assertFalse(same_institution('ETH Zurich, Switzerland', 'EPFL, Switzerland'))
        self.assertFalse(same_institution('MPI-IS, Tübingen', 'University of Tübingen, Tübingen'))
        self.assertFalse(same_institution('LIRIS, CNRS', 'LIP6, CNRS'))
        self.assertFalse(same_institution('Fraunhofer IAIS', 'Fraunhofer HHI'))


class VerifiedRosterWindowTests(unittest.TestCase):
    def test_a_final_pass_read_dates_an_undated_roster_signal(self):
        import datetime
        from table_export import filter_window
        start, end = datetime.date(2023, 10, 14), datetime.date(2026, 10, 14)
        roster = {'signal_type': 'lab_member', 'channel': 'funding-de-ch', 'evidence_url': 'https://lab.example/team', 'hop_depth': 1}
        paper = {'signal_type': 'lab_publication', 'channel': 'funding-de-ch', 'date': '2019-05-01', 'evidence_url': 'https://doi.org/x'}
        read = {'name': 'Member', 'signals': [roster, paper], 'last_verified': '2026-10-15', 'final_pass_url': 'https://lab.example/team'}
        unread = {'name': 'Other', 'signals': [roster, paper]}
        old_read = {'name': 'Stale', 'signals': [roster], 'last_verified': '2021-01-01'}
        kept, rejected = filter_window([read, unread, old_read], start, end)
        self.assertEqual([p['name'] for p in kept], ['Member'])
        self.assertEqual(kept[0]['qualifying'], [roster])  # the old paper stays background evidence
        self.assertEqual({r['name'] for r in rejected}, {'Member', 'Other', 'Stale'})


class RemainingDefectTests(unittest.TestCase):
    def test_weak_key_knows_institution_aliases(self):
        a = {'name_raw': 'Deniz Bayazit', 'affiliation_raw': 'EPFL'}
        b = {'name_raw': 'Deniz Bayazit', 'affiliation_raw': 'École Polytechnique Fédérale de Lausanne'}
        self.assertTrue(weak_match(a, b))
        self.assertFalse(weak_match(a, {'name_raw': 'Deniz Bayazit', 'affiliation_raw': 'ETH Zurich'}))
        self.assertFalse(weak_match(a, {'name_raw': 'Deniz Bayazit', 'affiliation_raw': ''}))

    def test_a_page_that_is_only_a_cookie_banner_is_empty(self):
        banner = ('Consent\nDetails\nAbout\nWe use cookies on ri.se\nWe use cookies to facilitate a satisfactory functioning of our '
                  'website, to analyze visitor data, and to protect the website against intrusions and load attacks. You, as a user, '
                  'have full control over whether you want to give your consent to the cookies we use.\nAccept all\nDeny')
        self.assertEqual(classify({'http_status': 200, 'title': 'Tor Skoglund | RISE', 'text': banner}), 'empty')
        page = banner + '\nTor Skoglund\nSenior Researcher, Humanized Autonomy\nRISE Research Institutes of Sweden\n' + 'Works on multimodal perception. ' * 6
        self.assertEqual(classify({'http_status': 200, 'title': 'Tor Skoglund | RISE', 'text': page}), 'readable')

    def test_pdf_rosters_are_read_through_pdftotext_when_installed(self):
        import email.message
        import io
        import subprocess

        class Response(io.BytesIO):
            status = 200
            headers = email.message.Message()
            headers['Content-Type'] = 'application/pdf'

            def geturl(self):
                return 'https://lab.example/team.pdf'

        class Opener:
            def open(self, request, timeout):
                return Response(b'%PDF-1.4 fake')

        with patch('visit_page.urllib.request.build_opener', return_value=Opener()), \
                patch('visit_page.shutil.which', return_value='/usr/bin/pdftotext'), \
                patch('visit_page.subprocess.run', return_value=subprocess.CompletedProcess([], 0, stdout=b'Team\nAlice PhD student\n', stderr=b'')):
            record = visit_page.http_read('https://lab.example/team.pdf', 10)
        self.assertEqual(record['text'], 'Team\nAlice PhD student')
        self.assertEqual(classify(record), 'readable')
        with patch('visit_page.urllib.request.build_opener', return_value=Opener()), patch('visit_page.shutil.which', return_value=None):
            record = visit_page.http_read('https://lab.example/team.pdf', 10)
        self.assertEqual(record['status'], 'unsupported_content')
        self.assertIn('pdftotext', record['error'])

    def test_a_university_name_as_parent_links_roster_members_only(self):
        university = 'UNIVERSITAT POLITÈCNICA DE VALÈNCIA'
        leader = {'name': 'Paolo Rosso', 'current_affiliation': university, 'role_class': 'professor',
                  'signals': [{'name_raw': 'Paolo Rosso', 'affiliation_raw': university, 'role': 'pi', 'signal_type': 'aei_project',
                               'channel': 'funding-fr-es-nl-be', 'evidence_url': 'https://aei.example/1'}]}
        grantee = {'name': 'Alberto Albiol', 'current_affiliation': university, 'role_class': 'researcher',
                   'signals': [{'name_raw': 'Alberto Albiol', 'affiliation_raw': university, 'role': 'pi', 'signal_type': 'aei_project',
                                'parent': university, 'channel': 'funding-fr-es-nl-be', 'evidence_url': 'https://aei.example/2'}]}
        listed = {**grantee, 'name': 'Jorge González', 'signals': [{**grantee['signals'][0], 'name_raw': 'Jorge González', 'role': 'team_member',
                                                                     'signal_type': 'lab_member', 'evidence_url': 'https://upv.example/team'}]}
        results = assign_groups([leader, grantee, listed])
        self.assertEqual(results[1]['group'], 'Alberto Albiol @ ' + university)  # a PI anchors their own project
        self.assertEqual(results[2]['group'], 'Paolo Rosso @ ' + university)
        coauthor = {**grantee, 'name': 'Jon Ander Gómez', 'signals': [{**grantee['signals'][0], 'name_raw': 'Jon Ander Gómez', 'role': 'coauthor',
                                                                        'signal_type': 'grant_publication', 'evidence_url': 'https://doi.org/x'}]}
        self.assertEqual(assign_groups([leader, coauthor])[1]['group'], '')

    def test_a_final_pass_move_overrides_an_undated_roster_listing(self):
        leader = {'name': 'Björn Ommer', 'current_affiliation': 'LMU Munich', 'role_class': 'professor',
                  'signals': [{'name_raw': 'Björn Ommer', 'affiliation_raw': 'LMU Munich', 'role': 'team_member', 'signal_type': 'lab_member',
                               'parent': 'Computer Vision & Learning Group', 'evidence_url': 'https://ommer-lab.com/people'}]}
        listing = {'name_raw': 'Robin Rombach', 'affiliation_raw': 'LMU Munich', 'role': 'team_member', 'signal_type': 'lab_member',
                   'parent': 'Computer Vision & Learning Group', 'evidence_url': 'https://ommer-lab.com/people'}
        moved = {'name': 'Robin Rombach', 'current_affiliation': 'Black Forest Labs', 'final_pass_affiliation': 'Black Forest Labs',
                 'final_pass_country': 'DE', 'last_verified': '2026-10-15', 'role_class': 'industry', 'signals': [listing]}
        self.assertEqual(assign_groups([leader, moved])[1]['group'], '')
        self.assertIn('moved', assign_groups([leader, moved])[1]['group_evidence'])
        stayed = {**moved, 'final_pass_affiliation': 'LMU Munich', 'current_affiliation': 'LMU Munich'}
        self.assertEqual(assign_groups([leader, stayed])[1]['group'], 'Björn Ommer @ LMU Munich')
        dated = {**moved, 'signals': [{**listing, 'date': '2026-09-01'}]}  # a dated roster is current evidence
        self.assertEqual(assign_groups([leader, dated])[1]['group'], 'Björn Ommer @ LMU Munich')

    def test_founder_and_c_level_titles_are_industry(self):
        for title in ('Founder & CEO', 'Co-Founder and CTO', 'Chief Executive Officer', 'COO & Co-Founder', 'Founder'):
            with self.subTest(title=title):
                self.assertEqual(title_class(title), 'industry')
        self.assertEqual(title_class('Professor and Co-Founder'), 'professor')


class AffiliationTrustTests(unittest.TestCase):
    def test_orcid_employment_named_by_the_newest_evidence_is_not_stale(self):
        from unittest.mock import patch
        import current_affiliation
        person = {'name': 'Isabelle Example', 'ids': {'orcid': '0000-0001-0000-0001', 'openalex': 'A1'},
                  'signals': [{'affiliation_raw': 'University of Copenhagen; ETH Zurich', 'country': 'CH', 'date': '2026-05-01',
                               'role': 'last_author', 'evidence_url': 'https://e/1'}]}
        employment = (2019, 'University of Copenhagen', 'DK', 'Professor', 'https://orcid.org/0000-0001-0000-0001')
        with patch.object(current_affiliation, 'orcid_current', return_value=employment), \
                patch.object(current_affiliation, 'openalex_current', return_value=None), \
                patch.object(current_affiliation, 'first_publication_year', return_value=None):
            result = current_affiliation.enrich(person, {'DK', 'CH'}, None, 2026)
        self.assertEqual((result['current_affiliation'], result['country']), ('University of Copenhagen', 'DK'))
        self.assertEqual(result['role_class'], 'professor')
        # The stale rule still applies when the evidence names another institution in another country.
        person['signals'][0]['affiliation_raw'] = 'ETH Zurich'
        with patch.object(current_affiliation, 'orcid_current', return_value=employment), \
                patch.object(current_affiliation, 'openalex_current', return_value=None), \
                patch.object(current_affiliation, 'first_publication_year', return_value=None):
            result = current_affiliation.enrich(person, {'DK', 'CH'}, None, 2026)
        self.assertEqual((result['current_affiliation'], result['country']), ('ETH Zurich', 'CH'))

    def test_single_institution_evidence_corrects_a_wrong_orcid_country(self):
        from unittest.mock import patch
        import current_affiliation
        person = {'name': 'Catarina Example', 'ids': {'orcid': '0000-0001-0000-0002'},
                  'signals': [{'affiliation_raw': 'ISR-Lisboa/LARSyS, Instituto Superior Técnico', 'country': 'PT', 'date': '2026-03-01',
                               'role': 'last_author', 'evidence_url': 'https://e/2'}]}
        employment = (2023, 'Instituto Superior Técnico', 'ID', 'Assistant Professor', 'https://orcid.org/0000-0001-0000-0002')
        with patch.object(current_affiliation, 'orcid_current', return_value=employment), \
                patch.object(current_affiliation, 'openalex_current', return_value=None), \
                patch.object(current_affiliation, 'first_publication_year', return_value=None):
            result = current_affiliation.enrich(person, {'PT'}, None, 2026)
        self.assertEqual((result['current_affiliation'], result['country']), ('Instituto Superior Técnico', 'PT'))
        self.assertIn('country from evidence', result['affiliation_source'])
        self.assertIn('evidence country used', result['notes'])

    def test_research_institutes_organised_as_gmbh_are_not_industry(self):
        for affiliation in ('DFKI GmbH', 'Deutsches Forschungszentrum für Künstliche Intelligenz GmbH',
                            'Forschungszentrum Jülich GmbH', 'Fraunhofer IAIS'):
            with self.subTest(affiliation=affiliation):
                person = {'name': 'A', 'current_affiliation': affiliation,
                          'signals': [{'affiliation_raw': affiliation, 'role_title': 'Researcher', 'evidence_url': 'https://e/1'}]}
                self.assertEqual(classify_role(person, 2026)['role_class'], 'researcher')
        person = {'name': 'B', 'current_affiliation': 'Bosch Hospital GmbH',
                  'signals': [{'affiliation_raw': 'Bosch Hospital GmbH', 'role_title': 'Researcher', 'evidence_url': 'https://e/1'}]}
        self.assertEqual(classify_role(person, 2026)['role_class'], 'industry')


if __name__ == '__main__':
    unittest.main()
