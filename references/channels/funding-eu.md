# Channel: EU funding

## ERC (highest yield per page)
- Results PDFs per call: `https://erc.europa.eu/system/files/<year-month>/erc-<year>-<stg|cog|adg|syg>-results-all-domains.pdf`, plus per-domain variants (`-pe.pdf`). Columns: last name, first name, host institution, host institution local name, host country, acronym, title, panel.
- Filter rows by the panel codes in the domain map, then by title keywords. Emit `person` signals with `role: pi`, `signal_type: erc_<stg|cog|adg|syg>`, strength high.
- Script: `scripts/erc_pdf_rows.py` parses the PDF *text* (extract text with whatever the platform offers) into rows.
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
