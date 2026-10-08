#!/usr/bin/env python3
"""Merge talent-scout signals into persons using the key ladder (see references/40-entity-resolution.md).

  merge_persons.py signals.jsonl > persons.jsonl

Strong keys: ids.orcid, ids.openalex, ids.dblp, ids.openreview, ids.github.
Weak key: normalised name + a shared institution token (a word longer than 4 chars common to both
affiliation strings, e.g. "Hugging Face, Paris" and "Hugging Face / Sorbonne" share "hugging").
Name-only matches are NEVER merged; they stay separate with merge_confidence=ambiguous.
Standard library only; no mutation of input records.
"""
from __future__ import annotations
import json, sys, unicodedata
from collections import defaultdict

STRONG = ("orcid", "openalex", "dblp", "openreview", "github")

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return s.replace("-", " ").replace(".", "").strip()

def inst_tokens(s: str) -> set[str]:
    return {w for w in norm(s).replace(",", " ").replace("/", " ").split() if len(w) > 4}

def strong_keys(sig: dict) -> list[str]:
    ids = sig.get("ids") or {}
    return [f"{k}:{ids[k]}" for k in STRONG if ids.get(k)]

def weak_match(a: dict, b: dict) -> bool:
    if norm(a.get("name_raw", "")) != norm(b.get("name_raw", "")):
        return False
    return bool(inst_tokens(a.get("affiliation_raw", "")) & inst_tokens(b.get("affiliation_raw", "")))

def cluster(signals: list[dict]) -> list[list[dict]]:
    parent: dict[int, int] = {}
    def find(i: int) -> int:
        while parent.setdefault(i, i) != i:
            i = parent[i]
        return i
    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)
    by_key: dict[str, int] = {}
    for i, s in enumerate(signals):
        for k in strong_keys(s):
            if k in by_key:
                union(i, by_key[k])
            else:
                by_key[k] = i
    by_name: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(signals):
        by_name[norm(s.get("name_raw", ""))].append(i)
    for idxs in by_name.values():
        for a in idxs:
            for b in idxs:
                if a < b and weak_match(signals[a], signals[b]):
                    union(a, b)
    groups: dict[int, list[dict]] = defaultdict(list)
    for i, s in enumerate(signals):
        groups[find(i)].append(s)
    return list(groups.values())

def confidence(group: list[dict]) -> str:
    if any(strong_keys(s) for s in group):
        return "high"
    if len(group) > 1:
        return "medium"
    return "low"

def to_person(group: list[dict], ambiguous_names: set[str]) -> dict:
    name = max((s["name_raw"] for s in group), key=len)
    ids: dict[str, str] = {}
    for s in group:
        ids = {**ids, **(s.get("ids") or {})}
    conf = confidence(group)
    if conf == "low" and norm(name) in ambiguous_names:
        conf = "ambiguous"
    return {"name": name, "signals": group, "ids": ids,
            "channels_hit": sorted({s["channel"] for s in group}),
            "hop_depth": min(s.get("hop_depth", 0) for s in group),
            "merge_confidence": conf}

def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    try:
        signals = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"bad input: {exc}")
    persons_sigs = [s for s in signals if s.get("kind") == "person"]
    groups = cluster(persons_sigs)
    name_counts: dict[str, int] = defaultdict(int)
    for g in groups:
        name_counts[norm(max((s["name_raw"] for s in g), key=len))] += 1
    ambiguous = {n for n, c in name_counts.items() if c > 1}
    for g in groups:
        print(json.dumps(to_person(g, ambiguous), ensure_ascii=False))
    print(f"{len(persons_sigs)} person signals → {len(groups)} persons ({len(ambiguous)} ambiguous names)", file=sys.stderr)

if __name__ == "__main__":
    main()
