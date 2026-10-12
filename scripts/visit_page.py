#!/usr/bin/env python3
"""Read one public webpage into a timestamped evidence JSON record.

python3 scripts/visit_page.py URL --out runs/page.json
python3 scripts/visit_page.py URL --browser --channel chrome --out runs/page.json
Browser mode needs Playwright and Chrome or installed Playwright Chromium.
No stored login session is loaded. Results are source material, not verified person roles.
"""
from __future__ import annotations
import argparse
import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 4_000_000
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
BLOCK = {'p', 'div', 'section', 'article', 'li', 'h1', 'h2', 'h3', 'h4', 'header', 'footer', 'tr', 'br'}


def validate_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Expected an http(s) URL without embedded credentials')
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
        style = re.sub(r'\s+', '', attrs.get('style', '')).lower()
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


def http_read(url: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={'User-Agent': 'talent-scout/0.1 public-page-reader',
                                                  'Accept': 'text/html,text/plain;q=0.9'})
    opener = urllib.request.build_opener(PublicRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
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


def browser_read(url: str, timeout: float, channel: str | None, wait_ms: int) -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        options = {'headless': True}
        if channel:
            options['channel'] = channel
        browser = runtime.chromium.launch(**options)
        try:
            context = browser.new_context(accept_downloads=False)
            page = context.new_page()
            page.set_default_timeout(timeout * 1000)
            response = page.goto(url, wait_until='domcontentloaded')
            # Bounded settling time for client-rendered public profile content.
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


def classify(result: dict) -> str:
    if result.get('status'):
        return result['status']
    code = result.get('http_status')
    path = urllib.parse.urlsplit(result.get('final_url', '')).path.lower()
    title = result.get('title', '').lower()
    text = result.get('text', '').lower()
    if code == 429:
        return 'rate_limited'
    if any(word in title for word in ('captcha', 'security verification', 'just a moment')) or any(
            word in text for word in ('verify you are human', 'verify you’re human', 'complete the captcha')):
        return 'challenge'
    if code == 401 or result.get('password_form') or any(
            segment in path.split('/') for segment in ('login', 'authwall', 'checkpoint', 'signin')):
        return 'login_required'
    if is_linkedin(result.get('final_url', '')) and (title.startswith(('sign in', 'sign up', '登录', '登入')) or
            any(word in title for word in ('log in or sign up', 'sign in or sign up', '登录或注册', '登入或註冊')) or
            any(word in text for word in ('sign in to view', 'join to view', '登录以查看', '登入即可查看'))):
        return 'login_required'
    if code in {403, 999}:
        return 'blocked'
    if code and code >= 400:
        return 'http_error'
    if not text.strip():
        return 'empty'
    return 'readable'


def visit(url: str, browser: bool = False, timeout: float = 30, channel: str | None = None,
          wait_ms: int = 1500, max_chars: int = 60000) -> dict:
    validate_url(url)
    result = {'requested_url': url, 'retrieved_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_type': 'linkedin' if is_linkedin(url) else 'webpage',
              'method': 'browser' if browser else 'http', 'final_url': url}
    try:
        result.update(browser_read(url, timeout, channel, wait_ms) if browser else http_read(url, timeout))
    except ImportError:
        result.update(status='dependency_missing', error='Install scripts/requirements-browser.txt to use --browser')
    except Exception as exc:
        # Do not serialize exception strings: URLs can contain access tokens.
        result.update(status='fetch_error', error=type(exc).__name__)
    result['status'] = classify(result)
    if is_linkedin(result.get('final_url', '')):
        result['source_type'] = 'linkedin'
    result.setdefault('text', '')
    result.setdefault('links', [])
    result.setdefault('title', '')
    result['truncated'] = result.get('truncated', False) or len(result['text']) > max_chars
    result['text'] = result['text'][:max_chars]
    result['needs_review'] = True
    result['role_verified'] = False
    result['content_scope'] = ('public_page_may_be_partial' if result['source_type'] == 'linkedin' else 'page_text')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('url')
    parser.add_argument('--out', help='Save UTF-8 JSON evidence; otherwise print JSON to stdout')
    parser.add_argument('--browser', action='store_true', help='Render JavaScript using an isolated Playwright browser')
    parser.add_argument('--channel', choices=['chrome', 'msedge'], help='Use installed Chrome/Edge instead of Playwright Chromium')
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--wait-ms', type=int, default=1500, help='Browser settling time after DOM load, maximum 10000')
    parser.add_argument('--max-chars', type=int, default=60000)
    args = parser.parse_args()
    try:
        validate_url(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    if args.timeout <= 0 or args.max_chars <= 0 or not 0 <= args.wait_ms <= 10000:
        parser.error('Positive timeout/max-chars and wait-ms between 0 and 10000 required')
    if args.channel and not args.browser:
        parser.error('--channel requires --browser')
    result = visit(args.url, args.browser, args.timeout, args.channel, args.wait_ms, args.max_chars)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding='utf-8')
    else:
        print(payload, end='')
    print(f"page status: {result['status']}; extracted {len(result['text'])} characters", file=sys.stderr)
    return 0 if result['status'] == 'readable' else 2


if __name__ == '__main__':
    raise SystemExit(main())
