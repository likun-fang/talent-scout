# Optional national funding channel: validated ANR, NWO, FRIS, FNRS and AEI paths

Channel id: `funding-fr-es-nl-be` (reserved geographic scope). ANR (FR), NWO (NL), FRIS (BE, Flanders) and FNRS
DataScops (BE, Wallonia–Brussels) extraction is enabled. AEI (ES) gives projects and institutions; its people come
from hops.
This is an opt-in sibling of `funding-de-ch`, not a replacement. Add it to the
run's `channels` with its own page budget (40 unless the run specifies another budget) and pass it in the worker
brief. Keep the existing eight defaults, region tiers, merge rules and funding-role inference unchanged.

Read the shared [signal, member-page and date rules](README.md) and [hop rules](../30-hops.md). Inputs are the
run's `region_core`, `region_extended`, `window_start`, `window_end` and domain-map keywords. Search only the
validated countries FR, NL, BE and ES that are in `region_extended`; visit core countries first.
The AEI table names no researcher: report ES people as found through hops, never as zero matches. No country or
multimodal keyword is an implicit inclusion criterion: project titles or abstracts must match the domain map.

## Sources and discovery

The official entry pages below were opened on 2026-10-12. Their availability and published search guidance were
checked. A live ANR/NWO sample is recorded in `notes/runs/2026-10-12-multimodal-funding-pilot.md`;
FRIS, DataScops and the AEI table download were read live on 2026-10-14 (below). Read current forms/API documentation
before using filters. Do not assume every portal exposes the same fields or a public bulk API.

| Country | Official entry | Status and follow-up |
|---------|----------------|----------------------|
| FR | [ANR funded projects](https://anr.fr/fr/projets-finances-et-impact/projets-finances/) | Validated detail-page extraction. Search domain keywords; inspect project details and linked project/institution sites. The entry page also links ANR datasets. |
| ES | [AEI awarded grants](https://www.aei.gob.es/ayudas-concedidas/buscador-ayudas-concedidas) | Validated table download, no key. The table has no researcher column: it gives project, reference and institution; people come from the host's pages. Rules below. |
| NL | [NWO API documentation](https://data.nwo.nl/en/how-to-use-the-nwopen-api) | Validated API extraction. Use the documented Projects endpoint or linked project database. Inspect titles, summaries, researchers, institutions and outputs where supplied. |
| BE | [FWO funded research](https://www.fwo.be/en/results-outreach/database-financed-research/) | Validated through FRIS, which FWO's page points to: SOAP services at `https://frisr4.researchportal.be/ws/`, no authentication. FRIS also holds university, VLAIO and EU projects of Flemish institutions. Rules below. |
| BE | [FNRS DataScops entry](https://www.frs-fnrs.be/fr/recherches-financees-par-le-fnrs-datascops) | Validated through the JSON backend of `https://datascops.frs-fnrs.be`, no key. Rules below. |

- Search English domain-map keywords first. Add relevant French, Spanish or Dutch equivalents to search queries
  where English has poor coverage, recording the actual queries in coverage. Do not translate source quotations.
- FRIS covers Flanders only; DataScops covers FNRS grants at the French-speaking universities. Run both for BE.
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
pages for current titles.

The bulk route, validated on 2026-10-15: the DGDS open dataset on data.gouv.fr ("ANR DGDS depuis 2010 — projets
financés", two CSV files, `…-projets-<date>.csv` and `…-partenaires-<date>.csv`, all projects since 2010, about
27,000 rows). The partners file names every partner's *Responsable scientifique* with ORCID and a coordinator flag;
the projects file gives `Projet.T0 scientifique` as a full date. Gate titles and abstracts locally in French and
English, emit the coordinator and each in-region partner lead as `role: pi` (partner leads with `hop_depth: 1`,
`parent` = the coordinator, "partner scientific lead" in `note`), cite the partners CSV as evidence URL and
title-case the family names, which the data print in capitals. Prefer this to the detail pages: it is one download
instead of one page per project.

### FRIS records (BE, Flanders): validated extraction rules

Read live on 2026-10-14. URLs opened: `https://frisr4.researchportal.be/ws/` (service list),
`https://frisr4.researchportal.be/ws/ProjectService?wsdl`, `…/ws/PersonService?wsdl`, POSTs to `…/ws/ProjectService`,
`…/ws/PersonService`, `…/ws/OrganisationService` and `…/ws/FundingCodeServiceFRIS`, and
`https://www.researchportal.be/en`. Every SOAP call answered 200 without credentials.

Search projects with one POST (`Content-Type: text/xml; charset=utf-8`, `SOAPAction: ""`) to
`https://frisr4.researchportal.be/ws/ProjectService`:

```xml
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:fris="http://fris.ewi.be/" xmlns:crit="http://fris.ewi.be/criteria">
 <soapenv:Body><fris:getProjects><crit:projectCriteria>
  <crit:window><crit:pageSize>500</crit:pageSize><crit:pageNumber>0</crit:pageNumber></crit:window>
  <crit:name><crit:search>robot</crit:search></crit:name>
 </crit:projectCriteria></fris:getProjects></soapenv:Body>
</soapenv:Envelope>
```

- `name` searches titles (`robot`: `totalResults` 466). The WSDL lists the other criteria: `keyword`, `uuids`,
  `associatedPersons`, `associatedOrganisations`, `fundingCode`, `typeClassification`, `lastModifiedDate`. The
  `keyword` criterion answers a SOAP fault (HTTP 500) with and without a locale, and some title words ("beeld") fault
  too, so search titles only, one term per call, in English and Dutch; a project whose title avoids the domain words
  is missed and the coverage note says so.
- `pageNumber` is echoed back but ignored: pages 0 to 3 returned the same first two projects. Set `pageSize` at or
  above `totalResults` (500 returned all 466 in one 5 MB response) or narrow the query. Cache responses under
  `RUN_DIR/cache/fris/`.
- The response is CERIF 1.5 XML. Each `cfProj` has `cfProjId` (a UUID), `cfStartDate`, `cfEndDate`, `cfAcro`,
  `cfURI` (a project website, on 22 of 100 projects), `cfTitle` and `cfAbstr` (`cfLangCode` en/nl), `cfKeyw`,
  `cfProj_Class` (scheme "Project Type": `PhD`, `Collaboration`, `Post-doctoral`; half the `robot` projects have
  none), `cfFedId` (institution and funder references), `cfProj_Fund` (`cfFundId`, `cfClassId` Principal Funding,
  Complementary Funding, …) and `frParticipant`.
- `frParticipant` with scheme "Project Person Participant Role" names a role: `Promoter`, `Co-promoter`, `Fellow`,
  `Collaborator`. Names are rarely inline (17 of 99 Promoters had `cfFirstNames` / `cfFamilyNames`). The usual entry
  carries only `frAssignmentId`; the top-level `frAssignment` with that id gives `cfPersId` and `cfOrgUnitId`.
- People: POST `getPersons` to `…/ws/PersonService` with `<crit:personCriteria>` holding the window and
  `<crit:uuids><crit:identifier>…</crit:identifier>…</crit:uuids>`, several ids per call. A `cfPers` has
  `cfPersName_Pers` (`cfFirstNames`, `cfFamilyNames`), `cfFedId` with `cfClassId` `ORCID` (→ `ids.orcid`) or an
  institution's staff number, and `frAssignment` (unit, start, end; an end of `9999-12-31` is open). It also links a
  work postal address and e-mail addresses (`cfPers_PAddr`, `cfPers_EAddr`): never fetch or store them.
- Units: POST `getOrganisations` to `…/ws/OrganisationService` with `<crit:organisationCriteria>` and `uuids`.
  `cfName` gives the unit ("Robotics, Automation and Mechatronics (RAM)"); `cfOrgUnit_OrgUnit` with `cfClassId`
  `Child` points to the parent in `cfOrgUnitId2`. Walk up to the institution.
- Funders: `getFundingCodes` on `…/ws/FundingCodeServiceFRIS` takes an unqualified `<criteria>` element (a
  `fundingCodeCriteria` element is a fault). Codes `7003`, `7010`, `7021`, `7028` are "FWO contract id", `54xx` "BOF
  contract id", `5435` "IOF contract id". The call returned 500 of 706 codes and paging is ignored here too, so `1000`
  and `8000`, both common, stayed unresolved; keep the raw code in `note`.
- The public project pages on `https://www.researchportal.be/en/project/<slug>` answered 403 (an Akamai "Access
  Denied") to plain HTTP and to a headless browser. The slug comes from the English title, not the UUID (Wayback
  holds pages such as `/en/project/3d-cellmap-unveiling-complex-cellular-interactions-tissues-through-3d-super-resolution`).

| FRIS role (project type) | signal |
|---|---|
| `Promoter` | `person`, `role: pi`, `signal_type: fris_project`, strength medium. The record labels project leadership explicitly, so the funding-role rule applies as for GEPRIS applicants |
| `Fellow` in a `PhD` project | `person`, `signal_type: national_fellowship`, `role: team_member`, `parent` = the Promoter's `name_raw`, `hop_depth: 1`. The Fellow is the doctoral researcher the project funds and the Promoter supervises: both fellows sampled joined the Promoter's unit the month their project started |
| `Fellow` in a `Post-doctoral` project | `person`, `signal_type: national_fellowship`, `role: pi`: a personal postdoc fellowship, no funding-role inference |
| `Co-promoter`, `Collaborator`, a `Fellow` elsewhere | `note` on the Promoter's signal; co-promoters often lead their own group |

- `name_raw`: first and family names from the person record. `ids.orcid` when present.
- `affiliation_raw`: `<institution> || <unit>` from the participant's assignment, the institution first so that
  stage 4 compares institutions on the first segment. `country: BE`.
- `date`: `cfStartDate`; FRIS has no award date. Say "project start" in `note`.
- `evidence_url`: the researchportal.be project URL when a web search for the title returns it; otherwise `cfURI`;
  otherwise `https://frisr4.researchportal.be/ws/ProjectService` with `cfProjId` in `note` and the cached response.
- `snippet`: project type, the role label, the funding code description when resolved, the English title.
- `role_title`: leave empty; Promoter and Fellow are register roles. `topics`: 1–3 phrases cut verbatim from the
  English `cfTitle`.

### FNRS DataScops records (BE, Wallonia–Brussels): validated extraction rules

Read live on 2026-10-14. URLs opened: `https://datascops.frs-fnrs.be/` and its scripts (`main-3F7PFGLH.js`),
`https://datascops.frs-fnrs.be/public2/rest/datascops/application-search/0/search?language_code=en` (POST),
`https://datascops.frs-fnrs.be/public2/rest/datascops/datascops/40041825?language_code=en`. The page is an Angular
application; a headless browser showed the JSON calls it makes, and both answered 200 to curl without login.

```sh
curl -s -X POST 'https://datascops.frs-fnrs.be/public2/rest/datascops/application-search/0/search?language_code=en' \
  -H 'Content-Type: application/json' \
  -d '{"query":{"condition":"and","rules":[]},"sortKeys":{},"page_from":1,"page_size":30,"full_text_query":"robot","pageIndex":1,"facetFilters":{},"language_code":"en"}'
```

- The answer has `count` (a string; `robot`: 134), `rows` and `facets`. Thirty rows come back per page whatever
  `page_size` says; raise `page_from` and `pageIndex` together (page 2 gave rows 31–60).
- A row: `id_application`, `annee` (call year), `appel_en` (call), `nom_instrument_en`, `titre_application_en`,
  `titre_application_fr`, `resume_application_en`, `date_debut_effective`, `date_fin_effective`, `institution`,
  `nom_applicant`, `tags` (Finished, In progress) and `contacts[]` with `prenom`, `nom`, `institution`,
  `id_type_application_contact` and `libelle_contact`. The UI lists these as funded projects; every row seen had
  status id 242.
- Contact labels seen: `Applicant` (`APPL`), `Promoter` (`PROM`), `Co-promoter` (`COPROM`), `Co-tutelle`,
  `Co-applicant`. Fellowships (Research Fellow, FRIA, FRESH, Postdoctoral Researcher, Research Associate) name the
  holder as Applicant and the supervisor as Promoter. Project instruments (Research Project, Research Credit,
  Incentive grant for scientific research, WEL-T, Incitant Horizon Europe) name an Applicant and no Promoter.
- One application: `GET https://datascops.frs-fnrs.be/public2/rest/datascops/datascops/<id_application>?language_code=en`
  returns the same fields plus `type_appel` and `categorie_type_appel`. Use it as `evidence_url`.
- The `sexe` facet is a gender breakdown: never store it.

| Record shape | signal |
|---|---|
| a `Promoter` is named | Promoter: `person`, `signal_type: national_project`, `role: pi`. Applicant: `person`, `signal_type: national_fellowship`, `role: team_member`, `parent` = the Promoter's `name_raw`, `hop_depth: 1`; the Applicant holds the fellowship in the Promoter's group |
| no `Promoter` (project instruments) | the sole Applicant: `person`, `signal_type: national_project`, `role: pi`. With no Promoter on the record, the Applicant is the grant holder; NWO's rule against applicants does not apply, because NWO lists a separate project leader |
| Equipment | none: an equipment grant, not a research project |

Co-promoters, co-tutelle partners and co-applicants go into `note`. `name_raw`: `prenom` + `nom` from `contacts`
(`nom_applicant` prints the family name in capitals). `affiliation_raw`: the contact's `institution`; `country: BE`.
`date`: `date_debut_effective` when on or before the run date, otherwise `annee`; say which in `note`.
`role_title`: leave empty. `topics`: 1–3 phrases cut verbatim from `titre_application_en`, or the French title when
there is no English one.

### AEI records (ES): table download, people by hop

Read live on 2026-10-14. URLs opened: `https://www.aei.gob.es/ayudas-concedidas/buscador-ayudas-concedidas`,
`…/buscador-ayudas-concedidas?year=2024&title=robot`,
`https://www.aei.gob.es/ayudas-concedidas/buscador-ayudas-concedidas/download/2024/All/All/All?title=robot`, and a
university's copy of an AEI resolution annex, `https://investiga.uva.es/files/2025/06/DATOS-2023-orientada-1.pdf`.

The finder is a plain GET form: `year`, `convocatory`, `code` (reference), `gender`, `area`, `subarea`, `title`,
`keywords`, `cif`, `name` (the institution), `ccaa`, `province`, `granted[min]`, `granted[max]`, `summary`. A results
page prints a "Descargar archivo" link, `/ayudas-concedidas/buscador-ayudas-concedidas/download/<year>/All/All/All?<the
text filters>`, which returns a CSV attachment: semicolon-separated UTF-8 with a BOM, one row per grant. Columns:
`Año`, `Convocatoria`, `Referencia`, `Género`, `Área`, `Subárea`, `Título`, `C.I.F.`, `Entidad`, `CC.AA.`,
`Provincia`, `€ Conced.`, `Resumen`. `year=2024&title=robot` gave 53 rows. `Resumen` was empty on 14 of them.

There is no researcher column. `Género` gives the gender of a person the table does not name: never store it. The
resolution annex ("Anexo I. Relación de ayudas concedidas") lists reference, title, centre, years and budget, and no
researcher either. A web search for one 2024 reference (`PID2024-161069OB-C31`) returned no page naming its
investigator on 2026-10-14.

- For each table row whose title or summary matches the domain map, emit an `org` signal: `name_raw` = `Entidad`,
  `role: unknown`, `signal_type: national_project`, `date` = `Año` (the call year; say so in `note`), the reference,
  `Convocatoria` and title in `snippet`, `evidence_url` = the download URL with its filters. `country: ES`.
- Hop to people through the reference: the institution's research portal or project page, the project website, or
  the acknowledgement of a paper. Emit a `person` with `signal_type: aei_project`, `role: pi` only when that page
  names the person as "Investigador/a principal" (IP, IP1, IP2) of that reference; the page is the `evidence_url`,
  `parent` = the `org` signal's `name_raw`, `hop_depth: 1`. Co-IPs both count as `pi`.
- Personal schemes in `Convocatoria` (Juan de la Cierva, Ramón y Cajal, Contratos Predoctorales, Torres Quevedo) fund
  a person, not a project: a named holder found by hop gets `national_fellowship`, with the scheme in `snippet`.
- `topics`: cut verbatim from `Título`; some titles are in capitals without accents, copy them as printed.

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
- `fris_project` (FRIS Promoters) and `aei_project` (an IP named on a page for that reference) are register-prefixed
  types like `dfg_project` and do trigger the funding-role rule (group leader, medium), because the source labels
  project leadership explicitly.
- `national_project` and `national_fellowship` use the schema's existing open signal vocabulary. They deliberately
  do not use `erc_`, `dfg_` or `snsf_` prefixes. They do not activate the existing funding-based professor/group-leader
  inference; current roles must be established through the normal title/affiliation evidence workflow.
- These signals remain available in the normal roster evidence and in the groups export's `active_funding`
  field. Their inclusion there is evidence aggregation, not an inference about the holder's role.

## Budget, overlap and output

Write `signals/funding-fr-es-nl-be.jsonl` and `signals/funding-fr-es-nl-be.coverage.md`. The page budget covers the
whole enabled channel (ANR, NWO, FRIS, DataScops and AEI), including follow-up hops, failed fetches and replacement pages. API/dataset
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
