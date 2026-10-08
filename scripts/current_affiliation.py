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

REGIONS = {
    "EU27": ["AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"],
    "UK": ["GB"], "CH": ["CH"], "EEA": ["IS","LI","NO"],
}

def region_codes(spec: str) -> set[str]:
    return {c for part in spec.split("+") for c in REGIONS.get(part.strip().upper(), [])}

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
            cand = (year, org.get("name"), (org.get("address") or {}).get("country"))
            best = cand if best is None or cand[0] > best[0] else best
    return best

def openalex_get(path: str, cache_key: str, cache: ResponseCache | None) -> dict | None:
    key = os.environ.get("OPENALEX_API_KEY", "")
    suffix = ("&" if "?" in path else "?") + urllib.parse.urlencode({"api_key": key}) if key else ""
    return cached_get(cache_key, f"https://api.openalex.org/{path}{suffix}", cache)

def openalex_current(author_id: str, cache: ResponseCache | None = None) -> tuple | None:
    author_id = author_id.rstrip("/").rsplit("/", 1)[-1]
    d = openalex_get(f"authors/{author_id}", f"openalex-author/{author_id}", cache)
    inst = ((d or {}).get("last_known_institutions") or [None])[0]
    return (inst.get("display_name"), inst.get("country_code"), d.get("updated_date") or "") if inst else None

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

def enrich(p: dict, codes: set[str], cache: ResponseCache | None = None) -> dict:
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
    return {**p, **publication, "current_affiliation": cur[0], "country": cur[1], "affiliation_source": cur[2],
            "notes": "; ".join(n for n in notes if n)[:500]}

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("persons"); ap.add_argument("--region", default="EU27+UK+CH")
    ap.add_argument("--cache-dir", default="./cache/affiliation/", help="Directory for reusable lookup JSON")
    ap.add_argument("--workers", type=int, choices=range(1, 7), default=1,
                    help="Concurrent persons to enrich (1-6); output stays in input order")
    a = ap.parse_args()
    try:
        persons = [json.loads(l) for l in open(a.persons, encoding="utf-8") if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"bad input: {exc}")
    codes = region_codes(a.region)
    cache = ResponseCache(a.cache_dir)
    with ThreadPoolExecutor(max_workers=a.workers) as executor:
        for result in executor.map(lambda person: enrich(person, codes, cache), persons):
            print(json.dumps(result, ensure_ascii=False))
    print(f"enriched {len(persons)} persons", file=sys.stderr)

if __name__ == "__main__":
    main()
