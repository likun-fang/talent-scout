# Run log: embodied AI / robot learning, Europe (2026-10-08)

First end-to-end run, in a claude.ai session with six parallel channel subagents sharing one brief.
Result: 845 signals (634 person, 82 work, 65 team, 37 company, 27 org) → 525 persons → 521 in-region rows.
By channel: industry 148, competitions 145, awards-papers 129, national-prizes 61, open-source 44, startups 34,
funding-eu 28. By country: DE 198, GB 84, FR 75, CH 66, IT 28, NL 18.

The run agent logged 22 problems. What changed in the skill because of them:

| # | Problem | Fix |
|---|---------|-----|
| 1 | Keyless OpenAlex quota already spent in a shared sandbox | stage 0 asks for the key; scripts read `OPENALEX_API_KEY` |
| 2 | GitHub API, `gh api`, OpenReview API 403; contributors page robots-blocked | open-source channel: bare blobless git clone + CITATION/CONTRIBUTORS/package.xml |
| 3 | DBLP turned into a bot-check page mid-run | stage 0 probes and records it; no channel depends on it |
| 4 | ERC site rate-limits; PDF names vary; reserve lists | funding-eu: serial fetch, name variants, reserve lists |
| 5 | CORDIS has no PI names or panels; acronyms repeat | funding-eu: CORDIS for discovery, ERC PDF for names |
| 6 | Top-3 topic pick returned "Smart Agriculture" | `--topic` lists 10 to choose from; `--topics` runs the chosen |
| 7 | "Any author in region" admits Tsinghua; author grouping favours prolific PIs | stage 1 text: leads not rows; keep in-region institutions |
| 8 | arXiv / Zenodo top the venue list; CoRL absent | script drops repositories; add PMLR venues by hand |
| 9 | ERC PE6/PE7 weak proxy; soft robotics in PE8 | sweep all PE rows by keyword |
| 10–11 | Award pages 404 / finalists only; bare URLs expire | awards-papers: year-stamped pages, round-ups, archived URLs |
| 12 | Senior prizes empty; useful ones missing from registry | registry gains RAS early career, Giralt, ELLIS, UK-RAS, RAEng, NWO, Branco Weiss |
| 13 | Results pages lack TDP links; image rankings; broad leagues | competitions: rosters from champion/TDP papers with year note; low strength for broad leagues |
| 14 | OpenAlex files DeepMind/NVIDIA global staff under GB; labs without records | industry: raw_affiliation_strings + city filter |
| 15 | Founders not on team pages; name collisions | startups: press for founders; ids only on topic match |
| 16 | Mixed / duplicate OpenAlex profiles; LeRobot → Oxford | entity-resolution traps list |
| 17 | Stale open ORCID employment moves people back decades | new `current_affiliation.py` with the recency override |
| 18 | Weak key needed identical institution strings | `merge_persons.py` matches on shared institution token (634 → 527 persons on this run's signals; hand merge gave 525) |
| 19 | Export did no region filter | `table_export.py --region`, out-of-region file |
| 20 | 521 rows vs target 50, no cut rule | `--max-rows` after sorting, reported in Coverage |
| 21 | Golden list empty | eval/ removed: the table itself is the check |
| 22 | Hand-seeded domain cache | replaced by the run's derived map |

Still open: NeurIPS / ICLR outstanding papers unchecked; IROS 2024–2025 and Humanoids award lists not public;
DeepMind London / Meta FAIR Paris robotics under-covered because arXiv-only papers carry no affiliation.
