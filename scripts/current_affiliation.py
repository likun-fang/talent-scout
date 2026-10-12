#!/usr/bin/env python3
"""Fill current_affiliation / country / affiliation_source on persons.jsonl.

  OPENALEX_API_KEY=... current_affiliation.py persons.jsonl [--region EU27+UK+CH]
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
from person_fields import assign_groups, topics_for
from openalex_auth import auth_headers

REGIONS = {
    "EU27": ["AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"],
    "UK": ["GB"], "CH": ["CH"], "EEA": ["IS","LI","NO"],
}

def region_codes(spec: str) -> set[str]:
    return {c for part in spec.split("+") for c in REGIONS.get(part.strip().upper(), [part.strip().upper()] if len(part.strip()) == 2 else [])}

class ResponseCache:
    """Cache raw JSON atomically; coalesce duplicate lookups within one run."""

    def __init__(self, directory: str) -> None:
        self.directory = Path(directory)
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
        headers = auth_headers()
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
    ('phd_student', r'\b(?:ph\.?d\.? (?:students?|candidates?|researchers?)|doctoral (?:students?|researchers?|candidates?)|doktorand\w*|dissertation|promovierende\w*)\b'),
    ('researcher', r'\b(?:postdoc\w*|senior scientists?|research scientists?|wissenschaftliche\w* mitarbeiter\w*|research associates?|staff scientists?|oberassistent\w*|research fellows?)\b'),
    ('professor', r'\b(?:professors?|professorin\w*|prof\.|chair of|chair holders?|chaired|professor and chair|lehrstuhl\w*|juniorprofessor\w*|faculty members?)\b|\bprof\.|^\s*faculty\s*$'),
    ('group_leader', r'\b(?:group leaders?|heads? of (?:the )?[\w\s,-]{0,60}?(?:lab\w*|group|team|unit|chair|institute|department)|principal investigators?|nachwuchsgruppenleiter\w*|team leaders?|lab directors?)\b|^\s*pi\s*$'),
)
# Add country-specific titles without widening the existing English/German rules.
# These are appointments/stages, not degree names (doctorat/doctorado/Dr.). French
# maître de conférences and directeur de recherche do not prove a full professorship
# or leadership of a particular group; preserve the original title in the evidence.
LOCAL_TITLE_RULES = (
    ('phd_student', r'\b(?:doctorant(?:e)?s?|doctorand[oa]s?|promovend(?:us|a|i|ae))\b'),
    ('researcher', r'\b(?:ma[iî]tre(?:sse)?s? de conf[eé]rences|charg[eé](?:e)?s? de recherche|direct(?:eur|rice)s? de recherche|investigador(?:a)?(?:es|as)? postdoctoral(?:es)?|onderzoekers?)\b'),
    ('professor', r'\b(?:professeur(?:e)?s? des universit[eé]s|catedr[aá]tic[oa]s? de universidad|profesor(?:a)?(?:es|as)? titular(?:es)? de universidad|hoogleraren|hoogleraar)\b'),
    ('group_leader', r"\b(?:responsables? d['’][eé]quipe|chef(?:fe)?s? d['’][eé]quipe|jef[ea]s? de grupo|groepsleiders?)\b"),
)
LOCAL_PAST_TITLE = r'\b(?:former|previous|ancien(?:ne)?s?|ex|voormalig(?:e)?|antigu[oa]s?)\b'
LOCAL_MIXED = r'\s(?:et|y|en)\s'
MIXED = r'\s(?:and|und|&|/|or|oder)\s|,\s|/'
# Words that make a joined heading a membership list rather than one person's stage.
OTHER_MEMBERS = r'\b(?:staff|scientific (?:assistants?|staff|employees?)|technical|administrative|alumni|members?|guests?|visitors?|students?)\b'
SUPERVISOR = r'\b(?:in the group of|in the lab of|supervised by|advised by|with prof|advisor|betreut von|sous la direction de|supervisad[oa] por|onder begeleiding van)\b.*$'
PRECEDENCE = ('phd_student', 'professor', 'group_leader', 'researcher')
COMPANY = r'\b(?:gmbh|ag|ltd|inc|sa)\b'
FUNDING_PREFIXES = ('erc_', 'dfg_', 'snsf_')
# Personal grants name the holder's own career stage; every other funding PI leads a project.
FUNDING_ROLE = {'snsf_ambizione': 'researcher', 'dfg_walter_benjamin': 'researcher', 'snsf_postdoc_mobility': 'researcher',
                'snsf_doc_ch': 'phd_student', 'snsf_doc_mobility': 'phd_student'}


def title_class(title: str, institution_type: str = '', affiliation: str = '') -> str:
    """Class named by a verbatim title. The person's own role is read before a supervisor mention.
    A heading that joins a doctoral stage with another stage or with staff words ("PhD Students and
    Scientific Assistants", "Staff / PhD Students") returns 'mixed': it proves membership, not the stage.
    One person's joined titles ("Professor and Head of Lab") keep the highest-precedence class."""
    own = re.sub(SUPERVISOR, '', title, flags=re.I)
    matches = [role_class for role_class, pattern in TITLE_RULES if re.search(pattern, own, re.I)]
    local_matches = [] if re.search(LOCAL_PAST_TITLE, own, re.I) else [
        role_class for role_class, pattern in LOCAL_TITLE_RULES if re.search(pattern, own, re.I)]
    matches = list(dict.fromkeys(matches + local_matches))
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
            institution_type == 'research' or re.search(r'\b(?:institute|institut|research institute)\b', title + ' ' + affiliation, re.I)):
        return 'professor'
    if re.search(r'\b(?:gmbh|ag|ltd|inc)\b', title, re.I) or (
            institution_type == 'company' and re.search(r'\b(?:engineer|software)\b', title, re.I)):
        return 'industry'
    return ''


def role_result(role_class: str, confidence: str, rule: int, source: str, excerpt: str, url: str) -> dict:
    caveat = ' (DE: may be PhD student)' if re.search(r'wissenschaftlicher mitarbeiter', excerpt, re.I) else ''
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
            entries.append(('signal role_title', signal['role_title'], signal.get('evidence_url', ''),
                            signal.get('institution_type') or inst_type, signal.get('affiliation_raw', '')))
    return entries


def inferred_role(person: dict, run_year: int) -> dict:
    signals = person.get('signals', [])
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


def classify_role(person: dict, run_year: int, employment: tuple | None = None,
                  institution: tuple | None = None) -> dict:
    """First matching rule wins. Classification is pure and never dates a verification."""
    verified = final_pass_title(person)
    if verified:
        role_class = title_class(verified[0], person.get('institution_type', ''), person.get('current_affiliation', ''))
        if role_class and role_class != 'mixed':
            return role_result(role_class, 'high', 0, f"final pass {person.get('last_verified')}", verified[0], verified[1])
    mixed = None
    for source, title, url, inst_type, affiliation in title_evidence(person, employment, institution):
        role_class = title_class(title, inst_type, affiliation)
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
    if institution and len(institution) > 3 and institution[3] == 'company':
        return role_result('industry', 'medium', 3, 'OpenAlex institution.type', 'company', institution[4])
    if person.get('institution_type') == 'company':
        return role_result('industry', 'medium', 3, 'OpenAlex institution.type', 'company', person.get('institution_url', ''))
    for signal in signals:
        if re.search(COMPANY, signal.get('affiliation_raw', ''), re.I):
            return role_result('industry', 'medium', 3, 'affiliation_raw', signal['affiliation_raw'], signal.get('evidence_url', ''))
    return inferred_role(person, run_year)

def enrich(p: dict, codes: set[str], cache: ResponseCache | None = None,
           run_year: int | None = None) -> dict:
    sigs = p.get("signals", [])
    newest = max(sigs, key=lambda s: date_value(s.get("date")), default={})
    ev = (newest.get("affiliation_raw", ""), newest.get("country", ""), newest.get("date", ""))
    ev_date = date_value(ev[2])
    ev_year = ev_date.year if ev_date != datetime.date.min else 0
    notes = list(p.get("notes_list", []))
    ids = p.get("ids") or {}
    oc = orcid_current(ids["orcid"], cache) if ids.get("orcid") else None
    oa = openalex_current(ids["openalex"], cache) if ids.get("openalex") else None
    first_year = first_publication_year(ids["openalex"], cache) if ids.get("openalex") else None
    stale_orcid = (oc and oc[1] and ev_year and ev[0] and ev[1] and
                   (not oc[0] or oc[0] < ev_year) and oc[2] != ev[1])
    stale_openalex = (oa and oa[0] and ev[0] and date_value(oa[2]) != datetime.date.min and
                      ev_date > date_value(oa[2]) and not (inst_tokens(oa[0]) & inst_tokens(ev[0])) and
                      oa[0].strip().casefold() != ev[0].strip().casefold())
    if stale_orcid:
        notes.append(f"ORCID open employment {oc[1]} ({oc[2]}, since {oc[0] or '?'}) predates newest evidence; evidence used")
        cur = (ev[0], ev[1], f"evidence {ev[2]}")
    elif oc and oc[1]:
        cur = (oc[1], oc[2], f"orcid employment since {oc[0] or '?'}")
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
              "notes": "; ".join(n for n in notes if n)[:500]}
    employment = oc if oc and not stale_orcid else None
    institution = oa if oa and not stale_openalex and oa[0] == cur[0] else None
    return {**result, **classify_role(result, run_year or datetime.date.today().year, employment, institution)}

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("persons"); ap.add_argument("--region", "--region-extended", dest="region", default="EU27+UK+CH")
    ap.add_argument("--date", type=datetime.date.fromisoformat, default=datetime.date.today())
    ap.add_argument("--region-core", default="DE+CH")
    ap.add_argument("--cache-dir", default="./cache/affiliation/", help="Directory for reusable lookup JSON")
    ap.add_argument("--workers", type=int, choices=range(1, 7), default=1,
                    help="Concurrent persons to enrich (1-6); output stays in input order")
    a = ap.parse_args()
    try:
        with open(a.persons, encoding="utf-8") as source:
            persons = [json.loads(l) for l in source if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"bad input: {exc}")
    codes = region_codes(a.region)
    cache = ResponseCache(a.cache_dir)
    with ThreadPoolExecutor(max_workers=a.workers) as executor:
        results = list(executor.map(lambda person: enrich(person, codes, cache, a.date.year), persons))
    from table_export import tier_for
    for result in assign_groups(results):
        print(json.dumps({**result, "tier": tier_for(result, region_codes(a.region_core), codes)}, ensure_ascii=False))
    print(f"enriched {len(persons)} persons", file=sys.stderr)

if __name__ == "__main__":
    main()
