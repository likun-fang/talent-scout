# Channel: top-venue paper awards

Signal types: `best_paper`, `outstanding_paper`, `distinguished_paper`, `best_student_paper`, `test_of_time` (low strength for finding current people).

## Sources
1. jeffhuang.com/best_paper_awards — 32 CS venues since 1996, hand-maintained, includes ISCA, MICRO-adjacent venues, AAAI, CHI, etc. **Caveat:** lists only each author's *first* affiliation and sometimes only the first author; a European co-author at position 3 is invisible here. Use it to get paper titles, then resolve full author lists via OpenAlex/DBLP.
2. github.com/FeijiangHan/Top-Conference-Best-Papers — ICLR/NeurIPS/ICML/ACL/EMNLP/NAACL/AAAI/CVPR/ECCV, 2022+, full author lists, no affiliations.
3. Per-venue award pages from the domain map (robotics venues ICRA/IROS/RSS/CoRL, circuits ISSCC/VLSI/DAC, systems OSDI/SOSP/EuroSys have **no** cross-venue aggregator).

## Procedure
- For each venue × year in window: get award page → list of (title, authors). Emit one `work` signal per paper with the award page as evidence.
- Resolve each title via `https://api.openalex.org/works?search=<title>&per_page=1` (or DBLP) to get the full author list with institutions and countries. Emit a `person` signal per author whose institution is in region, with `role` by author position. Keep non-region authors out of the table but note them in the work signal.
- Workshop awards and "honorable mention" count as `medium`.

## Traps
- Award pages often list affiliations at publication time; a person may have moved. Record as `affiliation_raw`; stage 4 fetches current affiliation.
- Several venues give awards per track; capture the track name in `snippet`.
