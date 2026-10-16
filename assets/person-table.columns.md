name, current_affiliation, country, role, domain, channels_hit, signals, evidence_urls, ids, hop_depth, merge_confidence, affiliation_source, last_verified, notes, fit, first_pub_year, latest_role, homepage, ranked_channels, role_class, role_confidence, tier, topics, group, role_evidence


The first line is the fixed 25-column contract, in order. `role_evidence` is column 25.
`group_evidence` and optional integer `group_rule` are person metadata; group evidence appears in the appendix,
not in an additional table column. Empty groups appear in the group view's `(unattached)` row.

A final-pass affiliation/country overrides `current_affiliation`/`country`; `affiliation_source` cites the actual
read date and URL, and notes retain the provider affiliation/source. `tier` uses the corrected country. `role`
and `latest_role` still describe the signals. Topics stay verbatim in source/person records; the exporters fold
cell whitespace consistently in CSV and Markdown without rewriting those records.

With a topic policy, the exported `topics` column contains configured short labels instead of the raw
phrases. Professors' labels require recent personally authored paper evidence. Group topics aggregate
retained members' labels, excluding coauthor-only links. Column counts do not change; see
`references/46-topic-qualification.md` for evidence, pending cases and historical-run compatibility.
