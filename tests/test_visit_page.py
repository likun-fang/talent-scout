import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import visit_page
from visit_page import TextPage, batch, classify, is_linkedin, linkedin_sections, validate_url, visit

PUBLIC_PROFILE = '\n'.join([
    'Skip to main content', 'LinkedIn', 'Sign in', 'Join now', 'Alex Example',
    'Research Scientist at Example Lab', 'Join to view profile', 'Experience', 'Research Scientist',
    'Example Lab', '2023 - Present', '3 years', 'PhD student', 'Example University', '2018 - 2023',
    'Education', 'Example University', 'PhD, Robotics', '2018 - 2023', 'View Alex’s full profile',
    'Join to view full profile', 'Other similar profiles',
])


class ReaderTests(unittest.TestCase):
    def test_html_text_and_links(self):
        parser = TextPage('https://example.org/lab/')
        parser.feed('<html><head><title>Team</title><script>secret</script></head><body>'
                    '<h1>Alex</h1><p>PhD <strong>student</strong></p>'
                    '<div hidden>old role</div><div style="display: none">hidden</div>'
                    '<a href="/person">Profile</a><a href="mailto:x@example.org">Contact</a>'
                    '<a href="http://127.0.0.1/admin">local</a></body></html>')
        result = parser.result()
        self.assertEqual(result['title'], 'Team')
        self.assertIn('PhD student', result['text'])
        for word in ('secret', 'old role', 'hidden'):
            self.assertNotIn(word, result['text'])
        self.assertEqual(result['links'], ['https://example.org/person'])

    def test_access_outcomes(self):
        for record, expected in [
            ({'http_status': 429}, 'rate_limited'),
            ({'http_status': 403}, 'blocked'),
            ({'http_status': 999}, 'blocked'),
            ({'final_url': 'https://www.linkedin.com/authwall?trk=x', 'text': 'Join'}, 'login_required'),
            ({'final_url': 'https://www.linkedin.com/in/example', 'title': 'Sign In | LinkedIn'}, 'login_required'),
            ({'final_url': 'https://www.linkedin.com/', 'title': '领英: 登录或注册'}, 'login_required'),
            ({'final_url': 'https://www.linkedin.com/uas/login'}, 'login_required'),
            ({'text': 'Verify you are human'}, 'challenge'),
            ({'password_form': True}, 'login_required'),
            ({'http_status': 404}, 'http_error'),
            ({'text': '   '}, 'empty'),
            ({'text': 'Alex — Research Engineer. Sign in newsletter'}, 'readable'),
        ]:
            with self.subTest(expected=expected, record=record):
                self.assertEqual(classify(record), expected)

    def test_public_profile_with_join_buttons_is_readable(self):
        record = {'http_status': 200, 'final_url': 'https://www.linkedin.com/in/alex-example',
                  'title': 'Alex Example - Research Scientist at Example Lab | LinkedIn', 'text': PUBLIC_PROFILE}
        self.assertEqual(classify(record), 'readable')

    def test_linkedin_record_keeps_excerpts_only(self):
        page = {'http_status': 200, 'final_url': 'https://www.linkedin.com/in/alex-example',
                'title': 'Alex Example - Research Scientist at Example Lab | LinkedIn', 'text': PUBLIC_PROFILE}
        with patch('visit_page.http_read', return_value=page):
            record = visit('https://www.linkedin.com/in/alex-example')
            full = visit('https://www.linkedin.com/in/alex-example', full_text=True)
        self.assertEqual(record['status'], 'readable')
        self.assertEqual(record['headline'], 'Alex Example - Research Scientist at Example Lab')
        self.assertEqual(record['sections']['experience'][:3], ['Research Scientist', 'Example Lab', '2023 - Present'])
        self.assertEqual(record['sections']['education'][0], 'Example University')
        self.assertEqual(record['text'], '')
        self.assertEqual(record['links'], [])
        self.assertIn('text_dropped', record)
        self.assertFalse(record['role_verified'])
        self.assertIn('Other similar profiles', full['text'])

    def test_sections_stop_at_next_heading(self):
        sections = linkedin_sections(PUBLIC_PROFILE)
        self.assertNotIn('Education', sections['experience'])
        self.assertNotIn('View Alex’s full profile', sections['education'])

    def test_does_not_verify_roles_and_marks_truncation(self):
        with patch('visit_page.http_read', return_value={'text': 'PhD student at Example', 'final_url': 'https://example.org/person'}):
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
        for url in ('file:///etc/passwd', 'ftp://example.org', 'https://user:password@example.org', 'https:///missing',
                    'http://localhost/x', 'http://127.0.0.1/', 'http://10.0.0.1/', 'http://169.254.169.254/latest',
                    'http://[::1]/', 'http://[fd00::1]/', 'http://host.local/', 'http://svc.internal/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)
        for url in ('https://example.org/', 'http://93.184.216.34/', 'https://uk.linkedin.com/in/example'):
            self.assertEqual(validate_url(url), url)
        self.assertTrue(is_linkedin('https://uk.linkedin.com/in/example'))
        self.assertFalse(is_linkedin('https://linkedin.com.example.org'))

    def test_batch_stops_at_first_linkedin_refusal(self):
        responses = {
            'https://www.linkedin.com/in/a': {'http_status': 200, 'final_url': 'https://www.linkedin.com/in/a',
                                               'title': 'A - X | LinkedIn', 'text': PUBLIC_PROFILE},
            'https://lab.example.org/team': {'http_status': 200, 'final_url': 'https://lab.example.org/team', 'text': 'Team: A, B'},
            'https://www.linkedin.com/in/b': {'http_status': 999, 'final_url': 'https://www.linkedin.com/in/b', 'text': ''},
            'https://www.linkedin.com/in/c': {'http_status': 200, 'final_url': 'https://www.linkedin.com/in/c', 'text': 'never read'},
        }
        urls = list(responses)
        with patch('visit_page.http_read', side_effect=lambda url, timeout: responses[url]), \
                patch('visit_page.time.sleep') as sleep, tempfile.TemporaryDirectory() as tmp:
            summary = batch(urls, Path(tmp), 5.0)
            files = sorted(Path(tmp).iterdir())
            first = json.loads(files[0].read_text())
        self.assertEqual((summary['read'], summary['refused'], summary['other']), (2, 1, 0))
        self.assertEqual(summary['stopped_at'], 'https://www.linkedin.com/in/b')
        self.assertEqual(summary['remaining'], ['https://www.linkedin.com/in/c'])
        self.assertEqual(len(files), 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(first['text'], '')
        self.assertIn('experience', first['sections'])

    def test_batch_skips_invalid_urls_without_stopping(self):
        with patch('visit_page.http_read', return_value={'text': 'ok', 'final_url': 'https://example.org/'}), \
                patch('visit_page.time.sleep'), tempfile.TemporaryDirectory() as tmp:
            summary = batch(['http://localhost/x', 'https://example.org/'], Path(tmp), 0)
        self.assertEqual((summary['read'], summary['other']), (1, 1))
        self.assertIsNone(summary['stopped_at'])


if __name__ == '__main__':
    unittest.main()
