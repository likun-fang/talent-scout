"""Conservative post-enrichment identity gate shared by both final exporters.

Strong-ID collisions are resolved before counting people. Conflicts are held with
their original records, never resolved by last-write-wins or a name-only merge.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

PROVIDERS = ('orcid', 'openalex', 'dblp', 'openreview', 'github', 'gepris', 'snsf')
HOSTS = {'orcid': {'orcid.org'}, 'openalex': {'openalex.org'}, 'dblp': {'dblp.org', 'dblp.uni-trier.de'},
         'github': {'github.com'}, 'openreview': {'openreview.net'}}


def normalize_id(provider, value):
    value = str(value or '').strip().rstrip('/')
    if not value:
        return ''
    if '://' in value:
        parsed = urlsplit(value)
        if provider in HOSTS and (parsed.hostname or '').lower().removeprefix('www.') not in HOSTS[provider]:
            return ''
        value = parsed.path.strip('/')
        if provider == 'dblp':
            value = value.removeprefix('pid/').removesuffix('.html')
        elif provider == 'openreview':
            from urllib.parse import parse_qs
            value = parse_qs(parsed.query).get('id', [value])[0]
    if provider in {'orcid', 'openalex'}:
        return value.upper()
    return value.lower() if provider in {'github', 'gepris', 'snsf'} else value


def id_values(records, include_signals=True, reviews=()):
    values = defaultdict(set)
    for record in records:
        sources = [record.get('ids') or {}]
        if include_signals:
            for signal in record.get('signals', []):
                sources += [signal.get('ids') or {}, (signal.get('publication') or {}).get('author_ids') or {}]
        for ids in sources:
            for provider in PROVIDERS:
                value = reviewed_id(provider, ids.get(provider), reviews)
                if value:
                    values[provider].add(value)
    return dict(values)


def conflicts(records, include_signals=True, reviews=()):
    result = {k: sorted(v) for k, v in id_values(records, include_signals, reviews).items() if len(v) > 1}
    bindings = [review_for(r, reviews) for r in records] if reviews else []
    if bindings and all(b and name_key(r.get('name') or r.get('name_raw')) in map(name_key, b['names'])
                        for r, b in zip(records, bindings)) and len({b['entity_id'] for b in bindings}) == 1:
        # Other providers' IDs remain unverified source annotations, not identity
        # aliases. They cannot veto a separately reviewed binding or become keys.
        result = {k: v for k, v in result.items() if k in bindings[0]['canonical_ids']}
    return result


def strong_keys(record):
    return {(k, normalize_id(k, v)) for k, v in (record.get('ids') or {}).items()
            if k in PROVIDERS and normalize_id(k, v)}


def name_key(name):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', name or '').casefold()
                           if not unicodedata.combining(c)).split())


def accepted_ids(review):
    values = {k: {normalize_id(k, v)} for k, v in review['canonical_ids'].items()}
    for k, aliases in review.get('id_aliases', {}).items():
        values[k].update(normalize_id(k, v) for v in aliases)
    return values


def validate_identity_reviews(reviews):
    """Reviewed identity bindings, not inferred name matches. Fail closed on bad ledgers."""
    owners, entity_ids = {}, set()
    for review in reviews:
        entity = review.get('entity_id')
        if not isinstance(entity, str) or not entity.strip() or entity in entity_ids:
            raise ValueError('identity reviews require unique nonempty entity_id')
        entity_ids.add(entity)
        if not isinstance(review.get('names'), list) or not review['names'] or not all(isinstance(n, str) and n.strip() for n in review['names']):
            raise ValueError('identity review requires explicit names')
        canonical = review.get('canonical_ids')
        if not isinstance(canonical, dict) or not canonical or any(
                k not in PROVIDERS or not isinstance(v, str) or not normalize_id(k, v) for k, v in canonical.items()):
            raise ValueError('identity review requires canonical provider IDs')
        for k, values in review.get('id_aliases', {}).items():
            if k not in canonical or not isinstance(values, list) or any(
                    not isinstance(v, str) or not normalize_id(k, v) for v in values):
                raise ValueError('identity aliases require a canonical ID for their provider')
        if not isinstance(review.get('evidence'), list) or not review['evidence']:
            raise ValueError('identity review requires quoted, dated evidence')
        for evidence in review['evidence']:
            parsed = urlsplit(evidence.get('url', ''))
            if parsed.scheme not in {'http', 'https'} or not parsed.netloc or not evidence.get('quote', '').strip():
                raise ValueError('identity evidence requires a URL and quote')
            datetime.date.fromisoformat(evidence.get('reviewed_on', ''))
        for decision in review.get('signal_reviews', []):
            if (decision.get('decision') not in {'accept', 'reject'} or not decision.get('evidence_url')
                    or not decision.get('reason') or not decision.get('evidence_refs')
                    or any(type(i) is not int or i < 0 or i >= len(review['evidence']) for i in decision['evidence_refs'])):
                raise ValueError('signal review requires decision, source URL, reason and evidence references')
        urls = [s['evidence_url'] for s in review.get('signal_reviews', [])]
        if len(urls) != len(set(urls)):
            raise ValueError('contradictory or duplicate signal reviews')
        for k, values in accepted_ids(review).items():
            for value in values:
                key = (k, value)
                if key in owners:
                    raise ValueError('a reviewed provider ID belongs to more than one entity')
                owners[key] = entity
    return reviews


def load_identity_reviews():
    path = Path(__file__).resolve().parents[1] / 'assets/identity-reviews.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('entities'), list):
        raise ValueError('invalid identity review registry')
    return validate_identity_reviews(data['entities'])


def reviewed_id(provider, value, reviews):
    value = normalize_id(provider, value)
    for review in reviews:
        if value and value in accepted_ids(review).get(provider, set()):
            return normalize_id(provider, review['canonical_ids'][provider])
    return value


def review_for(record, reviews):
    # Canonical record IDs take precedence over a possibly misattributed source ID.
    for keys in [strong_keys(record), {(k, v) for k, vs in id_values([record]).items() for v in vs}]:
        matches = [r for r in reviews if keys & {(k, v) for k, vs in accepted_ids(r).items() for v in vs}]
        if matches:
            return matches[0] if len(matches) == 1 else None
    return None


def reviewed_keys(record, reviews):
    keys = {(k, reviewed_id(k, v, reviews)) for k, v in strong_keys(record)}
    review = review_for(record, reviews)
    if review and name_key(record.get('name') or record.get('name_raw')) in map(name_key, review['names']):
        keys.add(('reviewed_entity', review['entity_id']))
    return keys


def partition_reviewed_signals(person, review):
    """An identity review does not automatically verify all of a person's publications."""
    allowed = accepted_ids(review)
    decisions = {s['evidence_url']: s for s in review.get('signal_reviews', [])}
    kept, held, corrections = [], [], []
    for signal in person.get('signals', []):
        decision = decisions.get(signal.get('evidence_url'))
        values = id_values([{'signals': [signal]}])
        mismatches = {k: sorted(v - allowed[k]) for k, v in values.items() if k in allowed and v - allowed[k]}
        linked = any(v & allowed.get(k, set()) for k, v in values.items())
        own_names = [n for n in [signal.get('name_raw'), (signal.get('publication') or {}).get('author_name')] if n]
        name_matches = all(name_key(n) in map(name_key, review['names']) for n in (own_names or [person.get('name')]))
        if mismatches and name_matches and decision and decision['decision'] == 'accept':
            # Explicit per-source authorship review can reject a provider binding
            # while retaining the publication. Never infer this from a profile alone.
            original = copy.deepcopy(signal)
            signal = copy.deepcopy(signal)
            for ids in [signal.get('ids', {}), (signal.get('publication') or {}).get('author_ids', {})]:
                for provider in mismatches:
                    if provider in ids:
                        ids[provider] = normalize_id(provider, review['canonical_ids'][provider])
            correction = {'signal': original, 'reason': 'reviewed_source_provider_binding_corrected',
                          'conflicts': mismatches, 'decision': decision}
            corrections.append(correction)
            signal['identity_binding_review'] = {'entity_id': review['entity_id'], 'decision': copy.deepcopy(decision)}
            if signal.get('publication'):
                signal['publication']['authorship_evidence_url'] = review['evidence'][decision['evidence_refs'][0]]['url']
            mismatches = {}
            linked = True
        reason = ('source_rejected_by_identity_review' if decision and decision['decision'] == 'reject'
                  else 'source_identity_name_mismatch' if not name_matches
                  else 'unreviewed_provider_binding' if mismatches
                  else 'source_identity_unbound' if not linked and not (decision and decision['decision'] == 'accept')
                  else '')
        if reason:
            held.append({'signal': copy.deepcopy(signal), 'reason': reason, 'conflicts': mismatches,
                         'decision': decision})
        else:
            kept.append(signal)
    return kept, held, corrections


def record_key(record):
    """Fallback keys distinguish namesakes; no bare-name navigation keys."""
    payload = {k: record.get(k) for k in ('name', 'ids', 'current_affiliation', 'country', 'signals')}
    return 'person-' + hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def unique_records(records):
    seen, output = set(), []
    for record in records:
        key = json.dumps(record, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            output.append(copy.deepcopy(record))
    return output


def compatible_names(records):
    def words(value):
        value = unicodedata.normalize('NFKD', value or '').casefold()
        return ''.join(c for c in value if not unicodedata.combining(c)).replace('.', '').replace('-', ' ').split()
    names = [words(p.get('name')) for p in records if p.get('name')]
    return all(a == b or len(a) > 1 and len(b) > 1 and a[-1] == b[-1] and a[0][0] == b[0][0]
               for a in names for b in names)


def load_source_reviews():
    path = Path(__file__).resolve().parents[1] / 'assets/source-reviews.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    for item in data['holds']:
        if not item.get('doi') or not item.get('reason') or not item.get('evidence_urls'):
            raise ValueError('source hold requires DOI, reason and evidence URLs')
    return data['holds']


def doi_key(value):
    value = str(value or '').strip().lower()
    for prefix in ('https://doi.org/', 'http://doi.org/', 'http://dx.doi.org/', 'https://dx.doi.org/', 'doi:'):
        value = value.removeprefix(prefix)
    return value.rstrip('/')


def resolve_persons(persons, source_reviews=None, identity_reviews=None):
    """Return safe person copies and a lossless audit of merges/holds.

    All strong keys form connected components BEFORE checking contradictions.
    An ID-less bridge cannot silently join two incompatible identities.
    No affiliation or name-only match is made at this final gate.
    """
    reviews = load_source_reviews() if source_reviews is None else source_reviews
    identities = load_identity_reviews() if identity_reviews is None else validate_identity_reviews(identity_reviews)
    blocked = {doi_key(r['doi']): r for r in reviews}
    prepared, audit = [], []
    for original in persons:
        p = copy.deepcopy(original)
        p.pop('identity_review', None)  # Only the current validated registry grants review authority.
        held_signals = []
        signals = []
        for signal in p.get('signals', []):
            pub = signal.get('publication') or {}
            hold = next((blocked[doi_key(v)] for v in [signal.get('evidence_url'), pub.get('url'), pub.get('doi')]
                         if doi_key(v) in blocked), None)
            if hold:
                held_signals.append({'signal': signal, 'review': hold})
            else:
                signals.append(signal)
        if held_signals:
            audit.append({'check': 'identity', 'reason': 'source_under_review', 'name': p.get('name'),
                          'record_key': record_key(original), 'held_signals': held_signals})
            p['signals'] = signals
            p['identity_sources_changed'] = True
            if not signals:
                audit.append({'check': 'identity', 'reason': 'no_safe_source', 'status': 'held', 'records': [original]})
                continue
        identity_review = review_for(p, identities)
        if identity_review and name_key(p.get('name')) not in map(name_key, identity_review['names']):
            audit.append({'check': 'identity', 'reason': 'reviewed_identity_name_conflict',
                          'status': 'held', 'records': [original]})
            continue
        # Explicit pending/held/deceased decisions are never overridden by an ID match.
        if p.get('identity_status') in {'pending', 'held', 'deceased'} or (
                p.get('identity_status') == 'conflict' and not identity_review):
            audit.append({'check': 'identity', 'reason': 'unresolved_identity_status', 'status': 'held', 'records': [original]})
            continue
        if identity_review:
            signals, held, corrections = partition_reviewed_signals(p, identity_review)
            audit.append({'check': 'identity', 'reason': 'identity_review_applied', 'status': 'reviewed',
                          'review': copy.deepcopy(identity_review), 'records': [original]})
            if corrections:
                audit.append({'check': 'identity', 'reason': 'source_provider_bindings_corrected', 'status': 'reviewed',
                              'name': p['name'], 'review_id': identity_review['entity_id'], 'corrections': corrections})
                p['identity_sources_changed'] = True
            if held:
                audit.append({'check': 'identity', 'reason': 'identity_sources_quarantined', 'status': 'partial',
                              'name': p['name'], 'review_id': identity_review['entity_id'],
                              'held_signals': held, 'records': [original]})
                p['identity_held_sources'] = unique_records(p.get('identity_held_sources', []) + held)
                p['identity_sources_changed'] = True
            p['signals'] = signals
            # Review bindings apply to identity, not to role, geography or topic eligibility.
            p['identity_original_ids'] = unique_records(p.get('identity_original_ids', [original.get('ids', {})]))
            p['ids'] = {k: normalize_id(k, v) for k, v in identity_review['canonical_ids'].items()}
            allowed_ids = accepted_ids(identity_review)
            changed_provider = any(normalize_id(k, original.get('ids', {}).get(k)) and
                                   normalize_id(k, original['ids'][k]) not in allowed_ids.get(k, set())
                                   for k in ('orcid', 'openalex'))
            profile_bound = original.get('final_pass_url') in {e['url'] for e in identity_review['evidence']}
            source = original.get('affiliation_source', '')
            profile_bound = profile_bound or any(source.startswith(prefix) and
                normalize_id(provider, original.get('ids', {}).get(provider)) in allowed_ids.get(provider, set())
                for provider, prefix in [('orcid', 'orcid employment'), ('openalex', 'openalex last_known')])
            if changed_provider and not profile_bound:
                # A corrected identity must not inherit another provider profile's job/location.
                p['identity_reenrichment_required'] = True
                for field in ('first_pub_year', 'current_affiliation', 'country', 'affiliation_source',
                              'institution_type', 'institution_name', 'institution_id', 'homepage',
                              'final_pass_title', 'final_pass_affiliation', 'final_pass_country',
                              'final_pass_url', 'last_verified', 'linkedin_headline', 'linkedin_url'):
                    p.pop(field, None)
                p.update(role_class='unknown', role_confidence='low', role_evidence='Identity binding corrected; profile enrichment required')
                audit.append({'check': 'identity', 'reason': 'identity_reenrichment_required', 'status': 'pending',
                              'name': p['name'], 'records': [original]})
            old_oa = normalize_id('openalex', original.get('ids', {}).get('openalex'))
            if old_oa and old_oa not in accepted_ids(identity_review).get('openalex', set()):
                p.pop('first_pub_year', None)
            p['name_aliases'] = sorted(set(p.get('name_aliases', []) + identity_review['names'] + [p['name']]))
            p['name'] = identity_review['names'][0]
            p['identity_status'] = 'reviewed_with_held_sources' if p.get('identity_held_sources') else 'reviewed'
            unreviewed = {k: sorted(v) for k, v in id_values([{'signals': signals}]).items()
                          if k not in identity_review['canonical_ids']}
            if unreviewed:
                audit.append({'check': 'identity', 'reason': 'unreviewed_provider_annotations', 'status': 'needs_review',
                              'name': p['name'], 'provider_ids': unreviewed, 'review_id': identity_review['entity_id']})
                if p['identity_status'] == 'reviewed':
                    p['identity_status'] = 'reviewed_with_pending_ids'
            p['merge_confidence'] = 'high'
            p['identity_review'] = copy.deepcopy(identity_review)
            p.pop('identity_conflicts', None)
            # No cached derived topics/qualifying papers may survive source quarantine.
            for field in ('qualifying', 'topic_signals', 'topic_papers', 'display_topics', 'active_topic_ids'):
                p.pop(field, None)
            from person_fields import topics_for
            p['topics'] = topics_for(signals)
        if p.get('identity_sources_changed'):
            from person_fields import topics_for
            p['topics'] = topics_for(p['signals'])
            for field in ('qualifying', 'topic_signals', 'topic_papers', 'display_topics', 'active_topic_ids'):
                p.pop(field, None)
        prepared.append(p)
    parent = list(range(len(prepared)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, p in enumerate(prepared):
        for key in reviewed_keys(p, identities) | {('exact_record', record_key(p))}:
            if key in seen:
                parent[find(i)] = find(seen[key])
            else:
                seen[key] = i
    components = defaultdict(list)
    for i, p in enumerate(prepared):
        components[find(i)].append(p)
    output = []
    for records in components.values():
        incompatible = conflicts(records, reviews=identities)
        if incompatible:
            audit.append({'check': 'identity', 'reason': 'conflicting_provider_ids', 'status': 'held',
                          'conflicts': incompatible, 'records': records})
            continue
        if not compatible_names(records):
            audit.append({'check': 'identity', 'reason': 'strong_id_name_conflict', 'status': 'held', 'records': records})
            continue
        # Duplicate enrichments must not silently choose a current employer.
        from person_fields import affiliation_for, same_institution
        verified = [p for p in records if p.get('final_pass_url') and p.get('last_verified')]
        candidates = verified or records
        if len(candidates) > 1 and any(affiliation_for(a) and affiliation_for(b) and not same_institution(a, b)
                                       for a in candidates for b in candidates):
            audit.append({'check': 'identity', 'reason': 'current_affiliation_conflict', 'status': 'held', 'records': records})
            continue
        chosen = max(candidates, key=lambda p: (p.get('last_verified') or '', len(p.get('signals', []))))
        p = copy.deepcopy(chosen)
        if len(records) > 1:
            p['signals'] = unique_records([s for r in records for s in r.get('signals', [])])
            p['ids'] = {**p.get('ids', {}), **{k: next(iter(v)) for k, v in id_values(records, include_signals=False, reviews=identities).items()}}
            for field in ('identity_held_sources', 'identity_original_ids'):
                values = [v for r in records for v in r.get(field, [])]
                if values:
                    p[field] = unique_records(values)
            if p.get('identity_held_sources') and p.get('identity_review'):
                p['identity_status'] = 'reviewed_with_held_sources'
            elif any(r.get('identity_status') == 'reviewed_with_pending_ids' for r in records):
                p['identity_status'] = 'reviewed_with_pending_ids'
            p['identity_records'] = unique_records([{'name': r.get('name'), 'ids': r.get('ids', {}),
                'affiliation': affiliation_for(r), 'country': r.get('country'), 'group': r.get('group'),
                'group_link': r.get('group_link'), 'group_evidence': r.get('group_evidence'),
                'notes': r.get('notes', '')} for r in records])
            p['notes'] = '; '.join(dict.fromkeys(r.get('notes', '') for r in records if r.get('notes')))
            audit.append({'check': 'identity', 'reason': 'duplicate_identity_merged', 'status': 'merged',
                          'name': p.get('name'), 'input_records': len(records), 'records': records})
        # Do not reset existing reviewed/ambiguous status just because an ID exists.
        p['entity_id'] = p['identity_review']['entity_id'] if p.get('identity_review') else record_key(p)
        p.setdefault('identity_status', 'provider_only' if strong_keys(p) else 'unkeyed')
        output.append(p)
    names = defaultdict(list)
    for p in output:
        key = ''.join(c for c in unicodedata.normalize('NFKD', p.get('name', '')).casefold()
                      if not unicodedata.combining(c))
        names[' '.join(key.split())].append(p)
    for name, records in names.items():
        if name and len(records) > 1 and any(not p.get('identity_review') for p in records):
            audit.append({'check': 'identity', 'reason': 'same_name_requires_review', 'status': 'needs_review',
                          'name': records[0]['name'], 'records': copy.deepcopy(records)})
            for p in records:
                # Distinguish confirmed namesakes from unresolved records with one provider key.
                if p.get('identity_review'):
                    continue
                p['identity_status'] = 'needs_review'
                note = 'Same-name records remain separate; identity or career-history evidence is required before merging.'
                if note not in (p.get('notes') or ''):
                    p['notes'] = '; '.join(filter(None, [p.get('notes'), note]))
    return output, audit


def assert_unique_identities(persons):
    seen = {}
    for index, p in enumerate(persons):
        for key in strong_keys(p) | {('entity', p.get('entity_id') or record_key(p))}:
            if key in seen:
                raise ValueError(f'duplicate identity {key[0]} at records {seen[key]} and {index}')
            seen[key] = index


def reference_leaders(audit, selected_pool):
    """Keep independently reviewed profile anchors, never disputed paper/team evidence.

    These are reference nodes for grouping only. They cannot enter the roster,
    qualify a topic, or supply paper-based coauthor relationships.
    """
    from current_affiliation import classify_role
    from person_fields import same_institution, normalized
    anchors = []
    for entry in audit:
        if entry.get('reason') != 'conflicting_provider_ids' or entry.get('status') != 'held':
            continue
        for person in entry.get('records', []):
            url, date = person.get('final_pass_url'), person.get('last_verified')
            affiliation, title = person.get('final_pass_affiliation'), person.get('final_pass_title')
            if not (url and date and affiliation and title):
                continue
            try:
                datetime.date.fromisoformat(date)
            except (TypeError, ValueError):
                continue
            for review in person.get('review_evidence', []):
                quote = review.get('excerpt') or review.get('quote') or ''
                if (review.get('status') != 'verified' or name_key(review.get('name')) != name_key(person['name'])
                        or (review.get('final_pass_url') or review.get('url')) != url
                        or review.get('last_verified') != date or normalized(title) not in normalized(quote)
                        or not same_institution(affiliation, review.get('final_pass_affiliation') or review.get('affiliation', ''))):
                    continue
                if any(name_key(p.get('name')) == name_key(person['name']) and same_institution(p, affiliation)
                       for p in selected_pool):
                    break
                anchor = {k: person[k] for k in ('name', 'final_pass_url', 'last_verified', 'final_pass_title',
                          'final_pass_affiliation', 'final_pass_country') if k in person}
                anchor.update(ids={}, current_affiliation=affiliation, country=person.get('final_pass_country', ''),
                              reference_only=True, identity_status='reference_only_identity_pending',
                              signals=[{'kind': 'person', 'name_raw': person['name'], 'affiliation_raw': affiliation,
                                        'country': person.get('final_pass_country', ''), 'role_title': title,
                                        'date': date, 'signal_type': 'reviewed_profile', 'channel': 'final-pass',
                                        'evidence_url': url, 'snippet': quote, 'topics': []}])
                anchor.update(classify_role(anchor, datetime.date.fromisoformat(date).year))
                if anchor['role_class'] in {'professor', 'group_leader'}:
                    anchors.append(anchor)
                break
    return unique_records(anchors)
