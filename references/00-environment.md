# Stage 0 — Probe environment, fix scope

## Probe (do all three, record results)

1. **Web**: can you fetch an arbitrary URL and read its text? Try `https://api.openalex.org/works?per_page=1`.
   If JSON comes back, structured APIs are reachable. If only a search tool exists, mark `web: search_only`.
2. **Interpreter**: can you run Python 3? If yes, scripts in `scripts/` are usable. Otherwise follow the
   manual path in each stage file.
3. **Files**: can you write files that persist across turns? If not, keep `signals` in the conversation
   and emit the final table in one message.

## Fix scope with the user (defaults in brackets, ask only if unstated)

- Domain phrase [required] and 0–5 seed names / labs / venues the user already knows [optional, helps stage 1].
- Region [Europe = EU27 + UK + CH; codes in `assets/countries.yaml`]. "Based in region" means the
  person's **current or most recent affiliation** is in region, regardless of nationality.
- Time window [last 5 years for awards / competitions; last 7 years for funding].
- Channels to run [all]. Page budget per channel [40 pages]. Target roster size [50 rows].

## Write `run.meta.json`

```json
{"domain": "...", "seeds": [], "region": "EU27+UK+CH", "window_years": 5,
 "channels": ["awards-papers","funding-eu","national-prizes","competitions","startups","industry","open-source"],
 "page_budget_per_channel": 40, "target_rows": 50,
 "env": {"web": "fetch|search_only", "interpreter": true, "files": true},
 "started": "YYYY-MM-DD"}
```

Everything downstream cites this file so a reader can tell how the table was produced.
