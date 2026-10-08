# Stage 1 — Derive the domain map from universal sources

Goal: turn a domain phrase into `domain-map.yaml` **without hand-curation**. Use the sources below
in order; each one is domain-agnostic. If `domain-cache/<slug>.yaml` exists, load it and refresh
only the dated fields (awards, competitions) instead of starting over.

## 1. Venues and labs — OpenAlex (keyless JSON)

- Topics: `https://api.openalex.org/topics?search=<phrase>` → take the top 1–3 topic ids.
- Venues: `https://api.openalex.org/works?filter=topics.id:<id>,publication_year:>YYYY,authorships.countries:<region codes joined by |>&group_by=primary_location.source.id`
  → top 15 sources by count = the domain's venues as seen from Europe. Keep conferences and journals separately.
- Labs: same query with `group_by=authorships.institutions.id` → top 30 institutions in region.
- Prolific authors (seed list, not final): `group_by=authorships.author.id` top 50. These are **leads**, not rows yet.

Manual path: open `https://openalex.org`, search the phrase, read the "Sources" and "Institutions"
facets with a Europe filter.

## 2. Funding codes — ERC panels and EuroSciVoc (universal tables in `assets/`)

- Pick ERC panel codes whose descriptions match the domain (`assets/erc-panels.yaml`). Computer
  science is PE6; systems / robotics / electronics are PE7; materials & devices often PE5/PE8.
  Choose 1–3 panels; record why.
- Pick EuroSciVoc paths (`assets/euroscivoc-paths.md`) for CORDIS filtering.

## 3. Award pages — derived from the venue list

For each conference venue: search `"<venue>" "best paper" OR "outstanding paper" award <year>`.
Record the award page URL per year. Two cross-venue lists exist and are good seeds, both with
caveats noted in `channels/awards-papers.md`: jeffhuang.com/best_paper_awards (32 CS venues,
first author's first affiliation only) and github.com/FeijiangHan/Top-Conference-Best-Papers (ML/NLP/CV).

## 4. Competitions — search, then confirm with user

Search `<phrase> competition OR challenge winners <year>` and `<phrase> league results <year>`.
Also check conference-hosted competitions (ICRA/IROS/NeurIPS/DAC/ISSCC publish competition lists).
Add each with its results URL pattern. Show the list to the user; competitions are the one part
a 30-second human glance improves most.

## 5. Companies — two universal sources

- EIC Accelerator selected-company PDFs (one per round, company / project / country).
- OpenAlex institutions of type `company` among the stage-1 lab list (industry labs publishing in the domain).
Add user-named competitors if given.

## 6. Open-source anchors

Search GitHub topics matching the phrase; take repos with the most stars whose owner org or
top contributors are in region. Record repo URLs; people come later via hops.

## Emit `domain-map.yaml` (template in `assets/domain-map.template.yaml`), save a copy to
`domain-cache/<slug>.yaml` with `derived_on` and `sources_used`, then show the user a one-screen
summary and continue unless they object.
