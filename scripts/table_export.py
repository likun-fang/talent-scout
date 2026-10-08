#!/usr/bin/env python3
"""Write roster.csv and roster.md from persons.jsonl with the fixed talent-scout columns.

  table_export.py persons.jsonl [--domain "<phrase>"] [--date YYYY-MM-DD] [--out roster]
Standard library only.
"""
from __future__ import annotations
import argparse, csv, datetime, json, sys

COLUMNS = ["name", "current_affiliation", "country", "role", "domain", "channels_hit", "signals",
           "evidence_urls", "ids", "hop_depth", "merge_confidence", "affiliation_source", "last_verified", "notes"]

def row_for(p: dict, domain: str, date: str) -> dict:
    sigs = p.get("signals", [])
    newest = max(sigs, key=lambda s: s.get("date") or "", default={})
    return {
        "name": p.get("name", ""),
        "current_affiliation": p.get("current_affiliation") or newest.get("affiliation_raw", ""),
        "country": p.get("country") or newest.get("country", ""),
        "role": newest.get("role", "unknown"),
        "domain": domain,
        "channels_hit": ";".join(p.get("channels_hit", [])),
        "signals": ";".join(f"{s.get('signal_type')}@{s.get('date','')}" for s in sigs),
        "evidence_urls": ";".join(dict.fromkeys(s.get("evidence_url", "") for s in sigs)),
        "ids": ";".join(f"{k}:{v}" for k, v in (p.get("ids") or {}).items()),
        "hop_depth": p.get("hop_depth", 0),
        "merge_confidence": p.get("merge_confidence", "low"),
        "affiliation_source": p.get("affiliation_source") or f"evidence {newest.get('date','')}",
        "last_verified": date,
        "notes": p.get("notes", ""),
    }

def sort_key(r: dict) -> tuple:
    rank = {"high": 0, "medium": 1, "low": 2, "ambiguous": 3}
    return (-len(r["channels_hit"].split(";")) if r["channels_hit"] else 0, rank.get(r["merge_confidence"], 9), r["name"])

def write_md(rows: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(COLUMNS) + " |\n|" + "---|" * len(COLUMNS) + "\n")
        for r in rows:
            f.write("| " + " | ".join(str(r[c]).replace("|", "/") for c in COLUMNS) + " |\n")

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("persons"); p.add_argument("--domain", default=""); p.add_argument("--out", default="roster")
    p.add_argument("--date", default=datetime.date.today().isoformat())
    a = p.parse_args()
    try:
        persons = [json.loads(l) for l in open(a.persons, encoding="utf-8") if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"bad input: {exc}")
    rows = sorted((row_for(x, a.domain, a.date) for x in persons), key=sort_key)
    rows = [r for r in rows if r["evidence_urls"]]  # no evidence, no row
    with open(f"{a.out}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
    write_md(rows, f"{a.out}.md")
    print(f"wrote {len(rows)} rows → {a.out}.csv, {a.out}.md", file=sys.stderr)

if __name__ == "__main__":
    main()
