# Channel: industry labs and competitor companies

OpenAlex traps for companies: multinationals are often filed under one national record ("Google DeepMind (United
Kingdom)", "Nvidia (United Kingdom)") so US staff appear as GB; several European labs have no institution record
(NAVER LABS Europe, Bosch Center for AI, Meta FAIR Paris, Huawei Noah's Ark London, Hugging Face Paris). Query
`raw_affiliation_strings.search:<company> <city>` and reject strings naming a US city; add a title keyword filter when
the topic is noisy. arXiv-only papers usually carry no affiliation at all.

Only public professional artefacts:
- Papers with company affiliation in region (OpenAlex institutions of type `company`, or user-named companies → `authorships.institutions.id`).
- Patents: Espacenet / Google Patents, applicant = company, inventor address in region; emit `person` with `role: inventor`, strength medium.
- Public talks: conference programmes, meetup pages, company engineering blogs with bylines.
- Open source: company GitHub organisations (see `open-source.md`).

## Reverse lookup by ROR

Company labs rarely publish a staff list. On 2026-10-14 NAVER LABS Europe, Google DeepMind, Meta FAIR, Sony AI, Bosch
Research, Mistral and Aleph Alpha were checked and none had a public roster. Their papers name the people, so go from
the company's ROR record to its papers.

1. Find the ROR record: `GET https://api.ror.org/v2/organizations?query=<company>`. Read `items[].names[]` (the
   `ror_display` name), `types` (`company`), `locations[0].geonames_details.country_code` and `relationships`
   (`parent`, `child`). Accept a record only when name and country fit the European lab. The `affiliation=` matcher
   on the same endpoint answers with `chosen: false` when unsure; do not take an unchosen match.
2. With a European record, list its works in the window:
   `GET https://api.openalex.org/works?filter=institutions.ror:<ror id>,from_publication_date:<window_start>,to_publication_date:<window_end>&select=id,doi,title,publication_date,authorships`
   (keyed: `Authorization: Bearer $(cat ~/.config/talent-scout/openalex.key)`), and keep the authorships whose
   `institutions[].ror` is that record.
3. When ROR has only the group's parent, the parent ROR is the wrong filter. Tested 2026-10-14: ROR has no record for
   NAVER LABS Europe; `query=NAVER LABS Europe` returned the Korean parent `Naver (South Korea)`
   (`https://ror.org/04nzrnx83`, company, KR) and NAVER Cloud, and the affiliation matcher offered NAVER Cloud
   unchosen. Works with `institutions.ror:04nzrnx83` in the window: 373, every one with the institution in KR.
   `raw_affiliation_strings.search:"NAVER LABS Europe"` in the window: 134 works, 99 distinct authors on the lab's
   authorships. Of those authorships, 160 were matched to the Korean parent and 213 to no institution at all, so the
   two filters combined found only 58 works. Use the raw-string filter, and keep an authorship only when its own
   `raw_affiliation_strings` names the European lab; 20 of them had no OpenAlex author id.

Signals: one `person` per kept authorship, `signal_type: company_paper`, `role` from `author_position`
(`first_author`, `last_author`, `coauthor`), `affiliation_raw` = the company name as the raw string prints it
("NAVER LABS Europe"), `institution_type: company`, `country` from the city or country in the raw string ("Meylan,
France" → FR), never from the OpenAlex institution (KR above). `ids.openalex` when the authorship has an author id
whose works fit the domain. `date` = `publication_date`; `evidence_url` = the DOI (130 of the 134 works had one),
else the OpenAlex work URL; `topics` from the title. Stage 4 classes these people as industry from the company name.

No social-network scraping, no login-gated pages; current roles are checked once on the cut table
(`../45-web-verification.md`). If the user names competitors, add them to the
domain map `companies:` list with the reason.

## role_title and topics
- `role_title`: the title part of a byline or speaker line as printed ("Research Scientist"), the company team page's
  title, or the patent's heading for the person ("Inventor").
- `topics`: from the paper, patent or talk title.
