#!/usr/bin/env python3
"""Check groups.json before it is published.

  check_groups.py groups.json --known assets/known-groups/<field>.json --as-of YYYY-MM-DD
                  [--persons persons.enriched.jsonl] [--sample 30] [--seed 2026]

(a) Recall: at least 90% of the known groups are in the file, with the same PI (accents and case ignored, same
surname and first initial) at the same institution (alias registry); an entry that names several institutions (a PI
who holds posts at two) counts on any of them. Each miss says whether the PI leads a group
at another institution, is in the persons file without a group of their own (needs --persons), or is absent.
(b) Freshness: at most 10% of groups were last verified more than 12 months before --as-of.
(c) No LinkedIn key or URL anywhere in the file.
(d) A seeded sample of groups, printed as a table for the manual spot check.
Prints every result and exits 1 when (a), (b) or (c) fails. Standard library only.
"""
from __future__ import annotations
import argparse, datetime, json, random, re, sys
from pathlib import Path
from table_export import signal_date, window_start
from person_fields import normalized, same_institution_name
from group_export import linkedin_hits

RECALL_MIN = 0.9
STALE_MAX = 0.1
UMLAUTS = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue'})


def name_keys(name: str) -> set[tuple[str, str]]:
    """(surname, first initial) for the accent-free spelling and for German umlauts written out, so Kühne
    matches both Kuhne and Kuehne."""
    keys = set()
    for spelling in (name, name.translate(UMLAUTS)):
        words = re.findall(r'[a-z]+', normalized(spelling))
        if words:
            keys.add((words[-1], words[0][0]))
    return keys


def same_pi(left: str, right: str) -> bool:
    return bool(name_keys(left or '') & name_keys(right or ''))


def institutions(item: dict) -> list[str]:
    return [item['institution']] if isinstance(item['institution'], str) else item['institution']


def recall(groups: list[dict], known: list[dict], persons: list[dict] | None) -> tuple[list, list]:
    hits, misses = [], []
    for item in known:
        same = [g for g in groups if same_pi(g['pi']['name'], item['pi'])]
        here = next((g for g in same if any(same_institution_name(g['institution']['name'], name)
                                            for name in institutions(item))), None)
        if here:
            hits.append((item, here))
        elif same:
            misses.append((item, 'group under another institution: ' + '; '.join(g['institution']['name'] for g in same)))
        elif persons is None:
            misses.append((item, 'not a group (no --persons to look further)'))
        else:
            found = [p for p in persons if same_pi(p.get('name', ''), item['pi'])]
            misses.append((item, 'PI present in persons but no group: ' + '; '.join(
                f"{p.get('name')} ({p.get('final_pass_affiliation') or p.get('current_affiliation') or '?'}; "
                f"group field: {p.get('group') or 'unattached'})" for p in found) if found else 'absent'))
    return hits, misses


def verified_since(value: str, cutoff: datetime.date) -> bool:
    """A year-only date counts when that year reaches the cutoff, as a year-only signal does in the window."""
    value = (value or '').strip()
    if re.fullmatch(r'\d{4}', value):
        return int(value) >= cutoff.year
    date = signal_date({'date': value})
    return date != datetime.date.min and date >= cutoff


def stale_groups(groups: list[dict], as_of: datetime.date) -> list[dict]:
    cutoff = window_start(as_of, 12)
    return [g for g in groups if not verified_since(g.get('last_verified', ''), cutoff)]


def sample(groups: list[dict], size: int, seed: int) -> list[dict]:
    chosen = random.Random(seed).sample(groups, min(size, len(groups)))
    return sorted(chosen, key=lambda g: (normalized(g['institution']['name']), normalized(g['pi']['name'])))


def cell(value: str) -> str:
    return ' '.join(str(value).split()).replace('|', '\\|')


def load_json(path: str, what: str):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'cannot read {what} {path}: {exc}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('groups')
    parser.add_argument('--known', required=True,
                        help='{"note": ..., "groups": [{"pi", "institution" (a name or a list of names), "country"}]}')
    parser.add_argument('--as-of', type=datetime.date.fromisoformat, required=True)
    parser.add_argument('--persons', default=None, help='persons file, to tell a PI without a group from an absent one')
    parser.add_argument('--sample', type=int, default=30)
    parser.add_argument('--seed', type=int, default=2026)
    args = parser.parse_args()
    doc, known = load_json(args.groups, 'groups'), load_json(args.known, 'known groups')
    if not isinstance(doc, dict) or not isinstance(doc.get('groups'), list):
        raise SystemExit(f'{args.groups}: expected an object with a "groups" list')
    if not isinstance(known, dict) or not isinstance(known.get('groups'), list) or not all(
            isinstance(k, dict) and k.get('pi') and k.get('institution') and (isinstance(k['institution'], str) or (
                isinstance(k['institution'], list) and all(isinstance(name, str) and name for name in k['institution'])))
            for k in known['groups']):
        raise SystemExit(f'{args.known}: expected {{"groups": [{{"pi": ..., "institution": a name or a list of names}}]}}')
    persons = None
    if args.persons:
        try:
            with open(args.persons, encoding='utf-8') as lines:
                persons = [json.loads(line) for line in lines if line.strip()]
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f'cannot read persons {args.persons}: {exc}')
    groups, failed = doc['groups'], False
    print(f'groups: {len(groups)} (as of {args.as_of})')

    hits, misses = recall(groups, known['groups'], persons)
    share = len(hits) / len(known['groups']) if known['groups'] else 1.0
    failed |= share < RECALL_MIN
    print(f"(a) {'PASS' if share >= RECALL_MIN else 'FAIL'} recall: {len(hits)}/{len(known['groups'])} = {share:.0%}"
          f" of the known groups (minimum {RECALL_MIN:.0%})")
    for item, reason in misses:
        print(f"  - {item['pi']} ({' or '.join(institutions(item))}): {reason}")

    stale = stale_groups(groups, args.as_of)
    share = len(stale) / len(groups) if groups else 0.0
    failed |= share > STALE_MAX
    print(f"(b) {'PASS' if share <= STALE_MAX else 'FAIL'} staleness: {len(stale)}/{len(groups)} = {share:.1%} last verified"
          f" before {window_start(args.as_of, 12)} or never (maximum {STALE_MAX:.0%})")
    for group in stale:
        print(f"  - {group['id']} | {group['pi']['name']} | {group['institution']['name']} | {group.get('last_verified') or 'never'}")

    linkedin = linkedin_hits(doc)
    failed |= bool(linkedin)
    print(f"(c) {'FAIL' if linkedin else 'PASS'} linkedin: {len(linkedin)} keys or URLs")
    for hit in linkedin:
        print(f'  - {hit}')

    chosen = sample(groups, args.sample, args.seed)
    print(f'(d) sample of {len(chosen)} groups (seed {args.seed}) for the manual spot check:')
    print('| group | PI | institution | homepage |\n|---|---|---|---|')
    for group in chosen:
        print(f"| {cell(group['id'])} | {cell(group['pi']['name'])} | {cell(group['institution']['name'])} | {cell(group.get('homepage', ''))} |")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
