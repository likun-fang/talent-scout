#!/usr/bin/env python3
"""Keyless OpenAlex helpers for talent-scout.

Usage:
  openalex_lookup.py --topic "embodied AI" [--region EU27+UK+CH] [--since 2021]
  openalex_lookup.py --title "Paper title"
  openalex_lookup.py --author A1234567890
Prints JSON to stdout. Standard library only.
Set OPENALEX_API_KEY (free, openalex.org/settings/api) for more than ~100 calls/day.
"""
from __future__ import annotations
import argparse, json, os, sys, urllib.parse, urllib.request

API = "https://api.openalex.org"
REGIONS = {
    "EU27": ["AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"],
    "UK": ["GB"], "CH": ["CH"], "EEA": ["IS","LI","NO"],
}

def region_codes(spec: str) -> list[str]:
    codes: list[str] = []
    for part in spec.split("+"):
        codes = codes + REGIONS.get(part.strip().upper(), [])
    return codes

def get(path: str, params: dict) -> dict:
    key = os.environ.get("OPENALEX_API_KEY")
    params = {**params, "api_key": key} if key else params
    url = f"{API}{path}?{urllib.parse.urlencode(params, safe=':,|>')}"
    req = urllib.request.Request(url, headers={"User-Agent": "talent-scout/0.1 (mailto:unset)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except Exception as exc:  # network / HTTP / JSON
        raise SystemExit(f"openalex request failed: {url}\n{exc}")

def topic_venues(phrase: str, region: str, since: int) -> dict:
    topics = get("/topics", {"search": phrase, "per_page": 3}).get("results", [])
    ids = "|".join(t["id"].rsplit("/", 1)[-1] for t in topics)
    if not ids:
        return {"topics": [], "venues": [], "institutions": [], "authors": []}
    base = f"topics.id:{ids},publication_year:>{since - 1},authorships.countries:{'|'.join(region_codes(region))}"
    def grouped(key: str) -> list[dict]:
        rows = get("/works", {"filter": base, "group_by": key, "per_page": 50}).get("group_by", [])
        return [{"id": r["key"], "name": r.get("key_display_name"), "count": r["count"]} for r in rows]
    return {
        "topics": [{"id": t["id"], "name": t["display_name"]} for t in topics],
        "venues": grouped("primary_location.source.id")[:20],
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
        "institutions": [{"name": i.get("display_name"), "country": i.get("country_code")} for i in a.get("institutions", [])],
    } for a in w.get("authorships", [])]
    return {"found": True, "title": w.get("title"), "year": w.get("publication_year"), "doi": w.get("doi"), "url": w.get("id"), "authors": authors}

def author_record(author_id: str) -> dict:
    a = get(f"/authors/{author_id}", {})
    return {"name": a.get("display_name"), "orcid": a.get("orcid"), "openalex": a.get("id"),
            "last_known_institutions": [{"name": i.get("display_name"), "country": i.get("country_code")} for i in a.get("last_known_institutions", [])],
            "works_count": a.get("works_count"), "updated": a.get("updated_date")}

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--topic"); g.add_argument("--title"); g.add_argument("--author")
    p.add_argument("--region", default="EU27+UK+CH"); p.add_argument("--since", type=int, default=2021)
    a = p.parse_args()
    if a.topic:
        out = topic_venues(a.topic, a.region, a.since)
    elif a.title:
        out = title_authors(a.title)
    else:
        out = author_record(a.author)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print(f"\nok: {'topic' if a.topic else 'title' if a.title else 'author'} lookup", file=sys.stderr)

if __name__ == "__main__":
    main()
