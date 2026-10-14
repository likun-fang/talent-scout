# Optional channel: Austrian, Swedish, Norwegian and Danish funding registers

Channel id: `funding-at-se-no-dk`. The national registers of AT, SE, NO and DK name each grant's project leader with
the institution. They sit in `region_extended`, not the core, so the channel is optional: enable it by listing the id
and its page budget in the run's `channels` and in the worker brief. ERC grants held in these countries stay with
`funding-eu.md`.

Read the shared [signal, member-page and date rules](README.md) and the [hop rules](../30-hops.md). The person names
come from the funders' public grant announcements. Keep the name, institution, identifiers and project fields named
below, and drop everything else a record carries (gender, amounts beyond the approval check).

Checked live on 2026-10-14. URLs opened:
`https://openapi.fwf.ac.at/fwfkey`, `https://openapi.fwf.ac.at/indexes`,
`https://openapi.fwf.ac.at/indexes/projects/documents?limit=1000&offset=0` (and every offset to 20000),
`https://openapi.fwf.ac.at/indexes/projects/search` (POST), `https://openapi.fwf.ac.at/indexes/output/search` (POST),
`https://www.fwf.ac.at/en/discover/open-api`, `https://www.fwf.ac.at/en/discover/open-api/queries`,
`https://doi.org/10.55776/STA235`, `https://www.fwf.ac.at/en/funding/portfolio/careers/fwf-astra-awards`,
`https://www.fwf.ac.at/en/funding/portfolio/careers/esprit`,
`https://www.fwf.ac.at/en/funding/portfolio/careers/erwin-schroedinger`, `https://api.ror.org/v2/organizations/054pv6659`;
`https://www.vr.se/english/swecris/swecris-api.html`, `https://www.vr.se/english/swecris.html`,
`https://www.vr.se/swecris/swecris-api/manual-kom-igang-med-swecris-api.html`,
`https://swecris-api.vr.se/swagger/SweCRISOpenAPISpecificationv1.0/swagger.json`,
`https://swecris-api.vr.se/v1/projects?page=1&size=1`, `https://swecris-api.vr.se/v1/funders`,
`https://swecris-api.vr.se/v1/scp/search?searchText=robot&page=1&size=2`,
`https://swecris-api.vr.se/v1/scp/export?searchText=machine%20learning&page=1&size=2000&token=…`,
`https://www.vr.se/english/swecris.html#/project/2024-05867_VR` (rendered);
`https://raw.githubusercontent.com/Forskningsradet/open-data/main/datasets/soknader2/dataset.csv`, its `fields.csv` and
`README.md`, `git ls-remote https://github.com/Forskningsradet/open-data refs/heads/main`,
`https://www.forskningsradet.no/tall-analyse/statistikk/offentlige-data/`, `https://prosjektbanken.forskningsradet.no/`,
`https://prosjektbanken.forskningsradet.no/project/FORISS/338694`,
`https://prosjektbanken.forskningsradet.no/project/FORISS/354071`.

## Keys

A key lives in `~/.config/talent-scout/<source>.key` with mode 600, outside the repository and the run directory.
Briefs, notes and coverage name the path, never the value. Read it at call time:
`-H "Authorization: Bearer $(cat ~/.config/talent-scout/fwf.key)"`.

| Source | File | Where it comes from | Registration | Quota |
|---|---|---|---|---|
| FWF | `fwf.key` | the whole body of `https://openapi.fwf.ac.at/fwfkey` (one 64-character hex string) | none | not stated |
| Swecris | `swecris.key` | the public token printed on `https://www.vr.se/english/swecris/swecris-api.html` (on 2026-10-14: valid from 2026-04-09; VR changes it "on a regular basis") | optional: a personal token from the form at `https://www.vr.se/english/swecris/swecris-api/request-for-api-token.html` (first name, surname, e-mail; organisation optional), sent by e-mail within a week | not stated |
| RCN | none | a public CSV on GitHub | none | — |

When FWF answers 403 `invalid_api_key`, fetch the key page again: the page always serves the current key. When the
Swecris export answers 401, copy the token from VR's page again.

## FWF Open API (AT)

A Meilisearch instance over the FWF's own project records, rebuilt daily (the three indexes `projects`, `output` and
`further-funding` all showed `createdAt` 2026-10-14). The data are CC0 according to the Open API page. On 2026-10-14
the `projects` index held 20,576 documents, the newest approved on 2026-10-13.

Every call needs the Bearer header; without it the answer is 401 `missing_authorization_header`. The index has no
filterable or sortable attributes: `filter` returns `invalid_search_filter` and `sort` returns `invalid_search_sort`,
so programme and date are filtered locally.

**Search** — POST JSON:

```sh
curl -s -X POST 'https://openapi.fwf.ac.at/indexes/projects/search' \
  -H "Authorization: Bearer $(cat ~/.config/talent-scout/fwf.key)" -H 'Content-Type: application/json' \
  -d '{"q":"robot learning","matchingStrategy":"all","limit":1000}'
```

- Send `"matchingStrategy":"all"`. The default drops words from the end of the query until something matches:
  `robot learning` gave 354 hits by default and 34 with `all`. A quoted phrase (`"q":"\"robot learning\""`) gave 1.
- The documents carry German and English fields, so run the German keyword too (`Robotik`).
- `limit` and `offset` page through hits; `estimatedTotalHits` is an estimate. Offset 1000 still returned hits, so no
  1,000-hit cap applies here.
- **Bulk**: `GET /indexes/projects/documents?limit=1000&offset=<n>&fields=<comma-separated names>` pages through the
  whole index in 21 calls. Use it when keyword search misses the domain's vocabulary; keep only matched rows in
  signals and the download in `RUN_DIR/cache/fwf/`.

**Fields** of a project document (2026-10-14): `id` (`projects-<FWF number>`), `_str.grantdoi` (`10.55776/<number>`),
`_str.url`, `_str.program.en` / `.de`, `_str.call.en`, `_date.approvaldate`, `_date.startdate`, `_date.enddate`,
`_str.status.en` (Ongoing, Pending, Ended, Withdrawn), `_str.projecttitle.en` / `.de`, `_list.keywords.split`,
`_list.researchdisciplines.en`, `_str.researchfields.en`, `_long.approvedamount`,
`_str.principalinvestigator.role` (German label: `Projektleiter:in`, `Koordinator:in`, `Antragsteller:in`, or
`Director of Research`), `_str.principalinvestigator.firstname`, `.lastname`, `.orcid` (bare iD), `.orcidlink`,
`.webpage`, `.researchinstitute.name`, `.researchinstitute.ror` (a full `https://ror.org/…` URL),
`_list.researchinstitutes`, `_list.nationalprojectparticipants.en`, `_list.internationalprojectparticipants.en`,
`_list.connected.output`, `_str.prproposalsummary.en` / `_str.prfinalreport.en` (when present),
`_str.scientificboardmeeting`.

Of the 2,413 projects approved from 2023-10-14 to 2026-10-13, 2,404 carry an ORCID and 2,389 a ROR. Applicants have
had to give an ORCID since 2016, so the ORCID is the merge key here, not the name.

| `_str.program.en` | signal_type | strength | what the role means |
|---|---|---|---|
| FWF START Awards (last approved 2024), FWF ASTRA Awards (from 2025) | `fwf_start` | high | career awards for researchers who already work independently. START is now listed under expiring programmes; ASTRA, launched July 2024, is for advanced postdocs to "acquire the necessary qualifications for academic leadership positions" |
| ESPRIT | `fwf_esprit` | medium | postdocs early in their career act as principal investigator of one independent project: stage 4 classes the holder as researcher |
| Erwin Schrödinger | `national_fellowship`, `role: pi` | medium | an outgoing postdoc fellowship for a project abroad. The record names the Austrian home institution, not the host abroad, so it gets no funding-role inference and no country from the record |
| FWF Wittgenstein Award | `fwf_project` | high | an Austrian Science Award for an established researcher, funding the holder's research |
| Principal Investigator Projects, Principal Investigator Projects International, International – Multilateral Initiatives, Clinical Research, 1000 Ideas, Arts-Based Research, Emerging Fields, Special Research Areas, Research Groups, Clusters of Excellence, doc.funds, doc.funds.connect, Elise Richter, #ConnectingMinds – Projects | `fwf_project` | medium | the named person leads or coordinates the project |
| Book Publications, Digital Publications, Academic Journals, Science Communication, Top Citizen Science, #ConnectingMinds – Workshops | none | — | publication and outreach subsidies, not research leadership |

Emit one `person` signal per kept project:

- `name_raw`: `firstname` + `lastname` as printed. `role: pi`. `channel: funding-at-se-no-dk`.
- `affiliation_raw`: `researchinstitute.name`. `country`: from the ROR record,
  `GET https://api.ror.org/v2/organizations/<ror id>` → `locations[0].geonames_details.country_code`; leave it empty
  for Erwin Schrödinger.
- `ids.orcid`: `principalinvestigator.orcid`. `ids.ror`: `researchinstitute.ror` as printed. The ROR names the
  institution, not the person; stage 4 uses it to compare institutions and never to merge people.
- `homepage`: `principalinvestigator.webpage` when present.
- `date`: `_date.approvaldate`, the Board decision (`_str.scientificboardmeeting` names the meeting). It is a full date,
  so window filtering is exact. A `Pending` project is approved and not yet started; keep it. Skip `Withdrawn`.
- `evidence_url`: `https://doi.org/<_str.grantdoi>`. It redirects to the English research-radar page;
  `_str.url` points at the older `fwf.ac.at/forschungsradar/…` path, which redirects too.
- `snippet`: programme, English title, the role label and the approval date. The summaries carry `\r\n`; collapse
  whitespace before copying.
- `role_title`: leave empty. `Projektleiter:in` and `Koordinator:in` are funding roles, not positions; keep them in
  `snippet`.
- `topics`: 1–3 phrases cut verbatim from `_str.projecttitle.en`; `_list.keywords.split` entries may be copied as
  they are.

`_list.nationalprojectparticipants.en` and `_list.internationalprojectparticipants.en` list collaboration partners
and mentors as `Name, Institution (ROR), role`. They go into `note`, like GEPRIS cooperation partners; they are not PIs.
doc.funds programmes are doctoral schools: their member pages follow the shared `lab_member` rules.

`_list.connected.output` holds ids in the `output` index, searchable by quoting the id
(`"q":"\"output-32145\""`). An output document has `_str.doi`, `_str.title`, `_list.year`, `_list.author`
(`Renaudo E` style) and `_list.connected.projects`. A dated output in the window can qualify an author through the
`work` hop.

When this channel runs, it owns the FWF START, ASTRA and Wittgenstein records; `national-prizes` skips its FWF entry
(`swept_by` in `assets/national-prizes.yaml`).

## Swecris (SE)

The national project database that the Swedish Research Council (VR) keeps for the government. It holds grants from
governmental and private funders to organisations in Sweden; `https://www.vr.se/english/swecris.html` lists each
funder's years and update rhythm (VR and Vinnova from 2008, continuously; the Swedish Energy Agency from 2010, once a
year).

Two routes, tested 2026-10-14 with the public token:

- The REST routes of the Swagger spec (`/v1/projects`, `/v1/persons/…`, `/v1/funders`, `/v1/scp/search`, …) answered
  401 with no body, with the token sent as `Authorization: Bearer` (the method VR's manual names), as a bare
  `Authorization` value and as a `token` query parameter. Not verified: whether a personal token opens them.
- The export route `GET https://swecris-api.vr.se/v1/scp/export`, which is in the same Swagger spec, returned a CSV.
  Without `token` it answers 401 `{"message":"Unauthorized"}`. A made-up token value also got 200, so a 200 here does
  not prove the token is still current.

Use the export route:

```sh
curl -s -G 'https://swecris-api.vr.se/v1/scp/export' --data-urlencode 'searchText=robot learning' \
  --data-urlencode 'year[]=2024' -d page=1 -d size=2000 \
  --data-urlencode "token=$(cat ~/.config/talent-scout/swecris.key)" -o "$RUN_DIR/cache/swecris/robot-learning-2024.csv"
```

The token sits in the URL, so record the query in coverage without it. `searchText` matches abstracts as well as
titles (CLEAR-BOT came back for `robot learning` through its abstract); `machine learning` returned 1,146 projects with
funding years up to 2026. `year[]` filters on `FundingYear` (`year[]=2024` gave 121 rows, all 2024); repeat it for
each window year, or drop it and filter locally.
Other filters: `fundingOrganisation[]`, `organisationType[]`, `scbIds[]` (Swedish subject codes).

The file is semicolon-separated UTF-8 with a BOM and carries stray NUL bytes (68 in a 4.7 MB file); strip them before
the CSV parser, which otherwise stops with "line contains NUL". One row per project. Columns: `ProjectId` (the
suffix names the funder: `_VR`, `_Vinnova`, `_Energi`, `_Formas`, `_HLF`, `_Forte`, `_KI`, `_RJ`, …),
`ProjectTitleSv`, `ProjectTitleEn`, `ProjectAbstractSv`, `ProjectAbstractEn`, `ProjectStartDate`, `ProjectEndDate`,
`CoordinatingOrganisationId`, `CoordinatingOrganisationNameSv`, `CoordinatingOrganisationNameEn`,
`CoordinatingOrganisationTypeOfOrganisationSv`, `CoordinatingOrganisationTypeOfOrganisationEn` (University, Company,
Governmental, University College, Non profits & Foundations, Other), `FundingOrganisationId`,
`FundingOrganisationNameSv`, `FundingOrganisationNameEn`, `FundingOrganisationTypeOfOrganisationSv`,
`FundingOrganisationTypeOfOrganisationEn`, `FundingsSek`, `FundingYear`, `FundingStartDate`, `FundingEndDate`,
`TypeOfAwardId`, `TypeOfAwardDescrSv`, `TypeOfAwardDescrEn`, `UpdatedDate`, `LoadedDate`, `InvolvedPeople`, `Scbs`.

`InvolvedPeople` packs every person into one field: `¤¤¤<person id>¤<full name>¤<ORCID or empty>¤<role EN>¤<role SV>¤<gender>`,
repeated. Roles seen: `Principal Investigator` / `Projektledare` and `Co-Investigator` / `Projektdeltagare`. Drop the
gender element. The person id is not a merge key: 61 of 1,071 ORCIDs in the test export sat under more than one id,
some with different name spellings. The ORCID is filled in 1,496 of 2,203 entries.

Swedish Energy Agency projects often have an empty `InvolvedPeople` (71 of 137 rows in the test export): VR's page
says their project leaders are not shown "due to the principle on data minimisation in GDPR". Such a project gives
an `org` signal for the coordinating organisation, `role: unknown`, `signal_type: national_project`, and no person.

| `TypeOfAwardDescrEn` | signal_type | strength |
|---|---|---|
| Project grant, Research environment, Unclassified (most Vinnova and Energy Agency rows) | `swecris_project` | medium |
| Grant for positions or stipends | `national_fellowship`, `role: pi` (personal funding, no funding-role inference) | medium |
| Research infrastructure | none: equipment and facilities, not a research project | — |

Emit one `person` signal per `Principal Investigator`:

- `name_raw`: the full name as packed. `role: pi`. `ids.orcid` when present; put the Swecris person id in `note`.
- `affiliation_raw`: `CoordinatingOrganisationNameEn`, the organisation that administers the grant; Swecris names no
  department. `country: SE`: Swecris covers funding to organisations in Sweden. A `Company` coordinator stays as
  printed; stage 4 reads the company name.
- `date`: the date part of `ProjectStartDate` when it is on or before the run date, otherwise `FundingYear`; say which
  in `note`. Swecris has no decision date.
- `evidence_url`: `https://www.vr.se/english/swecris.html#/project/<ProjectId>`. The page is client-rendered: read it
  with `visit_page.py --browser`; it prints the title, the project period and the abstract.
- `snippet`: `TypeOfAwardDescrEn`, `FundingOrganisationNameEn`, the English title and the role label.
- `role_title`: leave empty; `Principal Investigator` is the funder's role label, kept in `snippet`.
- `topics`: 1–3 phrases cut verbatim from `ProjectTitleEn`, or `ProjectTitleSv` when the English title is empty
  (9 of 1,146 rows).

Co-Investigators go into the PI signal's `note`, like GEPRIS cooperation partners: the record does not say whether
they work in the PI's group or lead their own elsewhere.

## Research Council of Norway (NO)

The Research Council of Norway (RCN, Forskningsrådet) publishes every application it has received since 2004, granted
and rejected, as one CSV on GitHub: `https://raw.githubusercontent.com/Forskningsradet/open-data/main/datasets/soknader2/dataset.csv`.
No key. On 2026-10-14 it was 54 MB with 88,268 rows, last updated 2026-08-27. RCN's page says the data are registered
in the national data catalogue; neither that page nor the repository states a licence. Not verified: the licence.

Download it once into `RUN_DIR/cache/rcn/`; it is a dataset download, not a page. Pin the version for evidence:
`git ls-remote https://github.com/Forskningsradet/open-data refs/heads/main` prints the commit (on 2026-10-14
`e05cc7afff5ea24fe5513a55ababd642e68eaf84`), and
`https://raw.githubusercontent.com/Forskningsradet/open-data/<commit>/datasets/soknader2/dataset.csv` keeps serving
that version. The bare git call works where the GitHub REST API is blocked.

The file is comma-separated UTF-8 without a BOM. Titles contain line breaks (3,471 rows), so read it with a CSV
parser, never line by line. One row per application or project. Columns (`fields.csv` describes each in Norwegian):
`prosjektnummer`, `prosjekttittel`, `soknadsfrist`, `soknadsdato`, `utlysnings_id`, `utlysningsaktivitet`,
`utlysningtittel`, `prosjekttype`, `soknadstype`, `soknadstypevariant`, `sokstart`, `sokslutt`, `prosjektfase`,
`prosjektstart`, `prosjektslutt`, `prosjektleder_kjonn`, `prosjektansvarlig_type`, `prosjektansvarlig_navn`,
`kortnavn`, `organisasjonsnummer`, `kp1`, `kp2`, `sektor`, `kategori`, `kommune`, `kommunenummer`, `fylke`,
`fylkenummer`, `landsdel`, `virkemiddel_sekvens`, `virkemiddel`, `hovedaktivitet_sekvens`, `hovedaktivitet`,
`aktivitet`, `aktivitet_kode`, `fagomraade`, `fag`, `fagdisiplin`, `dr_stip_aarsverk`, `postdok_aarsverk`,
`sokt_belop`, `tildelt_belop`, `prosjektleder`.

**Granted rows only.** Rejected applications name their project leader too. Keep a row when `prosjektfase` is
`Bevilgning` (granted, running) or `Avsluttet` (granted, finished) and `tildelt_belop` is above 0. The amount alone is
not enough: 150 rows still in `Vurderes` (under assessment) already carry an amount. The other phases are `Avslag`
(rejected) and `Mottatt` (received).

**2026.** The CSV holds 1,466 granted projects starting in 2026 and calls with deadlines up to 2026-06-03. Its README
warns that it holds no data from RCN's new case system, Tibi, and the Prosjektbanken front page says 2026 data are not
shown for a period after the system change. So 2026 is partial: grants handled in the old system are in, grants
handled in Tibi are not. Say so in coverage.

| `soknadstype` (`soknadstypevariant`) | signal_type | strength |
|---|---|---|
| Forskerprosjekt (Fornyelse, Unge forskertalenter, Stort, tverrfaglig forskerprosjekt, Radikal nyskapende forskning), Kompetanse- og samarbeidsprosjekt, Innovasjonsprosjekt, Internasjonale utlysninger, Forskningssenter | `rcn_project` | medium |
| Forskerprosjekt (Internasjonalt mobilitetsstipend) | `national_fellowship`, `role: pi` (personal mobility grant, no funding-role inference) | medium |
| Koordinerings- og støtteaktivitet, Forskningsinfrastruktur, institutional support types, Støtte fra andre enn Forskningsrådet, Ingen søknadstype | none: networks, events, proposal support, equipment, core funding | — |
| Kommersialiseringsprosjekt | none here; a domain-relevant one is a lead for `startups.md` | — |

Emit one `person` signal per kept row:

- `name_raw`: `prosjektleder`. `role: pi`. The CSV carries no ORCID or person id, so these signals merge on name plus
  institution until stage 4 finds an identifier.
- `affiliation_raw`: `prosjektansvarlig_navn` as printed. RCN files the grant at the lowest unit, so it is often a
  department or faculty ("Økonomisk institutt"); `kortnavn` names the parent (UIO, NTNU) and is filled mostly for
  universities and institutes. Put `kortnavn` and `organisasjonsnummer` (0 for sub-units) in `note`.
  `sektor: Næringsliv` means a company holds the grant; stage 4 reads the company name.
- `country: NO`, except `sektor: Utlandet`, where it stays empty.
- `date`: `prosjektstart`, a year; say "project start year" in `note`. The CSV has no decision date, and
  `soknadsfrist` / `soknadsdato` are the call deadline and the submission, both before the decision.
- `evidence_url`: `https://prosjektbanken.forskningsradet.no/project/FORISS/<prosjektnummer>`. The page is plain HTML
  and prints the leader with a title ("Prosjektleder: Professor Konstantinos Alexis"), the period and the amount.
  Projects that started in 2026 are not there yet (`354071`: "ble ikke funnet"); for those, use the pinned CSV URL
  and put `prosjektnummer` in `snippet`.
- `role_title`: the title the Prosjektbanken page prints between "Prosjektleder:" and the name, when that page is read
  ("Professor"). The CSV has none; leave it empty then.
- `snippet`: `soknadstype` / `soknadstypevariant`, `aktivitet`, the title, "prosjektleder".
- `topics`: 1–3 phrases cut verbatim from `prosjekttittel`, line breaks collapsed. Titles come in English or
  Norwegian as submitted; do not translate.

Drop `prosjektleder_kjonn`. `dr_stip_aarsverk` and `postdok_aarsverk` say a project pays doctoral or postdoc years,
not who holds them: look for those people on the leader's team page under the shared `lab_member` rules.
