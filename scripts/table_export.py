#!/usr/bin/env python3
"""Write roster.csv and roster.md from persons.jsonl with the fixed talent-scout columns.

  table_export.py persons.jsonl [--domain "<phrase>"] [--date YYYY-MM-DD] [--out roster]
                  [--region EU27+UK+CH+NO] [--max-rows N] [--coverage-dir signals/]
Rows whose country is outside the region go to <out>.out-of-region.json. With --max-rows the table is cut
after sorting and the Coverage block says how many rows were cut. --coverage-dir appends every
*.coverage.md it finds to roster.md. Standard library only.
A person qualifies through at least one signal dated inside the window (default: the 36 months ending on
--date). Ranking, channels_hit and hop_depth use qualifying signals only; older or undated signals stay in the
row as evidence (signals and evidence_urls columns) and are listed in <out>.excluded-signals.json.
Ranking uses tier, eligible channel count, strongest signal, newest signal date, then name.
"""
from __future__ import annotations
import argparse, csv, datetime, glob, json, os, sys
from pathlib import Path
from current_affiliation import region_codes, apply_final_pass, classify_role, FUNDING_PREFIXES
from person_fields import topics_for, assign_groups, past_position

COLUMNS = ["name", "current_affiliation", "country", "role", "domain", "channels_hit", "signals",
           "evidence_urls", "ids", "hop_depth", "merge_confidence", "affiliation_source", "last_verified", "notes",
           "fit", "first_pub_year", "latest_role", "homepage", "ranked_channels",
           "role_class", "role_confidence", "tier", "topics", "group", "role_evidence"]

STRENGTH = {"high": 3, "medium": 2, "low": 1}

def signal_date(signal: dict) -> datetime.date:
    value = (signal.get("date") or "")[:10]
    value += "-01-01" if len(value) == 4 else "-01" if len(value) == 7 else ""
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return datetime.date.min

def ranked_channels(p: dict) -> int:
    return len({s["channel"] for s in p.get("qualifying", p.get("signals", [])) if s.get("channel") and
                (s.get("hop_depth", 0) == 0 or s.get("strength") in {"high", "medium"})})

def window_start(end: datetime.date, months: int) -> datetime.date:
    """First day of the window: `months` back from `end`, same day of month (clamped), inclusive."""
    year, month = divmod((end.year * 12 + end.month - 1) - months, 12)
    month += 1
    last = (datetime.date(year + month // 12, month % 12 + 1, 1) - datetime.timedelta(days=1)).day
    return datetime.date(year, month, min(end.day, last))

def in_window(signal: dict, start: datetime.date, end: datetime.date) -> bool:
    """A year-only date (GEPRIS start years) qualifies when that year overlaps the window at all."""
    date = signal_date(signal)
    if date == datetime.date.min:
        return False
    if len((signal.get("date") or "").strip()) == 4:
        return start.year <= date.year <= end.year
    return start <= date <= end

ROSTER_SIGNALS = {"lab_member", "team_member", "company_team", "company_member", "graduiertenkolleg_member", "imprs_member"}


def verified_in_window(person: dict, start: datetime.date, end: datetime.date) -> bool:
    """A final-pass read on or after the window start dates the person's undated roster signals: the page was read
    then and still listed them, which is the strongest evidence of a current role a roster can give. The pass runs
    after the run date, so the read is not bounded by the window end."""
    verified = (person.get("last_verified") or "").strip()[:10]
    try:
        return start <= datetime.date.fromisoformat(verified)
    except ValueError:
        return False


def filter_window(persons: list[dict], start: datetime.date, end: datetime.date) -> tuple:
    """Split each person's signals into qualifying (in window) and background. A person without a
    qualifying signal is dropped; the others keep every signal as evidence but rank on qualifying ones."""
    kept, rejected = [], []
    for person in persons:
        qualifying = []
        verified = verified_in_window(person, start, end)
        for signal in person.get("signals", []):
            date = signal_date(signal)
            undated_roster = date == datetime.date.min and signal.get("signal_type") in ROSTER_SIGNALS
            if in_window(signal, start, end) or (verified and undated_roster):
                qualifying.append(signal)
            else:
                reason = "missing_or_invalid_date" if date == datetime.date.min else "outside_window"
                rejected.append({"name": person.get("name", ""), "reason": reason, "signal": signal})
        if qualifying:
            kept.append({**person, "qualifying": qualifying,
                         "channels_hit": sorted({s["channel"] for s in qualifying if s.get("channel")}),
                         "hop_depth": min(s.get("hop_depth", 0) for s in qualifying)})
    return kept, rejected

# Tie-break for the row role: the role that says most about the person wins, never set iteration order.
ROLE_RANK = ['pi', 'last_author', 'first_author', 'founder', 'maintainer', 'inventor', 'team_member', 'coauthor']


def rank_known(role: str) -> int:
    return ROLE_RANK.index(role) if role in ROLE_RANK else len(ROLE_RANK)


def row_for(p: dict, domain: str, date: str) -> dict:
    p = apply_final_pass(p)
    sigs = p.get("signals", [])
    newest = max(sigs, key=signal_date, default={})
    fits = {s["fit"] for s in sigs if s.get("fit")}
    fit = "" if not fits else "core" if fits == {"core"} else "adjacent" if fits == {"adjacent"} else "mixed"
    roles = [s.get("role") for s in sigs if s.get("role") and s.get("role") != "unknown"]
    role = max(sorted(set(roles), key=rank_known), key=roles.count) if roles else "unknown"
    return {
        "name": p.get("name", ""),
        # A past position read in the final pass leaves no current affiliation; older records do not refill it.
        "current_affiliation": "" if past_position(p) else p.get("current_affiliation") or newest.get("affiliation_raw", ""),
        "country": country_for(p),
        "role": role,
        "domain": domain,
        "channels_hit": ";".join(p.get("channels_hit", [])),
        "signals": ";".join(f"{s.get('signal_type')}@{s.get('date','')}" for s in sigs),
        "evidence_urls": ";".join(dict.fromkeys(s.get("evidence_url", "") for s in sigs)),
        "ids": ";".join(f"{k}:{v}" for k, v in (p.get("ids") or {}).items()),
        "hop_depth": p.get("hop_depth", 0),
        "merge_confidence": p.get("merge_confidence", "low"),
        "affiliation_source": p.get("affiliation_source") or f"evidence {newest.get('date','')}",
        "last_verified": p.get("last_verified") or "",
        "notes": p.get("notes", ""),
        "fit": fit,
        "first_pub_year": p.get("first_pub_year", ""),
        "latest_role": newest.get("role") or "unknown",
        "homepage": p.get("homepage") or next((s["homepage"] for s in sigs if s.get("homepage")), ""),
        "ranked_channels": ranked_channels(p),
        "role_class": p.get("role_class", "unknown"),
        "role_confidence": p.get("role_confidence", "low"),
        "tier": p.get("tier", 5),
        "topics": ";".join(topics_for(sigs)),
        "group": p.get("group", ""),
        "role_evidence": p.get("role_evidence", ""),
    }

def sort_key(p: dict) -> tuple:
    sigs = p.get("qualifying", p.get("signals", []))
    strongest = max((STRENGTH.get(s.get("strength"), 0) for s in sigs), default=0)
    newest = max((signal_date(s) for s in sigs), default=datetime.date.min)
    return (p.get("tier", 5), -ranked_channels(p), -strongest, -newest.toordinal(), p.get("name", ""))

def flat(value) -> str:
    return ' '.join(str(value).split())


def write_md(rows: list[dict], path: str, coverage: str, columns: list[str] = COLUMNS, appendix: str = "") -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n")
        for r in rows:
            f.write("| " + " | ".join(flat(r[c]).replace("|", "\\|") for c in columns) + " |\n")
        f.write("\n## Coverage\n\n" + coverage + appendix)

def coverage_text(kept: int, cut: int, out_of_region: int, cov_dir: str | None) -> str:
    lines = [f"- rows in table: {kept}", f"- rows cut at --max-rows: {cut}", f"- persons outside region (see .out-of-region.json): {out_of_region}", ""]
    for path in sorted(glob.glob(os.path.join(cov_dir, "*.coverage.md"))) if cov_dir else []:
        lines.append(f"### {os.path.basename(path)}\n")
        with open(path, encoding="utf-8") as source:
            lines.append(source.read().strip() + "\n")
    return "\n".join(lines)


def country_for(person: dict) -> str:
    if past_position(person):
        return ''  # the page read says the position is over; no current country until a current one is read
    if person.get('final_pass_affiliation'):
        return person.get('final_pass_country') or ''
    newest = max(person.get('signals', []), key=signal_date, default={})
    return person.get('country') or newest.get('country', '')


def tier_for(person: dict, core: set[str], extended: set[str] | None = None) -> int:
    """1 core professor/group leader, 2 extended professor/group leader, 3 core researcher/PhD student,
    4 extended PhD student, 5 everyone else in the region. Extended means extended minus core."""
    country = country_for(person)
    if country not in (extended if extended is not None else region_codes('EU27+UK+CH+NO')):
        return 5  # Export removes these records before ranking.
    role = person.get('role_class', 'unknown')
    in_core = country in core
    if role in {'professor', 'group_leader'}:
        return 1 if in_core else 2
    if in_core and role in {'researcher', 'phd_student'}:
        return 3
    if role == 'phd_student':
        return 4
    return 5


def evidence_appendix(persons: list[dict]) -> str:
    lines = ['\n## Evidence\n']
    for person in persons:
        lines.append(f"\n### {person['name']}\n")
        lines.append(flat(person.get('role_evidence', 'Role evidence unavailable')) + '\n')
        lines.append(flat(person.get('group_evidence', 'unattached')) + '\n')
        lines.extend(flat(f"- {s.get('signal_type', '')}@{s.get('date') or ''}: {s.get('snippet', '')} | {s.get('evidence_url', '')}")
                     for s in person.get('signals', []))
    return '\n'.join(lines) + '\n'


GROUP_COLUMNS = ['group', 'pi_name', 'institution', 'country', 'tier', 'homepage', 'topics', 'members',
                 'member_count', 'recent_outputs', 'active_funding', 'open_source', 'evidence_urls']


def unique_signals(persons: list[dict]) -> list[dict]:
    signals = [s for p in persons for s in p.get('signals', [])]
    # The same paper or grant may occur on several members' records.
    keyed = {}
    for signal in signals:
        key = (signal.get('signal_type'), signal.get('date'), signal.get('evidence_url'))
        previous = keyed.get(key)
        if previous is None or STRENGTH.get(signal.get('strength'), 0) > STRENGTH.get(previous.get('strength'), 0):
            keyed[key] = signal
    return list(keyed.values())


def join_unique(values) -> str:
    return ';'.join(dict.fromkeys(value for value in values if value))


def group_row(group: str, persons: list[dict], start: datetime.date, end: datetime.date) -> dict:
    members = sorted(persons, key=lambda p: (p['tier'], p.get('name', '')))
    pi_name, _, institution = group.rpartition(' @ ')
    pi = next((p for p in members if p.get('name') == pi_name), {})
    signals = [s for p in members for s in p.get('signals', [])]
    recent = sorted((s for s in unique_signals(members) if in_window(s, start, end)),
                    key=lambda s: (-STRENGTH.get(s.get('strength'), 0), -signal_date(s).toordinal(),
                                   s.get('signal_type', ''), s.get('evidence_url', '')))
    return {
        'group': group or '(unattached)', 'pi_name': pi_name, 'institution': institution,
        'country': join_unique(country_for(p) for p in members), 'tier': min(p['tier'] for p in members),
        'homepage': pi.get('homepage') or next((s['homepage'] for s in pi.get('signals', []) if s.get('homepage')), ''),
        'topics': ';'.join(topics_for(signals)),
        'members': ';'.join(f"{p['name']}({p.get('role_class', 'unknown')})" for p in members),
        'member_count': len(members),
        'recent_outputs': ';'.join(f"{s.get('signal_type')}@{s.get('date') or ''}: {(s.get('snippet') or '')[:80]}" for s in recent[:3]),
        'active_funding': join_unique(f"{s.get('signal_type')}@{s.get('date') or ''}" for s in signals
                                      if s.get('signal_type', '').startswith(FUNDING_PREFIXES)
                                      or s.get('signal_type') in ('national_project', 'national_fellowship')),
        'open_source': join_unique(s.get('evidence_url', '') for s in signals if s.get('channel') == 'open-source'),
        'evidence_urls': join_unique(s.get('evidence_url', '') for s in signals),
    }


def group_rows(persons: list[dict], start: datetime.date, end: datetime.date) -> list[dict]:
    groups = {}
    for person in persons:
        groups.setdefault(person.get('group') or '', []).append(person)
    rows = [group_row(group, members, start, end) for group, members in groups.items()]
    return sorted(rows, key=lambda row: (row['group'] == '(unattached)', row['tier'], -row['member_count'], row['pi_name']))


def write_csv(rows: list[dict], path: str, columns: list[str]) -> None:
    with open(path, 'w', encoding='utf-8-sig', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: flat(value) for key, value in row.items()} for row in rows)


def write_groups(persons: list[dict], out: str, start: datetime.date, end: datetime.date) -> None:
    rows = group_rows(persons, start, end)
    path = Path(out).parent / 'groups'
    count = sum(bool(p.get('group')) for p in persons)
    coverage = (f"- groups: {sum(row['group'] != '(unattached)' for row in rows)}\n"
                f"- unattached persons: {len(persons) - count}\n"
                '- scope: people retained in the cut roster\n')
    write_csv(rows, str(path) + '.csv', GROUP_COLUMNS)
    write_md(rows, str(path) + '.md', coverage, GROUP_COLUMNS)


def select_persons(persons: list[dict], args) -> tuple:
    persons = [apply_final_pass(p) for p in persons]
    persons = [{**p, **classify_role(p, args.date.year)} if p.get('final_pass_affiliation') or
               p.get('final_pass_title') or p.get('linkedin_headline') else p for p in persons]
    if any(p.get('final_pass_affiliation') or p.get('final_pass_title') for p in persons):
        persons = assign_groups(persons)
    start = window_start(args.date, args.window_months)
    qualified, rejected = filter_window(persons, start, args.date)
    codes, core = region_codes(args.region), region_codes(args.region_core)
    eligible = [{**p, 'tier': tier_for(p, core, codes)} for p in qualified
                if any(s.get('evidence_url') for s in p.get('signals', []))]
    in_region = sorted((p for p in eligible if country_for(p) in codes), key=sort_key)
    outside = [row_for(p, args.domain, args.date.isoformat()) for p in eligible if country_for(p) not in codes]
    selected = in_region[:args.max_rows] if args.max_rows else in_region
    return selected, outside, rejected, len(in_region) - len(selected), len(persons) - len(qualified)


def window_coverage(persons: list[dict], selected: list[dict], start: datetime.date,
                    end: datetime.date, no_qualifying: int) -> str:
    retained_background = sum(not in_window(s, start, end) for p in selected for s in p.get('signals', []))
    omitted_signals = sum(len(p.get('signals', [])) for p in persons) - sum(len(p.get('signals', [])) for p in selected)
    return (f'- signal window: {start} to {end} (inclusive; month-only dates use the first day; year-only dates qualify when the year overlaps the window)\n'
            f'- signals outside the window or undated, retained on table persons as evidence but not ranked: {retained_background}\n'
            f'- signals belonging to omitted persons (window, region, missing evidence or row cut): {omitted_signals}\n'
            '- window-excluded signals from both retained and omitted persons: see .excluded-signals.json\n'
            f'- persons without a qualifying signal, not in table: {no_qualifying}\n')


def export(persons: list[dict], args) -> None:
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    selected, outside, rejected, cut, no_qualifying = select_persons(persons, args)
    rows = [row_for(p, args.domain, args.date.isoformat()) for p in selected]
    start = window_start(args.date, args.window_months)
    write_csv(rows, f'{args.out}.csv', COLUMNS)
    with open(f'{args.out}.out-of-region.json', 'w', encoding='utf-8') as target:
        json.dump([{k: r[k] for k in ('name', 'current_affiliation', 'country', 'affiliation_source')} for r in outside], target, ensure_ascii=False, indent=1)
    with open(f'{args.out}.excluded-signals.json', 'w', encoding='utf-8') as target:
        json.dump(rejected, target, ensure_ascii=False, indent=2)
    coverage = window_coverage(persons, selected, start, args.date, no_qualifying)
    coverage += coverage_text(len(rows), cut, len(outside), args.coverage_dir)
    write_md(rows, f'{args.out}.md', coverage, appendix=evidence_appendix(selected))
    write_groups(selected, args.out, start, args.date)
    print(f'wrote {len(rows)} rows ({cut} cut, {len(outside)} outside region) → {args.out}.csv, {args.out}.md, groups.csv, groups.md', file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('persons')
    parser.add_argument('--domain', default='')
    parser.add_argument('--out', default='roster')
    parser.add_argument('--date', type=datetime.date.fromisoformat, default=datetime.date.today())
    parser.add_argument('--window-months', type=int, default=36)
    parser.add_argument('--region', '--region-extended', dest='region', default='EU27+UK+CH+NO')
    parser.add_argument('--region-core', default='DE+CH')
    parser.add_argument('--max-rows', type=int, default=0)
    parser.add_argument('--coverage-dir', default=None)
    args = parser.parse_args()
    if not 1 <= args.window_months <= (args.date.year - 1) * 12 + args.date.month - 1:
        parser.error('--window-months must be positive and not reach before year 1')
    if args.max_rows < 0:
        parser.error('--max-rows must be non-negative')
    try:
        with open(args.persons, encoding='utf-8') as source:
            persons = [json.loads(line) for line in source if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'bad input: {exc}')
    export(persons, args)


if __name__ == '__main__':
    main()
