# Stage 5 — Output

The person table is written to `roster.csv` and `roster.md`; the Markdown also includes Coverage and evidence.
A group view is written to `groups.csv` and `groups.md` in the same directory. Write the CSV as UTF-8 **with BOM** (`utf-8-sig`): Windows Excel
otherwise guesses a local code page and turns ä, ł, ś into mojibake; Mac readers accept either. Columns are fixed
(`assets/person-table.columns.md`); do not add or drop columns per run.

| column | content |
|--------|---------|
| name | display name as on the most authoritative evidence page |
| current_affiliation | from stage 4, with source + date in `affiliation_source` |
| country | ISO-2 of current affiliation |
| role | first_author / pi / team_member / founder / maintainer / inventor / unknown (data field only) |
| domain | the run's domain phrase |
| channels_hit | semicolon list, e.g. `awards-papers;funding-eu` |
| signals | semicolon list of `signal_type@date` |
| evidence_urls | semicolon list; at least one, one per signal |
| ids | `orcid:…;github:…;openalex:…` |
| hop_depth | 0 (named directly), 1, 2 |
| merge_confidence | high / medium / low / ambiguous |
| affiliation_source | `orcid 2026-09` etc. |
| last_verified | date of an actual final-pass page read; empty until then, never the export date |
| notes | free text: ambiguity, missing roster, time-of-award affiliation |
| fit | core / adjacent / mixed, from the signals' `fit` tags |
| first_pub_year | year of the person's earliest work in OpenAlex, when an id exists (a career-stage fact, not a judgement) |
| latest_role | role in the newest signal |
| homepage | public lab or personal page, when any signal carried one |
| ranked_channels | channels counted for sorting: those with a hop-0 signal or a high/medium signal |
| role_class | professor / researcher / phd_student / industry / unknown, from stage 4 |
| role_confidence | high / medium / low |
| tier | 1 / 2 / 3 / 4, recomputed from role and current country |
| topics | at most five deduplicated verbatim signal topics, joined with `;` |
| group | `<PI name> @ <institution>`, or empty if inference was inconclusive |

Before sorting, split each person's signals by the run window (default: the 36 months ending on the run date).
A person needs at least one signal inside it; `channels_hit`, `hop_depth`, `ranked_channels` and the sort use only
those. Signals outside the window, undated or future-dated stay in the row's `signals` and `evidence_urls` columns
as evidence and are listed in `roster.excluded-signals.json`. This audit file includes window-excluded
signals from both retained and omitted people; its length is not the retained-evidence count. `first_pub_year` is a
lifetime fact, not an activity filter. Month-only dates use the first day of the month. A year-only date (GEPRIS gives
start years) qualifies when that year overlaps the window at all, so a project begun in the window's start year counts. Pass `--date`
from `run.meta.json` for reproducibility and `--window-months` only when the user asked for another window.

Assign tiers before sorting:

| tier | current country and role_class |
|------|--------------------------------|
| 1 | in core (default DE+CH), professor |
| 2 | in core, researcher or phd_student |
| 3 | in extended minus core (default EU27+UK+CH minus DE+CH), phd_student |
| 4 | all other people in extended, including industry and unknown roles |

Countries outside extended go to `roster.out-of-region.json` and do not enter the table.
Sort by tier ascending, `ranked_channels` descending, strongest qualifying signal descending,
newest qualifying signal descending, then name ascending. Low-strength hop-1 signals (a name
in an author list) stay as evidence but do not lift a row; otherwise the industry channel's author lists outrank ERC
grants and prizes. Keep only rows whose country is in
the region; write the others to `roster.out-of-region.json` and count them. Cut the table to `target_rows` after
sorting and report the cut in Coverage. There is no composite score; the cut is a budget, not a judgement.

Below the table, add a short **Coverage** block: channels run, pages read per channel, what was
skipped at budget, competitions whose rosters were not public. Report separately the number of window-excluded signals retained on the final table's people and the
number of all signals belonging to omitted people (no qualifying signal, outside the region, missing evidence,
or cut by `--max-rows`). Counts use person records, not names, so namesakes cannot collide. Then add the
per-person evidence appendix: `role_evidence` including the rule and source, plus one bullet per signal
with its URL. `role_evidence` does not become a table column.

After the table is cut, run the final pass in `45-web-verification.md` on those rows only. It fills `notes` with
role excerpts and sources, sets `last_verified` only for an actual page read, and reports in Coverage how
many profiles were read and how many were refused. Preserve these dates on re-export.

## Group view

`groups.csv` and `groups.md` aggregate only the final, region-filtered, cut roster. Group membership is
inferred in stage 4, before cutting; a PI omitted by the cut can still be named by members' `group` field.
Do not substitute a member's personal homepage for a missing PI homepage.

Columns, in order:

`group, pi_name, institution, country, tier, homepage, topics, members, member_count, recent_outputs, active_funding, open_source, evidence_urls`

- `group`, `pi_name`, `institution`: group string and its components; `country` comes from members'
  current countries (deduplicated and joined with `;`), `tier` is the minimum member tier.
- `homepage`: the PI's homepage if the PI is present; otherwise empty. `topics`: exact deduplication
  of member signal topics, maximum five, joined with `;`.
- `members`: `Name(role_class)`, joined with `;`, sorted by tier ascending then name. `member_count`
  counts included person records.
- `recent_outputs`: the strongest three signals inside the run window, ties by newest date and then
  signal type/URL; `signal_type@date: snippet` with at most 80 characters of the snippet. Shared outputs
  are deduplicated by type, date and evidence URL, retaining the strongest instance.
- `active_funding`: all retained `erc_`/`dfg_`/`snsf_` signals as `signal_type@date`, deduplicated and
  joined with `;`. The contract supplies no funding end dates: this is funding evidence, not an assertion
  that an older award is still active.
- `open_source`: deduplicated evidence URLs from the `open-source` channel. `evidence_urls`: all group
  evidence URLs. Both keep retained background evidence and use `;`.

Sort groups by minimum tier ascending, member count descending, then PI name ascending.
People with empty `group` go into a single `(ungrouped)` row at the end, only when needed; it has no
invented PI or institution. Below `groups.md`, Coverage reports the number of named groups (excluding
that row), ungrouped people, and that the view covers the cut roster. Both CSVs use UTF-8 with BOM.

Script (paths are relative to `RUN_DIR`; resources live under `SKILL_ROOT`):

```sh
python3 "$SKILL_ROOT/scripts/table_export.py" "$RUN_DIR/persons.jsonl" --date 2026-10-12 --region-core DE+CH --region-extended EU27+UK+CH --max-rows 50 --coverage-dir "$RUN_DIR/signals" --out "$RUN_DIR/roster"
```

`--region` remains an alias for `--region-extended`. `--max-rows 0` keeps all qualifying in-region people.
The script writes both person files, both group files, the out-of-region and excluded-signal JSON files,
and appends every `signals/*.coverage.md` to roster Coverage. It does not rewrite `persons.jsonl`.
