#!/usr/bin/env python3
"""Write groups.json for the public group map: one record per research group of one field.

  group_export.py persons.enriched.jsonl --domain "<phrase>" --date YYYY-MM-DD [--region EU27+UK+CH+NO]
                  [--out DIR] [--window-months 36] [--facets facets.json] [--geo-cache FILE] [--offline]

The unit is the group: its PI, institution and homepage, with the people linked to it named under it by role.
Selection, groups, institution names, positions and direction tags are those of table_export.py and talent_map.py
(same persons, date and region), so the map and the roster agree. Nothing ranks: the record has no tier and no
score. Nothing comes from LinkedIn: a LinkedIn key or URL on a record the map is built from (its role, group or
evidence could rest on it), or anywhere in the output, stops the export. assets/groups.schema.json describes the
file. Standard library only.
"""
from __future__ import annotations
import argparse, datetime, json, re, sys, urllib.parse
from collections import Counter
from pathlib import Path
from table_export import select_persons, signal_date
from talent_map import ASSETS, Geocoder, build_data_from, load_facets, load_geo_overrides
from person_fields import TEAM_SIGNALS, normalized, same_institution_name

MEMBER_LINKS = ('team', 'project')  # a coauthor-only link is counted, not listed
# The final pass reads the PI's own or institutional page, but sometimes a news item about the PI (an award, an
# appointment); such a page verifies the group and stays in the evidence, but it is not a homepage.
NEWS_PATH = r'/(?:news|aktuell\w*|press\w*|actualit\w*|nieuws|notizie|noticias|blog|events?)/'


def linkedin_hits(value, path: str = '$') -> list[str]:
    """Where a key names LinkedIn or a URL points to a LinkedIn host; prose that mentions LinkedIn is not a hit."""
    hits = []
    if isinstance(value, dict):
        for key, item in value.items():
            if 'linkedin' in str(key).casefold():
                hits.append(f'{path}.{key}')
            hits += linkedin_hits(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits += linkedin_hits(item, f'{path}[{index}]')
    elif isinstance(value, str):
        text = value.strip()
        host = (urllib.parse.urlsplit(text).hostname or '') if re.match(r'https?://', text, re.I) else ''
        if 'linkedin' in host or re.search(r'\blinkedin\.com\b', text, re.I):
            hits.append(f'{path}: {text}')
    return hits


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', normalized(text)).strip('-')


def pages(person: dict) -> set[str]:
    """Pages that list the person: roster pages and the page the final pass read."""
    urls = {s.get('evidence_url') for s in person['signals'] if s.get('signal_type') in TEAM_SIGNALS}
    return {url for url in urls | {person.get('final_pass_url')} if url}


def team_page(people: list[dict], page_groups: dict, group: str) -> str:
    """A page that lists two or more of the group's people and nobody from another group: the group's own page.
    A page that lists people of several groups is a department or institute page."""
    counts = Counter(url for person in people for url in pages(person) if page_groups.get(url) == {group})
    return next((url for url, n in counts.most_common() if n >= 2), '')


def newest_record_date(people: list[dict], as_of: datetime.date) -> str:
    """Newest signal date up to the as-of date; a record dated later (a future event) says nothing yet."""
    dates = [s['date'] for person in people for s in person['signals']
             if s.get('date') and datetime.date.min < signal_date(s) <= as_of]
    return max(dates, key=lambda date: signal_date({'date': date}), default='')


def institution_ids(pi_record: dict | None, name: str) -> dict:
    """The PI's OpenAlex institution, only when it is the group's institution (a provider id describes the
    provider's institution, which a final-pass move can leave behind). ROR enters only as a position source."""
    if pi_record and pi_record.get('institution_id') and same_institution_name(pi_record.get('institution_name', ''), name):
        return {'openalex': pi_record['institution_id']}
    return {}


def group_record(group: dict, linked: list[dict], pi: dict | None, pi_record: dict | None, place: dict,
                 page_groups: dict, as_of: datetime.date) -> dict:
    members = sorted((p for p in linked if p['name'] != group['pi_name'] and p.get('group_link') in MEMBER_LINKS),
                     key=lambda p: normalized(p['name']))
    read = pi.get('final_pass_url', '') if pi else ''
    pi_homepage = (pi.get('homepage') or ('' if re.search(NEWS_PATH, read, re.I) else read)) if pi else ''
    named = ([pi] if pi else []) + members
    verified = max((p['last_verified'] for p in named if p.get('last_verified')), default='')
    record_date = '' if verified else newest_record_date(named or linked, as_of)
    location = None
    if place.get('lat') is not None:
        location = {'lat': place['lat'], 'lng': place['lng'], 'city': place.get('city', ''), 'source': place['geo_source']}
    return {
        'id': '-'.join(filter(None, [slug(group['pi_name']), slug(group['institution_key'])])) or 'group',
        'pi': {'name': group['pi_name'], 'role_class': pi['role_class'] if pi else 'unknown', 'homepage': pi_homepage},
        'institution': {'name': group['institution_key'], 'country': place.get('country', ''),
                        'ids': institution_ids(pi_record, group['institution_key']), 'location': location},
        'homepage': team_page(named, page_groups, group['group']) or pi_homepage,
        'tags': [tag for tag, _ in group['tags']],
        'topics': group['topics'],
        'members': [{'name': p['name'], 'role_class': p['role_class'], 'link': p['group_link']} for p in members],
        'coauthors_count': sum(p.get('group_link') == 'coauthor' for p in linked),
        'active_funding': [dict(zip(('type', 'date'), (item.split('@', 1) + [''])[:2])) for item in group['active_funding']],
        'open_source': group['open_source'],
        'evidence_urls': list(dict.fromkeys(group['evidence_urls'] + [p['final_pass_url'] for p in named if p.get('final_pass_url')])),
        'last_verified': verified or record_date,
        'last_verified_from': 'final_pass' if verified else 'record_date' if record_date else '',
        'sources': sorted({s['channel'] for p in linked for s in p['signals'] if s.get('channel')}),
        'as_of': as_of.isoformat(),
    }


def export(persons: list[dict], args, geocoder, facets: list[dict]) -> dict:
    # Tiers and the row cut never reach groups.json; the selection needs both settings all the same.
    options = argparse.Namespace(**{**vars(args), 'region_core': 'DE+CH', 'max_rows': 0})
    selection = select_persons(persons, options)
    data = build_data_from(selection, options, geocoder, facets=facets)
    selected = selection[0]  # the records behind data['persons'], in the same order
    index = {p['name']: i for i, p in enumerate(data['persons'])}  # one record per name, as the talent map picks a PI
    by_name = {name: data['persons'][i] for name, i in index.items()}
    places = {i['name']: i for i in data['institutions']}
    linked, page_groups = {}, {}
    for person in data['persons']:
        linked.setdefault(person['group'], []).append(person)
        for url in pages(person) if person['group'] else ():
            page_groups.setdefault(url, set()).add(person['group'])
    groups = sorted(data['groups'], key=lambda g: (normalized(g['institution_key']), normalized(g['pi_name']), g['group']))
    records, seen = [], Counter()
    for group in groups:
        record = group_record(group, linked.get(group['group'], []), by_name.get(group['pi_name']),
                              selected[index[group['pi_name']]] if group['pi_name'] in index else None,
                              places.get(group['institution_key'], {}), page_groups, args.date)
        seen[record['id']] += 1
        if seen[record['id']] > 1:
            record['id'] += f"-{seen[record['id']]}"
        records.append(record)
    doc = {'meta': {'domain': args.domain, 'as_of': args.date.isoformat(), 'region': args.region,
                    'window_start': data['meta']['window_start'], 'facets': data['meta']['facets']},
           'groups': records}
    # The map is built from the PIs' records and everyone linked to a group (coauthors feed topics and evidence).
    # Notes are left out: they log searches, LinkedIn searches that were not used among them, and feed no field.
    exported = {g['group'] for g in groups}
    used = {i for i, p in enumerate(data['persons']) if p['group'] in exported} | {index[g['pi_name']] for g in groups
                                                                                if g['pi_name'] in index}
    found = [f"{selected[i].get('name')}: {hit}" for i in sorted(used)
             for hit in linkedin_hits({key: value for key, value in selected[i].items() if key != 'notes'})]
    found += [f"{r['id']} ({r['pi']['name']}): {hit}" for r in records for hit in linkedin_hits(r)]
    found += linkedin_hits(doc['meta'], '$.meta')
    if found:
        raise SystemExit('LinkedIn data would reach the group map; fix the source records: ' + '; '.join(found[:10])
                         + (f' (+{len(found) - 10} more)' if len(found) > 10 else ''))
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('persons')
    parser.add_argument('--domain', default='')
    parser.add_argument('--date', type=datetime.date.fromisoformat, default=datetime.date.today())
    parser.add_argument('--window-months', type=int, default=36)
    parser.add_argument('--region', '--region-extended', dest='region', default='EU27+UK+CH+NO')
    parser.add_argument('--out', default='site', help='directory for groups.json')
    parser.add_argument('--facets', default=None,
                        help='research-direction facets JSON; default: facets.json next to the persons file when present')
    parser.add_argument('--geo-cache', default=None, help='default: cache/geo/institutions.json next to the persons file')
    parser.add_argument('--offline', action='store_true', help='use the geo cache only; no ROR requests')
    args = parser.parse_args()
    if not 1 <= args.window_months <= (args.date.year - 1) * 12 + args.date.month - 1:
        parser.error('--window-months must be positive and not reach before year 1')
    source = Path(args.persons)
    if args.facets is None and (source.parent / 'facets.json').is_file():
        args.facets = str(source.parent / 'facets.json')
    try:
        with source.open(encoding='utf-8') as lines:
            persons = [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f'cannot read {args.persons}: {exc}')
    geocoder = Geocoder(args.geo_cache or str(source.parent / 'cache' / 'geo' / 'institutions.json'), offline=args.offline,
                        overrides=load_geo_overrides(str(ASSETS / 'geo-overrides.json')))
    doc = export(persons, args, geocoder, load_facets(args.facets))
    geocoder.save()
    out = Path(args.out) / 'groups.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    located = sum(g['institution']['location'] is not None for g in doc['groups'])
    print(f"wrote {out}: {len(doc['groups'])} groups ({located} placed on the map)", file=sys.stderr)


if __name__ == '__main__':
    main()
