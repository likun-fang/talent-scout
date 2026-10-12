import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from visit_page import TextPage, classify, is_linkedin, validate_url, visit


class ReaderTests(unittest.TestCase):
    def test_html_text_and_links(self):
        parser = TextPage('https://example.org/lab/')
        parser.feed('<html><head><title>Team</title><script>secret</script></head><body>'
                    '<h1>Alex</h1><p>PhD <strong>student</strong></p>'
                    '<div hidden>old role</div><div style="display: none">hidden</div>'
                    '<a href="/person">Profile</a><a href="mailto:x@example.org">Contact</a></body></html>')
        result = parser.result()
        self.assertEqual(result['title'], 'Team')
        self.assertIn('PhD student', result['text'])
        for word in ('secret', 'old role', 'hidden'):
            self.assertNotIn(word, result['text'])
        self.assertEqual(result['links'], ['https://example.org/person'])

    def test_access_outcomes(self):
        for record, expected in [
            ({'http_status':429}, 'rate_limited'),
            ({'http_status':403}, 'blocked'),
            ({'http_status':999}, 'blocked'),
            ({'final_url':'https://www.linkedin.com/authwall', 'text':'Join'}, 'login_required'),
            ({'final_url':'https://www.linkedin.com/in/example', 'title':'Sign In | LinkedIn'}, 'login_required'),
            ({'final_url':'https://www.linkedin.com/', 'title':'领英: 登录或注册'}, 'login_required'),
            ({'final_url':'https://www.linkedin.com/in/example', 'text':'Join to view full profile'}, 'login_required'),
            ({'text':'Verify you are human'}, 'challenge'),
            ({'password_form':True}, 'login_required'),
            ({'http_status':404}, 'http_error'),
            ({'text':'   '}, 'empty'),
            ({'text':'Alex — Research Engineer. Sign in newsletter'}, 'readable'),
        ]:
            with self.subTest(expected=expected, record=record):
                self.assertEqual(classify(record), expected)

    def test_does_not_verify_roles_and_marks_truncation(self):
        with patch('visit_page.http_read', return_value={'text':'PhD student at Example', 'final_url':'https://example.org/person'}):
            record = visit('https://example.org/person', max_chars=8)
        self.assertTrue(record['truncated'])
        self.assertFalse(record['role_verified'])
        self.assertTrue(record['needs_review'])
        self.assertEqual(len(record['text']), 8)
        self.assertIn('retrieved_at', record)

    def test_error_is_recorded_without_exception_details(self):
        with patch('visit_page.http_read', side_effect=RuntimeError('SECRET')):
            record = visit('https://example.org/person')
        self.assertEqual(record['status'], 'fetch_error')
        self.assertEqual(record['error'], 'RuntimeError')
        self.assertNotIn('SECRET', str(record))

    def test_urls(self):
        for url in ('file:///etc/passwd', 'ftp://example.org', 'https://user:password@example.org', 'https:///missing'):
            with self.assertRaises(ValueError):
                validate_url(url)
        self.assertTrue(is_linkedin('https://uk.linkedin.com/in/example'))
        self.assertFalse(is_linkedin('https://linkedin.com.example.org'))


if __name__ == '__main__':
    unittest.main()
