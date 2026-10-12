import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import openalex_auth as auth
import openalex_lookup as lookup
from setup_openalex import save_key


class AuthTests(unittest.TestCase):
    def test_file_loading_and_env_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private' / 'key'
            save_key('fixture-file-key', path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with patch.dict(os.environ, {'OPENALEX_API_KEY_FILE': str(path)}, clear=True):
                self.assertEqual(auth.api_key(), 'fixture-file-key')
                os.environ['OPENALEX_API_KEY'] = 'fixture-env-key'
                self.assertEqual(auth.api_key(), 'fixture-env-key')

    def test_missing_configured_file_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'OPENALEX_API_KEY_FILE': str(Path(directory) / 'missing')}, clear=True):
                with self.assertRaises(RuntimeError):
                    auth.api_key()

    def test_header_and_failure_do_not_expose_key(self):
        with patch.dict(os.environ, {'OPENALEX_API_KEY': 'fixture-secret'}, clear=True):
            with patch.object(lookup.urllib.request, 'urlopen', side_effect=OSError('fixture-secret')) as request:
                with self.assertRaises(SystemExit) as error:
                    lookup.get('/topics', {'search': 'multimodal'})
                self.assertNotIn('fixture-secret', str(error.exception))
                req = request.call_args.args[0]
                self.assertNotIn('fixture-secret', req.full_url)
                self.assertEqual(req.get_header('Authorization'), 'Bearer fixture-secret')

    def test_anonymous_without_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True), patch.object(auth, 'DEFAULT_KEY_FILE', Path(directory) / 'missing'):
                self.assertEqual(auth.auth_headers(), {})


if __name__ == '__main__':
    unittest.main()
