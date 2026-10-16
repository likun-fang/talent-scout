# Stage 0 — Probe environment, fix scope

## Paths

`SKILL_ROOT` is the directory holding `SKILL.md`; every `references/`, `assets/`, `scripts/` and `domain-cache/`
path in this skill is relative to it. `RUN_DIR` is this run's directory, default `<working directory>/runs/<slug>-<run
date>/`, never inside `SKILL_ROOT` when the skill is installed by symlink. Every artefact (`run.meta.json`,
`domain-map.yaml`, `signals/`, `signals.jsonl`, `persons.jsonl`, `roster.*`, `groups.*`, `pages/`, the run's
`domain-cache/` copy) is written under `RUN_DIR`. `SKILL_ROOT/domain-cache/` is read as a starting point and updated
only when the maintainer confirms by hand.

## Probe (do all three, record results)

1. **Web**: can you fetch an arbitrary URL and read its text? Try `https://api.openalex.org/works?per_page=1`.
   Check what came back, not only the status: JSON with a `results` array means OpenAlex is reachable keyless; record
   `openalex: keyless` and continue. A 200 that carries HTML (a bot check, a "Request Rejected" page) counts as not
   reachable. Then ask the user once, at stage 0, for a free key (openalex.org/settings/api, exported as
   `OPENALEX_API_KEY`): stages 1 and 2 run keyless, but stage 4 makes two to three calls per person (ORCID title,
   institution, first publication year) and a 500-person run is far beyond the keyless quota. Without a key, stage 4
   runs without those lookups and most people without a printed title stay `unknown`; say so in Coverage. Record
   `openalex: keyed|keyless`. A key given as a file path is read with `OPENALEX_API_KEY=$(cat <path>)` before each
   script call; never copy the key into any run file. If only a search tool exists,
   mark `web: search_only`; if nothing loads, `web: none`.
   **OpenAlex credit plan.** A free key buys 10,000 credits a day (a `search=` call costs 10, a filtered list 1, a
   single-record GET 0), shared by every agent of the run and reset at 00:00 UTC. Six parallel stage-2 channels
   spent a day's credits by 21:20 UTC and left stage 4 waiting for the reset. Write the plan into `run.meta.json`
   (`openalex_credits: {"per_channel": N, "stage_4_reserve": M}`) and into each channel brief: a channel stops at
   its cap and lists the skipped lookups in its coverage note, nobody falls back to keyless calls or retries a 429,
   and the reserve (two to three list calls per person expected in the roster) stays untouched until stage 4.
   Prefer filtered lists (`filter=`) over `search=`; use `search=` once per title, never per author.
   Also probe once each and record the result: `https://api.github.com/repos/huggingface/lerobot` (often 403),
   `https://api.openreview.net/notes?limit=1` (often 403), `https://dblp.org/search/publ/api?q=robot&format=json`
   (may turn into a bot-check page mid-run), `git ls-remote https://github.com/huggingface/lerobot` (bare clones
   usually work when the API does not). The repository names only test connectivity; they are not tied to the domain.
   For the core-region registers: a POST to the GEPRIS search backend and a `HEAD` on the SNSF grants dataset
   (exact calls in `channels/funding-de-ch.md`).
2. **Interpreter**: can you run Python 3? If yes, scripts in `scripts/` are usable. Otherwise follow the
   manual path in each stage file.
3. **Files**: can you write files under `RUN_DIR`? If not, keep `signals` in the conversation and emit the final
   table in one message.

## Fix scope

Every item below except the domain phrase has a default. Apply the defaults the user did not override without asking;
ask only for the domain phrase when the request does not name one. List the values you used in one line when you show
the stage-1 summary, so the user can change them there.

- Domain phrase [required, no default] and 0–5 seed names / labs / venues the user already knows [none].
- Region, two layers (codes in `assets/countries.yaml`):
  - `region_core` [DE+CH]: professors and research groups here come first in the table;
  - `region_extended` [EU27+UK+CH+NO]: everyone with a qualifying signal here gets a row; professors and group
    leaders in the extended region rank right after the core-region ones and before core-region researchers and
    doctoral students. The tiers are in `references/50-output.md`.
  "Based in region" means the person's **current or most recent affiliation** is in the region, regardless of
  nationality. People outside `region_extended` get no person signal.
- Time window [the 36 months ending on the run date, for all channels including funding]. For a run on 2026-10-12
  this is 2023-10-12 through 2026-10-12, inclusive. Record the exact bounds. Use the event or work date, never the
  date a page was fetched; see `channels/README.md`.
- Final-pass budget [team pages: one per group, tier 1 first; LinkedIn profile reads: 20, serial, 5 s apart, optional;
  see `45-web-verification.md`. The anonymous quota is per outbound address and is often already spent, so the pass
  must not depend on it].
- Channels to run [the eight default channels listed below; optional channels require explicit selection]. Page budget per channel [40 fetch attempts, counting failures and replacements; API calls,
  dataset downloads and git clones are not pages]. Target
  roster size [uncapped, `target_rows: 0`]: every qualifying person in the region gets a row and the final pass
  budget, not the row count, limits the work; when the user asks for a cut, the table is cut after sorting and the
  Coverage block reports how many rows were cut.
- `RUN_DIR` [see Paths].

## Write `run.meta.json`

Write it to `RUN_DIR/run.meta.json`:

```json
{"domain": "...", "purpose": "discovery of technology and research groups through their public professional record; roles recorded as data",
 "seeds": [], "region_core": "DE+CH", "region_extended": "EU27+UK+CH+NO", "region": "EU27+UK+CH+NO",
 "window_months": 36, "window_start": "YYYY-MM-DD", "window_end": "YYYY-MM-DD", "final_pass_linkedin_budget": 20,
 "channels": ["awards-papers","funding-eu","funding-de-ch","national-prizes","competitions","startups","industry","open-source"],
 "page_budget_per_channel": 40, "target_rows": 0,
 "openalex_credits": {"per_channel": 900, "stage_4_reserve": 4000},
 "run_dir": "/absolute/path/to/runs/<slug>-YYYY-MM-DD",
 "stage_status": {"0": "done", "1": "", "2": "", "3": "", "4": "", "5": "", "final_pass": ""},
 "env": {"web": "fetch|search_only|none", "interpreter": true, "files": true, "openalex": "keyed|keyless", "github_api": false,
         "openreview_api": false, "dblp": true, "git_clone": true, "gepris_api": true, "snsf_datasets": true},
 "started": "YYYY-MM-DD"}
```

`region` is kept equal to `region_extended` for older readers. `stage_status` holds `""` (not started), `"running"`
or `"done"` per stage; set a stage to `"running"` when you start it and to `"done"` when its "Done when" condition in
`SKILL.md` holds. Stages 1 and 2 end with a stop for the user, so they stay `"running"` until the user has replied.

Everything downstream cites this file so a reader can tell how the table was produced.

For new runs, also record an `execution` object with `plan: "execution-plan.json"`,
`check: "execution-check.json"`, `coverage_status: "not_checked"` and `tracing: "local"`.
After stage 1, record the frozen plan hash and actual code version; update coverage_status from the checker.
Use `local+langsmith` only when export is explicitly enabled. Never store API keys here.
See `20-execution-tracing.md`. Mutable run metadata must not be included in frozen configuration checksums.
