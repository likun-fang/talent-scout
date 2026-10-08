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

## Traps
- OpenAlex often has **empty institutions for arXiv-only versions** of award papers (checked 2025 ICRA best paper: 7 authors, 0 institutions). When that happens, take affiliations from the award page, the PDF header, DBLP, or the author's ORCID record, and say which.
- OpenAlex `search=` treats `?` and `*` as wildcards; strip them from titles.
- Award pages often list affiliations at publication time; a person may have moved. Record as `affiliation_raw`; stage 4 fetches current affiliation.
- Several venues give awards per track; capture the track name in `snippet`.
