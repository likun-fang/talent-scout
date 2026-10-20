# Run log: embodied AI / robot learning, core DE+CH (2026-10-12, two runs)

Both runs were made by a Codex agent with the skill installed by symlink, in one day, before and after the
day's changes. Rosters stay in the run directories (gitignored): they are personal data and belong with the run.

## Run 1 (morning, skill as of 5aca628)

783 signals → 602 persons → 100 rows. Lessons folded into the skill the same day:

| Problem | Fix |
|---|---|
| Stage 0 said to ask for the OpenAlex key only after a 429; the run stayed keyless and skipped the stage-4 lookups (571/602 persons kept raw affiliations, no `first_pub_year`) | stage 0 asks once; stage 4's "done when" requires `current_affiliation.py` |
| 317 people without a printed title were `unknown`, tier 4, cut; among them Siegwart, Stachniss, Haddadin, Brock, Toussaint | enrichment + final-pass title write-back (`final_pass_title`, rule 0) |
| Funding PI → "professor, high" put two postdocs in the professor bucket | `group_leader` class; a grant without a title is medium |
| "PhD Students and Scientific Assistants" heading labelled technical staff as doctoral | mixed headings prove membership only |
| Channels counted 40 *readable* pages and overran to 50 attempts | budget is 40 attempts, failures included |
| Agents invented `lab_member` and five other types for funded-lab people pages | `lab_member` defined; `role_title` = section heading, never page title |
| IMPRS scholar list and IEEE RAS award page unreadable (JS shell, 403) | fetch ladder: browser UA → Wayback → Jina → local Chrome; `--render` for client-side rosters |
| LinkedIn batch refused on the first request (the machine's anonymous quota was spent by tests) | LinkedIn optional, default budget 20, "quota spent" recorded |
| 16 well-known DE/CH PIs absent, 8 more cut | seeds at stage 0; seed audit in the run |

## Run 2 (afternoon, skill as of 9b27c38, with a key and 18 seed names)

1834 signals → 835 persons → 100 rows, 71 groups. By channel (persons / with role_title): funding-de-ch 590/340,
awards-papers 234/128, funding-eu 195/110, competitions 145/59, national-prizes 114/58, open-source 78/54,
industry 53/17, startups 26/26.

- Stage 4 ran: 253 persons with `first_pub_year`, 179 ORCID ids, 221 current affiliations from ORCID or OpenAlex.
- 99 of 100 rows classify by rule 0 (a title read in the final pass); 97 high confidence.
- Roles in the table: 72 professor, 8 group_leader, 10 researcher, 8 phd_student, 2 industry. Tier 1: 80, tier 2: 18.
- Seeds: 15 of 18 in. Out, correctly: Dongheui Lee (main post TU Wien, AT), Martin Riedmiller (Vesoma, country
  unclear), Sami Haddadin (MBZUAI, AE). Fisher Yu in but low confidence (ETH NCCR page lists him as alumni).
- 273 doctoral students in the candidate pool, 8 in the table: 80 core professors and group leaders fill the cap
  first. Open decision: raise `target_rows` or reserve a doctoral quota.
- Still unreadable: DBLP (Anubis proof-of-work; the browser step passes it but needs a longer wait), OpenReview 403,
  SUPSI pages returned HTTP 500 during the final pass.
