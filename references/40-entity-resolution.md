# Stage 4 — Merge signals into persons

## Keys, in order of trust
1. ORCID (academic spine). OpenAlex author records carry it; ORCID public API `https://pub.orcid.org/v3.0/<id>` returns employment history (current affiliation!).
2. OpenAlex author id, DBLP pid, OpenReview id, GEPRIS person id (`ids.gepris`), SNSF person number (`ids.snsf`).
3. GitHub login (engineering spine).
4. Weak key: normalised name + a shared institution token ("Hugging Face, Paris" and "Hugging Face / Sorbonne" match;
   exact-string matching missed six such pairs in the first run).

## Procedure
- Group signals sharing any strong key → one person.
- For remaining signals, attempt the weak key only when the institution matches or the two
  affiliations are linked by a known move (e.g., the ORCID employment history shows both).
- Confidence: `high` (strong key), `medium` (weak key + same domain + plausible timeline),
  `low` (name match only: two rows, each marked `ambiguous`, joined later only by a strong key or a shared institution).
- Current affiliation: ORCID employment with no end date, **unless** it started before the newest evidence and names
  another country (people leave old records open; one run would have sent a professor back to a 1996 post). Then
  OpenAlex `last_known_institutions` when in region, then the newest evidence page. Record which source won and its
  date. When the newest evidence is dated after the OpenAlex record and names another institution, the evidence
  wins too (an arXiv parsing error filed a whole Hugging Face team under Oxford). `scripts/current_affiliation.py`
  applies exactly this order and caches lookups under `cache/affiliation/` so reruns do not re-request.

Current-role checks against web pages and public LinkedIn profiles happen by group after the initial stage-5 export
(`45-web-verification.md`); they do not run per person here.

## Script
`scripts/merge_persons.py signals.jsonl > persons.jsonl` implements the key ladder and leaves name-only
matches as separate rows. Manual path: build the table in the conversation, one row per strong key.

## Known failure modes
- Common names (Chinese, Spanish, German) → always demand a strong key or shared institution.
- OpenAlex `last_known_institutions` can lag 1–2 years or be plain wrong (a hospital, "LIGO"); profiles get mixed
  with namesakes and some people have two ids. Check that the profile's works are in the domain before trusting it.
- arXiv papers can carry one wrong affiliation for every author (LeRobot → Oxford). Prefer the project page or GitHub.
- Industry people rarely have ORCID; GitHub + company page is the pair to look for.
- Name order and diacritics: normalise (NFKD, strip marks, lowercase) before any comparison.

## Role and person fields

Keep `role` on each signal as the participation role (for example `pi` or `first_author`).
`role_class` describes the person. `current_affiliation.py` applies the following rules in order;
stop at the first match. It uses only the standard library.

| priority | evidence | role_class | role_confidence |
|----------|----------|------------|-----------------|
| 1 | Verbatim title: phd student, doctoral student/researcher/candidate, doktorand, dissertation, ph.d. candidate | phd_student | high |
| 1 | Verbatim title: postdoc, postdoctoral, senior scientist, research scientist, senior researcher and lecturer, imaging scientist, clinical scientist, wissenschaftlicher mitarbeiter, research associate, staff scientist, oberassistent | researcher | high |
| 0 | `final_pass_title` read from the person's own or institutional page, with `final_pass_url` and `last_verified` | by title, as rule 1 | high |
| 1 | Verbatim title: professor, prof., Honorarprofessor / Honorary Professor (evidence annotates `honorary`), chair of / chair holder / professor and chair, lehrstuhl, juniorprofessor, assistant/associate professor, faculty member or a bare "Faculty" heading; direktor/director with research-institute context. A bare "Chair" (board, session) is not a professorship | professor | high |
| 1 | Verbatim title: group leader, Research Junior Group Lead, JRG Leader, Junior Research Group Leader, Site Lead, Head of any named area (including Digital Humanities), principal investigator / PI, Nachwuchsgruppenleiter, team leader, lab director | group_leader | high |
| 1 | A heading that joins a doctoral stage with another stage or with staff words ("PhD Students and Scientific Assistants", "Staff / PhD Students") | unknown, evidence says "mixed heading proves membership only" | low |
| 1 | engineer, software, research engineer with institution type company; or a title containing GmbH/AG/Ltd/Inc | industry | high |
| 2 | `erc_*`, `dfg_*`, `snsf_*`, `fwf_*`, `swecris_*`, `rcn_*`, `dff_*`, `fris_*`, `aei_*` signal with `role: pi` and no title seen. A grant proves the person leads a project, not an appointment. Personal grants name the holder's own stage: `snsf_ambizione`, `dfg_walter_benjamin`, `snsf_postdoc_mobility`, `fwf_esprit` → researcher; `snsf_doc_ch`, `snsf_doc_mobility` → phd_student | group_leader, or the personal-grant stage | medium |
| before titles (rule 3) | Current company employer; a literal professorial title remains professor and mixed headings remain unknown | industry | high for a dated final-pass page; medium for provider/name evidence |
| 4 | Run year minus `first_pub_year` is 0–5 and strictly more than half of all signals have `role: first_author` | phd_student | low |
| 4 | Run year minus `first_pub_year` is at least 10 and strictly more than half of all signals have `role: last_author` or `pi` | group_leader | low |
| 4 | All other cases, including a missing/invalid publication year or no majority | unknown | low |

The employer check runs before title mapping and funding inference. Use the first available affiliation in
`final_pass_affiliation`, `current_affiliation`, newest signal `affiliation_raw`. Match the company-name list
(NAVER, DeepMind, Google, Meta/FAIR, Sony, Bosch, Mistral, Aleph Alpha, Microsoft, NVIDIA, Amazon, Apple,
Hugging Face), the word forms GmbH / AG / Ltd / Inc / SA / SAS / B.V. / Labs / Research Europe, or a matching
OpenAlex `institution.type == company`. A current academic affiliation suppresses a former company's type.
Preserve the original title in evidence as `industry | Research Scientist | …`; do not infer a professor from
company leadership. `fwf_project`, `swecris_project`, `rcn_project`, `dff_project`, `fris_project`, `aei_project`
and `fwf_start` with `role: pi` map to group_leader at medium confidence; `fwf_esprit` maps to researcher.

Within rule 1 a supervisor mention ("… in the group of Prof. Meyer", "supervised by …") is cut off before matching,
so the person's own title decides. One person's joined titles ("Professor and Head of Lab", "Senior Scientist and
Group Leader") keep the highest class in the order phd_student, professor, group_leader, researcher.
The patterns accept plural and German feminine forms ("Doctoral students", "Professors", "Wissenschaftliche
Mitarbeiterinnen"), because a section heading is the usual `role_title` on people pages.
Rule 1 sources are signal `role_title`, current ORCID employment `role-title`, and a final-pass
LinkedIn headline. Within this rule, use the dated final-pass headline first, then current ORCID,
then signal titles from newest to oldest. Stale ORCID employment rejected during affiliation resolution
also cannot supply a title. OpenAlex type applies only when its institution is the selected current
institution. A generic director title without institute context does not imply professor.

Every classification writes `role_evidence` as `<source> | <verbatim excerpt> | <URL>`; the source
includes `rule 1`, `rule 2`, `rule 3` or `rule 4`. Inference records the publication year, run year and
participation roles instead of inventing a quoted title. For `Wissenschaftlicher Mitarbeiter`, the source
also includes `DE: may be PhD student`. Rule 4 without any source URL keeps that component empty.

Signal `topics` contains 1–3 phrases copied verbatim from a paper title, project name or repository name;
`role_title` is also verbatim. The schema retains an open signal-type vocabulary, including
`dfg_project`, `dfg_emmy_noether`, `dfg_heisenberg`, `snsf_project`, `snsf_starting_grant`,
`snsf_ambizione`, `snsf_professorship`, `graduiertenkolleg_member` and `imprs_member`.
Funding signals prefixed `erc_`, `dfg_`, `snsf_`, `fwf_`, `swecris_`, `rcn_`, `dff_`, `fris_` or `aei_` carry `role: pi`. Membership signals alone do not establish
a doctoral role. Person `topics` is the union of signal topics in input order, deduplicated exactly and
limited to five; do not paraphrase or case-fold the phrases.

`group` is `<PI name> @ <institution>`, using the leader's displayed institution. Leaders are people with
`role_class` professor/group_leader or a pi/last_author signal. A PI signal anchors its own group. A leader
without a PI signal can belong to another leader's team. Apply these rules in order; ambiguity stops the search:

| group rule | link evidence |
|------------|---------------|
| 1 | A signal `parent` equals a leader's name/name_raw, or that leader's signal parent/affiliation_raw/homepage or person homepage; compare after casefold, accent removal and stripping academic titles |
| 2 | Member and leader homepages share a non-generic host. Personal github.io subdomains and lab domains count; sites.google.com, github.com, personnel directories and institution roots do not. A www-prefixed lab subdomain can count |
| 3 | An open-source member repository's GitHub organization matches any leader evidence URL/homepage organization |
| 4 | Same current institution and shared parent or a shared-paper last author, with matching signal institutions; leader self anchors also record rule 4 |
| none | Empty group and `group_evidence: unattached` |

For multiple candidates, retain those at the member's institution; if there is still not exactly one, leave
`group` empty and record `ambiguous: A, B`. A single explicit link in rules 1–3 does not require the same
institution. Preserve that distinction when reviewing moves or cross-institution groups. Resolve a linked
leader's own membership to its final PI and record the chain; cyclic or unresolved leader chains remain
ambiguous. An isolated last-author signal without a linked member does not invent a team.

Compare institution names using only the first `||` segment, casefold, accent removal and removal of generic
articles/prefixes (`the`, `university of`, `Universität`, `Université`, `Universiteit van`). Matching institutional
OpenAlex IDs (`institution_id`, `ids.openalex_institution`, `institution.id`) or RORs (`ror`, `ids.ror`,
`institution.ror`) also count; an OpenAlex **author** ID does not. `assets/institution-aliases.yaml` supplies
aliases such as EPFL / École Polytechnique Fédérale de Lausanne. It uses the JSON subset of YAML so the loader
needs only the standard library. This normalization is for comparison; displayed affiliations stay verbatim.

Every assigned group has `group_evidence: rule N: <match> | <URL>` and `group_rule` (integer; null if
unattached). The evidence appendix includes it; the fixed person table does not add a column.

Stage 4 emits `role_class`, `role_evidence`, `role_confidence`, `topics`, `group`, `group_evidence`, `group_rule`, `tier` and `last_verified`.
The tier helper lives in `table_export.py` (see `50-output.md`) and is reused by both stage-4 CLIs.
Export recomputes tiers using the requested regions. Out-of-region persons carry a placeholder tier 4
in stage 4 and are excluded from the roster.

`last_verified` starts as `""`. Only the final pass that actually reads a person's page may fill it with
the read date; lookups, merging and table export do not verify a person or manufacture a date.
Enrichment and export preserve an explicitly supplied verification date. For a reviewed final-pass
LinkedIn headline, supply `linkedin_headline` and `linkedin_url` on the person together with that date;
a headline without `last_verified` is ignored. These are optional input adapters, not new output columns.
Do not mark a refused page as verified. `visit_page.py` retains `role_verified: false` until a human/agent
reviews what was read.

Pass the same run date to stage 4 and export, for example:

```sh
python3 "$SKILL_ROOT/scripts/merge_persons.py" "$RUN_DIR/signals.jsonl" --date 2026-10-12 > "$RUN_DIR/persons.jsonl"
python3 "$SKILL_ROOT/scripts/current_affiliation.py" "$RUN_DIR/persons.jsonl" --date 2026-10-12 --region-core DE+CH --region EU27+UK+CH+NO --cache-dir "$RUN_DIR/cache/affiliation" > "$RUN_DIR/persons.enriched.jsonl"
```

The first command is offline. The optional enrichment command uses provider lookups and caches responses;
it preserves input order even with multiple workers. Run artifacts and caches belong under `RUN_DIR`.

A supplied `final_pass_affiliation` and `final_pass_country` override provider affiliation and country before tier calculation. The original affiliation/source is retained in notes. See `45-web-verification.md`. Use `--offline --cache-dir <existing-cache>` to read caches without network or cache writes; missing queries are skipped and counted.
