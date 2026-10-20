#!/usr/bin/env python3
"""Publish one field's group map into the folder GitHub Pages serves.

  publish_site.py <run_dir> <slug> [--out docs] [--known assets/known-groups/<slug>.json]
                  [--removals ~/.config/talent-scout/removals.json]

Reads <run_dir>/site/groups.json, applies the removals file (kept outside the repository, so the repository never lists
who asked to be removed; its absence is noted and means none), and refuses to publish (nothing is written) when an acceptance check of
check_groups.py fails (recall of the known groups, staleness, LinkedIn), when the file carries a LinkedIn key or URL or
a `notes` field, or when it or a page built from it names an email address or a local or run path. Otherwise writes:

  <out>/<slug>/groups.json   the run's file after removals, with meta.checks (check values) and meta.removals (a count)
  <out>/<slug>/index.html    the map (group_map.py) with the data inlined, linking the repository's correction form
                             and the site's about page; rendered anew, so a run's own page with its placeholder
                             correction link is never copied
  <out>/index.html           one line per published field, from every <out>/*/groups.json
  <out>/about.html           what the map is, its sources, its method with each field's check values, and how to
                             correct an entry or have it removed
  <out>/.nojekyll            so GitHub Pages serves the folder as it is

It also refuses when <out> holds a file it does not write: the folder is the public site and nothing else.

Standard library only.
"""
from __future__ import annotations
import argparse, datetime, html, json, os, re, sys, tempfile, urllib.parse
from pathlib import Path
from check_groups import RECALL_MIN, STALE_MAX, recall, stale_groups
from group_export import linkedin_hits
from group_map import render_html
from person_fields import normalized
from table_export import window_start

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'https://github.com/likun-fang/talent-scout'
CORRECTION_FORM = f'{REPOSITORY}/issues/new?template=correction.yml'
OPT_OUT_FORM = f'{REPOSITORY}/issues/new?template=opt-out.yml'
SAMPLE_SIZE = 30  # check_groups.py's default spot-check sample
DEFAULT_REMOVALS = Path.home() / '.config' / 'talent-scout' / 'removals.json'
SCOPES = ('person', 'group')
SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
EMAIL = re.compile(r'(?:"[^"\n]+"|[\w.+%-]+)@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b')
# A path on the machine that built the run, or into a run directory. Inside a web URL the same words follow a host or
# another path segment and do not count, so data values that are web URLs are checked for email addresses only.
# Any absolute path of two segments, a drive or network path, a home or relative path, or a run directory.
# A segment may hold any character but must not start with a space, so "vision / language" is prose, not a path.
LOCAL_PATH = re.compile(r'file://|\\\\[^\\\s]+\\|(?<![\w/.%-])(?:~/|\.\.?/|/[^/\s][^/\n]*/[^/\s]|[A-Za-z]:[\\/]|runs/)')
WEB_URL = re.compile(r'^https?://\S+$', re.I)
# The pages link each other relatively ("../about.html"), so a page is checked for absolute and run paths only.
PAGE_PATH = re.compile(r'file://|\\\\[\w.$-]+\\|(?<![\w/.%-])(?:/(?:Users|home|private|tmp|var|Volumes|mnt|opt|root|srv)/'
                       r'|[A-Za-z]:[\\/]|runs/)')


def private_text(text: str) -> list[str]:
    """Email addresses and absolute or run paths in a page."""
    return [match.group(0) for pattern in (EMAIL, PAGE_PATH) for match in pattern.finditer(text)]


def strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, str):
        yield value


def private_values(doc: dict) -> list[str]:
    """Private text in the data's decoded strings: each value is checked on its own, so an escape such as a newline
    written as \\n cannot hide a path."""
    found = []
    for text in strings(doc):
        found += [m.group(0) for m in EMAIL.finditer(text)]
        if not WEB_URL.match(text.strip()):
            found += [m.group(0) for m in LOCAL_PATH.finditer(text)]
    return found


def decoded_linkedin(doc: dict) -> list[str]:
    """LinkedIn hosts written with percent escapes ("%6cinkedin.com"), which a browser decodes."""
    found = []
    for text in strings(doc):
        decoded = text
        for _ in range(3):
            decoded = urllib.parse.unquote(decoded)
        if decoded != text and linkedin_hits(decoded):
            found.append(text)
    return found


def notes_fields(value, path: str = '$') -> list[str]:
    """Where a `notes` key sits: notes are the run's working remarks and stay in the run."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() == 'notes':
                found.append(f'{path}.{key}')
            found += notes_fields(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += notes_fields(item, f'{path}[{index}]')
    return found


def load_json(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'cannot read {what} {path}: {exc}')


def checks(doc: dict, known: list[dict]) -> dict:
    """The values of check_groups.py's checks (a)-(d); SystemExit when (a), (b) or (c) fails."""
    groups = doc['groups']
    hits, misses = recall(groups, known, None)
    as_of = datetime.date.fromisoformat(doc['meta']['as_of'])
    stale = stale_groups(groups, as_of)
    linkedin = linkedin_hits(doc) + decoded_linkedin(doc)
    values = {'recall': {'found': len(hits), 'known': len(known)},
              'stale': {'groups': len(stale), 'of': len(groups), 'verified_since': window_start(as_of, 12).isoformat()},
              'banned_source_hits': len(linkedin), 'sample': min(SAMPLE_SIZE, len(groups))}
    failed = []
    if known and len(hits) / len(known) < RECALL_MIN:
        failed.append(f"recall {len(hits)}/{len(known)} below {RECALL_MIN:.0%} (missing: "
                      + '; '.join(item['pi'] for item, _ in misses) + ')')
    if groups and len(stale) / len(groups) > STALE_MAX:
        failed.append(f'stale {len(stale)}/{len(groups)} above {STALE_MAX:.0%}')
    if linkedin:
        failed.append(f'LinkedIn keys or URLs: {linkedin[:5]}')
    if failed:
        raise SystemExit('not published: ' + '; '.join(failed) + '. Run check_groups.py for the details.')
    return values


def load_removals(path: Path) -> list[dict]:
    """[{"issue": <number>, "person": <name as shown>, "group": <group id>, "scope": "person" | "group"}]. An absent
    file means no removals, with a notice; an unreadable or malformed one stops the publication."""
    if not path.exists():
        print(f'no removals file at {path}; publishing with 0 removals', file=sys.stderr)
        return []
    try:
        entries = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f'cannot read the removals file {path}: {exc}')
    def valid(entry) -> bool:
        return (isinstance(entry, dict) and isinstance(entry.get('issue'), int) and not isinstance(entry['issue'], bool)
                and isinstance(entry.get('group'), str) and entry['group'].strip() and entry.get('scope') in SCOPES
                and isinstance(entry.get('person'), str) and (entry['scope'] == 'group' or entry['person'].strip()))
    if not isinstance(entries, list) or not all(valid(entry) for entry in entries):
        raise SystemExit(f'the removals file {path}: expected a list of {{"issue": <number>, "person": "<name as shown>", '
                         f'"group": "<group id>", "scope": "person" or "group"}}')
    return entries


def name_in_url(name: str, url: str) -> bool:
    """A URL whose path spells the name ("/people/ben-ott", "ben_ott.html")."""
    words = re.findall(r'[a-z0-9]+', normalized(name))
    path = normalized(urllib.parse.unquote(urllib.parse.urlsplit(url).path))
    return len(words) > 1 and any(joiner.join(words) in path for joiner in ('-', '_', '.', ''))


def apply_removals(doc: dict, entries: list[dict]) -> tuple[dict, int]:
    """The field without the removed people and groups, and how many requests applied to it. A person leaves the named
    group with the URLs that spell their name; a PI who asks to be removed takes the group along, since the group is
    shown under the PI's name. A lab whose partner groups are gone stops being drawn as a lab."""
    same = lambda left, right: ' '.join(normalized(left).split()) == ' '.join(normalized(right).split())
    groups, applied = {g['id']: g for g in doc['groups']}, 0
    for entry in entries:
        group = groups.get(entry['group'])
        if group is None:
            continue  # a request for a group of another field
        if entry['scope'] == 'group' or same(entry['person'], group['pi']['name']):
            del groups[entry['group']]
            applied += 1
            continue
        kept = [m for m in group['members'] if not same(m['name'], entry['person'])]
        if len(kept) < len(group['members']):
            urls = lambda key: [u for u in group.get(key, []) if not name_in_url(entry['person'], u)]
            groups[entry['group']] = {**group, 'members': kept, 'evidence_urls': urls('evidence_urls'),
                                      'open_source': urls('open_source')}
            applied += 1
    result = []
    for group in groups.values():
        lab = group.get('lab')
        if lab:
            partners = [gid for gid in lab['groups'] if gid in groups]
            group = {key: value for key, value in group.items() if key != 'lab'}
            if len(partners) > 1:
                group['lab'] = {**lab, 'groups': partners}
        result.append(group)
    return {**doc, 'groups': result}, applied


def stray_files(out: Path, slug: str) -> list[str]:
    """Files under out that publication does not write: the folder is served as it is, so anything else would be
    published too."""
    slugs = {path.parent.name for path in out.glob('*/groups.json')} | {slug}
    written = {'.nojekyll', 'index.html', 'about.html'} | {f'{s}/{name}' for s in slugs for name in ('groups.json', 'index.html')}
    return sorted(path.relative_to(out).as_posix() for path in out.rglob('*')
                  if path.is_file() and path.relative_to(out).as_posix() not in written)


def published_field(path: Path) -> dict:
    """An earlier publication, read back for the index and about pages: its values reach those pages, so they are
    checked again here."""
    doc = load_json(path, 'published groups')
    meta = doc.get('meta') if isinstance(doc, dict) else None
    checks = (meta or {}).get('checks')
    count = lambda value: isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if not (isinstance(meta, dict) and isinstance(doc.get('groups'), list) and isinstance(meta.get('domain'), str)
            and isinstance(meta.get('as_of'), str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', meta['as_of'])
            and isinstance(checks, dict) and isinstance(checks.get('recall'), dict) and isinstance(checks.get('stale'), dict)
            and all(count(v) for v in (checks['recall'].get('found'), checks['recall'].get('known'),
                                       checks['stale'].get('groups'), checks['stale'].get('of'),
                                       checks.get('banned_source_hits'), checks.get('sample')))):
        raise SystemExit(f'{path}: an earlier publication without valid meta and meta.checks; publish that field again')
    found = private_values(doc) + linkedin_hits(doc) + decoded_linkedin(doc)
    if found:
        raise SystemExit(f'{path}: an earlier publication with private or LinkedIn text: {found[:5]}')
    return doc


def published_fields(out: Path, slug: str, doc: dict) -> list[tuple[str, dict]]:
    """(slug, groups.json) of every field under out, with this publication in place of its earlier one."""
    fields = {path.parent.name: published_field(path) for path in sorted(out.glob('*/groups.json'))
              if path.parent.name != slug}
    fields[slug] = doc
    return sorted(fields.items(), key=lambda item: (normalized(item[1]['meta'].get('domain', '')), item[0]))


PAGE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fff;--fg:#1b1b1b;--muted:#6b6b6b;--line:#e4e4e4;--accent:#1f5fbf}
@media (prefers-color-scheme: dark){:root{--bg:#161618;--fg:#e8e8e8;--muted:#a0a0a0;--line:#333;--accent:#7aa7ef}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}
header{display:flex;gap:12px;align-items:baseline;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:8px}
h1{font-size:20px;margin:8px 0}
h2{font-size:16px;margin:22px 0 6px}
a{color:var(--accent)}
.m{color:var(--muted)}
button{font:inherit;background:none;border:1px solid var(--line);border-radius:4px;color:var(--fg);padding:2px 8px;cursor:pointer}
table{border-collapse:collapse;font-size:14px}
td,th{border-bottom:1px solid var(--line);padding:4px 8px 4px 0;text-align:left;vertical-align:top}
[hidden]{display:none}
</style>
</head>
<body>
__BODY__
<script>
let lang = 'en';
try { lang = localStorage.getItem('group-map.lang') || (navigator.language.startsWith('zh') ? 'zh' : 'en'); } catch (e) {}
if (/^(en|zh)$/.test(new URLSearchParams(location.search).get('lang') || '')) lang = new URLSearchParams(location.search).get('lang');
function show(next) {
  lang = next;
  document.querySelectorAll('main[lang]').forEach(m => { m.hidden = m.lang !== lang; });
  document.documentElement.lang = lang === 'zh' ? 'zh' : 'en';
  try { localStorage.setItem('group-map.lang', lang); } catch (e) {}
}
document.querySelectorAll('[data-lang]').forEach(b => b.addEventListener('click', () => show(b.dataset.lang)));
show(lang);
</script>
</body>
</html>
'''


def page(title: str, english: str, chinese: str) -> str:
    body = (f'<main lang="en">{english}</main>\n<main lang="zh" hidden>{chinese}</main>')
    return PAGE.replace('__TITLE__', html.escape(title)).replace('__BODY__', body)


def header(title: str, other: str, other_lang: str, back: str = '') -> str:
    return (f'<header><h1>{html.escape(title)}</h1><span>{back}<button data-lang="{other_lang}">{other}</button></span></header>')


def field_lines(fields: list[tuple[str, dict]], zh: bool) -> str:
    lines = []
    for slug, doc in fields:
        meta, count = doc['meta'], len(doc['groups'])
        detail = (f'{count} 个课题组 · 截至 {meta["as_of"]}' if zh else
                  f'{count} group{"" if count == 1 else "s"} · as of {meta["as_of"]}')
        lines.append(f'<li><a href="{html.escape(slug)}/">{html.escape(meta.get("domain", slug))}</a> '
                     f'<span class="m">· {html.escape(detail)}</span></li>')
    return '<ul>' + ''.join(lines) + '</ul>'


def index_page(fields: list[tuple[str, dict]]) -> str:
    english = (header('Research group maps', '中文', 'zh')
               + '<p>Public maps of research groups in Europe, one per field. One entry per group: its PI, institution '
               'and homepage. No ranking.</p>' + field_lines(fields, False)
               + '<p><a href="about.html">About these maps, their sources and how to correct or remove an entry</a></p>')
    chinese = (header('研究课题组地图', 'English', 'en')
               + '<p>欧洲研究课题组的公开地图，每个领域一张。每个课题组一条：负责人、机构和主页。不排名。</p>'
               + field_lines(fields, True)
               + '<p><a href="about.html">关于这些地图：来源、方法，以及如何更正或删除条目</a></p>')
    return page('Research group maps', english, chinese)


def check_rows(fields: list[tuple[str, dict]], zh: bool) -> str:
    head = ('<tr><th>领域</th><th>(a) 召回</th><th>(b) 过期</th><th>(c) 领英</th><th>(d) 抽查</th></tr>' if zh else
            '<tr><th>field</th><th>(a) recall</th><th>(b) stale</th><th>(c) LinkedIn</th><th>(d) spot check</th></tr>')
    rows = []
    for slug, doc in fields:
        c = doc['meta'].get('checks')
        if not c:
            continue
        sample = f'{c["sample"]} 个' if zh else f'{c["sample"]} group{"" if c["sample"] == 1 else "s"}'
        cells = [f'{c["recall"]["found"]}/{c["recall"]["known"]}', f'{c["stale"]["groups"]}/{c["stale"]["of"]}',
                 str(c['banned_source_hits']), sample]
        rows.append(f'<tr><td><a href="{html.escape(slug)}/">{html.escape(doc["meta"].get("domain", slug))}</a></td>'
                    + ''.join(f'<td>{html.escape(cell)}</td>' for cell in cells) + '</tr>')
    return f'<table>{head}{"".join(rows)}</table>'


def about_page(fields: list[tuple[str, dict]]) -> str:
    aliases = f'{REPOSITORY}/blob/main/assets/institution-aliases.yaml'
    english = header('About the research group maps', '中文', 'zh', '<a href="index.html">all maps</a> ') + f'''
<section data-part="what"><h2>What the maps are</h2>
<p>Each map shows the research groups of one field in Europe: the EU, the UK, Switzerland and Norway.</p>
<p>One entry is one group: a PI, an institution and the group's homepage.</p>
<p>Members appear by name and role under their group. Nothing else about them is shown.</p>
<p>There is no ranking and there are no tiers. Groups are listed by institution, then by PI name.</p>
{field_lines(fields, False)}</section>
<section data-part="sources"><h2>Data sources</h2>
<p>Public academic pages: lab, group and institutional pages, read by hand.</p>
<p>Public funding registers, publication metadata, and award and competition pages.</p>
<p>Never LinkedIn and never paid sources.</p>
<p>Each group shows the date its page was last read.</p></section>
<section data-part="method"><h2>Method</h2>
<p>A group forms around its PI: a professor, a group leader named as such on a public page, or the lead of a grant.</p>
<p>A member joins a group when a public team page lists them with the PI, or when they work on the PI's grant at the
same institution. People who only share papers with the PI are counted, not named. A team page that still lists
someone whom a newer page places elsewhere does not count.</p>
<p>The institution is the one the PI's own page names. Spellings of one institution are joined through a
<a href="{aliases}">public table of names</a>. A second post elsewhere, such as an honorary professorship, is listed
next to it, not in its place.</p>
<p>A card that says "members not yet collected" has no member linked from a public page yet. It does not mean the group
has no members.</p>
<p>Before each publication four checks run. (a) At least {RECALL_MIN:.0%} of a list of well-known groups in the field
are on the map, with the same PI at the same institution. (b) At most {STALE_MAX:.0%} of groups were last read more
than 12 months before the map's date. (c) No LinkedIn key or URL appears anywhere in the data. (d) A random sample of
groups is checked by hand against their pages. The current values:</p>
{check_rows(fields, False)}</section>
<section data-part="corrections"><h2>Corrections and removal</h2>
<p>To correct an entry, use "Report a correction" on the group's card, or the
<a href="{CORRECTION_FORM}">correction form</a>. Say what is wrong and link a public page that shows the correct fact.</p>
<p>To be removed, use the <a href="{OPT_OUT_FORM}">removal form</a>. Give your name as shown and the group, and say
whether to remove you or the whole group. No reason is needed. The removal is made at the next publication.</p>
<p>Both forms are GitHub issues: they need a GitHub account and are public.</p>
<p>For each person the map stores the name, role, institution, group, the public URLs these come from, and the date
the page was read. Nothing else.</p></section>'''
    chinese = header('关于研究课题组地图', 'English', 'en', '<a href="index.html">全部地图</a> ') + f'''
<section data-part="what"><h2>地图是什么</h2>
<p>每张地图展示一个领域在欧洲（欧盟、英国、瑞士和挪威）的研究课题组。</p>
<p>一个条目就是一个课题组：负责人、机构和课题组主页。</p>
<p>成员只以姓名和角色列在所属课题组下，不显示其他信息。</p>
<p>不排名，不分级。课题组按机构、再按负责人姓名排列。</p>
{field_lines(fields, True)}</section>
<section data-part="sources"><h2>数据来源</h2>
<p>学术公开页面：实验室、课题组和机构页面，人工阅读。</p>
<p>公开的资助登记、论文元数据，以及奖项和竞赛页面。</p>
<p>从不使用领英，也不使用付费来源。</p>
<p>每个课题组都标明其页面最近一次阅读的日期。</p></section>
<section data-part="method"><h2>方法</h2>
<p>课题组以负责人为中心：教授、公开页面上写明的课题组长，或资助项目的负责人。</p>
<p>公开的团队页面把某人与负责人列在一起，或某人在同一机构参与负责人的资助项目，此人即为成员。只与负责人合写过论文的人只计数，不列名。如果较新的页面显示某人已在别处，仍列着此人的旧团队页面不算数。</p>
<p>机构取负责人本人页面上的机构。同一机构的不同写法通过<a href="{aliases}">公开的名称表</a>合并。在别处的第二职位（如名誉教授）列在旁边，不取代主机构。</p>
<p>卡片上写"成员未采集"，表示还没有从公开页面关联到成员，并不表示该课题组没有成员。</p>
<p>每次发布前运行四项检查：(a) 该领域知名课题组清单中至少 {RECALL_MIN:.0%} 在图上，负责人和机构一致；(b) 最近一次阅读早于地图日期 12 个月以上的课题组不超过 {STALE_MAX:.0%}；(c) 数据中没有任何领英字段或链接；(d) 随机抽取若干课题组，人工对照其页面核查。当前数值：</p>
{check_rows(fields, True)}</section>
<section data-part="corrections"><h2>更正与删除</h2>
<p>要更正条目，请点课题组卡片上的"报告错误"，或使用<a href="{CORRECTION_FORM}">更正表单</a>：说明哪里有误，并附上能证明正确信息的公开页面。</p>
<p>要求删除，请使用<a href="{OPT_OUT_FORM}">删除表单</a>：填写页面上显示的姓名和课题组，并选择删除本人还是整个课题组。无需说明理由。删除在下一次发布时生效。</p>
<p>两个表单都是 GitHub issue：需要 GitHub 账号，内容公开。</p>
<p>对每个人，地图只存储姓名、角色、机构、课题组、这些信息所来自的公开链接，以及页面阅读日期。</p></section>'''
    return page('About the research group maps', english, chinese)


def publish(run_dir: Path, slug: str, out: Path, known_path: Path, removals_path: Path = DEFAULT_REMOVALS) -> dict:
    """Apply removals, check, then write the field's files and rewrite the site's index and about pages. Returns
    meta.checks."""
    if not SLUG.match(slug or ''):
        raise SystemExit(f'slug {slug!r}: expected lowercase words joined by hyphens, such as multimodal-ai')
    stray = stray_files(out, slug) if out.exists() else []
    if stray:
        raise SystemExit(f'not published: {out} holds files publication does not write, and the folder is served as it '
                         f'is: {stray[:10]}. Move them elsewhere.')
    doc = load_json(run_dir / 'site' / 'groups.json', 'groups.json of the run')
    if not isinstance(doc, dict) or not isinstance(doc.get('meta'), dict) or not isinstance(doc.get('groups'), list):
        raise SystemExit(f'{run_dir}/site/groups.json: expected an object with "meta" and "groups" (group_export.py)')
    known = load_json(known_path, 'known groups')
    if not isinstance(known, dict) or not isinstance(known.get('groups'), list):
        raise SystemExit(f'{known_path}: expected {{"groups": [{{"pi": ..., "institution": ...}}]}}')
    doc, removed = apply_removals(doc, load_removals(removals_path))
    notes = notes_fields(doc)
    if notes:
        raise SystemExit(f'not published: notes fields stay in the run: {notes[:5]}')
    found = private_values(doc)
    if found:
        raise SystemExit(f'not published: private text (email addresses or local paths) in the data: {found[:5]}')
    doc = {**doc, 'meta': {**doc['meta'], 'checks': checks(doc, known['groups']), 'removals': removed}}
    data = json.dumps(doc, ensure_ascii=False, indent=1) + '\n'
    fields = published_fields(out, slug, doc)
    files = {out / slug / 'groups.json': data,
             out / slug / 'index.html': render_html(doc, correction_url=CORRECTION_FORM, about_url='../about.html'),
             out / 'index.html': index_page(fields), out / 'about.html': about_page(fields), out / '.nojekyll': ''}
    found = sorted({hit for text in files.values() for hit in private_text(text)})
    if found:
        raise SystemExit(f'not published: private text (email addresses or local paths): {found[:5]}')
    write_all(files)
    return doc['meta']['checks']


def write_all(files: dict[Path, str]) -> None:
    """Write every file or none: each goes to a temporary file beside its target first, and a failure while the
    targets are replaced puts the earlier contents back."""
    earlier = {path: path.read_bytes() if path.exists() else None for path in files}
    staged, replaced = {}, []
    try:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            handle, name = tempfile.mkstemp(dir=path.parent, prefix='.publish-')
            staged[path] = name  # registered before the write, so a failed write is cleaned up too
            with os.fdopen(handle, 'w', encoding='utf-8') as temporary:
                temporary.write(text)
        for path, name in staged.items():
            os.replace(name, path)
            replaced.append(path)
    except OSError as exc:
        for path in replaced:
            if earlier[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(earlier[path])
        for name in staged.values():
            Path(name).unlink(missing_ok=True)
        raise SystemExit(f'not published: writing failed ({exc}); the earlier files are back in place')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('slug')
    parser.add_argument('--out', type=Path, default=ROOT / 'docs')
    parser.add_argument('--known', type=Path, default=None, help='default: assets/known-groups/<slug>.json')
    parser.add_argument('--removals', type=Path, default=DEFAULT_REMOVALS, help=f'default: {DEFAULT_REMOVALS}')
    args = parser.parse_args()
    values = publish(args.run_dir, args.slug, args.out, args.known or ROOT / 'assets' / 'known-groups' / f'{args.slug}.json',
                     args.removals)
    print(f"published {args.slug} into {args.out}: recall {values['recall']['found']}/{values['recall']['known']}, "
          f"stale {values['stale']['groups']}/{values['stale']['of']}, LinkedIn {values['banned_source_hits']}", file=sys.stderr)


if __name__ == '__main__':
    main()
