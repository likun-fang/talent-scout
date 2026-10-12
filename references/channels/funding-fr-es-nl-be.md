# Optional national funding channel: validated ANR and NWO paths

Channel id: `funding-fr-es-nl-be` (reserved geographic scope). Only ANR (FR) and NWO (NL) extraction is currently enabled.
This is an opt-in sibling of `funding-de-ch`, not a replacement. Add it to the
run's `channels` with its own page budget (40 unless the run specifies another budget) and pass it in the worker
brief. Keep the existing eight defaults, region tiers, merge rules and funding-role inference unchanged.

Read the shared [signal, member-page and date rules](README.md) and [hop rules](../30-hops.md). Inputs are the
run's `region_core`, `region_extended`, `window_start`, `window_end` and domain-map keywords. Search only the
validated countries FR and NL that are in `region_extended`; visit core countries first.
AEI, FWO/FRIS and FNRS below are entry-page leads only: do not sweep them or emit their signals through this
channel until a separate extraction validation is recorded. Report ES/BE as unvalidated, not zero matches. No country or
multimodal keyword is an implicit inclusion criterion: project titles or abstracts must match the domain map.

## Sources and discovery

The official entry pages below were opened on 2026-10-12. Their availability and published search guidance were
checked. A live ANR/NWO sample is recorded in `docs/runs/2026-10-12-multimodal-funding-pilot.md`;
AEI, FWO/FRIS and FNRS extraction remains unvalidated. Read current forms/API documentation
before using filters. Do not assume every portal exposes the same fields or a public bulk API.

| Country | Official entry | Status and follow-up |
|---------|----------------|----------------------|
| FR | [ANR funded projects](https://anr.fr/fr/projets-finances-et-impact/projets-finances/) | Validated detail-page extraction. Search domain keywords; inspect project details and linked project/institution sites. The entry page also links ANR datasets. |
| ES | [AEI awarded grants](https://www.aei.gob.es/ayudas-concedidas/buscador-ayudas-concedidas) | Entry page only; extraction disabled. Future validation: title, keywords or abstract filters; narrow by call year/area where useful. Keep the grant reference to resolve the same project on its host's website. |
| NL | [NWO API documentation](https://data.nwo.nl/en/how-to-use-the-nwopen-api) | Validated API extraction. Use the documented Projects endpoint or linked project database. Inspect titles, summaries, researchers, institutions and outputs where supplied. |
| BE | [FWO funded research](https://www.fwo.be/en/results-outreach/database-financed-research/) | Entry page only; extraction disabled. Follow the official link to FRIS for future validation. Search titles/keywords and use funder, programme, start date and discipline filters as available. |
| BE | [FNRS DataScops entry](https://www.frs-fnrs.be/fr/recherches-financees-par-le-fnrs-datascops) | Entry page only; extraction disabled. For future validation, follow its DataScops link; search keywords and inspect funding periods, subject filters, projects and named researchers. |

- Search English domain-map keywords first. Add relevant French, Spanish or Dutch equivalents to search queries
  where English has poor coverage, recording the actual queries in coverage. Do not translate source quotations.
- Future Belgian validation needs both routes: FWO/FRIS alone does not cover FNRS.
- AEI call year and a portal's funding-period filter are discovery aids, not proof of the award/start date.
  Inspect each selected record before setting `date`.
- NWO's documented endpoint is `https://nwopen-api.nwo.nl/NWOpen-API/api/Projects?`. Check the linked API documentation
  for current filters/pagination; cache responses under the run directory. An API failure is not a zero-result sweep.
- For rendered forms, use the existing page-reading ladder. If a portal cannot be searched, use public official
  project pages or institutional project records as fallback, recording the blocked route and incomplete coverage.
  A search snippet alone is insufficient evidence for a person or role.

## From projects to people

### Relevance and funding gate (before emitting signals)

Keyword hits are discovery leads, not accepted projects. Read the title and abstract against the run's domain
map. Record each reviewed project's disposition (`core`, `adjacent`, `excluded`, or `pending`), reason and a
supporting excerpt in the run audit. Only core/adjacent records produce signals; pending is not a weak positive.
Do not create person signals for excluded projects. In the pilot, `multimodal` retrieved transport and chemistry;
the word alone did not establish AI research. These are contextual examples, not a global keyword blacklist.

Preserve the exact funding scheme and distinguish research grants, fellowships, compute/resource allocations,
and unknown schemes in `note`. A compute allocation is a technical lead, not evidence of a competitive research
grant: emit `signal_type: resource_allocation`, `strength: low`, with its actual date and scheme. This type stays
in ordinary evidence but does not enter `groups.active_funding` or funding-role inference. Unknown schemes stay
pending until their type is resolved. Do not infer prestige from the funder, amount, or the project title.

### NWO records: validated extraction rules

The pilot fetched `api/Projects?summary=multimodal` and `api/Projects?summary=multimodal&page=2` under
`https://nwopen-api.nwo.nl/NWOpen-API/`. Read `meta.count`, `meta.pages`, `meta.page`, and `projects`;
deduplicate project IDs across pages, checking completeness before claiming a complete query. A complete
keyword query is not complete domain coverage. Filter `start_date` locally when using the start-date fallback;
preserve missing dates and old records as background, not recent funding.

Within each project, combine `project_members` rows with the same nonempty `member_id`. Retain all printed
roles and organisations in the audit. Explicit `Project leader` supports `role: pi`; `Main Applicant` and
`Co-applicant` alone do not. Missing member IDs must not all collapse into one row; keep ambiguous entries
separate pending identity resolution. Conflicting organisations require review, not selection by array order.
This is source-record deduplication, not a new cross-channel person merge key.

`organisation` is a grant-associated affiliation and uses `||` hierarchy separators. Neither `active: true`
nor the funder's country establishes current employment/country. Do not write these into `current_affiliation`
or `last_verified`. Follow the existing affiliation verification flow; unresolved geography remains a lead
in coverage. Never copy `degree_pre_nominal` or `degree_post_nominal` into `role_title`.

### ANR records: validated extraction rules

Plain HTML detail pages expose `Project coordination`, `Partnership`, `Help of the ANR`, and
`Beginning and duration of the scientific project`. The coordinator name and institution support project
responsibility; partnership entries are organisations, not unnamed team members. Month-only starts stay
`YYYY-MM`. An ANR reference's year or a call label does not supply an exact award date. Follow personal/team
pages for current titles; native search filters and bulk dataset extraction are not yet validated by this pilot.

### Emit accepted records

1. Select a project whose title/abstract matches the domain map. Preserve its canonical record URL, reference,
   funder, scheme, title and date basis in the evidence. If only an institution is named, emit an `org` signal with
   that institution's name, `role: unknown`, `signal_type: national_project`, `hop_depth: 0`.
2. Where the project record explicitly names its PI/project leader, emit a `person` signal directly with
   `role: pi`, `signal_type: national_project`, `hop_depth: 0`. Copy the leadership label into `snippet`; being
   a contact, beneficiary, applicant or listed researcher alone is not enough to infer PI responsibility.
3. Follow the project or host's team page to identify people when the register does not name them. Emit one person
   signal per evidenced participant, normally `role: team_member`; use `role: pi` only for explicit project
   leadership. Set `parent` to the emitted parent signal's `name_raw`, increment `hop_depth` (maximum 2), and keep
   the parent record URL/reference in `note` alongside the person-naming `evidence_url`.
4. Follow a relevant lab's member page using the shared `lab_member` rules. Copy current section headings, omit
   alumni and excluded member categories, and seek dated outputs for otherwise undated membership. A project's
   award date cannot be assigned to all people currently in the PI's lab.
5. For personal fellowships, emit `signal_type: national_fellowship`, `role: unknown` unless the source separately
   establishes actual PI responsibility. Preserve the scheme and original title; a fellowship alone does not prove
   professorship, group leadership, doctoral enrolment or current employment.

All emitted signals use `channel: funding-fr-es-nl-be`. Use `strength: medium` for a documented project/fellowship
award, with the resource-allocation exception above; do not inflate it from the funder name or grant amount. Keep `fit` and verbatim `topics` under the shared
rules. A current host country must come from affiliation evidence, not the funder's country or a person's name.
An unresolved country stays absent with an explanatory note until the existing affiliation stage resolves it.

## Dates, titles and identities

- Use the award/selection date, or project start date when no award date is available; state the basis in `note`.
  Keep true year/month precision. An old ongoing project is background; a recent separately evidenced paper or
  contribution can qualify its author. Never use today's date or the project end date as an award date.
- Copy `role_title` verbatim from the position line or section heading next to the person. Project responsibility
  belongs in `role` and its supporting `snippet`; do not invent an academic title from a funding programme.
- Attach ORCID or a verified OpenAlex/person identifier only when it belongs to that person. Project references,
  grant IDs and institution IDs belong in `note` or project evidence, never as person merge keys.
- `national_project` and `national_fellowship` use the schema's existing open signal vocabulary. They deliberately
  do not use `erc_`, `dfg_` or `snsf_` prefixes. They do not activate the existing funding-based professor/group-leader
  inference; current roles must be established through the normal title/affiliation evidence workflow.
- These signals remain available in the normal roster evidence and in the groups export's `active_funding`
  field. Their inclusion there is evidence aggregation, not an inference about the holder's role.

## Budget, overlap and output

Write `signals/funding-fr-es-nl-be.jsonl` and `signals/funding-fr-es-nl-be.coverage.md`. The page budget covers the
whole enabled channel (ANR and NWO), including follow-up hops, failed fetches and replacement pages. API/dataset
downloads follow the existing run budget policy; they do not grant unlimited page reads for person verification.
Record attempts and results by source/country so a budget-limited sweep is distinguishable from no matches.

The worker brief should identify any overlapping programmes already assigned to `national-prizes` (for example,
NWO personal grants). Assign each identical award record to one channel before sweeping; do not emit the same event
in two channels merely to increase `channels_hit`. Distinct awards and separately dated outputs remain valid signals.
ERC/CORDIS projects remain owned by `funding-eu` even when their hosts are in these four countries.

Coverage must list sources and queries used, date fields chosen, pages attempted, records reviewed, person hops
completed, unresolved roles/countries/dates, duplicate events skipped, and portals or countries left unfinished.
Use the existing channel-parallel workflow. This channel owns its two output files and its single page budget;
no domain-based orchestration or additional worker protocol is introduced.
