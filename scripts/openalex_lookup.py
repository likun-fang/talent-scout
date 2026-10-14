#!/usr/bin/env python3
"""Keyless OpenAlex helpers for talent-scout.

Usage:
  openalex_lookup.py --topic "embodied AI" [--region EU27+UK+CH+NO]   # lists the top 10 topics
  openalex_lookup.py --topics T10462,T10653 [--region ...] [--date YYYY-MM-DD] [--since YYYY]   # venues/institutions/authors
      for chosen topics, over the 36 months ending on --date (default today); --since YYYY widens to that January 1
  openalex_lookup.py --title "Paper title"
  openalex_lookup.py --author A1234567890
Prints JSON to stdout. Standard library only.
Set OPENALEX_API_KEY (free, openalex.org/settings/api) for more than ~100 calls/day.
"""
from __future__ import annotations
import argparse, datetime, json, os, sys, urllib.parse, urllib.request

from openalex_auth import auth_headers

API = "https://api.openalex.org"
REGIONS = {
    "EU27": ["AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"],
    "UK": ["GB"], "CH": ["CH"], "EEA": ["IS","LI","NO"],
}

def region_codes(spec: str) -> list[str]:
    codes: list[str] = []
    for part in spec.split("+"):
        codes = codes + REGIONS.get(part.strip().upper(), [part.strip().upper()] if len(part.strip()) == 2 else [])
    return codes

def get(path: str, params: dict) -> dict:
    url = f"{API}{path}?{urllib.parse.urlencode(params, safe=':,|>')}"
    try:
        headers = auth_headers()
    except RuntimeError as exc:
        raise SystemExit(f"openalex configuration error: {exc}") from None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "talent-scout/0.1 (mailto:unset)", **headers})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except Exception as exc:  # network / HTTP / JSON
        raise SystemExit(f"openalex request failed: {path} ({type(exc).__name__})")

REPOSITORY_WORDS = ("arxiv", "zenodo", "ssrn", "hal ", "research square", "biorxiv", "openreview", "techrxiv")


def non_repository_sources(venues: list[dict]) -> list[dict]:
    types = {}
    ids = list(dict.fromkeys(v['id'] for v in venues if v.get('id') and v['id'] != 'unknown'))
    for offset in range(0, len(ids), 50):
        sources = get('/sources', {'filter': 'ids.openalex:' + '|'.join(ids[offset:offset + 50]),
                                   'per_page': 50, 'select': 'id,type'}).get('results', [])
        types.update({s['id'].rsplit('/', 1)[-1]: s.get('type') for s in sources})
    return [v for v in venues if types.get(v['id']) != 'repository'
            and not any(word in (v.get('name') or '').lower() for word in REPOSITORY_WORDS)]

def list_topics(phrase: str) -> dict:
    topics = get("/topics", {"search": phrase, "per_page": 10}).get("results", [])
    return {"topics": [{"id": t["id"].rsplit("/", 1)[-1], "name": t["display_name"],
                        "subfield": (t.get("subfield") or {}).get("display_name")} for t in topics],
            "next": "pick the topics that are the domain, then rerun with --topics T1,T2"}

def window_start(end: datetime.date, months: int = 36) -> datetime.date:
    year, month = divmod((end.year * 12 + end.month - 1) - months, 12)
    month += 1
    last = (datetime.date(year + month // 12, month % 12 + 1, 1) - datetime.timedelta(days=1)).day
    return datetime.date(year, month, min(end.day, last))

def topic_groups(topic_ids: str, region: str, start: datetime.date, until: datetime.date) -> dict:
    ids = "|".join(t.strip() for t in topic_ids.split(",") if t.strip())
    base = f"topics.id:{ids},from_publication_date:{start.isoformat()},to_publication_date:{until.isoformat()},authorships.countries:{'|'.join(region_codes(region))}"
    def grouped(key: str) -> list[dict]:
        rows = get("/works", {"filter": base, "group_by": key, "per_page": 100}).get("group_by", [])
        return [{"id": r["key"].rsplit("/", 1)[-1], "name": r.get("key_display_name"), "count": r["count"]} for r in rows]
    venues = non_repository_sources(grouped("primary_location.source.id"))
    return {
        "note": "counts are works with at least one author in region; institutions and authors are leads, not rows. "
                "PMLR-hosted venues (CoRL) rarely appear here: add known venues by hand.",
        "window": {"from": start.isoformat(), "to": until.isoformat()},
        "venues": venues[:25],
        "institutions": grouped("authorships.institutions.id")[:30],
        "authors": grouped("authorships.author.id")[:50],
    }

def title_authors(title: str) -> dict:
    clean = title.replace("?", " ").replace("*", " ")  # OpenAlex treats ? and * as wildcards
    res = get("/works", {"search": clean, "per_page": 1}).get("results", [])
    if not res:
        return {"found": False, "title": title}
    w = res[0]
    authors = [{
        "position": a.get("author_position"),
        "name": a["author"].get("display_name"),
        "openalex": a["author"].get("id"),
        "orcid": a["author"].get("orcid"),
        "institutions": [{"name": i.get("display_name"), "country": i.get("country_code"), "type": i.get("type")} for i in a.get("institutions", [])],
    } for a in w.get("authorships", [])]
    return {"found": True, "title": w.get("title"), "year": w.get("publication_year"), "doi": w.get("doi"), "url": w.get("id"), "authors": authors}

def author_record(author_id: str) -> dict:
    a = get(f"/authors/{author_id}", {})
    return {"name": a.get("display_name"), "orcid": a.get("orcid"), "openalex": a.get("id"),
            "last_known_institutions": [{"name": i.get("display_name"), "country": i.get("country_code"), "type": i.get("type")} for i in a.get("last_known_institutions", [])],
            "works_count": a.get("works_count"), "updated": a.get("updated_date")}

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--topic"); g.add_argument("--topics"); g.add_argument("--title"); g.add_argument("--author")
    p.add_argument("--region", default="EU27+UK+CH+NO")
    p.add_argument("--date", type=datetime.date.fromisoformat, default=datetime.date.today(), help="Run date and publication cutoff")
    p.add_argument("--since", type=int, help="First publication year (January 1); default: 36 months before --date")
    a = p.parse_args()
    if a.since is not None and not 1 <= a.since <= a.date.year:
        p.error("--since must be between 1 and the run year")
    start = datetime.date(a.since, 1, 1) if a.since is not None else window_start(a.date)
    if a.topic:
        out = list_topics(a.topic)
    elif a.topics:
        out = topic_groups(a.topics, a.region, start, a.date)
    elif a.title:
        out = title_authors(a.title)
    else:
        out = author_record(a.author)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print("\nok", file=sys.stderr)

if __name__ == "__main__":
    main()
