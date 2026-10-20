---
name: talent-scout
description: Build a public, correctable map of the research groups of a technical domain in Europe (EU27 + UK + CH + NO), group by group with PI, institution, homepage and named members, from the public academic record; no ranking, no LinkedIn.
---

# Talent Scout

Deliverable: `groups.json`, one record per research group with its PI, institution, homepage, named members and
evidence URLs, and the map and about page written from it (`references/50-output.md`). `roster.csv`, `roster.md`,
`groups.csv` and `groups.md` are working tables of the run, with a Coverage block saying what was read and what was
skipped; they stay in the run directory. It records roles and groups as data taken from public pages and makes no
judgement about anyone.

Read `references/60-scope-and-ethics.md` once before stage 0.

## Stages

Each stage names the file to read when you reach it and the condition that ends it.

| # | Stage | Read | Done when |
|---|-------|------|-----------|
| 0 | Probe environment, fix scope, ask once for the OpenAlex key | `references/00-environment.md` | `run.meta.json` written with env (OpenAlex keyed, or keyless with the user's answer recorded), `region_core` + `region_extended`, window, channels, page budgets, `run_dir`, `stage_status` |
| 1 | Derive the domain map from the field's pack and universal sources | `references/15-domain-pack.md`, `references/10-domain-discovery.md` | `domain-map.yaml` written with its run copy under `domain-cache/`, shown to the user in one screen, and the user has replied |
| 2 | Sweep channels into signals, hopping to people inside each channel | `references/channels/README.md`, then one file per channel in the run; hop rules in `references/30-hops.md` | every channel in `run.meta.json` has either reached its page budget or exhausted its sources; `signals/<channel>.jsonl` and `signals/<channel>.coverage.md` exist for each |
| 3 | Close the hop gaps | `references/30-hops.md` | every non-person signal across channels has produced person signals or a `roster not public` note; `signals.jsonl` is the concatenation |
| 4 | Merge signals into persons, then enrich | `references/40-entity-resolution.md` | `persons.jsonl` written by `merge_persons.py` **and passed through `current_affiliation.py`** (ORCID title and employment, OpenAlex institution and first publication year); each person has a strong key, or a weak key with same institution, or is marked `ambiguous`; each carries `role_class`, `role_evidence`, `role_confidence`, `tier`, `topics`, `group` |
| 5 | Emit the roster and the group view | `references/50-output.md` | `roster.csv`, `roster.md`, `groups.csv` and `groups.md` written with the fixed columns, sorted by tier, uncapped unless the user set `target_rows`, with the Coverage block |

Two moments to stop for the user: after stage 1 (the domain map and the chosen OpenAlex topics, one screen) and after
stage 2 (the raw candidate count, before budget goes into enrichment). Show the screen, stop, and wait for the user's
reply before the next stage.

The tier in stages 4 and 5 is a sort order of the working table only and never reaches the map.

Channels are independent: run them as parallel subagents sharing one brief (`assets/channel-brief.template.md`),
each doing its own hops and writing its own coverage note. A first real run (embodied AI, 2026-10-08) did this
with six agents and produced 845 signals, 521 in-region people; its lessons are in `notes/runs/`.

## Working rules

- Paths: skill files (`references/`, `assets/`, `scripts/`, `domain-cache/`) are relative to `SKILL_ROOT`, the
  directory holding this file; every artefact of a run is written under `RUN_DIR` (`run_dir` in `run.meta.json`), and
  `SKILL_ROOT/domain-cache/` changes only when the maintainer confirms by hand.
- Take structured sources first: OpenAlex (keyless until a 429, then a free key), ORCID, the CORDIS search API, ERC
  results PDFs, the DFG GEPRIS backend, the SNSF open datasets, bare git clones of anchor repos, EIC selected-company
  PDFs. Expect OpenReview, the GitHub REST API and DBLP to be blocked or rate-limited from agent sandboxes; each
  channel file names the fallback. Reach for web search where no structured source exists: award pages, competition
  results, lab team pages.
- The window is the 36 months ending on the run date, for every channel including funding. Follow the date rules in
  `references/channels/README.md`: an older or undated signal stays in the row as evidence but cannot qualify a person
  or lift its rank.
- Carry the evidence URL, a verbatim snippet, the verbatim `role_title` and the `topics` with every signal from the
  moment you find it.
- Keep two people with the same name as two rows marked `ambiguous` until a strong key or a shared institution joins them.
- Stop a channel at its page budget (40 fetch attempts, failures included) and write the skipped items into the
  channel's coverage note.
- Record evidence URLs that will still resolve next year: year-stamped pages (`/2024/program/awards/`), PDFs,
  or a web.archive.org capture when the live page is the only source.

## Resuming a run

The run directory is the handoff. Read `RUN_DIR/run.meta.json` and continue from the first stage in `stage_status`
that is not `"done"`. A stage marked `"running"` was interrupted or is waiting for the user: re-read its output and its
stage reference, and for stages 1 and 2 show the summary again and wait. An output file without a `"done"` status
does not count as a finished stage.

## Domain reuse

The procedure is domain-agnostic; a field is one pack (`references/15-domain-pack.md`): its domain map
`domain-cache/<slug>.yaml`, its facets and its known groups, checked by `scripts/check_domain_pack.py`. A run starts
from the pack and refreshes it, with `derived_on` as the signal for which fields to re-check; the pack changes only
through a pull request. Region codes, ERC panels, EuroSciVoc paths and the national prize registry are universal and
live in `assets/`.

## Final pass: current roles and affiliations, by group

After the stage 5 export, and only then, check current roles and affiliations. Work group by group, tier 1 first:
read the PI's team page once, which verifies the PI and lists the current members, then individual pages
(`references/45-web-verification.md`); LinkedIn is not read (`references/60-scope-and-ethics.md`). The budget counts pages, so
one team page covers a whole group. The optional `scripts/visit_page.py` records page excerpts and access status;
reading a page does not itself verify a role. Write what the page says into `final_pass_title`,
`final_pass_affiliation` and `final_pass_country`, then re-export: a corrected country or role changes the tier,
but the pass adds nobody to the table. Set `stage_status["final_pass"]` when done.
To read the result as a map, run `scripts/talent_map.py` on the same enriched `persons.jsonl` after the re-export:
one `talent-map.html` in `RUN_DIR` with every institution, group, person and evidence link, filterable by the
research-direction tags of `RUN_DIR/facets.json` from stage 1 (`scripts/README.md`).

## Scripts

`scripts/` holds optional Python 3 standard-library helpers for OpenAlex lookups, merging, table export and
the talent map, each with a manual equivalent in its stage file, plus a page reader for the final pass. All run on the standard
library; the reader's browser mode for JavaScript-only lab pages is the one optional Playwright dependency.
See `scripts/README.md`.
