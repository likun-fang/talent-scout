import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_domain_pack
from check_domain_pack import check_pack, load_yaml

SAMPLE = '''# a comment line
domain: "multimodal AI"   # trailing comment
slug: multimodal-ai
window: {from: "2023-10-14", to: null}
sources_used:
  - "openalex-topics (searches: multimodal, vision-language)"
  - erc-panels # a source
venues:
  conferences:
    - {name: CVPR, award_page_pattern: "https://x.example/#awards", works: 639}
  journals: []
directions:
  - id: vla
    queries: [vision-language-action, 'it''s quoted']
    inclusion: Visual and language inputs condition robot actions.
  - id: wam
    queries: []
scope:
  core:
    - One line.
keyword_rules: ""
'''


def pack_text(**overrides):
    """A complete, valid pack yaml for slug 'demo-field' with the given top-level values replaced (JSON-encoded)."""
    values = {'domain': '"demo field"', 'slug': 'demo-field', 'derived_on': '"2026-10-14"',
              'window': '{from: "2023-10-14", to: "2026-10-14"}', 'sources_used': '[openalex-topics]',
              'region_core': '"DE+CH"', 'region_extended': '"EU27+UK+CH+NO"', 'facets_file': 'assets/facets/demo-field.json',
              'scope': '{core: [], conditional: [], excluded: []}', 'directions': '[]', 'discovery_seeds': '[]',
              'collection_requirements': '[]', 'openalex_topics': '[{id: T1, name: Topic, fit: core}]',
              'topic_discovery_queries': '[]', 'venues': '{conferences: [], journals: []}', 'panels_to_sweep': '[]',
              'euroscivoc_paths': '[]', 'register_subject_filters': '{dfg_review_boards: [], snsf_main_disciplines: []}',
              'competitions': '[]', 'labs': '[]', 'companies': '[]', 'open_source_anchors': '[]', 'keywords': '[]',
              'keyword_rules': '""', 'prizes_filter': '""', 'historical_snapshot': '{}',
              'quirks': '{title_words: [], institution_patterns: [], evidence_venues: []}'}
    values.update(overrides)
    return ''.join(f'{key}: {value}\n' for key, value in values.items() if value is not None)


class YamlSubsetTests(unittest.TestCase):
    def test_the_subset_the_packs_use_parses_like_yaml(self):
        data = load_yaml(SAMPLE)
        self.assertEqual(data['domain'], 'multimodal AI')
        self.assertEqual(data['window'], {'from': '2023-10-14', 'to': None})
        self.assertEqual(data['sources_used'], ['openalex-topics (searches: multimodal, vision-language)', 'erc-panels'])
        self.assertEqual(data['venues'], {'conferences': [{'name': 'CVPR', 'award_page_pattern': 'https://x.example/#awards', 'works': 639}],
                                          'journals': []})
        self.assertEqual(data['directions'], [{'id': 'vla', 'queries': ['vision-language-action', "it's quoted"],
                                               'inclusion': 'Visual and language inputs condition robot actions.'},
                                              {'id': 'wam', 'queries': []}])
        self.assertEqual(data['scope'], {'core': ['One line.']})
        self.assertEqual(data['keyword_rules'], '')

    def test_a_plain_list_item_with_a_colon_and_space_is_a_mapping_as_in_yaml(self):
        self.assertEqual(load_yaml('items:\n  - openalex (searches: x)\n'), {'items': [{'openalex (searches': 'x)'}]})

    def test_edge_cases_parse_as_yaml_does(self):
        cases = {'keywords: ["a\\" # b"]\n': {'keywords': ['a" # b']},
                 'labs: [{https://example.org: Lab}]\n': {'labs': [{'https://example.org': 'Lab'}]},
                 'items:\n  -\n  - robots\n': {'items': [None, 'robots']},
                 'labs:\n  - "name": Robotics\n    country: DE\n': {'labs': [{'name': 'Robotics', 'country': 'DE'}]},
                 'keywords: [a, b,]\n': {'keywords': ['a', 'b']},
                 "keywords: ['it''s # robotics']\n": {'keywords': ["it's # robotics"]},
                 'labs: [{"name" : Robotics}]\n': {'labs': [{'name': 'Robotics'}]},
                 'labs: [{name:[robotics]}]\n': {'labs': [{'name': ['robotics']}]},
                 'keyword_rules: use a "robotics term # comment\n': {'keyword_rules': 'use a "robotics term'},
                 'keyword_rules: search vision, "robotics # comment\n': {'keyword_rules': 'search vision, "robotics'},
                 'labs: [{name: "a, #1", url: https://x.example/#top}] # c\n': {'labs': [{'name': 'a, #1', 'url': 'https://x.example/#top'}]}}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(load_yaml(text), expected)

    def test_flow_collections_need_commas_and_anchors_are_outside_the_subset(self):
        for text in ('keywords: ["robots" "vision"]\n', 'keywords: [&seed robotics, *seed]\n', 'labs: {a: !tag b}\n',
                     'snapshot: {terms: [a,,b]}\n', 'keyword_rules: a: b\n', 'keywords: [robot: arm]\n', 'keywords: [foo{bar]\n',
                     'keywords: []\nkeywords: [x]\n', 'labs: [{name: a, name: b}]\n', 'keywords: [robot:]\n',
                     'labs:\n  - - robotics\n', 'keywords: [True]\n', 'keywords: [Null]\n', 'keywords: [0x10]\n',
                     'keywords: [0123]\n', 'derived_on: 2026-10-14\n', 'keywords: [? robot]\n', 'keywords: [|]\n',
                     'keywords: [- robot]\n', 'snapshot: {true: x}\n', '1: x\n', 'keywords: [\t"robot", x]\n'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as stop:
                    load_yaml(text)
                self.assertRegex(str(stop.exception), r'^line \d+: ')

    def test_a_line_the_subset_does_not_cover_names_its_line(self):
        with self.assertRaises(ValueError) as stop:
            load_yaml('notes: |\n  a block scalar\n')
        self.assertIn('line 1', str(stop.exception))


class PackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ('domain-cache', 'assets/facets', 'assets/known-groups'):
            (self.root / folder).mkdir(parents=True)
        (self.root / 'assets/facets/demo-field.json').write_text(json.dumps({'facets': []}), encoding='utf-8')
        (self.root / 'assets/known-groups/demo-field.json').write_text(json.dumps({'groups': []}), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, text, slug='demo-field'):
        (self.root / 'domain-cache' / f'{slug}.yaml').write_text(text, encoding='utf-8')
        return check_pack(slug, self.root)

    def test_a_complete_pack_passes(self):
        errors, warnings = self.check(pack_text())
        self.assertEqual((errors, warnings), ([], []))

    def test_unknown_or_missing_keys_and_bad_values_are_errors(self):
        cases = {'seeds': pack_text(seeds='[{name: Anna Meyer}]'), 'missing quirks': pack_text(quirks=None),
                 'derived_on': pack_text(derived_on='"2026-13-01"'), 'slug': pack_text(slug='other-field'),
                 'fit': pack_text(openalex_topics='[{id: T1, name: Topic, fit: central}]'),
                 'quirks key': pack_text(quirks='{title_words: [], institution_patterns: [], evidence_venues: [], extra: []}')}
        for case, text in cases.items():
            with self.subTest(case=case):
                errors, _ = self.check(text)
                self.assertTrue(errors, case)

    def test_a_value_of_the_wrong_type_is_reported_not_a_crash(self):
        (self.root / 'domain-cache/demo-field.yaml').write_text(pack_text(labs='3'), encoding='utf-8')
        line = check_domain_pack.report('demo-field', self.root)
        self.assertTrue(line.startswith('FAIL demo-field'))
        self.assertIn('$.labs: expected array', line)

    def test_personal_data_is_an_error(self):
        for value in ('[https://www.linkedin.com/in/someone]', '["author A5024508073 dropped"]'):
            with self.subTest(value=value):
                errors, _ = self.check(pack_text(sources_used=value))
                self.assertTrue(any('personal data' in e for e in errors), errors)

    def test_personal_data_in_the_facets_or_known_groups_file_is_an_error(self):
        for name, content in (('assets/facets/demo-field.json', {'facets': [{'keywords': ['https://www.linkedin.com/in/x']}]}),
                              ('assets/known-groups/demo-field.json', {'groups': [{'pi': 'A', 'ids': 'https://openalex.org/A5024508073'}]})):
            with self.subTest(name=name):
                original = (self.root / name).read_text(encoding='utf-8')
                (self.root / name).write_text(json.dumps(content), encoding='utf-8')
                errors, _ = self.check(pack_text())
                self.assertTrue(any('personal data' in e for e in errors), errors)
                (self.root / name).write_text(original, encoding='utf-8')

    def test_the_facets_file_must_exist_and_a_missing_known_groups_list_is_a_warning(self):
        (self.root / 'assets/known-groups/demo-field.json').unlink()
        errors, warnings = self.check(pack_text())
        self.assertEqual(errors, [])
        self.assertTrue(any('known-groups' in w for w in warnings))
        (self.root / 'assets/facets/demo-field.json').unlink()
        errors, _ = self.check(pack_text())
        self.assertTrue(any('facets' in e for e in errors))


class ShippedPackTests(unittest.TestCase):
    def test_the_shipped_packs_and_the_template_validate(self):
        for slug in ('embodied-ai', 'multimodal-ai'):
            with self.subTest(slug=slug):
                self.assertEqual(check_pack(slug, ROOT)[0], [])
        self.assertEqual(check_domain_pack.check_file(ROOT / 'assets/domain-map.template.yaml', template=True), [])

    def test_every_pack_has_the_same_key_set_as_the_template(self):
        keys = set(load_yaml((ROOT / 'assets/domain-map.template.yaml').read_text(encoding='utf-8')))
        for slug in ('embodied-ai', 'multimodal-ai'):
            with self.subTest(slug=slug):
                self.assertEqual(set(load_yaml((ROOT / f'domain-cache/{slug}.yaml').read_text(encoding='utf-8'))), keys)


if __name__ == '__main__':
    unittest.main()
