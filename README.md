# talent-scout

An [Agent Skills](https://agentskills.io) package: give it a technical domain, get back a sourced roster of the
people and research groups doing notable work in it, for technology discovery and collaboration. The core region is
Germany + Switzerland, the extended region EU27 + UK + CH + NO; people are discovered across paper awards, national prizes,
EU, DFG and SNSF funding, competitions, startups, industry labs and open source.

Runs in any skills-aware agent (Claude.ai, Claude Code, ChatGPT, Codex, Cursor, ...) using only
web search, page reading and keyless public APIs. Bundled Python scripts are optional accelerators, including a
page reader used once, on the final table, to check current roles from public pages.

## What it does

- Input: a domain phrase (semiconductors, computer architecture, embodied AI, ...). Output: a roster table and a
  group table (CSV + Markdown), each row carrying evidence URLs.
- Two region layers. Every row is in the extended region; rows are sorted into tiers: professors in DE/CH first,
  then DE/CH researchers and doctoral students, then doctoral students elsewhere in the extended region, then everyone
  else. Each person carries a role class (professor, researcher, doctoral student, industry, unknown) with the
  verbatim page evidence it rests on, and a research group (`<PI> @ <institution>`); `groups.csv` lists the groups
  with members, recent outputs, active funding and open-source work.
- Every channel uses the same window: the 36 months ending on the run date. Older evidence stays visible in a
  row but does not qualify or rank anyone.
- It finds people and records their public work. Role, tier and group are data columns and a sort order, nothing more.
- The domain map is derived at run time from universal sources (OpenAlex topics, ERC panels, EuroSciVoc, DFG review
  boards) and cached under `domain-cache/`; switching domains changes no procedure.
- Depth lives in the hop rules (`references/30-hops.md`): orgs, works, teams and companies are turned into
  people with recorded provenance, then people expand one hop to co-authors.
- Portable: follows the Agent Skills open standard and depends on no local MCP server, paid database or
  vendor-specific tool. OpenAlex works keyless; a free API key is needed only once the shared keyless quota runs out.
- Paths: skill files resolve against the directory holding `SKILL.md`; each run writes only into its own run
  directory.

## Layout

```
SKILL.md                 entry point (directory page)
references/              stage-by-stage procedures
  channels/              one playbook per signal channel
assets/                  universal data: country sets, ERC panels, prize registry, schemas, table template
domain-cache/            derived domain maps (cache, refreshable)
scripts/                 optional stdlib-only helpers
```
