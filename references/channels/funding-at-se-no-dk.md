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
`https://www.fwf.ac.at/en/funding/portfolio/careers/erwin-schroedinger`, `https://api.ror.org/v2/organizations/054pv6659`.

## Keys

A key lives in `~/.config/talent-scout/<source>.key` with mode 600, outside the repository and the run directory.
Briefs, notes and coverage name the path, never the value. Read it at call time:
`-H "Authorization: Bearer $(cat ~/.config/talent-scout/fwf.key)"`.

| Source | File | Where it comes from | Registration | Quota |
|---|---|---|---|---|
| FWF | `fwf.key` | the whole body of `https://openapi.fwf.ac.at/fwfkey` (one 64-character hex string) | none | not stated |

When FWF answers 403 `invalid_api_key`, fetch the key page again: the page always serves the current key.

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
