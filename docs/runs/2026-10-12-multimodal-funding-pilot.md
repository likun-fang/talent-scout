# Live source pilot: multimodal AI, ANR and NWO (2026-10-12)

Purpose: test project-to-person extraction requested in PR #1 review. This is a source pilot, not a full
stage 0–5 sourcing run, a production roster, or evidence that domain-parallel agents outperform channel agents.
No sourcing procedure or ranking code was changed. All raw data and named-person artifacts stay in the ignored
`runs/multimodal-funding-pilot-2026-10-12/` directory. Its `extract.py` replays extraction offline.

## Scope and observed results

- Window: 2023-10-12 through 2026-10-12. Project start is used as a documented fallback, not an award date.
- NWO: one complete `summary=multimodal` query, two pages, 98 distinct project IDs. Of these, 41 have start
  dates in the window. This is not 41 relevant AI projects: domain relevance was not adjudicated for every hit.
- Selected two clearly relevant NWO projects for extraction: `2024.051` (Multilingual Image Generation) and
  `2024.052` (Hallucination-free Open Vision Langauge Model of the NL; spelling preserved from source).
- ANR: search-discovered project details `ANR-25-CE23-4683` (GestToSay) and `ANR-24-CE23-4826` (MINERAL),
  both within the start-date window, extracted from downloaded HTML.
- Four project samples yielded nine person/project rows and seven distinct named people. Three people's
  current title sections were checked on public institutional/personal pages. The other four remain unclassified.
- No current-affiliation API enrichment, final roster export, full-domain recall measurement, or parallel-agent
  comparison was performed. ANR native search filters and bulk datasets remain untested.

## NWO: reproducible requests and actual fields

Official documentation: https://data.nwo.nl/en/how-to-use-the-nwopen-api

```text
https://nwopen-api.nwo.nl/NWOpen-API/api/Projects?summary=multimodal
https://nwopen-api.nwo.nl/NWOpen-API/api/Projects?summary=multimodal&page=2
```

No API key was needed. The first local request failed because sandbox DNS could not resolve the host;
the approved network retry succeeded. Responses were saved as `raw/nwo-multimodal.json` and
`raw/nwo-multimodal-page2.json`. The envelope contains `meta` and `projects`. Observed metadata:
`count: 98`, `per_page: 50`, `pages: 2`, `page: 1|2`; page lengths were 50 and 48 with no duplicate project IDs.

Useful project fields: `project_id`, `title`, `funding_scheme`, `start_date`, `end_date`, `reporting_year`,
`summary_en`, `summary_nl`, `grant_id`, `project_members`, and optional `products`.
Member fields include `member_id`, `first_name`, `prefix`, `last_name`, `role`, `organisation`, `ror`,
`active`, optional `orcid`, and degree fields. Organisation hierarchy is separated with `||`.

Observed traps:

- `multimodal` also retrieves transport, ethnography, chemistry and other unrelated meanings. Inspect abstracts.
- Data includes pre-2016 projects despite the introductory documentation's stated coverage. Filter dates locally;
  the pilot did not verify a server-side date filter. Missing dates are not recent evidence.
- The same member appears as both `Main Applicant` and `Project leader`. Collapse by member ID within a project
  and preserve the explicit leader role; do not treat these as two people. Do not add project IDs as person keys.
- `active` can be true for members on old projects; it is not proof of present employment.
- `degree_pre_nominal` / `degree_post_nominal` are not current job titles. Co-applicants are not automatically PIs.
- Both selected projects are under a computing-time funding scheme. They are useful technical leads, but should
  not be presented as equivalent in prestige to an ERC award or an ordinary cash research grant.

## ANR: extraction from actual project records

```text
https://anr.fr/Project-ANR-25-CE23-4683
https://anr.fr/Project-ANR-24-CE23-4826
```

Both downloaded successfully with plain HTTP requests; no rendered browser was needed. Extracted sections:
project title/summary, `Project coordination` (name and institution), `Partnership`, `Help of the ANR`,
and `Beginning and duration of the scientific project`. The two start dates have month precision only:
December 2025 and September 2024. Preserve that precision. The call year is not the exact award date.

The coordinator label supports project leadership, not professorship. Institutional/personal pages provide
independent title evidence. One page lists a current professorship and a previous lecturer appointment:
select the current section, not every title on the page. Another person's English and French pages use
different academic labels; retain the original wording rather than implying that the role taxonomy is universal.

## Coverage and remaining validation

The extraction payloads comprise two NWO API pages and five saved HTML pages (two ANR records, three profiles).
Additional web-tool reads covered documentation, source discovery and profile checks; they were not a budgeted
channel sweep. One profile web-tool open failed, while its direct HTTP fetch succeeded. This pilot does not
claim page-budget exhaustion or stage-2 completion.

Next evidence needed: test ANR structured datasets/native filters; expand keyword coverage; adjudicate relevance
and funding types; verify unresolved people and affiliations. Validate any domain-parallel proposal separately
against a comparable channel-parallel run. This pilot only establishes working source-to-person paths for the
four sampled projects.

## Corrections replayed after review

The saved responses were replayed with an explicit domain audit: two NWO projects accepted, two demonstrated
non-AI hits excluded, and the remaining 94 kept pending (including old records). Pending hits do not become
positive evidence. The window audit remains separate from relevance adjudication.

Member duplicates now retain every source role and organisation, selecting explicit project leadership without
discarding other roles. Missing member IDs stay separate; organisation conflicts are flagged. The seven NWO
person/project rows are labelled `resource_allocation`, low strength, with the exact computing-time scheme.
The two ANR rows remain research-grant evidence. All register affiliations are explicitly historical/project
affiliations; no current affiliation is fabricated from `active`. Current titles are selected manually from
current-position sections, excluding historical appointments. The nine rows still represent seven people,
not nine independent candidates. These are evidence-table corrections, not a completed production roster.

The channel reference now documents the observed fields, relevance gate, member deduplication and allocation
distinction. A regression test confirms resource allocations stay in evidence/recent outputs but do not enter
research-grant aggregation or infer a job title. These changes leave the existing merge and ranking code intact.
