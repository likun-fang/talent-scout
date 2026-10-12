# Optional scripts (Python 3.9+, standard library by default)

OpenAlex calls honour `OPENALEX_API_KEY` (free key; without it OpenAlex allows roughly 100 calls/day).

| script | stage | input → output |
|--------|-------|----------------|
| `openalex_lookup.py` | 1, 3, 4 | `--topic "<phrase>"` → top 10 topics to choose from; `--topics T1,T2` → venues (repositories dropped) / institutions / lead authors in region; `--title "<paper>"` → authors with institutions; `--author <id>` → record with ORCID |
| `visit_page.py` | 4 | public URL → timestamped page text, links and access status; optional Playwright browser rendering |
| `current_affiliation.py` | 4 | `persons.jsonl` → same records with current affiliation from ORCID / OpenAlex / newest evidence, with the stale-ORCID override |
| `merge_persons.py` | 4 | `signals.jsonl` → `persons.jsonl` using the key ladder; never merges on name alone |
| `table_export.py` | 5 | `persons.jsonl` → region-filtered `roster.csv` + `roster.md` (+ Coverage block, + `.out-of-region.json`), cut to `--max-rows` |

Date defaults: `openalex_lookup.py --topics` queries the run year and previous two years through `--date`
(default today); `--since` overrides the first year. `table_export.py` applies the same three-calendar-year
window before sorting, with `--window-years` to override, and writes `.excluded-signals.json` for old,
future, missing or invalid dates. Use the same `--date YYYY-MM-DD` for both scripts.

All scripts read/write UTF-8, exit non-zero on malformed input, and print a one-line summary to stderr.
`table_export.py` writes CSV as UTF-8 with a BOM (`utf-8-sig`) so Windows Excel reads accented names correctly;
Markdown and JSON output remain plain UTF-8 without a BOM.
If no interpreter is available, each stage file describes the manual equivalent.

## Webpage / LinkedIn evidence reader

Static HTML/text (no extra dependencies):

```sh
python3 scripts/visit_page.py 'https://example.org/person' --out runs/demo/pages/person.json
```

For dynamic pages install the optional browser dependency in a project-local environment:

```sh
python3 -m venv .venv-browser
.venv-browser/bin/python -m pip install -r scripts/requirements-browser.txt
.venv-browser/bin/python scripts/visit_page.py 'https://www.linkedin.com/in/PROFILE/' --browser --channel chrome --out runs/demo/pages/linkedin.json
```

`--channel chrome` uses installed Google Chrome in a new, unauthenticated context. Alternatively run
`.venv-browser/bin/python -m playwright install chromium` and omit `--channel`.
The reader does not import your browser cookies or log into accounts. It reads one supplied URL per call;
profile discovery still uses the agent's web search. It never clicks buttons or submits forms.

JSON includes `status`, `requested_url`, `final_url`, `retrieved_at`, `title`, `text`, `links`,
`http_status`, `truncated` and `role_verified: false`. Access-status detection is heuristic, so inspect
the returned content before using it as evidence. LinkedIn public pages may be partial. A blocked or
login-gated result is recorded with exit code 2, not treated as a successful profile lookup.
Use `--timeout`, `--wait-ms` and `--max-chars` to bound a read.
See `references/45-web-verification.md` for matching and evidence rules.
