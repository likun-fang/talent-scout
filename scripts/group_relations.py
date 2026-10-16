"""Direct reviewed memberships, separate from publication identity and eligibility."""
from __future__ import annotations
import hashlib
import json
from collections import defaultdict


def person_ref(person):
    """Evidence changes do not change a keyed person's recovery task identity.

    Unkeyed records use their source URLs as a conservative fallback; no name-only
    merge. Identity changes require a new task, never a silent reassignment.
    """
    from identity_quality import strong_keys, name_key
    ids = sorted(strong_keys(person))
    if person.get('entity_id', '').startswith('reviewed-'):
        identity = {'entity': person['entity_id']}
    elif ids:
        identity = {'ids': ids, 'name': name_key(person.get('name'))}
    else:
        identity = {'name': name_key(person.get('name')), 'affiliation': person.get('current_affiliation', ''),
                    'sources': sorted({s.get('evidence_url', '') for s in person.get('signals', [])})}
    return 'member-' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]


def assignments(persons, relations, as_of=None):
    """Map validated, current direct relationships to existing display fields.

    Reviewed relations enter only through the recovery ledger loader. They do
    not add people, change roles/countries, or qualify a paper/topic.
    """
    indexed = defaultdict(list)
    groups = {}
    for relation in relations:
        group = relation['group']
        if group['id'] in groups and groups[group['id']] != group:
            raise ValueError('conflicting definitions for one reviewed group')
        groups[group['id']] = group
        indexed[relation['person_ref']].append(relation)
    labels = defaultdict(set)
    for group in groups.values():
        labels[group['name'] + ' @ ' + group['institution']].add(group['id'])
    output = {}
    for person in persons:
        ref = person_ref(person)
        available = indexed.get(ref, [])
        if not available:
            continue
        current = [r for r in available if r['status'] == 'current' and
                   (not as_of or (r['observed_on'] <= as_of and
                    (not r.get('valid_from') or r['valid_from'] <= as_of) and
                    (not r.get('valid_to') or r['valid_to'] >= as_of)))]
        if not current:
            output[ref] = {'group': '', 'group_link': '', 'group_rule': 'reviewed',
                           'group_evidence': 'Reviewed relationship is historical or outside the run date',
                           'group_memberships': available}
            continue
        primary = [r for r in current if r.get('primary')]
        choices = primary or current
        ids = {r['group']['id'] for r in choices}
        if len(ids) != 1:
            output[ref] = {'group': '', 'group_link': '', 'group_rule': 'reviewed',
                           'group_evidence': 'Multiple verified memberships; primary group not established',
                           'group_memberships': available}
            continue
        chosen = choices[0]; group = chosen['group']
        label = group['name'] + ' @ ' + group['institution']
        if len(labels[label]) > 1:
            suffix = hashlib.sha256(group['id'].encode()).hexdigest()[:8]
            label = group['name'] + ' [' + suffix + '] @ ' + group['institution']
        output[ref] = {'group': label, 'group_id': group['id'], 'group_definition': group,
                       'group_rule': 'reviewed', 'group_link': 'team', 'group_memberships': available,
                       'group_evidence': f"Reviewed {chosen['relation_type']} | {chosen['evidence'][0]['url']}"}
        if group.get('leader'):
            leader = group['leader']
            output[ref]['group_leader_reference'] = {'name': leader['name'], 'url': leader['url'],
                'last_verified': chosen['observed_on'], 'status': 'reviewed_team_reference'}
    return output
