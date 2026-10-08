# talent-scout

An [Agent Skills](https://agentskills.io) package: give it a technical domain, get back a sourced
roster table of notable people in Europe (EU27 + UK + CH by default), discovered across paper
awards, national prizes, EU funding, competitions, startups, industry labs and open source.

Runs in any skills-aware agent (Claude.ai, Claude Code, ChatGPT, Codex, Cursor, ...) using only
web search, page reading and keyless public APIs. Bundled Python scripts are optional accelerators.

## What it does

- Input: a domain phrase (semiconductors, computer architecture, embodied AI, ...). Output: a roster table
  (CSV + Markdown) of people, each row carrying evidence URLs.
- It finds people and records their public work. Role and career stage are data columns, nothing more.
- The domain map is derived at run time from universal sources (OpenAlex topics, ERC panels, EuroSciVoc) and
  cached under `domain-cache/`; switching domains changes no procedure.
- Depth lives in the hop rules (`references/30-hops.md`): orgs, works, teams and companies are turned into
  people with recorded provenance, then people expand one hop to co-authors.
- Portable: follows the Agent Skills open standard and depends on no local MCP server, paid database or
  vendor-specific tool. OpenAlex needs a free API key beyond about 100 calls a day.

## Layout

```
SKILL.md                 entry point (directory page)
references/              stage-by-stage procedures
  channels/              one playbook per signal channel
assets/                  universal data: country sets, ERC panels, prize registry, schemas, table template
domain-cache/            derived domain maps (cache, refreshable)
scripts/                 optional stdlib-only helpers
```
