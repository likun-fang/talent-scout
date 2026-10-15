# Channel: core-region funding registers (DFG GEPRIS, SNSF data portal)

The two national registers of the core region name each grant's PI with institution, subject area and funding
programme, and need no key. ERC grants held in DE and CH come from `funding-eu.md`; this channel adds the national
programmes, and the Research Training Groups and International Max Planck Research Schools whose member pages are the
main public source for doctoral students.

Checked live on 2026-10-12. URLs opened:
`https://gepris.dfg.de/backend/project/search` (POST), `https://gepris.dfg.de/backend/project/get?id=572962544&ranking=0`,
`https://gepris.dfg.de/project/572962544`, `https://data.snf.ch/datasets/grants.csv`,
`https://data.snf.ch/datasets/persons.csv`, `https://data.snf.ch/grants/grant/234742`, `https://www.mpg.de/en/imprs`.

## DFG GEPRIS (gepris.dfg.de)

GEPRIS is a JavaScript application. The old search links (`gepris/OCTOPUS?task=doSearchSimple&…`) answer 301 to
`/project/results` and drop the query; old project links (`gepris/projekt/<id>`) still redirect to `/project/<id>`.
Read it through the JSON backend the application uses.

**Search** — POST JSON; a GET to the same path returns HTTP 200 with an HTML "Request Rejected" page, so check the
content type:

```sh
curl -s -X POST 'https://gepris.dfg.de/backend/project/search' -H 'Content-Type: application/json' \
  -d '{"query_string":"<keywords>","dfg_verfahren_1":["ENP"],"fachkolleg":["4.43"],"size":"50","from":"0","sort":"prj_beginn_jahr:desc"}'
```

- `query_string`: full text over German and English titles, abstracts and listed publications, with stemming. Run the
  English and the German keyword (`robot learning`, `Robotik`). The full text reaches into listed publications, so
  most hits are noise (a multimodal-AI run saw 888 of 1,069 hits without the domain words in title or abstract):
  keep a project only when `prj_titel_en` / `PRJ_ABSTRACT_EN` matches the domain map, and count the rest in
  Coverage as rejected.
- `dfg_verfahren_1`: programme key (table below). Omit it to get all programmes.
- `fachkolleg`: DFG review board such as `4.41` (systems engineering, robotics) or `4.43` (computer science). The codes
  are in each hit's `fkl_bezeichnung_en` and in `aggregations.fachkolleg` of an unfiltered search. Stage 1 records the
  boards in `register_subject_filters`.
- `size` (at most 50 per page), `from` (offset), `sort: "prj_beginn_jahr:desc"`. Page until `prj_beginn_jahr` drops
  below the window's start year.
- Response: `hits.total`, `hits.hits[]` with `prj_id`, `prj_titel_en` / `prj_titel`, `prj_verfahren_en` (programme
  and sub-programme as printed, e.g. "Emmy Noether Programme Emmy Noether Independent Research Groups"),
  `prj_beginn_jahr`, `prj_ende_jahr`, `prj_foerderzeitraum_en` ("since 2026", "since 2019 to 2024"),
  `fkl_bezeichnung_en` (review board and subject area), `bt_pers[]` (people: `bt_partner_name_komplett` = name with
  academic title, `BTR_BEZEICHNUNG_GRUP` = German role label, `BTR_KEY_GRUP` = role key), `bt_ins_json[]`.
- Count without hits: `GET https://gepris.dfg.de/backend/project/count?query_string=<keywords>&dfg_verfahren_1=ENP`.

**Project** — `GET https://gepris.dfg.de/backend/project/get?id=<prj_id>&ranking=0`:
`data.PRJ_TITEL_EN`, `PRJ_VERFAHREN_KEY`, `PRJ_VERFAHREN_EN`, `PRJ_FOERDERZEITRAUM_EN`, `FKL_BEZEICHNUNG_EN`,
`PRJ_ABSTRACT_EN`, `PRJ_WEBSEITE` (an `<a href>` to the project's own site); `per.<role key>[]` with `id` (the person
id), `data.label_EN` (seen: "Applicant", "Spokesperson", "Persons responsible for project"; "Project Heads", key `PLE`,
on CRC/TRR subprojects) and
`data.beteiligungen_en` (the person's institution and chair as printed); `ins` (applicant institution).

**Person** — `GET https://gepris.dfg.de/backend/person/get?id=<person id>&ranking=0`: `data.PER_ORCID_ID` (often
empty; when present it is `ids.orcid`, the merge key), `INS_NAMEENGLISCH`, `ROOT_NAMEENGLISCH`, `ANS_LAND_EN`.
Take institution and country; leave the street and postcode fields out.

**Evidence URL**: `https://gepris.dfg.de/project/<prj_id>`. Put the person id in `ids.gepris`; it is a strong merge
key in stage 4, like the SNSF person number in `ids.snsf`.

**Without an interpreter**: web search `site:gepris.dfg.de "<keyword>" "Emmy Noether"`, then read each project
through `backend/project/get`, which is a plain GET.

| `dfg_verfahren_1` (label) | sub-programmes as printed (key) | signal_type | what the role means |
|---|---|---|---|
| `ENP` Emmy Noether Programme | Emmy Noether Independent Research Groups (`NWG`, `NWGAI`) | `dfg_emmy_noether` | leads an independent junior research group for six years to qualify for a professorship; postdocs and junior professors, normally up to four years after the doctorate |
| `HEI` Heisenberg Programme | Heisenberg Professorships (`HBP`), Heisenberg Grants (`HEIF`), Heisenberg Fellowships (`SHEI`) | `dfg_heisenberg` | already meets all requirements for a permanent professorship; Heisenberg Professorships hold a professorship at the host university; Grants and Fellowships fund the person's own position; up to five years |
| `GRK` Research Training Groups | Research Training Groups (`GRK`), International Research Training Groups (`GRKI`) | `dfg_project` for the Spokesperson and the Persons responsible for project; doctoral members via the group's site, below | a structured doctoral programme run by a group of PIs |
| `WBP` Walter Benjamin-Programme | Position, Fellowship, Return Grant (`STELL`, `STIP`, `RUEW`) | `dfg_walter_benjamin` | personal postdoc funding: stage 4 classes the holder as researcher, not professor |
| every other programme (`SBH` Research Grants, `SFB` CRCs, `SPP`, `FOR`, `EXC`, …) | as printed | `dfg_project` | the applicant or spokesperson leads the project or subproject |

Emit one `person` signal per person whose label is Applicant, Spokesperson, Persons responsible for project, Project
Heads, or another label that says the person leads the project or a subproject: `role: pi`, `channel: funding-de-ch`,
strength high for `dfg_emmy_noether` and `dfg_heisenberg`, medium for `dfg_project`. Copy `prj_verfahren_en` and the
project title into `snippet`. Other labels (cooperation partners, participating researchers) go into `note`.

## SNSF data portal (data.snf.ch)

The portal's grant search is client-rendered (`https://data.snf.ch/grants?q=<keywords>` in a browser). The structured
route is the open datasets: semicolon-separated, UTF-8 with BOM, CC BY-SA 4.0, both dated the day they were checked:

- `https://data.snf.ch/datasets/grants.csv` (about 64 MB): `GrantNumber`, `Title`, `TitleEnglish`,
  `ResponsibleApplicantName`, `FundingInstrumentPublished`, `FundingInstrumentReporting`, `FundingInstrumentLevel1`
  (Careers, Projects, Programmes, …), `Institute`, `InstituteCity`, `InstituteCountry`, `ResearchInstitution`,
  `ResearchInstitutionType`, `MainDiscipline`, `MainDiscipline_Level2`, `MainFieldOfResearch`,
  `EffectiveGrantStartDate`, `EffectiveGrantEndDate`, `Keywords`, `State` (Approved, Ongoing, Completed),
  `CallFullTitle`, `CallEndDate`, `CallDecisionYear`.
- `https://data.snf.ch/datasets/persons.csv` (about 47 MB): `FirstName`, `LastName`, `Institute`,
  `InstituteCountry`, `ResearchInstitution`, `PersonNumber`, `ORCID`, `ResponsibleApplicantGrantNumber`,
  `CoApplicantGrantNumber`, `EmployeeGrantNumber`, … Grant-number fields hold several numbers separated by `;` inside
  a quoted field, so read with a CSV parser, never by splitting lines.
- The old `data.snf.ch/exportcsv/*.csv` links return 404.

Procedure: download both into `RUN_DIR/cache/snsf/`; keep grants whose instrument is in the table, whose
`TitleEnglish`, `Title` or `Keywords` match the domain keywords (and `MainDiscipline` when stage 1 chose one), and whose
date falls in the window; join persons on `ResponsibleApplicantGrantNumber`; keep `ORCID` as `ids.orcid` and
`PersonNumber` as `ids.snsf`. Store only the matched rows in signals; the downloaded files stay in the run cache and
are deleted with the run. Evidence URL: `https://data.snf.ch/grants/grant/<GrantNumber>`.

| `FundingInstrumentPublished` | signal_type | what the role means |
|---|---|---|
| SNSF Starting Grants (reported under Horizon Europe Transitional Measures), SNSF Starting Grants 2025 and later | `snsf_starting_grant` | the SNSF's highest career-funding level: up to five years to lead an independent project and team |
| Ambizione, Ambizione Energy | `snsf_ambizione` | early-career researchers who conduct, manage and lead an independent project at a Swiss higher education institution; not a professorship |
| SNSF Professorships, Eccellenza, Eccellenza grant | `snsf_professorship` | assistant professorship funding (SNSF professorships were replaced by Eccellenza Professorial Fellowships in 2018, aimed at a permanent professorship; both discontinued, ongoing grants only) |
| Project funding, Sinergia, PRIMA, SNSF Consolidator / Advanced Grants and other project instruments | `snsf_project` | the responsible applicant leads the project |
| Doc.CH | `snsf_doc_ch` | personal doctoral funding: stage 4 classes the holder as phd_student |
| Doc.Mobility | `snsf_doc_mobility` | doctoral mobility fellowship: phd_student |
| Postdoc.Mobility | `snsf_postdoc_mobility` | personal postdoc fellowship: researcher |
| SNSF Swiss Postdoctoral Fellowships | `snsf_swiss_postdoc` | the MSCA-replacement fellowship for postdocs coming to Switzerland: researcher; the host institute is the person's affiliation |

Signals: `role: pi`, `channel: funding-de-ch`, strength high for Starting Grant, Ambizione and Professorship, medium
for `snsf_project`. `date`: `EffectiveGrantStartDate` when it is on or before the run date; otherwise (approved, start
in the future) `CallDecisionYear`; say which in `note`. Copy `FundingInstrumentPublished`, `CallFullTitle` and the
English title into `snippet`.

## Doctoral students: Research Training Groups and IMPRS

- **Research Training Groups (Graduiertenkollegs)**: from the GEPRIS search with `dfg_verfahren_1: ["GRK"]`, take
  each group active in the window, emit an `org` signal (the group, its host institution, `PRJ_WEBSEITE`), then open
  the group's site and its people page ("Doctoral researchers", "Doktorandinnen und Doktoranden", "PhD students",
  "Members"). One `person` signal per listed person: `signal_type: graduiertenkolleg_member`, `role: team_member`,
  `hop_depth: 1`, `parent` = the group's title, `evidence_url` = the people page.
- **International Max Planck Research Schools**: the list of schools with their topics and links is at
  `https://www.mpg.de/en/imprs`. Pick the schools whose topic matches the domain map, open each school's students or
  doctoral researchers page, emit `imprs_member` signals the same way (`parent` = the school's name).
- Member pages are rarely dated. Use a printed cohort or start year as `date`; otherwise emit without a date (evidence
  only) and let the person qualify through a dated work found by the `org` hop (`../30-hops.md`). Alumni sections are
  `note: alumni`, not members.

## role_title and topics

- `role_title`: GEPRIS — the title printed in the name field (`bt_partner_name_komplett`: "Professor Dr.",
  "Dr.-Ing."), else the role label (`label_EN`: "Applicant", "Spokesperson", "Persons responsible for project"); keep
  the title out of `name_raw` and the role label in `snippet`. SNSF — the heading the grant page prints over the name
  ("Applicants"; "Employees" for employees). Research Training Group
  and IMPRS pages — the section heading the name sits under, verbatim ("Doctoral Researchers", "Principal
  Investigators", "Associated Members").
- `topics`: 1–3 phrases cut verbatim from `prj_titel_en` / `TitleEnglish`; SNSF `Keywords` entries may be copied as
  they are. Member signals take theirs from the group's or school's title.

## Traps

- A `dfg_*` or `snsf_*` PI signal makes the person a professor in stage 4 unless its type is a personal grant
  (`dfg_walter_benjamin`, `snsf_ambizione`, `snsf_postdoc_mobility`, `snsf_swiss_postdoc` → researcher; `snsf_doc_ch`, `snsf_doc_mobility`
  → phd_student). DFG Research Grants also fund applicants' own positions ("Eigene Stelle"): when the name field
  carries no professorial title, put `role_title` as printed and say "Eigene Stelle" in `note`, so an explicit title
  (rule 1) can override the funding rule.
- GEPRIS dates are years. A year-only `date` qualifies when that year overlaps the window, so a project begun in the
  window's start year counts; record the start year as printed and do not invent a month.
- `beteiligungen_en` is the institution on the project record; the person record may name another. When they differ,
  keep both in `note` and let stage 4 choose the current one.
- Graduate school and group pages list alumni next to current members; keep alumni out of member signals.
