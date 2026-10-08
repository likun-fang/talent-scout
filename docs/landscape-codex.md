<!-- Independent survey written by a Codex (GPT-6) agent on 2026-10-08 from the brief in this repo's history. Kept verbatim as maintainer reference; see landscape.md for the merged conclusions. -->
# 公开信号驱动的人物发现：同类产品、开源组件与 Agent Skills 调研

调研日期：2026-10-08。共收录 **16 个对象：A 类 4 个、B 类 4 个、C 类 3 个、D 类 5 个**。

我的判断：本次核查到的对象已经分别解决了学术作者发现、代码贡献者发现、跨源实体归并和带来源的调研报告，但尚未核实到一个现成产品同时满足“输入技术领域、跨奖项／论文／资助／赛事／公司／开源发现人、逐条保留出处、以跨平台 SKILL.md 交付、无需付费数据库”这组要求。这里的机会主要在把这些环节接起来，并把证据链做扎实。

优先研究顺序：**Exa Research Orchestrator → Browserbase Company Research → OpenSanctions 的证据模型 → CSRankings → GitHub Talent MCP**。前三个分别提供工作流、交付物和数据模型参考；后两个展示两条实际的人物发现路径。

核查方法：搜索官方产品文档和 GitHub，读取 README、相关代码及 D 类全部 5 份 SKILL.md 原文；也用 `skills find` 核查已发布技能。没有安装或运行这些项目，没有测量其效果，也没有登录付费产品。以下“缺口”指公开资料及所读实现尚未提供的能力，不代表证明了厂商所有版本都不存在该能力。收费产品作为设计参照，不作为拟议工具的必需依赖；免费 API、付费搜索服务和付费数据库分别标明。

## A. 人才／专家发现产品

### A1. CSRankings

| 字段 | 调研结果 |
| --- | --- |
| 名称 | CSRankings，计算机科学领域的机构与活跃教师发现工具。 |
| URL | [产品与方法说明](https://csrankings.org/faq.html)；[代码与数据仓库](https://github.com/emeryberger/CSrankings)。 |
| 做什么 | 按研究方向、地区及年份查看机构研究产出，并展开到教师；与“给一个领域，从高水平成果找到人”的入口高度相似。 |
| 数据源 | DBLP 论文记录、维护者及用户提交的教师名单、机构、个人主页等；领域对应的会议集合由项目明确维护。 |
| 怎么从信号到人 | 选领域与会议 → 匹配论文作者 → 用维护的教师记录及 DBLP 消歧名称关联机构。其提交流程显式处理改单位和 DBLP 同名后缀，不是单纯依赖姓名字符串。 |
| 输出形态 | 可交互机构／教师列表、论文产出统计、个人主页链接，以及仓库内的数据文件。 |
| 值得借鉴 | 把“领域对应哪些会议”变成可审查的配置，同时维护独立的“人—机构”记录。领域入口和身份维护均可复用其思路。 |
| 我们需要补齐 | 主要覆盖符合其收录条件的教师，不能代表全部作者、工程师和赛事成员；统计论文发表也不等于核实论文获奖。还需奖项、资助、赛事和开源连接。 |
| 依赖与采用判断 | 适合借鉴产品结构。其 FAQ 标示代码／数据采用 CC BY-NC-ND 4.0，并明确限制衍生分发；**代码可见不代表可直接移植进商业 Skill**。 |

### A2. Scholia

| 字段 | 调研结果 |
| --- | --- |
| 名称 | Scholia，基于 Wikidata 的学术人物与主题画像。 |
| URL | [官方文档](https://scholia.readthedocs.io/en/latest/)；[代码仓库](https://github.com/WDscholia/scholia)。 |
| 做什么 | 为研究者、机构、主题、论文、会议和奖项生成学术视图；尤其适合从主题或机构进入，再沿关系找到人。 |
| 数据源 | Wikidata 与 Wikidata Query Service 的 SPARQL 查询。页面展示的信息取决于 Wikidata 已有记录。 |
| 怎么从信号到人 | 从主题、论文或机构关系查询关联的作者实体，再以 Wikidata QID 聚合人物。它主要利用已有实体关系，而非自行把任意网页上的同名人物消歧。 |
| 输出形态 | 人物／机构页面、论文列表、任职时间线、合作与主题网络、引文图；底层查询可查看和复用。 |
| 值得借鉴 | 为同一实体提供多个入口：用户可以从领域、获奖成果或机构进入，最终落到同一个人的证据集合。 |
| 我们需要补齐 | Wikidata 未建人物实体、只保留作者姓名或缺少团队成员关系时，Scholia 无法补出事实；需要主动读取原始名单、个人主页与成员页。 |
| 依赖与采用判断 | 公开代码及开放图谱，适合借鉴查询模式。已核读文档和仓库，未验证其在线服务的实时响应与覆盖率。 |

### A3. OpenAIRE EXPLORE／OpenAIRE Graph

| 字段 | 调研结果 |
| --- | --- |
| 名称 | OpenAIRE EXPLORE 及其底层 OpenAIRE Graph。 |
| URL | [EXPLORE](https://explore.openaire.eu/)；[官方服务说明](https://catalogue.openaire.eu/service/openaire.explore)；[人物 API 文档](https://graph.openaire.eu/docs/next/apis/graph-api-v4/persons/)。 |
| 做什么 | 检索相互关联的研究成果、项目、机构和资助信息，是本清单中与欧洲科研体系最贴近的发现产品之一。 |
| 数据源 | 聚合的科研仓储、出版平台、研究信息及资助元数据；Graph 连接成果、作者、机构、资助方等对象。 |
| 怎么从信号到人 | 从项目或主题检索成果 → 沿作者／贡献者关系找人 → 使用图谱内的人物标识继续查询。人物接口与成果关系减少了逐篇手工搜作者的工作。 |
| 输出形态 | 检索页面、关联记录、API JSON 和图谱数据发布；不是专门的人才名单交付模板。 |
| 值得借鉴 | 把“项目—成果—作者”作为明确的多跳路径，避免把项目合作机构的负责人误当成项目所有参与者。 |
| 我们需要补齐 | 获奖性质、赛事成员、代码贡献者及公司早期技术成员不属于它所展示的统一发现工作流；还要保留原始证据并补足断裂关系。 |
| 依赖与采用判断 | 可作为开放学术骨干。此次所核人物端点位于 `next` 文档并使用 `api-beta`，不能写成已验证的稳定生产接口；接入时应确认版本。 |

### A4. AmazingHiring

| 字段 | 调研结果 |
| --- | --- |
| 名称 | AmazingHiring，技术人才跨平台搜索与画像聚合产品。 |
| URL | [产品官网](https://amazinghiring.com/)；[聚合机制说明](https://help.amazinghiring.com/article/4827)；[Search API 文档](https://help.amazinghiring.com/help/article/search-api-en)。 |
| 做什么 | 把多个平台上的技术人才公开资料合并为可搜索档案，是直接的人才发现竞品。 |
| 数据源 | 官方列出的来源包括 GitHub、Stack Overflow、Kaggle 等职业／技术平台，也包括 LinkedIn 等其他来源；这里只借鉴公开学术与开源信号的聚合方式。 |
| 怎么从信号到人 | 从技术关键词和来源平台筛选候选档案，再汇总多个账户链接。API 支持按来源域名包含／排除，但公开文档没有解释足够细的跨账户身份合并算法。 |
| 输出形态 | 搜索结果、个人聚合档案、浏览器扩展及 API；档案包含来源链接。 |
| 值得借鉴 | 将来源平台作为可见的筛选条件：用户可以明确要求“必须有代码证据”，并看见某个人由哪些渠道发现。 |
| 我们需要补齐 | 所读文档没有提供领域化的顶会奖项、欧盟资助、竞赛成员管线，也没有公开可审计的合并决策实现。 |
| 依赖与采用判断 | 商业服务，API 有开通与配额限制，不符合无付费数据库的核心依赖条件。另外 API 来源链接默认可能是代理链接；我们的表格应保存可复核的原始出处。 |

## B. 开源项目、公开代码与数据管线组件

本组区分“直接发现人”“作者消歧组件”和“只完成上游项目／机构整理”。没有把 API 包装器或数据仓库描述成完整的人物发现工具。

### B1. S2AND

| 字段 | 调研结果 |
| --- | --- |
| 名称 | AllenAI S2AND，作者姓名消歧模型、基准与评估工具。 |
| URL | [项目与使用说明](https://github.com/allenai/S2AND)；[原始论文](https://arxiv.org/abs/2103.07534)。 |
| 做什么 | 判断不同论文里的作者署名是否对应同一个人，并提供训练、推理和评估代码。属于核心算法组件。 |
| 数据源 | S2AND 发布的作者消歧基准，以及按规定格式输入的论文和作者署名；使用姓名、机构及论文上下文等信息，具体特征随模型版本变化。 |
| 怎么从信号到人 | 论文中的作者署名记录 → 候选匹配与成对模型 → 聚类，形成同一作者的署名集合。它接受结构化输入，不负责搜索获奖名单或抓取个人网页。 |
| 输出形态 | 署名到作者簇的映射、预测结果、模型及评估结果；不会自动生成带原始网页出处的人物简报。 |
| 值得借鉴 | 将“发现了一条作者署名”与“确认了一个真实人物”分成两个步骤，并用独立消歧测试集评估。 |
| 我们需要补齐 | 要把 OpenAlex／DBLP 等输入转成模型需要的格式，并另做 ORCID、GitHub、公司成员与赛事成员间的身份连接；论文消歧效果不能直接外推到这些渠道。 |
| 依赖与采用判断 | 优先借鉴数据结构与评估方式，未必在首版就部署完整模型。当前 README 对代码、包元数据和数据集列出不同许可说明，复用前需分别核查。 |

### B2. PyAlex

| 字段 | 调研结果 |
| --- | --- |
| 名称 | PyAlex，OpenAlex 的轻量 Python 客户端。 |
| URL | [项目 README 与代码](https://github.com/J535D165/pyalex)；[OpenAlex 作者署名字段](https://help.openalex.org/data/authorships/)。 |
| 做什么 | 对论文、作者、机构等实体进行过滤、查询、分页和字段选择，适合成为 Skill 里的确定性取数脚本。它本身不是人才搜索成品。 |
| 数据源 | OpenAlex API；可通过 OpenAlex ID、DOI、ORCID、ROR 等入口定位相应实体。 |
| 怎么从信号到人 | 按机构或主题取得论文 → 从 `authorships` 取作者 ID 和该篇论文中的机构关系 → 查询作者。该路径可以用库提供的接口实现；身份聚合主要继承 OpenAlex，PyAlex 不另做消歧。 |
| 输出形态 | Python 对象／字典和分页结果，需上层自行生成 JSONL、CSV 或 Markdown。 |
| 值得借鉴 | 确定性 API 查询交给脚本，让 LLM 处理领域理解、缺口判断和非结构化页面，不必由模型手写并维护每一条请求。 |
| 我们需要补齐 | 不会判断获奖与入围、验证当前机构，也不会将作者对应到 GitHub 账户或竞赛队员；结果仍需事实来源与身份匹配记录。 |
| 依赖与采用判断 | README 标示 MIT，适合作为实际候选依赖。OpenAlex 有免费 API 使用额度；认证与配额以[当前服务端文档](https://help.openalex.org/api/)为准，不照抄可能过期的客户端说明。 |

### B3. GitHub Talent MCP

| 字段 | 调研结果 |
| --- | --- |
| 名称 | `carolinacherry/github-talent-mcp`。 |
| URL | [项目仓库](https://github.com/carolinacherry/github-talent-mcp)；[仓库贡献者实现](https://github.com/carolinacherry/github-talent-mcp/blob/main/src/github_talent_mcp/tools/contributors.py)。 |
| 做什么 | 通过 MCP 搜索开发者、读取档案、查仓库贡献者并比较候选人；在“开源项目→人”上与需求直接重合。 |
| 数据源 | GitHub REST API 的用户、仓库、贡献者与公开活动数据；实用调用量通常需要 GitHub Token。 |
| 怎么从信号到人 | 输入仓库 → 调 contributors 接口 → 过滤非 `User` 类型 → 返回账号、贡献次数和主页链接，再取个人资料。也支持按语言、地区等搜索账户。此处已读实际函数，不仅依据宣传描述。 |
| 输出形态 | MCP 的 JSON 结果及 Agent 整理的候选列表／比较表，贡献者结果明确包含 `html_url`。 |
| 值得借鉴 | 用领域代表项目作为入口，先定位实际贡献账户，再补人物资料；比单独搜索“某领域专家”更容易解释发现理由。 |
| 我们需要补齐 | GitHub 账号尚不等于已确认的现实人物；还要与论文、公司及团队信息交叉验证。其关键词／活跃度评分也不能代替实际技术贡献证据。 |
| 依赖与采用判断 | README 标示 Apache 2.0，无付费人才库依赖。但它是需运行服务的 MCP 项目，不是零安装的 SKILL.md 包；可借鉴或抽取公共数据读取逻辑。 |

### B4. Horizon Funding Data Warehouse

| 字段 | 调研结果 |
| --- | --- |
| 名称 | `tavitatavi/horizon-funding-data-warehouse`，CORDIS 本地分析仓库。 |
| URL | [代码与数据模型说明](https://github.com/tavitatavi/horizon-funding-data-warehouse)。 |
| 做什么 | 用 dbt 与 DuckDB 清洗 Horizon Europe 项目和参与机构数据，构建可测试的分析表。**这是相邻组件，没有完成人物发现。** |
| 数据源 | CORDIS `project.csv` 与 `organization.csv`；README 说明所附快照及更新方式。 |
| 怎么从信号到人 | 已实现的路径止于“项目→参与机构及角色”。没有研究者成员表，也没有从机构继续找到人的实现；不能把协调机构名称当成人名输出。 |
| 输出形态 | 本地 DuckDB、项目和机构维表、资金事实表、分析表及 dbt 数据沿袭文档。 |
| 值得借鉴 | 原始数据、清洗、实体和分析分层，并用测试确认真实粒度。其模型保留“机构×项目×角色”，提醒我们别把不同角色压成一条关系。 |
| 我们需要补齐 | 必须新增“项目官网／公开成果→成员名单或作者→个人”的证据链，并与其他渠道做身份归并。 |
| 依赖与采用判断 | 本地免费工具，无付费数据库依赖；代码公开，但此次未完成逐文件许可核查。适合借鉴数据清洗方法，不能作为已经解决 CORDIS→人的案例。 |

## C. 跨渠道“信号聚合→实体→证据”产品

### C1. OpenSanctions 及其实体归并组件

| 字段 | 调研结果 |
| --- | --- |
| 名称 | OpenSanctions；关联组件包括 yente、nomenklatura、FollowTheMoney。按一个产品体系计数。 |
| URL | [标识与去重文档](https://www.opensanctions.org/docs/identifiers/)；[逐条声明的数据模型](https://www.opensanctions.org/docs/statements/)；[归并设计说明](https://www.opensanctions.org/articles/2021-11-11-deduplication/)。 |
| 做什么 | 将不同公共名单和登记来源中的人、机构等记录整合为实体，提供搜索与匹配。此处仅借鉴实体工程和证据结构。 |
| 数据源 | 各类公共名单、登记数据及补充实体来源。每个来源先有独立记录，再进入归并过程。 |
| 怎么从信号到人 | 来源记录 → 统一属性模型 → 匹配候选与归并决定 → 规范实体 ID；保留来源 ID 的对应关系。历史设计公开说明了人工确认机制；不能据此断言其当前所有匹配均为人工。 |
| 输出形态 | 实体页面、API、结构化导出，以及能追踪属性出处和时间的 statement 数据。支持归并、拆分及 ID 变更处理。 |
| 值得借鉴 | **事实声明独立于实体归并保存**。同一个人的名字、机构、成果可以来自不同页面；撤销错误合并时，不必丢掉原始证据。 |
| 我们需要补齐 | 不提供技术领域、论文奖项与竞赛成员的发现适配器；匹配模型的适用输入也不同，不能直接视为科研作者消歧器。 |
| 依赖与采用判断 | 设计与开源组件值得研究；其数据集商业使用需要许可，不能因项目包含开源代码就当作免费数据库依赖。 |

### C2. OCCRP Aleph

| 字段 | 调研结果 |
| --- | --- |
| 名称 | Aleph，跨文档和结构化数据的调查检索平台。 |
| URL | [项目仓库](https://github.com/alephdata/aleph)；[实体概念](https://docs.aleph.occrp.org/users/getting-started/key-terms/)；[表格映射与交叉检索](https://docs.aleph.occrp.org/users/investigations/cross-referencing/)。 |
| 做什么 | 在文档、数据集和人物／公司实体之间检索、关联，组织调查工作空间并绘制关系。 |
| 数据源 | 用户导入的文档和表格，以及其有权限使用的数据集；不是自动拥有全网数据的搜索引擎。 |
| 怎么从信号到人 | 将表格列映射成 Person、Company 等实体属性，选标识字段生成实体，再与其他数据集交叉检索；文档中的提及也可作为找到相关记录的入口。交叉命中仍需核实。 |
| 输出形态 | 命中列表、实体记录、关联文档、关系图与时间线。文档和实体归属于具体数据集或工作空间。 |
| 值得借鉴 | 让人和公司在数据层显式区分，并保留“这个字段是从哪张表、哪份文档来的”。对奖项名单和团队名单尤其有用。 |
| 我们需要补齐 | 需要自己提供科研与赛事抓取器、领域判断和人员确认步骤；完整部署也比一个便携 Skill 重。 |
| 依赖与采用判断 | 可自建的开源平台；参考其实体映射和复核界面即可。OCCRP 实例里有哪些数据可访问，与软件能否自建是两回事。 |

### C3. Diffbot Knowledge Graph

| 字段 | 调研结果 |
| --- | --- |
| 名称 | Diffbot Knowledge Graph，公开网页知识图谱与实体查询服务。 |
| URL | [产品说明](https://www.diffbot.com/products/knowledge-graph)；[实体、来源与时间概念](https://www.diffbot.com/docs/dql/concepts)；[人物对象](https://www.diffbot.com/docs/ontology/person)。 |
| 做什么 | 从公开网页抽取信息并组织为人物、机构等实体，允许按属性和关系查询；接近通用版“多源网页→实体表”。 |
| 数据源 | 对公共网络的抓取与抽取结果，具体查询覆盖取决于其已有图谱。 |
| 怎么从信号到人 | 网页中的人物事实及关系 → 平台的实体解析／合并 → Person 实体及其组织关系。归并的详细模型不是公开可复现实现。 |
| 输出形态 | 图谱查询、API JSON、CSV；文档区分实体 ID、事实来源 Origin、抓取时间和置信度等概念。 |
| 值得借鉴 | 把“来源 URL”“抓取时间”“事实值”一起建模，而不是只给一个看起来完整的人物摘要。 |
| 我们需要补齐 | 所读资料没有给出奖项／竞赛优先的领域发现流程，也不能保证特定欧洲技术圈人物和团队成员被完整覆盖。 |
| 依赖与采用判断 | 商业 API／知识库，只作设计参照；不能把它列为无需付费数据库方案的必选底座。 |

## D. 已发布的 Agent Skills／LLM 工作流

以下五项均核读了仓库中的真实 `SKILL.md`。它们的指令是本次调研对象，不是本次任务实际执行的工作流。没有因技能存在于 GitHub，就假定它能在所有 Agent 平台原样运行。

### D1. Anthropic Account Research

| 字段 | 调研结果 |
| --- | --- |
| 名称 | `anthropics/knowledge-work-plugins` 的 `account-research`。 |
| URL | [SKILL.md 原文](https://github.com/anthropics/knowledge-work-plugins/blob/main/sales/skills/account-research/SKILL.md)；[skills.sh 条目](https://skills.sh/anthropics/knowledge-work-plugins/account-research)。 |
| 做什么 | 输入公司名称／域名，可附联系人，生成公司与人物背景简报，并检查既有 CRM 记录。 |
| 数据源 | 可用的网页搜索、数据补充工具、CRM，以及用户上传或粘贴的资料；原文明确允许缺少连接器时降级。 |
| 怎么从信号到人 | 从已知公司及可选联系人出发，查公开角色、演讲与背景，并整理近期公司事件。它偏向已知对象的资料补全，尚不是从任意技术领域广泛发现人物。 |
| 输出形态 | 公司快照、有日期和出处的事件、可选联系人部分、匹配表和后续建议。要求引用所读数据并区分空字段与未查询。 |
| 值得借鉴 | **降级时明确哪些来源可用、哪些维度未验证**，避免没有连接器仍输出一个貌似完整的档案。 |
| 我们需要补齐 | 新增领域→成果／团队→人物的发现阶段、统一人物 ID 和可导出的逐事实证据表；CRM 查重不能替代跨学术与开源的身份归并。 |
| 依赖与采用判断 | 核心流程不强制付费 CRM／补充数据源；部分交付与连接器指令依赖宿主环境。适合提炼工作流，不能直接承诺全平台无改动运行。 |

### D2. Browserbase Company Research

| 字段 | 调研结果 |
| --- | --- |
| 名称 | `browserbase/skills` 的 `company-research`。 |
| URL | [SKILL.md 原文及脚本入口](https://github.com/browserbase/skills/blob/main/skills/company-research/SKILL.md)；[skills.sh 条目](https://skills.sh/browserbase/skills/company-research)。 |
| 做什么 | 根据用户公司的产品与目标客户条件发现公司，再逐个深查，生成研究文件和名单。是本清单里交付流程最具体的 Skill 之一。 |
| 数据源 | Browserbase Search／Fetch、公司网站、站点地图及外部网页。要求 `browse` CLI 和 `BROWSERBASE_API_KEY`。 |
| 怎么从信号到人 | 当前主实体是公司：搜索发现公司网站 → URL 去重 → 计划、研究、综合。没有完整的公司→具体技术成员步骤，人物发现需要新增第二跳。 |
| 输出形态 | 每家公司一份 Markdown，脚本汇编为 HTML 总览、单家公司页面及 `results.csv`；提供不同研究深度。 |
| 值得借鉴 | **先落结构化的单对象研究文件，再用确定性脚本生成汇总表**；也明确要求无法读取公司产品说明时标为未知，不能凭页面风格猜内容。 |
| 我们需要补齐 | URL 去重升级为人物身份归并；公司主页扩展到论文、奖项、项目和成员名单；每个表格字段需关联事实出处。 |
| 依赖与采用判断 | 技能标示 MIT，但要求特定托管 API 与工具名，还有宿主特定的 Bash／Agent 调度约定。属于“公开技能＋服务依赖”，不能称为完全免费或天然可移植。 |

### D3. Exa Research Orchestrator

| 字段 | 调研结果 |
| --- | --- |
| 名称 | `exa-labs/exa-mcp-server` 中的 `search` Skill，正文名为 Exa Research Orchestrator。 |
| URL | [SKILL.md 原文](https://github.com/exa-labs/exa-mcp-server/blob/main/skills/search/SKILL.md)。 |
| 做什么 | 把复杂调研拆成定义结果字段、搜索、抽取、筛选、归并和综合；覆盖线索发现、人物／公司研究及专家发现。 |
| 数据源 | Exa 搜索和内容接口；原文支持 OAuth、API Key 或受限匿名模式。 |
| 怎么从信号到人 | 原文明示多跳实体发现：第一轮找公司，第二轮找关联人物，第三轮补充公开言论；每轮之间先汇总和去重。这一结构最接近“成果／团队→人→证据”。 |
| 输出形态 | 结构化结果、带链接的表格或引用式报告；大结果可写入 CSV／Markdown 文件。先定义列再搜索。 |
| 值得借鉴 | 将多跳发现写进执行协议，每轮产生明确的中间实体集合，再进入下一轮，避免一条大提示词包办全部任务。 |
| 我们需要补齐 | 当前去重要求多为自然语言指令，没有 ORCID／DBLP／GitHub 的实体归并模型；也未提供年份化的奖项、资助和赛事适配器。 |
| 依赖与采用判断 | 最接近工作流骨架，但绑定 Exa 与特定子任务调度方式。受限匿名访问不等于大规模免费可用；跨平台版本需抽象搜索和任务调度接口。 |

### D4. Composio Lead Research Assistant

| 字段 | 调研结果 |
| --- | --- |
| 名称 | `ComposioHQ/awesome-claude-skills` 的 `lead-research-assistant`。 |
| URL | [SKILL.md 原文](https://github.com/ComposioHQ/awesome-claude-skills/blob/master/lead-research-assistant/SKILL.md)。 |
| 做什么 | 理解产品与目标客户条件，寻找公司并整理匹配理由、决策者角色和后续研究建议。 |
| 数据源 | 可用网页搜索、公司公开资料、新闻、招聘信息和技术线索；示例涉及 GitHub 证据。没有固定的已实现数据连接器集合。 |
| 怎么从信号到人 | 先发现符合业务条件的公司，再寻找相关决策者；输出模板允许只有职位名称，因此不能把每条公司线索都视为已经识别了某个人。 |
| 输出形态 | 分条 Markdown 线索简报；CSV 被列为可选后续动作，技能本身未给出确定性的表格编译脚本。 |
| 值得借鉴 | 用简洁输入约定把任务跑起来，适合作为 Skill 的交互层参考。 |
| 我们需要补齐 | 要有实际连接器、人物确认标准、合并记录及逐事实引用。它虽然要求公司网站和可选档案链接，却没有要求每个判断都绑定来源。 |
| 依赖与采用判断 | 原文不强制某个付费数据库，便于理解和改写；主要是提示词工作流，不能把它当成经过验证的端到端数据管线。 |

### D5. Firecrawl Lead Research

| 字段 | 调研结果 |
| --- | --- |
| 名称 | `firecrawl/firecrawl-workflows` 的 `firecrawl-lead-research`。 |
| URL | [SKILL.md 原文](https://github.com/firecrawl/firecrawl-workflows/blob/main/skills/firecrawl-lead-research/SKILL.md)。 |
| 做什么 | 为已知公司和可选人物制作会前情报简报，包含近期事件、关键人物与讨论背景。 |
| 数据源 | Firecrawl Search／Scrape 读取公司网站、团队页、新闻、公开个人资料、演讲、文章和访谈。 |
| 怎么从信号到人 | 从公司或已知人物出发，独立收集公司资料、近期活动和人物背景，再综合成简报；要求各研究部分返回 URL 和有证据的事实。 |
| 输出形态 | Markdown 简报，含 Key People、Sources 以及可重新运行的输入参数区块。 |
| 值得借鉴 | **把重新运行所需的输入写入交付物**，以后能按同一公司、人物和上下文更新，减少重复解释任务。 |
| 我们需要补齐 | 增加领域级名单发现、人物消歧、跨渠道去重和固定列导出；报告末尾的来源列表还需细化为事实与来源之间的映射。 |
| 依赖与采用判断 | SKILL.md 标示 ISC，明确要求托管请求的 `FIRECRAWL_API_KEY`。不依赖付费人才数据库，但仍有采集服务依赖，不能与零成本混为一谈。 |

## 调研中值得保留的边界

本次没有核实到一个通用、可直接复用的“机器人竞赛队伍→历届成员→个人身份”开源项目。也没有把 CORDIS 项目／机构分析仓库算作已完成“项目→人员”的工具。这两条连接应被当成明确的开发工作，而不是在产品规划里被一个“网页搜索”方框带过。该结论只针对本次找到并检查的对象，不是全网不存在此类实现的断言。

“公开来源”“公开代码”“无付费数据库”“跨平台 Skill”也是四件事：AmazingHiring 和 Diffbot 主要提供产品参照；PyAlex 与 GitHub Talent MCP 更接近可用组件；Browserbase、Exa 和 Firecrawl 的技能公开，但运行依赖各自服务。CSRankings 还提醒我们，仓库公开不等于具有宽松的代码／数据复用许可。

## 从同类产品学到的五条设计教训

1. **发现与补全要分开，而且每一跳都要有产物。** CSRankings 从领域进入，GitHub Talent MCP 从仓库进入，Account Research 则从已知公司进入。我们的领域输入应先产生成果／项目／团队清单，再生成候选人物；只有拿到可验证的人物关联，才进入个人资料补全。输出中保留“找到团队但未确认成员”的线索，不能用猜测补齐名单。这个设计判断来自上述三类入口的差异。

2. **来源记录与真实人物必须分两层，归并应可撤销。** S2AND 的基本输入是论文署名，OpenSanctions 则区分来源 ID 与合并后的实体 ID。我们也应保存 `source_record_id`、内部 `person_id`、外部标识和匹配依据，保留“不确定／不合并”的结果；不能把同 URL 去重、姓名相同和确认同一个人混为一件事。这是对 [S2AND](https://github.com/allenai/S2AND) 与 [OpenSanctions 实体设计](https://www.opensanctions.org/docs/identifiers/)的组合借鉴。

3. **出处要落到事实，而非只在报告末尾列链接。** Firecrawl 的来源区块和 Composio 的公司主页链接足够支撑简报阅读，却不等于逐字段可核验。借鉴 [OpenSanctions statements](https://www.opensanctions.org/docs/statements/)与 [Diffbot Origin](https://www.diffbot.com/docs/dql/concepts)，建议至少保存“人物 ID、事实类型、事实值、来源 URL、来源日期、抓取时间、证据位置”。“某论文获奖”和“某人是该论文作者”应是两条相连的证据，不能由一个含糊的链接包办。

4. **SKILL.md 负责工作约定，脚本负责可重复的数据操作，平台能力由适配层提供。** Browserbase 已展示“单对象研究文件→脚本编译→HTML／CSV”的实际模式；PyAlex 展示了薄 API 客户端的价值。我们的包应将字段检查、ID 保留、分页、导出等确定性步骤放在脚本中，把搜索、抓取和任务调度做成可替换能力。缺少某个服务时明确降级，而不是要求所有平台安装同一商业搜索栈。这是对 [Browserbase Skill](https://github.com/browserbase/skills/blob/main/skills/company-research/SKILL.md)、[PyAlex](https://github.com/J535D165/pyalex)和 [Account Research 降级设计](https://github.com/anthropics/knowledge-work-plugins/blob/main/sales/skills/account-research/SKILL.md)的取舍。

5. **可复查的覆盖记录比“搜了很多”更有价值。** Exa 原文将部分 `sources_reviewed` 计数定义为请求的 `numResults` 之和；这不能证明页面已打开、阅读或提供了有效证据。我们的运行记录应分开统计请求数、实际返回、去重 URL、成功抓取、有效事实、已确认人物及失败原因，并保存领域配置和运行输入。借鉴 [Firecrawl 的重跑参数](https://github.com/firecrawl/firecrawl-workflows/blob/main/skills/firecrawl-lead-research/SKILL.md)，更新时重跑同一范围；借鉴 [S2AND 的评估思路](https://arxiv.org/abs/2103.07534)，另测身份匹配准确性，而不是用名单长度证明质量。
