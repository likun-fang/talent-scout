#!/usr/bin/env python3
"""Render the roster as a single-file talent map: talent-map.html with every person, group and evidence link.

  talent_map.py persons.jsonl --date YYYY-MM-DD [--domain "<phrase>"] [--out RUN_DIR/talent-map.html]
                [--region EU27+UK+CH+NO] [--region-core DE+CH] [--window-months 36]
                [--geo-cache RUN_DIR/cache/geo/institutions.json] [--offline]

Selection, ranking, tiers and groups are exactly those of table_export.py (same persons.jsonl, same date, same
region), so the map shows the roster, not a different cut. Institutions are placed from the manual table
assets/geo-overrides.json first, then with the ROR API (free, no key); a manual entry or ROR lookup whose country
disagrees with the roster's country is not used, and the institution falls back to its country centroid with a
small deterministic offset, labelled as such. Lookups are cached in --geo-cache;
--offline uses the cache only. The page loads Leaflet and OpenStreetMap tiles from the network when opened;
everything else is inline. Standard library only.
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, re, sys, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path
from table_export import select_persons, row_for, group_rows, window_start, signal_date
from person_fields import facet_texts, tags_for

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
ROR_API = 'https://api.ror.org/v2/organizations?query='
# Rough national centroids (lat, lng) for EU27 + UK + CH + NO: the fallback when ROR has no usable record.
CENTROIDS = {
    'AT': (47.6, 14.1), 'BE': (50.6, 4.6), 'BG': (42.7, 25.5), 'HR': (45.5, 16.0), 'CY': (35.1, 33.4), 'CZ': (49.8, 15.5),
    'DK': (56.0, 10.0), 'EE': (58.7, 25.0), 'FI': (62.0, 26.0), 'FR': (46.6, 2.4), 'DE': (51.1, 10.4), 'GR': (39.0, 22.0),
    'HU': (47.2, 19.4), 'IE': (53.3, -8.0), 'IT': (42.8, 12.6), 'LV': (56.9, 24.6), 'LT': (55.2, 23.9), 'LU': (49.8, 6.1),
    'MT': (35.9, 14.4), 'NL': (52.2, 5.3), 'PL': (52.1, 19.4), 'PT': (39.6, -8.0), 'RO': (45.9, 24.9), 'SK': (48.7, 19.7),
    'SI': (46.1, 14.8), 'ES': (40.2, -3.7), 'SE': (60.1, 15.0), 'GB': (53.0, -1.8), 'UK': (53.0, -1.8), 'CH': (46.8, 8.2),
    'NO': (61.5, 9.0),
}
SIGNAL_FIELDS = ('signal_type', 'date', 'strength', 'channel', 'evidence_url', 'snippet', 'role', 'role_title',
                 'affiliation_raw', 'country', 'hop_depth', 'parent', 'topics', 'note', 'fit')


def load_aliases() -> dict:
    path = ASSETS / 'institution-aliases.yaml'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def canonical_institution(name: str, aliases: dict) -> str:
    """First `||` segment and first list item ("A; B", "A / B"), folded whitespace, then the alias table
    (case-insensitive) on the whole name or on the part before the comma ("LMU Munich, Chair of X") → one display name."""
    name = ' '.join(re.split(r';|\s/\s', (name or '').split('||')[0])[0].split())
    if not name:
        return ''
    for candidate in (name, name.split(',')[0].strip()):
        lowered = candidate.casefold()
        for canonical, variants in aliases.items():
            if lowered == canonical.casefold() or any(lowered == v.casefold() for v in variants):
                return canonical
    return name


def country_centroid(code: str, name: str) -> tuple | None:
    base = CENTROIDS.get(code)
    if not base:
        return None
    digest = hashlib.sha1(name.encode('utf-8')).digest()
    jitter = lambda b: (b / 255 - 0.5) * 1.2  # within ±0.6° so markers of one country stay apart but inside it
    return (round(base[0] + jitter(digest[0]), 4), round(base[1] + jitter(digest[1]), 4), '', 'country centroid')


def default_fetch(url: str) -> dict:
    request = urllib.request.Request(url, headers={'User-Agent': 'talent-scout/1.0 (talent_map.py)'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def load_geo_overrides(path: str) -> dict:
    """The manual table {"overrides": {"<institution as the map shows it>": [lat, lng, "City", "CC"]}} for
    institutions ROR does not know; absent file, no overrides."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'cannot read geo overrides {path}: {exc}')
    overrides = data.get('overrides') if isinstance(data, dict) else None
    valid = isinstance(overrides, dict) and all(
        isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) for x in v[:2])
        and isinstance(v[2], str) and isinstance(v[3], str) and re.fullmatch(r'[A-Z]{2}', v[3]) for v in overrides.values())
    if not valid:
        raise SystemExit(f'geo overrides {path}: expected {{"overrides": {{"<institution>": [lat, lng, "City", "CC"]}}}}')
    return overrides


def same_country(code: str, country: str) -> bool:
    return code == country or code == 'GB' and country == 'UK'


class Geocoder:
    """Manual table first, then ROR lookups keyed by `name|country`; ROR misses are cached as null so a rerun
    never repeats them."""

    def __init__(self, cache_path: str, fetch=default_fetch, offline: bool = False, overrides: dict | None = None) -> None:
        self.path, self.fetch, self.offline = Path(cache_path), fetch, offline
        self.overrides = overrides or {}
        try:
            self.cache = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            self.cache = {}

    def locate(self, name: str, country: str) -> tuple | None:
        manual = self.overrides.get(name)
        # One name can stand for sites in several countries ("Microsoft"): an entry places only its own country.
        if manual and (not country or same_country(manual[3], country)):
            return (manual[0], manual[1], manual[2], 'manual')
        key = f'{name}|{country}'
        if key in self.cache:
            hit = self.cache[key]
            return tuple(hit) if hit else None
        if self.offline:
            return None
        try:
            items = self.fetch(ROR_API + urllib.parse.quote(name)).get('items', [])
        except Exception as exc:  # network or JSON; the map still renders with the centroid fallback
            print(f'ror lookup failed for {name!r}: {exc}', file=sys.stderr)
            return None
        found = None
        for item in items[:5]:
            details = (item.get('locations') or [{}])[0].get('geonames_details') or {}
            code = details.get('country_code', '')
            if details.get('lat') is None or (country and not same_country(code, country)):
                continue
            found = (details['lat'], details['lng'], details.get('name', ''), f"ror:{item.get('id', '')}")
            break
        self.cache[key] = list(found) if found else None
        return found

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')


def trimmed_signal(signal: dict) -> dict:
    return {key: signal.get(key) for key in SIGNAL_FIELDS if signal.get(key) not in (None, '', [])}


def person_entry(person: dict, row: dict, aliases: dict) -> dict:
    signals = sorted(person.get('signals', []), key=signal_date, reverse=True)
    entry = {**row, 'topics': [t for t in row['topics'].split(';') if t] if isinstance(row['topics'], str) else row['topics'],
             'channels_hit': person.get('channels_hit', []), 'ids': person.get('ids') or {},
             'institution_key': canonical_institution(row['current_affiliation'], aliases),
             'signals': [trimmed_signal(s) for s in signals],
             'group_evidence': person.get('group_evidence', ''), 'group_rule': person.get('group_rule'),
             'group_link': person.get('group_link', '')}
    for key in ('final_pass_title', 'final_pass_affiliation', 'final_pass_country', 'final_pass_url', 'linkedin_headline'):
        if person.get(key):
            entry[key] = person[key]
    return entry


def load_summaries(path: str | None) -> dict:
    """Optional sidecar {"groups": {"<PI> @ <inst>": {"en": ..., "zh": ...}}, "persons": {"<name>": {...}}}.

    Written by a later summarisation step; the page falls back to a sentence built from the record when absent."""
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'cannot read summaries {path}: {exc}')
    if not isinstance(data, dict) or not all(isinstance(data.get(k, {}), dict) for k in ('groups', 'persons')):
        raise SystemExit(f'summaries {path}: expected an object with "groups" and "persons" maps')
    return data


def load_facets(path: str | None) -> list[dict]:
    """Optional research-direction facets (`assets/facets.template.json` describes the file): tags with keyword
    lists per facet, labelled in en/zh. Absent, the page shows no tag filters."""
    if not path:
        return []
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'cannot read facets {path}: {exc}')
    facets = data.get('facets') if isinstance(data, dict) else None
    if not isinstance(facets, list) or not all(
            isinstance(f, dict) and isinstance(f.get('id'), str) and isinstance(f.get('tags'), list) and all(
                isinstance(t, dict) and isinstance(t.get('id'), str) and isinstance(t.get('keywords'), list) for t in f['tags'])
            for f in facets):
        raise SystemExit(f'facets {path}: expected {{"facets": [{{"id", "label", "tags": [{{"id", "label", "keywords"}}]}}]}}')
    ids = [t['id'] for f in facets for t in f['tags']]
    if len(ids) != len(set(ids)):
        raise SystemExit(f'facets {path}: tag ids must be unique across facets')
    return facets


def build_data(persons: list[dict], args, geocoder, summaries: dict | None = None, facets: list[dict] | None = None) -> dict:
    return build_data_from(select_persons(persons, args), args, geocoder, summaries, facets)


def build_data_from(selection: tuple, args, geocoder, summaries: dict | None = None, facets: list[dict] | None = None) -> dict:
    """build_data for a caller that already ran select_persons and keeps the selected records; `persons` in the
    result follows their order."""
    aliases = load_aliases()
    summaries = summaries or {}
    facets = facets or []
    selected, outside, rejected, cut, no_qualifying = selection
    date = args.date.isoformat()
    entries = [person_entry(p, row_for(p, args.domain, date), aliases) for p in selected]
    for person, entry in zip(selected, entries):
        entry['tags'] = tags_for(*facet_texts(person), facets) if facets else []
    start = window_start(args.date, args.window_months)
    by_name = {e['name']: e for e in entries}
    groups = []
    for row in group_rows(selected, start, args.date):
        if row['group'] == '(unattached)':
            continue
        pi = by_name.get(row['pi_name'])
        # The group's own institution: a PI's affiliation can list a company first ("valeo.ai; Sorbonne Univ.").
        key = canonical_institution(row['institution'], aliases) or (pi['institution_key'] if pi else '')
        # A coauthor-only link says nothing about what the group works on.
        tag_counts = Counter(tag for e in entries if e['group'] == row['group'] and e['group_link'] != 'coauthor'
                             for tag in e['tags'])
        groups.append({**row, 'institution_key': key, 'pi_in_roster': pi is not None,
                       'tags': [[tag, n] for tag, n in tag_counts.most_common()],
                       'topics': [t for t in row['topics'].split(';') if t],
                       'members': [{'name': m.rsplit('(', 1)[0], 'role_class': m.rsplit('(', 1)[1].rstrip(')')}
                                   for m in row['members'].split(';') if m],
                       'active_funding': [f for f in row['active_funding'].split(';') if f],
                       'open_source': [u for u in row['open_source'].split(';') if u],
                       'evidence_urls': [u for u in row['evidence_urls'].split(';') if u]})
    spelling = {}  # "Naver Labs Europe" and "NAVER LABS Europe" are one marker; the first spelling seen wins
    for item in entries + groups:
        item['institution_key'] = spelling.setdefault(item['institution_key'].casefold(), item['institution_key'])
    for item in entries + groups:  # "ETH Zurich, Robotic Systems Lab" joins the ETH Zurich marker when that exists
        head = item['institution_key'].split(',')[0].strip().casefold()
        if head != item['institution_key'].casefold() and head in spelling:
            item['institution_key'] = spelling[head]
    for entry in entries:
        if entry['name'] in summaries.get('persons', {}):
            entry['summary'] = summaries['persons'][entry['name']]
    for group in groups:
        if group['group'] in summaries.get('groups', {}):
            group['summary'] = summaries['groups'][group['group']]
    group_institution = {g['group']: g['institution_key'] for g in groups}
    for entry in entries:  # a member placed at the PI's institution keeps the group together on the map
        if entry['group'] in group_institution and not entry['institution_key']:
            entry['institution_key'] = group_institution[entry['group']]
    institutions = []
    keys = Counter(e['institution_key'] for e in entries if e['institution_key'])
    for group in groups:  # a group named after its academic institution can be the only record of that institution
        if group['institution_key']:
            keys.setdefault(group['institution_key'], 0)
    for key, members in sorted(keys.items()):
        named = {g['group'] for g in groups if g['institution_key'] == key}
        people = [e for e in entries if e['institution_key'] == key] or [e for e in entries if e['group'] in named]
        country = Counter(e['country'] for e in people if e['country']).most_common(1)
        country = country[0][0] if country else ''
        located = geocoder.locate(key, country) or country_centroid(country, key)
        lat, lng, city, source = located if located else (None, None, '', 'not located')
        institutions.append({'name': key, 'country': country, 'lat': lat, 'lng': lng, 'city': city, 'geo_source': source,
                             'person_count': members, 'group_count': sum(g['institution_key'] == key for g in groups),
                             'tier': min(e['tier'] for e in people)})
    return {
        'meta': {'domain': args.domain, 'date': date, 'window_start': start.isoformat(), 'region': args.region,
                 'region_core': args.region_core, 'persons': len(entries), 'groups': len(groups),
                 'institutions': len(institutions), 'out_of_region': len(outside), 'no_qualifying': no_qualifying,
                 'cut': cut, 'generated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
                 'facets': [{'id': f['id'], 'label': f.get('label', {}),
                             'tags': [{'id': t['id'], 'label': t.get('label', {})} for t in f['tags']]} for f in facets]},
        'institutions': institutions, 'groups': groups, 'persons': entries,
    }


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    return TEMPLATE.replace('__TITLE__', f"Talent map · {data['meta']['domain'] or 'roster'} · {data['meta']['date']}") \
                   .replace('__DATA__', payload)


TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--bg:#fff;--fg:#1b1b1b;--muted:#6b6b6b;--line:#e4e4e4;--panel:#f7f7f8;--card:#fff;--hover:#eef3fb;--chip:#eef3fb;--accent:#1f5fbf;
      --t1:#c0392b;--t2:#8e44ad;--t3:#e67e22;--t4:#2980b9;--t5:#7f8c8d}
@media (prefers-color-scheme: dark){:root{--bg:#121212;--fg:#ececec;--muted:#a3a3a3;--line:#2e2e2e;--panel:#181818;--card:#202020;--hover:#263244;--chip:#263244}}
*{box-sizing:border-box}
html,body{height:100%;margin:0;font:14px/1.5 -apple-system,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",Helvetica,Arial,sans-serif;color:var(--fg);background:var(--bg)}
header{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;padding:8px 14px;border-bottom:1px solid var(--line)}
header h1{font-size:16px;margin:0 6px 0 0;white-space:nowrap}
.counts{color:var(--muted);font-size:12.5px;white-space:nowrap}
header input,header select,header button,.mapctl select{font:inherit;font-size:13px;padding:4px 7px;border:1px solid var(--line);border-radius:5px;background:var(--card);color:var(--fg)}
header input{flex:1 1 260px;min-width:200px}
header button{cursor:pointer}
#lang{margin-left:auto}
main{display:grid;grid-template-columns:minmax(0,1fr) clamp(430px,36vw,700px);height:calc(100% - 50px)}
#mapwrap{position:relative;min-width:0}
#map{height:100%}
.mapctl{position:absolute;top:10px;right:10px;z-index:500}
aside{border-left:1px solid var(--line);background:var(--panel);overflow:auto;padding:10px 16px 24px}
.tabs{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap}
.tabs button{font:inherit;font-size:13px;padding:3px 11px;border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--fg);cursor:pointer}
.tabs button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.crumbs{font-size:12.5px;color:var(--muted);margin:2px 0 8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.crumbs a{color:var(--accent);cursor:pointer;text-decoration:none}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-bottom:10px}
.card h2{margin:0 0 2px;font-size:16px;line-height:1.3}
.card h3{margin:10px 0 4px;font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.card h3:first-child{margin-top:0}
.sub{color:var(--muted);font-size:12.5px;margin-bottom:6px}
.intro{margin:6px 0 8px;line-height:1.55}
.row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:0 10px;padding:6px 4px;border-bottom:1px solid var(--line);cursor:pointer;border-radius:4px}
.row:last-child{border-bottom:0}
.row:hover{background:var(--hover)}
.row .t{font-weight:500}
.row .m{grid-column:1 / -1;color:var(--muted);font-size:12.5px}
.row .k{grid-column:1 / -1;font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .r{white-space:nowrap;color:var(--muted);font-size:12.5px;align-self:start}
.badge{display:inline-block;font-size:11px;padding:0 6px;line-height:17px;border-radius:9px;color:#fff;background:var(--t5);vertical-align:1px}
.badge.t1{background:var(--t1)}.badge.t2{background:var(--t2)}.badge.t3{background:var(--t3)}.badge.t4{background:var(--t4)}.badge.t5{background:var(--t5)}
.role{display:inline-block;font-size:11.5px;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 5px;line-height:17px;vertical-align:1px}
.muted{color:var(--muted)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:3px 12px;margin:4px 0}
dt{color:var(--muted);font-size:12.5px;max-width:120px}
dd{margin:0;min-width:0;word-break:break-word}
a{color:var(--accent)}
ul.sig{list-style:none;padding:0;margin:4px 0}
ul.sig li{padding:6px 0;border-bottom:1px dashed var(--line);font-size:12.5px}
ul.sig li:last-child{border-bottom:0}
.topic{display:inline-block;background:var(--chip);border-radius:4px;padding:1px 7px;margin:2px 4px 2px 0;font-size:12px}
.tag{display:inline-block;border:1px solid var(--accent);color:var(--accent);border-radius:4px;padding:0 5px;margin:1px 4px 1px 0;font-size:11px;line-height:16px}
.row .tags{grid-column:1 / -1;line-height:1.2}
.btn{font:inherit;font-size:12px;padding:2px 8px;border:1px solid var(--line);border-radius:4px;background:var(--card);color:var(--accent);cursor:pointer}
details summary{cursor:pointer;color:var(--muted);font-size:12.5px}
.leaflet-container{font:inherit}
@media (max-width:900px){main{grid-template-columns:1fr;grid-template-rows:50% 50%}aside{border-left:0;border-top:1px solid var(--line)}#lang{margin-left:0}}
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <span class="counts" id="counts"></span>
  <input id="q" type="search">
  <select id="f-country"></select>
  <select id="f-tier"></select>
  <select id="f-role"></select>
  <select id="f-channel"></select>
  <span id="facets"></span>
  <select id="sort"></select>
  <button id="reset"></button>
  <button id="lang">中文</button>
</header>
<main>
  <div id="mapwrap"><div id="map"></div>
    <div class="mapctl"><select id="basemap"></select> <span class="counts" id="tilehint"></span></div></div>
  <aside>
    <div class="tabs"><button data-tab="groups"></button><button data-tab="places"></button><button data-tab="people"></button><button data-tab="about"></button></div>
    <div class="crumbs" id="crumbs"></div>
    <div id="panel"></div>
  </aside>
</main>
<script id="talent-data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('talent-data').textContent);
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const link = (u, t) => u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t || u.replace(/^https?:\/\/(www\.)?/, '').slice(0, 72))}</a>` : '';
const badge = t => `<span class="badge t${t}">T${t}</span>`;
const list = s => (Array.isArray(s) ? s : String(s || '').split(';')).map(x => x.trim()).filter(Boolean);

// ---- language
const I18N = {
  en: {
    tabs: {groups: 'Groups', places: 'Institutions', people: 'People', about: 'About'},
    search: 'search name, institution, group, topic', allCountries: 'all countries', allTiers: 'all tiers', allRoles: 'all roles',
    allChannels: 'all channels', reset: 'reset', tier: 'tier', sortTier: 'sort: tier, then size', sortSize: 'sort: size', sortName: 'sort: name',
    sortNewest: 'sort: newest signal', people: 'people', groups: 'groups', institutions: 'institutions', members: 'members', back: '← back',
    showOnMap: 'show on map', approx: 'approximate position', manualPos: 'position from the manual table', position: 'position', noMatch: 'nothing matches', noInst: 'No institution on record',
    loose: 'Not attached to a group here', unattached: 'unattached', group: 'group', pi: 'PI', institution: 'institution', homepage: 'homepage',
    topics: 'topics', funding: 'active funding', recent: 'recent outputs', openSource: 'open source', evidence: 'evidence links', signals: 'public records',
    affiliation: 'affiliation', finalPass: 'final pass', roleEvidence: 'role evidence', rolesInSignals: 'roles in records', channels: 'channels',
    ids: 'identifiers', notes: 'notes', hop: 'hop', merge: 'merge', fit: 'fit', latest: 'latest', firstPub: 'first publication', undated: 'undated',
    groupEvidence: 'grouping evidence', parent: 'parent', tags: 'direction tags', all: 'all', tagged: 'people tagged', untagged: 'without a tag',
    coauthors: 'coauthors', coauthorsOnly: 'coauthors only',
    facetsNote: 'Tags come from a per-domain keyword list (facets.json): one keyword in a topic, or two different keywords in snippets and project titles. A tag means the words occur in the record, not that a reviewer classified the work.',
    basemaps: {esri: 'Esri light gray', osmde: 'OpenStreetMap (DE mirror)', osm: 'OpenStreetMap', none: 'no basemap'},
    tileHint: n => `basemap "${n}" is not loading on this network; pick another one, the markers still work`,
    roles: {professor: 'professor', group_leader: 'group leader', researcher: 'researcher / postdoc', phd_student: 'PhD student', industry: 'industry', unknown: 'role unknown'},
    strength: {high: 'strong', medium: 'medium', low: 'weak'},
    tiers: {1: 'T1 core-region professor or group leader', 2: 'T2 extended-region professor or group leader', 3: 'T3 core-region researcher or PhD student',
      4: 'T4 extended-region PhD student', 5: 'T5 everyone else in the region'},
    tiersShort: {1: 'T1 core professors / leaders', 2: 'T2 extended professors / leaders', 3: 'T3 core researchers / PhDs', 4: 'T4 extended-region PhDs', 5: 'T5 others'},
    about: {domain: 'domain', date: 'run date', window: 'signal window', region: 'region', core: 'core', people: 'people', tiers: 'tiers', positions: 'positions',
      generated: 'generated', peopleLine: m => `${m.persons} in the roster · ${m.out_of_region} outside the region · ${m.no_qualifying} without a record in the window (not shown)`,
      positions_: 'institution coordinates from ROR; "position from the manual table" means assets/geo-overrides.json (city level); "approximate position" means the country centroid',
      note: 'Every person, group and role comes with the public record it was read from. Roles are inferred from titles and funding records and can be wrong: check the evidence before acting on a row.',
      how: 'How to read it: pick a group (the PI and the people linked to them), or click an institution on the map. Filters narrow all three lists and the map at once; the address bar carries a link to the open card.'},
    introPerson: p => {
      const r = I18N.en.roles[p.role_class] || p.role_class, where = p.current_affiliation ? ` at ${p.current_affiliation} (${p.country})` : ` (${p.country})`;
      let s = `${p.name}: ${r}${where}, tier ${p.tier}.`;
      if (p.group) s += ` Linked to ${p.group.split(' @ ')[0]}'s group.`;
      const n = p.signals.length, newest = p.signals.find(x => x.date);
      s += ` ${n} public record${n === 1 ? '' : 's'} via ${p.channels_hit.join(', ')}` + (newest ? `; newest: ${label(newest.signal_type)} (${newest.date}).` : '.');
      if (p.topics.length) s += ` Works on: ${p.topics.slice(0, 3).join('; ')}.`;
      if (p.first_pub_year) s += ` First publication ${p.first_pub_year}.`;
      return s;
    },
    introGroup: (g, members) => {
      const counts = roleCounts(members).map(([k, n]) => `${n} ${I18N.en.roles[k] || k}`).join(', ');
      let s = `${g.pi_name}'s group at ${g.institution_key} (${g.country}): ${members.length} people on record (${counts}).`;
      if (g.active_funding.length) s += ` Active funding: ${g.active_funding.map(f => label(f.split('@')[0]) + (f.split('@')[1] ? ' ' + f.split('@')[1] : '')).join('; ')}.`;
      if (g.topics.length) s += ` Topics: ${g.topics.slice(0, 4).join('; ')}.`;
      return s;
    },
  },
  zh: {
    tabs: {groups: '课题组', places: '机构', people: '人员', about: '说明'},
    search: '搜索姓名、机构、课题组、方向', allCountries: '所有国家', allTiers: '所有层级', allRoles: '所有角色',
    allChannels: '所有渠道', reset: '重置', tier: '第', sortTier: '排序：层级，再按人数', sortSize: '排序：人数', sortName: '排序：姓名',
    sortNewest: '排序：最新记录', people: '人', groups: '课题组', institutions: '机构', members: '成员', back: '← 返回',
    showOnMap: '在地图上显示', approx: '位置为近似', manualPos: '位置来自手工表', position: '定位', noMatch: '没有匹配结果', noInst: '没有机构记录',
    loose: '本机构内未归入课题组', unattached: '未归组', group: '课题组', pi: '负责人', institution: '机构', homepage: '主页',
    topics: '方向', funding: '在研资助', recent: '近期产出', openSource: '开源', evidence: '证据链接', signals: '公开记录',
    affiliation: '隶属', finalPass: '终检', roleEvidence: '角色依据', rolesInSignals: '记录中的身份', channels: '渠道',
    ids: '标识', notes: '备注', hop: '跳数', merge: '合并', fit: '匹配', latest: '最新', firstPub: '首篇发表', undated: '无日期',
    groupEvidence: '归组依据', parent: '来源', tags: '方向标签', all: '全部', tagged: '人有标签', untagged: '无标签',
    coauthors: '合著', coauthorsOnly: '仅合著',
    facetsNote: '标签来自按领域写的关键词表（facets.json）：方向里出现一个关键词，或摘录和项目标题里出现两个不同的关键词。有标签只说明记录里出现了这些词，不代表有人审过。',
    basemaps: {esri: 'Esri 浅灰底图', osmde: 'OpenStreetMap（德国镜像）', osm: 'OpenStreetMap', none: '无底图'},
    tileHint: n => `底图 "${n}" 在当前网络加载不了，换一个即可，圆点不受影响`,
    roles: {professor: '教授', group_leader: '课题组长', researcher: '研究员/博后', phd_student: '博士生', industry: '业界', unknown: '角色未定'},
    strength: {high: '强', medium: '中', low: '弱'},
    tiers: {1: 'T1 核心区（德/瑞）教授或课题组长', 2: 'T2 扩展区教授或课题组长', 3: 'T3 核心区研究员或博士生', 4: 'T4 扩展区博士生', 5: 'T5 区域内其他人'},
    tiersShort: {1: 'T1 核心区教授/组长', 2: 'T2 扩展区教授/组长', 3: 'T3 核心区研究员/博士生', 4: 'T4 扩展区博士生', 5: 'T5 其他'},
    about: {domain: '领域', date: '运行日期', window: '记录窗口', region: '区域', core: '核心区', people: '人数', tiers: '层级', positions: '定位',
      generated: '生成时间', peopleLine: m => `名单 ${m.persons} 人 · 区域外 ${m.out_of_region} 人 · 窗口内无记录 ${m.no_qualifying} 人（不显示）`,
      positions_: '机构坐标来自 ROR；"位置来自手工表"表示取自 assets/geo-overrides.json（城市级）；"位置为近似"表示用的是国家中心点',
      note: '每个人、每个课题组、每个角色都附带读取它的公开记录。角色是从头衔和资助记录推断的，可能有错：行动前先看证据。',
      how: '怎么找：先按课题组看（负责人和挂在其名下的人），或者点地图上的机构。筛选同时作用于三个列表和地图；地址栏带有当前卡片的链接。'},
    introPerson: p => {
      const r = I18N.zh.roles[p.role_class] || p.role_class;
      let s = `${p.name}，${p.current_affiliation ? p.current_affiliation + '（' + p.country + '）' : p.country}${r}，第 ${p.tier} 层。`;
      if (p.group) s += `挂在 ${p.group.split(' @ ')[0]} 课题组。`;
      const newest = p.signals.find(x => x.date);
      s += `共 ${p.signals.length} 条公开记录，来自 ${p.channels_hit.map(channelLabel).join('、')}` + (newest ? `；最新一条是 ${label(newest.signal_type)}（${newest.date}）。` : '。');
      if (p.topics.length) s += `研究内容：${p.topics.slice(0, 3).join('；')}。`;
      if (p.first_pub_year) s += `首篇发表于 ${p.first_pub_year}。`;
      return s;
    },
    introGroup: (g, members) => {
      const counts = roleCounts(members).map(([k, n]) => `${I18N.zh.roles[k] || k} ${n} 人`).join('，');
      let s = `${g.pi_name} 课题组，${g.institution_key}（${g.country}），有记录的成员 ${members.length} 人（${counts}）。`;
      if (g.active_funding.length) s += `在研资助：${g.active_funding.map(f => label(f.split('@')[0]) + (f.split('@')[1] ? ' ' + f.split('@')[1] : '')).join('；')}。`;
      if (g.topics.length) s += `方向：${g.topics.slice(0, 4).join('；')}。`;
      return s;
    },
  },
};
const SIGNAL_ZH = {lab_member: '团队页成员', team_member: '团队成员', lab_publication: '实验室论文', pi_coauthor_publication: '与负责人合著论文',
  grant_publication: '项目论文', company_paper: '公司论文', industry_publication: '业界论文', startup_paper: '创业公司论文', best_paper: '最佳论文',
  best_student_paper: '最佳学生论文', outstanding_paper: '杰出论文', best_paper_honorable_mention: '最佳论文提名', award_candidate: '获奖论文作者',
  dfg_project: 'DFG 项目', snsf_project: 'SNSF 项目', snsf_ambizione: 'SNSF Ambizione', erc_stg: 'ERC Starting Grant', erc_cog: 'ERC Consolidator',
  erc_adg: 'ERC Advanced', erc_syg: 'ERC Synergy', national_project: '国家项目', national_fellowship: '国家级资助', swecris_project: '瑞典项目',
  fris_project: '佛兰德项目', aei_project: '西班牙项目', rcn_project: '挪威项目', fwf_project: '奥地利项目', graduiertenkolleg_member: '研究生院成员',
  imprs_member: 'IMPRS 成员', code_contribution: '代码贡献', repository_activity: '仓库活动', competition_result: '竞赛成绩', competition_paper: '竞赛论文',
  competition_special_award: '竞赛特别奖', national_prize: '国家级奖项', young_researcher_award: '青年学者奖', dissertation_award: '博士论文奖',
  doctoral_prize: '博士奖', doctoral_prize_finalist: '博士奖入围', ellis_fellow: 'ELLIS fellow', ellis_scholar: 'ELLIS scholar', startup_founder: '创业者',
  startup_milestone: '创业里程碑', industry_lab: '业界实验室', industry_appointment: '业界任职', company_member: '公司成员', eic_accelerator: 'EIC Accelerator',
  resource_allocation: '算力分配', role_evidence: '角色证据', personal_role: '个人页角色', professional_profile: '职业档案'};
const CHANNEL_ZH = {'funding-de-ch': '德瑞资助', 'funding-eu': 'EU 资助', 'funding-fr-es-nl-be': '法西荷比资助', 'funding-at-se-no-dk': '奥瑞挪丹资助',
  'awards-papers': '获奖论文', competitions: '竞赛', industry: '业界', 'national-prizes': '国家奖项', 'open-source': '开源', startups: '创业'};
let lang = 'en';
try { lang = localStorage.getItem('talent-map.lang') || (navigator.language.startsWith('zh') ? 'zh' : 'en'); } catch (e) {}
if (/^(en|zh)$/.test(new URLSearchParams(location.search).get('lang') || '')) lang = new URLSearchParams(location.search).get('lang');  // ?lang=zh for a shared link
const T = () => I18N[lang];
const label = t => lang === 'zh' ? (SIGNAL_ZH[t] || t.replace(/_/g, ' ')) : t.replace(/_/g, ' ');
const channelLabel = c => lang === 'zh' ? (CHANNEL_ZH[c] || c) : c;
const roleLabel = r => T().roles[r] || r;
const FACETS = DATA.meta.facets || [];
const TAGS = Object.fromEntries(FACETS.flatMap(f => f.tags.map(t => [t.id, t])));
const i18nLabel = (x, fallback) => (x && (x[lang] || x.en || x.zh)) || fallback;
const tagLabel = id => i18nLabel((TAGS[id] || {}).label, id);
const facetOf = id => FACETS.find(f => f.tags.some(t => t.id === id));
const tagChips = (tags, counts) => tags.map(t => `<span class="tag" title="${esc(i18nLabel((facetOf(t) || {}).label, ''))}">${esc(tagLabel(t))}${counts ? ` ${counts[t]}` : ''}</span>`).join('');
const ROLE_ORDER = ['professor', 'group_leader', 'researcher', 'phd_student', 'industry', 'unknown'];
const isCoauthor = p => p.group_link === 'coauthor';  // linked only through a shared paper: listed apart, not counted as a member
const roleCounts = members => ROLE_ORDER.map(k => [k, members.filter(p => p.role_class === k).length]).filter(x => x[1]);

// ---- state and filters
const state = {tab: 'groups', view: null, stack: []};
const filters = {q: '', country: '', tier: '', role: '', channel: '', sort: 'tier', tags: {}};
function matches(p) {
  if (filters.country && p.country !== filters.country) return false;
  if (filters.tier && String(p.tier) !== filters.tier) return false;
  if (filters.role && p.role_class !== filters.role) return false;
  if (filters.channel && !p.channels_hit.includes(filters.channel)) return false;
  for (const tag of Object.values(filters.tags)) if (tag && !(p.tags || []).includes(tag)) return false;
  if (filters.q) {
    const hay = [p.name, p.current_affiliation, p.institution_key, p.group, ...(p.topics || []), ...(p.tags || []).map(tagLabel)].join(' ').toLowerCase();
    if (!hay.includes(filters.q)) return false;
  }
  return true;
}
const visible = () => DATA.persons.filter(matches);
const groupOf = name => DATA.groups.find(g => g.group === name);
const personOf = name => DATA.persons.find(p => p.name === name);
const newestDate = p => (p.signals.find(s => s.date) || {}).date || '';
function sortPeople(people) {
  const by = {tier: (a, b) => a.tier - b.tier || a.name.localeCompare(b.name), size: (a, b) => a.tier - b.tier || b.signals.length - a.signals.length,
    name: (a, b) => a.name.localeCompare(b.name), newest: (a, b) => newestDate(b).localeCompare(newestDate(a))}[filters.sort];
  return [...people].sort(by);
}
function sortGroups(groups, countOf) {
  const by = {tier: (a, b) => a.tier - b.tier || countOf(b) - countOf(a), size: (a, b) => countOf(b) - countOf(a),
    name: (a, b) => a.pi_name.localeCompare(b.pi_name), newest: (a, b) => a.tier - b.tier || countOf(b) - countOf(a)}[filters.sort];
  return [...groups].sort(by);
}

// ---- map
const map = L.map('map', {worldCopyJump: false}).setView([50.5, 9], 5);
const OSM_CREDIT = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const BASEMAPS = {  // keyless hosts; the public OSM servers reject pages opened as a local file (osm.wiki/blocked)
  esri: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {maxZoom: 16, attribution: 'Tiles &copy; Esri'}],
  osmde: ['https://tile.openstreetmap.de/{z}/{x}/{y}.png', {maxZoom: 19, attribution: OSM_CREDIT}],
  osm: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: OSM_CREDIT}],
};
let tiles = null, tileErrors = 0;
function useBasemap(name) {
  if (tiles) map.removeLayer(tiles);
  tiles = null; tileErrors = 0; $('#tilehint').textContent = '';
  if (!BASEMAPS[name]) return;
  tiles = L.tileLayer(...BASEMAPS[name]).addTo(map);
  tiles.on('tileerror', () => { if (++tileErrors === 3) $('#tilehint').textContent = T().tileHint(T().basemaps[name]); });
}
const layer = L.layerGroup().addTo(map);
const tierColor = {1: '#c0392b', 2: '#8e44ad', 3: '#e67e22', 4: '#2980b9', 5: '#7f8c8d'};
let fitPending = true;
function drawMarkers(people) {
  layer.clearLayers();
  const counts = new Map();
  for (const p of people) if (p.institution_key) counts.set(p.institution_key, (counts.get(p.institution_key) || 0) + 1);
  const points = [];
  for (const inst of DATA.institutions) {
    const n = counts.get(inst.name); if (!n || inst.lat == null) continue;
    const tier = Math.min(...people.filter(p => p.institution_key === inst.name).map(p => p.tier));
    const m = L.circleMarker([inst.lat, inst.lng], {radius: 5 + Math.sqrt(n) * 3, color: tierColor[tier], weight: 1.5, fillColor: tierColor[tier], fillOpacity: 0.45});
    m.bindTooltip(`<b>${esc(inst.name)}</b><br>${n} ${T().people} · ${inst.group_count} ${T().groups}${inst.geo_source === 'country centroid' ? '<br><i>' + T().approx + '</i>' : ''}`);
    m.on('click', () => show('institution', inst.name));
    m.addTo(layer); points.push([inst.lat, inst.lng]);
  }
  if (fitPending && points.length) { map.fitBounds(points, {padding: [30, 30], maxZoom: 7}); fitPending = false; }
}
function flyToInst(name) {
  const inst = DATA.institutions.find(i => i.name === name);
  if (inst && inst.lat != null) map.flyTo([inst.lat, inst.lng], Math.max(map.getZoom(), 8), {duration: 0.6});
}

// ---- panel
function show(kind, key, push = true) {
  if (push && state.view) state.stack.push(state.view);
  state.view = {kind, key};
  history.replaceState(null, '', `#${kind}=${encodeURIComponent(key)}`);
  render();
}
function back() { state.view = state.stack.pop() || null; history.replaceState(null, '', state.view ? `#${state.view.kind}=${encodeURIComponent(state.view.key)}` : '#'); render(); }
function openFromHash() {
  const m = /^#(person|group|institution)=(.*)$/.exec(location.hash);
  if (m) show(m[1], decodeURIComponent(m[2]), false);
}
function crumbs() {
  const parts = [`<a data-home>${esc(T().tabs[state.tab])}</a>`];
  if (state.view) parts.push(`<span>›</span><span>${esc(state.view.key)}</span>`);
  if (state.view) parts.push(`<a data-back>${T().back}</a>`);
  $('#crumbs').innerHTML = parts.join(' ');
}
function render() {
  const people = visible();
  drawMarkers(people);
  $('#counts').textContent = `${people.length} / ${DATA.persons.length} ${T().people} · ${DATA.groups.length} ${T().groups} · ${DATA.institutions.length} ${T().institutions}`;
  crumbs();
  const v = state.view;
  let html;
  if (!v) html = {places: placesList, groups: groupsList, people: peopleList, about: about}[state.tab](people);
  else if (v.kind === 'institution') html = institutionView(v.key, people);
  else if (v.kind === 'group') html = groupView(v.key, people);
  else html = personView(v.key);
  $('#panel').innerHTML = html;
  document.querySelector('aside').scrollTop = 0;
}
const topicsLine = ts => ts.length ? `<div class="k">${esc(ts.slice(0, 3).join(' · '))}</div>` : '';
const tagsLine = tags => tags.length ? `<div class="tags">${tagChips(tags.slice(0, 6))}</div>` : '';
function personRow(p) {
  return `<div class="row" data-person="${esc(p.name)}"><div><span class="t">${esc(p.name)}</span> ${badge(p.tier)} <span class="role">${esc(roleLabel(p.role_class))}</span></div>
    <div class="r">${newestDate(p) || ''}</div><div class="m">${esc(p.current_affiliation || '')}${p.country ? ' · ' + esc(p.country) : ''}${p.group ? ' · ' + esc(p.group.split(' @ ')[0]) : ''}</div>${tagsLine(p.tags || [])}</div>`;
}
function groupRow(g, n, m = 0) {
  return `<div class="row" data-group="${esc(g.group)}"><div><span class="t">${esc(g.pi_name)}</span> ${badge(g.tier)}</div>
    <div class="r">${n} ${T().members}${m ? ` (+${m} ${T().coauthors})` : ''}</div><div class="m">${esc(g.institution_key)} · ${esc(g.country)}</div>${tagsLine((g.tags || []).map(x => x[0]))}${topicsLine(g.topics)}</div>`;
}
function groupsList(people) {
  const counts = new Map(), coauthors = new Map();
  for (const p of people) if (p.group) { const m = isCoauthor(p) ? coauthors : counts; m.set(p.group, (m.get(p.group) || 0) + 1); }
  const rows = sortGroups(DATA.groups.filter(g => counts.get(g.group) || coauthors.get(g.group)), g => counts.get(g.group) || 0)
    .map(g => groupRow(g, counts.get(g.group) || 0, coauthors.get(g.group) || 0));
  const loose = people.filter(p => !p.group);
  return `<div class="card">${rows.join('') || `<span class="muted">${T().noMatch}</span>`}</div>` +
    (loose.length ? `<div class="card"><h3>${T().unattached} (${loose.length})</h3>${sortPeople(loose).map(personRow).join('')}</div>` : '');
}
function placesList(people) {
  const counts = new Map();
  for (const p of people) if (p.institution_key) counts.set(p.institution_key, (counts.get(p.institution_key) || 0) + 1);
  const rows = DATA.institutions.filter(i => counts.get(i.name)).sort((a, b) => filters.sort === 'name' ? a.name.localeCompare(b.name) : counts.get(b.name) - counts.get(a.name))
    .map(i => `<div class="row" data-inst="${esc(i.name)}"><div><span class="t">${esc(i.name)}</span> ${badge(i.tier)}</div>
      <div class="r">${counts.get(i.name)} ${T().people} · ${i.group_count} ${T().groups}</div><div class="m">${esc(i.country)}${i.city ? ' · ' + esc(i.city) : ''}${i.geo_source === 'country centroid' ? ' · ' + T().approx : ''}</div></div>`);
  const loose = people.filter(p => !p.institution_key);
  return `<div class="card">${rows.join('') || `<span class="muted">${T().noMatch}</span>`}</div>` +
    (loose.length ? `<div class="card"><h3>${T().noInst} (${loose.length})</h3>${sortPeople(loose).map(personRow).join('')}</div>` : '');
}
function peopleList(people) {
  return `<div class="card">${sortPeople(people).map(personRow).join('') || `<span class="muted">${T().noMatch}</span>`}</div>`;
}
function membersByRole(people) {
  const members = people.filter(p => !isCoauthor(p)), coauthors = people.filter(isCoauthor);
  return roleCounts(members).map(([k, n]) => `<h3>${esc(roleLabel(k))} (${n})</h3>` + sortPeople(members.filter(p => p.role_class === k)).map(personRow).join('')).join('') +
    (coauthors.length ? `<h3>${esc(T().coauthorsOnly)} (${coauthors.length})</h3>` + sortPeople(coauthors).map(personRow).join('') : '');
}
function institutionView(name, people) {
  const inst = DATA.institutions.find(i => i.name === name) || {};
  const here = people.filter(p => p.institution_key === name);
  const groups = sortGroups(DATA.groups.filter(g => g.institution_key === name && here.some(p => p.group === g.group)), g => here.filter(p => p.group === g.group && !isCoauthor(p)).length);
  const loose = here.filter(p => !groups.some(g => g.group === p.group));
  return `<div class="card"><h2>${esc(name)} ${badge(inst.tier)}</h2><div class="sub">${esc(inst.country)}${inst.city ? ' · ' + esc(inst.city) : ''} · ${here.length} ${T().people} · ${groups.length} ${T().groups} · ${T().position}: ${inst.geo_source === 'country centroid' ? T().approx : inst.geo_source === 'manual' ? T().manualPos : inst.geo_source.startsWith('ror:') ? link(inst.geo_source.slice(4), 'ROR') : esc(inst.geo_source)} <button class="btn" data-fly="${esc(name)}">${T().showOnMap}</button></div></div>` +
    groups.map(g => { const ms = here.filter(p => p.group === g.group), team = ms.filter(p => !isCoauthor(p));
      return `<div class="card">${groupRow(g, team.length, ms.length - team.length)}<p class="intro muted">${esc(summaryFor(g, 'group', team))}</p>${membersByRole(ms)}</div>`; }).join('') +
    (loose.length ? `<div class="card"><h3>${T().loose} (${loose.length})</h3>${sortPeople(loose).map(personRow).join('')}</div>` : '');
}
function summaryFor(x, kind, members) {
  const s = x.summary && x.summary[lang];
  if (s) return s;
  return kind === 'group' ? T().introGroup(x, members) : T().introPerson(x);
}
function groupView(name, people) {
  const g = groupOf(name); if (!g) return '<div class="card">?</div>';
  const linked = people.filter(p => p.group === name), members = linked.filter(p => !isCoauthor(p)), coauthors = linked.length - members.length;
  const fund = g.active_funding.map(f => { const [t, d] = f.split('@'); return `${esc(label(t))}${d ? ' · ' + esc(d) : ''}`; });
  return `<div class="card"><h2>${esc(g.pi_name)} ${badge(g.tier)}</h2>
    <div class="sub"><a data-inst="${esc(g.institution_key)}" href="#">${esc(g.institution_key)}</a> · ${esc(g.country)} · ${members.length} ${T().members}${coauthors ? ` (+${coauthors} ${T().coauthors})` : ''} <button class="btn" data-fly="${esc(g.institution_key)}">${T().showOnMap}</button></div>
    <p class="intro">${esc(summaryFor(g, 'group', members))}</p>
    <dl><dt>${T().pi}</dt><dd>${g.pi_in_roster ? `<a data-person="${esc(g.pi_name)}" href="#">${esc(g.pi_name)}</a>` : esc(g.pi_name)}</dd>
    ${g.homepage ? `<dt>${T().homepage}</dt><dd>${link(g.homepage)}</dd>` : ''}
    ${FACETS.length ? `<dt>${T().tags}</dt><dd>${tagChips((g.tags || []).map(x => x[0]), Object.fromEntries(g.tags || [])) || '<span class="muted">—</span>'}</dd>` : ''}
    <dt>${T().topics}</dt><dd>${g.topics.map(t => `<span class="topic">${esc(t)}</span>`).join('') || '<span class="muted">—</span>'}</dd>
    ${fund.length ? `<dt>${T().funding}</dt><dd>${fund.join('<br>')}</dd>` : ''}
    ${g.recent_outputs ? `<dt>${T().recent}</dt><dd>${list(g.recent_outputs).map(r => { const [t, rest] = r.split(/:(.*)/s); return `<b>${esc(label((t || '').split('@')[0]))}</b> ${esc((t || '').split('@')[1] || '')} ${esc((rest || '').replace(/\b([0-9a-f]{7})[0-9a-f]{33}\b/g, '$1').replace(/\|/g, ' · '))}`; }).join('<br>')}</dd>` : ''}
    ${g.open_source.length ? `<dt>${T().openSource}</dt><dd>${g.open_source.slice(0, 8).map(u => link(u)).join('<br>')}</dd>` : ''}
    </dl></div>
    <div class="card">${membersByRole(linked)}</div>
    <div class="card"><details><summary>${T().evidence} (${g.evidence_urls.length})</summary>${g.evidence_urls.slice(0, 60).map(u => link(u)).join('<br>')}</details></div>`;
}
function personView(name) {
  const p = personOf(name); if (!p) return '<div class="card">?</div>';
  const ids = Object.entries(p.ids || {}).map(([k, v]) => k === 'orcid' ? link(`https://orcid.org/${v}`, `ORCID ${v}`)
    : k === 'openalex' ? link(`https://openalex.org/${v}`, `OpenAlex ${v}`) : `${esc(k)}: ${esc(v)}`);
  const sig = s => `<li><b>${esc(label(s.signal_type))}</b> · ${esc(s.date || T().undated)} · ${esc(T().strength[s.strength] || s.strength || '')} · ${esc(channelLabel(s.channel))} · ${T().hop} ${s.hop_depth ?? ''}
      ${s.role_title ? `<br><i>${esc(s.role_title)}</i>` : ''}${s.affiliation_raw ? `<br>${esc(s.affiliation_raw)} ${esc(s.country || '')}` : ''}
      ${s.snippet ? `<br><span class="muted">${esc(s.snippet)}</span>` : ''}${s.parent ? `<br>${T().parent}: ${esc(s.parent)}` : ''}
      ${(s.topics || []).length ? `<br>${s.topics.map(t => `<span class="topic">${esc(t)}</span>`).join('')}` : ''}
      ${s.note ? `<br><span class="muted">${esc(s.note)}</span>` : ''}<br>${link(s.evidence_url)}</li>`;
  return `<div class="card"><h2>${esc(p.name)} ${badge(p.tier)} <span class="role">${esc(roleLabel(p.role_class))} · ${esc(p.role_confidence)}</span></h2>
    <div class="sub">${p.institution_key ? `<a data-inst="${esc(p.institution_key)}" href="#">${esc(p.current_affiliation)}</a>` : esc(p.current_affiliation) || '—'} · ${esc(p.country)}${p.institution_key ? ` <button class="btn" data-fly="${esc(p.institution_key)}">${T().showOnMap}</button>` : ''}</div>
    <p class="intro">${esc(summaryFor(p, 'person'))}</p>
    <dl><dt>${T().affiliation}</dt><dd>${esc(p.current_affiliation) || '—'}<br><span class="muted">${esc(p.affiliation_source)}</span></dd>
    ${p.final_pass_title || p.final_pass_affiliation ? `<dt>${T().finalPass}</dt><dd>${esc(p.final_pass_title || '')} ${esc(p.final_pass_affiliation || '')} ${esc(p.final_pass_country || '')} ${link(p.final_pass_url)}<br><span class="muted">${esc(p.last_verified)}</span></dd>` : ''}
    <dt>${T().group}</dt><dd>${p.group ? `<a data-group="${esc(p.group)}" href="#">${esc(p.group)}</a>` : `<span class="muted">${T().unattached}</span>`}${p.group_evidence ? `<br><span class="muted">${esc(p.group_evidence)}</span>` : ''}</dd>
    <dt>${T().roleEvidence}</dt><dd class="muted">${esc(p.role_evidence) || '—'}</dd>
    <dt>${T().rolesInSignals}</dt><dd>${esc(p.role)} · ${T().latest} ${esc(p.latest_role)}${p.first_pub_year ? ` · ${T().firstPub} ${esc(p.first_pub_year)}` : ''}</dd>
    <dt>${T().channels}</dt><dd>${p.channels_hit.map(c => esc(channelLabel(c))).join(', ')} · ${T().hop} ${esc(p.hop_depth)} · ${T().merge} ${esc(p.merge_confidence)} · ${T().fit} ${esc(p.fit) || '—'}</dd>
    ${p.homepage ? `<dt>${T().homepage}</dt><dd>${link(p.homepage)}</dd>` : ''}
    ${ids.length ? `<dt>${T().ids}</dt><dd>${ids.join(' · ')}</dd>` : ''}
    ${FACETS.length ? `<dt>${T().tags}</dt><dd>${tagChips(p.tags || []) || '<span class="muted">—</span>'}</dd>` : ''}
    <dt>${T().topics}</dt><dd>${(p.topics || []).map(t => `<span class="topic">${esc(t)}</span>`).join('') || '<span class="muted">—</span>'}</dd>
    ${p.notes ? `<dt>${T().notes}</dt><dd class="muted">${esc(p.notes)}</dd>` : ''}</dl></div>
    <div class="card"><h3>${T().signals} (${p.signals.length})</h3><ul class="sig">${p.signals.map(sig).join('')}</ul></div>`;
}
function about() {
  const m = DATA.meta, a = T().about;
  return `<div class="card"><p class="intro">${esc(a.how)}</p><dl>
    <dt>${a.domain}</dt><dd>${esc(m.domain) || '—'}</dd><dt>${a.date}</dt><dd>${esc(m.date)}</dd>
    <dt>${a.window}</dt><dd>${esc(m.window_start)} → ${esc(m.date)}</dd>
    <dt>${a.region}</dt><dd>${esc(m.region)} · ${a.core} ${esc(m.region_core)}</dd>
    <dt>${a.people}</dt><dd>${esc(a.peopleLine(m))}</dd>
    <dt>${a.tiers}</dt><dd>${[1, 2, 3, 4, 5].map(t => badge(t) + ' ' + esc(T().tiers[t].slice(3))).join('<br>')}</dd>
    <dt>${a.positions}</dt><dd>${esc(a.positions_)}</dd>
    <dt>${a.generated}</dt><dd>${esc(m.generated)}</dd></dl>
    <p class="muted">${esc(a.note)}</p></div>` + facetsAbout();
}
function facetsAbout() {
  if (!FACETS.length) return '';
  const counts = {};
  for (const p of DATA.persons) for (const t of p.tags || []) counts[t] = (counts[t] || 0) + 1;
  const tagged = DATA.persons.filter(p => (p.tags || []).length).length;
  return `<div class="card"><h3>${esc(T().tags)}</h3><p class="muted">${esc(T().facetsNote)} ${tagged} ${esc(T().tagged)}, ${DATA.persons.length - tagged} ${esc(T().untagged)}.</p><dl>` +
    FACETS.map(f => `<dt>${esc(i18nLabel(f.label, f.id))}</dt><dd>${tagChips(f.tags.map(t => t.id).filter(t => counts[t]), counts) || '<span class="muted">—</span>'}</dd>`).join('') + '</dl></div>';
}

// ---- chrome (labels that change with the language)
function applyLanguage() {
  const t = T();
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  $('#lang').textContent = lang === 'zh' ? 'EN' : '中文';
  $('#q').placeholder = t.search; $('#reset').textContent = t.reset;
  document.querySelectorAll('.tabs button').forEach(b => { b.textContent = t.tabs[b.dataset.tab]; b.classList.toggle('on', b.dataset.tab === state.tab); });
  const fill = (id, first, values, labelOf = x => x) => {
    const el = $(id), cur = el.value;
    el.innerHTML = `<option value="">${esc(first)}</option>` + values.map(v => `<option value="${esc(v)}">${esc(labelOf(v))}</option>`).join('');
    el.value = cur;
  };
  fill('#f-country', t.allCountries, [...new Set(DATA.persons.map(p => p.country))].filter(Boolean).sort());
  fill('#f-tier', t.allTiers, ['1', '2', '3', '4', '5'], v => t.tiersShort[v]);
  fill('#f-role', t.allRoles, ROLE_ORDER.filter(r => DATA.persons.some(p => p.role_class === r)), roleLabel);
  fill('#f-channel', t.allChannels, [...new Set(DATA.persons.flatMap(p => p.channels_hit))].sort(), channelLabel);
  $('#facets').innerHTML = FACETS.map(f => `<select data-facet="${esc(f.id)}"></select>`).join(' ');
  for (const f of FACETS) {
    const el = document.querySelector(`select[data-facet="${f.id}"]`), used = new Set(DATA.persons.flatMap(p => p.tags || []));
    el.innerHTML = `<option value="">${esc(i18nLabel(f.label, f.id))}: ${esc(t.all)}</option>` +
      f.tags.filter(x => used.has(x.id)).map(x => `<option value="${esc(x.id)}">${esc(i18nLabel(x.label, x.id))}</option>`).join('');
    el.value = filters.tags[f.id] || '';
    el.addEventListener('change', e => { filters.tags[f.id] = e.target.value; fitPending = true; render(); });
  }
  $('#sort').innerHTML = [['tier', t.sortTier], ['size', t.sortSize], ['newest', t.sortNewest], ['name', t.sortName]].map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join('');
  $('#sort').value = filters.sort;
  const bm = $('#basemap'), cur = bm.value;
  bm.innerHTML = ['esri', 'osmde', 'osm', 'none'].map(v => `<option value="${v}">${esc(t.basemaps[v])}</option>`).join('');
  bm.value = cur || 'esri';
  $('#title').textContent = `${DATA.meta.domain || 'Talent map'} · ${DATA.meta.date}`;
}

// ---- events
document.addEventListener('click', e => {
  const t = e.target.closest('[data-person],[data-group],[data-inst],[data-fly],[data-back],[data-home],[data-tab]');
  if (!t) return;
  if (t.tagName === 'A') e.preventDefault();
  if (t.dataset.person) show('person', t.dataset.person);
  else if (t.dataset.group) show('group', t.dataset.group);
  else if (t.dataset.inst) { flyToInst(t.dataset.inst); show('institution', t.dataset.inst); }
  else if (t.dataset.fly) { e.stopPropagation(); flyToInst(t.dataset.fly); }
  else if ('back' in t.dataset) back();
  else if ('home' in t.dataset) { state.view = null; state.stack = []; history.replaceState(null, '', '#'); render(); }
  else if (t.dataset.tab) { state.tab = t.dataset.tab; state.view = null; state.stack = []; history.replaceState(null, '', '#');
    document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b === t)); render(); }
});
$('#q').addEventListener('input', e => { filters.q = e.target.value.trim().toLowerCase(); fitPending = true; render(); });
for (const [id, key] of [['#f-country', 'country'], ['#f-tier', 'tier'], ['#f-role', 'role'], ['#f-channel', 'channel'], ['#sort', 'sort']]) {
  $(id).addEventListener('change', e => { filters[key] = e.target.value; if (key !== 'sort') fitPending = true; render(); });
}
$('#reset').addEventListener('click', () => { for (const k in filters) filters[k] = k === 'sort' ? 'tier' : k === 'tags' ? {} : ''; $('#q').value = '';
  document.querySelectorAll('header select').forEach(s => s.value = s.id === 'sort' ? 'tier' : ''); state.view = null; state.stack = []; history.replaceState(null, '', '#'); fitPending = true; render(); });
$('#lang').addEventListener('click', () => { lang = lang === 'zh' ? 'en' : 'zh'; try { localStorage.setItem('talent-map.lang', lang); } catch (e) {} applyLanguage(); render(); });
let basemap = 'esri';
try { basemap = localStorage.getItem('talent-map.basemap') || basemap; } catch (e) {}
$('#basemap').addEventListener('change', e => { useBasemap(e.target.value); try { localStorage.setItem('talent-map.basemap', e.target.value); } catch (err) {} });
window.addEventListener('hashchange', openFromHash);
applyLanguage();
$('#basemap').value = basemap;
useBasemap(basemap);
render();
openFromHash();
</script>
</body>
</html>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('persons')
    parser.add_argument('--domain', default='')
    parser.add_argument('--out', default='talent-map.html')
    parser.add_argument('--date', type=datetime.date.fromisoformat, default=datetime.date.today())
    parser.add_argument('--window-months', type=int, default=36)
    parser.add_argument('--region', '--region-extended', dest='region', default='EU27+UK+CH+NO')
    parser.add_argument('--region-core', default='DE+CH')
    parser.add_argument('--geo-cache', default=None, help='default: <out dir>/cache/geo/institutions.json')
    parser.add_argument('--offline', action='store_true', help='use the geo cache only; no ROR requests')
    parser.add_argument('--summaries', default=None, help='optional JSON with en/zh summaries per group and person')
    parser.add_argument('--facets', default=None,
                        help='research-direction facets JSON (assets/facets.template.json); default: facets.json next to the persons file when present')
    args = parser.parse_args()
    if args.facets is None and (Path(args.persons).parent / 'facets.json').is_file():
        args.facets = str(Path(args.persons).parent / 'facets.json')
    args.max_rows = 0  # the map always shows the whole roster
    try:
        with open(args.persons, encoding='utf-8') as source:
            persons = [json.loads(line) for line in source if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f'cannot read {args.persons}: {exc}')
    out = Path(args.out)
    geocoder = Geocoder(args.geo_cache or str(out.parent / 'cache' / 'geo' / 'institutions.json'), offline=args.offline,
                        overrides=load_geo_overrides(str(ASSETS / 'geo-overrides.json')))
    data = build_data(persons, args, geocoder, load_summaries(args.summaries), load_facets(args.facets))
    geocoder.save()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(data), encoding='utf-8')
    approx = sum(i['geo_source'] == 'country centroid' for i in data['institutions'])
    manual = sum(i['geo_source'] == 'manual' for i in data['institutions'])
    tagged = sum(bool(p['tags']) for p in data['persons'])
    print(f"wrote {out}: {data['meta']['persons']} people, {data['meta']['groups']} groups, "
          f"{data['meta']['institutions']} institutions ({manual} from the manual table, {approx} at country centroid)"
          + (f"; {tagged} people tagged via {args.facets}" if args.facets else ''), file=sys.stderr)


if __name__ == '__main__':
    main()
