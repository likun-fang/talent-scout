# Stage 2 — Channels → signals

Every channel emits **signals** in one schema (`assets/signal.schema.json`). A signal points at a
person, or at something that can be hopped to people later (org, work, team, company). Do not try
to resolve people inside the channel sweep; that is stage 3.

```json
{"kind": "person|org|work|team|company",
 "name_raw": "...", "affiliation_raw": "...", "country": "DE",
 "role": "first_author|last_author|coauthor|pi|team_member|founder|maintainer|inventor|unknown",
 "channel": "awards-papers", "signal_type": "best_paper", "strength": "high|medium|low",
 "date": "2025-06", "evidence_url": "https://...", "snippet": "verbatim text that supports the claim",
 "hop_depth": 0}
```

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
