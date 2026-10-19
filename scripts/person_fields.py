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


def facet_texts(person: dict) -> tuple[list[str], list[str]]:
    """The verbatim phrases a person's record carries: (person and signal topics, signal snippets and
    project / paper parents)."""
    topics = list(person.get('topics', []))
    texts = []
    for signal in person.get('signals', []):
        topics += signal.get('topics') or []
        texts += [signal.get(key) or '' for key in ('snippet', 'parent')]
    return [t for t in topics if t], [t for t in texts if t]


def _keyword_text(value: str) -> str:
    return ' '.join(normalized(value).replace('-', ' ').replace('_', ' ').split())


def _tag_pattern(keywords: list[str]) -> 're.Pattern':
    words = sorted({_keyword_text(k) for k in keywords if k}, key=len, reverse=True)
    alternatives = '|'.join(re.escape(w).replace(r'\ ', r'\s+') for w in words)
    return re.compile(rf'(?<![a-z0-9])(?:{alternatives})(?![a-z0-9])')


def tags_for(topics: list[str], texts: list[str], facets: list[dict]) -> list[str]:
    """Tag ids with enough evidence: a keyword in one of the topics, or two distinct keywords across the
    snippets and parents (one word in a snippet is often incidental: "robust", "bias"). Keywords match as whole
    words; hyphens and underscores count as spaces, so "vision-language", "vision language" and
    "Vision_Language" are one keyword. Order follows the facets file."""
    # The separator keeps a multi-word keyword from spanning two phrases.
    topic_text = ' | '.join(_keyword_text(t) for t in topics)
    other_text = ' | '.join(_keyword_text(t) for t in texts)
    found = []
    for facet in facets:
        for tag in facet.get('tags', []):
            if not tag.get('keywords'):
                continue
            pattern = _tag_pattern(tag['keywords'])
            if pattern.search(topic_text) or len({' '.join(m.split()) for m in pattern.findall(other_text)}) >= 2:
                found.append(tag['id'])
    return found


# Employer words. "univ\w*" covers Univ., Universidad, Università, Universitet; Unibertsitatea is the Basque form.
ACADEMIC_EMPLOYER = r'\b(?:hospital|klinik|clinic|univ\w*|unibertsitate\w*|institute of technology|hochschule|school|college)\b'
RESEARCH_GMBH = r'\b(?:dfki|forschungszentrum|forschungsgesellschaft|fraunhofer|helmholtz|max.planck|leibniz)\b'
ACADEMIC_WORDS = '|'.join([ACADEMIC_EMPLOYER, RESEARCH_GMBH,
                           r'\b(?:institut\w*|cent(?:er|re)s?|laborator\w*|klinik\w*|mpi|inria|cnrs|supercomputing|academ\w*|polytech\w*|eth|epfl|charit[eé])\b'])


def affiliation_for(person: dict) -> str:
    if person.get('final_pass_affiliation'):
        return person['final_pass_affiliation']
    if person.get('current_affiliation'):
        return person['current_affiliation']
    if person.get('affiliation_raw'):
        return person['affiliation_raw']
    signals = sorted(person.get('signals', []), key=lambda s: s.get('date') or '', reverse=True)
    return next((s['affiliation_raw'] for s in signals if s.get('affiliation_raw')), '')


def group_affiliation(person: dict) -> tuple[str, list[str]]:
    """The institution a group is named after, and the other organisations its leader is at. When the affiliation
    lists an academic institution next to another organisation ("valeo.ai; Sorbonne Univ."), the group sits at the
    academic one. So it does when the affiliation is an ORCID employment at a company (a spin-off) and a record dated
    since that employment began places the leader at a university; a company the final pass read is a move and stays."""
    affiliation = affiliation_for(person)
    items = [item.strip() for item in re.split(r';|\s/\s', affiliation) if item.strip()]
    academic = [item for item in items if re.search(ACADEMIC_WORDS, item, re.I)]
    if academic and len(academic) < len(items):
        return '; '.join(academic), [item for item in items if item not in academic]
    since = re.match(r'orcid employment since (\d{4})', person.get('affiliation_source') or '')
    if items and not academic and since and not person.get('final_pass_affiliation'):
        records = sorted((s for s in person.get('signals', []) if (s.get('date') or '')[:4] >= since.group(1)
                          and re.search(ACADEMIC_WORDS, s.get('affiliation_raw') or '', re.I)),
                         key=lambda s: s['date'], reverse=True)
        if records:
            place = next(item.strip() for item in re.split(r';|\s/\s', records[0]['affiliation_raw'])
                         if re.search(ACADEMIC_WORDS, item, re.I))
            return place, [affiliation]
    return affiliation, []


def group_name(leader: dict) -> str:
    return f"{leader['name']} @ {group_affiliation(leader)[0]}"


def normalized(value: str) -> str:
    value = unicodedata.normalize('NFKD', value or '').casefold()
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).split())


def institution_name(value: str) -> str:
    """Comparison key: the words that stay once "University of" and its translations are gone, so that
    "Utrecht University", "Universiteit Utrecht" and "University of Utrecht" compare equal."""
    value = normalized(value.split('||', 1)[0])
    value = re.sub(r'\b(?:the|university|universit(?:a|at|e|eit|ad|ade)|degli studi|of|di|de|van)\b', ' ', value)
    return ' '.join(value.split())


@lru_cache(maxsize=1)
def institution_aliases() -> dict[str, str]:
    # JSON is a YAML subset, so the small registry needs no YAML dependency.
    path = Path(__file__).resolve().parents[1] / 'assets/institution-aliases.yaml'
    aliases = json.loads(path.read_text(encoding='utf-8'))
    return {institution_name(alias): institution_name(canonical)
            for canonical, variants in aliases.items() for alias in [canonical, *variants]}


@lru_cache(maxsize=1)
def institution_alias_spellings() -> set[str]:
    path = Path(__file__).resolve().parents[1] / 'assets/institution-aliases.yaml'
    registry = json.loads(path.read_text(encoding='utf-8'))
    return {normalized(alias) for canonical, variants in registry.items() for alias in [canonical, *variants]}


INSTITUTION_WORDS = (r'universit|hochschule|institut|school|college|cent(?:er|re)|laborator|polytech|academ|akademie|'
                     r'\beth\b|\bepfl\b|\bmpi\b|max.planck|inria|gmbh|\bag\b|\binc\b|\bltd\b|\blabs?\b|research|'
                     r'hospital|klinik|clinic|charit|foundation|stiftung')
# National umbrella bodies (comparison key -> the word their institutes carry). Two units that both belong to one
# are not one institution; an affiliation naming only the body is compatible with any of its institutes.
UMBRELLA = {'cnrs': 'cnrs', 'centre national recherche scientifique': 'cnrs', 'inserm': 'inserm', 'cea': 'cea',
            'fraunhofer': 'fraunhofer', 'fraunhofer gesellschaft': 'fraunhofer', 'helmholtz': 'helmholtz',
            'helmholtz association': 'helmholtz', 'leibniz association': 'leibniz', 'max planck society': 'max planck',
            'max planck gesellschaft': 'max planck'}


def institution_names(value: str) -> tuple[set[str], set[str]]:
    """(institutions, umbrella words) a printed affiliation names, folded through the alias registry: the items
    of a list ("A; B", "A / B") and, for "Unit, Institution" or "Institution, City", the comma segment that reads
    as an institution (a city, country or unit name does not count)."""
    aliases = institution_aliases()
    names, umbrellas = set(), set()
    for part in re.split(r';|\s/\s', (value or '').split('||', 1)[0]):
        candidates = [part]
        if ',' in part:
            # "Chair of Robotics, KIT, Karlsruhe": a short alias such as KIT has no institution word of its own.
            candidates += [segment for segment in part.split(',') if re.search(INSTITUTION_WORDS, normalized(segment))
                           or normalized(segment) in institution_alias_spellings()]
        for candidate in candidates:
            name = institution_name(candidate)
            if name in UMBRELLA:
                umbrellas.add(UMBRELLA[name])
            elif name:
                names.add(aliases.get(name, name))
    return names, umbrellas


def same_institution_name(left: str, right: str) -> bool:
    (a, ua), (b, ub) = institution_names(left), institution_names(right)
    if a & b:
        return True
    return any(word in name for word in ua for name in b) or any(word in name for word in ub for name in a)


def institution_ids(record: dict) -> set[str]:
    ids = record.get('ids') or {}
    institution = record.get('institution') or {}
    # Provider ids describe the provider's institution: after a final-pass move they no longer place the person.
    final = record.get('final_pass_affiliation')
    if final and not same_institution_name(final, record.get('institution_name', '')):
        return set()
    values = [('openalex', record.get('institution_id') or ids.get('openalex_institution') or institution.get('id')),
              ('ror', record.get('ror') or ids.get('ror') or institution.get('ror'))]
    return {f"{kind}:{value.rstrip('/').rsplit('/', 1)[-1].casefold()}" for kind, value in values if value}


def same_institution(left: str | dict, right: str | dict) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        if institution_ids(left) & institution_ids(right):
            return True
    left = affiliation_for(left) if isinstance(left, dict) else left
    right = affiliation_for(right) if isinstance(right, dict) else right
    return same_institution_name(left, right)


AUTHORSHIP = {'first_author', 'coauthor', 'last_author'}
# How a member is linked to its leader, strongest first. team: listed on the leader's team, company or school page;
# project: works on a grant or project the leader holds; coauthor: shares only a paper or another output.
LINKS = ('team', 'project', 'coauthor')
TEAM_SIGNALS = {'lab_member', 'team_member', 'company_team', 'company_member', 'graduiertenkolleg_member', 'imprs_member'}
COAUTHOR_SIGNALS = {'pi_coauthor_publication', 'lab_publication'}


def link_kind(signal: dict, key: str, project_parents: set[str]) -> str:
    kind = signal.get('signal_type', '')
    if kind in TEAM_SIGNALS:
        return 'team'
    if kind in COAUTHOR_SIGNALS:
        return 'coauthor'
    if kind == 'grant_publication' or key in project_parents or (signal.get('channel') or '').startswith('funding'):
        return 'project'
    return 'coauthor'


def strongest(kinds) -> str:
    kinds = set(kinds)
    return next((kind for kind in LINKS if kind in kinds), '')


def project_parents(leader: dict) -> set[str]:
    return {parent_name(s['parent']) for s in leader.get('signals', []) if s.get('role') == 'pi' and s.get('parent')}


def related(member: dict, leader: dict) -> str:
    """The strongest link kind through a shared parent or paper at matching signal institutions, or ''."""
    kinds = []
    for a in member.get('signals', []):
        for b in leader.get('signals', []):
            if not same_institution(a, b):
                continue
            if (leader.get('role_class') in {'professor', 'group_leader'}
                    and a.get('parent') and a.get('parent') == b.get('parent')):
                kinds.append('project' if b.get('role') == 'pi' else link_kind(a, parent_name(a['parent']), set()))
            if (b.get('role') == 'last_author' and a.get('role') in {'first_author', 'coauthor'}
                    and a.get('evidence_url') and a.get('evidence_url') == b.get('evidence_url')):
                kinds.append('coauthor')
    return strongest(kinds)


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


def name_variant(key: str, names: set[str]) -> bool:
    """A person-name parent spelled differently from the leader's name: same surname (last token) and the same
    first initial ("George Drettakis" for "Georges Drettakis", "G. Drettakis")."""
    tokens = key.split()
    if not 2 <= len(tokens) <= 4:
        return False
    for name in names:
        other = name.split()
        if len(other) >= 2 and other[-1] == tokens[-1] and other[0][0] == tokens[0][0]:
            return True
    return False


def rule_one(member: dict, leader: dict, lab_parents: set[str]) -> tuple[str, str, str]:
    """(evidence, rejection, link kind) for the strongest parent link from member to leader."""
    names = [leader.get('name', ''), leader.get('name_raw', '')]
    names += [s.get('name_raw', '') for s in leader.get('signals', [])]
    person_names = {parent_name(v) for v in names if v}
    direct = {parent_name(v) for v in homepages(leader)} | person_names
    # A leader's own authorship on a grant's or another PI's paper does not make that parent the leader's team:
    # the grant parent belongs to its PI (role pi), a team-page parent to the person listed on it.
    shared = {parent_name(s['parent']) for s in leader.get('signals', [])
              if s.get('parent') and s.get('role') not in AUTHORSHIP}
    # The leader's institution as a parent ("UNIVERSITAT POLITÈCNICA DE VALÈNCIA" on a grant record) names the
    # employer, not the team: it links a member only through a roster signal.
    institution = {parent_name(s['affiliation_raw']) for s in leader.get('signals', []) if s.get('affiliation_raw')}
    projects = project_parents(leader)
    rejected, links = '', []
    for signal in member.get('signals', []):
        parent = signal.get('parent')
        key = parent_name(parent) if parent else ''
        anchor = leader.get('role_class') in {'professor', 'group_leader'}
        exact = key in direct or anchor and (key in shared or key in institution and signal.get('signal_type') in TEAM_SIGNALS)
        # A spelling variant is only trusted where the institution confirms it.
        variant = not exact and key and name_variant(key, person_names) and same_institution(member, leader)
        if not key or not (exact or variant):
            continue
        url = signal.get('evidence_url') or evidence_url(leader)
        # An undated roster still listing someone whom the final pass found at another institution is stale.
        if (signal.get('signal_type') in TEAM_SIGNALS and not signal.get('date') and member.get('final_pass_affiliation')
                and not same_institution(member, leader)):
            rejected = f"moved since the roster: {parent} -> {leader['name']}, now {member['final_pass_affiliation']} | {url}"
            continue
        paper = signal.get('channel') in {'awards-papers', 'industry', 'competitions'} or key not in lab_parents
        if paper and not same_institution(member, leader):
            rejected = f"coauthor only, different institution: {parent} -> {leader['name']} | {url}"
            continue
        note = ' (name variant)' if variant else ''
        links.append((link_kind(signal, key, projects), f"parent {parent} -> {leader['name']}{note} | {url}"))
    if links:
        kind = strongest(kind for kind, _ in links)
        return next(evidence for k, evidence in links if k == kind), '', kind
    return '', rejected, ''


def choose(member: dict, candidates: list[tuple], rule: int) -> dict | None:
    """candidates are (leader, evidence, link kind)."""
    if not candidates:
        return None
    original = candidates
    if len(candidates) > 1:
        candidates = [candidate for candidate in candidates if same_institution(member, candidate[0])]
    if len(candidates) != 1:
        names = ', '.join(leader['name'] for leader, *_ in (candidates or original))
        return {'group': '', 'group_rule': rule,
                'group_evidence': f'rule {rule}: ambiguous: {names} | {evidence_url(member)}'}
    leader, match, kind = candidates[0]
    return {'_leader': id(leader), 'group': group_name(leader), 'group_rule': rule,
            'group_evidence': f'rule {rule}: {match}', 'group_link': kind}


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
    if not same_institution(member, leader):
        return ''  # A company or consortium site hosts pages for several employers' staff.
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
        own = {'_leader': id(person), 'group': group_name(person), 'group_rule': 4,
               'group_evidence': f"rule 4: leader self {person['name']} | {evidence_url(person)}", 'group_link': 'team'}
        match = own if (pi or person.get('role_class') == 'professor') and affiliation_for(person) else None
        if match is None:
            candidates = [(leader, rule_one(person, leader, lab_parents)) for leader in leaders if leader is not person]
            match = choose(person, [(leader, link, kind) for leader, (link, _, kind) in candidates if link], 1)
            if match is None:
                rejected = [reason for _, (_, reason, _) in candidates if reason]
                if rejected:
                    match = {'group': '', 'group_rule': 1, 'group_evidence': 'rule 1: ' + '; '.join(rejected)}
        for rule, link_for in ((2, domain_link), (3, repository_link)):
            if match is None:
                candidates = [(leader, link_for(person, leader)) for leader in leaders if leader is not person]
                match = choose(person, [(leader, link, 'team') for leader, link in candidates if link], rule)
        if match is None:
            candidates = [(leader, f"same institution and parent/paper -> {leader['name']} | {evidence_url(person)}", kind)
                          for leader in leaders if leader is not person and same_institution(person, leader)
                          for kind in [related(person, leader)] if kind]
            match = choose(person, candidates, 4)
        if match is None and affiliation_for(person) and (person.get('role_class') in {'professor', 'group_leader'} or
                any(s.get('role') == 'last_author' for s in person.get('signals', [])) and
                any(other is not person and related(other, person) for other in persons)):
            match = own
        results.append({**person, 'group_rule': None, 'group_link': '', **(match or {'group': '', 'group_evidence': 'unattached'})})
    by_id = {id(person): index for index, person in enumerate(persons)}
    incoming = {p.get('_leader') for p in results if p.get('_leader')}
    for original, result in zip(persons, results):
        if id(original) in incoming and result['group_evidence'] == 'unattached':
            result.update(_leader=id(original), group=group_name(original), group_rule=4,
                          group_evidence=f"rule 4: linked leader self {original['name']} | {evidence_url(original)}", group_link='team')
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
                updated.update(group='', group_link='', group_evidence=f"rule {result['group_rule']}: ambiguous: {names} (leader chain unresolved) | {evidence_url(persons[index])}")
            elif result['group'] != results[current]['group']:
                kinds = [results[i].get('group_link', '') for i in path[:-1]]
                # Sharing a paper is not a transitive team relation: a coauthor stays with the direct association.
                if 'coauthor' in kinds:
                    updated['group_evidence'] += ' | coauthor chain stopped at direct association'
                    resolved.append(updated)
                    continue
                via = '; '.join(f"via {results[i]['name']}: {results[i]['group_evidence']}" for i in path[1:])
                # A member of a project collaborator's team reaches the PI only through that project.
                updated.update(group=results[current]['group'], group_link='project' if 'project' in kinds else result['group_link'],
                               group_evidence=f"{result['group_evidence']} | {via}")
        resolved.append(updated)
    return resolved


def group_for(person: dict, leaders: list[dict], persons: list[dict]) -> str:
    """Compatibility helper; assign_groups also returns the required evidence."""
    return next(p['group'] for original, p in zip(persons, assign_groups(persons)) if original is person)
