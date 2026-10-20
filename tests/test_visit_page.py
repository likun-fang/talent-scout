import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import visit_page
from visit_page import OutsideSources, TextPage, batch, classify, validate_url, visit

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
            ({'final_url': 'https://intranet.example.org/login?next=/team'}, 'login_required'),
            ({'text': 'Verify you are human'}, 'challenge'),
            ({'http_status': 200, 'text': "Making sure you're not a bot! Loading... Anubis to protect the server"}, 'challenge'),
            ({'password_form': True}, 'login_required'),
            ({'http_status': 404}, 'http_error'),
            ({'text': '   '}, 'empty'),
            ({'text': 'Alex — Research Engineer. Sign in newsletter'}, 'readable'),
        ]:
            with self.subTest(expected=expected, record=record):
                self.assertEqual(classify(record), expected)

    def test_a_linkedin_url_is_refused_before_any_request(self):
        for url in ('https://www.linkedin.com/in/alex-example', 'https://uk.linkedin.com/in/x', 'https://linkedin.com/company/y'):
            with self.subTest(url=url), patch('visit_page.http_read') as read, self.assertRaises(OutsideSources) as stop:
                visit(url)
            self.assertIn('LinkedIn is outside the sources', str(stop.exception))
            self.assertFalse(read.called)
        for url in ('https://linkedin.com.example.org/', 'https://lab.example.org/team#linkedin.com'):
            with self.subTest(url=url), patch('visit_page.http_read', return_value={'text': 'ok', 'final_url': url}):
                self.assertEqual(visit(url, ladder=('http',))['status'], 'readable')

    def test_a_wrapped_or_dotted_linkedin_url_is_refused_too(self):
        for url in ('https://web.archive.org/web/20250101000000/https://linkedin.com/in/x',
                    'https://web.archive.org/web/2025/linkedin.com/in/x', 'https://r.jina.ai/https://linkedin.com/in/x',
                    'https://www.linkedin.com./in/x', 'https://example.org/go?to=https%3A%2F%2Fwww.linkedin.com%2Fin%2Fx',
                    'https://r.jina.ai/https://%4Cinkedin.com/in/x', 'https://example.org/reader?url=https%3A%2F%2Flinkedin.com&format=text'):
            with self.subTest(url=url), patch('visit_page.http_read') as read, self.assertRaises(OutsideSources):
                visit(url)
            self.assertFalse(read.called)

    def test_a_jina_answer_from_linkedin_or_a_refused_redirect_to_linkedin_stops_the_ladder(self):
        jina = {'http_status': 200, 'final_url': 'https://r.jina.ai/https://lab.example.org/alex',
                'text': 'Title: Alex | LinkedIn\nURL Source: https://www.linkedin.com/in/alex\nMarkdown Content:\nAlex ' * 3}
        with patch('visit_page.http_read', side_effect=[{'http_status': 403, 'final_url': 'https://lab.example.org/alex', 'text': ''}, jina]), \
                patch('visit_page.wayback_read', return_value={'status': 'unavailable', 'text': '', 'final_url': 'https://lab.example.org/alex'}):
            record = visit('https://lab.example.org/alex', ladder=('http', 'wayback', 'jina'))
        self.assertEqual(record['status'], 'outside_sources')
        self.assertEqual(record['text'], '')
        redirect = {'status': 'unsupported_content', 'final_url': 'https://www.linkedin.com/in/alex', 'text': ''}
        with patch('visit_page.http_read', return_value=redirect), patch('visit_page.wayback_read') as wayback:
            record = visit('https://lab.example.org/alex')
        self.assertEqual(record['status'], 'outside_sources')
        self.assertFalse(wayback.called)

    def test_a_page_that_redirects_to_linkedin_keeps_nothing_and_does_not_climb(self):
        page = {'http_status': 200, 'final_url': 'https://www.linkedin.com/in/alex-example', 'title': 'Alex | LinkedIn',
                'text': 'Alex Example\nResearch Scientist at Example Lab\nExperience', 'links': ['https://example.org/x']}
        with patch('visit_page.http_read', return_value=page), patch('visit_page.wayback_read') as wayback:
            record = visit('https://lab.example.org/alex')
        self.assertEqual(record['status'], 'outside_sources')
        self.assertEqual((record['text'], record['links'], record['title']), ('', [], ''))
        self.assertFalse(wayback.called)

    def test_the_command_line_refuses_a_linkedin_url_in_one_line(self):
        for argv in (['visit_page.py', 'https://www.linkedin.com/in/alex'],
                     ['visit_page.py', 'https://www.linkedin.com/in/alex', '--browser']):
            with self.subTest(argv=argv), patch.object(sys, 'argv', argv), patch('visit_page.http_read') as read, \
                    self.assertRaises(SystemExit) as stop:
                visit_page.main()
            self.assertEqual(str(stop.exception), 'visit_page.py: LinkedIn is outside the sources of this skill; the URL was not read')
            self.assertFalse(read.called)

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
        for url in ('https://example.org/', 'http://93.184.216.34/'):
            self.assertEqual(validate_url(url), url)

    def test_batch_reads_serially_and_records_a_linkedin_url_as_outside_the_sources(self):
        responses = {
            'https://lab.example.org/team': {'http_status': 200, 'final_url': 'https://lab.example.org/team', 'text': 'Team: A, B'},
            'https://lab.example.org/blocked': {'http_status': 403, 'final_url': 'https://lab.example.org/blocked', 'text': ''},
            'https://lab.example.org/more': {'http_status': 200, 'final_url': 'https://lab.example.org/more', 'text': 'More'},
        }
        urls = ['https://lab.example.org/team', 'https://www.linkedin.com/in/b', 'https://lab.example.org/blocked',
                'https://lab.example.org/more']
        with patch('visit_page.http_read', side_effect=lambda url, timeout: responses[url]) as read, \
                patch('visit_page.time.sleep') as sleep, tempfile.TemporaryDirectory() as tmp:
            summary = batch(urls, Path(tmp), 5.0, ladder=('http',))
            records = [json.loads(path.read_text()) for path in sorted(Path(tmp).iterdir())]
        self.assertEqual((summary['read'], summary['refused'], summary['other']), (2, 1, 1))
        self.assertEqual([r['status'] for r in records], ['readable', 'outside_sources', 'blocked', 'readable'])
        self.assertNotIn('https://www.linkedin.com/in/b', [call.args[0] for call in read.call_args_list])
        self.assertEqual(sleep.call_count, 3)

    def test_batch_skips_invalid_urls_without_stopping(self):
        with patch('visit_page.http_read', return_value={'text': 'ok', 'final_url': 'https://example.org/'}), \
                patch('visit_page.time.sleep'), tempfile.TemporaryDirectory() as tmp:
            summary = batch(['http://localhost/x', 'https://example.org/'], Path(tmp), 0, ladder=('http',))
        self.assertEqual((summary['read'], summary['other']), (1, 1))


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
