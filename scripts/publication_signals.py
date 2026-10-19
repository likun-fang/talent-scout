"""Authorship roles read from the full author list, and one observation per work for role inference.

Stage 3 keeps only in-region authors of a work. Numbering that shortlist makes the first European
author a "first author"; `author_position` records the place in the complete list instead.
"""
from __future__ import annotations
import re
from urllib.parse import unquote

POSITION_ROLES = {'first': 'first_author', 'middle': 'coauthor', 'last': 'last_author'}
AUTHORSHIP = set(POSITION_ROLES.values())


def author_role(signal: dict) -> str:
    """The role implied by `author_position`, else the recorded role."""
    return POSITION_ROLES.get(signal.get('author_position') or '', signal.get('role') or 'unknown')


def normalize_authorship(signal: dict) -> dict:
    role = author_role(signal)
    if role == (signal.get('role') or 'unknown'):
        return signal
    return {**signal, 'role': role, 'original_role': signal.get('role') or 'unknown'}


def work_keys(signal: dict) -> set[str]:
    """DOI, arXiv id or OpenAlex id of the work behind a signal.

    A plain page URL is not a key: a lab publication list is the evidence for many works at once.
    """
    keys = set()
    for value in filter(None, [signal.get('evidence_url'), signal.get('source_work_id')]):
        value = unquote(str(value)).casefold().strip().rstrip('/')
        arxiv = re.search(r'arxiv(?:\.org/(?:abs|pdf|html)/|[:/])(\d{4}\.\d{4,5})(?:v\d+)?', value)
        doi = re.search(r'10\.\d{4,9}/[^\s?#]+', value)
        if arxiv:
            keys.add('arxiv:' + arxiv[1])
        elif doi:
            keys.add('doi:' + doi[0])
        elif re.search(r'(?:^|/)w\d+$', value):
            keys.add('openalex:' + value.rsplit('/', 1)[-1])
    return keys


def inference_signals(signals: list[dict]) -> list[dict]:
    """One signal per distinct work for the majority rules in role inference.

    The same paper reached through two channels must not count twice. Grants, rosters and other
    non-authorship signals pass through unchanged. Positions that disagree for one work leave it unknown.
    """
    works: list[list[dict]] = []
    owner: dict[str, int] = {}
    kept = []
    for signal in signals:
        if author_role(signal) not in AUTHORSHIP:
            kept.append(signal)
            continue
        keys = work_keys(signal)
        hits = sorted({owner[k] for k in keys if k in owner})
        if not hits:
            index = len(works)
            works.append([])
        else:
            index = hits[0]
            for old in hits[1:]:  # a later key joined two groups already seen apart
                works[index].extend(works[old])
                works[old] = []
                owner.update({k: index for k, v in owner.items() if v == old})
        works[index].append(signal)
        owner.update(dict.fromkeys(keys, index))
    for group in filter(None, works):
        roles = {author_role(s) for s in group}
        kept.append({**group[0], 'role': roles.pop() if len(roles) == 1 else 'unknown'})
    return kept
