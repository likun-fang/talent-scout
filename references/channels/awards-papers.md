# Channel: top-venue paper awards

Signal types: `best_paper`, `outstanding_paper`, `distinguished_paper`, `best_student_paper`, `test_of_time` (low strength for finding current people).

## Sources
1. jeffhuang.com/best_paper_awards — 32 CS venues since 1996, hand-maintained, includes ISCA, MICRO-adjacent venues, AAAI, CHI, etc. **Caveat:** lists only each author's *first* affiliation and sometimes only the first author; a European co-author at position 3 is invisible here. Use it to get paper titles, then resolve full author lists via OpenAlex/DBLP.
2. github.com/FeijiangHan/Top-Conference-Best-Papers — ICLR/NeurIPS/ICML/ACL/EMNLP/NAACL/AAAI/CVPR/ECCV, 2022+, full author lists, no affiliations.
3. Per-venue award pages from the domain map (robotics venues ICRA/IROS/RSS/CoRL, circuits ISSCC/VLSI/DAC, systems OSDI/SOSP/EuroSys have **no** cross-venue aggregator).

## Where the lists actually are (2026-10 run)
- Conference award pages are unstable: corl.org/program/awards 404s, corl2022.org now redirects to an unrelated
  site, IROS 2024 returned 403, Humanoids publishes no list, RSS 2023 and ICRA 2026 name finalists only.
  Reliable substitutes: year-stamped pages (`roboticsconference.org/<year>/program/awards/`,
  `<year>.corl.org/program/awards`), the robohub / aihub award round-ups, RA-L and T-RO award pages on
  ieee-ras.org, institutional press releases. Record the year-stamped or archived URL, never the bare `/awards/`.
- Mark finalists `medium` and winners `high`; say in `snippet` which it was.

## Procedure
- For each venue × year in window: get award page → list of (title, authors). Emit one `work` signal per paper with the award page as evidence.
- Resolve each title via `https://api.openalex.org/works?search=<title>&per_page=1` (or DBLP) to get the full author list with institutions and countries. Emit a `person` signal per author whose institution is in region, with `role` by author position. Keep non-region authors out of the table but note them in the work signal.
- Workshop awards and "honorable mention" count as `medium`.

## Optional recent ordinary papers

Only run this extension when `run.meta.json.sourcing_extensions.recent_papers` is explicitly `true`. The existing
award sweep stays unchanged and uses the same channel budget; do it first and report any ordinary-paper queries
skipped at the remaining budget. Missing or false means awards only.

- Query recent works using the domain map's selected topics, `region_extended` and both window boundaries; use
  the selected venues to focus the results, and verify domain keywords against each title/abstract. For an adjacent
  topic, the topic ID alone never establishes domain fit. Record queries, ordering and result limits in coverage.
- Resolve each relevant work to its full author list using the same procedure above; check affiliations rather
  than assuming every coauthor of a European paper is in Europe. Deduplicate versions by DOI or canonical work ID
  and retain the actual publication date. An arXiv preprint and its conference version are not independent works.
- Emit `signal_type: paper` under `channel: awards-papers`, for both work and person signals. Use `medium` for a
  directly evidenced, domain-relevant paper with a resolved author list, or `low` when attribution/fit remains
  uncertain (explain the uncertainty). Never give an ordinary paper award strength or an award signal type.
  Keep award evidence separately when the same work really won an award.
- Preserve `parent`, `hop_depth`, author-position `role`, and verbatim topic phrases under the normal hop rules.
  Publication authorship does not establish a current job title; do not infer `role_title` from author order.

## Traps
- OpenAlex often has **empty institutions for arXiv-only versions** of award papers (checked 2025 ICRA best paper: 7 authors, 0 institutions). When that happens, take affiliations from the award page, the PDF header, DBLP, or the author's ORCID record, and say which.
- OpenAlex `search=` treats `?` and `*` as wildcards; strip them from titles.
- Award pages often list affiliations at publication time; a person may have moved. Record as `affiliation_raw`; stage 4 fetches current affiliation.
- Several venues give awards per track; capture the track name in `snippet`.

## role_title and topics
- `role_title`: copy a title only when the award page prints it next to the name. Author lists carry none; author
  position goes into `role`, and "best student paper" belongs in `snippet`, not in `role_title`.
- `topics`: 1–3 phrases cut from the paper title as written ("legged locomotion", "diffusion policy").
