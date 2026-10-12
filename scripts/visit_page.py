#!/usr/bin/env python3
"""Read public webpages into timestamped evidence JSON records.

  visit_page.py URL [--out runs/<run>/pages/x.json]
  visit_page.py URL --browser [--channel chrome] --out x.json        # JS-rendered lab/company pages only
  visit_page.py --batch urls.txt --out-dir runs/<run>/pages/ [--delay 5]   # final-roster LinkedIn pass

Pages that refuse or come back as a JavaScript shell climb a keyless ladder: plain HTTP with a browser
User-Agent, then the closest Wayback Machine snapshot, then Jina Reader (r.jina.ai), then a local headless
Chrome when Playwright is installed. Each attempt is recorded; `fetch_via` names the step that produced the text.
LinkedIn never climbs: plain HTTP is the only mode that reads a public profile (a headless browser lands on the
authwall), and no archive or reader proxy is used for it. For LinkedIn the record keeps the headline, Experience and Education excerpts, not the page
text; pass --full-text to keep everything. Batch mode runs serially with a delay and stops at the first
LinkedIn authwall / 999 / 429, because the anonymous quota is per outbound IP, not per profile.
Results are source material, not verified roles. Standard library only; browser mode needs Playwright.
"""
from __future__ import annotations
import argparse
import datetime
import ipaddress
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 4_000_000
MIN_TEXT = 200  # fewer characters than this on a 200 page is a JavaScript shell, not content
BROWSER_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
PLAIN_UA = 'talent-scout/0.1 public-page-reader'  # r.jina.ai answers a browser UA with a Cloudflare challenge
RENDER_WAIT_MS = 4000  # client-rendered rosters need a few seconds before the list exists
DEFAULT_LADDER = ('http', 'wayback', 'jina', 'browser')
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
BLOCK = {'p', 'div', 'section', 'article', 'li', 'h1', 'h2', 'h3', 'h4', 'header', 'footer', 'tr', 'br'}
STOP_BATCH = {'login_required', 'blocked', 'rate_limited', 'challenge'}
LINKEDIN_SECTIONS = ('Experience', 'Education', 'Publications', 'Projects', 'Licenses & certifications')


def validate_url(url: str) -> str:
    """Accept only public http(s) URLs: no credentials, no loopback, link-local or private hosts."""
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in {'http', 'https'} or not host or parsed.username or parsed.password:
        raise ValueError('Expected an http(s) URL without embedded credentials')
    if host in {'localhost', 'localhost.localdomain'} or host.endswith(('.local', '.localhost', '.internal')):
        raise ValueError('Local hostnames are not public pages')
    try:
        address = ipaddress.ip_address(host.strip('[]'))
    except ValueError:
        return url
    if not address.is_global:
        raise ValueError('Private, loopback and link-local addresses are not public pages')
    return url


def is_linkedin(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or '').lower()
    return host == 'linkedin.com' or host.endswith('.linkedin.com')


class TextPage(HTMLParser):
    """Lightweight HTML fallback. Browser mode is required for CSS/JS visibility."""
    def __init__(self, url: str):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.stack = []
        self.parts = []
        self.titles = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        style = re.sub(r'\s+', '', attrs.get('style') or '').lower()
        hidden = (any(item[1] for item in self.stack) or tag in {'script', 'style', 'template', 'noscript', 'head'}
                  or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
                  or 'display:none' in style or 'visibility:hidden' in style)
        if tag == 'a' and not hidden and attrs.get('href'):
            link = urllib.parse.urljoin(self.url, attrs['href'])
            try:
                validate_url(link)
            except ValueError:
                pass
            else:
                if link not in self.links:
                    self.links.append(link)
        if tag in BLOCK and not hidden:
            self.parts.append('\n')
        if tag not in VOID:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in BLOCK:
            self.parts.append('\n')

    def handle_data(self, data):
        if any(item[0] == 'title' for item in self.stack):
            self.titles.append(data)
        if not any(item[1] for item in self.stack):
            self.parts.append(data)

    def result(self):
        text = '\n'.join(line for part in ''.join(self.parts).splitlines() if (line := ' '.join(part.split())))
        return {'title': ' '.join(''.join(self.titles).split()), 'text': text, 'links': self.links[:200]}


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_read(url: str, timeout: float, user_agent: str = BROWSER_UA) -> dict:
    """One plain GET. A browser User-Agent is used because many public pages answer 403 to anything else;
    nothing else about the request pretends to be a person: no cookies, no login, no proxy."""
    request = urllib.request.Request(url, headers={'User-Agent': user_agent,
                                                  'Accept': 'text/html,text/plain;q=0.9,*/*;q=0.5',
                                                  'Accept-Language': 'en,de;q=0.8'})
    opener = urllib.request.build_opener(PublicRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.fp is None:  # status line without a body: nothing to parse
            return {'final_url': exc.geturl() or url, 'http_status': exc.code, 'content_type': '',
                    'text': '', 'title': '', 'links': [], 'truncated': False}
        response = exc
    with response:
        content_type = response.headers.get_content_type()
        result = {'final_url': response.geturl(), 'http_status': response.status, 'content_type': content_type}
        if content_type not in {'text/html', 'application/xhtml+xml', 'text/plain'}:
            return {**result, 'status': 'unsupported_content', 'text': '', 'title': '', 'links': []}
        data = response.read(MAX_BYTES + 1)
        truncated = len(data) > MAX_BYTES
        charset = response.headers.get_content_charset() or 'utf-8'
        try:
            html = data[:MAX_BYTES].decode(charset, errors='replace')
        except LookupError:
            html = data[:MAX_BYTES].decode('utf-8', errors='replace')
        if content_type == 'text/plain':
            parsed = {'text': html, 'title': '', 'links': []}
        else:
            parser = TextPage(result['final_url'])
            parser.feed(html)
            parsed = parser.result()
        return {**result, **parsed, 'truncated': truncated}


def launch(runtime, channel: str | None):
    """Installed Chrome (or Edge) when asked for or available, else Playwright's own Chromium."""
    candidates = [channel] if channel else ['chrome', None]
    last = None
    for candidate in candidates:
        try:
            return runtime.chromium.launch(headless=True, **({'channel': candidate} if candidate else {}))
        except Exception as exc:  # playwright.Error: executable missing, channel not installed
            last = exc
    raise ImportError(f'no browser available for Playwright ({type(last).__name__}); install Google Chrome or run playwright install chromium')


def browser_read(url: str, timeout: float, channel: str | None, wait_ms: int) -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        browser = launch(runtime, channel)
        try:
            context = browser.new_context(accept_downloads=False)
            page = context.new_page()
            page.set_default_timeout(timeout * 1000)
            response = page.goto(url, wait_until='domcontentloaded')
            if wait_ms:
                page.wait_for_timeout(wait_ms)
            text = page.locator('body').inner_text()
            links = page.locator('a[href]').evaluate_all('nodes => nodes.filter(n => n.getClientRects().length).map(n => n.href)')
            links = list(dict.fromkeys(link for link in links if link.startswith(('http://', 'https://'))))[:200]
            password = page.locator('input[type=password]:visible').count() > 0
            return {'final_url': page.url, 'http_status': response.status if response else None,
                    'title': page.title(), 'text': text, 'links': links, 'password_form': password,
                    'truncated': False, 'content_type': response.headers.get('content-type', '') if response else ''}
        finally:
            browser.close()


def wayback_read(url: str, timeout: float) -> dict:
    """Closest Wayback Machine capture, raw (the `id_` flag drops the archive toolbar)."""
    query = 'https://archive.org/wayback/available?' + urllib.parse.urlencode({'url': url})
    empty = {'text': '', 'title': '', 'links': [], 'final_url': url, 'http_status': None}
    try:
        with urllib.request.urlopen(urllib.request.Request(query, headers={'User-Agent': PLAIN_UA}), timeout=timeout) as r:
            closest = (json.load(r).get('archived_snapshots') or {}).get('closest') or {}
    except urllib.error.HTTPError as exc:  # the availability API rate-limits after a handful of calls
        if exc.code != 429:
            return {**empty, 'status': 'unavailable', 'http_status': exc.code}
        closest = {'available': True, 'timestamp': str(datetime.date.today().year), 'status': '200', 'via': 'redirect'}
    if not closest.get('available') or not closest.get('timestamp') or not str(closest.get('status', '200')).startswith('2'):
        return {**empty, 'status': 'unavailable'}
    raw = f"https://web.archive.org/web/{closest['timestamp']}id_/{url}"
    try:
        record = http_read(raw, timeout)  # a year-only timestamp redirects to the closest capture
    except urllib.error.HTTPError as exc:
        return {**empty, 'status': 'unavailable', 'http_status': exc.code}
    if record.get('http_status') == 404 or 'web.archive.org' not in (record.get('final_url') or ''):
        return {**empty, 'status': 'unavailable', 'http_status': record.get('http_status')}
    archived_at = re.search(r'/web/(\d{4,14})', record.get('final_url', '')) 
    stamp = archived_at.group(1) if archived_at else closest['timestamp']
    return {**record, 'archived_at': stamp, 'archive_url': f"https://web.archive.org/web/{stamp}/{url}"}


def jina_read(url: str, timeout: float) -> dict:
    """Jina Reader renders the page and returns it as text; keyless, rate-limited, public pages only."""
    record = http_read('https://r.jina.ai/' + url, timeout, user_agent=PLAIN_UA)
    text = record.get('text', '')
    title = ''
    if text.startswith('Title:'):
        title, _, text = text.partition('\n')
        title = title[6:].strip()
        text = text.split('Markdown Content:', 1)[-1].strip() if 'Markdown Content:' in text else text
    if record.get('http_status', 0) and record['http_status'] >= 400:
        return {**record, 'text': '', 'title': title, 'status': 'unavailable'}
    return {**record, 'text': text, 'title': title or record.get('title', ''), 'final_url': url}


def needs_escalation(record: dict, min_chars: int = MIN_TEXT) -> bool:
    status = classify(record)
    return status != 'readable' or len(record.get('text', '').strip()) < min_chars


def climb(url: str, timeout: float, ladder: tuple, channel: str | None, wait_ms: int,
          min_chars: int = MIN_TEXT, render: bool = False) -> tuple:
    """Try each step until one yields readable text. Returns (record, attempts).
    `render` jumps straight from http to the browser: a people page whose list is built client-side
    reads as a short but 'readable' navigation shell, which no text threshold can tell apart."""
    steps = {'http': lambda: http_read(url, timeout), 'wayback': lambda: wayback_read(url, timeout),
             'jina': lambda: jina_read(url, timeout),
             'browser': lambda: browser_read(url, timeout, channel, max(wait_ms, RENDER_WAIT_MS))}
    if render:
        ladder = tuple(step for step in ladder if step in {'http', 'browser'}) or ('http', 'browser')
    attempts, best, best_via, queue = [], None, None, list(ladder)
    while queue:
        step = queue.pop(0)
        try:
            record = steps[step]()
        except ImportError:
            attempts.append({'via': step, 'status': 'dependency_missing'})
            continue
        except Exception as exc:  # network, HTTP without body, JSON
            attempts.append({'via': step, 'status': 'fetch_error', 'error': type(exc).__name__})
            continue
        status = classify(record)
        attempts.append({'via': step, 'status': status, 'http_status': record.get('http_status'),
                         'chars': len(record.get('text', '').strip())})
        if best is None or (status not in STOP_BATCH and len(record.get('text', '')) > len(best.get('text', ''))):
            best, best_via = record, step
        if not needs_escalation(record, min_chars) and not (render and step == 'http' and 'browser' in queue):
            return {**record, 'fetch_via': step}, attempts
        if status == 'http_error' and record.get('http_status') == 404 and step == 'http':
            queue = [s for s in queue if s == 'wayback']  # a missing page can only come from the archive
    # Nothing readable: keep the attempt with the most text, so a partial render beats a refusal page.
    return {**(best or {}), 'fetch_via': best_via}, attempts


def classify(result: dict) -> str:
    """Access outcome from status code, final URL and page shape. Button labels such as
    'Join to view profile' appear on readable public profiles and are deliberately ignored."""
    if result.get('status'):
        return result['status']
    code = result.get('http_status')
    final_url = result.get('final_url', '')
    path = urllib.parse.urlsplit(final_url).path.lower()
    title = result.get('title', '').lower()
    text = result.get('text', '').lower()
    if code == 429:
        return 'rate_limited'
    if any(word in title for word in ('captcha', 'security verification', 'just a moment')) or any(
            word in text for word in ('verify you are human', 'verify you’re human', 'complete the captcha',
                                      "making sure you're not a bot", 'anubis to protect', 'checking your browser')):
        return 'challenge'
    if code == 401 or result.get('password_form') or any(
            segment in path.split('/') for segment in ('login', 'authwall', 'checkpoint', 'signin', 'uas')):
        return 'login_required'
    if is_linkedin(final_url) and title.split('|')[0].strip().startswith(
            ('sign in', 'sign up', 'log in', 'join linkedin', '登录', '登入', '领英: 登录', '領英: 登入')):
        return 'login_required'
    if code in {403, 999}:
        return 'blocked'
    if code and code >= 400:
        return 'http_error'
    if not text.strip():
        return 'empty'
    return 'readable'


def section_excerpts(text: str, lines_per_section: int = 14, page_truncated: bool = False) -> dict:
    """A flag per excerpt distinguishes a line/page cap from a natural section boundary."""
    lines = text.splitlines()
    result = {}
    for i, line in enumerate(lines):
        if line.strip() not in LINKEDIN_SECTIONS:
            continue
        block = []
        truncated = page_truncated
        for candidate in lines[i + 1:]:
            if candidate.strip() in LINKEDIN_SECTIONS or candidate.startswith('View '):
                truncated = False
                break
            if len(block) >= lines_per_section:
                truncated = True
                break
            block.append(candidate)
        key = line.strip().lower().replace(' & ', '_')
        result[key] = {'lines': block, 'section_truncated': truncated}
    return result


def linkedin_sections(text: str, lines_per_section: int = 14) -> dict:
    """Compatibility view: section names mapped to excerpt lines."""
    return {key: value['lines'] for key, value in section_excerpts(text, lines_per_section).items()}


def visit(url: str, browser: bool = False, timeout: float = 30, channel: str | None = None,
          wait_ms: int = 1500, max_chars: int = 60000, full_text: bool = False,
          ladder: tuple = DEFAULT_LADDER, min_chars: int = MIN_TEXT, render: bool = False) -> dict:
    validate_url(url)
    linkedin = is_linkedin(url)
    result = {'requested_url': url, 'retrieved_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_type': 'linkedin' if linkedin else 'webpage',
              'method': 'browser' if browser else 'http', 'final_url': url}
    if browser:
        try:
            result.update(browser_read(url, timeout, channel, wait_ms), fetch_via='browser')
        except ImportError:
            result.update(status='dependency_missing', error='Install scripts/requirements-browser.txt to use --browser')
        except Exception as exc:
            # Do not serialize exception strings: URLs can contain access tokens.
            result.update(status='fetch_error', error=type(exc).__name__)
    else:
        record, attempts = climb(url, timeout, ('http',) if linkedin else ladder, channel, wait_ms,
                                 min_chars, render and not linkedin)
        result.update(record, attempts=attempts)
        if not record.get('text') and attempts and all(a['status'] in {'fetch_error', 'dependency_missing'} for a in attempts):
            result['status'] = attempts[0]['status']
            result['error'] = attempts[0].get('error', 'Install scripts/requirements-browser.txt to use --browser')
    result['status'] = classify(result)
    if is_linkedin(result.get('final_url', '')):
        result['source_type'] = 'linkedin'
    result.setdefault('text', '')
    result.setdefault('links', [])
    result.setdefault('title', '')
    result['truncated'] = result.get('truncated', False) or len(result['text']) > max_chars
    result['text'] = result['text'][:max_chars]
    if result['source_type'] == 'linkedin':
        result['headline'] = result['title'].rsplit('|', 1)[0].strip()
        excerpts = section_excerpts(result['text'], page_truncated=result['truncated'])
        result['sections'] = {key: value['lines'] for key, value in excerpts.items()}
        result['section_truncated'] = {key: value['section_truncated'] for key, value in excerpts.items()}
        result['content_scope'] = 'public_page_may_be_partial'
        if not full_text:
            result['text'] = ''
            result['links'] = []
            result['text_dropped'] = 'linkedin: only professional excerpts are retained (data minimisation)'
    else:
        result['content_scope'] = 'page_text'
    result['needs_review'] = True
    result['role_verified'] = False
    return result


def save(record: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def batch(urls: list[str], out_dir: Path, delay: float, **options) -> dict:
    """Serial pass over the final roster's URLs. Stops at the first LinkedIn access refusal."""
    summary = {'read': 0, 'refused': 0, 'other': 0, 'stopped_at': None, 'files': []}
    for n, url in enumerate(urls):
        try:
            record = visit(url, **options)
        except ValueError as exc:
            record = {'requested_url': url, 'status': 'invalid_url', 'error': str(exc), 'role_verified': False}
        path = out_dir / f"{n + 1:03d}-{re.sub(r'[^a-z0-9]+', '-', url.lower())[:80].strip('-')}.json"
        save(record, path)
        summary['files'].append(str(path))
        status = record['status']
        key = 'read' if status == 'readable' else 'refused' if status in STOP_BATCH else 'other'
        summary[key] += 1
        print(f"{status:16} {url}", file=sys.stderr)
        if status in STOP_BATCH and is_linkedin(record.get('final_url', url)):
            summary['stopped_at'] = url
            summary['remaining'] = urls[n + 1:]
            break
        if n + 1 < len(urls):
            time.sleep(delay)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('url', nargs='?')
    parser.add_argument('--batch', help='Text file with one URL per line; reads serially into --out-dir')
    parser.add_argument('--out', help='Save UTF-8 JSON evidence; otherwise print JSON to stdout')
    parser.add_argument('--out-dir', help='Directory for batch records (default: pages/)', default='pages')
    parser.add_argument('--delay', type=float, default=5.0, help='Seconds between batch requests (default 5)')
    parser.add_argument('--browser', action='store_true', help='Render JavaScript with an isolated Playwright browser (not for LinkedIn)')
    parser.add_argument('--channel', choices=['chrome', 'msedge'], help='Use installed Chrome/Edge instead of Playwright Chromium')
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--wait-ms', type=int, default=1500, help='Browser settling time after DOM load, maximum 10000')
    parser.add_argument('--max-chars', type=int, default=60000)
    parser.add_argument('--full-text', action='store_true', help='Keep full page text for LinkedIn records too')
    parser.add_argument('--render', action='store_true',
                        help='People/roster page built client-side: read it with the local browser after the plain fetch')
    parser.add_argument('--min-chars', type=int, default=MIN_TEXT,
                        help=f'Readable text shorter than this climbs the ladder (default {MIN_TEXT})')
    parser.add_argument('--ladder', default=','.join(DEFAULT_LADDER),
                        help='Fallback steps after a refused or empty page, in order (default: http,wayback,jina,browser); "http" alone disables fallbacks')
    args = parser.parse_args()
    if bool(args.url) == bool(args.batch):
        parser.error('Give exactly one of URL or --batch FILE')
    if args.timeout <= 0 or args.max_chars <= 0 or not 0 <= args.wait_ms <= 10000 or args.delay < 0:
        parser.error('Positive timeout/max-chars, wait-ms between 0 and 10000, non-negative delay required')
    if args.channel and not args.browser:
        parser.error('--channel requires --browser')
    ladder = tuple(step.strip() for step in args.ladder.split(',') if step.strip())
    if not ladder or ladder[0] != 'http' or set(ladder) - set(DEFAULT_LADDER):
        parser.error('--ladder must start with http and use only: ' + ','.join(DEFAULT_LADDER))
    if args.min_chars < 0:
        parser.error('--min-chars must be non-negative')
    options = dict(browser=args.browser, timeout=args.timeout, channel=args.channel, wait_ms=args.wait_ms,
                   max_chars=args.max_chars, full_text=args.full_text, ladder=ladder, min_chars=args.min_chars,
                   render=args.render)
    if args.batch:
        try:
            with open(args.batch, encoding='utf-8') as source:
                urls = [l.strip() for l in source if l.strip() and not l.startswith('#')]
        except OSError as exc:
            parser.error(f'cannot read --batch file: {exc}')
        if args.browser and any(is_linkedin(u) for u in urls):
            parser.error('Browser mode lands on the LinkedIn authwall; run LinkedIn URLs without --browser')
        summary = batch(urls, Path(args.out_dir), args.delay, **options)
        save(summary, Path(args.out_dir) / 'summary.json')
        print(f"batch: {summary['read']} readable, {summary['refused']} refused, {summary['other']} other"
              + (f"; stopped at {summary['stopped_at']}" if summary['stopped_at'] else ''), file=sys.stderr)
        return 0 if summary['stopped_at'] is None else 2
    try:
        validate_url(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    if args.browser and is_linkedin(args.url):
        parser.error('Browser mode lands on the LinkedIn authwall; read LinkedIn profiles without --browser')
    result = visit(args.url, **options)
    if args.out:
        save(result, Path(args.out))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    kept = len(result['text']) or sum(len(v) for v in result.get('sections', {}).values())
    print(f"page status: {result['status']} via {result.get('fetch_via')}; kept {kept} {'lines' if result['source_type'] == 'linkedin' else 'characters'}", file=sys.stderr)
    return 0 if result['status'] == 'readable' else 2


if __name__ == '__main__':
    raise SystemExit(main())
