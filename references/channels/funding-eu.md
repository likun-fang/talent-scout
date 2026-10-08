# Channel: EU funding

## Discovery vs names
CORDIS has abstracts, call ids and host organisations but **no PI names and no panel codes**; ERC results PDFs have
names and panels but no abstracts. Use both: CORDIS search API for discovery
(`https://cordis.europa.eu/search?q=<query>&format=json`, about 10 records per page, acronyms repeat across
projects), then the ERC PDF for the PI name. Fetch erc.europa.eu **serially**: parallel requests get HTTP 200 "Sorry"
pages or 429. PDF names vary (`-results-pe.pdf`, `-result-pe.pdf`, `-results-all-domains.pdf`); some funded PIs appear
only on reserve lists.

## ERC (highest yield per page)
- Results PDFs per call: `https://erc.europa.eu/system/files/<year-month>/erc-<year>-<stg|cog|adg|syg>-results-all-domains.pdf`, plus per-domain variants (`-pe.pdf`). Columns: last name, first name, host institution, host institution local name, host country, acronym, title, panel.
- Sweep every PE row by title keywords (panels are only a weak proxy, see stage 1), then read the matching rows. Emit `person` signals with `role: pi`, `signal_type: erc_<stg|cog|adg|syg>`, strength high.
- Read the PDF directly (or its extracted text). Cells wrap over several lines, so read record by record: a record is
  the line carrying `<last name> … <country code> <acronym> … <panel>` plus the title lines around it. Keep the rows
  whose panel is in the domain map and whose title matches the domain; copy the title verbatim into `snippet`.
  A tried column-splitting script recovered 38 of ~478 rows on the 2025 StG PDF, so reading beats parsing here.
- ERC project pages (`erc.europa.eu/projects-statistics`) and CORDIS give the project abstract when title keywords are ambiguous.

## CORDIS (Horizon Europe + H2020)
- Monthly CSV bundles on data.europa.eu: projects, organisations, and a separate "Principal Investigators in ERC projects" table. Project → organisations gives orgs, not people; emit `org` signals (coordinator and participants in region) for stage 3 hops. Filter by EuroSciVoc path and keywords.
- Project websites (field `projectUrl`) usually have a consortium / team page.

## Chips JU, EuroHPC JU, KDT/ECSEL
- Consortium-level; participants are organisations. Treat as `org` signals. Funded project lists live on each JU site; CORDIS also carries them.

## EIC (Pathfinder, Transition, Accelerator)
- Accelerator rounds publish a selected-companies PDF (company, project, country). Emit `company` signals; founders resolved in stage 3.
- Pathfinder grants list coordinator organisations and sometimes PIs.

## Traps
- ERC host country is at application time.
- CORDIS CSV column names change between releases; read the header, do not hard-code positions.
