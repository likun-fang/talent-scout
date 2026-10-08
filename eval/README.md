# Recall checks

One golden file per domain: people a domain insider says "must be found". Columns:
`name, affiliation, country, why_expected, source_url`. After a run, count how many golden rows
appear in `roster.csv` (match on ORCID / GitHub if present, else normalised name + affiliation).
Report recall and list the misses with the channel that should have caught each one.

Golden lists are built by humans from memory, not by the tool, otherwise the check is circular.
