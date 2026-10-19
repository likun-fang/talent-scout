import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import group_map
from group_map import render_html, CORRECTION_URL


def record(pi, institution, country='DE'):
    slug = re.sub(r'\W+', '-', f'{pi} {institution}'.lower()).strip('-')
    return {'id': slug, 'pi': {'name': pi, 'role_class': 'professor', 'homepage': ''},
            'institution': {'name': institution, 'country': country, 'ids': {},
                            'location': {'lat': 48.1, 'lng': 11.6, 'city': 'Munich', 'source': 'manual'}},
            'homepage': 'https://lab.example', 'tags': ['vision-language'], 'topics': ['vision-language models'],
            'members': [{'name': 'Ben Ott', 'role_class': 'phd_student', 'link': 'team'}], 'coauthors_count': 2,
            'active_funding': [{'type': 'erc_cog', 'date': '2024'}], 'open_source': [], 'evidence_urls': ['https://lab.example'],
            'last_verified': '2026-10-15', 'last_verified_from': 'final_pass', 'sources': ['funding-eu'], 'as_of': '2026-10-15'}


def doc(*groups):
    return {'meta': {'domain': 'multimodal AI', 'as_of': '2026-10-15', 'region': 'EU27+UK+CH+NO', 'window_start': '2023-10-15',
                     'facets': [{'id': 'modality', 'label': {'en': 'modality', 'zh': '模态'},
                                 'tags': [{'id': 'vision-language', 'label': {'en': 'vision-language', 'zh': '视觉-语言'}}]}]},
            'groups': list(groups)}


def payload(html):
    return json.loads(re.search(r'<script id="group-data" type="application/json">(.*?)</script>', html, re.S).group(1))


class PageTests(unittest.TestCase):
    def test_page_embeds_the_groups_sorted_by_institution_then_pi(self):
        html = render_html(doc(record('Zoe Adler', 'Utrecht University', 'NL'), record('Bruno Ziegler', 'Aalto University', 'FI'),
                               record('Anna Meyer', 'Aalto University', 'FI')))
        self.assertEqual([g['pi']['name'] for g in payload(html)['groups']], ['Anna Meyer', 'Bruno Ziegler', 'Zoe Adler'])

    def test_static_page_with_pinned_leaflet_and_two_languages(self):
        html = render_html(doc(record('Anna Meyer', 'TUM')))
        self.assertIn('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', html)
        self.assertIn("zh: {", html)
        self.assertIn('<title>Research groups · multimodal AI · 2026-10-15</title>', html)

    def test_every_card_links_a_correction_report_and_the_about_section(self):
        html = render_html(doc(record('Anna Meyer', 'TUM')))
        self.assertIn(json.dumps(CORRECTION_URL), html)
        self.assertIn('id="about"', html)
        self.assertIn('href="#about"', html)

    def test_no_tiers_badges_scores_or_person_pages(self):
        html = render_html(doc(record('Anna Meyer', 'TUM'))).lower()
        for word in ('tier', 'badge', 'score', 'rank', 'data-person'):
            with self.subTest(word=word):
                self.assertNotIn(word, html)

    def test_markup_in_the_data_cannot_close_or_comment_out_the_payload(self):
        evil = record('Anna </script><script>alert(1)</script>', 'TUM')
        evil['topics'] = ['<!--<script>', 'R&D > 1']
        html = render_html(doc(evil))
        data = html.split('<script id="group-data" type="application/json">', 1)[1].split('</script>', 1)[0]
        self.assertNotIn('<', data)
        self.assertEqual(payload(html)['groups'][0]['pi']['name'], 'Anna </script><script>alert(1)</script>')
        self.assertEqual(payload(html)['groups'][0]['topics'], ['<!--<script>', 'R&D > 1'])

    def test_changing_a_filter_returns_from_an_open_card_to_the_filtered_list(self):
        html = render_html(doc(record('Anna Meyer', 'TUM')))
        self.assertIn('function filtersChanged() { fitPending = true; home(); }', html)
        self.assertEqual(html.count('filtersChanged()'), 4)  # the definition, search, country and each facet select


class SharedLabTests(unittest.TestCase):
    def test_groups_of_one_lab_are_drawn_once_as_a_lab_with_their_pi_groups_inside(self):
        lab = {'homepage': 'https://vgg.example/people', 'groups': ['anna-meyer-tum', 'ben-ott-tum']}
        html = render_html(doc({**record('Anna Meyer', 'TUM'), 'lab': lab}, {**record('Ben Ott', 'TUM'), 'lab': lab},
                               record('Cara Lin', 'TUM')))
        self.assertEqual([g.get('lab') for g in payload(html)['groups']], [lab, lab, None])
        # The list draws a lab once, with each of its PI groups as a row inside; a card links the lab's other groups.
        self.assertIn('function labBlock(', html)
        self.assertIn("lab: 'lab'", html)
        self.assertIn("lab: '实验室'", html)


class CommandLineTests(unittest.TestCase):
    def test_main_writes_index_html_and_rejects_a_file_that_is_not_groups_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / 'groups.json', Path(tmp) / 'site' / 'index.html'
            source.write_text(json.dumps(doc(record('Anna Meyer', 'TUM'))), encoding='utf-8')
            old, sys.argv = sys.argv, ['group_map.py', str(source), '--out', str(out)]
            try:
                group_map.main()
                self.assertIn('Anna Meyer', out.read_text(encoding='utf-8'))
                source.write_text('[]', encoding='utf-8')
                with self.assertRaises(SystemExit) as stop:
                    group_map.main()
                self.assertIn('expected an object with "meta" and "groups"', str(stop.exception))
            finally:
                sys.argv = old


if __name__ == '__main__':
    unittest.main()
