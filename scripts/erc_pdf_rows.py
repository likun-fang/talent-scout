#!/usr/bin/env python3
"""Turn the TEXT of an ERC results PDF into talent-scout signals.

The PDF tables have columns: Last name, First name, Host institution, Host institution local name,
Host country, Acronym, Title, Panel. Extract text first (any PDF-to-text your platform offers),
then:

  erc_pdf_rows.py erc-2025-stg.txt --call stg --year 2025 --panels PE6,PE7 \
      --keywords robot,manipulation,humanoid --url https://erc.europa.eu/.../erc-2025-stg-results-all-domains.pdf

Writes signals JSONL to stdout. Rows are detected by a trailing panel code (PE6, LS3, SH2 ...);
the country is the 2-letter token before the acronym. Standard library only.
"""
from __future__ import annotations
import argparse, json, re, sys

ROW_END = re.compile(r"\s(?P<panel>(?:PE|LS|SH)\d{1,2})\s*$")
COUNTRY = re.compile(r"\s(?P<cc>[A-Z]{2})\s(?P<acr>\S+)\s(?P<title>.+)$")

def parse_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    buf = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("ERC ", "Host institution refers", "Last name", "Page ")):
            continue
        buf = f"{buf} {line}".strip()
        m = ROW_END.search(buf)
        if not m:
            continue
        body = buf[: m.start()]
        c = COUNTRY.search(body)
        if c:
            head = body[: c.start()].split()
            rows.append({"last": head[0] if head else "", "first": " ".join(head[1:3]) if len(head) > 1 else "",
                         "host_raw": " ".join(head[3:]), "country": c.group("cc"), "acronym": c.group("acr"),
                         "title": c.group("title").strip(), "panel": m.group("panel")})
        buf = ""
    return rows

def to_signal(row: dict, call: str, year: int, url: str) -> dict:
    return {"kind": "person", "name_raw": f"{row['first']} {row['last'].title()}".strip(),
            "affiliation_raw": row["host_raw"], "country": row["country"], "role": "pi",
            "channel": "funding-eu", "signal_type": f"erc_{call}", "strength": "high", "date": str(year),
            "evidence_url": url, "snippet": f"{row['acronym']}: {row['title']} ({row['panel']})", "hop_depth": 0}

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("textfile"); p.add_argument("--call", required=True, choices=["stg", "cog", "adg", "syg", "poc"])
    p.add_argument("--year", type=int, required=True); p.add_argument("--url", required=True)
    p.add_argument("--panels", default=""); p.add_argument("--keywords", default="")
    a = p.parse_args()
    try:
        text = open(a.textfile, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        raise SystemExit(f"cannot read {a.textfile}: {exc}")
    panels = {x.strip().upper() for x in a.panels.split(",") if x.strip()}
    kws = [k.strip().lower() for k in a.keywords.split(",") if k.strip()]
    rows = parse_rows(text)
    kept = [r for r in rows if (not panels or r["panel"] in panels)
            and (not kws or any(k in r["title"].lower() for k in kws))]
    for r in kept:
        print(json.dumps(to_signal(r, a.call, a.year, a.url), ensure_ascii=False))
    print(f"parsed {len(rows)} rows, kept {len(kept)}", file=sys.stderr)

if __name__ == "__main__":
    main()
