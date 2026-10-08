#!/usr/bin/env python3
"""Write roster.csv and roster.md from persons.jsonl with the fixed talent-scout columns.

  table_export.py persons.jsonl [--domain "<phrase>"] [--date YYYY-MM-DD] [--out roster]
                  [--region EU27+UK+CH] [--max-rows N] [--coverage-dir signals/]
Rows whose country is outside the region go to <out>.out-of-region.json. With --max-rows the table is cut
after sorting and the Coverage block says how many rows were cut. --coverage-dir appends every
*.coverage.md it finds to roster.md. Standard library only.
Ranking uses eligible channel count, strongest signal, newest signal date, then name.
"""
from __future__ import annotations
import argparse, csv, datetime, glob, json, os, sys

REGIONS = {
    "EU27": ["AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"],
    "UK": ["GB"], "CH": ["CH"], "EEA": ["IS","LI","NO"],
}

def region_codes(spec: str) -> set[str]:
    return {c for part in spec.split("+") for c in REGIONS.get(part.strip().upper(), [])}

COLUMNS = ["name", "current_affiliation", "country", "role", "domain", "channels_hit", "signals",
           "evidence_urls", "ids", "hop_depth", "merge_confidence", "affiliation_source", "last_verified", "notes",
           "fit", "first_pub_year", "latest_role", "homepage", "ranked_channels"]

STRENGTH = {"high": 3, "medium": 2, "low": 1}

def signal_date(signal: dict) -> datetime.date:
    value = (signal.get("date") or "")[:10]
    value += "-01-01" if len(value) == 4 else "-01" if len(value) == 7 else ""
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return datetime.date.min

def ranked_channels(p: dict) -> int:
    return len({s["channel"] for s in p.get("signals", []) if s.get("channel") and
                (s.get("hop_depth", 0) == 0 or s.get("strength") in {"high", "medium"})})

def row_for(p: dict, domain: str, date: str) -> dict:
    sigs = p.get("signals", [])
    newest = max(sigs, key=signal_date, default={})
    fits = {s["fit"] for s in sigs if s.get("fit")}
    fit = "" if not fits else "core" if fits == {"core"} else "adjacent" if fits == {"adjacent"} else "mixed"
    roles = [s.get("role") for s in sigs if s.get("role") and s.get("role") != "unknown"]
    role = max(set(roles), key=roles.count) if roles else "unknown"
    return {
        "name": p.get("name", ""),
        "current_affiliation": p.get("current_affiliation") or newest.get("affiliation_raw", ""),
        "country": p.get("country") or newest.get("country", ""),
        "role": role,
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
        "fit": fit,
        "first_pub_year": p.get("first_pub_year", ""),
        "latest_role": newest.get("role") or "unknown",
        "homepage": next((s["homepage"] for s in sigs if s.get("homepage")), ""),
        "ranked_channels": ranked_channels(p),
    }

def sort_key(p: dict) -> tuple:
    sigs = p.get("signals", [])
    strongest = max((STRENGTH.get(s.get("strength"), 0) for s in sigs), default=0)
    newest = max((signal_date(s) for s in sigs), default=datetime.date.min)
    return (-ranked_channels(p), -strongest, -newest.toordinal(), p.get("name", ""))

def write_md(rows: list[dict], path: str, coverage: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(COLUMNS) + " |\n|" + "---|" * len(COLUMNS) + "\n")
        for r in rows:
            f.write("| " + " | ".join(str(r[c]).replace("|", "/") for c in COLUMNS) + " |\n")
        f.write("\n## Coverage\n\n" + coverage)

def coverage_text(kept: int, cut: int, out_of_region: int, cov_dir: str | None) -> str:
    lines = [f"- rows in table: {kept}", f"- rows cut at --max-rows: {cut}", f"- persons outside region (see .out-of-region.json): {out_of_region}", ""]
    for path in sorted(glob.glob(os.path.join(cov_dir, "*.coverage.md"))) if cov_dir else []:
        lines.append(f"### {os.path.basename(path)}\n")
        lines.append(open(path, encoding="utf-8").read().strip() + "\n")
    return "\n".join(lines)

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("persons"); p.add_argument("--domain", default=""); p.add_argument("--out", default="roster")
    p.add_argument("--date", default=datetime.date.today().isoformat())
    p.add_argument("--region", default="EU27+UK+CH"); p.add_argument("--max-rows", type=int, default=0)
    p.add_argument("--coverage-dir", default=None)
    a = p.parse_args()
    try:
        persons = [json.loads(l) for l in open(a.persons, encoding="utf-8") if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"bad input: {exc}")
    codes = region_codes(a.region)
    all_rows = [row_for(x, a.domain, a.date) for x in sorted(persons, key=sort_key)]
    all_rows = [r for r in all_rows if r["evidence_urls"]]  # a row carries evidence or it is not a row
    in_region = [r for r in all_rows if r["country"] in codes]
    outside = [r for r in all_rows if r["country"] not in codes]
    rows = in_region[: a.max_rows] if a.max_rows else in_region
    cut = len(in_region) - len(rows)
    with open(f"{a.out}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
    with open(f"{a.out}.out-of-region.json", "w", encoding="utf-8") as f:
        json.dump([{k: r[k] for k in ("name", "current_affiliation", "country", "affiliation_source")} for r in outside], f, ensure_ascii=False, indent=1)
    write_md(rows, f"{a.out}.md", coverage_text(len(rows), cut, len(outside), a.coverage_dir))
    print(f"wrote {len(rows)} rows ({cut} cut, {len(outside)} outside region) → {a.out}.csv, {a.out}.md", file=sys.stderr)

if __name__ == "__main__":
    main()
