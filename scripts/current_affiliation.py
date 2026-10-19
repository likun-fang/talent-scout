#!/usr/bin/env python3
"""Fill current_affiliation / country / affiliation_source on persons.jsonl.

  OPENALEX_API_KEY=... current_affiliation.py persons.jsonl [--region EU27+UK+CH+NO]
      [--cache-dir ./cache/affiliation/] [--workers 1] > persons.enriched.jsonl

Order of trust, per person:
 1. ORCID employment with no end date — unless it started before the newest evidence and names another
    country; an unknown start year also predates dated evidence.
 2. OpenAlex last_known_institutions, when inside the region, unless newer evidence
    names a different institution than the author record's updated_date supports.
 3. The newest signal's affiliation. If OpenAlex puts the person outside the region, a note says so.
OpenAlex also supplies first_pub_year from the author's earliest publication.
Successful JSON responses are cached by provider and ID, without an automatic expiry.
Failed lookups are retried on later runs. --workers accepts 1 to 6 and preserves input order.
Standard library only; records never mutated in place.
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, re, sys, tempfile, threading, unicodedata
import urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable
from person_fields import assign_groups, topics_for, same_institution
from openalex_auth import auth_headers
from publication_signals import inference_signals

REGIONS = {
    "EU27": ["AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"],
    "UK": ["GB"], "CH": ["CH"], "NO": ["NO"], "EEA": ["IS","LI","NO"],
}

def region_codes(spec: str) -> set[str]:
    return {c for part in spec.split("+") for c in REGIONS.get(part.strip().upper(), [part.strip().upper()] if len(part.strip()) == 2 else [])}

class ResponseCache:
    """Cache raw JSON atomically; coalesce duplicate lookups within one run."""

    def __init__(self, directory: str, offline: bool = False) -> None:
        self.directory = Path(directory)
        self.offline = offline
        self.misses = 0
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def load(self, key: str, fetch: Callable[[], dict | None]) -> dict | None:
        filename = hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json"
        path = self.directory / filename
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            try:
                with path.open(encoding="utf-8") as f:
                    cached = json.load(f)
                if isinstance(cached, dict):
                    return cached
            except (OSError, ValueError):
                pass
            if self.offline:
                with self._guard:
                    self.misses += 1
                return None
            response = fetch()
            if not isinstance(response, dict):
                return None
            temporary = None
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                                 suffix=".tmp", delete=False) as f:
                    temporary = f.name
                    json.dump(response, f)
                os.replace(temporary, path)
            except OSError as exc:
                print(f"cache write failed: {exc}", file=sys.stderr)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
            return response

def get(url: str, headers: dict | None = None) -> dict | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=40) as r:
            return json.load(r)
    except Exception as exc:  # network, HTTP, JSON
        # Query strings may contain an API key; never include them in diagnostics.
        print(f"lookup failed {url.split('?')[0]}: {type(exc).__name__}", file=sys.stderr)
        return None

def cached_get(key: str, url: str, cache: ResponseCache | None,
               headers: dict | None = None) -> dict | None:
    return cache.load(key, lambda: get(url, headers)) if cache is not None else get(url, headers)

def orcid_current(orcid: str, cache: ResponseCache | None = None) -> tuple | None:
    orcid = orcid.rstrip("/").rsplit("/", 1)[-1]
    d = cached_get(f"orcid-employments/{orcid}", f"https://pub.orcid.org/v3.0/{orcid}/employments",
                   cache, {"Accept": "application/json"})
    best = None
    for g in (d or {}).get("affiliation-group", []):
        for s in g.get("summaries", []):
            e = s.get("employment-summary", {})
            if e.get("end-date"):
                continue
            st = e.get("start-date") or {}
            year = int(((st.get("year") or {}).get("value")) or 0)
            org = e.get("organization", {})
            cand = (year, org.get("name"), (org.get("address") or {}).get("country"),
                    e.get("role-title") or "", f"https://orcid.org/{orcid}")
            best = cand if best is None or cand[0] > best[0] else best
    return best

def openalex_get(path: str, cache_key: str, cache: ResponseCache | None) -> dict | None:
    try:
        headers = {} if cache is not None and cache.offline else auth_headers()
    except RuntimeError as exc:
        raise SystemExit(f"openalex configuration error: {exc}") from None
    return cached_get(cache_key, f"https://api.openalex.org/{path}", cache, headers)

def openalex_current(author_id: str, cache: ResponseCache | None = None) -> tuple | None:
    author_id = author_id.rstrip("/").rsplit("/", 1)[-1]
    d = openalex_get(f"authors/{author_id}", f"openalex-author/{author_id}", cache)
    inst = ((d or {}).get("last_known_institutions") or [None])[0]
    return (inst.get("display_name"), inst.get("country_code"), d.get("updated_date") or "", inst.get("type") or "",
            inst.get("id") or f"https://openalex.org/{author_id}") if inst else None

def first_publication_year(author_id: str, cache: ResponseCache | None = None) -> int | None:
    author_id = author_id.rstrip("/").rsplit("/", 1)[-1]
    path = f"works?filter=author.id:{author_id}&sort=publication_year:asc&per_page=1&select=publication_year"
    d = openalex_get(path, f"openalex-first-publication/{author_id}", cache)
    works = (d or {}).get("results") or []
    return works[0].get("publication_year") if works else None

def date_value(value: str) -> datetime.date:
    value = (value or "")[:10]
    value += "-01-01" if len(value) == 4 else "-01" if len(value) == 7 else ""
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return datetime.date.min

def inst_tokens(value: str) -> set[str]:
    """Compare meaningful normalized words, including short names such as ETH."""
    normalized = unicodedata.normalize("NFKD", value or "").casefold()
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    generic = {"university", "universitat", "universite", "universita", "institute", "institution",
               "technology", "technological", "research", "department", "school", "college",
               "laboratory", "laboratories", "center", "centre", "the", "and", "for"}
    return {word for word in re.findall(r"\w+", normalized) if len(word) > 2 and word not in generic}


# Most specific first: a lab line such as "Postdoctoral researcher in the group of Prof. Meyer" names the
# person's own role before the supervisor's. Bare "chair" is a board or session title, not a professorship.
# Patterns accept plural and German feminine forms, because section headings ("Doctoral students",
# "Wissenschaftliche Mitarbeiterinnen") are a main source of role_title.
TITLE_RULES = (
    ('phd_student', r'\b(?:ph\.?d\.?[ -](?:students?|candidates?|researchers?|fellows?)|doctoral (?:students?|researchers?|candidates?|assistants?|thes[ei]s)|research students?|(?:industri)?doktorand\w*|dissertation|promovierende\w*)\b'),
    # Lecturer ranks (Swedish universitetslektor, a lecturer outside GB/IE) prove a staff position, not leadership
    # of a group; in GB and IE they are faculty ranks (FACULTY_RANKS below).
    ('researcher', r'\b(?:post[ -]?do[ck]\w*|research and teaching associates?|senior scientists?|senior researchers?|advanced researchers?|researchers?|imaging scientists?|clinical scientists?|physician scientists?|research scientists?|wissenschaftliche\w* mitarbeiter\w*|scientific staff|research associates?|staff scientists?|oberassistent\w*|ober[aä]rzt\w*|research fellows?|(?:senior |associate |assistant |university )?lecturers?|universitetslektor\w*|forskare|ricerca(?:tore|trice|tori|trici) a tempo determinato)\b'),
    ('professor', r'\b(?:honorarprofessor\w*|honorary professors?|professors?|professorin\w*|prof\.|chair of|chair ?holders?|chaired|professor and chair|lehrstuhl\w*|juniorprofessor\w*|hochschullehrer\W?\w*|faculty members?)\b|\bprof\.|^\s*faculty(?:\s*\(w[123]\))?\s*$'),
    ('group_leader', r'\b(?:research junior group leads?|jrg leaders?|junior research group leaders?|site leads?|group leaders?|group heads?|principal researchers?|heads? of (?:the )?[\w\s,-]{0,60}?(?:lab\w*|group|team|unit|chair|institute|department)|heads? of [\w][\w\s,-]{0,60}|principal investigators?|nachwuchsgruppenleiter\w*|team lead(?:er)?s?|lab directors?)\b|^\s*(?:pi|heads?)\s*$'),
)
# In GB and IE, Lecturer, Senior Lecturer and Reader are the permanent faculty ranks below Professor (the US assistant
# and associate professor), so there they count as professor. External, guest and visiting lecturers, the teaching-only
# associate/assistant lecturer and the German Lehrbeauftragte are hired to teach a course, and a research lecturer
# (Oxford) holds a research-staff post: none of them count.
FACULTY_RANK_COUNTRIES = {'GB', 'IE'}
FACULTY_RANKS = r'\b(?:(?:senior |university )?lecturers?|readers?|associate professors?)\b'
NOT_FACULTY = r'\b(?:external|guest|visiting|associate|assistant|research)\s+lecturers?\b|\blehrbeauftragte'
# "Scholars" is a doctoral stage only where the page belongs to a doctoral school (IMPRS-IS calls its doctoral
# researchers scholars); elsewhere it is a visitor or fellowship label.
DOCTORAL_SCHOOL = r'\b(?:imprs\w*|max planck research school|graduate school|doctoral (?:school|program\w*))\b'
# Add country-specific titles without widening the existing English/German rules.
# These are appointments/stages, not degree names (doctorat/doctorado/Dr.). French
# maître de conférences and directeur de recherche do not prove a full professorship
# or leadership of a particular group; preserve the original title in the evidence.
LOCAL_TITLE_RULES = (
    ('phd_student', r'\b(?:doctorant(?:e)?s?|doctorand[oa]s?|promovend(?:us|a|i|ae))\b'),
    ('researcher', r'\b(?:ma[iî]tre(?:sse)?s? de conf[eé]rences|charg[eé](?:e)?s? de recherche|direct(?:eur|rice)s? de recherche|investigador(?:a)?(?:es|as)? postdoctoral(?:es)?|onderzoekers?)\b'),
    ('professor', r'\b(?:professeur(?:e)?s? des universit[eé]s|catedr[aá]tic[oa]s? de universidad|(?:profesor(?:a)?(?:es|as)? )?titular(?:es)? de universidad|profesor(?:a)?(?:es|as)? agregad[oa]s?|hoogleraren|hoogleraar)\b'),
    ('group_leader', r"\b(?:responsables? d['’][eé]quipe|chef(?:fe)?s? d['’][eé]quipe|jef[ea]s? de grupo|groepsleiders?)\b"),
)
LOCAL_PAST_TITLE = r'\b(?:former|previous|ancien(?:ne)?s?|ex|voormalig(?:e)?|antigu[oa]s?)\b'
LOCAL_MIXED = r'\s(?:et|y|en)\s'
MIXED = r'\s(?:and|und|&|/|or|oder)\s|,\s|/'
# Words that make a joined heading a membership list rather than one person's stage.
OTHER_MEMBERS = r'\b(?:staff|scientific (?:assistants?|staff|employees?)|technical|administrative|alumni|members?|guests?|visitors?|students?)\b'
SUPERVISOR = r'\b(?:in the group of|in the lab of|supervised by|advised by|with prof|advisor|betreut von|sous la direction de|supervisad[oa] por|onder begeleiding van)\b.*$'
PRECEDENCE = ('phd_student', 'professor', 'group_leader', 'researcher')
COMPANY = (r'\b(?:gmbh|ag|ltd|inc|sas|b\.v\.|research europe)(?:\b|(?<=\.))'
           r'|\b(?-i:SA)(?=\s*(?:,|$))|\b(?:naver|bell)\s+labs\b')
COMPANY_NAMES = r'\b(?:naver|deepmind|google|facebook|sony|bosch|mistral|aleph alpha|microsoft|nvidia|hugging face)\b'
COMPANY_SUFFIX = r'\b(?:gmbh|ag|inc|ltd)\b'
ACADEMIC_EMPLOYER = r'\b(?:hospital|klinik|clinic|university|universität|université|universiteit|institute of technology|hochschule|school|college)\b'
RESEARCH_GMBH = r'\b(?:dfki|forschungszentrum|forschungsgesellschaft|fraunhofer|helmholtz|max.planck|leibniz)\b'
# A founder or C-level title is an industry role; a professorial title next to it still wins (precedence above).
FOUNDER = r'\b(?:co-?founders?|founders?|chief (?:executive|technology|operating|scientific) officer|ceo|cto|coo|cso)\b'
FUNDING_PREFIXES = ('erc_', 'dfg_', 'snsf_', 'fwf_', 'swecris_', 'rcn_', 'dff_', 'fris_', 'aei_')
# Personal grants name the holder's own career stage; every other funding PI leads a project.
FUNDING_ROLE = {'snsf_ambizione': 'researcher', 'dfg_walter_benjamin': 'researcher', 'snsf_postdoc_mobility': 'researcher',
                'snsf_swiss_postdoc': 'researcher',
                'snsf_doc_ch': 'phd_student', 'snsf_doc_mobility': 'phd_student',
                'fwf_esprit': 'researcher', 'fwf_start': 'group_leader',
                **dict.fromkeys(('fwf_project', 'swecris_project', 'rcn_project', 'dff_project',
                                 'fris_project', 'aei_project'), 'group_leader')}


def title_class(title: str, institution_type: str = '', affiliation: str = '', country: str = '') -> str:
    """Class named by a verbatim title. The person's own role is read before a supervisor mention.
    A heading that joins a doctoral stage with another stage or with staff words ("PhD Students and
    Scientific Assistants", "Staff / PhD Students") returns 'mixed': it proves membership, not the stage.
    One person's joined titles ("Professor and Head of Lab") keep the highest-precedence class.
    `country` (ISO-2 of the person's current country) decides whether a lecturer rank is faculty."""
    own = re.sub(SUPERVISOR, '', title, flags=re.I)
    matches = [role_class for role_class, pattern in TITLE_RULES if re.search(pattern, own, re.I)]
    if ((country or '').upper() in FACULTY_RANK_COUNTRIES and re.search(FACULTY_RANKS, own, re.I)
            and not re.search(NOT_FACULTY, own, re.I)):
        matches.append('professor')
    local_matches = [] if re.search(LOCAL_PAST_TITLE, own, re.I) else [
        role_class for role_class, pattern in LOCAL_TITLE_RULES if re.search(pattern, own, re.I)]
    matches = list(dict.fromkeys(matches + local_matches))
    if not matches and re.search(r'^\s*scholars?\s*$', own, re.I) and re.search(DOCTORAL_SCHOOL, title + ' ' + affiliation, re.I):
        matches = ['phd_student']
    joined = re.search(MIXED, own, re.I)
    if local_matches:
        joined = joined or re.search(LOCAL_MIXED, own, re.I)
    stage_words = re.sub(r'ph\.?d\.? students?|doctoral students?', '', own, flags=re.I)
    if joined and matches and (('phd_student' in matches and len(matches) > 1) or re.search(OTHER_MEMBERS, stage_words, re.I)):
        return 'mixed'
    for role_class in PRECEDENCE:
        if role_class in matches:
            return role_class
    if re.search(r'\b(?:direktor|director)\b', title, re.I) and (
            institution_type == 'research' or re.search(r'\b(?:institute|institut|research institute|mpi)\b', title + ' ' + affiliation, re.I)):
        return 'professor'
    if re.search(r'\b(?:gmbh|ag|ltd|inc)\b', title, re.I) or re.search(FOUNDER, own, re.I) or (
            institution_type == 'company' and re.search(r'\b(?:engineer|software)\b', title, re.I)):
        return 'industry'
    return ''


def role_result(role_class: str, confidence: str, rule: int, source: str, excerpt: str, url: str) -> dict:
    caveat = ' (DE: may be PhD student)' if re.search(r'wissenschaftlicher mitarbeiter|scientific staff|research and teaching associate', excerpt, re.I) else ''
    if re.search(r'\b(?:honorarprofessor\w*|honorary professor)\b', excerpt, re.I):
        caveat += ' (honorary)'
    return {'role_class': role_class, 'role_confidence': confidence,
            'role_evidence': f'rule {rule}: {source}{caveat} | {excerpt} | {url}'}


def title_evidence(person: dict, employment: tuple | None, institution: tuple | None) -> list[tuple]:
    """Within rule 1: current ORCID, then newest signal titles. (The final pass is rule 0.)"""
    entries = []
    inst_type = institution[3] if institution and len(institution) > 3 else person.get('institution_type', '')
    affiliation = person.get('current_affiliation', '')
    if employment and len(employment) > 3 and employment[3]:
        entries.append(('ORCID employment role-title', employment[3], employment[4], inst_type, employment[1]))
    for signal in sorted(person.get('signals', []), key=lambda s: date_value(s.get('date')), reverse=True):
        if signal.get('role_title'):
            # The parent names the page the heading sits on ("Scholars" under the IMPRS-IS roster).
            context = ' / '.join(filter(None, [signal.get('affiliation_raw'), signal.get('parent')]))
            entries.append(('signal role_title', signal['role_title'], signal.get('evidence_url', ''),
                            signal.get('institution_type') or inst_type, context))
    return entries


def inferred_role(person: dict, run_year: int) -> dict:
    signals = inference_signals(person.get('signals', []))
    try:
        first_year_number = int(person.get('first_pub_year') or 0)
        years = run_year - first_year_number if 1 <= first_year_number <= run_year else -1
    except (TypeError, ValueError):
        years = -1
    first_year = person.get('first_pub_year')
    role_class = 'unknown'
    if first_year and 0 <= years <= 5 and sum(s.get('role') == 'first_author' for s in signals) > len(signals) / 2:
        role_class = 'phd_student'
    elif first_year and years >= 10 and sum(s.get('role') in {'last_author', 'pi'} for s in signals) > len(signals) / 2:
        role_class = 'group_leader'
    excerpt = f'first_pub_year={first_year or "unknown"}; run_year={run_year}; roles=' + ','.join(s.get('role') or 'unknown' for s in signals)
    return role_result(role_class, 'low', 4, 'publication/role inference', excerpt,
                       next((s['evidence_url'] for s in signals if s.get('evidence_url')), ''))


def final_pass_title(person: dict) -> tuple | None:
    """Rule 0: a title read from the person's own or institutional page in the final pass, with its URL
    and the read date. `linkedin_headline` / `linkedin_url` are accepted as the same adapter."""
    title = person.get('final_pass_title') or person.get('linkedin_headline')
    url = person.get('final_pass_url') or person.get('linkedin_url', '')
    if person.get('last_verified') and title:
        return (title, url)
    return None


def apply_final_pass(person: dict) -> dict:
    """Apply reviewed affiliation without mutating signals or losing the provider provenance."""
    if not person.get('final_pass_affiliation'):
        return dict(person)
    source = f"final pass {person.get('last_verified', '')} {person.get('final_pass_url', '')}".strip()
    notes = person.get('notes', '')
    if person.get('affiliation_source') != source:
        newest = max(person.get('signals', []), key=lambda s: date_value(s.get('date')), default={})
        old = person.get('current_affiliation') or newest.get('affiliation_raw', '')
        old_source = person.get('affiliation_source') or f"evidence {newest.get('date', '')}"
        provenance = f"source affiliation: {old} ({old_source})"
        if old and provenance not in notes:
            notes = '; '.join(filter(None, [notes, provenance]))
    return {**person, 'current_affiliation': person['final_pass_affiliation'],
            'country': person.get('final_pass_country') or '', 'affiliation_source': source, 'notes': notes}


def company_evidence(person: dict, institution: tuple | None) -> tuple | None:
    """Use the most current employer; a former company's type cannot override a reviewed move."""
    signals = sorted(person.get('signals', []), key=lambda s: date_value(s.get('date')), reverse=True)
    newest = next((s for s in signals if s.get('affiliation_raw')), {})
    affiliation = person.get('final_pass_affiliation') or person.get('current_affiliation') or newest.get('affiliation_raw', '')
    final = bool(person.get('final_pass_affiliation'))
    url = person.get('final_pass_url', '') if final else newest.get('evidence_url', '')
    if re.search(ACADEMIC_EMPLOYER, affiliation, re.I) and not re.search(COMPANY_SUFFIX, affiliation, re.I):
        return None
    if re.search(RESEARCH_GMBH, affiliation, re.I):
        return None  # DFKI, Forschungszentrum Jülich and the like are research institutes in a GmbH shell
    if re.search(COMPANY, affiliation, re.I) or re.search(COMPANY_NAMES, affiliation, re.I):
        return ('high' if final and person.get('last_verified') else 'medium',
                f"final pass {person.get('last_verified', '')}" if final else 'current employer', affiliation, url)
    if institution and len(institution) > 3 and institution[3] == 'company' and (
            not affiliation or same_institution(affiliation, institution[0])):
        return ('medium', 'OpenAlex institution.type', affiliation or institution[0], institution[4])
    if person.get('institution_type') == 'company' and (not final or same_institution(
            affiliation, person.get('institution_name', ''))):
        return ('medium', 'OpenAlex institution.type', affiliation, person.get('institution_url', ''))
    if not final:
        for signal in signals:
            if signal.get('institution_type') == 'company' and (not affiliation or same_institution(affiliation, signal.get('affiliation_raw', ''))):
                return ('medium', 'signal institution.type', affiliation, signal.get('evidence_url', ''))
    return None


def classify_role(person: dict, run_year: int, employment: tuple | None = None,
                  institution: tuple | None = None) -> dict:
    """First matching rule wins. Classification is pure and never dates a verification."""
    verified = final_pass_title(person)
    company = company_evidence(person, institution)
    entries = title_evidence(person, employment, institution)
    country = person.get('final_pass_country') or person.get('country') or ''
    if company:
        title = verified[0] if verified else next((entry[1] for entry in entries), '')
        url = verified[1] if verified else next((entry[2] for entry in entries), company[3])
        own_class = title_class(title, country=country)
        if own_class == 'professor':
            return role_result('professor', 'high', 0 if verified else 1, 'professorial title', title, url)
        if own_class == 'mixed':
            return role_result('unknown', 'low', 0 if verified else 1, 'mixed heading proves membership only', title, url)
        return role_result('industry', company[0], 3, f'{company[1]} ({company[2]})',
                           f'industry | {title}', company[3] or url)
    if verified:
        role_class = title_class(verified[0], person.get('institution_type', ''),
                                 person.get('final_pass_affiliation') or person.get('current_affiliation', ''), country)
        if role_class == 'mixed':
            return role_result('unknown', 'low', 0, 'final pass: mixed heading proves membership only', verified[0], verified[1])
        if role_class:
            return role_result(role_class, 'high', 0, f"final pass {person.get('last_verified')}", verified[0], verified[1])
    mixed = None
    for source, title, url, inst_type, affiliation in entries:
        role_class = title_class(title, inst_type, affiliation, country)
        if role_class == 'mixed':
            mixed = mixed or (source, title, url)
            continue
        if role_class:
            return role_result(role_class, 'high', 1, source, title, url)
    signals = sorted(person.get('signals', []), key=lambda s: date_value(s.get('date')), reverse=True)
    for signal in signals:
        kind = signal.get('signal_type', '')
        if kind.startswith(FUNDING_PREFIXES) and signal.get('role') == 'pi':
            # A grant proves the person leads a project, not a professorial appointment: medium until a title confirms.
            role_class = FUNDING_ROLE.get(kind, 'group_leader')
            return role_result(role_class, 'medium', 2, 'funding PI (no title seen)', signal.get('snippet') or kind, signal.get('evidence_url', ''))
    if mixed:
        return role_result('unknown', 'low', 1, f'{mixed[0]}: mixed heading proves membership only', mixed[1], mixed[2])
    return inferred_role(person, run_year)

def enrich(p: dict, codes: set[str], cache: ResponseCache | None = None,
           run_year: int | None = None) -> dict:
    sigs = p.get("signals", [])
    newest = max(sigs, key=lambda s: date_value(s.get("date")), default={})
    ev = (newest.get("affiliation_raw", ""), newest.get("country", ""), newest.get("date", ""))
    ev_date = date_value(ev[2])
    ev_year = ev_date.year if ev_date != datetime.date.min else 0
    notes = list(p.get("notes_list", []))
    if p.get("notes"):
        notes.append(p["notes"])
    ids = p.get("ids") or {}
    oc = orcid_current(ids["orcid"], cache) if ids.get("orcid") else None
    oa = openalex_current(ids["openalex"], cache) if ids.get("openalex") else None
    first_year = first_publication_year(ids["openalex"], cache) if ids.get("openalex") else None
    # An open ORCID employment that the newest evidence still names is current, even when that evidence lists a
    # second institution in another country (a Copenhagen professor on an ETH paper stays in Copenhagen).
    named_by_evidence = bool(oc and oc[1] and ev[0] and inst_tokens(oc[1]) & inst_tokens(ev[0]))
    stale_orcid = (oc and oc[1] and ev_year and ev[0] and ev[1] and
                   (not oc[0] or oc[0] < ev_year) and oc[2] != ev[1] and not named_by_evidence)
    stale_openalex = (oa and oa[0] and ev[0] and date_value(oa[2]) != datetime.date.min and
                      ev_date > date_value(oa[2]) and not (inst_tokens(oa[0]) & inst_tokens(ev[0])) and
                      oa[0].strip().casefold() != ev[0].strip().casefold())
    if stale_orcid:
        notes.append(f"ORCID open employment {oc[1]} ({oc[2]}, since {oc[0] or '?'}) predates newest evidence; evidence used")
        cur = (ev[0], ev[1], f"evidence {ev[2]}")
    elif oc and oc[1]:
        cur = (oc[1], oc[2], f"orcid employment since {oc[0] or '?'}")
        # ORCID addresses carry typos ("Lisbon, ID"): when one piece of evidence names the same employer alone,
        # with another country, the evidence country wins; a country on an affiliation list proves nothing.
        single = not re.search(r';|\s/\s', ev[0] or '')
        if named_by_evidence and single and ev[1] and ev[1] != oc[2]:
            cur = (oc[1], ev[1], f"orcid employment since {oc[0] or '?'}; country from evidence {ev[2]}")
            notes.append(f"ORCID address says {oc[2]}, evidence {ev[2]} places {oc[1]} in {ev[1]}; evidence country used")
    elif oa and oa[1] in codes and not stale_openalex:
        cur = (oa[0], oa[1], f"openalex last_known {oa[2]}")
    else:
        cur = (ev[0], ev[1], f"evidence {ev[2]}")
        if stale_openalex:
            notes.append(f"OpenAlex last_known {oa[0]} (updated {oa[2]}) predates newest evidence {ev[2]} naming {ev[0]}; evidence used")
        elif oa and oa[1] and oa[1] not in codes:
            notes.append(f"OpenAlex last_known {oa[0]} ({oa[1]}): moved or mixed profile; evidence affiliation kept")
    publication = {"first_pub_year": first_year if first_year is not None else p.get("first_pub_year", "")} if ids.get("openalex") else {}
    result = {**p, **publication, "current_affiliation": cur[0], "country": cur[1], "affiliation_source": cur[2],
              "topics": topics_for(sigs), "last_verified": p.get("last_verified") or "",
              "notes": "; ".join(dict.fromkeys(n for n in notes if n))}
    employment = oc if oc and not stale_orcid else None
    institution = oa if oa and not stale_openalex and oa[0] == cur[0] else None
    if institution:
        result.update(institution_type=institution[3], institution_name=institution[0], institution_id=institution[4])
    result = apply_final_pass(result)
    if result.get('final_pass_affiliation') and employment and not same_institution(result['current_affiliation'], employment[1]):
        employment = None
    return {**result, **classify_role(result, run_year or datetime.date.today().year, employment, institution)}

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("persons"); ap.add_argument("--region", "--region-extended", dest="region", default="EU27+UK+CH+NO")
    ap.add_argument("--date", type=datetime.date.fromisoformat, default=datetime.date.today())
    ap.add_argument("--region-core", default="DE+CH")
    ap.add_argument("--cache-dir", default="./cache/affiliation/", help="Directory for reusable lookup JSON")
    ap.add_argument("--offline", action="store_true", help="Read cache only; skip and count missing queries without network or cache writes")
    ap.add_argument("--workers", type=int, choices=range(1, 7), default=1,
                    help="Concurrent persons to enrich (1-6); output stays in input order")
    a = ap.parse_args()
    try:
        with open(a.persons, encoding="utf-8") as source:
            persons = [json.loads(l) for l in source if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"bad input: {exc}")
    codes = region_codes(a.region)
    cache = ResponseCache(a.cache_dir, offline=a.offline)
    with ThreadPoolExecutor(max_workers=a.workers) as executor:
        results = list(executor.map(lambda person: enrich(person, codes, cache, a.date.year), persons))
    from table_export import tier_for
    for result in assign_groups(results):
        print(json.dumps({**result, "tier": tier_for(result, region_codes(a.region_core), codes)}, ensure_ascii=False))
    print(f"enriched {len(persons)} persons" + (f"; offline cache misses: {cache.misses}" if a.offline else ""), file=sys.stderr)

if __name__ == "__main__":
    main()
