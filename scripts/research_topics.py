"""Run-scoped display topics and publication-backed professor eligibility.

Source signals remain verbatim. Topic relevance and authorship are sourced research
assertions; this module checks their structure, identity, dates and quoted evidence,
not the truth of a remote page. No network calls or implicit domain vocabulary.
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def normalized(value):
    return ' '.join(str(value or '').casefold().split())


def web_url(value):
    try:
        parsed = urlsplit(value if isinstance(value, str) else '')
        return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)
    except ValueError:
        return False


def validate_policy(policy):
    if not isinstance(policy, dict) or policy.get('version') != 1:
        raise ValueError('topic policy must have version 1')
    if type(policy.get('include_preprints')) is not bool:
        raise ValueError('include_preprints must be a boolean')
    topics = policy.get('topics')
    if not isinstance(topics, list) or not topics:
        raise ValueError('topics must be a nonempty list')
    ids, labels = set(), set()
    for topic in topics:
        if not isinstance(topic, dict):
            raise ValueError('each topic must be an object')
        tid, label = topic.get('id'), topic.get('label')
        if not isinstance(tid, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', tid) or tid in ids:
            raise ValueError('topic ids must be unique lowercase slugs')
        if (not isinstance(label, str) or not label.strip() or len(label) > 24 or
                len(label.split()) > 3 or ';' in label or '\n' in label or normalized(label) in labels):
            raise ValueError('topic labels must be unique, at most 24 characters / 3 words, without semicolons or newlines')
        mapped = topic.get('facet_ids', [])
        if (not isinstance(mapped, list) or any(not isinstance(f, str) or not f for f in mapped)
                or len(set(mapped)) != len(mapped)):
            raise ValueError('facet_ids must be unique strings within each topic')
        ids.add(tid)
        labels.add(normalized(label))
    return policy


def load_policy(path):
    try:
        return validate_policy(json.loads(Path(path).read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        raise SystemExit(f'cannot read topic policy {path}: {exc}')


def policy_for(args):
    """Explicit file, then sibling policy. No policy preserves historical exports."""
    explicit = getattr(args, 'topic_policy', None)
    if isinstance(explicit, dict):
        return validate_policy(explicit)
    if explicit:
        return load_policy(explicit)
    persons_path = getattr(args, 'persons', None)
    sibling = Path(persons_path).parent / 'topic-policy.json' if persons_path else None
    return load_policy(sibling) if sibling and sibling.exists() else None


def publication_interval(value):
    """A partial date represents its full interval; boundary ambiguity fails closed."""
    if not isinstance(value, str):
        return None
    try:
        if re.fullmatch(r'\d{4}', value):
            return dt.date(int(value), 1, 1), dt.date(int(value), 12, 31)
        if re.fullmatch(r'\d{4}-\d{2}', value):
            year, month = map(int, value.split('-'))
            return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            date = dt.date.fromisoformat(value)
            return date, date
    except ValueError:
        pass
    return None


def author_id(value, provider):
    """Accept canonical identifiers or their provider URLs, never another host's ID."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip().casefold().rstrip('/')
    if '://' in value:
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or parsed.netloc != {'openalex': 'openalex.org', 'orcid': 'orcid.org'}[provider]:
            return None
        value = parsed.path.lstrip('/')
    pattern = r'a[0-9]+' if provider == 'openalex' else r'[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9x]'
    return value if re.fullmatch(pattern, value) else None


def supported_topics(signal, policy, publication_only=False):
    """Require a reviewer-supplied contribution quote, never inherit parent/lab tags."""
    publication = signal.get('publication')
    publication = publication if isinstance(publication, dict) else {}
    texts = [publication.get('title', ''), publication.get('abstract', '')]
    if not publication_only:
        texts += signal.get('topics') or []
        texts += [signal.get('snippet', '')]
    known = {t['id'] for t in policy['topics']}
    supported = set()
    for item in signal.get('topic_evidence') or []:
        if not isinstance(item, dict):
            continue
        quote = normalized(item.get('quote'))
        if (item.get('topic_id') in known and item.get('relation') == 'contribution'
                and len(quote) >= 8 and any(quote in normalized(text) for text in texts)):
            supported.add(item['topic_id'])
    return supported


def publication_problem(person, signal, start, end, policy):
    pub = signal.get('publication')
    if not isinstance(pub, dict):
        return 'missing_publication_metadata'
    if pub.get('status') not in {'published', 'preprint'}:
        return 'unverified_publication_status'
    if pub['status'] == 'preprint' and not policy['include_preprints']:
        return 'preprint_excluded'
    if not pub.get('title') or not web_url(pub.get('url')) or not web_url(pub.get('authorship_evidence_url')):
        return 'missing_publication_source'
    if pub.get('authorship_verified') is not True or signal.get('kind') != 'person':
        return 'unverified_authorship'
    if person.get('merge_confidence') == 'ambiguous':
        return 'ambiguous_person_identity'
    # Match the reviewed author identity to this merged person. A conflicting strong
    # ID cannot be overridden by a matching name. Name-only evidence needs review.
    author_ids = pub.get('author_ids') or {}
    if not isinstance(author_ids, dict):
        return 'author_identity_mismatch'
    person_ids = person.get('ids') or {}
    shared = set(author_ids) & set(person_ids) & {'openalex', 'orcid'}
    from identity_quality import reviewed_id, validate_identity_reviews
    reviews = validate_identity_reviews([person['identity_review']]) if person.get('identity_review') else []
    if any(not author_id(author_ids[k], k) or not author_id(person_ids[k], k) or
           reviewed_id(k, author_ids[k], reviews) != reviewed_id(k, person_ids[k], reviews)
           for k in shared):
        return 'author_identity_mismatch'
    names = {normalized(person.get('name')), normalized(signal.get('name_raw'))} - {''}
    if not shared and normalized(pub.get('author_name')) not in names:
        return 'author_identity_mismatch'
    interval = publication_interval(pub.get('date'))
    if interval is None:
        return 'missing_or_invalid_publication_date'
    if interval[1] < start or interval[0] > end:
        return 'publication_outside_window'
    if not start <= interval[0] <= interval[1] <= end:
        return 'publication_date_boundary_uncertain'
    return None


def apply_policy(persons, policy, start, end, recent_signals):
    """Return selected annotated copies and audit records, leaving inputs untouched.

    recent_signals(person) is the existing non-professor activity-window predicate.
    Professors qualify on publication dates, independently of a signal's event date.
    """
    kept, audit = [], []
    for person in persons:
        professor = person.get('role_class') == 'professor'
        accepted, active, papers = [], set(), []
        candidates = person.get('signals', []) if professor else recent_signals(person)
        for signal in candidates:
            topics = supported_topics(signal, policy, publication_only=professor)
            reason = publication_problem(person, signal, start, end, policy) if professor else None
            if professor and (reason or not topics):
                audit.append({'name': person.get('name'), 'reason': reason or 'missing_topic_evidence',
                              'signal': signal})
                continue
            accepted.append(signal)
            active.update(topics)
            if professor:
                pub = signal['publication']
                papers.append({**pub, 'topic_ids': sorted(topics)})
        if professor and not papers:
            audit.append({'name': person.get('name'), 'reason': 'professor_pending_recent_topic_paper',
                          'status': 'pending_evidence', 'signals': person.get('signals', [])})
            continue
        if not accepted:
            continue
        if not active:
            audit.append({'name': person.get('name'), 'reason': 'unmapped_topics', 'status': 'pending_topic_review'})
        display = [t['label'] for t in policy['topics'] if t['id'] in active]
        qualifying = accepted
        if professor:
            # Eligibility does not discard otherwise-valid channels from ranking.
            accepted_ids = {id(s) for s in accepted}
            qualifying = [s for s in recent_signals(person) if id(s) not in accepted_ids]
            qualifying += [{**s, 'date': s['publication']['date']} for s in accepted]
        kept.append({**person, 'display_topics': display, 'active_topic_ids': sorted(active),
                     'topic_papers': papers, 'topic_signals': accepted,
                     'qualifying': qualifying,
                     'channels_hit': sorted({s['channel'] for s in qualifying if s.get('channel')}),
                     'hop_depth': min(s.get('hop_depth', 0) for s in qualifying)})
    return kept, audit


def topic_tags(person, policy, facets, infer_tags, facet_texts):
    """Keep auxiliary facets, but never resurrect a rejected main topic from old text."""
    scoped = {'signals': person['topic_signals']}
    inferred = infer_tags(*facet_texts(scoped), facets)
    mapped = {fid for t in policy['topics'] for fid in t.get('facet_ids', [])}
    active = set(person['active_topic_ids'])
    available = {t['id'] for f in facets for t in f['tags']}
    explicit = [fid for t in policy['topics'] if t['id'] in active for fid in t.get('facet_ids', [])
                if fid in available]
    return list(dict.fromkeys([tag for tag in inferred if tag not in mapped] + explicit))
