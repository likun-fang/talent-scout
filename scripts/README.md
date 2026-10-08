# Optional scripts (Python 3.9+, standard library only, no network keys)

| script | stage | input → output |
|--------|-------|----------------|
| `openalex_lookup.py` | 1, 3, 4 | `--topic "<phrase>"` → venues / institutions in region; `--title "<paper>"` → authors with institutions; `--author <id>` → record with ORCID |
| `erc_pdf_rows.py` | 2 | ERC results PDF **text** (extract with your platform's PDF reader) → rows filtered by panel codes / keywords, as signals JSONL |
| `merge_persons.py` | 4 | `signals.jsonl` → `persons.jsonl` using the key ladder; never merges on name alone |
| `table_export.py` | 5 | `persons.jsonl` → `roster.csv` + `roster.md` with the fixed columns |

All scripts read/write UTF-8, exit non-zero on malformed input, and print a one-line summary to stderr.
If no interpreter is available, each stage file describes the manual equivalent.
