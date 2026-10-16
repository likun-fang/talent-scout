# Evidence-backed identity decisions

`assets/identity-reviews.json` is a shared, domain-independent review registry. The registry contains curated, dated identity decisions; it is not a complete identity directory.
Do not populate it from a name match, an unchanged row count, or an unreviewed provider response. Each decision
requires public evidence actually read by a reviewer. Cached evidence retains its original review date.

The following is a **format example**, not a real approved identity:

```json
{
  "schema_version": 1,
  "entities": [{
    "entity_id": "reviewed-example-researcher",
    "names": ["Example Researcher", "E. Researcher"],
    "canonical_ids": {"orcid": "0000-0001-1111-1111", "openalex": "A1"},
    "id_aliases": {"openalex": ["A2"]},
    "evidence": [{
      "url": "https://institution.example/researcher",
      "quote": "Verbatim reviewed text supporting the identity bindings and aliases.",
      "reviewed_on": "2026-10-16"
    }],
    "signal_reviews": [{
      "evidence_url": "https://papers.example/work",
      "decision": "accept",
      "reason": "The original author list and linked profile establish this person's authorship.",
      "evidence_refs": [0]
    }]
  }]
}
```

- `entity_id` is the persistent key for this reviewed identity. Names are explicitly reviewed spellings; they are
  not wildcard matches. Each accepted provider ID can belong to only one registered entity.
- `canonical_ids` and optional `id_aliases` contain only established bindings. Do not list a merely plausible
  OpenAlex ID as an alias. An ORCID-only decision can leave OpenAlex IDs unverified: they remain raw annotations,
  are disclosed in the audit, and do not become canonical keys or an assertion that the profiles are equivalent.
- `evidence` contains the actual URLs, quotations and original review dates supporting the bindings. An official
  job title alone does not establish which author IDs or papers belong to the person.
- A source with accepted identifiers and no contrary reviewed binding may remain evidence. Other conflicting
  or unbound sources are held. A per-source `accept` with appropriate author evidence may correct a wrong ID
  binding; the original full signal and the decision remain in the audit. Its authorship evidence URL points
  to the cited review evidence. `reject` excludes that source even if its IDs otherwise match.
- Acceptance does not create publication metadata or turn `authorship_verified: false` into true. It does not
  change dates, grant a topic, establish a job, or override an explicit pending/held/deceased decision. Current
  employment conflicts remain separate from identity aliases.
- When a canonical correction invalidates the cached profile, the candidate is marked for re-enrichment and
  cannot qualify geographically using the discarded employer. Offline cache misses do not clear this hold.
- `identity_status` distinguishes provider-only records, unkeyed records, unresolved namesakes, reviewed
  identities, and reviewed identities with held sources or unverified provider annotations. Source matching
  confidence and current-role confidence are different facts; neither certifies identity.

Reprocess the original source records after changing a decision. A filtered export alone cannot restore evidence
that was held earlier. Keep `roster.identity-audit.json`; it contains inputs, reviews, source corrections and holds.
Both exporters enforce the same gate. Approved ID aliases are also understood by `research_topics.py`, so a
valid paper is not lost merely because its retained original author ID is an approved alias.

Tests must cover false merges and lost valid evidence, source-level rejection and correction, unresolved provider
profiles, professor topic eligibility, repeated execution, namesakes, and independent group relationships.
