---
name: talent-scout
description: Find people in a user-chosen technical domain (default region Europe = EU27 + UK + CH) across many public signal channels (top-venue paper awards, national prizes, EU funding, competitions, startups, industry labs, open source) and output a sourced, table-shaped roster with per-person evidence. Use when asked to "find talent / researchers / engineers / teams in <domain>", build a candidate list, or map who is doing notable work in a field. Works with web search + page reading alone; bundled scripts are optional accelerators.
---

# Talent Scout

Produces a **roster table** (CSV + Markdown) of people in a domain, every row backed by URLs.
It is a finding tool. It does not judge whether anyone would change jobs, and it never writes
recruiting advice. Career stage / role is recorded as a data field only.

## Run in five stages (read the linked file when you reach the stage)

| # | Stage | Read | Output |
|---|-------|------|--------|
| 0 | Probe environment, fix scope | `references/00-environment.md` | `run.meta.json` |
| 1 | Derive the domain map (venues, awards, competitions, funding codes, labs, keywords) **from universal sources**, not by hand | `references/10-domain-discovery.md` | `domain-map.yaml` |
| 2 | Sweep channels → signals | `references/channels/README.md` then one file per channel | `signals.jsonl` |
| 3 | Hop from orgs / works / teams / companies to **people**; snowball one hop | `references/30-hops.md` | more `signals.jsonl` |
| 4 | Merge same-person signals, score confidence | `references/40-entity-resolution.md` | `persons.jsonl` |
| 5 | Emit the roster table + per-person evidence | `references/50-output.md` | `roster.csv`, `roster.md` |

Rules that apply at every stage are in `references/60-scope-and-ethics.md`. Read it once at start.

## Non-negotiables

- A row with no evidence URL does not enter the table.
- Unresolved same-name cases stay as separate rows marked `ambiguous`; never merge on name alone.
- Each channel has a page budget (set in `run.meta.json`); stop at budget, record what was skipped.
- Prefer keyless structured sources (OpenAlex, ORCID, DBLP, OpenReview, CORDIS CSV, ERC PDFs,
  GitHub anonymous API, EIC PDFs) over search-engine reading. Fall back to search only where no
  structured source exists (award pages, competition results, lab team pages).
- Two human checkpoints: after stage 1 (show the domain map, 1-minute review) and after stage 2
  (show the raw candidate count before spending budget on hops and enrichment).

## Reuse across domains

The procedure is domain-agnostic. A domain map is **derived** at stage 1 and cached under
`domain-cache/<slug>.yaml`; a cached map is a starting point to refresh, never a requirement.
Country lists, ERC panel codes, EuroSciVoc paths and national prize registries are universal
and live in `assets/`.

## Optional scripts (`scripts/`, Python 3 standard library only)

Use when an interpreter is available; every script has a manual equivalent described in the
stage file. See `scripts/README.md`.
