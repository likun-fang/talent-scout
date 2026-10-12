# Optional run profile: multimodal talent sourcing in six core countries

This is a run configuration and discovery guide for the existing stages and channels. It does not replace the
generic domain map, change ranking, create a channel or automatically enable extensions for every multimodal run.
Use it when the requested scope includes Germany, Switzerland, France, Spain, the Netherlands and Belgium.

## Configure the run explicitly

Keep the existing rolling 36-month window, stage approval stops and page budgets. Set these fields in
`RUN_DIR/run.meta.json` and mirror them in `RUN_DIR/domain-map.yaml` (the JSON equivalent of the YAML below).
Preserve the rest of both files:

```yaml
region_core: "DE+CH+FR+ES+NL+BE"
region_extended: "EU27+UK+CH"
sourcing_extensions:
  recent_papers: true
  model_cards: true
```

`run.meta.json` is authoritative for extension switches. Each switch is independently optional, with absent or
false preserving the original procedure. These are Agent instructions, not new script arguments. If the metadata
also contains the compatibility field `region`, keep it equal to `region_extended`.

The four added countries already belong to the extended region; placing them in core gives them the existing
core-region tier treatment. It does not alter role priorities: industry/unknown roles retain their existing tier.
The Python helpers do not automatically load these run settings. Follow `scripts/README.md` and explicitly pass
the same `--date` and `--region-core DE+CH+FR+ES+NL+BE` to the merge, affiliation and export commands;
pass `--region-extended EU27+UK+CH` to affiliation and export (merge has no such flag).
Do not change repository-wide defaults to apply this run profile.

## Fill the existing domain-map fields with evidence

- `keywords`: discover and validate phrases for vision-language models, image-text understanding/retrieval,
  video-language understanding, audio-language models, multimodal generation and multimodal reasoning. These
  are query seeds; adapt them to the user's actual scope. Pure unimodal work and robotics work without a relevant
  multimodal contribution are not core merely because they share an institution, venue or broad topic.
- `openalex_topics`: select actual returned topic IDs with the existing fit and selection-reason rules. Never
  hard-code one broad topic as sufficient evidence of multimodal relevance.
- `venues`: derive sources through the existing topic queries; manually added conferences still need a
  `selection_reason`. A general ML/CV/NLP conference requires work-level relevance checks.
- `labs`: use the existing institution discovery procedure with the shared six-country core and extended region.
  Institutions remain leads until stage 2 resolves their actual groups and people pages.
- `companies`: use the existing company discovery procedure and user-named competitors. Company headquarters
  do not establish an individual researcher's current country.
- `open_source_anchors`: include relevant code and public model/dataset cards with linked reports, recording
  provenance in `sources_used`. Do not copy model names or organisation handles into person records.

Keep the standard stage-1 summary and user reply before stage 2. Show the chosen switches and six-country scope
alongside the normal map summary.

## Subdomain work split

When parallel agents are requested, use complementary research subdomains rather than country assignments:

- Vision-language / image-text: image understanding, retrieval, grounding and visual reasoning.
- Video-language: video understanding, temporal grounding and video-language reasoning.
- Audio / speech-language: audio-text understanding and speech-language multimodal work.
- Multimodal generation: generation or editing conditioned across modalities, including image/video/audio outputs.

Adapt these boundaries to the requested scope and actual domain map. Every subdomain uses the same
`region_core`, `region_extended`, date window, evidence standards and role rules. These are work assignments
within the existing workflow, not separate pipelines or additional channels. Papers, models and people can span
subdomains: preserve their evidence and stable IDs for the existing merge rather than forcing exclusive labels.
Set `run.meta.json.parallel_sourcing.mode` to `domain` and fill its worker assignments using
[`../20-parallel-sourcing.md`](../20-parallel-sourcing.md) for file ownership, budget allocation and joining results;
the profile itself does not multiply the channel budgets.

## Sweep through existing channels

- `awards-papers`: keep the award sweep, then use its optional ordinary-paper procedure for recent relevant
  authors who have no award. They receive `paper` signals, never invented award evidence.
- `open-source`: keep repository contributors and add the optional card → report/repository → person procedure.
- The other existing channels use the same domain keywords, regions, window and budgets as before. No extra
  page allowance or automatic parallel job is implied by these switches.

Each channel still writes its own JSONL and coverage report. Merge, current-affiliation enrichment, export and
final verification run in the existing order. Country coverage and unresolved identities go in the normal
coverage reports; no new person schema, scoring system or output format is required.
