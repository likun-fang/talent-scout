# Stage 4 — Merge signals into persons

## Keys, in order of trust
1. ORCID (academic spine). OpenAlex author records carry it; ORCID public API `https://pub.orcid.org/v3.0/<id>` returns employment history (current affiliation!).
2. OpenAlex author id, DBLP pid, OpenReview id.
3. GitHub login (engineering spine).
4. Weak key: normalised name + institution + overlapping year window.

## Procedure
- Group signals sharing any strong key → one person.
- For remaining signals, attempt the weak key only when the institution matches or the two
  affiliations are linked by a known move (e.g., the ORCID employment history shows both).
- Confidence: `high` (strong key), `medium` (weak key + same domain + plausible timeline),
  `low` (name match only; keep as **separate rows** marked `ambiguous`, do not merge).
- Current affiliation: prefer ORCID employment with no end date, then the most recent OpenAlex
  `last_known_institutions`, then the newest evidence page. Record which source won and its date.

## Script
`scripts/merge_persons.py signals.jsonl > persons.jsonl` implements the key ladder; it never merges
on name alone. Manual path: build the table in the conversation, one row per strong key.

## Known failure modes
- Common names (Chinese, Spanish, German) → always demand a strong key or shared institution.
- OpenAlex `last_known_institutions` can lag 1–2 years; ORCID is often more current for academics.
- Industry people rarely have ORCID; GitHub + company page is the pair to look for.
- Name order and diacritics: normalise (NFKD, strip marks, lowercase) before any comparison.
