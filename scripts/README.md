# Optional scripts (Python 3.9+, standard library by default)

OpenAlex calls honour `OPENALEX_API_KEY` (free key; without it OpenAlex allows roughly 100 calls/day).

| script | stage | input → output |
|--------|-------|----------------|
| `openalex_lookup.py` | 1, 3, 4 | `--topic "<phrase>"` → top 10 topics to choose from; `--topics T1,T2` → venues (repositories dropped) / institutions / lead authors in region; `--title "<paper>"` → authors with institutions; `--author <id>` → record with ORCID |
| `visit_page.py` | final pass | public URL (or `--batch` file) → timestamped page text or LinkedIn excerpts, access status; optional Playwright rendering for JS-only lab pages |
| `current_affiliation.py` | 4 | `persons.jsonl` → same records with current affiliation from ORCID / OpenAlex / newest evidence, with the stale-ORCID override |
| `merge_persons.py` | 4 | `signals.jsonl` → `persons.jsonl` using the key ladder; never merges on name alone |
| `table_export.py` | 5 | `persons.jsonl` → region-filtered `roster.csv` + `roster.md` (+ Coverage block, + `.out-of-region.json`), cut to `--max-rows` |

Date defaults: `openalex_lookup.py --topics` queries the 36 months ending on `--date` (default today);
`--since YYYY` widens the start to that January 1. `table_export.py` applies the same 36-month window before
sorting (`--window-months` to override): a person needs one signal inside it, ranking uses those, and older or
undated signals stay in the row as evidence and are listed in `.excluded-signals.json`. Use the same
`--date YYYY-MM-DD` for both scripts.

All scripts read/write UTF-8, exit non-zero on malformed input, and print a one-line summary to stderr.
`table_export.py` writes CSV as UTF-8 with a BOM (`utf-8-sig`) so Windows Excel reads accented names correctly;
Markdown and JSON output remain plain UTF-8 without a BOM.
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
