import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import publish_site
from publish_site import publish
from test_group_export import validate

ISSUES = 'https://github.com/likun-fang/talent-scout/issues/new?template=correction.yml'


def group(pi, institution, last_verified='2026-10-15', **fields):
    slug = re.sub(r'\W+', '-', f'{pi} {institution}'.lower()).strip('-')
    return {'id': slug, 'pi': {'name': pi, 'role_class': 'professor', 'homepage': ''},
            'institution': {'name': institution, 'country': 'DE', 'ids': {},
                            'location': {'lat': 48.1, 'lng': 11.6, 'city': 'Munich', 'source': 'manual'}},
            'homepage': 'https://lab.example', 'tags': [], 'topics': ['vision-language models'],
            'members': [{'name': 'Ben Ott', 'role_class': 'phd_student', 'link': 'team'}], 'coauthors_count': 0,
            'active_funding': [], 'open_source': [], 'evidence_urls': ['https://lab.example'],
            'last_verified': last_verified, 'last_verified_from': 'final_pass', 'sources': ['funding-eu'],
            'as_of': '2026-10-15', **fields}


def groups_doc(*groups, domain='multimodal AI'):
    return {'meta': {'domain': domain, 'as_of': '2026-10-15', 'region': 'EU27+UK+CH+NO', 'window_start': '2023-10-15',
                     'facets': []},
            'groups': list(groups)}


class Fixture:
    """A run directory with site/groups.json, a known-groups file and an empty docs directory."""

    def __init__(self, tmp: str, doc: dict, known: list[dict]):
        self.root = Path(tmp)
        self.run = self.root / 'run'
        (self.run / 'site').mkdir(parents=True)
        (self.run / 'site' / 'groups.json').write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        self.known = self.root / 'known.json'
        self.known.write_text(json.dumps({'groups': known}), encoding='utf-8')
        self.docs = self.root / 'docs'

    def publish(self, slug='multimodal-ai'):
        return publish(self.run, slug, self.docs, self.known)


KNOWN = [{'pi': 'Anna Meyer', 'institution': 'TUM'}]


class PublishTests(unittest.TestCase):
    def test_it_writes_the_field_page_its_data_the_field_index_and_the_about_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, groups_doc(group('Anna Meyer', 'TUM'), group('Cara Lin', 'TUM', members=[])), KNOWN)
            site.publish()
            self.assertEqual(sorted(p.relative_to(site.docs).as_posix() for p in site.docs.rglob('*') if p.is_file()),
                             ['about.html', 'index.html', 'multimodal-ai/groups.json', 'multimodal-ai/index.html'])
            page = (site.docs / 'multimodal-ai' / 'index.html').read_text(encoding='utf-8')
            self.assertIn(f'const CORRECTION_URL = {json.dumps(ISSUES)};', page)
            self.assertIn('const ABOUT_URL = "../about.html";', page)
            self.assertIn('Cara Lin', page)
            index = (site.docs / 'index.html').read_text(encoding='utf-8')
            self.assertIn('href="multimodal-ai/"', index)
            self.assertIn('multimodal AI', index)
            self.assertIn('href="about.html"', index)

    def test_the_published_data_carries_the_check_values_and_still_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, groups_doc(group('Anna Meyer', 'TUM'), group('Cara Lin', 'TUM', last_verified='2024-01-10')),
                           KNOWN + [{'pi': 'Dan Roe', 'institution': 'ETH Zurich'}])
            # 1 of 2 known groups and 1 of 2 groups stale miss the limits: widen them for this fixture only.
            old = publish_site.RECALL_MIN, publish_site.STALE_MAX
            publish_site.RECALL_MIN, publish_site.STALE_MAX = 0.5, 0.5
            try:
                site.publish()
            finally:
                publish_site.RECALL_MIN, publish_site.STALE_MAX = old
            doc = json.loads((site.docs / 'multimodal-ai' / 'groups.json').read_text(encoding='utf-8'))
            self.assertEqual(doc['meta']['checks'], {'recall': {'found': 1, 'known': 2}, 'stale': {'groups': 1, 'of': 2,
                             'verified_since': '2025-10-15'}, 'banned_source_hits': 0, 'sample': 2})
            schema = json.loads((ROOT / 'assets/groups.schema.json').read_text(encoding='utf-8'))
            self.assertEqual(validate(doc, schema, schema), [])

    def test_the_about_page_has_four_parts_in_two_languages_with_the_current_check_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, groups_doc(group('Anna Meyer', 'TUM')), KNOWN)
            site.publish()
            about = (site.docs / 'about.html').read_text(encoding='utf-8')
            for part in ('data-part="what"', 'data-part="sources"', 'data-part="method"', 'data-part="corrections"'):
                with self.subTest(part=part):
                    self.assertEqual(about.count(part), 2)  # once per language
            self.assertIn('lang="zh"', about)
            self.assertIn('1/1', about)  # recall of the published field
            self.assertIn('issues/new?template=opt-out.yml', about)
            self.assertIn('issues/new?template=correction.yml', about)
            self.assertIn('members not yet collected', about)
            self.assertIn('成员未采集', about)

    def test_a_second_field_joins_the_index_and_the_first_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, groups_doc(group('Anna Meyer', 'TUM')), KNOWN)
            site.publish('multimodal-ai')
            (site.run / 'site' / 'groups.json').write_text(json.dumps(groups_doc(group('Anna Meyer', 'TUM'), domain='embodied AI')),
                                                           encoding='utf-8')
            site.publish('embodied-ai')
            index = (site.docs / 'index.html').read_text(encoding='utf-8')
            self.assertLess(index.index('href="embodied-ai/"'), index.index('href="multimodal-ai/"'))
            self.assertTrue((site.docs / 'multimodal-ai' / 'index.html').exists())

    def test_nothing_under_docs_names_a_local_path_or_an_email_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, groups_doc(group('Anna Meyer', 'TUM')), KNOWN)
            site.publish()
            for path in site.docs.rglob('*'):
                if path.is_file():
                    text = path.read_text(encoding='utf-8')
                    with self.subTest(path=path.name):
                        self.assertNotIn(tmp, text)
                        self.assertEqual(publish_site.private_text(text), [])


class RefusalTests(unittest.TestCase):
    def refused(self, doc, known=KNOWN, slug='multimodal-ai') -> str:
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, doc, known)
            with self.assertRaises(SystemExit) as stop:
                site.publish(slug)
            self.assertFalse(site.docs.exists() and any(site.docs.rglob('*')), 'a refused publication writes nothing')
            return str(stop.exception)

    def test_a_failed_recall_check_stops_the_publication(self):
        message = self.refused(groups_doc(group('Anna Meyer', 'TUM')), KNOWN + [{'pi': 'Dan Roe', 'institution': 'ETH Zurich'}])
        self.assertIn('recall 1/2', message)

    def test_a_failed_staleness_check_stops_the_publication(self):
        message = self.refused(groups_doc(group('Anna Meyer', 'TUM', last_verified='2024-01-10')))
        self.assertIn('stale 1/1', message)

    def test_a_linkedin_key_or_url_stops_the_publication(self):
        for extra in ({'linkedin_url': 'https://example.org'}, {'evidence_urls': ['https://www.linkedin.com/in/anna']}):
            with self.subTest(extra=extra):
                self.assertIn('LinkedIn', self.refused(groups_doc(group('Anna Meyer', 'TUM', **extra))))

    def test_a_percent_encoded_linkedin_host_stops_the_publication(self):
        message = self.refused(groups_doc(group('Anna Meyer', 'TUM', homepage='https://www.%6cinkedin.com/in/anna')))
        self.assertIn('LinkedIn', message)

    def test_an_earlier_field_with_malformed_check_values_stops_the_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, groups_doc(group('Anna Meyer', 'TUM')), KNOWN)
            site.publish('old-field')
            old = site.docs / 'old-field' / 'groups.json'
            doc = json.loads(old.read_text(encoding='utf-8'))
            doc['meta']['checks']['sample'] = '<img src=x onerror=alert(1)>'
            old.write_text(json.dumps(doc), encoding='utf-8')
            with self.assertRaises(SystemExit) as stop:
                site.publish('multimodal-ai')
            self.assertIn('old-field', str(stop.exception))
            self.assertFalse((site.docs / 'multimodal-ai').exists())

    def test_a_notes_field_stops_the_publication(self):
        message = self.refused(groups_doc(group('Anna Meyer', 'TUM', notes='moved in 2025')))
        self.assertIn('$.groups[0].notes', message)

    def test_an_email_address_or_a_local_path_stops_the_publication(self):
        for topic in ('write to anna.meyer@tum.de', '/Users/someone/projects/x', 'runs/multimodal-ai-2026-10-14/site',
                      'file:///tmp/x.html', '../runs/private/site', '/Volumes/Private/run/site', '"anna meyer"@tum.de',
                      'line one\n/Users/alice/private', '~/projects/x', 'mailto:anna@tum.de', '/srv/private/run/site',
                      'C:/work/private/run/site', '\\\\server\\private\\run', '/Shared Data/private/run',
                      '/data+archive/private/run'):
            with self.subTest(topic=topic):
                self.assertIn('private', self.refused(groups_doc(group('Anna Meyer', 'TUM', topics=[topic]))))

    def test_slashes_in_prose_are_not_paths(self):
        for topic in ('vision / language / action', 'audio-visual/text models', '3D/4D reconstruction', 'w/o labels'):
            with self.subTest(topic=topic):
                self.assertEqual(publish_site.private_values({'topics': [topic]}), [])

    def test_a_slug_that_is_not_a_plain_name_is_refused(self):
        for slug in ('../x', 'Multimodal AI', ''):
            with self.subTest(slug=slug):
                self.assertIn('slug', self.refused(groups_doc(group('Anna Meyer', 'TUM')), slug=slug))

    def test_a_run_without_site_groups_json_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as stop:
                publish(Path(tmp), 'multimodal-ai', Path(tmp) / 'docs', Path(tmp) / 'known.json')
            self.assertIn('groups.json', str(stop.exception))


class WriteTests(unittest.TestCase):
    def test_a_failed_write_leaves_the_earlier_publication_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, groups_doc(group('Anna Meyer', 'TUM')), KNOWN)
            site.publish()
            before = {p: p.read_bytes() for p in site.docs.rglob('*') if p.is_file()}
            (site.run / 'site' / 'groups.json').write_text(json.dumps(groups_doc(group('Anna Meyer', 'TUM'), group('Cara Lin', 'TUM'))),
                                                           encoding='utf-8')
            original, calls = publish_site.os.replace, []

            def failing_replace(source, target):
                calls.append(target)
                if len(calls) == 2:
                    raise OSError('disk full')
                return original(source, target)
            publish_site.os.replace = failing_replace
            try:
                with self.assertRaises(SystemExit):
                    site.publish()
            finally:
                publish_site.os.replace = original
            self.assertEqual({p: p.read_bytes() for p in site.docs.rglob('*') if p.is_file()}, before)


    def test_a_failed_staging_write_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, groups_doc(group('Anna Meyer', 'TUM')), KNOWN)
            original = publish_site.os.fdopen

            def failing_fdopen(*args, **kwargs):
                handle = original(*args, **kwargs)
                handle.write = lambda text: (_ for _ in ()).throw(OSError('disk full'))
                return handle
            publish_site.os.fdopen = failing_fdopen
            try:
                with self.assertRaises(SystemExit):
                    site.publish()
            finally:
                publish_site.os.fdopen = original
            self.assertEqual([p.name for p in site.docs.rglob('.publish-*')], [])


class CommandLineTests(unittest.TestCase):
    def test_main_publishes_with_the_known_groups_of_the_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Fixture(tmp, groups_doc(group('Anna Meyer', 'TUM')), KNOWN)
            old, sys.argv = sys.argv, ['publish_site.py', str(site.run), 'multimodal-ai', '--out', str(site.docs),
                                       '--known', str(site.known)]
            try:
                publish_site.main()
            finally:
                sys.argv = old
            self.assertTrue((site.docs / 'multimodal-ai' / 'groups.json').exists())


class IssueFormTests(unittest.TestCase):
    def test_the_correction_form_prefills_the_group_and_blank_issues_are_off(self):
        forms = ROOT / '.github' / 'ISSUE_TEMPLATE'
        correction = (forms / 'correction.yml').read_text(encoding='utf-8')
        self.assertIn('id: group', correction)  # the map's &group=<id> fills this field
        self.assertIn('id: source', correction)
        opt_out = (forms / 'opt-out.yml').read_text(encoding='utf-8')
        for field in ('id: name', 'id: group', 'id: scope'):
            with self.subTest(field=field):
                self.assertIn(field, opt_out)
        self.assertNotIn('reason', opt_out.casefold().replace('no reason', ''))
        self.assertIn('blank_issues_enabled: false', (forms / 'config.yml').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
