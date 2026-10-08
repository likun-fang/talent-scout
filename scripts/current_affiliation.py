#!/usr/bin/env python3
"""Fill current_affiliation / country / affiliation_source on persons.jsonl.

  OPENALEX_API_KEY=... current_affiliation.py persons.jsonl [--region EU27+UK+CH] > persons.enriched.jsonl

Order of trust, per person:
 1. ORCID employment with no end date — unless it started before the newest evidence and names another
    country; then it is a stale open record and the evidence wins (note added).
 2. OpenAlex last_known_institutions, when inside the region.
 3. The newest signal's affiliation. If OpenAlex puts the person outside the region, a note says so.
Standard library only; records never mutated in place.
"""
from __future__ import annotations
import argparse, json, os, sys, urllib.request

REGIONS = {
    "EU27": ["AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"],
    "UK": ["GB"], "CH": ["CH"], "EEA": ["IS","LI","NO"],
}

def region_codes(spec: str) -> set[str]:
    return {c for part in spec.split("+") for c in REGIONS.get(part.strip().upper(), [])}

def get(url: str, headers: dict | None = None) -> dict | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=40) as r:
            return json.load(r)
    except Exception as exc:  # network, HTTP, JSON
        print(f"lookup failed {url}: {exc}", file=sys.stderr)
        return None

def orcid_current(orcid: str) -> tuple | None:
    d = get(f"https://pub.orcid.org/v3.0/{orcid}/employments", {"Accept": "application/json"})
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

def openalex_current(author_id: str) -> tuple | None:
    key = os.environ.get("OPENALEX_API_KEY", "")
    d = get(f"https://api.openalex.org/authors/{author_id}" + (f"?api_key={key}" if key else ""))
    inst = ((d or {}).get("last_known_institutions") or [None])[0]
    return (inst.get("display_name"), inst.get("country_code"), (d.get("updated_date") or "")[:7]) if inst else None

def enrich(p: dict, codes: set[str]) -> dict:
    sigs = p.get("signals", [])
    newest = max(sigs, key=lambda s: s.get("date") or "", default={})
    ev = (newest.get("affiliation_raw", ""), newest.get("country", ""), newest.get("date", ""))
    ev_year = int((ev[2] or "0")[:4] or 0)
    notes = list(p.get("notes_list", []))
    ids = p.get("ids") or {}
    oc = orcid_current(ids["orcid"].replace("https://orcid.org/", "")) if ids.get("orcid") else None
    oa = openalex_current(ids["openalex"]) if ids.get("openalex") else None
    if oc and oc[1] and oc[0] and oc[0] < ev_year and oc[2] != ev[1]:
        notes.append(f"ORCID open employment {oc[1]} ({oc[2]}, since {oc[0]}) predates newest evidence; evidence used")
        oc = None
    if oc and oc[1]:
        cur = (oc[1], oc[2], f"orcid employment since {oc[0] or '?'}")
    elif oa and oa[1] in codes:
        cur = (oa[0], oa[1], f"openalex last_known {oa[2]}")
    else:
        cur = (ev[0], ev[1], f"evidence {ev[2]}")
        if oa and oa[1] and oa[1] not in codes:
            notes.append(f"OpenAlex last_known {oa[0]} ({oa[1]}): moved or mixed profile; evidence affiliation kept")
    return {**p, "current_affiliation": cur[0], "country": cur[1], "affiliation_source": cur[2],
            "notes": "; ".join(n for n in notes if n)[:500]}

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("persons"); ap.add_argument("--region", default="EU27+UK+CH")
    a = ap.parse_args()
    try:
        persons = [json.loads(l) for l in open(a.persons, encoding="utf-8") if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"bad input: {exc}")
    codes = region_codes(a.region)
    for p in persons:
        print(json.dumps(enrich(p, codes), ensure_ascii=False))
    print(f"enriched {len(persons)} persons", file=sys.stderr)

if __name__ == "__main__":
    main()
