# Channel brief — talent-scout run "<domain>", <region>

Goal: find PEOPLE doing notable public work in <domain> (<sub-areas>) whose current or most recent
affiliation is in <region>. Window: awards/competitions <years>; funding <years>.

## Output
Append one JSON object per line to `signals/<channel>.jsonl` (schema: `assets/signal.schema.json`).
- Emit the non-person signal (work / team / company / org) AND hop to people yourself: one person signal per
  in-region person, `hop_depth: 1`, `parent` set, `evidence_url` = the page that names the person.
- Every signal carries an evidence URL you actually opened or received from search. Prefer year-stamped or archived URLs.
- Fill `ids.openalex` / `ids.orcid` / `ids.github` whenever a source gives them; attach an OpenAlex id only when
  that profile's works are in the domain.
- People outside the region get no person signal.

## Access (fill from run.meta.json env)
- OpenAlex: `OPENALEX_API_KEY` is set; strip `?` and `*` from titles; arXiv-only records often have empty institutions.
- GitHub API / OpenReview API / DBLP: <reachable or blocked>; fallbacks are in the channel file.
- Web fetch and search for award pages, team pages, company pages.

## Rules
- Public professional record only: institutional pages, papers, grant registers, results pages, company team pages,
  public code. Pages behind a login, social profiles, people-search sites and private contact details stay out.
  No sensitive categories. Junior / school competitions and minors stay out.
- Page budget: <N> fetched pages for this channel; API calls and git clones are not pages. Stop at budget.
- Finish with `signals/<channel>.coverage.md`: pages read, skipped at budget, rosters not public, and every place the
  channel file did not fit reality (blocked sites, rate limits, missing data).
- Final reply: signals by kind, distinct in-region people, problems list.
