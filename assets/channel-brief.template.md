# Channel brief — talent-scout run "<domain>", core <region_core>, extended <region_extended>

Goal: find the PEOPLE and research groups doing notable public work in <domain> (<sub-areas>), for technology
discovery and collaboration. Current or most recent affiliation must be in <region_extended>; <region_core> comes first:
there, professors and group leaders matter most, then researchers and doctoral students; doctoral students elsewhere
in <region_extended> come next. Window for all channels, including funding: <window_start> through <window_end>,
inclusive (default: the 36 months ending on the run date). Use event dates, never fetch dates.
Follow the date rules in `references/channels/README.md`; emit older or undated evidence with its real date or none.

## Paths
- Skill files are relative to `SKILL_ROOT` = <skill_root> (the directory holding `SKILL.md`).
- Write everything under `RUN_DIR` = <run_dir>; never write into `SKILL_ROOT`.

## Output
Append one JSON object per line to `RUN_DIR/signals/<channel>.jsonl` (schema: `SKILL_ROOT/assets/signal.schema.json`).
- Emit the non-person signal (work / team / company / org) AND hop to people yourself: one person signal per
  person in <region_extended>, `hop_depth: 1`, `parent` set, `evidence_url` = the page that names the person.
- Every signal carries an evidence URL you actually opened or received from search. Prefer year-stamped or archived URLs.
- Fill `ids.openalex` / `ids.orcid` / `ids.github` whenever a source gives them; attach an OpenAlex id only when
  that profile's works are in the domain.
- Fill `role_title` with the title or section heading printed next to the name on the source page, copied verbatim
  ("Professor", "Doctoral researchers", "Wissenschaftlicher Mitarbeiter"); leave it empty when the page prints none,
  never infer it. Fill `topics` with 1–3 key phrases cut verbatim from the paper title, project name or repository
  name. The channel file says where both come from.
- Tag `fit`: `core` or `adjacent`. Add `homepage` when the page links a lab or personal site.
- People outside <region_extended> get no person signal.

## Access (fill from run.meta.json env)
- OpenAlex: <keyless | keyed>. Keyless is fine until a call returns 429; then stop and ask for a key. Strip `?` and
  `*` from titles; arXiv-only records often have empty institutions.
- OpenAlex credits for this channel: <per_channel> of the run's 10,000 daily credits (`search=` costs 10, a filtered
  list 1, a single-record GET 0; the budget is shared by all channels and stage 4, reset 00:00 UTC). Count your
  calls, stop at the cap, list the skipped lookups in coverage; never fall back to keyless calls or retry a 429.
- GitHub API / OpenReview API / DBLP / GEPRIS backend / SNSF datasets: <reachable or blocked>; fallbacks are in the
  channel file.
- Web fetch and search for award pages, team pages, company pages.

## Rules
- Public professional record only: institutional pages, papers, grant registers, results pages, company team pages,
  public code. No LinkedIn or other social profiles anywhere in the run.
  Login-gated content, people-search sites and private contact details stay out.
- Keys: a source that needs a key or public token reads it from `~/.config/talent-scout/<source>.key`; name the
  path in notes and coverage, never the value. Do not register accounts or request keys on the user's behalf.
  No sensitive categories. Junior / school competitions and minors stay out.
- Page budget: <N> fetch attempts for this channel, counting failed and replacement fetches; API calls, dataset
  downloads and git clones are not pages. Stop at the Nth attempt, not the Nth readable page.
- Finish with `RUN_DIR/signals/<channel>.coverage.md`: pages read, skipped at budget, rosters not public, and every
  place the channel file did not fit reality (blocked sites, rate limits, missing data).
- Final reply: signals by kind, distinct people in <region_core> and in <region_extended>, problems list.
