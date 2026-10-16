# Short topics and recent professor publications

For new runs, write `RUN_DIR/topic-policy.json` at stage 1. Start from the selected domain preset's
`topic_policy_file`, or adapt `assets/topic-policy.template.json` to the actual domain. Labels are concise
research directions such as `VLM`, `VLA`, `Agentic`, `Policy`, `World Model`, `WAM`: at most three words and
24 characters. The template is a format example, not a scope expansion. In embodied AI, Agentic requires
explicitly agreed embodied-agent scope; a world model is not automatically a joint world-action model.
Map each topic's `facet_ids` to equivalent existing facet tags so the main topic filters agree with the
cards. Broad facets may map to multiple topics. Task, modality and evaluation attributes remain separate.
Include this policy in the execution plan's `config_refs` alongside the domain map and facets.

Keep raw `signal.topics` verbatim. For each sourced contribution, add `topic_evidence` with the configured
topic ID, a verbatim source quote, and `relation: contribution`. Merely mentioning a baseline or related
work is `background`, not eligibility. One paper can support multiple topics only with evidence for each.
Do not copy a lab's topics to all its members. Missing mappings are pending review, never guessed.

## Professor paper check (during collection and before final export)

Every displayed professor topic needs at least one paper personally coauthored by that professor inside
the run window (default: the last 36 months, inclusive). Any author position counts. Recent grants,
awards, lab membership and unrelated papers cannot substitute. Only `role_class: professor` is subject
to this additional gate; do not infer that every PI/group leader has a professorial title.

For professors discovered through any channel, inspect recent works using the resolved author ID and
then verify the original publication/author list. Record this evidence on a person signal:

```json
{
  "publication": {
    "title": "Example title describing vision-language-action policies",
    "abstract": "Verbatim abstract, when needed for topic attribution.",
    "date": "2025-06-01",
    "status": "published",
    "url": "https://example.org/paper",
    "author_name": "Name as printed on the author list",
    "author_ids": {"openalex": "A123"},
    "authorship_verified": true,
    "authorship_evidence_url": "https://example.org/paper/authors"
  },
  "topic_evidence": [{
    "topic_id": "vla",
    "quote": "vision-language-action policies",
    "relation": "contribution"
  }]
}
```

Use real source values, never this example's IDs or dates. Verify authorship through the author list and
resolved identity (name plus affiliation/identifiers for namesakes). `authorship_verified` is a sourced
research assertion, not a field an exporter independently verifies online. Supply stable author IDs when
available. Ambiguous merged identities cannot qualify. Keep the original work and author-list response
in the run cache and record the retrieval in the execution task. A title/abstract quote must describe the
paper's contribution under the domain inclusion rules; token occurrence alone is insufficient.

`publication.date` is the first published/publicly posted date of the work, not a webpage refresh,
arXiv revision, award or access date. Deduplicate preprint/published versions during collection. Default
`include_preprints: true` counts them but labels them `preprint`; set false when only formal publications
are requested. Year/month-only dates qualify only if their **entire interval** is inside the window;
boundary-straddling dates need a precise date. Never invent January 1 to qualify a paper.

If evidence is missing, search the author's recent papers before exporting. If access or the budget
prevents verification, keep the candidate's signals and report `pending_evidence`; do not claim they have
stopped research. A professor without any qualifying topic is omitted from the main roster and retained
in `roster.topic-audit.json`. Existing identity, affiliation, geography, group inference and ranking rules
remain in effect. Once the paper gate passes, other recent signals still contribute to ranking.

## Export and historical runs

Both exporters use the same policy and selection code:

```sh
python3 "$SKILL_ROOT/scripts/table_export.py" "$RUN_DIR/persons.jsonl" --date YYYY-MM-DD --topic-policy "$RUN_DIR/topic-policy.json" --out "$RUN_DIR/roster"
python3 "$SKILL_ROOT/scripts/talent_map.py" "$RUN_DIR/persons.jsonl" --date YYYY-MM-DD --topic-policy "$RUN_DIR/topic-policy.json" --out "$RUN_DIR/talent-map.html"
```

Pass the same region/window options to both. The explicit policy path is required for new-run delivery;
a missing/invalid file stops export. With no explicit flag, a sibling `topic-policy.json` is auto-loaded.
Historical runs without one retain the previous behavior and report `not_checked`, not compliance.
To migrate an old run, copy the policy, backfill reviewed publication/topic evidence, then re-export;
changing the HTML alone or treating `semantic_directions` as verified paper evidence is insufficient.

CSV/Markdown keep their fixed columns: exported `topics` contains short labels; source/person JSON is
untouched. The person HTML and Markdown appendix list qualifying papers with dates, status and links.
Professor main-topic facets use only validated topic IDs; other facets use qualifying paper signals.
Group topics aggregate retained members' short labels, excluding coauthor-only links. They describe
member activity and do not prove that an absent PI personally authored papers on every group topic.
Non-professors retain the existing activity gate and use reviewed topic mappings from recent signals.

For delivery inspect `roster.topic-audit.json`: distinguish missing publication metadata, unknown topic
mapping, author mismatch, old papers, uncertain dates and excluded preprints. Audit entries are per signal
plus pending-person summaries, not a distinct-person count. Pending paper evidence must be disclosed in
coverage even when discovery tasks are marked complete.
