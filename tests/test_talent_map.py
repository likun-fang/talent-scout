import argparse
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import talent_map
from talent_map import build_data, canonical_institution, country_centroid, Geocoder, render_html


def sig(name, affiliation, country, date='2025-06-01', signal_type='lab_member', url='https://lab.example/team',
        topics=None, parent=None, hop=1):
    return {'kind': 'person', 'name_raw': name, 'affiliation_raw': affiliation, 'country': country, 'channel': 'funding-de-ch',
            'signal_type': signal_type, 'strength': 'medium', 'date': date, 'evidence_url': url, 'hop_depth': hop,
            'snippet': f'{name} on the team page', 'topics': topics or [], 'parent': parent}


def person(name, affiliation, country, role_class, group, **extra):
    base = {'name': name, 'ids': {}, 'channels_hit': ['funding-de-ch'], 'hop_depth': 1, 'merge_confidence': 'high',
            'signals': [sig(name, affiliation, country, topics=['Vision-language  models'])], 'topics': ['Vision-language  models'],
            'current_affiliation': affiliation, 'country': country, 'role_class': role_class, 'role_confidence': 'high',
            'role_evidence': 'rule 1: title', 'group': group, 'group_evidence': 'rule 1: team page', 'tier': 4}
    base.update(extra)
    return base


def args(**over):
    ns = argparse.Namespace(date=datetime.date(2026, 10, 14), window_months=36, region='EU27+UK+CH+NO', region_core='DE+CH',
                            max_rows=0, domain='multimodal AI')
    for key, value in over.items():
        setattr(ns, key, value)
    return ns


class FakeGeocoder:
    def __init__(self, table):
        self.table, self.calls = table, []

    def locate(self, name, country):
        self.calls.append((name, country))
        return self.table.get(name)


class InstitutionNameTests(unittest.TestCase):
    def test_aliases_and_pipe_segments_fold_to_one_name(self):
        aliases = {'ETH Zurich': ['ETH Zürich', 'Eidgenössische Technische Hochschule Zürich']}
        self.assertEqual(canonical_institution('ETH Zürich', aliases), 'ETH Zurich')
        self.assertEqual(canonical_institution('Universiteit van Amsterdam||Faculteit der Natuurwetenschappen', {}), 'Universiteit van Amsterdam')
        self.assertEqual(canonical_institution('  TU   Darmstadt ', {}), 'TU Darmstadt')
        self.assertEqual(canonical_institution('', {}), '')
        self.assertEqual(canonical_institution('ETH Zürich, Robotic Systems Lab', aliases), 'ETH Zurich')
        self.assertEqual(canonical_institution('Helmholtz Munich / TUM', {}), 'Helmholtz Munich')
        self.assertEqual(canonical_institution('Graz University of Technology; EPFL', {}), 'Graz University of Technology')
        self.assertEqual(canonical_institution('Fraunhofer, Munich', aliases), 'Fraunhofer, Munich')

    def test_country_centroid_covers_region_and_jitters_deterministically(self):
        for code in ('DE', 'CH', 'NO', 'GB', 'MT'):
            with self.subTest(code=code):
                self.assertIsNotNone(country_centroid(code, 'Some Institute'))
        a = country_centroid('DE', 'Institute A')
        b = country_centroid('DE', 'Institute B')
        self.assertEqual(a, country_centroid('DE', 'Institute A'))
        self.assertNotEqual(a, b)
        self.assertLess(abs(a[0] - b[0]), 2)
        self.assertIsNone(country_centroid('XX', 'Nowhere'))


class BuildDataTests(unittest.TestCase):
    def setUp(self):
        self.persons = [
            person('Zeynep Akata', 'Technical University of Munich', 'DE', 'professor', 'Zeynep Akata @ Technical University of Munich',
                   homepage='https://eml-munich.de', ids={'orcid': '0000-0002-1432-7747'}),
            person('A Student', 'TUM', 'DE', 'phd_student', 'Zeynep Akata @ Technical University of Munich'),
            person('Cees Snoek', 'University of Amsterdam', 'NL', 'professor', 'Cees Snoek @ University of Amsterdam'),
            person('Lone Postdoc', 'Unknown Institute', 'FR', 'researcher', ''),
            person('Far Away', 'MIT', 'US', 'professor', ''),
        ]
        self.geo = FakeGeocoder({'Technical University of Munich': (48.15, 11.57, 'Munich', 'ror:https://ror.org/02kkvpp62'),
                                 'University of Amsterdam': (52.37, 4.9, 'Amsterdam', 'ror:https://ror.org/04dkp9463')})

    def test_institutions_groups_and_persons_are_aggregated_with_evidence(self):
        data = build_data(self.persons, args(), self.geo)
        inst = {i['name']: i for i in data['institutions']}
        self.assertEqual(set(inst), {'Technical University of Munich', 'University of Amsterdam', 'Unknown Institute'})
        self.assertEqual(inst['Technical University of Munich']['person_count'], 2)
        self.assertEqual(inst['Technical University of Munich']['group_count'], 1)
        self.assertEqual(inst['Technical University of Munich']['geo_source'], 'ror:https://ror.org/02kkvpp62')
        self.assertEqual(inst['Unknown Institute']['geo_source'], 'country centroid')
        self.assertEqual(inst['Unknown Institute']['country'], 'FR')
        self.assertEqual([g['group'] for g in data['groups']][:2],
                         ['Zeynep Akata @ Technical University of Munich', 'Cees Snoek @ University of Amsterdam'])
        akata = next(g for g in data['groups'] if g['pi_name'] == 'Zeynep Akata')
        self.assertEqual(akata['institution_key'], 'Technical University of Munich')
        self.assertEqual(akata['tier'], 1)
        self.assertEqual(akata['member_count'], 2)
        names = {p['name'] for p in data['persons']}
        self.assertIn('Lone Postdoc', names)
        self.assertNotIn('Far Away', names)
        student = next(p for p in data['persons'] if p['name'] == 'A Student')
        self.assertEqual(student['institution_key'], 'Technical University of Munich')
        self.assertEqual(student['group'], 'Zeynep Akata @ Technical University of Munich')
        self.assertEqual(student['topics'], ['Vision-language  models'])
        self.assertEqual(student['signals'][0]['evidence_url'], 'https://lab.example/team')
        self.assertEqual(student['group_evidence'], 'rule 1: team page')
        self.assertEqual(data['meta']['persons'], 4)
        self.assertEqual(data['meta']['out_of_region'], 1)
        self.assertEqual(data['meta']['window_start'], '2023-10-14')
        self.assertEqual(self.geo.calls.count(('Technical University of Munich', 'DE')), 1)

    def test_group_leader_outside_the_roster_is_named_but_not_linked(self):
        # The leader was cut from the roster (out of region here); the student's group still shows.
        far = person('Far Student', 'MIT', 'US', 'phd_student', 'Far Away @ MIT')
        local = person('Home Student', 'TUM', 'DE', 'phd_student', 'Gone Leader @ Technical University of Munich')
        data = build_data(self.persons + [far, local], args(), self.geo)
        groups = {g['pi_name']: g for g in data['groups']}
        self.assertNotIn('Far Away', groups)
        self.assertFalse(groups['Gone Leader']['pi_in_roster'])
        self.assertTrue(groups['Zeynep Akata']['pi_in_roster'])
        self.assertIn('g.pi_in_roster ?', render_html(data))

    def test_spelling_variants_and_sub_units_share_one_marker(self):
        persons = self.persons + [
            person('Lab Member', 'Technical University of Munich, Chair of X', 'DE', 'phd_student', ''),
            person('Shouting Member', 'TECHNICAL UNIVERSITY OF MUNICH', 'DE', 'researcher', ''),
            person('Comma Only', 'Fraunhofer, Munich', 'DE', 'researcher', ''),
        ]
        data = build_data(persons, args(), self.geo)
        inst = {i['name']: i['person_count'] for i in data['institutions']}
        self.assertEqual(inst['Technical University of Munich'], 4)
        self.assertEqual(inst['Fraunhofer, Munich'], 1)
        member = next(p for p in data['persons'] if p['name'] == 'Lab Member')
        self.assertEqual(member['institution_key'], 'Technical University of Munich')
        self.assertEqual(member['current_affiliation'], 'Technical University of Munich, Chair of X')

    def test_summaries_sidecar_attaches_to_groups_and_persons(self):
        summaries = {'groups': {'Zeynep Akata @ Technical University of Munich': {'en': 'Explainable multimodal models.', 'zh': '可解释多模态模型。'}},
                     'persons': {'A Student': {'en': 'Works on captioning.'}}}
        data = build_data(self.persons, args(), self.geo, summaries)
        akata = next(g for g in data['groups'] if g['pi_name'] == 'Zeynep Akata')
        self.assertEqual(akata['summary']['zh'], '可解释多模态模型。')
        self.assertEqual(next(p for p in data['persons'] if p['name'] == 'A Student')['summary'], {'en': 'Works on captioning.'})
        self.assertNotIn('summary', next(p for p in data['persons'] if p['name'] == 'Cees Snoek'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'summaries.json'
            path.write_text('[]', encoding='utf-8')
            with self.assertRaises(SystemExit):
                talent_map.load_summaries(str(path))
            self.assertEqual(talent_map.load_summaries(None), {})

    FACETS = [{'id': 'modality', 'label': {'en': 'modality', 'zh': '模态'}, 'tags': [
        {'id': 'vision-language', 'label': {'en': 'vision–language', 'zh': '视觉-语言'}, 'keywords': ['vision-language', 'vlm']},
        {'id': 'audio', 'label': {'en': 'speech', 'zh': '语音'}, 'keywords': ['speech', 'audio']}]}]

    def test_facets_tag_persons_and_groups_from_record_phrases(self):
        from person_fields import tags_for
        self.assertEqual(tags_for(['Vision Language Models for robots'], [], self.FACETS), ['vision-language'])
        self.assertEqual(tags_for(['A VLM benchmark', 'speech-to-text'], [], self.FACETS), ['vision-language', 'audio'])
        self.assertEqual(tags_for(['audiovisual'], [], self.FACETS), [])  # whole words only
        self.assertEqual(tags_for(['anything'], [], []), [])

    def test_snippets_and_parents_need_two_distinct_keywords(self):
        from person_fields import facet_texts, tags_for
        self.assertEqual(tags_for([], ['A VLM benchmark', 'speech-to-text'], self.FACETS), [])
        self.assertEqual(tags_for([], ['A VLM benchmark', 'Vision_Language grounding'], self.FACETS), ['vision-language'])
        self.assertEqual(tags_for([], ['A VLM benchmark', 'another VLM', 'vision language', 'vision-language'], self.FACETS),
                         ['vision-language'])
        self.assertEqual(tags_for([], ['VLM', 'another vlm'], self.FACETS), [])
        self.assertEqual(tags_for([], ['speech and audio'], self.FACETS), ['audio'])
        self.assertEqual(tags_for(['vision'], ['language'], self.FACETS), [])  # a keyword never spans two phrases
        record = {'topics': ['Topic A'], 'signals': [{'topics': ['Topic B'], 'snippet': 'Snippet', 'parent': 'Parent', 'note': 'x'}]}
        self.assertEqual(facet_texts(record), (['Topic A', 'Topic B'], ['Snippet', 'Parent']))
        data = build_data(self.persons, args(), self.geo, facets=self.FACETS)
        student = next(p for p in data['persons'] if p['name'] == 'A Student')
        self.assertEqual(student['tags'], ['vision-language'])
        akata = next(g for g in data['groups'] if g['pi_name'] == 'Zeynep Akata')
        self.assertEqual(akata['tags'], [['vision-language', 2]])
        self.assertEqual(data['meta']['facets'][0]['tags'][1], {'id': 'audio', 'label': {'en': 'speech', 'zh': '语音'}})
        self.assertNotIn('keywords', json.dumps(data['meta']))
        self.assertEqual(build_data(self.persons, args(), self.geo)['meta']['facets'], [])

    def test_coauthor_only_members_are_counted_apart(self):
        coauthor = person('Paper Coauthor', 'Technical University of Munich', 'DE', 'researcher',
                          'Zeynep Akata @ Technical University of Munich', group_link='coauthor', topics=['speech recognition'],
                          signals=[sig('Paper Coauthor', 'Technical University of Munich', 'DE', topics=['speech recognition'])])
        data = build_data(self.persons + [coauthor], args(), self.geo, facets=self.FACETS)
        self.assertEqual(next(p for p in data['persons'] if p['name'] == 'Paper Coauthor')['group_link'], 'coauthor')
        self.assertEqual(next(p for p in data['persons'] if p['name'] == 'A Student')['group_link'], '')
        akata = next(g for g in data['groups'] if g['pi_name'] == 'Zeynep Akata')
        self.assertEqual(akata['tags'], [['vision-language', 2]])
        self.assertEqual(akata['member_count'], 3)
        html = render_html(data)
        for snippet in ("coauthorsOnly: 'coauthors only'", "coauthorsOnly: '仅合著'", "p.group_link === 'coauthor'"):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, html)

    def test_facets_file_is_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'facets.json'
            path.write_text(json.dumps({'facets': self.FACETS}), encoding='utf-8')
            self.assertEqual(talent_map.load_facets(str(path))[0]['id'], 'modality')
            for bad in ('[]', '{"facets": [{"id": "x"}]}', json.dumps({'facets': self.FACETS + self.FACETS})):
                path.write_text(bad, encoding='utf-8')
                with self.assertRaises(SystemExit):
                    talent_map.load_facets(str(path))
            self.assertEqual(talent_map.load_facets(None), [])
        template = Path(__file__).resolve().parents[1] / 'assets' / 'facets.template.json'
        self.assertTrue(talent_map.load_facets(str(template)))

    def test_html_embeds_data_and_needs_no_build_step(self):
        data = build_data(self.persons, args(), self.geo)
        html = render_html(data)
        self.assertTrue(html.startswith('<!doctype html>'))
        self.assertIn('leaflet@1.9.4', html)
        self.assertIn(json.dumps('Zeynep Akata'), html)
        self.assertIn('https://lab.example/team', html)
        self.assertNotIn('</script>', json.dumps(data))
        self.assertEqual(html.count('<script id="talent-data"'), 1)

    def test_five_tiers_have_labels_colours_and_filters(self):
        data = build_data(self.persons, args(), self.geo)
        self.assertEqual({p['name']: p['tier'] for p in data['persons']},
                         {'Zeynep Akata': 1, 'A Student': 3, 'Cees Snoek': 2, 'Lone Postdoc': 5})
        html = render_html(data)
        for snippet in ('--t5:', '.badge.t5', "['1', '2', '3', '4', '5']", '[1, 2, 3, 4, 5].map',
                        "5: 'T5 everyone else in the region'", "2: 'T2 extended-region professor or group leader'",
                        "5: 'T5 区域内其他人'", "5: 'T5 others'", "5: 'T5 其他'"):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, html)


class GeocoderTests(unittest.TestCase):
    def test_cache_hits_skip_the_network_and_offline_never_calls_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'geo.json'
            cache.write_text(json.dumps({'ETH Zurich|CH': [47.37, 8.55, 'Zurich', 'ror:https://ror.org/05a28rw58']}), encoding='utf-8')
            calls = []

            def fetch(url):
                calls.append(url)
                return {'items': []}

            geocoder = Geocoder(str(cache), fetch=fetch)
            self.assertEqual(geocoder.locate('ETH Zurich', 'CH'), (47.37, 8.55, 'Zurich', 'ror:https://ror.org/05a28rw58'))
            self.assertEqual(calls, [])
            offline = Geocoder(str(cache), fetch=fetch, offline=True)
            self.assertIsNone(offline.locate('TU Wien', 'AT'))
            self.assertEqual(calls, [])

    def test_manual_table_comes_before_cache_and_ror_when_the_country_agrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'geo.json'
            cache.write_text(json.dumps({'Kyutai|FR': None}), encoding='utf-8')
            calls = []

            def fetch(url):
                calls.append(url)
                return {'items': []}

            overrides = {'Kyutai': [48.8567, 2.3522, 'Paris', 'FR'], 'Wayve': [51.5072, -0.1275, 'London', 'GB']}
            geocoder = Geocoder(str(cache), fetch=fetch, overrides=overrides)
            self.assertEqual(geocoder.locate('Kyutai', 'FR'), (48.8567, 2.3522, 'Paris', 'manual'))
            self.assertEqual(geocoder.locate('Wayve', 'UK'), (51.5072, -0.1275, 'London', 'manual'))
            self.assertEqual(geocoder.locate('Kyutai', ''), (48.8567, 2.3522, 'Paris', 'manual'))
            self.assertIsNone(geocoder.locate('Kyutai', 'DE'))  # another country: the table does not apply
            self.assertEqual(len(calls), 1)
            geocoder.save()
            self.assertNotIn('Kyutai|FR', [k for k, v in json.loads(cache.read_text(encoding='utf-8')).items() if v])

    def test_manual_table_file_is_validated_and_every_entry_has_a_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'geo-overrides.json'
            good = {'_comment': 'x', 'overrides': {'Kyutai': [48.8567, 2.3522, 'Paris', 'FR']},
                    '_sources': {'Kyutai': ['https://kyutai.org/']}}
            path.write_text(json.dumps(good), encoding='utf-8')
            self.assertEqual(talent_map.load_geo_overrides(str(path)), good['overrides'])
            for bad in ({'overrides': {'Kyutai': [48.8, 2.3, 'Paris']}}, {'overrides': {'Kyutai': ['48.8', 2.3, 'Paris', 'FR']}},
                        {'overrides': {'Kyutai': [48.8, 2.3, 'Paris', 'France']}}, {'overrides': []}):
                path.write_text(json.dumps(bad), encoding='utf-8')
                with self.assertRaises(SystemExit):
                    talent_map.load_geo_overrides(str(path))
            self.assertEqual(talent_map.load_geo_overrides(str(Path(tmp) / 'missing.json')), {})
        asset = Path(__file__).resolve().parents[1] / 'assets' / 'geo-overrides.json'
        table = talent_map.load_geo_overrides(str(asset))
        self.assertTrue(table)
        sources = json.loads(asset.read_text(encoding='utf-8'))['_sources']
        self.assertEqual(set(table), set(sources))

    def test_page_names_the_manual_table_as_the_position_source(self):
        html = render_html(build_data([person('Kyutai Researcher', 'Kyutai', 'FR', 'researcher', '')], args(),
                                      FakeGeocoder({'Kyutai': (48.8567, 2.3522, 'Paris', 'manual')})))
        self.assertIn('"geo_source": "manual"', html)
        for snippet in ("manualPos: 'position from the manual table'", "manualPos: '位置来自手工表'", "inst.geo_source === 'manual'"):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, html)

    def test_ror_hit_in_another_country_is_rejected_and_misses_are_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'geo.json'
            answers = {'TU Wien': {'items': [{'id': 'https://ror.org/04d836q62', 'locations': [
                {'geonames_details': {'lat': 48.2, 'lng': 16.37, 'name': 'Vienna', 'country_code': 'AT'}}]}]},
                       'Sorbonne': {'items': [{'id': 'https://ror.org/x', 'locations': [
                           {'geonames_details': {'lat': 1.0, 'lng': 2.0, 'name': 'Elsewhere', 'country_code': 'US'}}]}]}}
            calls = []

            def fetch(url):
                calls.append(url)
                key = next(k for k in answers if k.replace(' ', '%20') in url)
                return answers[key]

            geocoder = Geocoder(str(cache), fetch=fetch)
            self.assertEqual(geocoder.locate('TU Wien', 'AT'), (48.2, 16.37, 'Vienna', 'ror:https://ror.org/04d836q62'))
            self.assertIsNone(geocoder.locate('Sorbonne', 'FR'))
            self.assertIsNone(geocoder.locate('Sorbonne', 'FR'))
            self.assertEqual(len(calls), 2)
            geocoder.save()
            stored = json.loads(cache.read_text(encoding='utf-8'))
            self.assertEqual(stored['Sorbonne|FR'], None)
            self.assertEqual(stored['TU Wien|AT'][2], 'Vienna')


if __name__ == '__main__':
    unittest.main()
