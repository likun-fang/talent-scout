"""Pure person-field helpers shared by stage 4 and export (no lookups)."""
from __future__ import annotations
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


def topics_for(signals: list[dict]) -> list[str]:
    return list(dict.fromkeys(topic for signal in signals for topic in signal.get('topics', []) if topic))[:5]


def affiliation_for(person: dict) -> str:
    if person.get('final_pass_affiliation'):
        return person['final_pass_affiliation']
    if person.get('current_affiliation'):
        return person['current_affiliation']
    if person.get('affiliation_raw'):
        return person['affiliation_raw']
    signals = sorted(person.get('signals', []), key=lambda s: s.get('date') or '', reverse=True)
    return next((s['affiliation_raw'] for s in signals if s.get('affiliation_raw')), '')


def normalized(value: str) -> str:
    value = unicodedata.normalize('NFKD', value or '').casefold()
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).split())


def institution_name(value: str) -> str:
    value = normalized(value.split('||', 1)[0])
    value = re.sub(r'\b(?:the|university of|universitat|universite|universiteit van)\b', ' ', value)
    return ' '.join(value.split())


@lru_cache(maxsize=1)
def institution_aliases() -> dict[str, str]:
    # JSON is a YAML subset, so the small registry needs no YAML dependency.
    path = Path(__file__).resolve().parents[1] / 'assets/institution-aliases.yaml'
    aliases = json.loads(path.read_text(encoding='utf-8'))
    return {institution_name(alias): institution_name(canonical)
            for canonical, variants in aliases.items() for alias in [canonical, *variants]}


def institution_ids(record: dict) -> set[str]:
    ids = record.get('ids') or {}
    institution = record.get('institution') or {}
    values = [('openalex', record.get('institution_id') or ids.get('openalex_institution') or institution.get('id')),
              ('ror', record.get('ror') or ids.get('ror') or institution.get('ror'))]
    return {f"{kind}:{value.rstrip('/').rsplit('/', 1)[-1].casefold()}" for kind, value in values if value}


def same_institution(left: str | dict, right: str | dict) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        if institution_ids(left) & institution_ids(right):
            return True
    left = affiliation_for(left) if isinstance(left, dict) else left
    right = affiliation_for(right) if isinstance(right, dict) else right
    aliases = institution_aliases()
    a, b = institution_name(left), institution_name(right)
    return bool(a and b and aliases.get(a, a) == aliases.get(b, b))


def related(member: dict, leader: dict) -> bool:
    for a in member.get('signals', []):
        for b in leader.get('signals', []):
            if not same_institution(a, b):
                continue
            shared_parent = (leader.get('role_class') in {'professor', 'group_leader'}
                             and a.get('parent') and a.get('parent') == b.get('parent'))
            same_paper = (b.get('role') == 'last_author' and a.get('role') in {'first_author', 'coauthor'}
                          and a.get('evidence_url') and a.get('evidence_url') == b.get('evidence_url'))
            if shared_parent or same_paper:
                return True
    return False


def parent_name(value: str) -> str:
    return normalized(re.sub(r'\b(?:professor|prof|dr(?:[.-]ing)?|ph\.?d)\b\.?\s*', '', normalized(value)))


def homepages(person: dict) -> list[str]:
    return [v for v in [person.get('homepage'), *(s.get('homepage') for s in person.get('signals', []))] if v]


def evidence_url(person: dict) -> str:
    return next((s['evidence_url'] for s in person.get('signals', []) if s.get('evidence_url')),
                next(iter(homepages(person)), ''))


def shared_parent_link(member: dict, leader: dict) -> bool:
    targets = {parent_name(s.get(key, '')) for s in leader.get('signals', [])
               for key in ('parent', 'affiliation_raw') if s.get(key)}
    return any(parent_name(s['parent']) in targets for s in member.get('signals', []) if s.get('parent'))


def rule_one(member: dict, leader: dict, lab_parents: set[str]) -> tuple[str, str]:
    names = [leader.get('name', ''), leader.get('name_raw', '')]
    names += [s.get('name_raw', '') for s in leader.get('signals', [])]
    direct = {parent_name(v) for v in homepages(leader) + names if v}
    shared = {parent_name(s[key]) for s in leader.get('signals', [])
              for key in ('parent', 'affiliation_raw') if s.get(key)}
    rejected = ''
    for signal in member.get('signals', []):
        parent = signal.get('parent')
        key = parent_name(parent) if parent else ''
        if not key or not (key in direct or key in shared and leader.get('role_class') in {'professor', 'group_leader'}):
            continue
        url = signal.get('evidence_url') or evidence_url(leader)
        paper = signal.get('channel') in {'awards-papers', 'industry', 'competitions'} or key not in lab_parents
        if paper and not same_institution(member, leader):
            rejected = f"coauthor only, different institution: {parent} -> {leader['name']} | {url}"
            continue
        return f"parent {parent} -> {leader['name']} | {url}", ''
    return '', rejected


def choose(member: dict, candidates: list[tuple], rule: int) -> dict | None:
    if not candidates:
        return None
    original = candidates
    if len(candidates) > 1:
        candidates = [(leader, match) for leader, match in candidates
                      if same_institution(member, leader)]
    if len(candidates) != 1:
        names = ', '.join(leader['name'] for leader, _ in (candidates or original))
        return {'group': '', 'group_rule': rule,
                'group_evidence': f'rule {rule}: ambiguous: {names} | {evidence_url(member)}'}
    leader, match = candidates[0]
    return {'_leader': id(leader), 'group': f"{leader['name']} @ {affiliation_for(leader)}", 'group_rule': rule,
            'group_evidence': f'rule {rule}: {match}'}


GENERIC_HOSTS = {'sites.google.com', 'github.com', 'www.github.com', 'people.epfl.ch',
                 'scholar.google.com', 'linkedin.com', 'orcid.org', 'researchgate.net'}


def personal_hosts(person: dict) -> set[str]:
    hosts = {(urlsplit(url).hostname or '').casefold() for url in homepages(person)}
    roots = {'epfl.ch', 'ethz.ch', 'rwth-aachen.de', 'tuwien.at', 'dlr.de', 'tum.de', 'mpg.de',
             'uni-bonn.de', 'uni-bremen.de', 'uni-freiburg.de', 'tu-darmstadt.de'}
    accepted = set()
    for host in hosts:
        bare = host.removeprefix('www.')
        labels = len(bare.split('.'))
        institutional_root = (host.startswith('www.') and labels == 2 or bare in roots or
                              bare.endswith('.edu') and labels == 2 or
                              bare.endswith(('.ac.uk', '.edu.uk')) and labels == 3)
        directory = bare.startswith(('people.', 'person.', 'profiles.', 'staff.', 'users.'))
        if host and bare not in GENERIC_HOSTS and not institutional_root and not directory:
            accepted.add(host)
    return accepted


def github_org(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.hostname or '').casefold() not in {'github.com', 'www.github.com'}:
        return ''
    parts = parsed.path.strip('/').split('/')
    return parts[0].casefold() if parts[0] and parts[0] not in {'orgs', 'users', 'topics', 'search', 'settings'} else ''


def domain_link(member: dict, leader: dict) -> str:
    if leader.get('role_class') not in {'professor', 'group_leader'} and shared_parent_link(member, leader):
        return ''  # The same team page cannot bypass the team-anchor requirement through its host.
    shared = personal_hosts(member) & personal_hosts(leader)
    if shared:
        host = sorted(shared)[0]
        url = next(url for url in homepages(member) if (urlsplit(url).hostname or '').casefold() == host)
        return f"homepage host {host} -> {leader['name']} | {url}"
    return ''


def repository_link(member: dict, leader: dict) -> str:
    leader_urls = homepages(leader) + [s.get('evidence_url', '') for s in leader.get('signals', [])]
    orgs = {github_org(url) for url in leader_urls} - {''}
    for signal in member.get('signals', []):
        url = signal.get('evidence_url', '')
        if signal.get('channel') == 'open-source' and len(urlsplit(url).path.strip('/').split('/')) >= 2:
            org = github_org(url)
            if org and org in orgs:
                return f"repository org {org} -> {leader['name']} | {url}"
    return ''


def assign_groups(persons: list[dict]) -> list[dict]:
    """Resolve ordered links to unique leaders, recording the rule even for ambiguity."""
    leaders = [p for p in persons if affiliation_for(p) and (p.get('role_class') in {'professor', 'group_leader'}
               or any(s.get('role') in {'pi', 'last_author'} for s in p.get('signals', [])))]
    lab_parents = {parent_name(s['parent']) for p in persons for s in p.get('signals', [])
                   if s.get('signal_type') == 'lab_member' and s.get('parent')}
    results = []
    for person in persons:
        pi = any(s.get('role') == 'pi' for s in person.get('signals', []))
        own = {'_leader': id(person), 'group': f"{person['name']} @ {affiliation_for(person)}", 'group_rule': 4,
               'group_evidence': f"rule 4: leader self {person['name']} | {evidence_url(person)}"}
        match = own if (pi or person.get('role_class') == 'professor') and affiliation_for(person) else None
        if match is None:
            candidates = [(leader, rule_one(person, leader, lab_parents)) for leader in leaders if leader is not person]
            match = choose(person, [(leader, link) for leader, (link, _) in candidates if link], 1)
            if match is None:
                rejected = [reason for _, (_, reason) in candidates if reason]
                if rejected:
                    match = {'group': '', 'group_rule': 1, 'group_evidence': 'rule 1: ' + '; '.join(rejected)}
        for rule, link_for in ((2, domain_link), (3, repository_link)):
            if match is None:
                candidates = [(leader, link_for(person, leader)) for leader in leaders if leader is not person]
                match = choose(person, [(leader, link) for leader, link in candidates if link], rule)
        if match is None:
            candidates = [(leader, f"same institution and parent/paper -> {leader['name']} | {evidence_url(person)}")
                          for leader in leaders if leader is not person
                          and same_institution(person, leader) and related(person, leader)]
            match = choose(person, candidates, 4)
        if match is None and affiliation_for(person) and (person.get('role_class') in {'professor', 'group_leader'} or
                any(s.get('role') == 'last_author' for s in person.get('signals', [])) and
                any(other is not person and related(other, person) for other in persons)):
            match = own
        results.append({**person, 'group_rule': None, **(match or {'group': '', 'group_evidence': 'unattached'})})
    by_id = {id(person): index for index, person in enumerate(persons)}
    incoming = {p.get('_leader') for p in results if p.get('_leader')}
    for original, result in zip(persons, results):
        if id(original) in incoming and result['group_evidence'] == 'unattached':
            result.update(_leader=id(original), group=f"{original['name']} @ {affiliation_for(original)}",
                          group_rule=4, group_evidence=f"rule 4: linked leader self {original['name']} | {evidence_url(original)}")
    resolved = []
    for index, result in enumerate(results):
        path, current = [], index
        while current not in path:
            path.append(current)
            target = by_id.get(results[current].get('_leader'))
            if target is None or target == current:
                break
            current = target
        else:
            current = None
        updated = {key: value for key, value in result.items() if key != '_leader'}
        if len(path) > 1:
            if current is None or not results[current]['group']:
                names = ', '.join(results[i]['name'] for i in path)
                updated.update(group='', group_evidence=f"rule {result['group_rule']}: ambiguous: {names} (leader chain unresolved) | {evidence_url(persons[index])}")
            elif result['group'] != results[current]['group']:
                via = '; '.join(f"via {results[i]['name']}: {results[i]['group_evidence']}" for i in path[1:])
                updated.update(group=results[current]['group'], group_evidence=f"{result['group_evidence']} | {via}")
        resolved.append(updated)
    return resolved


def group_for(person: dict, leaders: list[dict], persons: list[dict]) -> str:
    """Compatibility helper; assign_groups also returns the required evidence."""
    return next(p['group'] for original, p in zip(persons, assign_groups(persons)) if original is person)
