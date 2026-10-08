# Stage 2 — Channels → signals

Every channel emits **signals** in one schema (`assets/signal.schema.json`). A signal points at a person, or at
something that is hopped to people (org, work, team, company). Each channel does its own hops (rules in
`../30-hops.md`): emit the non-person signal, then one person signal per in-region person with `hop_depth: 1` and
`parent` set. Write `signals/<channel>.jsonl` and `signals/<channel>.coverage.md` (pages read, skipped at budget,
rosters not public, where the method did not fit reality).

```json
{"kind": "person|org|work|team|company",
 "name_raw": "...", "affiliation_raw": "...", "country": "DE",
 "role": "first_author|last_author|coauthor|pi|team_member|founder|maintainer|inventor|unknown",
 "channel": "awards-papers", "signal_type": "best_paper", "strength": "high|medium|low",
 "date": "2025-06", "evidence_url": "https://...", "snippet": "verbatim text that supports the claim",
 "ids": {"openalex": "A5027377212", "orcid": "0000-...", "github": "login"},
 "hop_depth": 0, "parent": "name_raw of the hopped-from signal", "note": "optional caveat",
 "fit": "core|adjacent", "homepage": "https://lab-or-personal-page"}
```

Tag every signal with `fit`: `core` when the work is the domain itself, `adjacent` when it is general robotics or a
neighbouring field (broad RoboCup leagues, exoskeletons, electronics-side ERC panels). The export can then filter on
it. Add `homepage` when the source page links a lab or personal page.

Fill `ids` whenever a source gives them: they are the merge keys in stage 4. Attach an OpenAlex id only when
that profile's works match the domain; name search alone returned a chemist for one robotics founder.

`strength` is about the signal, not the person: a best-paper award is high, a conference competition
3rd place is medium, a GitHub star count is low.

| Channel | File | Structured source? |
|---------|------|--------------------|
| Top-venue paper awards | `awards-papers.md` | partial (two cross-venue lists), otherwise award pages |
| EU funding (ERC, CORDIS, Chips JU, EuroHPC, EIC) | `funding-eu.md` | yes: PDFs + CSV |
| National prizes and academies | `national-prizes.md` | registry in `assets/national-prizes.yaml`, pages per prize |
| Competitions | `competitions.md` | no: results pages + team documents |
| Startups | `startups.md` | partial: EIC PDFs; company pages |
| Industry labs / competitors | `industry.md` | partial: OpenAlex company affiliations, patents |
| Open source | `open-source.md` | yes: GitHub anonymous API |

Stop a channel at its page budget. Write a `skipped` note listing what was not read so the gap is visible.
