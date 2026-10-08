# Stage 5 — Output

Two files with identical content: `roster.csv` and `roster.md`. Columns are fixed
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
| last_verified | run date |
| notes | free text: ambiguity, missing roster, time-of-award affiliation |
| fit | core / adjacent / mixed, from the signals' `fit` tags |
| first_pub_year | year of the person's earliest work in OpenAlex, when an id exists (a career-stage fact, not a judgement) |
| latest_role | role in the newest signal |
| homepage | public lab or personal page, when any signal carried one |
| ranked_channels | channels counted for sorting: those with a hop-0 signal or a high/medium signal |

Sort by `ranked_channels`, then strongest signal, then newest signal, then name. Low-strength hop-1 signals (a name
in an author list) stay as evidence but do not lift a row; otherwise the industry channel's author lists outrank ERC
grants and prizes. Keep only rows whose country is in
the region; write the others to `roster.out-of-region.json` and count them. Cut the table to `target_rows` after
sorting and report the cut in Coverage. There is no composite score; the cut is a budget, not a judgement.

Below the table, add a short **Coverage** block: channels run, pages read per channel, what was
skipped at budget, competitions whose rosters were not public. Then an optional per-person
evidence appendix (one bullet per signal with URL) for the top rows.

Script: `scripts/table_export.py persons.jsonl --region EU27+UK+CH --max-rows 50 --coverage-dir signals/` writes
both files, the out-of-region list and the Coverage block (it appends every `signals/*.coverage.md`).
