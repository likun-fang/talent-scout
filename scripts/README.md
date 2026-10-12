# Optional scripts (Python 3.9+, standard library by default)

OpenAlex calls honour `OPENALEX_API_KEY` (free key; without it OpenAlex allows roughly 100 calls/day).

| script | stage | input → output |
|--------|-------|----------------|
| `openalex_lookup.py` | 1, 3, 4 | `--topic "<phrase>"` → top 10 topics to choose from; `--topics T1,T2` → venues (repository source types dropped, name blacklist as supplement) / institutions / lead authors in region; `--title "<paper>"` → authors with institutions; `--author <id>` → record with ORCID |
| `visit_page.py` | final pass | public URL (or `--batch` file) → timestamped page text or LinkedIn excerpts, access status; optional Playwright rendering for JS-only lab pages |
| `current_affiliation.py` | 4 | `persons.jsonl` → same records with current affiliation from ORCID / OpenAlex / newest evidence, with the stale-ORCID override, role classification, topics, group and tier |
| `merge_persons.py` | 4 | `signals.jsonl` → `persons.jsonl` using the key ladder; emits role fields, topics, group and tier; never merges on name alone |
| `table_export.py` | 5 | `persons.jsonl` → region-filtered `roster.csv` + `roster.md` + `groups.csv` + `groups.md` (+ Coverage and evidence, `.out-of-region.json`, `.excluded-signals.json`), sorted by tier before `--max-rows` |

Date defaults: `openalex_lookup.py --topics` queries the 36 months ending on `--date` (default today);
`--since YYYY` widens the start to that January 1. `table_export.py` applies the same 36-month window before
sorting (`--window-months` to override): a person needs one signal inside it, ranking uses those, and older or
undated signals stay in the row as evidence and are listed in `.excluded-signals.json`. Use the same
`--date YYYY-MM-DD` for lookups, merging, affiliation enrichment and export. It controls the publication
year inference as well as the activity window; it does not fill `last_verified`.

All scripts read/write UTF-8, exit non-zero on malformed input, and print a one-line summary to stderr.
`table_export.py` writes CSV as UTF-8 with a BOM (`utf-8-sig`) so Windows Excel reads accented names correctly;
`groups.csv` also uses a BOM. Markdown and JSON output remain plain UTF-8 without a BOM.
If no interpreter is available, each stage file describes the manual equivalent.

## Page reader for the final pass

Static HTML/text (no extra dependencies):

```sh
python3 scripts/visit_page.py 'https://example.org/person' --out runs/demo/pages/person.json
```

One serial LinkedIn batch for the cut table, 5 s apart, stopping at the first authwall / 999 / 429:

```sh
python3 scripts/visit_page.py --batch runs/demo/linkedin-urls.txt --out-dir runs/demo/pages/linkedin/ --delay 5
```

LinkedIn records keep only the headline and the Experience / Education / Publications / Projects excerpts
(`sections`), plus URL, status and `retrieved_at`; page text and links are dropped unless `--full-text` is given.
A refused page is recorded with its status and exit code 2, never treated as a successful lookup.
Each section has a boolean in `section_truncated`, keyed by the same section name as `sections`;
this preserves the existing lists of lines in `sections`. A line cap or page/byte cap before a section's
end marks it true; reaching the next heading or public-profile boundary marks it false. A readable
public profile may still be incomplete even when this flag is false.

For JavaScript-only lab or company pages, install the optional browser dependency in a project-local environment:

```sh
python3 -m venv .venv-browser
.venv-browser/bin/python -m pip install -r scripts/requirements-browser.txt
.venv-browser/bin/python scripts/visit_page.py 'https://lab.example.org/team' --browser --channel chrome --out runs/demo/pages/team.json
```

`--channel chrome` uses installed Google Chrome in a new, unauthenticated context; or run
`.venv-browser/bin/python -m playwright install chromium` and omit `--channel`. The reader refuses LinkedIn URLs
in browser mode because a headless browser lands on the authwall. It never loads browser cookies, logs in,
clicks buttons or submits forms, and it rejects localhost, private and link-local addresses.

JSON includes `status`, `requested_url`, `final_url`, `retrieved_at`, `title`, `text` (or `sections`), `links`,
`http_status`, `truncated` and `role_verified: false`. Access-status detection is heuristic; read the content
before citing it. Use `--timeout`, `--wait-ms` and `--max-chars` to bound a read.
See `references/45-web-verification.md` for the order of sources and what to record.

## Roles, regions and group export

All generated artifacts belong under `RUN_DIR`; invoke script resources under `SKILL_ROOT`.
The scripts do not update repository `domain-cache/` or `run.meta.json`. Pass metadata's `region_core`,
`region_extended` and run date explicitly; `--region` is the existing extended-region option,
and export/enrichment also accept `--region-extended`.

```sh
python3 "$SKILL_ROOT/scripts/merge_persons.py" "$RUN_DIR/signals.jsonl" --date 2026-10-12 --region-core DE+CH > "$RUN_DIR/persons.jsonl"
python3 "$SKILL_ROOT/scripts/current_affiliation.py" "$RUN_DIR/persons.jsonl" --date 2026-10-12 --region-core DE+CH --region-extended EU27+UK+CH --cache-dir "$RUN_DIR/cache/affiliation" > "$RUN_DIR/persons.enriched.jsonl"
python3 "$SKILL_ROOT/scripts/table_export.py" "$RUN_DIR/persons.enriched.jsonl" --date 2026-10-12 --region-core DE+CH --region-extended EU27+UK+CH --max-rows 50 --coverage-dir "$RUN_DIR/signals" --out "$RUN_DIR/roster"
```

Merging is offline. Enrichment looks up current ORCID role titles and OpenAlex institution types;
classification itself is a pure function in `current_affiliation.py`. Explicit titles take precedence
over funding PI identity, then company type/name, then publication-year and authorship inference.
`role_evidence` records the rule, verbatim excerpt and URL, including the German research-assistant caveat.
See the exact mapping and the optional `linkedin_headline`/`linkedin_url` final-pass input adapter in
`references/40-entity-resolution.md`. Provider enrichment never claims a final-pass verification.
`last_verified` remains empty unless a final-pass reader explicitly supplied an actual read date.

The last five roster columns are `role_class, role_confidence, tier, topics, group`. Person topics are
exactly deduplicated, capped at five, and serialized with `;`. The evidence appendix carries `role_evidence`.
Core professors are tier 1; core researchers/doctoral students tier 2; doctoral students in extended
minus core tier 3; other in-region people tier 4. Sort by tier, eligible channel count, strongest signal,
newest date, name; apply the row cap afterward. The 36-month window remains unchanged.

Group inference requires a unique leader linked through the same institution and parent or paper last
author; unresolved people stay ungrouped. `groups.csv` and `groups.md` aggregate the cut roster and sort
by minimum tier, descending member count, PI name; `(ungrouped)` comes last. They include member roles,
top three recent outputs, funding evidence, open-source links and Coverage counts. `active_funding`
lists retained funding signals; absent award end dates, it does not establish that a grant is still active.
See `references/50-output.md` for exact columns and aggregation rules.

Roster Coverage distinguishes window-excluded evidence retained on final table people from all signals
belonging to omitted people. The `.excluded-signals.json` audit contains window-excluded signals from
both sets and therefore has a different total from retained background evidence.

Tests use synthetic fixtures, standard-library `unittest` and mocked lookups; they do not contact providers:

```sh
python3 -m unittest discover -s tests
```
