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
    if person.get('affiliation_raw'):
        return person['affiliation_raw']
    if person.get('current_affiliation'):
        return person['current_affiliation']
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
            shared_parent = a.get('parent') and a.get('parent') == b.get('parent')
            same_paper = (b.get('role') == 'last_author' and a.get('role') in {'first_author', 'coauthor'}
                          and a.get('evidence_url') and a.get('evidence_url') == b.get('evidence_url'))
            if shared_parent or same_paper:
                return True
    return False


def parent_name(value: str) -> str:
    return normalized(re.sub(r'\b(?:professor|prof|dr|dr-ing|ph\.?d)\.?\s*', '', normalized(value)))


def homepages(person: dict) -> list[str]:
    return [v for v in [person.get('homepage'), *(s.get('homepage') for s in person.get('signals', []))] if v]


def evidence_url(person: dict) -> str:
    return next((s['evidence_url'] for s in person.get('signals', []) if s.get('evidence_url')),
                next(iter(homepages(person)), ''))


def rule_one(member: dict, leader: dict) -> str:
    names = [leader.get('name', ''), leader.get('name_raw', '')]
    names += [s.get('name_raw', '') for s in leader.get('signals', [])]
    values = homepages(leader) + names
    values += [s.get(key, '') for s in leader.get('signals', []) for key in ('parent', 'affiliation_raw')]
    targets = {parent_name(v) for v in values if v}
    for signal in member.get('signals', []):
        parent = signal.get('parent')
        if parent and parent_name(parent) in targets:
            return f"parent {parent} -> {leader['name']} | {signal.get('evidence_url') or evidence_url(leader)}"
    return ''


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
    return {'group': f"{leader['name']} @ {affiliation_for(leader)}", 'group_rule': rule,
            'group_evidence': f'rule {rule}: {match}'}


GENERIC_HOSTS = {'sites.google.com', 'github.com', 'www.github.com', 'people.epfl.ch',
                 'scholar.google.com', 'linkedin.com', 'orcid.org', 'researchgate.net'}


def personal_hosts(person: dict) -> set[str]:
    hosts = {(urlsplit(url).hostname or '').casefold() for url in homepages(person)}
    # Shared directories and institution roots cannot identify a particular team.
    return {host for host in hosts if host and host not in GENERIC_HOSTS
            and not host.startswith(('www.', 'people.', 'person.', 'profiles.', 'staff.', 'users.'))
            and len(host.split('.')) > 2} - {
                host for host in hosts if len(host.split('.')) == 3 and host.endswith(('.ac.uk', '.edu.uk'))}


def github_org(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.hostname or '').casefold() not in {'github.com', 'www.github.com'}:
        return ''
    parts = parsed.path.strip('/').split('/')
    return parts[0].casefold() if parts[0] and parts[0] not in {'orgs', 'users', 'topics', 'search', 'settings'} else ''


def domain_link(member: dict, leader: dict) -> str:
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
    results = []
    for person in persons:
        pi = any(s.get('role') == 'pi' for s in person.get('signals', []))
        own = {'group': f"{person['name']} @ {affiliation_for(person)}", 'group_rule': 4,
               'group_evidence': f"rule 4: leader self {person['name']} | {evidence_url(person)}"}
        match = own if pi and affiliation_for(person) else None
        if match is None:
            candidates = [(leader, rule_one(person, leader)) for leader in leaders if leader is not person]
            match = choose(person, [(leader, link) for leader, link in candidates if link], 1)
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
    return results


def group_for(person: dict, leaders: list[dict], persons: list[dict]) -> str:
    """Compatibility helper; assign_groups also returns the required evidence."""
    return next(p['group'] for original, p in zip(persons, assign_groups(persons)) if original is person)
