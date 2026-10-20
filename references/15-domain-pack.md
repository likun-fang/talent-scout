# Domain pack

A field is described by one pack, so a new field needs a pack and no change to the scripts. The pack for `<slug>` is
three files under `SKILL_ROOT`:

| file | holds | shape |
|------|-------|-------|
| `domain-cache/<slug>.yaml` | the domain map: scope, directions, topics, venues, panels, register filters, competitions, labs, companies, anchors, keywords, quirks | `assets/domain-pack.schema.json`; blank form `assets/domain-map.template.yaml` |
| `assets/facets/<slug>.json` | the research-direction facets of the map's filters | `assets/facets.template.json` |
| `assets/known-groups/<slug>.json` | the groups any good map of the field must contain, for the recall check | `assets/known-groups/multimodal-ai.json` |

Every key of the yaml is present in every pack; a key the field does not use stays empty. The pack maps institutions
and sources only: names of people, OpenAlex author ids and LinkedIn URLs never go into it (seed groups go into the
known-groups list, which names PIs because recall is measured on them). `quirks` holds the field-specific rules the
scripts keep in code today (title words, employer patterns, venues whose awards count as evidence), so they can be
read and changed in one place. `python3 scripts/check_domain_pack.py <slug>` validates a pack; a missing known-groups
list is a warning, because only the publication check needs it.

A run starts from the pack: stage 1 loads it, refreshes the dated fields and writes the run's copy. The pack itself
changes only through a pull request, after the maintainer has read what the run found.

## Starting a field: ten questions

The maintainer answers these before the first run; stage 1 turns the answers into the first pack.

1. Scope: one sentence that says what the field is, as a reader of the map would put it.
2. Directions: the two to five research directions inside it, and for each what is in and what is out.
3. Seed groups: three groups that certainly belong, with PI and institution (they start the known-groups list).
4. Venues: the conferences and journals where the field publishes, and which of their awards count.
5. Funding panels: the ERC panels, DFG review boards and SNSF disciplines that fund it.
6. Vocabulary: the words that find the field in titles, and the words that are too broad on their own.
7. National quirks: titles, institution types or registers of a country that need a rule.
8. Known groups: the groups beyond the seeds that a good map must show.
9. Region: the core and extended regions, if not the defaults.
10. Exclusions: neighbouring fields, applications or employers to leave out.
