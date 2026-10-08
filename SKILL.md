---
name: talent-scout
description: Find the people behind notable work in a technical domain, defaulting to Europe (EU27 + UK + CH), and deliver a sourced roster table. Use when asked to find talent, researchers, engineers or teams in a field, to list who is doing notable work in a domain, or to build a candidate roster from public signals such as paper awards, prizes, EU funding, competitions, startups and open source.
---

# Talent Scout

Deliverable: `roster.csv` + `roster.md`, one row per person, every row carrying at least one evidence URL,
plus a Coverage block saying what was read and what was skipped. It is a finding tool: it records roles and
career stage as data and leaves judgements about hiring to the reader.

Read `references/60-scope-and-ethics.md` once before stage 0.

## Stages

Each stage names the file to read when you reach it and the condition that ends it.

| # | Stage | Read | Done when |
|---|-------|------|-----------|
| 0 | Probe environment, fix scope, get the OpenAlex key | `references/00-environment.md` | `run.meta.json` written with env, region, window, channels, page budgets; `OPENALEX_API_KEY` set |
| 1 | Derive the domain map from universal sources | `references/10-domain-discovery.md` | `domain-map.yaml` written, cached under `domain-cache/`, and shown to the user in one screen |
| 2 | Sweep channels into signals, hopping to people inside each channel | `references/channels/README.md`, then one file per channel in the run; hop rules in `references/30-hops.md` | every channel in `run.meta.json` has either reached its page budget or exhausted its sources; `signals/<channel>.jsonl` and `signals/<channel>.coverage.md` exist for each |
| 3 | Close the hop gaps | `references/30-hops.md` | every non-person signal across channels has produced person signals or a `roster not public` note; `signals.jsonl` is the concatenation |
| 4 | Merge signals into persons | `references/40-entity-resolution.md` | `persons.jsonl` written; each person has a strong key, or a weak key with same institution, or is marked `ambiguous` |
| 5 | Emit the roster | `references/50-output.md` | `roster.csv` and `roster.md` written with the fixed columns, region-filtered, cut to `target_rows`, with the Coverage block |

Two moments to pause for the user: after stage 1 (the domain map and the chosen OpenAlex topics, one screen)
and after stage 2 (the raw candidate count, before budget goes into enrichment).

Channels are independent: run them as parallel subagents sharing one brief (`assets/channel-brief.template.md`),
each doing its own hops and writing its own coverage note. A first real run (embodied AI, 2026-10-08) did this
with six agents and produced 845 signals, 521 in-region people; its lessons are in `docs/runs/`.

## Working rules

- Take structured sources first: OpenAlex (key required in practice), ORCID, CORDIS search API, ERC results PDFs,
  bare git clones of anchor repos, EIC selected-company PDFs. Expect OpenReview, the GitHub REST API and DBLP to be
  blocked or rate-limited from agent sandboxes; each channel file names the fallback. Reach for web search where
  no structured source exists: award pages, competition results, lab team pages.
- Carry the evidence URL and a verbatim snippet with every signal from the moment you find it.
- Keep two people with the same name as two rows marked `ambiguous` until a strong key or a shared institution joins them.
- Stop a channel at its page budget and write the skipped items into the channel's coverage note.
- Record evidence URLs that will still resolve next year: year-stamped pages (`/2024/program/awards/`), PDFs,
  or a web.archive.org capture when the live page is the only source.

## Resuming a run

The run directory is the handoff. A new session continues from the last stage whose output file exists:
`run.meta.json` → `domain-map.yaml` → `signals.jsonl` → `persons.jsonl` → `roster.csv`. Re-read that file,
re-read the matching stage reference, continue.

## Domain reuse

The procedure is domain-agnostic; the domain map is derived at stage 1 and cached under
`domain-cache/<slug>.yaml`. A cached map is a starting point to refresh, with its `derived_on` date as the
signal for which fields to re-check. Region codes, ERC panels, EuroSciVoc paths and the national prize
registry are universal and live in `assets/`.

## Scripts

`scripts/` holds optional Python 3 standard-library helpers for OpenAlex lookups, merging and table export,
each with a manual equivalent in its stage file. See `scripts/README.md`.
