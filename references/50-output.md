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

Sort by number of distinct channels hit, then by strongest signal. No composite score.

Below the table, add a short **Coverage** block: channels run, pages read per channel, what was
skipped at budget, competitions whose rosters were not public. Then an optional per-person
evidence appendix (one bullet per signal with URL) for the top rows.

Script: `scripts/table_export.py persons.jsonl` writes both files.
