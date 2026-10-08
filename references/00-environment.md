# Stage 0 — Probe environment, fix scope

## Probe (do all three, record results)

1. **Web**: can you fetch an arbitrary URL and read its text? Try `https://api.openalex.org/works?per_page=1`.
   If JSON comes back, structured APIs are reachable. If only a search tool exists, mark `web: search_only`.
   OpenAlex's keyless quota is shared per outbound IP, so from an agent sandbox it is usually already spent.
   Ask the user for a free key (openalex.org/settings/api) at stage 0 and export it as `OPENALEX_API_KEY`.
   Also probe once each and record the result: `https://api.github.com/repos/huggingface/lerobot` (often 403),
   `https://api.openreview.net/notes?limit=1` (often 403), `https://dblp.org/search/publ/api?q=robot&format=json`
   (may turn into a bot-check page mid-run), `git ls-remote https://github.com/huggingface/lerobot` (bare clones
   usually work when the API does not).
2. **Interpreter**: can you run Python 3? If yes, scripts in `scripts/` are usable. Otherwise follow the
   manual path in each stage file.
3. **Files**: can you write files that persist across turns? If not, keep `signals` in the conversation
   and emit the final table in one message.

## Fix scope with the user (defaults in brackets, ask only if unstated)

- Domain phrase [required] and 0–5 seed names / labs / venues the user already knows [optional, helps stage 1].
- Region [Europe = EU27 + UK + CH; codes in `assets/countries.yaml`]. "Based in region" means the
  person's **current or most recent affiliation** is in region, regardless of nationality.
- Time window [last 5 years for awards / competitions; last 7 years for funding].
- Channels to run [all]. Page budget per channel [40 fetched pages; API calls and git clones are not pages]. Target
  roster size [50 rows]; the table is cut to this after sorting, and the Coverage block reports how many rows were cut.

## Write `run.meta.json`

```json
{"domain": "...", "seeds": [], "region": "EU27+UK+CH", "window_years": 5, "funding_window_years": 7,
 "channels": ["awards-papers","funding-eu","national-prizes","competitions","startups","industry","open-source"],
 "page_budget_per_channel": 40, "target_rows": 50,
 "env": {"web": "fetch|search_only", "interpreter": true, "files": true, "openalex": "keyed|keyless", "github_api": false, "openreview_api": false, "dblp": true},
 "started": "YYYY-MM-DD"}
```

Everything downstream cites this file so a reader can tell how the table was produced.
