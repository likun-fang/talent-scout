# Stage 1 — Derive the domain map from universal sources

Goal: turn a domain phrase into `RUN_DIR/domain-map.yaml`. The map is evidence-driven: each entry comes from one of
the sources below, and every manual pick (a topic chosen from a list, a venue added by hand, a source dropped) carries
a `selection_reason`. Use the sources in order; each one is domain-agnostic. If `SKILL_ROOT/domain-cache/<slug>.yaml`
exists, load it, refresh the dated fields and recompute publication-based counts for the run window instead of
starting over. The cache records the `window` its counts were computed over; counts from another window are not
recent activity. This stage maps where to look; it reads no grant lists or rosters (that is stage 2).

A run starts from the field's pack (`references/15-domain-pack.md`): the cached map, `assets/facets/<slug>.json` and
`assets/known-groups/<slug>.json`. For a new field, the maintainer's answers to the pack's ten questions start the map.
What the run learns goes into the run's copy, never into the pack directly: the pack changes only through a pull
request, and `scripts/check_domain_pack.py <slug>` passes before it is merged.

## 1. Venues and labs — OpenAlex (keyless JSON)

- Topics: `https://api.openalex.org/topics?search=<phrase>` → read the top 10 (or all, when fewer come back) and
  **choose** the ones that are the domain, each with a `selection_reason` (`scripts/openalex_lookup.py --topic` lists
  them). The third hit for "robot learning" was "Smart Agriculture and AI"; a topic such as "Reinforcement Learning in
  Robotics" also carries game theory and LLM fine-tuning, so plan a title keyword filter when you use it downstream.
  When no topic is the domain itself, rephrase the search once (a narrower or a broader phrase); if that also fails,
  take the closest broader topic, mark it `fit: adjacent` and rely on `keywords` downstream.
- Venues: `https://api.openalex.org/works?filter=topics.id:<id>,from_publication_date:<window_start>,to_publication_date:<window_end>,authorships.countries:<region_extended codes joined by |>&group_by=primary_location.source.id`
  → the domain's venues as seen from Europe (`--topics T1,T2` in the script). Drop repositories (arXiv, Zenodo, HAL,
  institutional portals): check the source's `type` (`repository`) rather than its name. PMLR proceedings such as
  CoRL rarely surface here: add the field's known conferences by hand with a `selection_reason`.
- Labs: same query with `group_by=authorships.institutions.id` → top 30 institutions. The filter means "any author in
  region", so non-European institutions appear through collaborations; look up each institution's country and type
  (`https://api.openalex.org/institutions/<id>`) and keep the ones in `region_extended`, core-region ones first.
  These are whole universities and institutes, not labs: the lab or group and its `people_page` come from stage 2.
- Prolific authors (`group_by=authorships.author.id`, top 50) are **leads for hops**, not rows: production ranking
  favours senior PIs and misses newer directions (VLA, humanoids). Awards, competitions and open source carry those.
  Confirm each lead is a natural person before using it: an author record whose works are papers with co-authors and
  an institution. Aggregations have surfaced software and model names as authors ("Chatterbox TTS"); drop those and
  note them in `sources_used`.

Manual path: open `https://openalex.org`, search the phrase, read the "Sources" and "Institutions"
facets with a Europe filter.

## 2. Funding codes — ERC panels, EuroSciVoc, national subject codes (universal tables in `assets/`)

- ERC panel codes (`assets/erc-panels.yaml`) are a weak proxy: PE7 is mostly electronics and communications, soft
  robotics sits in PE8, learning in PE6. Record `panels_to_sweep` (each with a reason) to order the funding sweep and
  the title `keywords` to match against. The sweep itself, across every PE row, happens in `channels/funding-eu.md`.
- Pick EuroSciVoc paths (`assets/euroscivoc-paths.md`) for CORDIS filtering.
- For the core-region registers, record `register_subject_filters`: the DFG review boards (`4.41`, `4.43`, …) that
  a keyword search on GEPRIS returns most often in `aggregations.fachkolleg`, and SNSF `MainDiscipline` names; see
  `channels/funding-de-ch.md`. They narrow the sweep; keywords still decide.

## 3. Award pages — derived from the venue list

For each conference venue: search `"<venue>" "best paper" OR "outstanding paper" award <year>`.
Record the award page URL per year. Two cross-venue lists exist and are good seeds, both with
caveats noted in `channels/awards-papers.md`: jeffhuang.com/best_paper_awards (32 CS venues,
first author's first affiliation only) and github.com/FeijiangHan/Top-Conference-Best-Papers (ML/NLP/CV).

## 4. Competitions — search, then list them for the user

Search `<phrase> competition OR challenge winners <year>` and `<phrase> league results <year>`.
Also check conference-hosted competitions (ICRA/IROS/NeurIPS/DAC/ISSCC publish competition lists).
Add each with its results URL pattern and a `selection_reason`. Competitions are the one part a 30-second human glance
improves most: they go into the one-screen summary below, and the user's reply confirms or edits them.

## 5. Companies — two universal sources

- EIC Accelerator selected-company PDFs (one per round, company / project / country).
- OpenAlex institutions of type `company` among the stage-1 lab list (industry labs publishing in the domain).
Add user-named competitors if given.

## 6. Open-source anchors

Search GitHub topics matching the phrase; take repos with the most stars whose owner org or
top contributors are in region. Record repo URLs; people come later via hops.

## Emit and stop

Write `RUN_DIR/domain-map.yaml` (template in `SKILL_ROOT/assets/domain-map.template.yaml`) and a copy to
`RUN_DIR/domain-cache/<slug>.yaml` with `derived_on` and `sources_used`; `SKILL_ROOT/domain-cache/` changes only when
the maintainer confirms by hand. Next to it write `RUN_DIR/facets.json` (template `SKILL_ROOT/assets/facets.template.json`):
two to four facets that classify the domain's research directions, each a short list of tags with the words that
put a record under the tag. Take the facets from how the field itself sorts its work, for example the axes of a
public leaderboard (RoboDojo sorts robot-manipulation policies by policy type, capability dimension and sim/real
setting); the keywords come from the topic phrases stage 1 has seen. The talent map matches them against every
person's topics, snippets and project titles and offers one filter per facet; the tags never enter the roster. Show the user a one-screen summary: topics, venues, labs (core region first),
competitions, companies, anchors, panels and register filters, plus the stage-0 defaults in use. Then stop and wait
for the user's reply; do not start stage 2 until the user has answered. One sentence is enough ("go", or the changes
to make). Apply the changes to both copies of the map, then set `stage_status["1"]` to `"done"`.
