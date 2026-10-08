# Landscape: what already exists, and what we take from it

Surveyed 2026-10-08 (web search, keyless). Maintainer notes, not runtime instructions.

## A. Talent / expert discovery products

| Product | What it does | Sources | How it gets to a person | Output | Take | Gap we fill |
|---|---|---|---|---|---|---|
| SeekOut, hireEZ, Findem, Pin, AmazingHiring, Juicebox | Commercial talent-intelligence aggregators, 500M–1B profiles | LinkedIn + GitHub + patents + papers + Stack Overflow | Pre-built person index; search → ranked profiles | Profile cards with "evidence" links (Pin), match scores | **Attach evidence links to each row** (Pin), multi-source per person | Paid, US-centric (SeekOut reviewers: little advantage in Europe), outreach-oriented, opaque scoring |
| AMiner (Tsinghua) | Scholar profiles, AI 2000 "most influential" lists by sub-field, rising-star lists | Own index of 270M papers / 133M scholars | Citation-ranked per sub-field from top venues | Ranked lists per sub-field, per year | **Sub-field × top-venue × time-window** as the ranking frame; publish yearly lists | Citation-only, no competitions/funding/open source; China-hosted |
| CheckMyManuscript Expert Finder | Upload a document → researchers whose work is closest, with a reason each | OpenAlex | Semantic match on works, then authors | Shortlist with one-line reason, affiliation | **Document-as-query** beats keywords; "absence from the list is not absence from the field" disclaimer; shows no contact details | Single channel (papers), no region filter, no table |
| OpenClaw "Expert Finder" skill | Finds domain experts from Twitter/Reddit activity | Social posts | Tiered query expansion (core / jargon / adjacent / discussion), author frequency, classify, score | Markdown report with types and 0–100 score | **Tiered query expansion** is reusable for stage-1 keyword derivation | Social-only, scoring without evidence URLs |
| MLCommons Rising Stars, AI 2000, KAUST Rising Stars | Curated cohorts of early-career people | Applications / citations | Human or algorithmic selection | Named cohort pages | Cohort pages are **high-precision signal pages**; add to national-prizes registry as "cohort programmes" | Narrow fields, not Europe-specific |

## B. Open data / disambiguation building blocks

| Thing | Use for us | Caveat |
|---|---|---|
| OpenAlex API | Topics → venues/institutions/authors; works → full author list with institutions, countries, ORCID | **Since 2026-02-13 an API key is required beyond ~100 calls/day; free key gives 100k/day.** Treat as "free key", not "keyless". ORCID present on ~1 in 6 authorships; `last_known_institutions` lags |
| ourresearch/openalex-name-disambiguation | Shows which features OpenAlex uses (name, institution, co-authors, ORCID) | Don't reimplement; consume author ids |
| openalexR, pyalex | Reference clients | We stay stdlib-only |
| ORCID public API | Employment history with dates = current affiliation | Industry coverage low |
| OpenAIRE Graph | EU-funded publications linked to grants and orgs | Overlaps CORDIS; useful for project → publications → authors hop |
| EURAXESS | Jobs/funding portal, not a people index | Not a source of people |
| GitRoll, OSS Insight | Developer vetting / repo activity rankings | GitRoll is a marketplace; OSS Insight ranks repos not people |

## C. Agent-skill precedents

| Skill | Structure worth copying | What not to copy |
|---|---|---|
| smixs/osint-skill | Phase 0 tooling self-check; graceful degradation by available APIs; cheap→expensive escalation ladder; A/B/C/D fact grades; dossier template in assets/; stdlib-only MCP client | Psychoprofile, social scraping, paid API dependence |
| "Professional People Search" (Claude Code skill) | Structured summaries with source citations | LinkedIn-derived career timelines |
| anthropics/skills, alirezarezvani/claude-skills | SKILL.md as a directory page; stdlib-only scripts; references/ for depth | Monolithic SKILL.md (SkillsBench: bloated skills reduce pass rate) |

## Design lessons taken

1. Evidence per row is the product, not the ranking. Commercial tools that show "why" (Pin, Juicebox, Expert Finder) are the ones users trust.
2. Rank frame = sub-field × top venues × time window (AMiner). Our stage 1 derives exactly these three from OpenAlex instead of hand lists.
3. Say what the index cannot see. Expert Finder's "absence is not evidence" is our Coverage block.
4. Environment self-check first, then degrade gracefully (osint-skill). Our stage 0.
5. Nobody covers Europe across funding + competitions + awards + open source in one table. That gap, plus the GDPR-clean "public professional record only" posture, is the reason to build.
