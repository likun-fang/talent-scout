# Optional scripts (Python 3.9+, standard library only)

OpenAlex calls honour `OPENALEX_API_KEY` (free key; without it OpenAlex allows roughly 100 calls/day).

| script | stage | input → output |
|--------|-------|----------------|
| `openalex_lookup.py` | 1, 3, 4 | `--topic "<phrase>"` → top 10 topics to choose from; `--topics T1,T2` → venues (repositories dropped) / institutions / lead authors in region; `--title "<paper>"` → authors with institutions; `--author <id>` → record with ORCID |
| `current_affiliation.py` | 4 | `persons.jsonl` → same records with current affiliation from ORCID / OpenAlex / newest evidence, with the stale-ORCID override |
| `merge_persons.py` | 4 | `signals.jsonl` → `persons.jsonl` using the key ladder; never merges on name alone |
| `table_export.py` | 5 | `persons.jsonl` → region-filtered `roster.csv` + `roster.md` (+ Coverage block, + `.out-of-region.json`), cut to `--max-rows` |

All scripts read/write UTF-8, exit non-zero on malformed input, and print a one-line summary to stderr.
`table_export.py` writes CSV as UTF-8 with a BOM (`utf-8-sig`) so Windows Excel reads accented names correctly;
Markdown and JSON output remain plain UTF-8 without a BOM.
If no interpreter is available, each stage file describes the manual equivalent.
