# Stage 4 — Merge signals into persons

## Keys, in order of trust
1. ORCID (academic spine). OpenAlex author records carry it; ORCID public API `https://pub.orcid.org/v3.0/<id>` returns employment history (current affiliation!).
2. OpenAlex author id, DBLP pid, OpenReview id.
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
