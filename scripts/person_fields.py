"""Pure person-field helpers shared by stage 4 and export (no lookups)."""
from __future__ import annotations


def topics_for(signals: list[dict]) -> list[str]:
    return list(dict.fromkeys(topic for signal in signals for topic in signal.get('topics', []) if topic))[:5]


def affiliation_for(person: dict) -> str:
    if person.get('current_affiliation'):
        return person['current_affiliation']
    signals = sorted(person.get('signals', []), key=lambda s: s.get('date') or '', reverse=True)
    return next((s['affiliation_raw'] for s in signals if s.get('affiliation_raw')), '')


def same_institution(left: str, right: str) -> bool:
    # Exact normalized names are deliberately conservative: no institution alias registry exists.
    return bool(left and right and ' '.join(left.casefold().split()) == ' '.join(right.casefold().split()))


def related(member: dict, leader: dict) -> bool:
    for a in member.get('signals', []):
        for b in leader.get('signals', []):
            if not same_institution(a.get('affiliation_raw', ''), b.get('affiliation_raw', '')):
                continue
            shared_parent = a.get('parent') and a.get('parent') == b.get('parent')
            same_paper = (b.get('role') == 'last_author' and a.get('role') in {'first_author', 'coauthor'}
                          and a.get('evidence_url') and a.get('evidence_url') == b.get('evidence_url'))
            if shared_parent or same_paper:
                return True
    return False


def assign_groups(persons: list[dict]) -> list[dict]:
    """PI signals anchor a group; a shared-paper last author can also identify its leader.

    Infer only a unique leader at the person's current institution. Ambiguity stays ungrouped.
    """
    leaders = [p for p in persons if any(s.get('role') in {'pi', 'last_author'} for s in p.get('signals', []))]
    return [{**p, 'group': group_for(p, leaders, persons)} for p in persons]


def group_for(person: dict, leaders: list[dict], persons: list[dict]) -> str:
    institution = affiliation_for(person)
    if not institution:
        return ''
    if any(s.get('role') == 'pi' for s in person.get('signals', [])):
        return f"{person['name']} @ {institution}"
    candidates = {f"{leader['name']} @ {institution}" for leader in leaders
                  if leader is not person and same_institution(institution, affiliation_for(leader))
                  and related(person, leader)}
    # Last authors with a linked coauthor are the same group's leader, too.
    if any(s.get('role') == 'last_author' for s in person.get('signals', [])) and any(
            other is not person and same_institution(institution, affiliation_for(other))
            and related(other, person) for other in persons):
        candidates.add(f"{person['name']} @ {institution}")
    return next(iter(candidates)) if len(candidates) == 1 else ''
