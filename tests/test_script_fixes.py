import ast
import datetime
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import openalex_lookup as oa


class RepositoryTests(unittest.TestCase):
    def test_source_type_removes_unlisted_repository_and_blacklist_supplements(self):
        venues = [{'id': 'S1', 'name': 'Unlisted Archive', 'count': 10},
                  {'id': 'S2', 'name': 'Journal', 'count': 9},
                  {'id': 'S3', 'name': 'arXiv', 'count': 8}]
        def lookup(path, params):
            self.assertEqual(path, '/sources')
            self.assertEqual(params['filter'], 'ids.openalex:S1|S2|S3')
            return {'results': [{'id': 'https://openalex.org/S1', 'type': 'repository'},
                                {'id': 'https://openalex.org/S2', 'type': 'journal'}]}
        with patch.object(oa, 'get', side_effect=lookup):
            self.assertEqual(oa.non_repository_sources(venues), [venues[1]])
        self.assertEqual(len(venues), 3)

    def test_source_lookups_batch_empty_and_preserve_unknown_type(self):
        venues = [{'id': f'S{i}', 'name': 'Journal', 'count': i} for i in range(101)]
        with patch.object(oa, 'get', return_value={'results': []}) as lookup:
            self.assertEqual(oa.non_repository_sources(venues), venues)
            self.assertEqual(lookup.call_count, 3)
            self.assertLessEqual(max(len(call.args[1]['filter'].split('|')) for call in lookup.call_args_list), 50)
        with patch.object(oa, 'get') as lookup:
            self.assertEqual(oa.non_repository_sources([]), [])
            lookup.assert_not_called()

    def test_topic_groups_resolves_types_before_top_25_cut(self):
        def lookup(path, params):
            if path == '/sources':
                return {'results': [{'id': 'https://openalex.org/S1', 'type': 'repository'}]}
            if params['group_by'] == 'primary_location.source.id':
                return {'group_by': [{'key': 'https://openalex.org/S1', 'key_display_name': 'New Archive', 'count': 100},
                                     {'key': 'https://openalex.org/S2', 'key_display_name': 'Conference', 'count': 90}]}
            return {'group_by': []}
        with patch.object(oa, 'get', side_effect=lookup):
            result = oa.topic_groups('T1', 'DE+CH', datetime.date(2023, 10, 12), datetime.date(2026, 10, 12))
        self.assertEqual([v['id'] for v in result['venues']], ['S2'])
        self.assertEqual(oa.region_codes('DE+CH'), ['DE', 'CH'])


class FileHandleTests(unittest.TestCase):
    def test_file_open_calls_use_context_managers(self):
        root = Path(__file__).resolve().parents[1] / 'scripts'
        for name in ['table_export.py', 'merge_persons.py', 'current_affiliation.py', 'visit_page.py']:
            tree = ast.parse((root / name).read_text())
            file_calls = {id(node) for node in ast.walk(tree) if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Name) and node.func.id == 'open'}
            managed = {id(item.context_expr) for node in ast.walk(tree) if isinstance(node, ast.With) for item in node.items}
            with self.subTest(script=name):
                self.assertTrue(file_calls <= managed)


if __name__ == '__main__':
    unittest.main()
