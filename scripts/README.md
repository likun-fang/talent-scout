# Optional scripts (Python 3.9+, standard library by default)

OpenAlex calls honour `OPENALEX_API_KEY` (free key; without it OpenAlex allows roughly 100 calls/day).

| script | stage | input → output |
|--------|-------|----------------|
| `openalex_lookup.py` | 1, 3, 4 | `--topic "<phrase>"` → top 10 topics to choose from; `--topics T1,T2` → venues (repository source types dropped, name blacklist as supplement) / institutions / lead authors in region; `--title "<paper>"` → authors with institutions; `--author <id>` → record with ORCID |
| `visit_page.py` | final pass | public URL (or `--batch` file) → timestamped page text or LinkedIn excerpts, access status; optional Playwright rendering for JS-only lab pages |
| `current_affiliation.py` | 4 | `persons.jsonl` → same records with current affiliation from ORCID / OpenAlex / newest evidence, with the stale-ORCID override, role classification, topics, group and tier |
| `merge_persons.py` | 4 | `signals.jsonl` → `persons.jsonl` using the key ladder; emits role fields, topics, group and tier; never merges on name alone |
| `table_export.py` | 5 | `persons.jsonl` → region-filtered `roster.csv` + `roster.md` + `groups.csv` + `groups.md` (+ Coverage and evidence, `.out-of-region.json`, `.excluded-signals.json`), sorted by tier before `--max-rows` |
| `talent_map.py` | 5 | the same `persons.jsonl` → one `talent-map.html`: a map of institutions with every group, person, signal and evidence link inline; same selection, tiers and groups as `table_export.py`; institutions placed from the manual table `assets/geo-overrides.json` (city level, with sources), then through ROR (cached in `cache/geo/`, `--offline` to reuse), country centroid when neither has a match; research-direction tags from `facets.json` (`--facets`) |

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

One serial LinkedIn batch for unresolved exported profiles, 5 s apart, stopping at the first authwall / 999 / 429:

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

Refused or empty pages climb a keyless ladder automatically (plain HTTP with a browser User-Agent → Wayback capture →
Jina Reader → local browser); `attempts` lists every step, `fetch_via` the one that worked, `--ladder http` turns it
off. A roster built client-side reads as a short "readable" shell: pass `--render` to go straight to the browser
(`--min-chars` raises the shell threshold instead); `--render` keeps the browser step even with `--ladder http`.
The browser step uses installed Google Chrome when present; `--channel chrome|msedge` picks the installed browser
for `--browser`, `--render` and the ladder alike. Bot-check interstitials (Cloudflare, Anubis, BunkerWeb, RISE,
OpenReview) are recorded as `challenge`, not as readable text, and a page that is only a cookie-consent wall is
`empty` (so the ladder climbs). A PDF roster is read through poppler's `pdftotext` when it is installed
(`brew install poppler` / `apt install poppler-utils`); without it the record says `unsupported_content`.

For JavaScript-only lab or company pages without Chrome, install the optional browser dependency in a project-local
environment:

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
python3 "$SKILL_ROOT/scripts/current_affiliation.py" "$RUN_DIR/persons.jsonl" --date 2026-10-12 --region-core DE+CH --region-extended EU27+UK+CH+NO --cache-dir "$RUN_DIR/cache/affiliation" > "$RUN_DIR/persons.enriched.jsonl"
python3 "$SKILL_ROOT/scripts/table_export.py" "$RUN_DIR/persons.enriched.jsonl" --date 2026-10-12 --region-core DE+CH --region-extended EU27+UK+CH+NO --max-rows 0 --coverage-dir "$RUN_DIR/signals" --out "$RUN_DIR/roster"
python3 "$SKILL_ROOT/scripts/talent_map.py" "$RUN_DIR/persons.enriched.jsonl" --date 2026-10-12 --domain "<phrase>" --region-core DE+CH --region-extended EU27+UK+CH+NO --out "$RUN_DIR/talent-map.html"
```

`talent_map.py` is for reading the result, not a deliverable column: open the HTML in a browser (Leaflet and the
map tiles load from the network; the data is inline). Rerun it after the final pass so the corrected affiliations
and `final_pass_*` fields appear. The page stays under `runs/`, which holds personal data and is not committed.
The embodied-AI facet example includes `robot-policy`: generating robot actions or action sequences from
observations/state and optional task instructions. It overlaps with VLA; imitation learning and RL describe
training methods, while a VLM or world model need not output actions. The facet id `policy` is retained for
compatibility, with the display label "research approach". Explicit robot-policy phrases (including diffusion
policy) enable the new tag; bare `policy`, `RL`, `flow matching` and `world model` do not enable it.
These are lexical discovery tags, not semantic verification: review the robot task and action-generation evidence
in the title/abstract/repository before accepting a lead. The embodied domain cache adds the same retrieval phrases.
Existing run-local `facets.json` files are not migrated automatically; copy the updated tag into the run's chosen
facets and regenerate its map when updating an existing run.

The page is bilingual (English / 中文 toggle, `?lang=zh` in a shared link). Each group and person card opens with
a sentence built from the record; `--summaries RUN_DIR/summaries.json` replaces it with written summaries,
`{"groups": {"<PI> @ <institution>": {"en": "...", "zh": "..."}}, "persons": {"<name>": {...}}}`, when a later
summarisation step has produced them. Research-direction tags come from `RUN_DIR/facets.json` (picked up by default
when it sits next to the persons file, or `--facets PATH`; format in `assets/facets.template.json`): per facet a list
of tags with keyword lists, matched as whole words: a tag applies when one keyword occurs in the person's or a signal's
topics, or two different keywords occur across the signal snippets and project / paper titles (one word in a snippet
is often incidental); a group carries its team and project members' tags with counts, not its coauthors'. The page
gets one filter per facet, tag chips on rows and cards, and the About tab lists the tag counts. A tag records that the words occur in the record, nothing more. Opened as a
local file, the public OpenStreetMap tile servers refuse the page (osm.wiki/blocked), so the default basemap is
Esri's keyless light-gray canvas.

Merging is offline. Enrichment looks up current ORCID role titles and OpenAlex institution types;
classification itself is a pure function in `current_affiliation.py`. Current company employer takes precedence over title mapping, except professorial titles (mixed headings remain
unknown); then use explicit titles, funding PI identity and publication-year/authorship inference. A dated final-pass
employer is high confidence; OpenAlex company type is medium confidence. Research institutes organised as a
GmbH (DFKI, Forschungszentrum Jülich, Fraunhofer, Helmholtz, Max Planck, Leibniz) are never industry. Company-name matches exclude
academic/healthcare terms unless GmbH/AG/Inc/Ltd is explicit; bare Meta/FAIR/Apple/Amazon and generic Labs
do not qualify. SA is case-sensitive and must end the affiliation or precede a comma.
`role_evidence` records the rule, verbatim excerpt and URL, including the German research-assistant caveat.
See the exact mapping and the optional `linkedin_headline`/`linkedin_url` final-pass input adapter in
`references/40-entity-resolution.md`. Provider enrichment never claims a final-pass verification.
`last_verified` remains empty unless a final-pass reader explicitly supplied an actual read date.

The last six roster columns are `role_class, role_confidence, tier, topics, group, role_evidence`; there are 25 columns total. Person topics are
exactly deduplicated, capped at five, and serialized with `;`. The evidence appendix carries both `role_evidence` and `group_evidence`; only role evidence is also a table column.
Core professors and group leaders are tier 1; professors and group leaders in extended minus core tier 2; core
researchers/doctoral students tier 3; doctoral students in extended minus core tier 4; other in-region people tier 5. Sort by tier, eligible channel count, strongest signal,
newest date, name; apply the row cap afterward. The 36-month window remains unchanged.

Group inference uses ordered parent/name/team-page, non-generic homepage-host, GitHub-organization, then
same-institution parent/paper links. Shared-team anchors require professor/group_leader roles; a project PI
researcher cannot acquire a team through shared parent or host fallback. Paper parents require the same
institution, while professors always anchor their own groups. Multiple candidates require institution disambiguation; aliases, institutional
OpenAlex IDs and RORs are supported. A person-name parent spelled differently from the leader's name (same surname,
same first initial) links only at the same institution. Each grouped person records `group_link`: `team`, `project`
or `coauthor`; the talent map counts team and project people as members and lists coauthor-only people apart.
Unresolved or cyclic links stay unattached with evidence. See
`references/40-entity-resolution.md` and `assets/institution-aliases.yaml`. `groups.csv` and `groups.md` aggregate the cut roster and sort
by minimum tier, descending member count, PI name; `(unattached)` comes last. They include member roles,
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

## Local OpenAlex setup

Run `python3 scripts/setup_openalex.py` in an interactive terminal.
Copy a key from https://openalex.org/settings/api
and paste it at the hidden prompt. The script checks the rate-limit endpoint before saving the key
to `~/.config/talent-scout/openalex.key` with mode 0600, outside the skill package.

Both OpenAlex helpers load credentials in this order: `OPENALEX_API_KEY`, the file named by
`OPENALEX_API_KEY_FILE`, then `~/.config/talent-scout/openalex.key`. Requests use a Bearer header, not a URL query key.
Use `python3 scripts/setup_openalex.py --check` to check connectivity without printing the key.
No key means anonymous requests; the setup script does not enable billing or change account settings.

The previous repository-local `.secrets/openalex.key` location is no longer read automatically.
If you used it, configure your key again with the setup script, then remove the old copy before packaging
the skill. Git ignore rules do not exclude files from arbitrary directory archives.

## Final-pass corrections and offline replay

`final_pass_affiliation` (verbatim) and `final_pass_country` (ISO-2) override provider values before tier calculation.
`affiliation_source` becomes `final pass <last_verified> <final_pass_url>`; notes keep the prior affiliation/source.
Signal `role`, `latest_role` and raw topics remain unchanged. Re-export refreshes reviewed titles and groups.

```sh
python3 "$SKILL_ROOT/scripts/current_affiliation.py" "$RUN_DIR/persons.jsonl" --date 2026-10-12 --offline --cache-dir "$RUN_DIR/cache/affiliation" > "$RUN_DIR/persons.enriched.jsonl"
python3 "$SKILL_ROOT/scripts/table_export.py" "$RUN_DIR/persons.enriched.jsonl" --date 2026-10-12 --max-rows 0 --out "$RUN_DIR/roster"
```

`--offline` never requests the network, reads API credentials or writes cache files; it skips missing/corrupt cache
queries and prints `offline cache misses: N`. The count is skipped query attempts, not distinct people. Normal
mode keeps provider caching. Default extended region is EU27+UK+CH+NO (including explicit `NO`); core is DE+CH.
The default row cap is 0 (unlimited). CSV and Markdown table cells use the same whitespace folding; source topics
stay verbatim. Year-only dates qualify when the year overlaps the window; month-only dates use their first day.
