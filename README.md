# talent-scout

An [Agent Skills](https://agentskills.io) package: give it a technical domain, get back a sourced
roster table of notable people in Europe (EU27 + UK + CH by default), discovered across paper
awards, national prizes, EU funding, competitions, startups, industry labs and open source.

Runs in any skills-aware agent (Claude.ai, Claude Code, ChatGPT, Codex, Cursor, ...) using only
web search, page reading and keyless public APIs. Bundled Python scripts are optional accelerators.

## 中文说明

- 用途:用户给一个领域(半导体 / 计算 / 具身智能 …),输出带出处的人才名单表格(CSV + Markdown)。
- 只找人、只给资料,不做可招聘性判断。职业阶段 / 角色只是表里的一列。
- 领域包不是手填的:第 1 阶段从 OpenAlex、ERC panel、EuroSciVoc 等通用源**推导**出该领域的
  会议、奖项、赛事、资助代码和实验室清单,结果缓存到 `domain-cache/`,换领域不改管线。
- 深度在「跳转规则」(`references/30-hops.md`):从机构、论文、队伍、公司跳到人,再从人扩一跳。
- 跨平台:遵循 Agent Skills 开放标准,不依赖本机 MCP、API key 或特定工具。

## Layout

```
SKILL.md                 entry point (directory page)
references/              stage-by-stage procedures
  channels/              one playbook per signal channel
assets/                  universal data: country sets, ERC panels, prize registry, schemas, table template
domain-cache/            derived domain maps (cache, refreshable)
scripts/                 optional stdlib-only helpers
eval/                    golden lists for recall checks
```
