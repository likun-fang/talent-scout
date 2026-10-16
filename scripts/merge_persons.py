#!/usr/bin/env python3
"""Merge talent-scout signals into persons using the key ladder (see references/40-entity-resolution.md).

  merge_persons.py signals.jsonl > persons.jsonl

Strong keys: ids.orcid, ids.openalex, ids.dblp, ids.openreview, ids.github, ids.gepris, ids.snsf.
Weak key: normalised name + a matching institution or a specific multiword institution prefix.
Name-only matches are NEVER merged; they stay separate with merge_confidence=ambiguous.
Standard library only; no mutation of input records.
"""
from __future__ import annotations
import argparse, datetime, json, re, sys, unicodedata
from current_affiliation import classify_role, region_codes
from person_fields import assign_groups, same_institution, topics_for
from collections import defaultdict
from identity_quality import (conflicts, id_values, normalize_id, load_identity_reviews,
                              validate_identity_reviews, reviewed_keys, review_for, name_key,
                              partition_reviewed_signals)

STRONG = ("orcid", "openalex", "dblp", "openreview", "github", "gepris", "snsf")

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return s.replace("-", " ").replace(".", "").strip()

def inst_tokens(s: str) -> set[str]:
    # Affiliation lists arrive joined by ";" or in brackets; a token must not keep the punctuation.
    return {w for w in re.findall(r"\w+", norm(s)) if len(w) > 4}

def strong_keys(sig: dict) -> list[str]:
    ids = sig.get("ids") or {}
    return [f"{k}:{normalize_id(k, ids[k])}" for k in STRONG if normalize_id(k, ids.get(k))]

def weak_match(a: dict, b: dict, identity_reviews=()) -> bool:
    if norm(a.get("name_raw", "")) != norm(b.get("name_raw", "")):
        return False
    left, right = a.get("affiliation_raw", ""), b.get("affiliation_raw", "")
    # A specific prefix handles e.g. "TUM Klinikum" / "TUM Klinikum Rechts der Isar";
    # a shared generic word such as "University" is never sufficient.
    generic = {'university', 'institute', 'research', 'department', 'school', 'hospital', 'college'}
    prefix = any(len(x.split()) >= 2 and x.split()[0] not in generic and
                 (y == x or y.startswith(x + ' '))
                 for atext, btext in [(left, right), (right, left)]
                 for x in [norm(p).strip() for p in atext.split(';') if p.strip()]
                 for y in [norm(p).strip() for p in btext.split(';') if p.strip()])
    return not conflicts([a, b], include_signals=False, reviews=identity_reviews) and (same_institution(left, right) or prefix)

def cluster(signals: list[dict], identity_reviews=None) -> list[list[dict]]:
    reviews = load_identity_reviews() if identity_reviews is None else validate_identity_reviews(identity_reviews)
    parent: dict[int, int] = {}
    members = {i: [s] for i, s in enumerate(signals)}
    def find(i: int) -> int:
        while parent.setdefault(i, i) != i:
            i = parent[i]
        return i
    def union(i: int, j: int) -> None:
        left, right = find(i), find(j)
        if left == right or conflicts(members[left] + members[right], include_signals=False, reviews=reviews):
            return
        parent[left] = right
        members[right] += members.pop(left)
    by_key: dict[str, int] = {}
    for i, s in enumerate(signals):
        for k in reviewed_keys(s, reviews):
            if k in by_key:
                union(i, by_key[k])
            else:
                by_key[k] = i
    by_name: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(signals):
        by_name[norm(s.get("name_raw", ""))].append(i)
    weak_edges = set()
    for idxs in by_name.values():
        for a in idxs:
            for b in idxs:
                if a < b and weak_match(signals[a], signals[b], reviews):
                    left, right = find(a), find(b)
                    if left != right:
                        weak_edges.add(tuple(sorted((left, right))))
    neighbors = defaultdict(set)
    for left, right in weak_edges:
        neighbors[left].add(right)
        neighbors[right].add(left)
    # An ID-less name/institution bridge must not attach to whichever conflicting
    # candidate happens to appear first in the input.
    ambiguous_roots = {root for root, adjacent in neighbors.items()
                       if conflicts([s for i in {root, *adjacent} for s in members[i]],
                                    include_signals=False, reviews=reviews)}
    for left, right in sorted(weak_edges):
        if left not in ambiguous_roots and right not in ambiguous_roots:
            union(left, right)
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

def to_person(group: list[dict], ambiguous_names: set[str], run_year: int | None = None, identity_reviews=None) -> dict:
    from publication_signals import normalize_authorship
    group = [normalize_authorship(signal) for signal in group]
    reviews = load_identity_reviews() if identity_reviews is None else validate_identity_reviews(identity_reviews)
    name = max((s["name_raw"] for s in group), key=len)
    values = id_values(group, include_signals=False, reviews=reviews)
    ids = {k: next(iter(v)) for k, v in values.items() if len(v) == 1}
    incompatible = conflicts(group, include_signals=False, reviews=reviews)
    conf = confidence(group)
    if conf == "low" and norm(name) in ambiguous_names:
        conf = "ambiguous"
    person = {"name": name, "signals": group, "ids": ids,
            "channels_hit": sorted({s["channel"] for s in group}),
            "hop_depth": min(s.get("hop_depth", 0) for s in group),
            "merge_confidence": conf, "topics": topics_for(group), "group": "", "last_verified": ""}
    binding = review_for(person, reviews)
    if binding and name_key(name) in map(name_key, binding['names']):
        # Resolve approved bindings before provider enrichment, so unreviewed IDs
        # and rejected-source affiliations cannot determine a current profile.
        safe, held, corrections = partition_reviewed_signals(person, binding)
        person.update(ids={k: normalize_id(k, v) for k, v in binding['canonical_ids'].items()},
                      signals=safe, topics=topics_for(safe), channels_hit=sorted({s['channel'] for s in safe}))
        if held:
            person['identity_held_sources'] = held
        if corrections:
            person['identity_binding_corrections'] = corrections
        if held or corrections:
            person['identity_sources_changed'] = True
        incompatible = conflicts([person], reviews=reviews)
    if incompatible:
        person.update(identity_status='conflict', identity_conflicts=incompatible, merge_confidence='ambiguous')
    return {**person, **classify_role(person, run_year or datetime.date.today().year)}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('signals')
    parser.add_argument('--date', type=datetime.date.fromisoformat, default=datetime.date.today())
    parser.add_argument('--region-core', default='DE+CH')
    args = parser.parse_args()
    try:
        with open(args.signals, encoding="utf-8") as source:
            signals = [json.loads(l) for l in source if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"bad input: {exc}")
    persons_sigs = [s for s in signals if s.get("kind") == "person"]
    groups = cluster(persons_sigs)
    name_counts: dict[str, int] = defaultdict(int)
    for g in groups:
        name_counts[norm(max((s["name_raw"] for s in g), key=len))] += 1
    ambiguous = {n for n, c in name_counts.items() if c > 1}
    from table_export import tier_for
    persons = assign_groups([to_person(g, ambiguous, args.date.year) for g in groups])
    for person in persons:
        print(json.dumps({**person, 'tier': tier_for(person, region_codes(args.region_core))}, ensure_ascii=False))
    print(f"{len(persons_sigs)} person signals → {len(groups)} persons ({len(ambiguous)} ambiguous names)", file=sys.stderr)

if __name__ == "__main__":
    main()
