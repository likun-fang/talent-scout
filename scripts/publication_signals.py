"""Shared authorship conversion and distinct-work evidence for role inference."""
from __future__ import annotations
import copy
import re
from urllib.parse import unquote


def author_role(author: dict) -> str:
    """Use position in the original list, never the index in a filtered shortlist."""
    position = author.get('author_position') or author.get('position')
    return {'first': 'first_author', 'last': 'last_author', 'middle': 'coauthor',
            'first_author': 'first_author', 'last_author': 'last_author',
            'coauthor': 'coauthor'}.get(position, 'unknown')


def publication_signal(author: dict, publication: dict, **fields) -> dict:
    return {**fields, 'kind': 'person', 'name_raw': author['name'],
            'ids': copy.deepcopy(author.get('ids', {})), 'role': author_role(author),
            'author_position': author.get('author_position') or author.get('position', ''),
            'publication': copy.deepcopy(publication)}


def normalize_authorship(signal):
    if author_role(signal) == 'unknown':
        return signal
    # Keep the raw observation when a legacy adapter discarded original position.
    return {**signal, 'original_role': signal.get('original_role', signal.get('role', 'unknown')),
            'role': author_role(signal)}


def work_keys(signal: dict) -> set[str]:
    pub = signal.get('publication') or {}
    values = [pub.get('doi'), pub.get('url'), signal.get('evidence_url'), signal.get('source_work_id')]
    keys = set()
    for value in filter(None, values):
        value = unquote(str(value)).lower().strip().rstrip('/')
        arxiv = re.search(r'(?:arxiv[.:/]|arxiv\.org/(?:abs|pdf|html)/)(\d{4}\.\d{4,5})(?:v\d+)?', value)
        doi = re.search(r'10\.\d{4,9}/[^\s?#]+', value)
        if arxiv:
            keys.add('arxiv:' + arxiv[1])
        elif doi:
            keys.add('doi:' + doi[0])
        elif re.search(r'(?:openalex.org/)?w\d+$', value):
            keys.add('openalex:' + value.rsplit('/', 1)[-1])
        elif value.startswith(('http://', 'https://')):
            keys.add('url:' + value)
    return keys


def inference_signals(signals: list[dict]) -> list[dict]:
    """Deduplicate publication observations, retain provenance outside this view.

    Explicit source author_position outranks the old generic role. Conflicting
    explicit positions remain unknown. Grants and unidentified legacy signals
    retain their existing behavior rather than being merged on a shared page.
    """
    groups, owners, other = [], {}, []
    for signal in signals:
        if not (signal.get('publication') or signal.get('source_work_id') or
                signal.get('signal_type') in {'paper_author', 'research_publication', 'model_paper',
                                            'model_paper_author', 'lab_publication'}):
            other.append(signal)
            continue
        keys = work_keys(signal)
        hits = {owners[k] for k in keys if k in owners}
        if not hits:
            index = len(groups); groups.append([])
        else:
            index = min(hits)
            for old in hits - {index}:
                groups[index].extend(groups[old]); groups[old] = []
                owners = {k: index if v == old else v for k, v in owners.items()}
        groups[index].append(signal)
        owners.update({k: index for k in keys})
    for group in filter(None, groups):
        explicit = {author_role(s) for s in group if author_role(s) != 'unknown'}
        roles = explicit or {s.get('role', 'unknown') for s in group}
        other.append({**group[0], 'role': next(iter(roles)) if len(roles) == 1 else 'unknown'})
    return other
