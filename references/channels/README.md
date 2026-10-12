# Stage 2 — Channels → signals

Every channel emits **signals** in one schema (`assets/signal.schema.json`). A signal points at a person, or at
something that is hopped to people (org, work, team, company). Each channel does its own hops (rules in
`../30-hops.md`): emit the non-person signal, then one person signal per person in `region_extended` with
`hop_depth: 1` and `parent` set. Write `signals/<channel>.jsonl` and `signals/<channel>.coverage.md` (pages read, skipped at budget,
rosters not public, where the method did not fit reality). Wherever a channel file says "in region", read
`region_extended`; `region_core` decides the tier later, not who gets a signal.

```json
{"kind": "person|org|work|team|company",
 "name_raw": "...", "affiliation_raw": "...", "country": "DE",
 "role": "first_author|last_author|coauthor|pi|team_member|founder|maintainer|inventor|unknown",
 "channel": "awards-papers", "signal_type": "best_paper", "strength": "high|medium|low",
 "date": "2025-06", "evidence_url": "https://...", "snippet": "verbatim text that supports the claim",
 "ids": {"openalex": "A5027377212", "orcid": "0000-...", "github": "login"},
 "hop_depth": 0, "parent": "name_raw of the hopped-from signal", "note": "optional caveat",
 "fit": "core|adjacent", "homepage": "https://lab-or-personal-page",
 "role_title": "Doctoral researchers", "topics": ["vision-language-action", "dexterous manipulation"]}
```

Tag every signal with `fit`: `core` when the work is the domain itself, `adjacent` when it is general robotics or a
neighbouring field (broad RoboCup leagues, exoskeletons, electronics-side ERC panels). The export can then filter on
it. Add `homepage` when the source page links a lab or personal page.

`role_title` and `topics` feed the role, tier and group columns of stage 4. `role_title` is the title printed with
the name on the evidence page (a position line or prefix such as "Professor", "Prof. Dr.", "Senior Scientist"), else
the heading of the section the name sits under ("Doctoral students", "Wissenschaftlicher Mitarbeiter"), copied
verbatim; leave it empty when the page prints neither. Never derive it from author position, degree suffixes or the
funding scheme. `topics` holds 1–3 key phrases cut verbatim from the paper title, project name or repository name the
signal rests on, without paraphrase or translation. Each channel file says where both come from on its sources.

Fill `ids` whenever a source gives them: they are the merge keys in stage 4. Attach an OpenAlex id only when
that profile's works match the domain; name search alone returned a chemist for one robotics founder.

`strength` is about the signal, not the person: a best-paper award is high, a conference competition
3rd place is medium, a GitHub star count is low.

| Channel | File | Structured source? |
|---------|------|--------------------|
| Top-venue paper awards | `awards-papers.md` | partial (two cross-venue lists), otherwise award pages |
| EU funding (ERC, CORDIS, Chips JU, EuroHPC, EIC) | `funding-eu.md` | yes: PDFs + CSV |
| Core-region funding (DFG GEPRIS, SNSF; Research Training Groups, IMPRS) | `funding-de-ch.md` | yes: GEPRIS JSON backend, SNSF CSV datasets; member pages for doctoral students |
| National prizes and academies | `national-prizes.md` | registry in `assets/national-prizes.yaml`, pages per prize |
| Competitions | `competitions.md` | no: results pages + team documents |
| Startups | `startups.md` | partial: EIC PDFs; company pages |
| Industry labs / competitors | `industry.md` | partial: OpenAlex company affiliations, patents |
| Open source | `open-source.md` | yes: GitHub anonymous API |

Stop a channel at its page budget. Write a `skipped` note listing what was not read so the gap is visible.

## Date rules (all channels)

Use `window_start` and `window_end` from `run.meta.json`: by default the 36 months ending on the run date.
For 2026-10-12, the window is 2023-10-12 to 2026-10-12, inclusive.

- Awards and prizes: award date/year; competitions: the relevant result date/year.
- Funding: award/selection date, or project start date if award date is unavailable (say which in `note`).
  An older grant still running today is background, unless there is a separately evidenced recent output.
- Industry: publication, patent publication, talk, or engineering post date.
- Startups: dated funding, product, or technical milestone; an undated founder biography is background.
- Open source: dated contributions/releases in the window, attributable to the person. Lifetime stars or
  a currently accessible maintainer page alone do not demonstrate recent activity. Bound git logs with
  both `--since` and `--until` for the window (include the full end day).

Store `date` as YYYY, YYYY-MM, or YYYY-MM-DD; year/month-only dates are interpreted as their first day.
Never substitute the crawl date for an unknown event date. Old and undated sources can help identify
people or verify affiliations; emit them, with the true date or none, and the export keeps them as
evidence without letting them qualify or rank a person. Record unresolved dates in channel coverage. A fresh parent event does not prove that an old team roster
participated: confirm membership for that event before inheriting its date in a person signal.
