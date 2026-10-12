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
            ({'http_status': 200, 'text': "Making sure you're not a bot! Loading... Anubis to protect the server"}, 'challenge'),
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
            record = visit('https://example.org/person', max_chars=8, ladder=('http',))
        self.assertTrue(record['truncated'])
        self.assertFalse(record['role_verified'])
        self.assertTrue(record['needs_review'])
        self.assertEqual(len(record['text']), 8)
        self.assertIn('retrieved_at', record)

    def test_error_is_recorded_without_exception_details(self):
        with patch('visit_page.http_read', side_effect=RuntimeError('SECRET')):
            record = visit('https://example.org/person', ladder=('http',))
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
            summary = batch(urls, Path(tmp), 5.0, ladder=('http',))
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
            summary = batch(['http://localhost/x', 'https://example.org/'], Path(tmp), 0, ladder=('http',))
        self.assertEqual((summary['read'], summary['other']), (1, 1))
        self.assertIsNone(summary['stopped_at'])


if __name__ == '__main__':
    unittest.main()


class LadderTests(unittest.TestCase):
    LONG = 'Members of the lab. ' * 20

    def test_climbs_until_readable_and_records_attempts(self):
        with patch('visit_page.http_read', return_value={'http_status': 403, 'final_url': 'https://lab.example/people', 'text': ''}), \
                patch('visit_page.wayback_read', return_value={'http_status': 200, 'final_url': 'https://web.archive.org/web/2025id_/x', 'text': 'shell', 'archived_at': '20250101'}), \
                patch('visit_page.jina_read', return_value={'http_status': 200, 'final_url': 'https://lab.example/people', 'text': self.LONG, 'title': 'People'}), \
                patch('visit_page.browser_read') as browser:
            record = visit('https://lab.example/people')
        self.assertEqual(record['status'], 'readable')
        self.assertEqual(record['fetch_via'], 'jina')
        self.assertEqual([a['via'] for a in record['attempts']], ['http', 'wayback', 'jina'])
        self.assertEqual(record['attempts'][0]['status'], 'blocked')
        self.assertFalse(browser.called)

    def test_readable_http_never_climbs(self):
        with patch('visit_page.http_read', return_value={'http_status': 200, 'final_url': 'https://lab.example/people', 'text': self.LONG}), \
                patch('visit_page.wayback_read') as wayback:
            record = visit('https://lab.example/people')
        self.assertEqual(record['fetch_via'], 'http')
        self.assertFalse(wayback.called)

    def test_linkedin_never_climbs(self):
        with patch('visit_page.http_read', return_value={'http_status': 999, 'final_url': 'https://www.linkedin.com/in/x', 'text': ''}), \
                patch('visit_page.wayback_read') as wayback, patch('visit_page.jina_read') as jina:
            record = visit('https://www.linkedin.com/in/x')
        self.assertEqual(record['status'], 'blocked')
        self.assertFalse(wayback.called or jina.called)

    def test_404_only_tries_the_archive(self):
        with patch('visit_page.http_read', return_value={'http_status': 404, 'final_url': 'https://lab.example/old', 'text': ''}), \
                patch('visit_page.wayback_read', return_value={'status': 'unavailable', 'text': '', 'final_url': 'https://lab.example/old'}), \
                patch('visit_page.jina_read') as jina, patch('visit_page.browser_read') as browser:
            record = visit('https://lab.example/old')
        self.assertEqual([a['via'] for a in record['attempts']], ['http', 'wayback'])
        self.assertFalse(jina.called or browser.called)
        self.assertEqual(record['status'], 'http_error')

    def test_missing_playwright_is_recorded_not_fatal(self):
        with patch('visit_page.http_read', return_value={'http_status': 403, 'final_url': 'https://x.example/', 'text': ''}), \
                patch('visit_page.wayback_read', return_value={'status': 'unavailable', 'text': '', 'final_url': 'https://x.example/'}), \
                patch('visit_page.jina_read', return_value={'http_status': 200, 'final_url': 'https://x.example/', 'text': ''}), \
                patch('visit_page.browser_read', side_effect=ImportError):
            record = visit('https://x.example/')
        self.assertEqual(record['attempts'][-1], {'via': 'browser', 'status': 'dependency_missing'})
        self.assertEqual(record['status'], 'blocked')

    def test_jina_parses_title_and_markdown(self):
        payload = {'http_status': 200, 'final_url': 'https://r.jina.ai/https://x', 'content_type': 'text/plain',
                   'text': 'Title: People\n\nURL Source: https://x\n\nMarkdown Content:\n# People\nAlex (PhD student)'}
        with patch('visit_page.http_read', return_value=payload):
            record = visit_page.jina_read('https://x', 10)
        self.assertEqual(record['title'], 'People')
        self.assertTrue(record['text'].startswith('# People'))
        self.assertEqual(record['final_url'], 'https://x')

    def test_render_goes_from_http_straight_to_browser(self):
        shell = 'Program\nPartners\nScholars\n' + 'IMPRS-IS is a diverse and international community of doctoral researchers. ' * 4
        roster = 'Scholars\n' + '\n'.join(f'Person {i}\nMachine Learning' for i in range(60))
        with patch('visit_page.http_read', return_value={'http_status': 200, 'final_url': 'https://imprs.example/scholars', 'text': shell}), \
                patch('visit_page.wayback_read') as wayback, patch('visit_page.jina_read') as jina, \
                patch('visit_page.browser_read', return_value={'http_status': 200, 'final_url': 'https://imprs.example/scholars', 'text': roster}) as browser:
            record = visit('https://imprs.example/scholars', render=True, wait_ms=1500)
        self.assertEqual(record['fetch_via'], 'browser')
        self.assertEqual([a['via'] for a in record['attempts']], ['http', 'browser'])
        self.assertFalse(wayback.called or jina.called)
        self.assertEqual(browser.call_args[0][3], visit_page.RENDER_WAIT_MS)

    def test_jina_uses_plain_user_agent(self):
        with patch('visit_page.http_read', return_value={'http_status': 200, 'text': 'Title: T\n\nMarkdown Content:\nbody', 'final_url': 'x'}) as http:
            visit_page.jina_read('https://x.example/', 10)
        self.assertEqual(http.call_args.kwargs.get('user_agent'), visit_page.PLAIN_UA)

    def test_wayback_rate_limit_falls_back_to_the_archive_redirect(self):
        import urllib.error
        err = urllib.error.HTTPError('https://archive.org/wayback/available', 429, 'Too Many', {}, None)
        capture = {'http_status': 200, 'final_url': 'https://web.archive.org/web/20250301120000id_/https://x.example/', 'text': 'archived body ' * 20}
        with patch('visit_page.urllib.request.urlopen', side_effect=err), patch('visit_page.http_read', return_value=capture) as http:
            record = visit_page.wayback_read('https://x.example/', 10)
        self.assertEqual(record['archived_at'], '20250301120000')
        self.assertTrue(http.call_args[0][0].startswith('https://web.archive.org/web/'))
        self.assertEqual(record['archive_url'], 'https://web.archive.org/web/20250301120000/https://x.example/')

    def test_wayback_without_capture_is_unavailable(self):
        import urllib.error
        err = urllib.error.HTTPError('https://archive.org/wayback/available', 429, 'Too Many', {}, None)
        missing = urllib.error.HTTPError('https://web.archive.org/web/2026id_/https://x.example/', 404, 'Not Found', {}, None)
        with patch('visit_page.urllib.request.urlopen', side_effect=err), patch('visit_page.http_read', side_effect=missing):
            record = visit_page.wayback_read('https://x.example/', 10)
        self.assertEqual(record['status'], 'unavailable')
