# CORE-Harness 架构决策记录（ADR）

> 记录关键架构决策、上下文、备选方案与理由。每条 ADR 编号递增，已接受的决策不可悄然推翻（需新 ADR 标记取代）。

---

## ADR-0001：采用"无特权核心"分层插件化架构

- **状态**：Accepted（2026-09-19）
- **上下文**：三源（dsh 插件化基底、ModularRSI 模块化自进化、GA 分层记忆）都强调"能力可替换、核心最小"。
- **决策**：L0 只保留组合基底（注册/可逆效应/coeffect/HMR），loop/记忆/进化引擎/模型适配器均为插件。
- **后果**：
  - ✅ 新增能力（如新模型、新记忆后端）不改核心（指标 M5）。
  - ⚠️ 需要严格定义插件契约（见 `03-interfaces/plugin-registry-interface.md`），否则组合语义模糊。

## ADR-0002：副作用一律建模为"可逆效应"

- **状态**：Accepted
- **上下文**：自进化需要安全回滚；传统框架副作用不可撤销，回滚=推倒重来。
- **决策**：每个写操作必须携带 `undo` 闭包；EffectTracker 维护 undo 栈，支持时间旅行回滚。
- **后果**：
  - ✅ 进化可回滚（M2）、可观测（NFR-OBS）。
  - ⚠️ 部分外部副作用（网络 API、支付）不可完全撤销，用"补偿事务"语义近似，并在 coeffect 标注 `irreversible`。

## ADR-0003：Coeffect 与 Effect 对偶建模

- **状态**：Accepted
- **上下文**：插件既产出副作用（effect），也消费环境约束（权限/宪章/配置）。
- **决策**：插件显式声明 `coeffects`（读入的约束），CoeffectResolver 在调用前解析注入；缺失则拒绝执行。
- **后果**：
  - ✅ 权限/宪章/密钥由环境统一注入，插件内不硬编码，密钥不进日志。
  - ⚠️ 需维护 coeffect 声明规范与默认值策略。

## ADR-0004：记忆与代码为"同一光谱"，采用五层分层记忆

- **状态**：Accepted
- **上下文**：GA 的分层记忆（L0–L4）证明"经验→技能→SOP"沉淀有效；ModularRSI 证明代码可归因进化。
- **决策**：L0元规则/L1索引/L2事实/L3技能/L4归档 五层；L3 技能可"结晶"为插件，插件失败可"溶解"回 L3 记忆。
- **后果**：
  - ✅ 打通"会记"与"会改"，token 有上界（M4）。
  - ⚠️ 结晶判定标准需可量化（复用次数阈值），见 evolution 规格。

## ADR-0005：进化产物"世代化 + 验证门 + 留出评测"

- **状态**：Accepted
- **上下文**：端到端自进化不可归因；ModularRSI 的模块级归因 + GA 的留出评测可缓解。
- **决策**：进化四阶段 诊断→提案→验证→评测；产物不可变、版本化（世代）；必须过 review + 运行时测试 + 留出集不退化方可发布。
- **后果**：
  - ✅ 可归因（M3）、防过拟合（M6）。
  - ⚠️ 需要维护留出集，避免与进化数据泄漏。

## ADR-0006：Python 3.11+ 作为实现语言

- **状态**：Accepted
- **上下文**：源架构源自 Python 技术栈（GA），且 Python 生态对 LLM/MCP/插件化支持成熟。
- **决策**：MVP 用 Python 3.11+；插件契约用 `Protocol`/`dataclass` 表达，跨语言扩展留到 v0.5+。
- **后果**：✅ 上手快、生态全；⚠️ 单进程性能需控制（配合异步）。

## ADR-0007：MCP 作为外部能力接入的标准协议

- **状态**：Accepted
- **上下文**：MCP 已成为 LLM 外部工具事实标准；自研协议维护成本高。
- **决策**：以 MCP client 身份接入外部 server；MCP 工具同样受可逆追踪 + 确认门约束；支持 stdio 与 HTTP 传输。
- **后果**：✅ 兼容庞大 MCP 生态；⚠️ 需处理远端不可逆工具的补偿语义（同 ADR-0002）。

## ADR-0008：记忆后端可插拔，文件后端先行

- **状态**：Accepted
- **上下文**：MVP 需快速落地且单进程可观测。
- **决策**：MemoryStore 定义统一接口；MVP 实现文件后端（Markdown/JSONL），后续可插向量库。
- **后果**：✅ 无外部依赖、可审计；⚠️ 大规模检索性能有限（NFR-PERF2 以 1 万条为验收基准）。

---

## ADR-0009：权限横切 deny-by-default + 人工审批

- **状态**：Accepted（2026-09-19）
- **上下文**：裸模型无约束执行存在失控风险；各工具若各自实现鉴权则语义割裂、难审计。
- **决策**：权限作为横切策略层统一拦截所有副作用动作；操作分只读/数据编辑/高危三级，高危默认拦截（deny-by-default）；高危操作走人工审批流，TTL 超时默认拒绝并审计归档；代码执行默认沙箱隔离，fail-closed。
- **后果**：✅ 单点鉴权、可审计、爆炸半径可控；⚠️ 审批引入延迟，安全优先于效率。

## ADR-0010：Observability 作为进化与审批的单一数据源

- **状态**：Accepted
- **上下文**：进化经验采集、审批审计、可观测各自采集会产生数据分歧、口径不一。
- **决策**：全链路结构化 JSONL（trace_id 贯穿一轮 loop）+ 指标聚合统一供给；evolution 经验采集与 permission 审计都从同一遥测流读取，不另建采集通道；日志脱敏，密钥不落地。
- **后果**：✅ 口径统一、可 replay；⚠️ 遥测体量需异步落盘 + 采样 + 脱敏。

## ADR-0011：Skills 与 Evolution 分工（版本/灰度 vs 结晶/溶解）

- **状态**：Accepted
- **上下文**：进化产物需要发布、路由、回退治理；直接由 evolution 承担会职责过重。
- **决策**：evolution 只负责"结晶/溶解"（产物如何产生）；skills 负责"版本/灰度/A-B/路由"（产物如何治理与调用）；二者以技能库为唯一交接面，结晶产物需评审入库。
- **后果**：✅ 职责清晰、发布可灰度回退；⚠️ 需约定技能库数据模型与交接契约。

## ADR-0012：上下文工程主动治理（信息地图 + 压实 + 预算）

- **状态**：Accepted
- **上下文**：长任务/千页文档极易挤爆上下文窗口，被动堆积不可持续。
- **决策**：Context 采用三管齐下：token 预算裁剪、信息地图（目录索引 + 按需 fetch + hash 失效重建）、多轮对话自动压实并写回记忆；与 MemoryStore 联动而非另起炉灶。
- **后果**：✅ 上下文有上界、按需加载；⚠️ 信息地图失效重建有成本，用增量重建 + 降级检索对冲。

## ADR-0013：CLI 采用 Textual（Python 原生）复刻 Ink 式交互

- **状态**：Accepted（2026-09-19）
- **上下文**：需要 Claude Code 式 Ink 友好终端交互（折叠块/流式/多面板/焦点管理），但 Ink 属 Node/TS 生态；core-agent 后端为 Python（ADR-0006），引入 Ink 需跨语言桥接。
- **决策**：取 Ink 的"声明式 + 响应式"交互哲学，用 Python 原生 Textual（Rich 团队出品）同进程复刻；CLI 走统一后端 API 层，不绕过内核。
- **后果**：✅ 与内核同进程零桥接、单语言栈；⚠️ Textual 生态小于 Web，复杂布局需自绘组件。

## ADR-0014：Web 采用自研单 SPA + 统一 API（不嵌入现成开源产品）

- **状态**：Accepted（2026-09-19）
- **上下文**：调研 Open WebUI/Lobe Chat/LibreChat/Cherry Studio/Dify 均为自带后端/数据模型/认证的完整产品，无"可嵌入框架"。
- **决策**：硬嵌 = 改造 Fork 成本 > 自研；自研单一 SPA + FastAPI 后端统一 API（HTTP + SSE 流式），参考 Open WebUI「Python 后端 + Svelte 前端」同栈经验。
- **后果**：✅ 全栈可控、与内核同栈；⚠️ 会话/流式/设置 UI 均需自研，工作量前置，用 P1→P4 分阶段对冲。

## ADR-0015：桌面端采用 Tauri 壳复用 SPA + sidecar 后端

- **状态**：Accepted（2026-09-19）
- **上下文**：需要桌面可打包安装且与 Web 体验一致；Electron 体积大、内存高，Tauri 体积小且支持 sidecar。
- **决策**：Tauri 壳只做开窗口/挂 SPA/启 sidecar 三件事，复用与 Web 相同的 SPA 构建产物实现 100% 一致，sidecar 拉起 Python 后端，参考 Cherry Studio 桌面包经验。
- **后果**：✅ 体积小、体验与 Web 一致；⚠️ 需 Rust 工具链，sidecar 跨平台打包需 CI 矩阵。

## ADR-0016：MCP Server 暴露面复用 ToolProvider + 白名单

- **状态**：Accepted（2026-09-19）
- **上下文**：0004 新增 MCP server 角色，需把 core-agent 工具对外暴露；若复制工具实现会双份维护，若绕过内核安全等于开后门。
- **决策**：暴露面复用 ToolProvider，经白名单筛选后包装为 MCP tool（命名空间 `core.<tool>`）；外部调用走同一 invoke 链路（permission 确认门 + observability 审计，来源 `external:<client_id>`），不绕过内核。
- **后果**：✅ 单一工具实现源、安全边界外扩一致；⚠️ 需维护白名单与来源标注。

## ADR-0017：MCP Server 传输 stdio 优先 + HTTP/SSE 可选

- **状态**：Accepted（2026-09-19）
- **上下文**：MCP server 需支持本地与远程两种挂载场景。
- **决策**：stdio 为默认（本地零配置、进程内 JSON-RPC，Claude Code 直接 `command` 拉起）；HTTP/SSE 为可选（远程/多客户端，鉴权必选 token/mTLS）。
- **后果**：✅ 本地零配置开箱即用；⚠️ HTTP/SSE 需鉴权，否则等同对外开洞。

---

## ADR-0018：IMGateway 统一协议抽象，新增平台零侵入

- **状态**：Accepted（2026-09-19）
- **上下文**：IM 网关需接入微信/飞书/Telegram/Discord 等多平台，协议差异大；若每个平台单独写一套内核交互逻辑，维护成本随平台数线性增长。
- **决策**：统一 IMGateway 抽象 + IMProvider 适配器；新增平台仅实现 Provider 并注册，内核 loop/工具链/权限/审计链路零改动。
- **后果**：✅ 平台可插拔、内核不污染；⚠️ 统一消息模型需覆盖各平台事件语义。

## ADR-0019：分平台接入方式（官方通道优先，个人号不采用）

- **状态**：Accepted（2026-09-19）
- **上下文**：各平台接入通道能力差异大，且存在合规/封号风险。
- **决策**：Telegram/Discord 用官方 Bot API（webhook/长轮询）；飞书用开放平台长连接 WebSocket（事件订阅）；微信用企业微信/公众号合规通道；个人微信接入因封号风险明确不采用。
- **后果**：✅ 官方通道稳定合规；⚠️ 飞书长连接需心跳保活与断线重连。

## ADR-0020：IM 远程调用复用内核安全链路

- **状态**：Accepted（2026-09-19）
- **上下文**：IM 是远程入口，任何人都可能给机器人发消息，安全边界比本机入口更脆。
- **决策**：身份白名单 + 群 @ 触发 + 高危操作 IM 内二次确认；所有调用走同一 invoke 链路（permission 确认门 + observability 审计，来源 `im:<platform>:<user_id>`），会话按 平台:用户/群 隔离熔断。
- **后果**：✅ 远程控制不降安全等级；⚠️ 需维护白名单与会话隔离策略。

## ADR-0021：LLMProvider 抽象接口归一化，LiteLLM 默认实现可替换

- **状态**：Accepted（2026-09-20）
- **上下文**：内核 loop 需调用三方大模型，各供应商协议差异大；硬编码单一供应商会形成锁定、更换/自研成本高，且错误与审计口径随供应商分裂。三条理由：① **API 波动**——供应商 API 频繁弃用/改参/改返回结构，抽象接口把波动隔离在 Provider 适配层，内核零感知；② **灵活性**——本地模型/自研后端/多供应商混用需自由切换，Registry 依赖注入保证更换零改动；③ **优化自由度**——prompt caching/batching/streaming 等厂商优化须贴近供应商实现，可替换 Provider 允许不改内核做针对性优化。
- **决策**：以 LLMProvider 抽象接口（completion/stream/embedding）为唯一调用契约；LiteLLM 作默认实现（MIT，100+ provider 归一化，任意 API Key + URL 配置即自动路由）；Registry 依赖注入可替换/可自研，调用方零改动；底层原始错误统一归一化为领域异常，不向上泄漏。
- **后果**：✅ 任意三方模型配置即用、可换/可自研、调用方零改动；⚠️ 抽象接口需覆盖流式/向量化等语义，LiteLLM 升级需回归。

## ADR-0022：分布式协议栈采用 A2A + MCP 互补（跨设备 Agent 互调）

- **状态**：Accepted（2026-09-20）
- **上下文**：多设备联合开发需 Agent 间对等协作与工具/资源调用，调研（research_findings.md）确认 A2A 是唯一面向 Agent 对等协作/委派的开放标准（Linux Foundation / Apache-2.0），MCP 负责 Agent↔工具/资源（spec 2026-07-28），二者互补非竞争。
- **决策**：应用层 A2A（Agent↔Agent 委派）+ 能力层 MCP（Agent↔工具/资源）+ mTLS/OAuth 鉴权三层协议栈；A2A Server 内部经 MCP 调用底层工具/数据完成任务。
- **后果**：✅ 跨设备互调标准开放、生态可对接；⚠️ 需同时维护 A2A 与 MCP 两套协议栈的版本兼容。

## ADR-0023：控制面/执行面分离拓扑（云端协调 + 本机执行）

- **状态**：Accepted（2026-09-20）
- **上下文**：云端/PC/移动/嵌入式四类设备能力与信任边界差异大，需明确各自角色与数据/工具归属。
- **决策**：云端为 A2A Server+控制面+relay（只承载协调与进度）；PC 为本地 Agent（文件系统/工具留本机）；移动端为 A2A 瘦客户端（仅发现/委派/订阅/展示）；嵌入式为 MCP Server 能力提供者；控制面与执行面分离。
- **后果**：✅ 敏感数据与工具留本机、云端权限最小化；⚠️ 需处理跨设备会话（contextId/taskId）与本地 context 模块对接。

---

## ADR-0024：Composition 组合与分发层（唯一静态层）

- **状态**：Accepted（2026-09-20）
- **上下文**：架构蓝图 L5「组合与分发层」需把已结晶技能与插件按需组合、跨部署分发、按用户差异覆盖，且该层不应承载业务逻辑。
- **决策**：以 profile（命名组合）/ bundle（分发格式）/ patch.yml（用户覆盖）三要素建模；composition 为唯一静态层——只做组合代数、无业务逻辑、永不进化；解析顺序固定为「bundle 层叠 → patch.yml 覆盖」，同名项由 patch.yml 覆盖，所有组合/覆盖操作可逆、可回退。
- **后果**：✅ 组合逻辑与进化逻辑彻底分离、可逆组合基底不被破坏；⚠️ 需定死 patch.yml 合并语义（浅/深合并、删除标记）与 bundle 版本/依赖/哈希元数据，否则破坏可逆性与跨部署一致性。

## ADR-0025：RAG 检索增强生成（本地向量库语义检索补 LLM 知识缺口）

- **状态**：Accepted（2026-09-20）
- **上下文**：LLM 存在知识缺口（训练截止、私有/领域知识缺失），需引入 RAG 通过本地向量库语义检索知识文档，把最相关片段作为上下文注入生成链路；与 codebase-memory-mcp 正交互补（RAG 管知识文档语义检索，其管代码结构）。
- **决策**：RAG 独立为 capability；向量库选 sqlite-vec（嵌入式零服务，与 SQLite 生态统一）；embedding 用 sentence-transformers + BGE 本地推理，可经 llm-provider 归一化入口切远端；检索片段经 context 装配器按预算裁剪注入生成，检索无结果降级纯 LLM 不阻断。
- **后果**：✅ 本地语义检索补知识缺口、零外部服务、生态统一；⚠️ 本地 embedding 推理有算力开销，向量索引需增量维护与 hash 失效检测。

## ADR-0026：Git 独立为版本控制 capability（编码闭环必要能力）

- **状态**：Accepted（2026-09-20）
- **上下文**：Core-Agent 需完美支持 Coding 编码能力，代码改动需版本化管理（commit/branch/merge/diff/log/status）与远程协作（clone/pull/push），Git 有独立状态机 + .git 保护 + 凭据安全面，故独立为 capability 而非 tool-use 内置工具。
- **决策**：Git 独立为 capability；凭据走 keychain 存取、不落盘明文、日志脱敏；高危操作（force-push/删远程分支/历史改写）接入 permission 审批链；.git 元数据默认拒绝改写，操作失败回滚至操作前状态。
- **后果**：✅ 编码版本化闭环完整、凭据安全、高危操作可审批；⚠️ 需维护 .git 元数据保护与工作区回滚语义。

---

## ADR-0027：统一数据模型收敛（单一索引 + 命名冲突裁决）

- **状态**：Accepted（2026-09-20）
- **上下文**：全量走查发现数据结构定义分散在各接口文档（`03-interfaces/*`）内，无单一索引；且存在 5 处跨层命名/语义冲突（Message / Profile / Trace / Task / Session），以及 2 处被引用但未定义实体（Session、ExecContext）。接口文档是行为契约（spec 的 how），命名收敛不宜塞进 specs（what），故新增 data-model.md 作为架构层索引。
- **决策**：新增 `doc/01-architecture/data-model.md` 作为单一权威索引 + 命名裁决；权威定义仍以各接口 class/字段为准，不重复定义字段；命名冲突以该文 §3 裁决为收敛目标，接口文档改名在编码阶段首个 change 执行。
- **后果**：✅ 消除双源漂移风险、提供跨层实体全景与冲突收敛；⚠️ data-model.md 与接口文档需在后续 change 中保持索引同步。

---

## ADR-0028：Deployment 独立为部署与托管 capability（自托管优先 + 可选云托管 BYOC）

- **状态**：Accepted（2026-09-21）
- **上下文**：架构设计评估发现「托管/部署平台」维度缺失（○纯自托管）；产品需可落地的运行环境与发布能力。它与 Composition（决定「装什么」——bundle 打包分发）和 Distributed（决定「和谁协作」——跨设备拓扑）正交：Deployment 只回答「跑在哪、怎么跑、怎么升级」，三者互不耦合。
- **决策**：Deployment 独立为 capability；自托管优先，云托管为可选 BYOC（bring your own cloud），二者共享同一部署抽象与配置；运行环境用抽象概念（进程级或容器级）描述，不锁定具体选型，兼容 PC/服务器/边缘设备；发布升级版本化（内容哈希）+ 滚动升级 + 失败自动回滚，不处半升级态；暴露健康探活端点与生命周期操作（启动/停止/重启），异常触发告警或自动恢复。
- **后果**：✅ 补齐交付闭环（跑在哪/怎么跑/怎么升级），与 Composition/Distributed 解耦；⚠️ 运行环境抽象不锁选型，需在编码阶段确定具体运行器（进程级/容器级），且升级回滚语义须与 composition bundle 哈希/版本兼容。

---

## ADR-0029：Core.md 两级灵魂文件（人格/宪法/全局规则 + 项目信息）

- **状态**：Accepted（2026-09-21）
- **上下文**：主流 Agent 产品（openclaude 等）均有「灵魂 md」预设以塑造 Agent 人格/宪法/全局规则；Core-Agent 缺此预设。CLAUDE.md（72 行）已占项目记忆语义位、保留给外部 Claude Code，不能复用为 Core-Agent 运行时灵魂文件；且 constitution:v1 coeffect（loop/protocol.py:62）是宪章唯一锚点、无独立文件载体，项目信息也无注入窗口。
- **决策**：新增 core-profile capability，落地两级 Core.md：① `~/.core/Core.md` = 人格/宪法/全局规则，Agent 启动读取，按双语义分区解析——「宪法+全局规则」→ constitution:v1 coeffect 载体、「人格」→ L0 记忆层；② `<project>/Core.md` = 项目信息，ContextEngine 按 cwd 向上查找并注入 context。与 CLAUDE.md 并存分工：CLAUDE.md 归外部 Claude Code，Core.md 归 Core-Agent 自身运行时。
- **后果**：✅ 补齐灵魂 md 预设，宪法获得文件载体、项目信息获得注入窗口；⚠️ 需维护 Core.md 与 CLAUDE.md 的语义边界，避免双源漂移，且两级文件合并优先级（项目级覆盖全局级）需在 spec 中定死。

---

## ADR-0030：编排运行时三能力（并行扇出 + 目标监控 + 优先级调度）

- **状态**：Accepted（2026-09-21）
- **上下文**：对照《Agentic Design Patterns》缺口分析，orchestration 现有三层能力（状态机管理/子任务拆解/多 Agent 协同）缺三个运行时能力：GAP-1 无显式并行执行模型（同波次无依赖子任务仍串行）、GAP-2 无目标监控 spec 定义（ProgressTracker 仅存在于模块文档）、GAP-4 无优先级字段（多子任务就绪无调度依据）。三者语义耦合（优先级决定波次调度顺序、目标监控决定 fan-in 成功判定），宜单 change 统一落地。
- **决策**：扩展 orchestration capability 追加三 Requirement——R5 并行扇出（fan-out/fan-in 波次调度，受资源上限约束）、R6 目标监控（Goal/SuccessCriteria SMART + ProgressTracker 进度追踪）、R7 优先级调度（priority + 就绪队列降序调度）；不新建 capability，改 Purpose 双向（delta 与正式 spec 同步）。
- **后果**：✅ 补齐编排引擎「并行执行、量化验收、优先级调度」三能力；⚠️ 并行执行需确保多子任务并发状态一致（依赖独立状态域/事件溯源），priority 仅在同波次就绪子任务间生效、跨波次仍守拓扑序。

---

## ADR-0031：单进程多会话进程模型

- **状态**：Accepted（2026-09-21）
- **上下文**：ui 现有 R1「三模统一内核启动」下，Web/Desktop 前端以「与后端同机运行」方式接入内核；deployment（ADR-0028）已确立自托管抽象运行环境，但缺少「常驻 Host 承载多客户端」的进程形态。多个客户端需同时接入同一 Core-Agent 实例时，每客户端各自拉起后端会导致资源重复与状态割裂。
- **决策**：采用单进程多会话进程模型——单一 Harness Host 进程常驻承载内核，多客户端并发接入、各自建立独立会话；会话隔离复用 mcp R7「会话与调用隔离」应用层语义 + 0018 R8「会话多流复用」传输层能力；不采用每客户端独立进程，避免资源膨胀。
- **后果**：✅ 资源复用、统一接入端点、会话隔离语义可复用既有设计；⚠️ 进程内会话需确保资源/状态互不串扰，Host 为单点故障面依赖探活恢复，前端独立升级需与 Host API 保持兼容。

---

## ADR-0032：独立持久性能力（Durability Capability）

- **状态**：Accepted（2026-09-25）
- **上下文**：orchestration 的任务级断点续跑、loop 的多轮推理-行动闭环，都使执行态面临"进程崩溃即前功尽弃"的脆弱性；tool-use 已有 EffectId undo 栈（时间旅行），但 checkpoint（检查点快照）、crash recovery（崩溃恢复）、retention（保留策略）散落无统一归口，缺少独立的能力抽象与可寻址快照入口。
- **决策**：新增独立 durability capability（横切层），统一提供 checkpoint 检查点快照、crash recovery 崩溃恢复、time-travel 时间旅行回滚、retention 保留策略；复用 orchestration 断点续跑与 tool-use EffectId undo 栈作为既有挂载点，不重复造轮子。
- **后果**：✅ 执行态可保存/可恢复/可回滚，长时程任务不再前功尽弃；⚠️ 检查点持久化引入存储配额与 I/O 开销，须按保留策略清理，且落盘故障须降级为内存环形缓冲、不阻塞主循环。

---

## ADR-0033：异步接口契约 + 流式编排

- **状态**：Accepted（2026-09-25）
- **上下文**：全库英文 `async` 关键字 0 次、中文「异步」15 处均为描述性措辞（「异步落盘/加载」），无任何异步接口契约；llm-provider 仅 completion/stream/embedding、tool-use 仅 invoke、loop 仅 run，全为同步调用。而真并发（并行扇出执行单元）与流式编排（token 级增量回传）属 I/O 密集场景，同步契约成为并发瓶颈，需一次补齐。
- **决策**：以 async 为主、sync 为薄壳，理由有三：① 并发刚需——LLM/工具调用为 I/O 密集，async 可消除串行阻塞、支撑并行扇出与流式回传；② 向后兼容——sync 接口保留为 `asyncio.run` 独立入口薄壳，既有同步调用方零迁移；③ 命名同构——沿用项目既有 `ainvoke` 的 a 前缀约定，新增 acompletion/astream/aembedding/ainvoke/arun，loop 流式产出 `AsyncIterator[LoopEvent]`（五事件），统一异步执行契约。
- **后果**：✅ 补齐异步接口契约与流式编排，并行扇出与 token 级流式回传具备契约依据；⚠️ sync 薄壳经 `asyncio.run` 无法在既有事件循环内再入（嵌套循环陷阱），并发执行需独立状态域保证一致性，流式迭代器生命周期需显式管理避免泄漏。

---

## ADR-0034：配置管理独立横切能力（Configuration Capability）

- **状态**：Accepted（2026-09-25）
- **上下文**：全库 22 个 specs 无独立 configuration 能力，配置散落各处、无统一收口——LLM 配置（provider/model/endpoint/api_key）是必选项但归属未定，IM 账户/ID/密钥接入信息未统一，功能开关（feature flag）无机制；llm-provider（0006）design.md Open Question 第 2 条「模型配置并入 config.yaml 还是独立 llm.yaml」悬而未决；全库无 schema 校验、无密钥分级，敏感密钥可能误入明文。
- **决策**：新增独立 configuration capability（第 5 横切能力，与 durability 并列），只描述配置语义（源/开关/密钥/校验/生效），不改 llm-provider/im-gateway 的 Requirement 正文、仅以「配置语义挂载点」引用；配置统一收口到单一 config.yaml（env 覆盖 + 默认值兜底，不引入 llm.yaml/im.yaml 等分裂文件）；敏感密钥（LLM api_key、IM secret 等）只在 env/keychain 存储、yaml 中以 `${VAR}` 引用、日志/报错脱敏；features 段提供模块级开关，关闭的模块不加载、不初始化。
- **后果**：✅ 配置获得统一归口、功能可裁剪、密钥安全分级，并关闭 0006 第 2 条 Open Question；⚠️ schema 校验通过才写盘（失败回滚不留半写状态），feature flag 热更新 vs 启动加载、keychain 后端与校验器选型待工程实现收敛。

---

## ADR-0035：技能市场独立 capability（SkillHub Market——多源+签名校验+审核流）

- **状态**：Accepted（2026-09-25）
- **上下文**：skills（ADR-0011）已有本地技能库 SkillLibrary 与版本管理 VersionManager，但技能只能本地编写/安装，无「市场」形态——用户无法从远端下载他人技能，也无法把本地技能发布出去供他人下载；全库 market/skillhub 零命中，属全新 capability。需对接 skills 模块，打通「下载→本地注册」与「本地发布→上架」两条链路。
- **决策**：新增独立 skillhub capability（L3 能力层，与 skills 并列），提供技能市场管理/下载/发布；4 组件——SkillHubClient（远端拉取/上传）、MarketIndex（索引与多源，source 字段预留、默认官方源）、TrustVerifier（技能包签名校验）、SkillPublisher（发布与审核流）。下载经 TrustVerifier 验签后复用 SkillLibrary.register 挂载、且默认 status=draft 不自动启用；发布复用 VersionManager 语义（v1→v2）、走 uploaded→pending→published/rejected 审核流，审核通过才上架。
- **后果**：✅ 技能可下载/发布，多源可扩展，签名校验+审核流保障供应链安全，默认 draft 防恶意自动启用；⚠️ 市场可用性依赖远端服务与网络，签名校验依赖密钥体系选型，审核流引入人工环节（发布延迟），需与 evolution 结晶闭环/灰度发布对齐。

---

## ADR-0036：CI/CD 交付流水线独立 capability（质量门禁 + 制品发布）

- **状态**：Accepted（2026-09-25）
- **上下文**：项目工程化现状为「无 pre-commit / tests 仅 smoke / 无远程 CI」，交付质量无统一闸门；工具链已由 0025-configuration 落地的 development-toolchain（ruff/pyright/pytest/构建）承载，但缺一条把 lint/typecheck/test/build 串成门禁、并在通过后产出可追溯制品的流水线。全库 ci-cd 零命中，属全新 capability。
- **决策**：新增独立 ci-cd capability（工程交付域，不进入运行时 L0–L5 分层、不计入 5 个横切能力），提供两道能力——质量门禁与制品发布；2 组件——CICDPipeline（串起 lint/typecheck/test/build 四道门禁，任一失败即阻断交付并返回失败门禁与原因）、ArtifactPublisher（门禁通过后打包版本化制品并进入发布通道，支持回滚到指定历史版本）。门禁实现引用 development-toolchain（0025-configuration 工具链：ruff/pyright/pytest/构建），不重复造轮子。
- **后果**：✅ 交付质量可门禁化、制品可追溯可回滚，工程闸门闭合「记忆即光谱」闭环的工程侧；⚠️ 门禁质量受 toolchain 覆盖度约束，发布通道初期仅本地/自托管（对齐 deployment 自托管优先），远程制品仓库与凭证属后续扩展。

---

## ADR-0037：统一插件安装抽象（PluginSource + InstallableAsset）

- **状态**：Accepted（2026-09-26）
- **上下文**：架构审计（2026-09-26）维度 A：架构对 skill 有完整安装闭环（skillhub 市场发现→多源路由→签名校验→发布审核），但 mcp/cli 无运行期安装生命周期；plugin-registry 只有进程内生命周期（注册/启停/卸载/依赖/隔离），无「来源（PluginSource）」抽象；skillhub 的「签名校验 / 多源路由」未上提到统一层复用，mcp/cli 无法复用；tool-use 无 install/uninstall 工具，Agent 无法经 AI 对话安装。
- **决策**：在 L0 plugin-registry 建立统一「可安装资产 + 来源」抽象——`InstallableAsset{kind∈skill|mcp|cli}` 只做 registry 层统一（来源发现/校验/安装/生命周期 discover→verify→install→register→activate→deactivate→uninstall），执行实现按 kind 适配不合并；skillhub 现有 4 Requirement 不动，其签名校验/多源路由语义上提到统一层复用；横切 mcp 复用 PluginSource（mcp-endpoint）补 add/remove；L1 tool-use 补 install/uninstall/list 三工具（经 SafetyGate + 审批流）。
- **后果**：✅ 三方插件统一安装闭环，签名校验/多源路由复用，AI 对话安装可行；⚠️ 来源抽象仅覆盖四类来源（后续新来源扩展枚举），签名校验密钥体系依赖选型（与 skillhub TrustVerifier 对齐），market-registry 远端服务与 git 版本锁定待实现收敛。

---

## ADR-0038：CLI 运维命令面独立横切能力（cli-ops + 参数映射 + permission-mode）

- **状态**：Accepted（2026-09-26）
- **上下文**：架构审计（2026-09-26）维度 B/C：core-agent 自身运维 CLI 命令集缺失（仅三模入口 TUI/serve/app）；启动参数与配置参数无一一对应（configuration 只有 yaml+env+默认值，无 CLI 覆盖层）；permission 无 permission-mode 启动开关。
- **决策**：新增横切能力 cli-ops（横切 5→6，不并入 ui），提供运维命令集六组（生命周期/状态/资产/连接/安全/网关）+ 启动参数映射（优先级链 CLI flag > env > config.yaml > 默认值，`--foo.bar=value ↔ config.foo.bar ↔ CORE_AGENT_FOO_BAR`）；configuration 增加 CLI 覆盖层 + ConfigSpec 单一真源（每项声明 cli_flag/env_var/default/map_to，暴露面 core/advanced/hidden 分级）；permission 增加 permission-mode 四档（read-only/interactive/auto-approve/high-risk-block）。
- **后果**：✅ 运维命令集与参数映射一一对应，配置三面由 ConfigSpec 单一真源生成，权限模式可启动开关；⚠️ M4 命令面代码随 Phase 3（需 M1/M2/M3 资产命令就位后收口），进程守护（start/stop/restart/kill）在 MVP 单进程模型下的实现形态待定，auto-approve 仍需对高危走审批不绕过审批流。

---

## ADR-0039：宠物模式（后台自治循环扩展 + 三入口激活）

- **状态**：Accepted（2026-09-26）
- **上下文**：core-agent 已有三模入口（TUI/serve/app）与编排层主循环，但缺一个「低优先级后台自治」面：重复简单任务（信息收集 / 闲逛探索）、主人偏好追踪、定期反馈/惊喜无承载；宿主层三入口（/pet 斜杠、pet CLI、WebUI 自然语言）无统一激活面。全库 pet-mode 零命中，属全新 capability。
- **决策**：新增编排层扩展 capability pet-mode——以 `PetSession` 统一会话生命周期承载后台自治循环（ACTIVE 运行 / SUSPENDED 让行 / RECOVERING 异常退避 / FAULTED 终止），复用 `Loop.run` 同步薄壳逐次执行、复用 orchestration 任务状态机 `SUSPENDED` 作为既有挂载点，不重复造轮子；任务类型限定信息收集 / 闲逛探索 / 偏好追踪三类（PetTaskTypes）；低优先级让行（主循环繁忙时 YIELD 不阻塞主循环）；偏好追踪落 `MemoryEntry.source=user`；三入口（/pet 斜杠命令、`pet <verb>` CLI argv、WebUI 自然语言）经 `UIAPILayer.list_tools/run_loop` 统一激活；定期反馈/惊喜不阻塞主循环。
- **后果**：✅ 重复简单任务后台自治、主人偏好可追踪、三入口统一激活、定期反馈与惊喜闭环；⚠️ 让行粒度受编排层调度约束，惊喜判定依赖偏好积累深度，后台循环与主循环的 LLM 配额共享策略待收敛。

---

## ADR-0040：模块抽象层（MAL——三方依赖边界统一约定）

- **状态**：Accepted（2026-09-27）
- **上下文**：架构审计走查三方依赖边界（2026-09-27）：llm-provider 已用「抽象接口 + 依赖注入隔离」把 LiteLLM 收敛为可替换默认实现（spec 三条 Requirement：抽象接口 / 默认实现 / DI 隔离），im 用 IMGateway+IMProvider 同法；但 rag spec 把 sqlite-vec / sentence-transformers+BGE 写死进 Requirement 本体且接口无装配 seam，mcp 的传输层 Transport 只存在于设计稿、未进接口契约，git 无 git-interface.md、无 GitClient 抽象。三方替换成本不一致，缺一条统一约定。
- **决策**：确立跨模块统一约定「模块抽象层（MAL）」：每个三方依赖边界须满足四条——①抽象接口存在且上层只依赖它（不 import 具体库）；②具体三方库隔离在单一适配器文件（懒 import，类型不泄漏进领域模型）；③DI seam 存在（registry / factory / coeffect 注入，换实现只改装配点）；④spec 说抽象、不说具体，具体库降级为「默认实现」。本次一并补齐三处缺口：rag spec 去具体化 + 补「存储与 Embedding 依赖注入隔离」Requirement、mcp spec/接口补 Transport 抽象、git 补 GitClient 接口与抽象 Requirement。
- **后果**：✅ 更换任意三方模块仅新增适配器、不动架构，替换语义可被「替换 X → 调用方零改动」测试锚点验证（llm-provider 已有 TC-LLM-03、im 已有 TC-IM-01；**rag/mcp/git 锚点据 2026-10-05 补记已登记：TC-RAG-10 / TC-MCP-06 / TC-GIT-11 —— 三条『替换 X → 调用方零改动』测试此前即已存在（`_FixedEmbedder` / `FakeTransport` / `FakeBackend`），本次补的是测试用例追踪号；rag『替换向量库』一侧仍单实现（生产 sqlite-vec 未接 → C 类）**）；⚠️ MAL 是约定而非强制机制，需接口文档与 spec 持续自查；后续新增三方边界（ui 的 FastAPI、im 的平台 SDK、git 的底层库）须按四条落契约。

---

## ADR-0041：神兽召唤模式（beast-mode——前台重大任务，pet-mode 对偶）

- **状态**：Accepted（2026-09-28）
- **上下文**：pet-mode（ADR-0039）只覆盖「后台重复简单任务」（信息收集 / 闲逛探索 / 偏好追踪），缺「前台重大任务」对偶能力：架构设计、性能攻坚、安全审计、测试生成等重大任务需独立子 Agent 前台接管、异步并发执行并自动回归。同时编排层 `handoff` 现状同步执行、仅返回 `trace_id`、`LoopResult` 无成败信号，召唤方拿不到完整结果、无法据失败判定驱动回归。全库 beast-mode 零命中，属全新 capability。
- **决策**：新增编排层扩展 capability beast-mode——① 20 个山海经神兽内置只读注册表（`agent_id=beast.<拼音>`，含称号 / 领域 / 独有神通 / 能力标签，区别于 pet.md 用户自定义）；② 召唤复用编排层既有交接语义：神兽即内置 `AgentProfile`，召唤 = `MultiAgentRouter.handoff(beast_id, TaskHandoff(...))`，不另造第二真源；③ 神兽以独立 `LoopPlugin` 实例运行（独立记忆命名空间 `source=beast.<agent_id>` + 独立上下文装配），运行时能力分两层——L1 工具共享全局 `ToolProvider`、L3 神通（`beast.*` Skill）注册进全局 `SkillLibrary`（loop→skill 运行时调用 deferred）；④ `BeastSession` 四态状态机（DORMANT→MANIFEST→ACTIVE→RECALLED）维护 `dict[agent_id, BeastSession]` 多实例（兽间并行、兽内串行，同兽重复召唤拒绝）；⑤ 召唤异步并发执行（`handoff` 经 `loop.arun` 非阻塞），完成后据 `LoopResult.failed` 判定成败自动回归；⑥ 三入口（/summon 斜杠、`summon <beast> [task]` CLI、WebUI 自然语言）落到同一 `BeastSession` 生命周期。为此小改 loop/orchestration 契约（`LoopResult` 补 `failed`、`handoff` 异步化并返回完整 `LoopResult`）。
- **后果**：✅ 前台重大任务独立子 Agent 异步并发执行 + 自动回归 + 记忆分区隔离（不污染主记忆）+ 三入口同源；⚠️ L3 神通运行时调用（loop→SkillLibrary 桥接）与专属路由 runtime 均 deferred，神兽短期内只拿 L1 工具 + 技能元数据；异步执行下无「中断在岗兽」窗口，手动召回按 beast_id 精确复位（他兽不受影响）。

---

## ADR-0042：决策能力独立横切 capability（judgment——JEV/TypeSafe System One 决策小模型接入）

- **状态**：Accepted（2026-09-29）
- **上下文**：JEV（TypeSafe 官方）是「System One」决策小模型，以 `POST /v1/systemone` 接收 state + 类型化问题（typed questions），返回类型化答案（typed answers）+ probability + confidence，专司快速结构化决策而非文本生成。当前 loop 路由选择、memory 记忆压实、permission 守卫判断三类决策点全部压在通用生成式 LLM 上：既慢又贵，且无结构化置信度可据以回退，决策轨迹亦无法被进化/审批消费。全库 judgment 零命中，属全新 capability。
- **决策**：新增横切 capability judgment——① 决策原语抽象：choice（选项路由）/score（评分筛选）/noul（布尔判断）三类原语作为统一决策入口，供 loop/orchestration/evolution 决策点调用；② JEVProvider 懒加载，经 api_key/base_url/model 建 HTTP 客户端，适配 System One 协议（state + typed questions → typed answers 按原语分形），不新增三方依赖（JEV 为 HTTP API）；③ DecisionRouter（loop 决策点用 choice）、Compactor（记忆压实用 score）、Guardrail（约束守卫用 noul）三处接线；④ 置信度回退：confidence 低于配置阈值回退主 LLM 重新决策，并标注回退轨迹；⑤ 决策审计：每次决策轨迹（输入 state、原语类型、选项、结果、置信度、是否回退）落 observability 链路。
- **后果**：✅ 决策点从生成式 LLM 解耦，获得结构化置信度 + 可回退下限 + 决策轨迹可审计（供进化/审批消费）；⚠️ 决策小模型只适用「选择/评分/布尔判断」结构化决策，开放生成仍走主 LLM；JEV 为外部 HTTP API，需网络可达与密钥配置，无内置兜底（低置信度回退主 LLM 即为质量下限保障）。

---

## ADR-0043：MCP SDK 依赖定位（stdio=stdlib、http=懒 import 可选依赖）

- **状态**：Accepted（2026-10-01）
- **上下文**：Phase 12（MCP 安装/传输/安全接线）因「引入 `mcp` SDK 触及 litellm 唯一运行时三方依赖红线 + 离线不可安装」正式 DEFERRED，重开首步即本 ADR（见 `coding-plan/phase-12.md` §4）。当前运行时依赖仅 `litellm`（唯一运行时三方依赖），`fastapi`/`uvicorn`/`textual` 为接入层边界依赖，`[project.optional-dependencies]` 已有 `dev` 分组。mcp 传输层已具 MAL 四要素（ADR-0040）：`Transport` 抽象（connect/call/ping/close）+ `FakeTransport` 测试替身 + `build_transport` 装配 seam + `mcp-interface.md` 说抽象不说具体；`build_transport` 现为占位抛 `MCP_CONNECT_FAILED`（「生产传输需 MCP SDK」）。**本轮收窄需求**：MCP client（连本地 stdio + 远端 http）+ MCP server（仅本地 stdio）。关键简化——`MCPEndpoint` 已双形态（`transport`/`command`/`args`/`url`/`headers`），`MCPServer` 域逻辑（`initialize`/`list_tools`/`call_tool`）已落地、只差 `serve()` 的 stdio 事件循环，`MCPClient.add` 现硬编码 `transport="http"`；且客户端本地与服务端本地**都是 stdio**、共享同一套 JSON-RPC 帧层 + stdio 传输，只有客户端远端（streamable-http + `Mcp-Session-Id` + SSE 推送）手写成本陡增。MCP 官方 Python SDK（PyPI 包名 `mcp`）是协议参考实现，但携带 pydantic/httpx/sse-starlette/starlette 等较重依赖树。须裁决 `mcp` SDK 按 transport 分流的依赖定位。
- **决策**：**按 transport 分流**——① stdio（客户端本地 + 服务端本地）：**stdlib 手写**（`asyncio` + `json` + `asyncio.create_subprocess_exec`/stdin-stdout），零新依赖，`build_transport` 增 stdio 分支、`MCPServer.serve` 补 stdio 事件循环；② http/streamable-http（客户端远端）：`mcp` SDK 加入 `[project.optional-dependencies]` 新增 `mcp` 分组（`mcp = ["mcp>=1"]`）+ **懒 import**，未装时 `build_transport` 抛 `MCP_CONNECT_FAILED` 并提示「连远程 MCP 需 `pip install core-agent[mcp]`」。**自适应**：`MCPClient.add` 按来源形状分流（`http(s)://` URL → http`url+headers`；本地命令/`command+args` → stdio），`build_transport(endpoint)` 按 `endpoint.transport` 分派。`Transport` 抽象 + `build_transport` seam 不变，SDK 仍只是 http transport 的「默认实现」而非契约。**不采纳**：① 边界依赖（mcp 及其重依赖树强加给全部安装、红线从 1 拉到 2）；② stdio 与 http **全** stdlib 手写（http 的 SSE/会话/分页漂移成本高，不值得）；③ 全交给 SDK（把本可零依赖的 stdio 也拖进重依赖树）。
- **后果**：✅ 默认安装仍 litellm-only（红线字面守住）；✅ 本地 MCP 消费 + 本地 MCP 服务**零新依赖**直接可用；✅ 只有连远程 MCP 才 opt-in 装 `[mcp]`；✅ MAL seam 不变、SDK 可替换。⚠️ own 一段 ~300 行 stdio JSON-RPC 客户端/服务端（`initialize`→`initialized`→`tools/list`/`tools/call`→`ping`），须随 MCP spec 修订；但域逻辑已在 `MCPServer`/`MCPClient`，实为「补传输」而非「写协议」。⚠️ http 远端仍须 `mcp` SDK 在目标环境可安装（硬前置，当前 dev 网络对包解析不可靠，实现时先验证）；⚠️ 装了 `[mcp]` 的部署依赖面扩大（pydantic/httpx/sse-starlette/starlette）。

---

## ADR-0044：零第三方依赖 LLM 层（stdlib OpenAI 兼容 provider 替换 litellm）

- **状态**：Accepted（2026-10-01）
- **上下文**：`litellm` 冷 import 实测 ~8s / 214MB RSS（`entry.py` 曾把预热 import 前移到启动期，仍不可接受），是「唯一运行时三方依赖红线」的实际来源。但审计 `litellm_provider.py` 发现 litellm 从未被当多供应商路由器用：`_map_response`/`_map_chunk`/`aembedding` 已把请求/响应钉死为 OpenAI chat/completions + embeddings 形状，`_build_kwargs` 仅透传 `model/messages/temperature/max_tokens/tools/api_key/api_base` 到单一 endpoint（`config.yaml` 的 `endpoint` 含 `/v1`）。即 litellm 实际只贡献 ① 异步 HTTP（内部 httpx）② SSE 流解析 ③ 异常归一化 三件可 stdlib 替换的小事；降级模型循环、指数退避重试、超时、审计钩子全在 `LiteLLMProvider` 自身，与 litellm 无关。对照样本 GenericAgent（`llmcore.py` 62KB）手写双协议 + 端点路由 + cache_control，代价远大于本场景所需。
- **决策**：**手写 stdlib OpenAI 兼容 provider 替换并删除 litellm**——新增 `StdlibLLMProvider`（`urllib.request` 直连 OpenAI 兼容端点 + `asyncio.to_thread`/`run_in_executor` 桥接 + 手写 SSE 解析 + `map_http_error` 按 HTTP 状态码归一），`registry`/`runtime` 默认实现改指新类，`entry.py` 删预热 import，`pyproject.toml` 删 `litellm` 依赖。**不采纳**：① 可选保留 litellm 作懒 import 后备（当前本就只用 OpenAI 兼容单一 endpoint，无多协议需求，保留是投机）；② 引入 httpx/requests 轻量 HTTP 库替换（红线从「1 个三方依赖」变「换一个三方依赖」，未消除依赖面）。
- **后果**：✅ 核心运行时**零第三方依赖**（红线从「litellm 唯一运行时三方依赖」升级为「核心零三方依赖 + 接入层边界依赖 fastapi/uvicorn/textual」），冷启动 8s→<0.5s；✅ 复用既有 `LLMProvider` 抽象 + `registry` + DI seam（ADR-0040），调用方零改动；⚠️ 失去 litellm 的多供应商协议路由能力（但当前本就钉死 OpenAI 兼容单一 endpoint，非回归）；⚠️ own 一段 ~150 行 OpenAI 兼容 HTTP/SSE + 状态码映射，须随 OpenAI 兼容端点行为修订。

---

## ADR-0045：记忆检索语义化（embedder 接入契约 + 向量缓存策略）

- **状态**：Accepted（2026-10-04；change `0039-memory-multifactor-recall`（seam，已归档）与 `0040-memory-embedding-config`（来源，已归档）均已落地，593→597 tests 绿）
- **上下文**：遗留项 C7（Phase 17.5 §3.1 走查）。`build_runtime` 构造 `MemoryStore` 时
  **未传 `embedder`**（`runtime.py:167-171`）→ 运行时恒走 `relevance._lexical_sim`
  （`relevance.py:73-77`），「语义检索」名存实亡。直接接入有三处障碍：① **契约不匹配**
  ——`MemoryStore.embedder` 是**批量可调用** `(list[str]) -> list[list[float]]`
  （`store.py:38`、`relevance.py:49`），而 rag `Embedder.embed(text) -> list[float]`
  （`rag/embedder.py:32`）是**单条**；② **成本**——`relevance._similarity` 对**每个候选**
  调 `embedder([entry.content, query])`（`relevance.py:66`）→ 每次 `read` **N+1 次
  embedding**，且 query 被逐候选重复向量化；③ **来源**——`StdlibLLMProvider.aembedding`
  复用同一 provider 的模型名打 `/embeddings`（`stdlib_provider.py:168-176`），聊天模型通常
  不支持 embedding，须**独立 embedding 模型**配置。另：本地语义模型
  （sentence-transformers+BGE）与「核心零三方依赖」红线（ADR-0044）冲突，不引入。
- **决策**：
  ① **适配器归 memory 层**：新增 `memory/embedding.py::batch_embed(single: Callable[[str],
  list[float]]) -> Callable[[list[str]], list[list[float]]]`，把单条可调用适配为批量契约；
  memory **不 import rag**（L2 不依赖 rag 抽象），runtime 装配时传入一个单条可调用
  （如 `rag.Embedder.embed` 或 `LLMEmbedder.embed`）。
  ② **向量缓存放 `MemoryStore`**：`read` 时 query **只向量化一次**；候选条目向量按
  `(entry.id, hash(content))` 缓存于 `self._vectors`，`content` 未变即复用；缓存为**进程内
  易失**（重启重建，不落盘、不改后端 schema）。
  ③ **embedder 来源经 llm-provider（远端），不引入本地语义模型**：新增可选配置
  `llm.embedding_model`（复用 `llm.endpoint` 与密钥引用）；设置时 runtime 以该 model 构造
  独立 provider → `LLMEmbedder` → `batch_embed` → `MemoryStore(embedder=...)`；未设置或
  不可达 → `embedder=None` → 词法降级（`relevance` 已内建 try/except 降级，
  `relevance.py:64-70`）。**投递拆分**：①②（seam/缓存/重排）在 `0039`（memory 能力内、
  离线可验）；③（配置旋钮 + 组合根装配）在 `0040`——memory 不感知 `embedding_model`
  （ADR-0040 MAL：memory 说抽象不说具体）。
  ④ **密钥只引用不读取**：embedding 复用 `llm.api_key_ref`，密钥经 `resolve_secret` 注入并
  登记脱敏，不进日志/记忆（沿用项目密钥红线）。
- **后果**：✅ 语义相似经远端 embedding 生效，且每 `read` 至多 1 次 query 向量化 + 未变条目
  零重算（N+1 → 1 + 增量 miss）；契约不匹配以适配器一次性收敛；memory↛rag 依赖方向保持。
  ✅ 默认安装仍是词法（`embedder=None`），零新依赖、离线可测（测试注入 fake embedder）；
  embedding 仅在显式配置 `llm.embedding_model` 时启用。⚠️ embedding 走远端 API → 需网络
  可达与额度，不可达时静默降级词法（排障须看日志）；⚠️ 向量缓存易失，重启后首次 `read` 有
  冷 miss，`content` 变更以 hash 失效；⚠️ `importance` 的**打分来源**不在本 ADR 范围
  （属 change 0039 的 ranking 设计，先由调用方写入、后续可接 judgment `score` 原语）。
- **不采纳**：① 本地 sentence-transformers/BGE（与零三方依赖红线冲突，语料亦不足）；
  ② 在 `relevance` 内逐候选调用 embedder（保留 N+1，成本不可接受）；③ 向量持久化落盘
  （引入 schema/迁移成本，收益有限，先用易失缓存）。

---

## ADR-0046：记忆摘要式压实（摘要接缝 DI + 会话分组归档 + 触发接线）

- **状态**：Accepted（2026-10-04；change `0041-memory-summary-compaction` 落地，597→608 tests 绿）
- **上下文**：Phase 18 #3（摘要式压缩）。走查发现两条**生产死路径**：① `context.Compactor`
  在 `build_runtime` 中**无任何构造点**（`runtime.py` 只构造了 judgment 的 `Compactor`）→
  `persist` 从未在生产执行；② `MemoryStore.compact` **无生产调用方**（`ui/api.py:119` 的
  `compact(session_id)` 是空实现 no-op）→ 压实链路整体不可达。另有两处规格/实现缺口：
  `migrate` **不记 `EffectTracker`**（迁出即不可逆，违反开发约定 #3「一切副作用可逆」）；
  `context.Compactor.persist` 写回的是**匿名 episodic 条目**（`source="context"`、
  `trace_id="compaction"` 固定），沉淀物无法追溯到原文。规格侧 memory spec「记忆压实」只要求
  「合并重复条目、归档过期会话、保持 L1 索引最小」，无 LLM 提炼语义。
- **决策**：
  ① **摘要接缝走 DI 可调用，不扩 judgment 原语**：`Summarizer = Callable[[list[MemoryEntry]], str]`
  定义在 memory 域（`memory/summarize.py`，含 `build_prompt`），模型调用经 `summarize_with(llm)`
  适配——照 `batch_embed` 先例（ADR-0045 同一依赖方向），memory **不 import LLM 抽象**，
  组合根注入；judgment 的 choice/score/noul 是**决策**底座，摘要是**生成**，加原语会波及既有
  决策点，blast radius 不成比例。`Compactor.score` 保留为「哪几条值得提炼」的选择步骤。
  ② **按 `session_id` 分组，不跨会话聚类**：确定性、离线可断言、无需 embedder；空会话归 `""` 组。
  ③ **原条目 `migrate` 到 L4 而非删除**（L4 是归档层，audit 可见），并**一并修 `migrate` 记
  Effect**（迁回原层）补上不可逆缺口。
  ④ **压实效应共用一个按会话确定的 trace**：`f"compaction.{session_id}"`（空会话 `default`），
  摘要写入 + 全部迁移登记其下 → `rollback(trace_id)` 按逆序整体逆转（摘要移除 + 原条目迁回）；
  `compact` **签名与返回值不变**（phase-18 §6 要求），撤销句柄由摘要条目的 trace/tags 暴露。
  ⑤ **出处放 `tags`（`from:<id>`），不放 `source`**：`source` 会被 `context/assembler.py` 原样
  作为出处标签放进 facts 交给模型，塞 id 列表会污染 prompt 并白烧 token；故 `source="compaction"`
  短标签 + `tags` 承载机器可读出处。
  ⑥ **context 压实定为启发式降级路径**（关键词识别），只收口产物形态（`kind="semantic"` +
  出处），**不新增第二个 LLM 调用点**；LLM 提炼统一归 memory 的摘要通道（上游沉淀 → 下游提炼，
  单向）。
  ⑦ **触发点接在 loop**（`DefaultLoop` 注入 `compactor`）：每轮 `observe` 后按既有
  `should_compact(rounds, token_used, budget)` 判定，命中则 `persist`（历史 → L2）→
  `memory.compact`（会话摘要归档）；**终止语义不变**（压实后仍按既有 `TOKEN_BUDGET_EXCEEDED`/
  轮数条件终止，不改成「压实后继续」，否则循环无界，反倒违背同一 Requirement 的「不无限烧
  token」）。`loop/spec.md` **不改**——既有「错误与预算控制」Scenario 本就要求此举，本变更让
  实现追上规格。压实失败**降级不中断本轮**：`ContextError`（无可沉淀关键信息）静默跳过，其余
  异常经 tracer 记 `compaction_failed` 留痕（memory 层不吞异常、不写半成品，原记忆保持不变）。
- **后果**：✅ 两条死路径接通（context 压实 + 记忆压实生产可达）；✅ 压实全链可逆（含新补的
  `migrate` 效应），`rollback("compaction.<session>")` 一键撤销；✅ 沉淀物可追溯（semantic +
  `from:<id>` 出处），归档原文仍以 L4 低优先级可检索；✅ 未注入摘要器/未注入压实器时行为**完全
  不变**（默认零 LLM 调用，离线可测）。⚠️ 生产侧 `session_id` 目前仍为空串（loop 不向记忆传会话
  标识）→ 压实实际按单一 `""` 组聚合；会话维度真正生效需把 `session_id` 从 UI 会话透传到
  `remember`（另立变更）。⚠️ 已知缺口（先于本变更存在，未扩大范围）：memory spec 的
  「并发压实一致性」Scenario 仍无对应实现——仓库是单线程事件循环、无并发压实调用方，加锁属
  投机性代码；`Compactor.compact` 的启发式关键词判定亦未升级为 LLM 判定（留 #4）。
- **不采纳**：① 扩 judgment 原语承载摘要（职责错位 + 波及 loop/permission 决策点）；
  ② 跨会话语义聚类（需 embedder 在线且质量难离线断言）；③ 压实即删除原条目（不可审计、不可
  回滚）；④ 为并发场景预先加锁（无并发调用方的投机代码，CLAUDE.md §2）。

---

## ADR-0047：记忆固化与遗忘（价值门控并入摘要通道 + 逐条目打分上界 + 遗忘只迁层）

- **状态**：Accepted（2026-10-04；change `0042-memory-consolidation-forgetting` 落地，
  608→616 tests 绿）
- **上下文**：Phase 18 #4/#5。0039 已给 `MemoryEntry` 加 `importance` 字段、0041 已打通
  「会话摘要 → semantic + L4 归档」，但三处仍是空的：① `importance` **全仓无写入点**（默认 0），
  多因子重排里的 `(1 + importance)` 恒为 1，主观重要度维度形同虚设；② 0041 的摘要对**所有**
  会话无差别提炼（低价值轨迹也产出 semantic 条目，稀释记忆质量）；③ **没有任何遗忘**——陈旧
  零复用的 episodic 条目永久占据 L2 并参与每次检索。规格侧 memory spec 无「固化」「遗忘」两条
  Requirement。
- **决策**：
  ① **固化并入 `compact` 的摘要通道，不新增 `consolidate()` 方法**：0041 的「会话分组 → 提炼 →
  归档」通道已就位，固化的增量是**价值判断**（门控），不是第二条通道；两条近同构链路并存会让
  「哪个入口负责提炼」失去唯一答案。
  ② **门控判据 = 会话内本轮取得分值的最高分 < `_CONSOLIDATE_THRESHOLD = 0.5`**；**本轮一个分值
  都没取得**（未注入 scorer / 打分失败 / 超出上界）时**不设门槛**——把「没配 judgment」或
  「决策服务抖动」变成「记忆停止固化」是新的死路径，与 0041 「缺省时降级而非停摆」同一取向。
  ③ **`importance` 打分走 judgment `score` 原语，逐条目一次调用**：`score` 原语的返回值是
  **条目集的单一分数**（`answers["score"]["score"]`，见 `judgment/models.py` 与
  `tests/test_judgment.py::test_score_returns_scores`），无 per-item 分数；故每条目一次调用，
  以 `_MAX_SCORED_PER_COMPACT = 20` 按本地多因子序取前 N 设上界，控制单次压实的模型调用数。
  **不**采纳「按会话打一个分整组套用」（同组 importance 成常数 → 该维度在排序中退化），**不**
  采纳「扩 score 原语为逐条返回」（judgment 规格变更，blast radius 覆盖 JEV prompt、router 解析
  与既有决策点）。
  ④ **打分写回是可逆写入**：逐条记 `Effect(op="memory.importance", undo=恢复旧值)`，trace 与压实
  同批（`compaction.<session_id>`）→ `rollback` 该轮同时撤销分值写回（开发约定 #3）。
  **打分失败 ≠ 打 0 分**：抛错/无分值即跳过，`importance` 保持原值——否则一次 LLM 抖动会清空全库
  重要度、连带触发误遗忘。
  ⑤ **`compact` 里既有的压实决策打分改为失败降级为 `decision=None`**：该调用是 0039/0041 遗留的
  咨询性返回值、无写入副作用（`compact` 的返回值仅作决策留痕），其失败没有理由连带阻断固化与
  遗忘。**摘要提炼失败仍按 0041 契约向上传播**（memory 层不吞、不写半成品），由触发点记
  `maintenance_failed`。此处对 ADR-0046「memory 层不吞异常」的收窄**只限无副作用的决策调用**，
  不触及有写入副作用的提炼阶段。
  ⑥ **遗忘 = 低分条目 `migrate` 到 L4，不删除**：新增 `MemoryStore.forget(*, threshold) ->
  list[MemoryId]`，候选**只限 L2 episodic**（semantic 是提炼产物、L0 是人格、L3 是技能，均不参与
  衰减）；每条例 `trace_id=f"forgetting.<entry_id>"` → 按 trace 回滚即迁回 L2。评分
  `recency_decay × (1 + log1p(reuse_count)) × (1 + importance)`。**偏离 phase-18 原文**：计划写的是
  `recency × (1 + log reuse) × importance`——直接乘 `importance` 会让**所有未打分条目**（默认 0）
  评分恒为 0，首次遗忘即把全库 L2 episodic 归档；改为 `(1 + importance)`（与 `rank` 的乘性项
  同构），缺省时遗忘只由「陈旧 + 零复用」决定。`_FORGET_THRESHOLD = 0.05` ≈ 19 天零复用零重要度；
  `ts<=0`（时间未知）时 `recency_decay` 返回 1.0，不惩罚。
  ⑦ **触发并入 loop 既有压实触发**（`persist → compact → forget`）：不新增触发面、不改终止语义；
  三步各自 try/except 降级（`ContextError` 静默跳过，其余记 `maintenance_failed`），固化/遗忘失败
  不中断本轮、原记忆不丢。
- **后果**：✅ `importance` 首次有了自动写入点（可逆），多因子重排的主观维度真正生效；✅ 低价值
  会话不再污染 semantic 层；✅ 记忆首次具备衰减归档能力，且**永不物理删除**（可 audit、可回滚）；
  ✅ 未注入 scorer/summarizer 时行为与 0041 完全一致（离线可测）。⚠️ 模型调用成本随候选条目数线性
  增长 → 以 `_MAX_SCORED_PER_COMPACT = 20` 设上界，**超界条目本轮不打分、也不参与门控**（门控
  只依据本轮分值，超界与失败同处理——宁可少提炼不误拦）。⚠️ 打分质量依赖 JEV/主 LLM 回退链，
  质量不可离线断言。⚠️ 已知缺口（不扩大范围）：`forget` **无调度器**（只在 loop 压实触发时顺带
  执行，「定时衰减循环」需调度依赖，另立变更）；`session_id` 生产侧仍为空串（同 0041，固化仍按
  单一 `""` 组聚合）；无并发锁（单线程事件循环假设）。
- **不采纳**：① 独立 `Consolidator` 类（与摘要通道职责重叠）；② 按会话批量打分（importance 退化
  为常数）；③ 改 judgment 原语为逐条返回（规格变更 blast radius 不抵）；④ 遗忘即物理删除
  （不可审计、不可回滚、违背「记忆即光谱」）；⑤ 直接乘 `importance` 的衰减式（未打分条目恒 0 →
  首次遗忘清空 L2）；⑥ 打分失败写 0（抖动即清空全库重要度并误遗忘）。

## ADR-0048：SOP 提炼（生成走 DI 接缝 + loop 只持回调 + 词法归组 + active 自动发布）

- **状态**：Accepted（2026-10-04；change `0043-sop-skill-extraction` 落地，616→626 tests 绿）
- **上下文**：Phase 18 #6（维度1 技能库全自动进化的第一环）。走查确认技能只有「注册 / 路由 /
  版本」三段，**没有任何产生技能的入口**——`SkillLibrary` 在生产恒为空，`SkillRouter.match`
  永远落空并把任务记为 miss（M3 遗留：miss 只沉淀、不复用）。skills spec 亦无对应 Requirement。
  没有提炼，phase-18 定位的「下次类似任务直接参考 skill 省 token」就没有来源。
- **决策**：
  ① **提炼是「生成」，走 DI 接缝而非 judgment 原语**：`SopWriter = Callable[[str], str]`（prompt →
  SOP 文本）定义在 skills 域（`skills/sop.py`：`build_sop_prompt` + `sop_writer_with`），模型调用由 L5
  组合根注入——与 0041 的 `memory/summarize.py` 同一依赖方向，skills **不 import 任何 LLM/rag 抽象**。
  **偏离 phase-18 原文**：计划写「LLM 提炼走 judgment（JEV 提炼不足则 fallback LLM）」，但 judgment
  只有 choice / score / noul 三种**决策**原语、**没有生成原语**——把「写一段 SOP」塞进 `score` 原语是
  职责错位。故生成统一走 DI 接缝，judgment 在技能链路上的角色留在 #7 语义路由打分。同理，**不**
  把 `SopWriter` 放在 judgment 域（生成能力不属于决策横切能力）。
  ② **loop 侧只持一个普通回调，不 import skills**：`test_architecture` 明令 `loop` 不得 import
  `skills`/`skillhub`。故收尾钩子是 `SopObserver = Callable[[str, list[str]], object]`（任务文本 +
  行动/结果序列），由 `build_runtime` 注入 `SopExtractor.observe`——与既有
  `skill_router=lambda task: [...]` 同法。**只有成功任务触发**（`ok=False` 即超限终止轮不提交：
  失败轨迹不是 SOP，其教训沉淀已有 memory/evolution 通道），故接缝**不需要 ok 参数**。钩子缺失时
  loop 行为完全不变；钩子抛错经 tracer 记 `sop_extract_failed` 降级，**不改变本轮结果与终止语义**。
  ③ **归组先复用已有 `task_types`，否则用任务词元签名**：`terms_of(task)`（与 `SkillRouter` 同一
  口径，由 `_terms` 提为公共名）与每种已有技能的每个 `task_type` 求交，命中即复用该 `task_type`
  作组键（使后续提炼落到同一技能，是 #8 迭代闭环的增量来源）；未命中则 `" ".join(sorted(terms))`
  作新组键。**词法归组是有意的下限**：同义不同词的任务各自成组（宁可分叉、不误并），语义归并归 #7。
  ④ **阈值 3 条成功轨迹；产物 `status="active"`（维度1 低风险自动发布）**：同类任务累计
  `_SOP_MIN_SAMPLES = 3` 条才提炼一次，**提炼后清空该组**（下批重新累积，避免每任务一调）。
  `skill_id` 由组键 blake2b 摘要派生（确定性 + 同组重复提炼覆盖同一条，不增长）。置 `active` 而非
  `draft`：维度1（技能库层、不动架构代码）本就是全自动无人值守，而 `draft` 对 `SkillRouter.match`
  （只认 active/gray）**不可见** → 置 draft 等于造一条死路径。提炼文本为空则**不入库**（不写半成品）。
  ⑤ **入库可逆**：登记 `Effect(op="skills.register", undo=移除技能)`（`trace_id="skills.extract"`），
  undo 幂等且**只在库中仍是本次产物时才移除**（已被后续提炼覆盖则不动）。未注入 tracker 时不记
  （缺省降级）。开发约定 #3「一切副作用可逆」在技能库层首次落实。
  ⑥ **不引入多版本维度**：`SkillLibrary.register` 仍按 `skill_id` 覆盖（单版本注册表），提炼只产出
  「当前版」；version 升级与 A/B 定夺是 #8 的交付物（`VersionManager` 当时存在但未接 runtime；✅ 已由 change 0045 闭合——`src/core/skills/iteration.py` 的 `SkillIterator` 即其生产调用方，见 `coding-plan/phase-19.md` G 类）。
  不预先造多版本结构（不做投机抽象）。
- **后果**：✅ 技能库首次有了产出入口，「经验 → 技能」方向在生产接通（此前只有注册/路由/版本三段）；
  ✅ 未注入 writer 时不累积、不提炼（零额外模型调用），未注入钩子时 loop 行为完全不变（离线可测）；
  ✅ 产物可被 `SkillRouter` 命中，且入库可逆。⚠️ **误提炼风险**（低质量 SOP 自动 active）：只吸收
  成功轨迹 + 同类 ≥3 次 + 空文本不入库 + 可逆回滚兜底；**质量门留待 #8**（现在加一个无消费者的
  门槛属投机代码）。⚠️ 词法归组漏并（同义不同词不并组）。⚠️ LLM 调用成本为「每组达阈值一次」而非
  每任务一次。⚠️ 已知缺口（不扩大范围）：技能库无持久化（进程内注册表，重启即失——先于本变更
  存在）；样本仅进程内累积（不落盘，避免无界写放大）；`register` 对同 id 重复注册会重复追加
  `_domain_index`（既有行为，不影响 `all_skills`/`remove` 正确性）。
- **不采纳**：① 把生成塞进 judgment `score` 原语（职责错位、无生成语义）；② 在 judgment 域新增
  生成原语（横切能力越界，blast radius 覆盖 JEV prompt 与 router 解析）；③ loop 直接 import
  skills 调 `SopExtractor`（违背架构红线）；④ 失败轨迹一并吸收（失败不是 SOP，会污染技能库）；
  ⑤ 产物置 `draft` 等人工放行（对路由不可见 → 死路径，且维度1 本就是全自动）；⑥ 未达阈值即提炼 /
  每任务一调（成本与噪声不可控）；⑦ 本次就引入多版本与 A/B（#8 的范围，投机抽象）。

## ADR-0049：语义路由（词法 fast path + judgment 逐候选打分 + 阈值门 + B4 删字段）

- **状态**：Accepted（2026-10-04；change `0044-semantic-skill-routing` 落地，626→637 tests 绿）
- **上下文**：Phase 18 #7（维度1 第二环）。走查确认 `SkillRouter._score` 只做字符包含匹配
  （任务词元 ∩ `skill_id`/`description`/`task_types`），**同义不同词永不命中**；未命中即
  `_record_miss` 记一条 L2——而 miss 只沉淀、不复用（M3 遗留）。#6 之后技能库开始有真实产出，
  但提炼出的 SOP 只要措辞与后续任务用词不同就**永远取不到**，"省 token" 的收益被词法口径吃掉。
  同时确认 B4：`ContextPack.skills` **无生产者、无消费者**（技能实际经 planner 的 `skill_router`
  回调进 prompt），唯一引用是 `BudgetManager` 的裁剪/计量。
- **决策**：
  ① **语义只在词法全无命中时兜底（词法是 fast path）**：`match` 先算词法分，有命中即返回，
  **零模型调用、零行为变化**；`scored or self._semantic(...)`——语义只补在「今天会记 miss 后丢弃」
  的那条死路上。**不采纳**「每次都用语义打分并与词法融合」：`match` 在每个推理轮都会被
  `planner._skill_hints` 调一次，每轮 K 次 judgment 调用会把辅助决策成本抬到主路径上。
  ② **打分走 judgment `score` 原语、逐候选一次调用，adapter 落在 judgment 域**：
  `score` 原语的返回值是「条目集单一分数」（无 per-item 分数，同 ADR-0047 决策 ③）→ K 个候选 =
  K 次 `decide()`。新增 `judgment/skills.py::SkillMatcher`（照 `judgment/compactor.py` 先例）：
  skills 域的 seam 只声明 `SkillScorer = Callable[[str, list[dict]], dict[str, float]]`，
  **不 import judgment**；judgment 侧只吃 dict、**不 import skills**——两侧都不知道对方的类型
  （与 0043 的 `SopWriter` 同一依赖方向，ADR-0040 MAL）。**不**在 judgment 域新增生成原语、
  **不**把打分循环放进 `SkillRouter`（那会让 skills 依赖 judgment 的请求形状）、**不**改 `score`
  原语为逐条返回（judgment 规格变更，blast radius 覆盖 JEV prompt 与 router 解析）。
  ③ **阈值 `_SEMANTIC_MIN_SCORE = 0.5`（构造参数可调）**：低于阈值不采纳，否则任何任务都能挂上
  某条技能、技能块被灌水进 prompt（白烧 token）。JEV 不可达回退主 LLM 时 `_fallback_answer` 给
  SCORE 的分恒为 `0.0` → 恒低于阈值 → **语义路径自然退化**，不需要额外开关。候选只含
  `active`/`gray`（`draft`/`deprecated` 不打分）。
  ④ **逐候选失败即跳过；`match` 不向调用方抛异常**：`SkillMatcher._score_one` 内 `except Exception`
  返回 `0.0`（坏答案/调用失败/回退一律不成候选），`SkillRouter._semantic` 再裹一层防御打分器整体
  抛错——`match` 由 `planner._system_prompt` **直接调用（无异常包裹）**，抛出会打断本轮推理；
  打分是无副作用的咨询性查询，降级为「该候选无分」是正确的失败面（同 0042 逐条目打分取向）。
  ⑤ **语义命中即命中，不再记 miss**：miss 的用途是「无技能可用 → 记录供新技能沉淀」；语义已把任务
  与已有技能接上时记 miss 是假信号（同时污染 M3 的沉淀入口）。有命中（词法或语义）则不记。
  ⑥ **B4 收口 = 删除 `ContextPack.skills` 字段**（用户 2026-10-04 定夺）：该字段无生产者、无消费者，
  唯一引用是 `BudgetManager` 的裁剪/计量与 `context-interface.md` 的声明。**不采纳**「装配器填充、
  planner 读 pack」：技能将与事实争同一预算（`enforce` 先裁 facts、skills 只吃**剩余**），记忆
  丰富时技能会被挤出 prompt——今天是**恒注入**，属功能退化。规格侧无对应 Requirement（context
  spec 从未提及 skills）→ **删除是规格中性**的；`ContextPack` 构造方均未传该字段，对生产零影响。
- **后果**：✅ 词法 fast path 逐字节不变（未注入打分器时行为与今天完全一致，离线可验证）；
  ✅ 同义不同词的任务首次能取到已提炼技能，M3「miss 只沉淀不复用」的死路被接上；✅ 打分器缺省/JEV
  未配置时零额外模型调用，JEV 不可达时自然退化。⚠️ **误匹配风险**（语义把不相关技能挂上）：阈值
  0.5 拦截 + 只在词法全无命中时启用 + 逐候选失败跳过；⚠️ **成本**：仅在「词法 miss」轮产生 K 次
  `score` 调用（K = 当前 active/gray 技能数，未预筛候选）；⚠️ 已知缺口（不扩大范围）：语义分只用于
  排序，**无历史成功率加权**（需命中/结果反馈闭环，属 #8）、候选未预筛（技能库规模上来后需粗筛）。
- **不采纳**：① 每次都语义打分并与词法融合（成本抬到每轮主路径）；② 把打分循环塞进 `SkillRouter`
  （skills 被迫依赖 judgment 请求形状，破坏 MAL）；③ 改 `score` 原语为逐条返回（judgment 规格
  blast radius）；④ 语义命中仍记 miss（假信号污染沉淀入口）；⑤ 低于阈值也采纳 / 无阈值（技能块
  灌水进 prompt）；⑥ 装配器填充 `ContextPack.skills`（技能与事实争预算 → 恒注入退化为可能被挤出）；
  ⑦ 保留恒空字段待将来使用（无生产者的字段是投机抽象）。

## ADR-0050：技能迭代闭环（命中注入纯 dict + 收尾钩子扩 ok + 进程内反馈 + 复用 VersionManager）

- **状态**：Accepted（2026-10-04；change `0045-skill-iteration` 落地，637→649 tests 绿）
- **上下文**：Phase 18 #8（维度1 第三环）。走查发现三处断链：① **`Skill.instructions` 从未进 prompt**
  ——planner 的技能块只渲染 `skill_id`，提炼出的步骤无人读，`#7` 的「语义路由取到技能」实际只取到一个
  名字；② **无任何命中/结果记录**——`#7` 遗留的「无历史成功率加权」无从实现；③ **`VersionManager`
  无调用者**——灰度/A/B 三段能力齐备（ADR-0048 决策 ⑥ 已记该缺口）但生产恒不触发。
  同时 `#6` 的收尾钩子 `SopObserver(task, steps)` 是**成功专语义**（失败轮不提交）→ 无法感知执行失败，
  迭代判据失真。
- **决策**：
  ① **命中注入的载荷是纯 dict 快照，由组合根组装**（`SkillHint = {skill_id, version, instructions[:400]}`）：
  与 `#6` 的 `SopWriter`、`#7` 的 `SkillScorer`、`facts: list[dict]` 同一口径——跨域接缝只传**纯数据**，
  loop 不 import skills（`test_architecture` 红线）。**不采纳**「`SkillRouter.match` 直接返回含
  instructions 的对象再序列化」：路由返回 `SkillMatch`（skills 类型）是域内自然形态，注入是**组合根**
  的职责（谁持版本与反馈，谁组装提示）。
  ② **收尾钩子扩为 `TurnObserver(task, steps, ok)`，成功/失败都提交**（用户 2026-10-04 定夺）：
  「结果不达标」的唯一来源是本轮成败（`limit_reason` 即失败）；只有成功信号无法感知失败。
  `SopExtractor.observe(..., ok=False)` 仍**只吸收成功**（`#6` 语义不变）；钩子抛错降级留痕，
  事件随语义泛化更名为 `turn_observer_failed`（原 `sop_extract_failed`）。**不采纳**「新增第二个
  outcome 钩子」（一个收尾点两个钩子冗余）、**不采纳**「成功-only 弱信号」（以「同组任务反复出现」
  代替失败率，判据不可信）。
  ③ **反馈按 `(skill_id, version)` 进程内累计**：版本维是 A/B 的前提（同技能两版本各自统计）；
  `version` 为显式关键字参数（避免 `(id, ok)` 的位置歧义）。不落盘、不写记忆——反馈是**运行时统计**，
  不是需跨会话追溯的事实（技能库本身亦无持久化）。`total` 只计有结果的执行（命中未收尾不计）。
  ④ **迭代复用 `VersionManager`，不新增 A/B 引擎**：灰度 = `promote(id, draft, 0.3)`、选版 =
  `select`、定夺 = `ab_test`，A/B 指标接 `feedback.success_rate`（越高越好，与 `b > a → promote` 同向）。
  **退化只丢草稿**：草稿版本**不是**库中 `Skill.version` → `ab_test` 的 revert 分支里
  `_deprecate(id, v_b)` 自然 no-op，**技能不会被误标 deprecated**（刻意依赖的既有行为，测试显式覆盖）。
  **不采纳**「新建 A/B 引擎」（重复 ADR-0048 已判为「能力已有、只缺调用者」的代码路径）。
  ⑤ **触发点全在组合根闭包**（`_loop_hooks()` 每 loop 一组）：命中钩子（路由 → `resolve` → 记命中 →
  快照）与收尾钩子（记结果 → `decide` → 失败再 `consider` → 转交 SOP 观察者）共用闭包内 `surfaced`
  快照；**状态不跨 loop 共享**（子 Agent loop 各自一组，为将来的嵌套 loop 留对形状）。loop 只持两个
  纯数据回调。
  ⑥ **改写走既有 DI 接缝**（复用 `SopWriter`：prompt → 文本）：skills 不 import 任何 LLM 抽象，
  模型调用由组合根注入（同 ADR-0048 决策 ①）。未注入 writer → `consider` 直接返回 None，
  **零额外模型调用**；改写文本为空 → 不入草稿（不写半成品）。
- **后果**：✅ 提炼出的 `instructions` 首次真正进入推理 prompt（技能从「名字」变为「可执行步骤」）；
  ✅ 命中/成功率成为可观测统计，`#7` 的「历史成功率加权」缺口具备了数据源（加权本身仍未接）；
  ✅ `VersionManager` 三段能力首次有生产调用者，灰度 → A/B → 落地/退回闭环可跑通且可逆
  （`Effect(op="skills.iterate")`）；✅ 反馈/迭代全在组合根，loop 零改动语义（仅钩子签名 + 事件名）。
  ⚠️ **改写依据弱**：prompt 只有「现行步骤 + 命中/失败计数」，无失败轨迹（轨迹级诊断属 evolution
  维度2）；⚠️ **样本进程内**：重启归零，草稿丢弃后需重新累计（无 cooldown、无轮数上限，技能库规模
  小时可接受）；⚠️ **成功率口径粗**：只区分成败，不检测 `instructions` 是否被模型实际采纳；
  ⚠️ 已知缺口（不扩大范围）：技能库无持久化、UIAPILayer.compact 仍为 no-op。
- **不采纳**：① 路由直接返回含 instructions 的对象（skills 类型泄漏进 loop）；② 新增第二个 outcome
  钩子（同一收尾点冗余）；③ 成功-only 弱信号（判据不可信）；④ 新建 A/B 引擎（重复既有能力）；
  ⑤ 命中/结果按技能（不分版本）累计（A/B 无从比较）；⑥ 反馈落盘/写记忆（运行时统计非事实）；
  ⑦ 共享一份 `surfaced`（子 Agent loop 互相污染）；⑧ 改写失败即抛（迭代是旁路，抛错会打断本轮推理）。

## ADR-0051：架构级候选强制人工审批（风险域固化物 + permission 域判定谓词 + confirm 三重校验）

- **状态**：Accepted（2026-10-04；change `0046-evolution-hitl-confirm` 落地，649→660 tests 绿）
- **上下文**：Phase 18 #9（维度2 架构级进化的「人工审核必审」收口）。走查确认：`EvolutionEngine`
  的 `confirm()` 只是 `candidate.status = "confirmed"` 的**裸 setter**（engine.py:104-106）——
  **任何调用方一句话就放行候选，与权限审批流零联动**；而 evolution spec「候选待人工确认」的
  Scenario 明确写着「通过后入 skills 库（**与权限审批流联动**）」。同时 `GenerationCandidate` 只有
  `kind`，架构级与技能库级候选在确认路径上**毫无区别**（phase-18 §4 第 8 条要求按风险域分流）。
  权限侧 `ApprovalWorkflow` 已备（create/ask/approve/reject/edit_plan + 归档），但**状态词表
  `"approved"` 是模块私有**（`approval.py:19-24`）→ 域外无法判定「批了吗」。
- **决策**：
  ① **`risk_level` 是候选的固化物，由提案阶段按 `kind` 判定**（plugin → `high`，skill → `low`）：
  风险域是**提案时的事实**，不是确认时的调用参数——由调用方声明风险等于把门禁交给被门禁的一方。
  字段默认 `"low"`，既有构造调用零改动。**不采纳**「调用方传 `risk_level`」（同一候选风险域随
  调用方而变，规格要求确定性判定）。
  ② **审批判定谓词落在 permission 域**（`is_approved(ticket)`，导出）：状态词表属 permission，
  若 evolution 自写 `ticket.status == "approved"`，等于把一个域的私有词表复制到另一个域。
  **不采纳**「engine 注入 `ApprovalWorkflow` 实例再调其方法」（该判定是审批单的**纯函数**，为它
  注入有状态对象是无谓依赖）、**不采纳**「evolution 自定义 `Callable[[Any], bool]` 接缝」（三行
  谓词藏进闭包让「谁在判定」不可见，且此处不存在需替换的实现）。方向 evolution(L4)→
  permission(横切底层) 是**下层依赖**，与既有 `im/gateway.py → core.permission` 同向。
  ③ **`confirm(candidate, *, approval=None)` 对 `high` 做三重校验**：**有单 + 已批准
  （`is_approved`）+ `request.target == candidate.target_plugin`**；任一不满足即抛
  `EvolutionError(CONFIRM_REQUIRED)`（**不返回布尔**——静默失败会让调用方误以为已放行），候选保持
  `pending`，既有的 `CANDIDATE_PENDING` 守卫在 `crystallize` 兜底。目标一致性挡住「拿别的插件的
  批准单解锁本候选」——没有它门禁只是仪式。
  ④ **`low` 分支行为不变，且明确不引入低风险自动结晶**：技能库级候选仍须**显式人工** `confirm()`；
  维度1 的「无人工 confirm」由 SOP 提炼直连 `SkillLibrary` 兑现（不经 evolution engine），
  两条通道不混。
  ⑤ **engine 只做门禁校验，不做人的事**：不建单、不阻塞等待、不推进单据生命周期（TTL / ask
  超时 fail-closed / UI·IM 交互属 permission 与交互端）。**不采纳**「engine 内建 workflow 自动
  建单等待」（把交互语义塞进冷路径引擎）。
  ⑥ **不新增可追溯字段**：审批单自身携带 `request.target` / `request.trace_id` 且经
  `ApprovalWorkflow` 归档（`list_archived`），追溯链已完整；**不采纳**「候选上再存 `approval_id`」
  （同一事实两处存储 → 两处漂移）。
- **后果**：✅ evolution spec「候选待人工确认（与权限审批流联动）」首次真正兑现——架构级候选**在
  代码层不可能**绕过人工审批放行；✅ 风险域成为候选的确定属性，「维度1 可自动 vs 维度2 必审」
  有判据可依；✅ 既有调用零改动（`GenerationCandidate` 新字段有默认值；`_engine()` 默认
  `Proposer(kind="skill")` → `low` → `confirm(candidate)` 行为不变）。⚠️ **进程内信任边界**：
  单据由 permission 域构造（状态只经 `_resolve` 迁移），但同进程代码理论上可自造
  `ApprovalTicket(status="approved")`——与既有 `approver` / `ApprovalChannel` 的信任面一致
  （进程边界外的不可信结构不在本次范围，如实记录）；⚠️ 审批归档与候选队列均不落盘（进化引擎
  本身无持久化）；⚠️ 已知缺口（不扩大范围）：观察期自动溶解归 #10。
- **不采纳**：① 由调用方传入 `risk_level`（门禁交给被门禁方）；② evolution 自认
  `"approved"` 字面量（跨域复制私有词表）；③ 注入 `ApprovalWorkflow` 实例 / 自定义判定接缝
  （纯函数 + 无替换需求）；④ 门禁失败静默返回布尔（调用方误以为放行）；⑤ 不校验审批单目标
  （跨候选复用审批 → 门禁形同虚设）；⑥ 低风险自动结晶（phase-18 §4 第 8 条明确排除）；
  ⑦ engine 自动建单/等待人工（交互语义塞进冷路径）；⑧ 候选上再存 `approval_id`（双份事实）。

## ADR-0052：观察期回归自动溶解（独立窗口注册表 + 绝对分差判据 + 采样接缝不调度 + 教训承载审计）

- **状态**：Accepted（2026-10-04；change `0047-evolution-auto-dissolve` 落地，660→669 tests 绿）
- **上下文**：Phase 18 #10（进化的回滚收口，验收锚点「已结晶技能在观察期回归超阈值 → 自动
  `dissolve` 并保留教训」）。走查确认：`EvolutionEngine.dissolve()` 已具备（技能标 deprecated +
  教训写 L2）但**没有任何调用方**——spec「溶解与回收 / 退化检测」在生产不可能发生；`crystallize`
  发布后**再无任何观察点**（`_eval[id(candidate)]` 只服务发布前门禁）；phase-18 §5 还要求退化后
  「冻结该方向（冷却期）」以防抖动。
- **决策**：
  ① **观察期窗口是独立注册表**（`evolution/observation.py::ObservationRegistry`），不是 engine 的
  私有 dict、也不挂在候选上：阈值口径（下限/容差/冷却期）是**窗口的性质**；而候选是「一次提案」的
  产物、`crystallize` 后即离场，窗口需要**独立于候选**存活。**不采纳**「复用 `Evaluator` 的留出
  评测」：留出评测是**发布前门禁**（候选 vs 基线，`score_fn` 跑留出集），观察期是**发布后的实测
  表现**——同一「退化」概念、两个数据源，合并会把发布前门禁拖进每个样本。
  ② **回归判据 = 样本下限(3) + 绝对分差(0.2)**：形状复用 `Evaluator.evaluate` 的
  `held_out < baseline - margin`（同一心智模型，不需要第二种「退化」定义）；用**绝对分差**而非相对
  比例——相对口径在基线接近 0 时会把 `baseline * (1 - tol)` 压到 0，任何微小波动都触发。基线为 0
  的窗口（`Evaluator` 默认评测分 0.0）在绝对容差下**不会触发**——「宁可漏报不误杀」：溶解是不可逆
  方向上的重动作。
  ③ **`observe` 是采样接缝，不内建调度**：谁按什么节奏采样属调用方（worker 冷路径 / 未来
  evaluator 循环 / 运维脚本）——`EvolutionWorker` 的节奏是「累计 N 条 trace 跑一次闭环」，与「按
  时间窗采样」是两条不同的冷路径；`now` 可注入使判定**离线可断言**。**不采纳**「引擎内起定时器」
  （把调度语义塞进领域引擎）、**不采纳**「`observe` 返回 bool」（返回
  `EvolutionOutcome(status="dissolved")` 与 `run_cycle` 同形状，调用方直接拿到审计产物）。
  ④ **冻结即清零样本**：只记 `frozen_until` 而保留旧样本，会让冷却期结束后的第一票采样立刻再次
  越线（旧样本 + 新样本已过下限）→ 溶解/重结晶抖动；清零是让冷却期**真正有效**的必要动作。
  ⑤ **审计留痕走既有教训条目**（回归证据拼进 `dissolve` 的 reason，落 L2
  `tags=["evolution","dissolve"]`）：evolution 目前**不依赖 observability**（引擎无 tracer，只有
  `EvolutionWorker` 持 tracer）；为一条审计事实给引擎接 Tracer 会改其构造面与装配，收益不足。
  **不采纳**「engine 注入 `Tracer`」（需要可观测面时由持 tracer 的 worker 侧记录）。
  ⑥ **两维度通用**：技能级与架构级候选的结晶产物同等开窗（`crystallize` 的两条分支统一在返回前
  开窗），与 phase-18 §4 第 9 条一致。
- **后果**：✅ spec「溶解与回收 / 退化检测」首次可发生——`dissolve` 从死路径变为**发布后被观察、
  退化即自动回滚**；✅ 冷却期让「自动回滚」不演变成抖动的自动翻转；✅ 发布前（门禁）与发布后
  （观察期）两条退化判据各司其职、形状统一；✅ 未调用 `observe` 时行为与今天逐字节一致。
  ⚠️ **无采样调度**：engine 只提供接缝，「按什么节奏采样」未定义（如实记录）；⚠️ **窗口进程内**：
  重启即失（进化引擎与候选队列均无持久化）；⚠️ **单目标单窗口**：重新发布覆盖旧窗口（刻意的
  「重新起算基线」，历史观察数据不保留）；⚠️ **基线 0 窗口不触发**（绝对容差的取向，见决策 ②）。
- **不采纳**：① 观察窗口塞进 engine 私有 dict / 挂到候选上；② 复用留出评测做观察期（数据源不同）；
  ③ 相对比例判据（基线趋 0 时误报爆炸）；④ 引擎内建采样调度（调度语义不属领域引擎）；⑤ `observe`
  返回 bool（丢审计产物）；⑥ 冻结保留样本（冷却期形同虚设）；⑦ 冻结需人工解冻（增加运维面，
  冷却到期自动恢复已足够）；⑧ engine 注入 `Tracer`（为一条审计事实改构造面）。

## ADR-0053：技能态持久化（逐类自持落盘 + 两个纯函数 + 损坏降级不阻断）

- **状态**：Accepted（2026-10-04；change `0050-persist-skills-state` 落地，679→685 tests 绿）
- **上下文**：Phase 19 账本 A3（进程内无持久化）。Phase 18 的「经验 → 技能」结晶链路有四处运行态
  只在进程里：`SkillLibrary` 注册表、`SkillFeedback` 统计（模块注释自陈「仅进程内统计」）、
  `SopExtractor` 样本累积、`VersionManager` 灰度·A-B 状态。组合根每进程新建 →
  生产**每次启动技能库恒为空、样本从零攒、灰度/定夺结果蒸发**，结晶实际不跨会话累积。
  Phase 18 有意把持久化排除（先跑通闭环、再补落盘），至此收口。仓库既有落盘惯例见
  `memory/backend.py`、`durability/store.py`、`deployment/host.py`（`path: Path | None` +
  `_load`/`_persist`）。
- **决策**：
  ① **逐类自持落盘，共用两个纯函数**（`skills/persist.py::read_state` / `write_state`）：四个类的
  序列化形状各不相同（技能字段全量 / 计数嵌套 / 样本组 / 灰度·A-B），抽象成通用存储会迫使它们
  共享协议、收益为负；而让四份「读 JSON + 容错 + 原子写」各自复制又必然漂移。故只把「字节进
  字节出」下沉为两个无状态纯函数，**放在 skills 包内**（只服务技能态，不构成横切能力、不新增分层
  箭头）。（**后续修订**：change `0051` 引入进化侧第二个消费者后，该前提不成立，两个纯函数已提升到
  `src/core/persistence.py`（中性模块），见 ADR-0054。）**不采纳**「新建通用 `StateStore` 服务」，**不采纳**「复用 `memory.FileBackend`」
  （它绑死 `MemoryEntry` + `Layer`）。
  ② **单文件 JSON 快照，非 JSONL 追加**：`memory.jsonl` / `checkpoints.jsonl` 是**追加式日志**
  （条目只增不改、可截断重放）；技能态是**可变快照**（技能字段被迭代改写、灰度状态被覆盖、样本组
  提炼后清空），整体重写才贴合语义，与 `entry.py` 的 `serve.json` / `releases.json` 同类。
  ③ **`path=None` 为缺省 = 纯内存**：不注入就不落盘——既有纯内存构造与测试**零改动**，落盘是组合根
  的选择；生产由 `build_runtime` 注入 `$CORE_STATE_DIR`（同 `_memory_path()` 约定，env 可覆盖、
  测试经 conftest 已隔离）。
  ④ **`VersionManager` 由组合根显式构造并注入**：`SkillIterator` 未收到 `versions=` 时会**内部
  自建**一份，组合根拿不到它、也就无法落盘；顺带把「灰度/A-B 指标 = 各版本成功率」这条口径从
  `SkillIterator` 的缺省分支提到组合根显式化。
  ⑤ **损坏降级为空态，不阻断启动**：技能态是**可重建的派生数据**（技能可从记忆/提炼重建、样本可由
  后续轨迹重攒），为它像 `ConfigManager.load()` 那样结构化拒绝启动不成比例；与 `CheckpointStore`
  的「损坏标记 + 跳过」同属一类防御。原子写（临时文件 + `os.replace`）避免半写文件被读到。
- **后果**：✅ 技能库 / 反馈 / 样本 / 灰度态**跨进程存活**，结晶链路首次可累积（SOP 阈值不再每进程
  清零）；✅ 缺省纯内存 → 既有行为逐字节一致、测试零改动；✅ 零第三方依赖（标准库 JSON）。
  ⚠️ **不做跨进程并发写合并**：CLI 与 serve 同时写同一文件为整文件覆盖（后写胜），沿用既有惯例；
  ⚠️ **进化侧仍未持久化**（观察窗口 / 候选队列进程内，随账本 A5 一并做；**change `0051` 已落地观察窗口落盘**，见 ADR-0054）；
  ⚠️ **状态无版本号/迁移**：结构变更后旧文件按「结构不符」降级为空态（可重建，接受）。
- **不采纳**：① 新建通用存储服务；② 复用 `memory.FileBackend`；③ JSONL 追加式；④ `path` 必填
  （破坏纯内存测试与既有构造）；⑤ 损坏即拒绝启动；⑥ 为文件加锁/合并（单机 CLI 语义下过度设计）；
  ⑦ 由 `SkillIterator` 内部落盘（组合根拿不到实例，且混淆「迭代器」与「存储」职责）。

## ADR-0054：进化冷路径驱动面 + 观察窗口持久化（loop 只持回调 + helper 提升到中性模块）

- **状态**：Accepted（2026-10-04；change `0051-evolution-cold-path` 落地，685→694 tests 绿）
- **上下文**：Phase 19 走查新增发现（账本 A10）——**进化冷路径在生产没有任何驱动面**：
  `EvolutionWorker.on_trace_complete` / `maybe_run` 全仓仅 `runtime.py`（构造）与 `tests/` 引用，
  CLI 无命令、loop 无节拍、无定时器 → L4 整条冷路径离线（`run_cycle`/`crystallize`/**开窗**都不发生）。
  账本 A5（观察期采样无来源）与 A3 的进化半边（观察窗口进程内）是它的**下游**。无真实常驻宿主
  （`HarnessHost` 每条 CLI 命令各起一份、serve 非长驻调度器），故「谁来定期驱动」只有两个诚实答案：
  **在有真实驱动的路径上搭节拍** + **显式入口**。
- **决策**：
  ① **驱动面 = loop 收尾节拍 + CLI 显式入口**：loop 收尾是唯一每轮必然经过的位置 → 与 change `0049`
  的记忆维护**共用同一节拍闸门**（`maintenance_interval`），由组合根注入一个可选冷路径回调
  `cold_path: Callable[[], None]`；CLI `core-agent evolve run` 提供一次性入口（`force=True` 跳过阈值门）。
  **不采纳**「loop 直接持 `EvolutionWorker`」：loop 属 L3、evolution 属 L4，loop 只拿回调（同 `hints` /
  `TurnObserver` 的 DI 手法），装配由组合根做——**架构红线（loop 不 import skills/evolution）不破**。
  ② **阈值门留在 `EvolutionTrigger`，节拍只给「机会」**：节拍不判「该不该跑」，`maybe_run()` 未达阈值
  返回 `None`（零模型调用、零状态变更）。**不采纳**「节拍自维护第二套阈值」：两处阈值必然漂移。
  ③ **采样来源 = 冷路径批次成功率（按 `plugin_id` 归因）**：台账 A5 两条路（评测轮回灌 / 外部上报）
  前者要再造一条无人驱动的评测、后者生产无上游；取**已有数据的最近似口径**——`EvolutionWorker`
  本批 trace 里已归因到该目标的成功率。**已知口径张力（如实记录）**：批次成功率与留出评测分**不是
  同一指标**（前者是线上代理指标），绝对分差容差 `0.2` 只是近似可比——宁漏报不误杀（溶解是不可逆
  方向的重动作，同 ADR-0052 决策 ②）。
  ④ **观察窗口沿用既有形状持久化**：`ObservationRegistry` 加可选 `path`，落盘
  `{target: {baseline, samples, frozen_until}}`；冻结截止**一并落盘**（否则重启即解冻、冷却期形同虚设，
  同 ADR-0052 决策 ④）。缺省纯内存。
  ⑤ **helper 提升到 `core/persistence.py`**：两个纯函数原在 `skills/persist.py`（ADR-0053 决策 ①），
  进化侧成为第二消费者后该前提不成立；留在 skills 包则 evolution 得反向 import skills 内部模块
  （**依赖方向错**）。提升到 `core/` 顶层的中性模块（**不 import 任何能力包、不构成横切能力**）是唯一
  不制造错误箭头的选择。**不采纳**「evolution 反向 import skills」与「各复制一份」。
- **后果**：✅ L4 冷路径首次有生产驱动面（长会话内可自动诊断/提案/开窗，CLI 可手动触发一轮）；
  ✅ 观察窗口跨进程存活（冻结期仍有效）；✅ loop 分层红线不破（只持 `Callable[[], None]`）；
  ✅ 缺省未注入回调 → 既有 loop 行为零变化。⚠️ **不做**常驻后台任务/定时器（无宿主）；
  ⚠️ **不做** A4（`confirm` 的生产调用方 / pending 队列驱动面）——那是审批操作面，另起；
  ⚠️ 采样口径与留出评测分非同指标（见 ③）。
- **不采纳**：① loop 直接 import evolution；② 定时器/后台线程（无宿主、引入调度语义）；
  ③ 节拍自维护第二套阈值；④ 采样只在 CLI 触发（节拍覆盖不到「长会话中自动回滚」）；
  ⑤ 窗口不落冻结截止；⑥ helper 留在 skills 包内。

## ADR-0055：constraints 中间件链接入 loop（结果侧观察者 + 按工具熔断 + 只计执行失败）

- **状态**：Accepted（2026-10-04；change `0052-constraints-middleware-wiring` 落地，694→706 tests 绿）
- **上下文**：Phase 19 账本 E1——**constraints 中间件链从未注入 loop**（`loop/default.py` 的
  `_apply_middlewares` 是生产死代码，`runtime.py` 从不传 `middlewares=`）。一手核实两处订正：
  ① **空转的不是校验**（校验已由 `ToolProvider._validate_args` 承担，与 `Validator.validate_input` 逐行等价）；
  ② 上下文压缩已接线（`compactor=`）。真实残留 = 熔断在生产**无任何等价物**。关键事实：loop 的
  before-only 接缝足以表达「拒绝/短路」（返回终止 Action 即经 `observe` 收尾，与 `decline` 同构），
  但**结果侧信号缺失**——没有东西能喂 `CircuitBreaker.record_result`，而 `before` 只在 `state==OPEN`
  抛错、`state` 只由 `record_result` 置 OPEN → **熔断证明不可开**。
- **决策**：
  ① **加法式结果侧接缝，不改 `Middleware` 契约**：保留 before-only 的
  `Middleware = Callable[[LoopContext, Action], Action | None]`，另增
  `action_observers: list[Callable[[LoopContext, Action, ActionResult], None]]`——每个**非终止**动作完成后
  按注册序回调、仅通知。**不采纳**「把 `Middleware` 改成 `before/after` Protocol」：破坏既有 callable 用法、
  且无逆序消费者（YAGNI）。
  ② **适配层落 loop 侧**：`src/core/loop/constraints_adapter.py`。`constraints → loop` 是测试强制红线
  （`test_phase2_middleware_no_reverse_dependency`），而 `loop → constraints` 合法 → 适配层只能在此侧。
  ③ **非对称失败策略**：before 侧中间件 fail-loud（异常传播，行为不变；适配层自捕获 `ConstraintError`）；
  结果侧观察者 fail-soft（单观察者异常降级为 `action_observer_failed` 遥测，不改本轮结局），对齐既有
  `turn_observer` / `cold_path` 降级先例。
  ④ **熔断按 `tool_id` 隔离**：`CircuitBreaker` 只有单计数器/单状态，直接接进 loop 会让一个坏工具
  **全局开闸**；适配层持 `dict[str, CircuitBreaker]` 惰性建，**不改 `CircuitBreaker` 既有契约**。
  ⑤ **只计执行类失败**：`TIMEOUT` / `EXECUTION_FAILED`（及未知码 fail-safe）→ `record_result(success=False)`；
  策略性拒绝（`INVALID_ARGS` / `COEFFECT_MISSING` / `GATE_DENIED` / `IRREVERSIBLE_BLOCKED` /
  `NO_TOOL_PROVIDER`）**完全不调** `record_result`——否则模型可用坏参数把工具"锁死"。
  ⑥ **短路语义 = 终止本轮**：熔断打开 → 返回终止 Action（与 `decline` 同构）。**接受**「无法同轮改投工具 B」。
  ⑦ **有意不接**：`Validator`（被工具层吸收且接线会更差：opaque 拒绝 vs 结构化错误供自纠）、
  `RetryPolicy`（副作用幂等风险 + `ToolDef` 无幂等标记 + 二次 `EffectTracker.record` 污染 undo 栈；
  规格重试场景已由 ReAct 观察回灌满足）、`Fallback`（无生产 `fallback_fn`）、`ContextCompressor`（非 `Middleware`）。
- **后果**：✅ constraints 熔断首次在生产真正开合（端到端：第 N+1 次调用不再执行该工具）；
  ✅ loop 分层红线不破（`action_observers` 只持回调，loop 不 import constraints）；✅ 缺省不接线 = 零行为变化
  （`action_observers` 缺省空）；⚠️ 熔断阈值/冷却不可配（`configuration/` 无 constraints 段，属 E10 配置门控）；
  ⚠️ 裸 `DefaultLoop()` 兜底路径（ui/pet/beast）无链——生产由组合根注入，E3/E4 跟踪注入面完整性。
- **不采纳**：① 把链压进 before-only（熔断不可开、校验/压缩重复 → 零收益）；② 包装 `ToolProvider`
  （工具边界已是同类链、且 `_apply_middlewares` 仍死）；③ 真洋葱逆序 `after`（无消费者）；
  ④ `CircuitBreaker` 直连 loop（全局开闸）；⑤ 策略性拒绝计入熔断；⑥ 接线 `Validator`/`RetryPolicy`/`Fallback`。

## ADR-0056：宠物子系统纳入组合根（运行时注入 + 注册表落盘 + 快照恢复）

- **状态**：Accepted（2026-10-04；change `0053-pet-runtime-wiring` 落地，706→714 tests 绿）
- **上下文**：Phase 19 账本 E4 —— **pet 子系统从未接入组合根**（`runtime.py` 零 pet 引用），
  `entry._pet` 每次调用**现造** `PetManager()`/`PetActivator()`。四项同根症状：① 注册表不落盘（进程退出即丢，
  `pet gather` 后新进程 `pet list` 看不见）；② `PetActivator._activate` 只传 `persona` → `PetSession` 拿
  **echo 的 `DefaultLoop()`** 且 `memory=None` → 偏好**落不到 L2**（违反 Preference Tracking）；③ 唤醒走 echo loop；
  ④ `ui/api.py` 零 pet 引用（三入口缺 WebUI NL）。前置 A3（存储选型）已由 change `0050` 关闭。
- **决策**：
  ① **pet 经组合根装配**：`runtime.py` 是唯一组合根（`test_runtime_is_sole_composition_root`），
  而 pet 依赖含 `loop`/`memory` —— 只有组合根持有；`pet` 属 `CAPABILITY_MODULES`，组合根 import 合法。
  `Runtime` 增 `pet_manager`/`pet_activator` 两字段（唯一构造点在 runtime）。**不采纳**入口自建
  （拿不到 runtime 的 loop/memory，症状 2/3 不可闭合）。
  ② **注册表落盘 = 快照 + 恢复工厂**：`PetSession.snapshot() -> dict`；`PetManager(path, *, factory)`
  init 加载、变更后落盘；组合根传 `factory` 使加载记录恢复为**带真依赖的活会话**。保持
  `list() -> list[PetSession]` 契约不变。落盘路径 `$CORE_STATE_DIR/pets.json`（沿用 `_skill_state_path`
  先例，单文件 JSON 快照）。**不采纳**落「元数据记录」并改 `list()` 返回类型（破坏既有契约与 `_print_pets`）。
  ③ **依赖注入加法式**：`PetActivator.__init__(manager=None, *, loop/memory/explorer/safety/notifier/busy=None)`，
  `_activate` 透传 `PetSession`；缺省全 `None` → 既有三入口测试行为不变。
  ④ **WebUI NL 入口落 `UIAPILayer.activate_pet`**（注入 `pet_activator`）；`/pet` 斜杠面板属 UI 层面
  （候选来自 `list_tools`），不进内核。
  ⑤ **`DefaultLoop` ↔ `LoopPlugin` 协议错位沿用 `cast` 桥接**（协议声明 `astream` async / `act` sync，
  与 `DefaultLoop` 实现方向相反；全仓既有 workaround，见 `entry._build_ui`），行为不变。
- **后果**：✅ 生产激活的宠物持有 runtime 的真 loop / 共享记忆（偏好落 L2、唤醒走真 loop，
  满足 Preference Tracking / Background Lifecycle）；✅ 注册表跨进程存活（`pet gather` 后新进程 `pet list`
  可见、`pet stop` 生效）；✅ 三入口（CLI / WebUI NL）落到同一 `PetManager`；✅ 缺省不接线 = 零行为变化
  （裸 `PetManager()`/`PetActivator()` 不变）；⚠️ `AsyncNotifier` 无 channel（`flush()` 投递为后续行）；
  ⚠️ 无后台 daemon（pet 仍显式 `wake`，daemon 化属另一变更）。
- **不采纳**：① 入口自建 pet（症状 2/3 不可闭合）；② `list()` 返回元数据记录（破坏契约）；
  ③ 自建调度线程 / daemon（超范围）；④ 把 `/pet` 斜杠面板塞进内核。

## ADR-0057：MCP stdio 传输生产实现（同步 stdlib）+ 消费侧安全接线

- **状态**：Accepted（2026-10-04；change `0054-mcp-stdio-transport`，732 tests 绿）
- **上下文**：ADR-0043 已裁 `mcp` SDK 按 transport 分流（stdio=stdlib 手写 / http=懒 import 可选 extra），但实现切片（`doc/openspec/changes/archive/2026-10-01-0033-mcp-install-security/tasks.md` 2.x–4.x）一直未落地：`build_transport` 恒抛 `MCP_CONNECT_FAILED`（连本地 stdio 都连不了）；`MCPClient.add` 硬编码 `transport="http"`（不按来源分流）；消费侧零安全接线（子进程不经沙箱、http 出站不经白名单）。落地时须裁决两件事：① stdio 传输**同步 vs 异步** —— `Transport` 契约（`connect/call/ping/close`）全是同步 `def`，`MCPClient`/`MCPServer`/`ToolProvider` 全链同步，而 ADR-0043 举的实现是 `asyncio.create_subprocess_exec`（async）；② 沙箱如何承载**长连接**子进程 —— `SandboxManager.run` 是一次性 `subprocess.run`（run-to-completion），无法提供持续 stdin/stdout。
- **决策**：
  ① **stdio 用同步 stdlib**：`StdioTransport` 以 `subprocess.Popen(text=True)` 拉起子进程 + 后台读线程把 stdout 行入 `queue.Queue`，`call` 写请求行、按 `id` 配对、`queue.get(timeout=budget.timeout_s)` 超时（`REMOTE_TIMEOUT`）；`close` terminate→kill 回收。ADR-0043 的 `asyncio` 是实现建议而非契约，同步实现与同步契约**零阻抗**；`asyncio` 在同步契约下反需再起线程跑事件循环桥接（多一层）。
  ② **沙箱增 `SandboxManager.spawn`**：复用 `_apply_resource_limits`（rlimit `preexec_fn`）返回**活** `Popen`，句柄归 transport 持有并在 `close` 终止；拉起失败降级 `SANDBOX_UNAVAILABLE`。与 `run` 互补（一次性 vs 常驻），内核安全链路 owner 仍是 `permission`（不让 transport 自写第二份 rlimit）。**接受**：可移植 fs jail 需 OS 设施，`spawn` 只做 rlimit（与既有 `_subprocess_backend` 同款限制）。
  ③ **http 只落地可离线验证的半**：`build_http_transport` = 出站白名单校验（非白名单 host → `PERMISSION_DENIED`）+ `mcp` SDK 懒加载检查（`importlib.util.find_spec`，缺失 → `MCP_CONNECT_FAILED` + `pip install core-agent[mcp]` 提示）；SDK 存在时明确报「会话待接入」。**不写无法运行/类型检查/测试的投机 SDK 适配层**；真实 `Mcp-Session-Id` 会话记后续。
  ④ **`add` 按来源形状分流** + `_call` 增 `except MCPError: raise`（传输层结构化错误码直通，不被兜底分支重包为 `MCP_UNAVAILABLE`）；`connect` 失败路径补 `transport.close()`（不留半开连接 / 残留子进程）。
  ⑤ **组合根装配**：`build_runtime` 建 `SandboxPolicy()` + `SandboxManager(policy=…)` + `MCPClient(sandbox=…, policy=…)`，注入 `InstallDispatcher`；`Runtime` 增 `mcp_client` 字段。空白名单 = fail-closed 全拒出站（安全默认）；白名单配置化记后续。
- **后果**：✅ 本地 stdio MCP **零新依赖**直接可用（连/发现/调用/销毁/超时全链）；✅ 消费侧安全接线落地（沙箱配额 + 出站白名单 + 确认门已有等价物的验证）；✅ `Transport` 抽象 / `build_transport` seam 不变，测试仍可注入 `FakeTransport`；⚠️ http 真实会话与 `MCPServer.serve` stdio 事件循环待接入；⚠️ `MCPClient._named` 仍进程内（CLI 跨进程可见性待端点注册表落盘）；⚠️ 出站白名单暂不可配置；⚠️ stdio 子进程 fs 隔离仅到 rlimit。**不采纳**：asyncio 版 stdio（同步契约下更复杂）；让 transport 自写 rlimit（重复内核安全实现）；为 http 写未验证的 SDK 适配层。

## ADR-0058：人工确认队列持久化 + 稳定候选身份 + 操作面签发审批单

- **状态**：Accepted（2026-10-04；change `0055-evolution-confirm-surface`，750 tests 绿）
- **上下文**：账本 A4 —— `EvolutionEngine.confirm`（HITL 闸门）自 `0046` 起**无生产调用方**，`crystallize` 同样无。change `0051` 的 `evolve run` 只把冷路径推到 `pending` 就断链。落地时须裁决三件事：① **队列在哪** —— CLI 每条命令各起一份 `HarnessHost`（`0051` 已记），`_pending` 是进程内列表，跨命令不可见；② **检索键是什么** —— 门禁/评测报告原以 `id(candidate)` 为键存于引擎私有字典，**跨进程必然失配**，重启后 `crystallize` 会把该发布的候选误判为未过门/退化；③ **审批单谁签发** —— `risk_level="high"` 候选需一张获批审批单，而其发起端（permission 审批流）在生产从未被调用。
- **决策**：
  ① **候选带稳定身份**：`GenerationCandidate.candidate_id`（UUID 前 12 位，`field(default_factory=...)` 构造即固化）；门禁/评测检索一律按它。**不采纳** `(generation, target_plugin)`：`Proposer._generation` 进程内自增，两次冷路径各产出 `generation=1` 的同目标候选，组合键并不唯一。
  ② **结论随候选整体落盘**：新增 `PendingQueue`（`evolution/pending.py`）以「一条记录 = 候选 + `GateReport` + `EvalReport`」为形状，复用 `core/persistence.py` 的 JSON 原子写（零第三方依赖，与 `ObservationRegistry` 同模式；ADR-0054 已确立「组件自持序列化、persistence 只做中性 IO」）。不留「候选在而结论缺」的半状态 —— 那正是要修的误判来源。**已否决**「只落候选、评测重跑」：留出评测不可复现（基准集非确定注入）。
  ③ **`pending()` 只列 `status=="pending"`**：原 `_pending` 只增不减（第二次 `confirm` 会静默重复放行）；已确认/已拒绝的记录留台账充当最小审计痕迹，不另建归档结构。
  ④ **`reject` 落引擎、签发审批单落操作面**：候选状态词表属 evolution 域，故 `EvolutionEngine.reject(candidate, *, reason=None)` 是引擎方法（域外不认字面量）；而审批单的**签发**（`ApprovalWorkflow.create → approve`）放在 CLI —— 操作面即「人工」这一事实的来源，引擎只收单据做判定（`confirm` 三重门语义一字不动）。**已否决**引擎自造审批单：那等于 HITL 门自己给自己盖章。
  ⑤ **操作面一次动作完成确认+发布**：`core-agent evolve confirm <id>` 内联 `confirm` → `crystallize`（分成两条命令只会让人漏掉第二步，而漏掉第二步正是本变更要修的病）；非 `pending` 态候选一律反馈 + 非零退出（不得复活已拒绝/已确认的候选）。
- **后果**：✅ L4 的「过门候选 → 人工确认 → 结晶发布」在生产**首次端到端可达**（`confirm` / `crystallize` 各有生产调用方）；✅ 待确认事项跨进程可见、可处置（重启不误判）；✅ 零新依赖（stdlib JSON）；✅ 未注入路径纯内存，既有 750 tests 语义不变；⚠️ `ApprovalWorkflow` 归档仍进程内（跨进程复查「谁批的」待 permission 域的另一议题）；⚠️ 台账随确认次数单调增长、无回收策略（当前无消费者）；⚠️ `evolve confirm` 接受完整 12 位 id，不做前缀匹配（避免歧义匹配的隐性错误）。
## ADR-0059：密钥引用校验对称化 + 枚举型配置项取值校验（契约基线对账）

- **状态**：Accepted（2026-10-04；change `0056-config-validation-symmetry`，761 tests 绿）
- **上下文**：账本 E7/E8 —— 契约层与实现对不上账。一手核对后两者性质不同：**E7 是文档漂移**（`cli-contract-baseline.md` §10 把 `code_run` 标「未实现」、并列出 `web_scan`/`web_execute_js`/`ask_user`/`process`/`memory` 五个**从未存在**的名字，而 `specs/tool-use` 只要求 `code_run` + `web_fetch`，与实测 8 个工具 ID 逐一对得上）；**E8 有三处「规格已承诺、实现未做」**：`im.secret` / `judgment.api_key` 只查明文不查空值与可解析（而 `llm.api_key` 三重校验），`permission.mode` 未校验取值（而 permission 规格明列四档并写明映射 `config.permission.mode`）。
- **决策**：
  ① **冲突裁决以规格为准，不以「谁更新」为准**：基线文件溯源到 Phase 早期 `temp/plan_cli_ops/*` 推演稿，属**设计态快照**；故订正文档并在头部标注「非规范文件」，**不**按过时清单补实现（那等于让推演稿反向定义产品范围）。
  ② **密钥引用同口径**：`_secret_refs` 统一产出 `llm.api_key` / `im.secret`（段存在时）/ `judgment.api_key`（`provider` 非空时），判定链 `明文 → 空 → 不可解析` 由 `_secret_ref_error` 单点给出，错误文案不再因引用不同而形状不一。**可选段语义保留**：IM 段缺失不校验、judgment 惰性段（`provider` 为空）不校验。
  ③ **枚举口径「规格定义、配置强制」**：`permission.mode` 四档词表在 configuration 侧以常量复述并在注释指明来源（`_PERMISSION_MODES`），**不 import** permission —— 配置层不得依赖能力层（分层红线）。代价是词表双写，可接受。
  ④ **`extra` 宽松性不动**（用户裁决 B）：`extra` 是「五类结构化段之外一切」的兜底，收紧为白名单会拒绝用户既有自定义段、改变既有接受行为；**未确认键校验**转出为独立后续行（待定夺「仅告警」还是「硬拒」）。
  ⑤ **`None → ""` 归一**：`_build_config` 三个引用的 `str(x or "")`，否则 yaml 中 `api_key:` 空值经 `str(None)` 变成 `"None"` 字符串，会被判为「明文密钥」而非「缺失」——**错误文案失真**，与本变更承诺的「指明缺失或不可解析」矛盾。
- **后果**：✅ 密钥引用校验口径一致，空 / 不可解析的 IM、决策模型密钥不再静默通过（安全缺口闭合）；✅ `permission.mode` 非法取值在加载期被拒并列出四档；✅ 无新依赖、无分层破坏；✅ 契约基线恢复可信（E7 全闭）；⚠️ **校验变严**是行为变更：既有「IM 段 + 空 secret」或非法 `permission.mode` 的仓外配置将从静默接受变为启动报错（已核对仓内无用例依赖宽松行为）；⚠️ 四档词表两处字面量（决策 ③）；⚠️ `extra` 未知键仍静默接受。
## ADR-0060：神兽运行时桥接（专用路由作用域 / 惰性 loop 装配 / 共享记忆注入）

- **状态**：已采纳（change 0057）
- **背景**：`beast-mode` spec R4/R5 正文自述「runtime 调用 deferred」——神兽的独立 loop、共享记忆命名空间、神通注册、专属路由四项在生产装配**一处未接**：`BeastManager.summon` 造裸 `BeastSession`（echo loop + 无记忆，`remember()` 必抛）、`register_innate_skills` 零调用方、`SkillRouter.match` 无域过滤、CLI `summon/recall` 造裸 `BeastActivator`。且**「只注册不路由」不是中性半成品**：注册后专属神通会进主 Agent 候选并灌入主 prompt。
- **决策**：
  ① **作用域强制下沉到路由期**：`SkillRouter.match(task, *, domain=None)` —— 三节 `beast.<域>.<技能>` 为专属技能，仅 `domain == "beast.<域>"` 时进候选。理由：候选池在路由手里，这是**唯一有主体**的位置；否决「在 BeastManager 过滤」（它拿不到候选，会造第二真源）与「靠调用方自觉」（无强制力、直接违反 R5）。`domain=None` 为既有调用方保零行为变更。
  ② **形状即约定**：专属性以 `skill_id` 三节且首节 `beast` 判定，不另建注册表——与 `Beast.agent_id` / `innate_skill` 天然对齐，避免与技能库落盘产生第二真源。
  ③ **惰性 loop_factory**：不预建 20 个 loop（常驻无用），`BeastManager.summon` 按需 `loop_factory(beast)` 造；每次 summon 新 loop（记忆在共享 `MemoryStore`，loop 无跨会话状态）。
  ④ **专用路由器**：神兽用 `MultiAgentRouter([])` 独立实例，不与 coding/research 子 Agent 的 `agent_router` 混（神兽走显式 `handoff` target，不需要 fallback 语义）。
  ⑤ **钩子工厂参数化**：`_loop_hooks(domain=None)` 三处共用（主 loop / 通用子 Agent / 神兽），神兽传 `beast.agent_id`；**共享**同一 `skill_feedback`/`sop_extractor`/`skill_iterator`——神通的进化与通用技能同构，不搞第二套。
  ⑥ **CLI 同口径**：`entry._summon/_recall` 改走 `build_runtime`（与 `_pet` 一致），不再造空装配。
- **后果**：✅ R4/R5 的 deferred 解除，四项生产可触达并有端到端测试；✅ 主 Agent prompt 不被 20 条神通灌水（token 有界）；✅ 召唤即真跑 LLM loop（**这是 R4 本意**，非回归；LLM 不可达时 planner 降级为「LLM 调用失败」回复，不抛裸异常）；⚠️ 每次 CLI 进程仍是无状态装配 → `recall <beast>` 在该进程内必 `BEAST_NOT_MANIFEST`（**既有性质**，多兽跨命令状态另属后续行）；⚠️ 词法路由的噪声项（如领域串里的 `/`）会让任务命中他兽技能——属打分口径，不属作用域（作用域只保证非本域**专属**神通不可达）。
- **关联**：`beast-mode` spec R4/R5（MODIFIED）；接口 `03-interfaces/beast-mode-interface.md` §6/§8/§10。

## ADR-0061：技能排序接历史成功率加权（判定用基础分 / 冷启动中性 / 带下限）

- **状态**：已采纳（change 0058）
- **背景**：`SkillMatch.score` 注释自述「匹配度（语义 + 历史成功率 + 适用声明）」，实现只算语义/词法分；`SkillFeedback` 自 change `0045` 起在生产接线却零消费方（账本 A7）——迭代闭环算出的成功率指标**路由侧不用**。
- **决策**：
  ① **因子只影响排序，不参与命中判定**：阈值判原始语义分、词法命中判基础分 > 0。否则「语义 0.9 + 历史全失败」会被加权到 0.45 < 阈值而**被丢弃**——那是语义漂移，不是加权。
  ② **冷启动中性**：`SkillFeedback.success_rate` 无样本返回 0.0，直接相乘会把**全部新技能归零**（路由当场失效）→ 无样本因子取 1.0。
  ③ **有样本带下限 0.5**：`0.5 + 0.5 × 成功率`。直接乘成功率会让「一次失败」把技能永久踢出，形成失败→不入选→无新样本→永久失败的正反馈；下限使其仍可被再次选中并翻盘。
  ④ **注入而非内建**：`SkillRouter(feedback=None)` 缺省 = 因子恒 1.0 ⇒ 既有装配与全部既有测试零行为变更；组合根注入与 `SkillIterator`/`VersionManager` **同一个** `SkillFeedback` 实例（避免「迭代看一套数、路由看另一套数」）。
  ⑤ **有意不做候选预筛**（用户 2026-10-05 裁决 A）：语义兜底只在「全库词法零命中」时触发，此时任何词元重叠式粗排都得到空集；有用的粗排必须比词法更粗（字符 n-gram 等）= 引入**第二套匹配语义** + `N`/阈值两个新常量。当前库规模不构成成本约束 → 记为后续行 **A11**（含前置与成本事实：`SkillMatcher.score` 逐候选一次决策调用）。
- **后果**：✅ 规格自述口径补齐，成功率指标真正参与路由；✅ 冷启动/无注入两条路径零行为变更；⚠️ 排序变化的唯一前提是技能**有样本且成败不一**；⚠️ 「适用声明」维度仍未做（无数据源、无消费者，不虚设字段）。

---

## ADR-0062：校验口径单一真源（工具层委托 constraints Validator / 行为中性）

- **状态**：已采纳（change 0059）
- **背景**：账本 E14 —— 「调用前 schema 校验」有**两份实现**：`tools/provider.py:_matches_type` 与 `constraints/validator.py:_matches_type` **逐字节相同**，`ToolProvider._validate_args` 与 `Validator.validate_input` **语义逐行等价**（同 `required` 早返回、同 `properties` 遍历、同错误消息模板）。这是 E1 走查的残留：E1 订正「校验空转」后确认**校验实由工具层承担**，而 constraints 的 `Validator` 是**同一口径的第二份实现**（其 `before` 从未接进 loop 链，见 ADR-0055）。两处真源 ⇒ 任何一侧单独演化都会让「工具层拒绝」与「校验中间件拒绝」**静默分叉**。
- **决策**：
  ① **真源留在 `constraints`**：该义务（「工具调用前校验输入 schema」）在 constraints spec 中已写成自己的 Requirement，故口径归属 `Validator.validate_input`。
  ② **方向 `tools → constraints`**（一手核验）：`BASE_MODULES` 不含 `tools`；phase1 禁集只有 `tools → {memory, llm_provider}`；phase2 禁集只有 `constraints → {loop, skills, orchestration}`；且 `constraints` 全包不 import `tools`（无环）。与 ADR-0055 的 `loop → constraints` **同型**：横切能力被使用方 import。反方向会污染横切层对 L1 的依赖，否决。
  ③ **复用既有公开 API**：`Validator.validate_input(tool, args, schema) -> list[str]`（`Validator` 为无状态 Protocol 实现）；不新造模块级校验函数（YAGNI）。provider 保留 `_validate_args` 方法壳作适配器（`list[str]` → `ToolError`）。
  ④ **行为中性**：拒绝码仍 `INVALID_ARGS`；错误消息**逐字不变**——`validate_input` 把缺参列在首位，`properties` 遍历序与旧实现一致，故 `errors[0]` 恒等于旧实现早返回的那条。差别仅在于旧实现遇错型立即返回、新路径收齐全部错误后取首条（**全量列表不外泄**，`ToolError` 单错误契约不变）。
  ⑤ **规格只改一处**：`constraints` spec 增「口径单一真源」bullet + 场景「工具层与校验中间件口径一致」；`tool-use` spec 的「参数校验」是**行为要求**且行为不变 → 不写 delta（同一句话写两遍正是本变更要消灭的形态）。
  ⑥ **防复发靠测试**：结构守护（`core.tools.provider` 不再有 `_matches_type`）+ 行为等价（缺参 / 错型两条路径拒绝口径一致）。
- **后果**：✅ 校验口径单真源，分叉风险消除；✅ 工具层对外行为零变更（消息 / 错误码 / 早返回语义）；⚠️ `tools` 包新增对 `constraints` 的 import（层级合法，见 ②）；⚠️ `Validator.parse_output` 仍零生产调用方（planner 自解析）——属账本 **E13**，本变更不并入。**（2026-10-05 补记：E13 已由 change `0063` 判定关闭 —— 该零调用方为**有意**：规格「输出解析失败不执行」的生产实现是**动作感知**的 `LLMPlanner._parse`（失败 → 终止 Action：工具不执行 + 原因回灌下一轮），`parse_output` 无动作语义、接进 planner 反而是降级；判定与追踪号 `TC-CONS-05` 见 `03-interfaces/constraints-interface.md` §2。）**

---

## ADR-0063：未知配置段仅告警（顶层段名口径 + 白名单由 ConfigSpec 派生 / 不硬拒不静默）

- **状态**：已采纳（change `0064-unknown-config-section-warning`；用户 2026-10-05 裁决「仅告警」）
- **背景**：账本 E18（E8 第 5 条转出）—— `AppConfig.extra` 收纳「五个结构化段之外的一切」
  （`llm` / `features` / `im` / `pet` / `judgment`），于是**拼错的段名**（如 `llmm:`）被**静默**吞进去：
  既不报「未知配置键」，也不提示拼写错误。用户实际看到的是「缺失 LLM 配置项」这类**误导性**报错
  ——错误现象与根因相隔一层。ADR-0059 决策 ④ 已把「收紧会拒绝既有自定义段」记下，本 ADR 落定形态。
- **决策**：
  ① **仅告警，不硬拒**（用户裁决）：收紧为白名单硬拒会**拒绝既有自定义段**，改变既有接受行为
  （`extra` 的契约就是「结构化段之外的一切」）；完全静默又让拼写错误无处暴露。告警二者兼顾：
  **启动不阻断**，但错误**可见**。
  ② **白名单由单一真源派生**：已知段 = 五个结构化段 ∪ `ConfigSpec.map_to` 前缀 ∪
  有运行时语义的 `extra` 已知段（`permission`，本模块消费 `permission.mode`）。
  **不另维护一份段名清单**——新增 `ConfigSpec` 自动进白名单，杜绝「清单与 Spec 漂移」这一第二真源。
  ③ **口径只到顶层段名**：不递归校验已知段内部的未知子键。——子段校验需要逐能力 schema，
  属各能力自己的义务（如 `permission.mode` 的枚举由本模块代持已有先例）；顶层段名正是
  「段名拼错」这一现象的**充分**作用域，判到子键会越界成「配置全量 schema 化」。
  ④ **告警走 stdlib `warnings`**：`validate_schema` 只**产出** `ValidationResult.warnings`（纯函数、可断言），
  **发出**放在 `load()`（`warnings.warn(..., stacklevel=2)`）——副作用不混进校验谓词，
  且不依赖任何日志装配，CLI / 库调用方默认都能看到（零接线）。
  ⑤ **段不丢弃**：告警后该段仍留在 `extra`（既有行为不变），故**不破坏**任何既有多余段的消费者。
- **后果**：✅ 拼错段名从静默变可见，且**无破坏性**（不阻断、不丢弃）；✅ 白名单单一真源，
  不会与 `_CONFIG_SPECS` 漂移；✅ 校验谓词保持纯函数（告警只是返回值里的一项）；
  ⚠️ 首次在 configuration 引入 `warnings`（stdlib，无新依赖）；
  ⚠️ 段名之外的拼写（如已知段内的子键拼错，`llm.endpont:`）仍不告警 —— 属决策 ③ 的作用域边界，
  需要时另开（要逐能力 schema）。
- **关联**：`configuration` spec「配置校验与生效」（MODIFIED）；
  接口 `03-interfaces/configuration-interface.md` §2.1/§2.2；模块 `02-modules/configuration.md` §5。

---

## ADR-0064：LLM 传输层连接复用（线程本地按 origin 复用 / 代理与 3xx 回落 urlopen / 失效仅重建一次）

- **状态**：已采纳（change `0066-llm-connection-reuse`；用户 2026-10-05 裁决「实现（stdlib 零依赖）」）
- **背景**：账本 E11②（`0060` 收口时记下：「`urllib` 每请求新建连接」）。规格 llm-provider
  「模型调用可靠性」**已声明**「复用底层 connection / keep-alive 连接，减少握手开销，连接失效时自动重建」，
  但实现里三条传输路径（chat / embedding / SSE）各自 `urllib.request.urlopen` —— **每次调用一次 TCP+TLS 握手**，
  与规格条款**不符**（本项与 E12 同型：规格要求 X 而实现没有 ⇒ 先改代码，不订正规格）。
  用户否决「订正规格承认现状」，裁「实现」。
- **决策**：
  ① **只换传输、不动协议**：新增 `llm_provider/http_pool.py`（`HTTPConnectionPool`），三条路径统一走
  `transport.send(request, timeout=...)` 上下文管理器；`StdlibLLMProvider.__init__(transport=...)` 是注入接缝
  （DI 对齐 ADR-0040：三方/多实现边界须有抽象 + 隔离适配 + 注入点）。请求构建、SSE 解析、错误归一化、重试/降级**一律不动**。
  ② **线程本地所有权**：空闲连接存 `threading.local()`，**不跨线程共享** ⇒ 无锁、无归还竞争。
  provider 的同步传输本就在工作线程上跑（`asyncio.to_thread` / `run_in_executor`），同一线程的连续调用即复用；
  **不做跨线程池**：跨线程复用需要锁 + 借用协议 + 半开状态，复杂度与其收益（线程池规模通常为 1~2）不成比例。
  ③ **代理回落 `urlopen`**：环境为该 scheme 配了代理时**不入池**（`http.client` 不读代理环境变量）。
  自实现 CONNECT 隧道是另一件事（属能力增量），回落既保语义又零风险。
  ④ **3xx 回落 `urlopen`**：`http.client` 不跟随重定向；回落保持既有「跟随重定向」行为不变。
  ⑤ **失效只重建一次**：复用到的连接若在**发请求 / 读状态行**阶段失效
  （`RemoteDisconnected` / `BadStatusLine` / reset / broken pipe），关掉后**换新连接重发一次**；
  限定「尚未收到任何响应字节」才重发 ⇒ 不会重复产生计费副作用，也不会把真故障（拒绝连接）吞成重试放大。
  ⑥ **错误口径不裂**：`map_http_error` 补 `http.client.HTTPException` / 其余 `OSError` → `LLMNetworkError`
  （与 `URLError` 同层级、可重试）；否则连接池路径会把「拒绝连接」落成**不可重试**的裸 `LLMError`。
  非 2xx 一律**转 `urllib.error.HTTPError`** 抛出（含 code/reason/headers），使既有状态码映射（429/401/504…）零改动继续生效。
  ⑦ **读尽才归还**：响应体读尽的连接才回池；未读尽（如 SSE 中途停止）**关闭丢弃**，防半读流污染下一次请求。
- **后果**：✅ 规格场景「连接复用 / 失效自动重建」由**真实 socket 用例**证明（本地桩计 accept 数：两次调用 1 条连接；服务端关连接后自动重建）；
  ✅ RAG 索引循环、多轮对话等连续调用省去重复握手的 RTT/TLS 开销；✅ 零第三方依赖（`http.client` + `ssl` 均 stdlib）；
  ⚠️ 新引入「连接生命周期」这一状态（空闲超时由**服务端**决定，客户端只负责失效重建）；
  ⚠️ 复用粒度是「线程 × origin」（非「进程 × origin」）——多线程下各持一条连接，属决策 ② 的作用域边界。
- **关联**：`llm-provider` spec「模型调用可靠性」场景「连接复用」（**未改规格**，实现向规格靠拢）；
  代码 `src/core/llm_provider/http_pool.py` / `stdlib_provider.py`；
  接口 `03-interfaces/llm-provider-interface.md` §3；模块 `02-modules/llm-provider.md` §3.6；
  测试 `tests/test_llm_provider_reuse.py`、`doc/04-testing/test-cases.md`（TC-LLM-06）。

---

## ADR-0065：功能开关运行时门控（门控名单归组合根 / 缺省装配 / 只管装配不改二级开关）

- **背景**：规格「功能开关（feature flag）」逐字要求「关闭的模块不加载、不初始化」，三条输入通道
  （yaml `features:` / env `CORE_FEATURES_*` / CLI `--feature`）早已齐备，但**零消费者** ——
  `ConfigManager.is_enabled` 无生产调用方，`build_runtime` 无条件构造全部模块（账本 E10）。
- **决策**：
  ① **门控名单归组合根**（`core.runtime.GATABLE_MODULES = ("pet", "beast", "evolution")`）：配置层
  属 `BASE_MODULES`，不该认识能力模块名；名单与装配点同处一地即单一真源。configuration 只提供
  **极性纯净**的谓词。
  ② **新增 `is_disabled(module)` 而不改 `is_enabled` 的语义**：`is_enabled`（显式开启查询，缺省 false）
  已被接口文档与测试锁定，且正是缺省关模块（`pet.enabled`）需要的极性；装配裁剪是相反的极性，
  故另起谓词（`features.get(module) is False`，缺省**不关**）。
  ③ **缺省装配**（用户裁决 2026-10-05）：名单内模块**未声明即开**，仅显式 `false` 才不装配 ——
  兼容现状（features 段当前无使用者 ⇒ 既有行为逐位不变），代价是与 `phase-0` 原文「缺省关闭」
  的字面不符，已在规格里订正为「白名单内缺省开」。
  ④ **关闭是彻底的**：不构造实例、不产生装配期副作用（`beast` 连 `register_innate_skills` 都不做、
  `pet` 不读 `pets.json`）、loop 冷路径**置 `None`**（不造空转闭包）、CLI 入口拒绝
  （stderr 说明 + 退出 0，对齐既有 `pet.enabled` 未启用形态）。
  ⑤ **两级开关分层，互不覆盖**：`features.<模块>` 管**装配**、模块自身开关（`pet.enabled`）管**启用**；
  feature flag 不越权改后者。副产品：WebUI 的 `activate_pet` 与 CLI 的准入判据首次一致
  （此前组合根永远装配 pet ⇒ WebUI 无条件可用，而 CLI 认 `pet.enabled`）。
  ⑥ **不做**：`mcp` 门控（装配惰性，随 B4 CLI 接线落）、`im` 门控（无装配点）、`features` 未知模块名
  告警（与 E18 同族，名单在组合根 ⇒ 配置层无从判名）、`features` 值非布尔强转（既有语义）。
- **后果**：✅ 规格契约有了可验证落点（`tests/test_feature_gating.py` 18 例：缺省装配 / 关闭面为空 /
  不注册神通 / 不读注册表 / 冷路径置空 / 核心面不受影响 / 六入口拒绝）；✅ 缺省即装配 ⇒ 对既有部署
  **零行为变化**；✅ 名单单一真源，加模块只改组合根一处。
  ⚠️ `Runtime` 五个字段变可空（字段集与顺序未动）；⚠️ 门控名单是**组合根知道的模块名清单**，
  与「能力模块可插拔」的理想尚有距离（未来插件化时名单应随注册表派生）。
- **关联**：`configuration` spec「功能开关（feature flag）」（**MODIFIED**：装配语义 + 缺省开 + 单一真源名单）；
  代码 `src/core/configuration/manager.py`（`is_disabled`）/ `src/core/runtime.py`（名单 + 三处裁剪）/
  `src/core/entry.py`（`_module_disabled` + 六入口）；接口 `03-interfaces/configuration-interface.md` §2.2；
  模块 `02-modules/configuration.md` §3.3 / `02-modules/pet.md` / `02-modules/beast-mode.md`；
  测试 `tests/test_feature_gating.py`、`doc/04-testing/test-cases.md`（TC-CONF-01…03）。

---

## ADR-0066：熔断阈值/冷却可配（ConfigSpec 单一真源 / 不新增结构化段 / 校验期拒绝而非静默兜底）

- **背景**：`ConstraintsChain` 的构造面（`failure_threshold` / `cooldown_s`）本就为注入而设计
  （`constraints-interface.md` 自述「可注入便于测试」），但生产唯一调用点 `runtime.py` 不传任何参数 ⇒
  **硬编码类缺省 5 / 30s**，运维无法按环境调整（账本 E15）。
- **决策**：
  ① **ConfigSpec 单一真源**：两键写进 `_CONFIG_SPECS`（`map_to="constraints.*"`），CLI flag / env /
  yaml / 优先级链与 §2.3 白名单**全部自动派生**，不另维护清单；
  ② **不新增结构化段**：镜像 `permission.mode` 的 **`extra` 驻留**先例，而非加 `ConstraintsConfig` 段 ——
  避免改配置规格里「五个结构化段」的字面枚举，且 `map_to` 前缀已让未知段白名单自动收纳 `constraints`；
  ③ **校验期拒绝，不静默兜底**：阈值须 **≥1 整数**、冷却须 **≥0 数值**，非法即 `validate_schema` 报错并
  **阻断启动**（对齐既有密钥/枚举校验口径），不落回缺省值 —— 静默兜底会把「配错了」伪装成「配对了」；
  ④ **组合根注入、链身份不变**：`build_runtime` 经 `config.circuit_breaker()` 读出后传给
  `build_constraints_chain`，主 loop 与子 agent loop 仍**共享同一实例**（熔断态 per-runtime 语义不破）；
  ⑤ **类型归一在读侧**：访问器把 `extra` 里的原始值归一到 `(int, float)`，校验已保证合法，读侧仅做转换。
- **否决**：新增结构化 `ConstraintsConfig` 段（动规格字面枚举、收益仅类型提示）；仅 yaml 无 CLI/env
  （破坏 ConfigSpec「一处声明、多通道派生」的单一真源，且与其余所有配置项不一致）。
- **后果**：✅ 阈值/冷却成为配置项，四通道 + 优先级链齐备；✅ 非法配置**启动即暴露**；
  ✅ 类缺省 `5` / `30.0` 与规格缺省逐位一致 ⇒ 对既有部署**零行为变化**；
  ⚠️ `constraints` 是 `extra` 驻留段（无 `AppConfig` 类型字段），访问器须自行处理缺失/类型。
- **关联**：`constraints` spec「容错中间件」（**MODIFIED**：阈值/冷却可配 + 取值约束 + 校验期拒绝）；
  代码 `src/core/configuration/manager.py`（两 ConfigSpec + `circuit_breaker()` + `validate_schema`）/ `src/core/runtime.py`（注入）；
  接口 `03-interfaces/constraints-interface.md`、`03-interfaces/configuration-interface.md` §2.4；
  模块 `02-modules/constraints.md`；测试 `tests/test_constraints_config.py`、`doc/04-testing/test-cases.md`（TC-CONS-06/07）。

---

## ADR-0067：装配前单键解析 `config_value`（只读单键 / 缺文件容错 / 键名经单一真源回填）

- **背景**：语法层 `resolve(key, cli=, env=, yaml=, specs=)` 的 `yaml=` 缺省为空映射 ⇒ 调用方漏传
  即**静默少一层**。`entry._pet` 正如此（`resolve("pet.enabled", cli=, env=)`）⇒ CLI 前置判定与
  同进程稍后的 `build_runtime`（走 `load()`，含 yaml 层）判据不一致，违反规格「宠物模式配置」
  「CLI flag / env / yaml **三面一一对应**…禁止 pet 配置绕过 ConfigSpec 另起解析」（账本 E21）。
- **决策**：
  ① **新增装配前只读单键通路** `ConfigManager.config_value(key)`，内部即
  `resolve(key, cli=self._cli, env=self._environ, yaml=<yaml 层>, specs=self._specs)` ——
  **不另起解析**、与 `load()` 共用 ConfigSpec 单一真源（规格硬要求）；
  ② **不校验 / 不阻断 / 不缓存**：前置判定发生在整份配置校验**之前**，只读单键、不构造 `AppConfig`；
  整份配置的校验仍**唯一归** `load()`（避免第二条校验真源）；
  ③ **config.yaml 缺失按「无 yaml 层」处理**，不抛 `ConfigurationError` —— 前置判定的前提是
  「配置文件本就可能不存在」；**若在此抛错，CI（无 config.yaml）`pet gather` 会由退出 0 变退出 1**；
  ④ **yaml 层经单一真源回填**：`resolve` 的 yaml 层以 **`ConfigSpec.key`** 为键，而文件按
  **`map_to`** 点分路径嵌套（`im.corp-id` vs `im.corp_id` 不同名）⇒ 由 `map_to` 逐键取路径、
  以 `key` 回填，不按点分拼键；
  ⑤ **返回各层原文**：env/CLI 层为字符串，归一化（`entry._as_bool`）归调用方 —— 与 `resolve` 口径一致。
- **否决**：让 `_pet` 直接调 `load()`（整份校验 + 缺文件抛错，破坏 ③）；在 `entry` 内自读 yaml
  （第二条解析真源，违反规格「禁止另起解析」）；把 `yaml=` 缺省改为「自动读盘」（语法层不该有 I/O
  副作用，且 `ParamMapper`/`config get` 等既有调用方语义会被隐式改变）。
- **后果**：✅ CLI 前置判定与装配判据**同源**，宠物模式三面一致；✅ 缺文件路径不炸（CI 行为不变）；
  ⚠️ 新通路可被误用为「跳过校验读配置」⇒ 契约写明「只读、不校验；整份校验仍归 `load()`」，
  且**新增消费方应审慎**（当前仅 `entry._pet`）。
- **关联**：`configuration` spec「宠物模式配置」（既有条款，**无 spec 改动** ⇒ `skip_specs`）；
  代码 `src/core/configuration/manager.py`（`config_value` + `_flatten_by_specs`）/ `src/core/entry.py`（`_pet`）；
  接口 `03-interfaces/configuration-interface.md` §2.5；测试 `tests/test_entry.py`、`tests/test_configuration.py`、
  `doc/04-testing/test-cases.md`（TC-CONF-04/05）。
  ⇒ **末位调用方收口**：`config get` 亦迁至本通路（change `0078`／ADR-0075，账本 E22）。

## ADR-0068：出站白名单配置化（逗号分隔标量 / 校验期拒绝 / fail-closed 缺省不变）

- **背景**：`SandboxPolicy(host_allowlist=...)` 构造面早可注入，但**唯一生产构造点**
  `runtime.py` 写死 `SandboxPolicy()` ⇒ 白名单**恒空**、http 出站**永远被拒**：规格
  「沙箱执行颗粒度」场景「网络出站白名单」的**放行半边在生产不可达**（账本 B5；ADR-0057 §⑤
  已登记「白名单配置化记后续」）。与 E15（change `0068` 熔断阈值）同型：可注入但唯一调用点不传参。
- **决策**：
  ① **取值形态 = 逗号分隔标量**（键 `permission.sandbox.host_allowlist`）—— 本仓 yaml 子集解析器
  明文「不含列表」（`_parse_yaml_subset`），三面（CLI / env / yaml）统一为标量最省：
  **不动 yaml 解析与写回**；归一（去空白 / 去空项 / 保序去重 / 兼容全角逗号）由访问器
  `sandbox_host_allowlist()` 内的 `_split_hosts()` 完成；
  ② **非法条目校验期拒绝**（`validate_schema` → `_sandbox_errors`）：`check_outbound` 的实参是
  `urlparse(url).hostname`（**不含 scheme / 端口 / 路径**），故带这些的条目**永不匹配** ——
  静默忽略的后果是「配了却连不上」，与 E15「不静默兜底」同口径；非字符串取值同拒；
  ③ **缺省空白名单 = fail-closed 全拒**：本变更只把「恒空」变成「可声明」，安全姿态不动
  （回归用例 `test_unconfigured_production_policy_denies_all_outbound` 锁住）；
  ④ **访问器口径**：沿用 `circuit_breaker()` / `permission_mode()` 的「寄居 `extra` + 访问器」先例
  （读嵌套路径、只做归一不做二次兜底）—— **不**改走 `config_value()` 的单键原文通路（见 ADR-0067，
  那条通路供装配**前**前置判定用）；
  ⑤ **共用策略实例**：`MCPClient` 与 `SandboxManager` 仍共享 `build_runtime` 里那**一个** `SandboxPolicy`
  （change `0054` 的既有分发，本变更只接上构造参数）。
- **否决**：yaml 原生列表（须改解析器 / 写回，三面形态不一）；容错归一（自动剥 scheme / 端口 / 路径
  —— 掩盖输入错误，且带路径时「究竟想配哪个主机」不可判定）；把 `fs_allowlist` 一并配置化
  （无生产调用点需要，YAGNI）。
- **后果**：✅ 白名单成为**可用**能力（此前只有「拦截」可观测），远端 MCP 出站可经配置打开；
  ✅ 默认安全姿态逐位不变（缺省全拒）；✅ 拼写形态错误在启动期暴露而非运行期静默；
  ⚠️ 白名单**非密钥**（主机名），不涉及「只引用不读取」的密钥约束。
- **关联**：`permission` spec「沙箱执行颗粒度」（**MODIFIED**）；代码
  `src/core/configuration/manager.py`（ConfigSpec + `sandbox_host_allowlist` + `_split_hosts` +
  `_sandbox_errors`）/ `src/core/runtime.py`；
  接口 `03-interfaces/permission-interface.md` §4.1、`03-interfaces/configuration-interface.md` §2.6；
  模块 `02-modules/permission.md` §3.3；测试 `tests/test_permission_sandbox_config.py`、
  `doc/04-testing/test-cases.md`（TC-PERM-05/06/07）。

## ADR-0069：功能开关三面接线与取值统一（构建前归一 / 显式取值集合 / 不收进 ConfigSpec）

- **背景**：规格「功能开关（feature flag）」明文列三条输入通道，ADR-0065 亦称其「早已齐备」，但实测
  **两处不符**（账本 E20②、E23）：① CLI 面 `--feature NAME[=BOOL]` **零消费** —— 只解析进
  `args.feature`，而 `entry._cli_overrides` 只收 `ConfigSpec` 声明键 ⇒ flag 静默无效；
  ② 取值被 `bool()` **静默强转** —— yaml 子集解析器只认 `true/false/null/~`，故 `features.beast: off`
  落地为字符串 ⇒ `bool("off") is True` ⇒ **显式关闭被当成开启**（`"false"`、env `=banana` 同理）。
- **决策**：
  ① **取值集合 = 原生布尔 + `true/false`·`yes/no`·`on/off`·`1/0`**（大小写不敏感、忽略首尾空白），
  其余取值**校验期拒绝并阻断启动**。理由：`off`/`no` 是 YAML 1.1 惯用写法、用户意图**无歧义**，
  归一而非拒绝（对照 B5 白名单拒绝带 scheme/端口条目 —— 那里是**语义错配**，此处不是）；
  **已否决**「只收原生布尔」（与环境面/用户直觉不一致，且使 `--feature x=off` 与 yaml `x: off` 行为不同）。
  ② **归一位于构建前**（`_build_config` / `_merge_patch`，单一函数 `_normalize_features()`）：
  `features` 是**结构化段**，化为布尔后原文不可追溯 ⇒ 非法取值只有构建前可见 —— 与 `load()` 顶部
  `validate_map_to` 同属「构建前阻断」通道；`validate_schema` 继续只管**留存于 `extra`** 的校验。
  **已否决**把 `features` 挪进 `extra`（改结构化段契约）或把原文塞回 `AppConfig`（为校验污染数据模型）。
  ③ **CLI 面经覆盖层收集，不收进 `ConfigSpec`**：模块名是**开放集合**（`GATABLE_MODULES` 归组合根，
  配置层不认识模块名 —— ADR-0065 的分层决定）。`_cli_overrides` 产出 `features.<模块>` 覆盖键，
  `_apply_cli` 按点分路径写入 ⇒ 与 yaml/env 走**同一条**归一/校验路径。裸名按 metavar `NAME[=BOOL]`
  语义视为开；语法非法（缺名/缺值）在解析点拒（flag 形状错误 ≠ 取值不合法，后者归配置层判定）。
  ④ **env 面写入原文**（原就地 `value.lower() in (...)` 强转 ⇒ `CORE_FEATURES_X=banana` 静默为假），
  使「合法取值集合」只有**一处**定义；副作用是非法 env 取值由静默变**阻断启动**。
- **否决**：拼接纠错提示（`--feature pett=false` 提示 `pet`）—— 无需求，YAGNI。
- **后果**：✅ 规格的三条通道**真的**三面生效，CLI flag 可支配装配（端到端用例锁住）；✅ yaml
  `off`/`no`/`"false"`/`0` 由「静默为**开**」变为**关**（即用户本意）；✅ 拼写/取值错误在启动期暴露；
  ⚠️ 既有原生 `true`/`false` 与 env `=true` 行为**逐位不变**（回归用例锁住）；⚠️ `maybe` 之类由静默
  变为**阻断启动**（口径收紧，属「不静默兜底」一脉）。
- **关联**：`configuration` spec「功能开关（feature flag）」（**MODIFIED**）；代码
  `src/core/configuration/manager.py`（`_FEATURE_TRUE`/`_FEATURE_FALSE` + `_normalize_features` +
  `_apply_env`/`_build_config`/`_merge_patch`）/ `src/core/entry.py`（`_cli_overrides` + `_parse_feature_flag`）；
  接口 `03-interfaces/configuration-interface.md` §2.2；模块 `02-modules/configuration.md` §3.3；
  测试 `tests/test_feature_flag_faces.py`、`doc/04-testing/test-cases.md`（TC-CONF-06/07/08）。
- **登记后续**：env 前缀 `CORE_FEATURES_`（复数，实现）v.s. `CORE_FEATURE_<模块>`（单数，规格/文档）
  —— 对外可观测的破坏性重命名，记账 E24；**已由 change `0080` 关闭**（用户裁决：改规格/文档向实现靠拢，
  零代码变更，`configuration` spec MODIFIED「功能开关（feature flag）」+ 顺带补齐本 delta 归档时丢失的正文段）；`features` 段内**未知模块名**无告警（E20①）——
  与本条无关，且规格「配置校验与生效」明文限告警于**顶层段名**，补齐须先改规格。

## ADR-0070：MCP Server 模式 stdio 事件循环（循环归 server / 错误分层 / `core.` 命名空间 / 共享协议常量）

- **背景**：规格「MCP Server 模式」场景「stdio 本地挂载」要求外部 agent 拉起本 server 并握手调工具，
  `MCPServer` 的方法级行为也早已齐备，但**没有事件循环**把 JSON-RPC 接到方法上（账本 B3）：
  `serve()` 只绑定连接即返回，CLI `mcp serve` 落「已识别，尚未接线」⇒ 场景在生产**不可达**。
  同批一手核实还发现**文档已写、代码缺席**的两处暴露面契约（`07-mcp-server` §4 / 接口 §6 均写
  `core.<tool>`）：`list_tools` 吐**裸** `tool_id`；`mcp.*` 远程工具可被**原样再暴露**（二级代理）。
- **决策**：
  ① **事件循环归 `MCPServer.serve_stdio(endpoint, *, stdin, stdout)`**：server 侧 stdio **就是本进程的
  流**，不存在「到远端的传输对象」（`StdioTransport` 是 client 侧拉起子进程用的，方向相反）；
  `stdin`/`stdout` 可注入 ⇒ 循环行为可**纯内存**验证。既有 `serve(transport, endpoint)` 签名不动
  （接口 §6 已文档化），改为委托 `_bind` —— http 方向的事件循环将来在它之上接入。
  **已否决**在 CLI 里构造 `StdioTransport()` 传给 `serve`（语义错误：client 传输搁到 server 侧）。
  ② **错误分层**：协议层走 JSON-RPC `error`（`-32601` 未实现 / `-32603` 内部异常），工具层走成功应答里的
  `CallResult`（`PERMISSION_DENIED` 等）。越权是**业务结论**而非协议故障，客户端应能读到码并据此决策；
  与 client 侧 `call_tool` 把 payload 包进 `CallResult(ok=True, data=payload)` 的既有形状一致。
  `_respond` **永不抛**：单条请求的任何异常（含提供者抛错、应答不可序列化）降级为该 `id` 的错误应答，
  循环继续 —— 对应规格 SHALL「单条请求异常不得终止事件循环」。
  ③ **暴露面三件套**：对外名 `core.<tool_id>`；白名单**接受裸名与带前缀两种写法**（用户最自然的写法是照
  `tools/list` 应答抄名字，只认裸名会「配了却不匹配」且静默 —— 同 B5 的「配了却连不上」）；`mcp.*`
  **过滤**（禁二级代理，防两个 core-agent 相互挂载递归放大暴露面）。
  ④ **协议版本常量同源**：`PROTOCOL_VERSION` 落 `core.mcp.models`（client 与 server 共同依赖的最小模块），
  弃用 client 侧私有 `_PROTOCOL_VERSION`。握手**判定在 client、应答在 server**，两处各写一份字面量是典型漂移面。
  ⑤ **沿用仓内 wire 形状**：`tools/list` **裸列表**、`tools/call` **`CallResult` 直出** —— 与 `MCPClient` /
  `FakeTransport` / 既存 echo server 三方一致（change `0054` 约定），本变更主题是**接线**，不擅自改契约。
- **后果**：✅ 规格场景「stdio 本地挂载」在生产可达，端到端用例用**本仓自己的 client** 拉起真实子进程锁住
  （握手 → 发现 → 真读文件 → 越权拒绝）；✅ 对外名与本地名 / 远程名三方隔离，二级代理递归被关；
  ⚠️ **已知偏离标准 MCP envelope**（`{"tools": [...]}` / `{"content": [...], "isError": ...}`）⇒ Claude Code /
  Cursor 等第三方客户端**直接挂载尚不可用**（账本新行，对齐标准属独立变更 —— **已由 ADR-0072 对齐**）；⚠️ 默认暴露面沿用既有
  `_is_readonly`（coeffects 不含 `write`）粗粒度启发式 ⇒ `tools.delegate` / `tools.web_fetch` 亦在默认暴露面
  （账本新行，是否收窄待裁决）。
- **关联**：`mcp` spec「MCP Server 模式」「工具暴露与白名单」（**MODIFIED** + 4 新场景）；代码
  `src/core/mcp/server.py`（`serve_stdio` / `_respond` / `_dispatch` / `_encode` / `_bind` / `_bare_name`）/
  `src/core/mcp/models.py`（`PROTOCOL_VERSION`）/ `src/core/mcp/client.py` / `src/core/entry.py`
  （`_mcp` / `_mcp_serve` / `_mcp_whitelist` + `mcp serve --whitelist`）；
  接口 `03-interfaces/mcp-interface.md` §6；模块 `02-modules/mcp.md` §3.5；方案 `07-mcp-server/mcp-server.md` §9；
  测试 `tests/test_mcp_server_stdio.py`、`doc/04-testing/test-cases.md`（TC-MCP-07/08/09）。

## ADR-0071：MCP 端点注册表与装配期注册（状态非配置 / 落盘即安装 / 稳定命名 / 降级不阻断）

- **背景**：`mcp` 规格「MCP Server 安装与移除」五条场景全部以 CLI 为锚（`WHEN 执行 mcp add`），
  而 `entry._mcp` 落到「已识别，尚未接线」兜底 ⇒ 场景在生产**不可达**（账本 B4）。安装管线（change `0054`）
  早已齐备，缺的是三件：① CLI 接线；② **跨进程持久化**（CLI 是一次性进程，`PluginInstaller._assets`
  随之蒸发，`mcp add` 的成果无处可寻）；③ **稳定工具命名**（`connect` 用 `uuid4().hex` 作 `handle_id`，
  工具名 `mcp.<uuid>.<tool>` 每次装配都不同，与模块文档「包装为 `mcp.<server>.<tool>`」不符）。
- **决策**：
  ① **端点注册表是状态不是配置**：落 `$CORE_STATE_DIR/mcp-endpoints.json`（同 `checkpoints.jsonl` /
  `pets.json` 约定，**原子写** tmp + `os.replace`，同 change 0062）。端点名是**开放集合**，无法进
  `ConfigSpec`（同 `features.<模块>` 之于 `GATABLE_MODULES`）；且它带**连接句柄语义**（由 `mcp add` 写入），
  不是用户声明的配置。**已否决**「加一个 `mcp.endpoints` 配置段」（把运行期安装伪装成静态配置）。
  ② **先连通验证再落盘**：`mcp add` 走既有安装管线（连接 + 握手 + 适配注册），成功才持久化
  —— 否则此后每次装配都徒劳重试一个打不通的端点（同 B5「配了却连不上」的静默失配之害）。
  ③ **稳定命名**：命名安装以**安装名**作 `handle_id`（`mcp.<名>.<工具>` 跨进程稳定）；匿名安装（无 `--name`
  且无法派生）沿用 uuid。派生顺序 `--name` > URL 主机名 > 命令基名；**重名拒绝**（`ENDPOINT_NAME_CONFLICT`）
  而**非静默覆盖** —— 覆盖会让「我以为装的是 A」与「实际连的是 B」错位。
  ④ **装配期连接注册 + 降级**：组合根读回注册表，逐端点经**同一安装管线**连接注册；单个端点不可达
  **只告警跳过**（fail-soft），坏端点不得让整个系统不可用；注册表损坏 / 条目残缺同样告警降级。
  ⑤ **`mcp remove` 对称**：先经安装管线卸载（释放连接 / 子进程），**再**删记录；删记录失败前不破坏已装态。
- **后果**：
  - 规格五条场景 + 新增四条（跨进程持久化 / 装配期注册 / 不可达降级 / 重名拒绝）在生产可达，
    端到端由真实子进程（`core-agent mcp add` → echo server）验证。
  - **`mcp list` 不连接**：列表只呈现配置面事实（端点名与形状），不隐式建连。
  - **无跨进程锁**：注册表读写假定同一时刻只有一个 CLI 写入者（安装是低频人工操作），
    未引入文件锁；并发 `mcp add` 理论上可丢更新（已知接受项）。
  - **`--command` 的 argparse dest 陷阱**：`mcp add --command C` 的 dest 曾与顶层
    `add_subparsers(dest="command")` 冲突，把 `args.command` 覆盖成 `None` ⇒ `mcp add` **静默落进 REPL**
    并阻塞。已改 dest 为 `mcp_command`/`mcp_args`（同型冲突的排查线索记此）。
- **关联**：`mcp` spec「MCP Server 安装与移除」（**MODIFIED** + 7 新场景）；代码
  `src/core/mcp/endpoints.py`（`mcp_endpoints_path` / `EndpointRecord` / `MCPEndpointRegistry` /
  `default_endpoint_name`）/ `src/core/mcp/client.py`（`connect(handle_id=)`）/ `src/core/mcp/errors.py`
  （`ENDPOINT_NAME_CONFLICT`）/ `src/core/runtime.py`（装配期读注册表）/ `src/core/entry.py`
  （`_mcp_add` / `_mcp_list` / `_mcp_remove`）；
  接口 `03-interfaces/mcp-interface.md` §7；模块 `02-modules/mcp.md` §3.6；测试 `tests/test_mcp_endpoints.py`、
  `doc/04-testing/test-cases.md`（TC-MCP-10）。

## ADR-0072：MCP 标准 envelope 双向对齐（两侧最小对齐 / 载荷 JSON 恒编码 / 裸形状兜底 / 真机双向验收）

- **背景**：`mcp` 规格「MCP Server 模式」逐字点名 Claude Code / Cursor 可直接挂载本 server，
  而一手核实**双向都不通**（账本 B6）：本 server 的 `tools/list` 应答是**裸列表**、`tools/call`
  是**序列化 `CallResult` 直出**（ADR-0070 ⑤ 沿用 change `0054` 的仓内三方约定）；本 client 的
  `initialize` params **为空**（对端 zod 校验直接回 `-32603`），且 `RemoteTool(**item)` 遇标准应答的
  **容器键**会逐字符迭代、遇**厂商扩展字段**（`claude mcp serve` 的 tool 对象带 12 个扩展键）会 `TypeError`。
- **决策**（以 `claude mcp serve` 的**实测形状**为基准）：
  ① **两侧最小对齐**：只改 wire 形状（server 应答 + client 解析），不动 Python 侧领域接口
  （`MCPServer.call_tool` 仍返回 `CallResult`）⇒ `test_mcp.py` 领域断言零改动。
  ② **载荷 JSON 恒编码**：`tools/call` 的 `content[].text` **总是** JSON 编码（即使载荷已是 str），
  保证 client 侧「解码即还原」的往返保真（否则 `"123"` 之类会被解码成 int 而漂移）；「是不是错」
  由 `isError` 承载，**不**引入 `structuredContent`（属 `2025-06-18`，本端协议版本 `2024-11-05`，引入即版本越界）。
  ③ **裸形状兜底**：client 侧标准优先、**旧式裸列表 / 裸对象原样承载** ⇒ 仓内两个 echo server 子进程
  夹具不作废，成为「旧服务端不被打破」的真实回归样本（否决「只认标准」）。
  ④ **协议版本不放宽**：`claude mcp serve` 应答 `2024-11-05` 与本端 `PROTOCOL_VERSION` 逐字相同
  ⇒ 既有严格比对保留（放宽反丢语义）。
  ⑤ **命名不放宽**：对外名仍 `core.<tool_id>`（规格「工具命名空间隔离」明文要求）；能否被第三方
  接受由**真机验收**判定，不先验改名。
- **后果**：✅ 规格场景「stdio 本地挂载」对第三方客户端成立（**真机双向验收**：`claude mcp add` 挂本
  server 后 `claude mcp list` 报 `✔ Connected`；反向 `core-agent mcp add "claude mcp serve"` 成功并发现
  对端 20 工具，此前为 `-32603`）；✅ server 应答字面为标准信封，`isError` 携 `{"code","error"}` 且
  **往返后结构化错误码可还原**；⚠️ **远端 JSON-RPC 错误码未映射**：`StdioTransport._await` 把一切远端
  `error` 包成 `MCP_UNAVAILABLE` ⇒ 对端「工具不存在」（`-32603`）在本端表现为 `MCP_UNAVAILABLE`
  而非 `MCP_TOOL_NOT_FOUND`（粒度不足但**不误导**，转出为账本新行）。
- **关联**：`mcp` spec「标准 MCP 互操作（双向）」（**ADDED** + 7 场景）；代码
  `src/core/mcp/server.py`（`_envelope` / `_dispatch` / `_serialize_call`）/
  `src/core/mcp/client.py`（`_handshake` / `_unwrap` / `_parse_call_result`）/ `src/core/mcp/transport.py`
  （`FakeTransport` 标准形状）；
  接口 `03-interfaces/mcp-interface.md` §5/§6；模块 `02-modules/mcp.md` §4；方案 `07-mcp-server/mcp-server.md` §9；
  测试 `tests/test_mcp_standard_envelope.py`、`doc/04-testing/test-cases.md`（TC-MCP-11）。

## ADR-0073：MCP 默认暴露面收窄（安全 coeffect 白名单 / 补声明委托 coeffect / 白名单语义不动）

- **背景**：`mcp` 规格场景「默认最小暴露」写「写/删除/**敏感**工具默认不暴露」，而实现
  `server._is_readonly`（coeffects 不含 `write`）只实现了「写/删除」，**漏掉「敏感」**（账本 B7）：
  生产工具源下默认暴露面含 `tools.web_fetch`（`network:outbound`，可外发数据 / 拉 arbitrary URL）
  与 `tools.delegate`（`coeffects=[]` **漏声明**，实为驱动子 Agent loop）⇒ 第三方客户端默认挂上即可出网与驱动子 loop。
- **决策**：
  ① **判据改为安全 coeffect 白名单**：默认出 ⟺ `set(coeffects) ⊆ {"filesystem:read"}`（**空集通过** ——
  coeffect 是工具的副作用**契约**，未声明即承诺无副作用）。函数更名 `_is_readonly` → `_is_default_exposed`。
  **已否决**「`_is_readonly` + 硬编码 `{"tools.delegate"}` 拒绝集」（让 MCP 层认识具体工具名 = 跨层耦合，
  且对下一个漏声明的跨边界工具再犯）。
  ② **给 `tools.delegate` 补声明 `agent:delegate`**：它本就驱动子 loop，只是 `coeffects=[]` 没写；补上后
  判据**结构化**识别委托类工具，无需 id 特判。组合根注册该 coeffect ⇒ 运行期行为不变，新增的是**可见性**。
  **已否决**「给 `ToolDef` 补风险分级字段」（现有 coeffect 已能表达跨边界能力，再引一层分级是重复真源）。
  ③ **白名单语义不动**：显式 `--whitelist` 仍可开放任意工具（含跨边界者）—— 收窄只改**默认面**。
- **后果**：✅ 默认面 = {`tools.file_read`, `tools.list`}（纯本地只读），`web_fetch`/`delegate` 默认不可见，
  与规格「只读类工具 + 敏感工具不暴露」一致；✅ 白名单路径 / `call_tool` 越权 / 命名空间 / 二级代理过滤**零改动**；
  ⚠️ **空集=只读的信任面**：留 `coeffects=[]` 的工具默认可见 —— 这是契约（未声明副作用即无副作用），
  delegate 的问题是**漏声明**而非契约缺陷；假将来插件工具谎报空 coeffect 属插件契约问题（另论）。
- **关联**：`mcp` spec「工具暴露与白名单」（**MODIFIED** + 新场景「默认面排除跨边界工具」）；代码
  `src/core/mcp/server.py`（`_DEFAULT_EXPOSED_COEFFECTS` / `_is_default_exposed`）/ `src/core/runtime.py`
  （`tools.delegate` 的 `agent:delegate` 声明与 resolver 注册）；
  接口 `03-interfaces/mcp-interface.md` §6；模块 `02-modules/mcp.md` §4；方案 `07-mcp-server/mcp-server.md` §9；
  测试 `tests/test_mcp_default_exposure.py`、`tests/test_phase13.py`；`doc/04-testing/test-cases.md`（TC-MCP-12）。

## ADR-0074：远端 JSON-RPC 错误码映射（tools/call 归调用被拒 / 其余按标准码 / 原始码保留）

- **背景**：账本 **B8**。`StdioTransport._await` 把**一切**远端 JSON-RPC `error` 包成
  `MCPError(MCP_UNAVAILABLE)` ⇒ 「方法未实现」「参数非法」「工具不存在」「内部异常」塌缩为同一本地码。
  一手实测（change `0075`）：`claude mcp serve` 对未知工具回 `{"error":{"code":-32603,"message":"Tool
  no_such_tool not found"}}`，本端 `call_tool` 归 `MCP_UNAVAILABLE` —— 模型无法区分「工具名写错」（当场可
  自纠）与「远端挂了」（该熔断重试）。属错误**语义丢失**。
- **决策**：
  ① `src/core/mcp/transport.py` 增模块级纯函数 `map_remote_error(method, error) -> MCPError`，`_await` 改调它；
  ② **`tools/call` 的 JSON-RPC 错误 → `MCP_TOOL_NOT_FOUND`**：MCP 约定工具**执行**失败走成功应答里的
  `isError` 结果信封（本端 server 侧即如此），故该路径上的 JSON-RPC 错误 = **调用本身被拒**（未知工具 /
  非法参数）；
  ③ **其余方法**按标准码：`-32700`/`-32600`/`-32601`/`-32602` → `MCP_PROTOCOL_MISMATCH`，`-32603` 与未知码 →
  `MCP_UNAVAILABLE`（`-32601` 与本端 server 侧对未知方法回 `-32601` 对称）；
  ④ 原始远端码与消息**保留**在错误文本（`远端错误: <code> <message>`）；
  ⑤ 映射落点唯一（`_await`）—— `client._call` 让传输层 `MCPError` 直通，无需动 client。
- **已否决**：**按码判（`-32602`→工具不存在、`-32603`→保持 UNAVAILABLE）** —— 实测对端对未知工具回 `-32603`
  （标准里的 Internal error），按码判会把本变更要修的用例继续漏掉；且 `-32602` 在 `tools/call` 上同样可表示
  未知工具，按码判是伪精确。**消息文本启发式**（按 `message` 含 "not found" 判）—— 依赖本地化 / 厂商措辞，
  且方法上下文已给出确定性判据。**新增本地错误码** —— 现有码集已能表达，新增码波及 `MCPErrorCode` 对外契约。
- **后果**：✅ `tools/call` 的未知工具/非法参数归 `MCP_TOOL_NOT_FOUND`（可自纠语义），协议层问题归
  `MCP_PROTOCOL_MISMATCH`，仅对端内部问题归 `MCP_UNAVAILABLE`；✅ 映射为**可测纯函数**（表驱动单测 + 真子进程
  端到端）；✅ client/server/命名空间/白名单/http 传输**零改动**。
  ⚠️ `tools/call` 归一只看方法不看码 —— 若某服务端把「工具内部异常」错报为 JSON-RPC 错误（而非 `isError`
  结果），会被记成「工具不存在」；属对端**违反 MCP 约定**，本地码仍 `ok=False`，原始码保留于文本。
- **关联**：`mcp` spec「调用转发与错误隔离」（**MODIFIED** + 新场景「远端工具不存在映射为工具不存在」
  「远端方法未实现映射为协议不匹配」）；代码 `src/core/mcp/transport.py`（`_JSONRPC_TO_LOCAL` /
  `map_remote_error`）；接口 `03-interfaces/mcp-interface.md` §8；模块 `02-modules/mcp.md`（故障隔离段）；
  测试 `tests/test_mcp_stdio.py`；`doc/04-testing/test-cases.md`（TC-MCP-13）。

## ADR-0075：`config get` 接入配置链 yaml 层（复用 `config_value` / 构造前移 / 语法层不动）

- **背景**：账本 **E22**。`entry._config` 的 `get` 分支用 `resolve(args.key, cli=, env=)` —— `yaml=`
  缺省为空映射 ⇒ `config get` **永远看不到 config.yaml**，配置里的非缺省值被显示为缺省（或 `(未配置)`）。
  与 E21 同型（同一处 `resolve` 漏参），并与同进程 `load()`（含 yaml 层）**判据不一致**。
  规格「配置源与分层」明文优先级链 CLI > env > config.yaml > 默认值 ⇒ 「规格要求 X、实现没有」型。
- **决策**：
  ① `config get` 改用 **`ConfigManager.config_value(key)`** —— 与 `entry._pet` 门控**同一通路**
  （ADR-0067：只读单键 / 不校验不缓存 / 缺文件容错 / 键名经单一真源回填），**不另起解析**；
  ② `ConfigManager` **构造前移**至 `_config` 函数开头（`show`/`set` 共用同一实例）；
  ③ 随之孤儿化的 `resolve` 导入**删除**（`entry.py` 内已无第二调用方）；
  ④ **不动语法层** `resolve` 的 `yaml=` 缺省（仍为空映射）—— ADR-0067 已否决「自动读盘」，
  语法层不该有 I/O 副作用；
  ⑤ **无 spec delta**（规格既有条款已覆盖，`skip_specs`，同 change `0070`）。
- **已否决**：在 `_config` 内自读 yaml（第二条解析真源，违反规格「禁止另起解析」）；
  顺手改 `config show/validate/set`（本就走 `load()`，无缺陷）。
- **后果**：✅ 单键读取与整体装配**同源**，优先级链一致；✅ 无配置文件机器上行为不变（缺文件容错）；
  ⚠️ `config get` 的**输出会变**（此前漏 yaml 显示的缺省 → yaml 真值）—— 这正是修复目标；
  既有 `test_config_get_default` 已改 hermetic（显式 `--config <不存在>`），不随开发机 / CI 漂移。
- **关联**：`configuration` spec「配置源与分层」（既有条款，**无 spec 改动** ⇒ `skip_specs`）；
  代码 `src/core/entry.py`（`_config`）；接口 `03-interfaces/configuration-interface.md` §2.5；
  产品 `00-product/user-guide.md`（单键读取）；测试 `tests/test_entry.py`；ADR-0067（通路来源）。

---
## ADR-0076：pet 通知三环接线（生产者落 `wake()` 收尾 / 投递点由组合根收口 / 缺省 sink 走 stderr）

- **背景**：账本 **E16**。一手核实「比记载严重 —— 通知链路三层全断」：① **生产者**——
  `PetSession._notifier` 只赋值、全程零调用，`report()`/`surprise()` 亦零调用方（含测试）；
  ② **通道**——组合根 `AsyncNotifier()` 不传 `channel` ⇒ `flush()` 恒返回 0、队列永不清；
  ③ **投递点**——`flush()` 全仓零调用方。即 `pet-notify` 是**孤立模块**（单测自证类可用，生产三处皆空）
  ⇒ 规格「Pet Notification」的「异步投递」未满足。账本自述前置「IM 通道为依赖」经核实**不存在**
  （`IMGateway` 在 `src/` 零生产装配 + im 规格「分平台接入」要求真实平台 Provider ⇒ C 类真后端）。
- **决策**：
  ① **生产者落 `wake()` 收尾**，判据复用既有 `report()` 的反馈周期（抽 `_on_feedback_cycle()` 单一真源）
  —— 不新造文案与频度策略，只把既有产出真的投出去；`report()` 保持纯格式化契约（不自身发通知）。
  ② **投递点由组合根收口**：注入面签名**一字不动**（仍是 `notifier: Callable[[str], None]`），
  组合根把「`notify` 入队 + `flush` 投递」收成单一可调用体 `_pet_notify` 注入
  `PetManager.factory` 与 `PetActivator`；生产者唯一调用点在 `wake()` 末 ⇒ 两步相邻执行，
  等价于「唤醒收尾 flush」。`AsyncNotifier` 的「notify 只入队、不阻塞」语义原样保留。
  ③ **缺省通道 = stderr 一行**（`_pet_notification_sink`，主人可见的观测面、不污染 stdout 机读输出）；
  真实通道（IM 网关等）由宿主注入替换。
  ④ **无 spec delta**（规格既有三处明文已覆盖，`skip_specs`，同 change `0070`/`0078`）。
- **已否决**：让 `report()` 自身发通知（破既有纯格式化契约）；每次唤醒都投递（绕开 `feedback_period`
  的反馈节拍语义 + 刷屏）；`surprise()` 同拍投递（它是「主动执行」的动作而非报告，无偏好时仍返回
  「已帮你安排」通用文案，投出即**谎报**）；给 `PetSession` 加第二个注入参数或改注入类型为对象/
  Protocol（协作者拆参、契约变更、三处注入面变大）；`PetSession` 内直接 `channel(msg)`（绕过
  `AsyncNotifier` 队列契约）；`Runtime` 加 `pet_notifier` 字段由宿主 flush（当前**无宿主驱动 `wake()`**，
  该路径今日不可达）；缺省 sink 走 `Tracer`（`TraceEvent` 是 trace 作用域 span 遥测，宠物通知无 trace
  上下文，硬造 `trace_id` 污染遥测域并使 `replay()` 出现无来源事件）；走 `logging`（全仓 `src/` 零用法）；
  缺省 `channel=None`（即现状，规格仍未满足）；新增配置项 `pet.notify_channel`（YAGNI，宿主替换是代码级注入）。
- **后果**：✅ 规格「异步投递」在无宿主时亦可达（一旦 `wake()` 被驱动）；✅ 既有用例零回归
  （无任何测试向 `PetSession`/`PetActivator` 传 `notifier=`）；✅ 注入面与接口文档签名不变；
  ⚠️ 缺省 sink 写 stderr，仅反馈周期命中时产出（`feedback_period` 缺省 5）⇒ 不刷屏。
- **关联**：`pet-mode` spec「Pet Notification」/「Pet Safety Bounds」/「Pet Session Runtime Wiring」
  （既有条款，**无 spec 改动** ⇒ `skip_specs`）；代码 `src/core/pet/core/session.py`（`wake`/`_notify_owner`）、
  `src/core/runtime.py`（`_pet_notification_sink`/`_pet_notify`）；接口 `03-interfaces/pet-mode-interface.md`
  §1/§5；模块 `02-modules/pet.md`；测试 `tests/test_pet_core.py`、`tests/test_pet_wiring.py`。
- **转出（另立账本项）**：安全越界通知（`SafetyBounds`/`Explorer` 注入但零消费，需安全强制执行路径）；
  `surprise()`/`MicrotaskRunner` 零调用方；`IMGateway` 零生产装配；无宿主驱动 `wake()`。

---
## ADR-0077：pet 安全边界强制执行（专属 loop / 越界即本轮终止不楔死 / 词汇表订正为真实 id）

- **背景**：账本 **E25**。一手核实「比记载严重」：① `Explorer`/`SafetyBounds` 由组合根注入 `PetSession`
  后**零读取点**（规格 R11/R12 明文要求强制，实现只注入不消费）；② 宠物**跑在主 loop 上**
  （`pet_loop = cast(LoopPlugin, loop)`）⇒ 一次唤醒可调用主 loop 的**全部**工具，边界无一处在路径上；
  ③ 两套词汇表（`file.read`/`web.search`/`memory.read`；`file.write`/`git.push`/`rm`）**与真实工具 id 对不上**
  ⇒ 即使今天接线也一条都匹配不上。
- **决策**（三项均经用户裁决）：
  ① **专属 loop 真强制**：组合根新增 `_pet_tools()`（**受限 `ToolProvider`**：只注册 `Explorer.available()`
  白名单内的真实工具）+ `_pet_loop()`（**专属 `DefaultLoop`**，`middlewares=[build_safety_middleware(...)]`）
  —— R11 由**注册面收窄**落地（未注册 ⇒ loop 结构化拒绝，fail-closed by construction，且模型看不到越界工具），
  R12 由 before 中间件落地。先例：`_agent_loop`/`_beast_loop` 均为专属 loop。
  ② **「越界即暂停」= 本轮阻断 + 通知主人，会话保持 `ACTIVE`**：终止 Action 与 loop 既有 `decline()` 路径
  **同构**（`observe()` 见 `data["reply"]` 即 `ctx.finish()`），不新增 loop 语义；**不** `suspend()`
  （无 `resume()` 调用方 ⇒ 永久楔死）、**不**转 `BACKOFF`（把越界当故障，语义过重）。规格原文「宠物暂停」的
  读法由此**钉死进规格**（本 change 的 MODIFIED requirement），避免将来再记一条「规格说暂停、代码没暂停」。
  ③ **词汇表订正为真实 id**：`Explorer` 缺省清单 → `tools.file_read`；`SafetyBounds` 不可逆集 →
  `tools.file_write`/`file_patch`/`code_run`/`install`/`uninstall`；「只读优先」由 `read` 前缀启发式改为
  **只读白名单**（真实 id 无此前缀，启发式必然失效）。**不做** id→旧词汇映射层（两套词汇长期并存即新真源）。
- **半径**：`allowed_prefixes` 语义不变，但**仅当 `target` 非空**时判定（真实工具参数名各异 ⇒ middleware 取
  `path`/`file`/`url`/`target` 首个命中键；取不到不判半径，避免「无目标动作一律被拒」）；组合根缺省
  `[Path.cwd()]`，构造面可替换。
- **spec delta**：`pet-mode` MODIFIED「Pet Safety Bounds」（保留标题/正文/既有场景，正文追加「暂停」实现口径，
  并新增场景「越界阻断不楔死会话」）。
- **已否决**：共享 `ConstraintsChain` 熔断给 pet loop（单实例熔断态会被宠物流量污染，且本变更无此需求）；
  `SafetyBounds` 加 `ConfigSpec` 键（构造面可注入即够，YAGNI）；给宠物注册 `tools.list`/插件管理工具
  （那是插件管理面，非「探索」）；在 middleware 做旧词汇映射；给宠物 loop 接技能/JEV 路由（pet 任务与
  结晶链路无关）；每宠一 loop（现状共享，多宠隔离已由会话/任务队列/人格承担）。
- **后果**：✅ R11/R12 在路径上真强制；✅ 宠物可用工具面**收窄**（**行为变更**，proposal/接口/模块三处显式登记）；
  ✅ 单测与文档词汇表同批订正；⚠️ 宠物 loop 与主 loop 各自独立（工具面/中间件不共享）。
- **关联**：`pet-mode` spec（R11「Exploration Toolset」/ R12「Pet Safety Bounds」/「Pet Session Runtime Wiring」）；
  代码 `src/core/runtime.py`（`_pet_tools`/`_pet_loop`）、`src/core/pet/safety/safety.py`、`…/safety/middleware.py`、
  `src/core/pet/explore/explorer.py`、`src/core/pet/core/layers.py`；接口 `03-interfaces/pet-mode-interface.md` §5.1；
  模块 `02-modules/pet.md` §3.5；测试 `tests/test_pet_safety.py`、`tests/test_pet_safety_guard.py`、
  `tests/test_pet_explore.py`、`tests/test_pet_wiring.py`；ADR-0076（通知通道）。
- **转出**：无新开账本行（E26/E27/E28 各自成行）；E28 语义更新 —— 一旦被宿主驱动，唤醒不仅投递通知（E16），
  且受安全边界约束（本变更）。

---

## ADR-0078：宿主驱动的唤醒节拍（新 CLI `pet run` / 驱动薄壳 / 故障隔离）

- **背景**：账本 **E28**。`0065`（E17）裁决「周期触发由宿主驱动、内核不自建 daemon」，但一手核实
  三入口**无一调用 `wake()`** —— `pet gather` 只激活并打印、`ui serve` 不调、`/pet` 同。故 pet 自治循环
  与通知三环（`0079`/`0081`）**在生产仅在有人手动驱动时才可达**，而没有任何宿主在驱动：
  又一例「接线已备、驱动缺席」。
- **决策**（均经用户裁决）：
  ① **驱动落点 = 新 CLI `core-agent pet run [--interval S]`**，**不做** `ui serve` 内置后台线程 ——
  驱动者 = 用户**显式启动**的前台进程（与 `0065`「内核不自建 daemon」相容：不是内核偷偷起线程，
  而是宿主**显式常驻**）；WebUI 一开就让宠物在后台真调 LLM / 真跑工具，是「用户没要求的动作却发生了」，
  与「一切副作用可逆、可解释」相悖；且无 UI 的部署（纯 CLI / 服务器）也须能驱动。
  接口 §5 那句「能承载常驻驱动的只有 `ui serve`」是**当时快照**，本 change 一并订正为「`ui serve` 或
  `pet run`」。
  ② **驱动薄壳**：`PetWakeDriver(sessions, *, sleep=time.sleep)` → `tick()` 逐会话唤醒、返回结构化
  `WakeOutcome`（库层**不打印** ⇒ 呈现与退出码归 CLI）；`sessions` 是**可调用体**（`PetManager.list`）
  每轮**重取** ⇒ 驱动期间新注册的宠物自动纳入；`sleep` 可注入 ⇒ 节拍测试**确定性**
  （先例：`0052` 给 `CircuitBreaker` 注入 `clock`），故**不**为测试加 `--oneshot`/`--iterations` 生产表面。
  ③ **故障隔离**（规格 R8「A 宠物异常不影响 B 宠物」）：让行/退避/未激活（`PetError`）= **预期态静默跳过**
  （让行是设计中的常态，逐轮刷 stderr 即噪音）；其他异常 ⇒ `FAILED` 记因并**继续其余宠物**
  （对齐 B4「单端点不可达只告警跳过」口径）。
  ④ **`--interval` 不进 `ConfigSpec`**：它是**宿主命令的运行参数**（同 `ui serve --host/--port`），
  配置面记「事实」（`pet.enabled`/`persons_dir`），这是「这次怎么跑」。
  ⑤ **无注册会话 ⇒ 提示三入口激活 + 退出 0**，**不自动造宠物**（激活归三入口，避免第二真源）。
- **实现细节**：`--interval` 从 `rest` 提取（`pet` 子命令用 `argparse.REMAINDER` 收自由文本，旗标与任务词
  同处 `rest` —— 同既有 `--name`/`_split_pet_name` 先例，不改 parser 结构）；非法 / 非正 / 缺值 ⇒
  用法错误 + 退出 1；`KeyboardInterrupt` 由 CLI 捕获并打印「已停止驱动」。**驱动不进 `runtime.py`**：
  组合根只装配、不驱动（驱动是宿主行为）。
- **已否决**：`ui serve` 后台线程（线程生命周期 + 新配置键 + 隐式副作用 + 无 UI 部署仍不可驱动）；
  `pet.wake_interval_s` 配置键；自动激活 / 缺省 persona 造宠物；`--oneshot`/`--iterations`/`--max-ticks`；
  让 `wake()` 内部吞异常返回结果对象（改领域语义以迁就驱动，方向反了）。
- **后果**：✅ pet 自治循环 + 通知三环 + 安全边界在生产**首次可达**；✅ 纯 CLI 部署可驱动；
  ✅ 规格中性（pet-mode 规格无「宿主须为哪个入口」条款，本变更是既有条款的宿主侧落地）；
  ⚠️ 驱动是**前台**进程，脱离终端存活需用户自行放进 supervisor / tmux。
- **关联**：账本 E28；`0065`（E17）；代码 `src/core/pet/core/driver.py`、`src/core/entry.py`（`_pet_run`）、
  `src/core/pet/core/__init__.py`；接口 `03-interfaces/pet-mode-interface.md` §5 / §5.2；
  模块 `02-modules/pet.md` §3.6 / §4；测试 `tests/test_pet_driver.py`、`tests/test_entry.py`（TC-PET-05）；
  ADR-0077（安全边界）。
- **转出**：无新开账本行；E28 关闭后 E 类余 E5 / E20① / E26 / E27。

---
## ADR-0079：自动课程（目标生成与调度 / 先验只破并列 / 显式目标直采）

- **背景**：账本 **E5**「主 Agent 自动迭代内部模块」。一手核实：进化闭环**四阶段与两个驱动面都已接线**
  （`EvolutionWorker.maybe_run` → `run_cycle` → 诊断/提案/验证门/留出评测），缺的不是闭环本身，而是
  **「这一轮该迭代谁」**——`Diagnoser` 只有单一信号（本批失败计数）且**并列即弃权**（转人工、无归因），
  跨轮**无记忆**（刚发布、仍在观察期的插件照样被再次选中）。又一例「闭环已备、目标选择缺席」。
- **决策**（落点与信号策略均经用户裁决）：
  ① **落点 = 引擎侧目标生成**（`evolution/curriculum.py`）。目标选择是进化引擎的**职责**；loop 侧会让
  `loop → evolution` 依赖方向倒挂且 CLI 入口无法复用，CLI 侧则只有显式入口有课程、宿主节拍（生产默认）
  拿不到 ⇒ 「自动」落空。两个驱动面保持「只给机会」的薄壳语义不变。
  ② **信号策略 = 结构化信号排序建议 + 显式目标入口**。**不用记忆自由文本**：`MemoryEntry.importance`
  缺省恒为 0、无结构化教训标记 ⇒ 只能做关键词启发式（排序不可解释、随文案漂移）。**不用 LLM**：非确定、
  无凭据不可验证、token 无界、失败模式是**静默编造**。故信号面封闭为引擎内部结构化数据三层：
  失败计数（定序）/ 观察期目标（降权）/ 待确认候选（降权）。
  ③ **先验，不是裁决**。议程作 `Diagnoser` 的 `plugin_signals` 并入分数表，权重**按位次几何递减**
  （首位 0.5、其后 0.25/0.125…）——**恒 < 1.0**，而每条失败证据计 1.0 ⇒ **任一插件多一条证据即压过先验**；
  先验的**唯一**效果是**解并列**（今天并列 = 弃权 = 转人工）。**降权同理**：只改并列顺序，不压证据。
  ④ **显式目标是指令**（`evolve run --goal X`）：人直接说「迭代 X」时目标即 X，**不参与归因竞争**
  （否则命令说 A、行为选 B，「显式入口」不可靠）。仍走**完整四阶段 + 验证门 + 人工 `confirm`**，
  只是跳过归因；无证据时也可聚焦（这是「迭代某个模块」的**可靠**入口）。
  ⑤ **红线不变**：驱动面仍只有 `evolution/spec.md`「冷路径驱动」的两个；课程**不常驻**、**不给模型新工具**
  （模型可见工具仍是 9 个）、**不放宽人工门**（低风险候选仍须显式 `confirm`）。
- **实现细节**：`CurriculumPlanner.plan(traces, *, explicit=None, limit=3)` 产出**有界、有序、确定**
  （失败数降序 → 已处理降权 → `plugin_id` 升序兜底）的议程；`limit` 是 P5「token 有界」在目标选择层的
  落地。`EvolutionWorker` **缺省自建** planner（只读 `engine.observations` / `engine.pending` 两个既有公开面
  ⇒ `runtime.py` **零改动**、生产两驱动面自动开课），可注入替换（对齐既有 `trigger` 惯用法）。
  `pending` 传**可调用体**（每轮重取，同 `PetWakeDriver(sessions=…)` 先例）。
- **已否决**：记忆驱动课程（无结构化教训标记）；LLM 驱动课程；新增第三个驱动面（违「两个入口」条款，
  `0065`/E17 已裁决内核不自建 daemon）；放宽低风险候选的人工确认；把课程做成 `Plugin`/工具（无生命周期、
  无副作用、模型不可见）；「曾未过门」也降权（门禁失败是**提案质量**问题而非目标问题，且证据仍可能
  正当指向它）。
- **后果**：✅ 「迭代谁」有了**可解释、可断言、零新增 IO** 的选择层；✅ 并列不再一律转人工（无课程注入时
  行为不变）；✅ 人有了**可靠**的目标入口（建议/指令分离）。⚠️ **行为变更**：并列在开课后由先验解，
  已登记进 spec delta（MODIFIED「对比诊断」）与接口/模块文档。⚠️ 议程质量上限 = 信号质量。
- **关联**：账本 E5；代码 `src/core/evolution/curriculum.py`、`diagnoser.py`、`engine.py`、`worker.py`、
  `src/core/entry.py`（`_evolve_run`）；接口 `03-interfaces/evolution-interface.md` §2 / §3 / §4.2；
  模块 `02-modules/evolution.md` §3.1 / §4；测试 `tests/test_evolution_curriculum.py`（TC-EVO-06）；
  change `0084`。
- **转出**：无新开账本行；E5 关闭后 E 类余 E20① / E26 / E27。

---

## ADR-0080：`features` 段未知模块名告警（注入归属 / 仅告警 / 缺省不校验）

- **背景**：`features` 段子键是**模块名**，模块名集合是组合根单一真源（`runtime.GATABLE_MODULES`，
  ADR-0065）。校验口径只到顶层段名 ⇒ `features.peet: false`（拼错）被照样归一、`is_disabled("pet")`
  查不到 `"pet"` ⇒ **静默 no-op**（关不掉 `pet`，账本 E20①）。
- **决策**：
  ① **注入归属** —— 集合仍归组合根；配置层经 `known_modules` **注入接收**（同既有 `specs=` 惯用法），
     **不 import runtime、不硬编码模块名** ⇒ 不逆转 ADR-0065 归属，只是「拥有者把集合交给校验者」。
     已否决「配置层自持集合」（与 `GATABLE_MODULES` 成两处真源）与「拼写近似告警」（引入编辑距离 +
     阈值常量，与既有白名单派生风格不一致）。
  ② **仅告警不阻断** —— 模块名是**开放集合**（`is_enabled` 供缺省关模块自查二级开关），硬拒会拒绝
     合法新键（与 E18 拒绝硬拒的理由同）；拼错的风险是静默 no-op，一条可忽略的告警足以暴露。
  ③ **缺省不校验** —— `known_modules=None`（缺省）⇒ 不产告警 ⇒ 既有构造面（10 处 CLI 构造点 +
     测试夹具含自定义 `features` 键）不破；「谁注入谁负责」。
  ④ **入口单点注入** —— `entry.py` 10 处 `ConfigManager(...)` 构造点收口为 `entry._config_manager`，
     消除漏传一处即该入口静默丢失告警的风险。
- **规格**：MODIFIED「配置校验与生效」—— 顶层段名口径**加 `features` 唯一例外**（按经注入的已知模块名
  校验、未知仅告警、未注入不校验）+ 两新场景。
- **转出**：无。

---

## ADR-0081：pet 惊喜真实化与上报（有前提才产出 / 节拍同源 / fail-soft）

- **背景**：`PetSession.surprise()` 零调用方，且**无论有无可代办之事都返回「已帮你安排」**、且**从不真的执行动作**
  —— 投出即谎报（账本 E26）。
- **决策**：
  ① **有真实前提才产出** —— `surprise() -> str | None`：无已记录偏好（当前唯一可得的真实可代办信号）⇒
     `None`，不产出不投递；有偏好 ⇒ 经**真实 loop** 跑一次偏好驱动代办、回报其**真实产出**（而非拼文案）。
     已否决「只改文案」（返回值仍与事实解耦，谎报照旧）。
     已否决「用 `has_surprise()` 谓词 + 原返回类型」（两处可能失步的真源；`str | None` 单值更省）。
  ② **节拍同源** —— 挂进 `_notify_owner()`，用既有 `_on_feedback_cycle()` 判据：惊喜要跑 loop（有成本），
     每次唤醒都跑会让唤醒翻倍；惊喜本属低频事件，与周期反馈同节拍天然契合。「随时可上报」= 节拍内**自动**
     上报，非「每次唤醒都报」。已否决「每次唤醒尝试」（成本翻倍 + 刷屏）。
  ③ **fail-soft** —— 惊喜在 `_notify_owner()` 内 `try/except` 吞掉异常：它把非关键路径的失败升级成唤醒失败
     会违反「宠物异常不阻塞主循环」（同 loop `action_observers` 的 fail-soft 先例）；而 `report()` 不跑 loop、
     保持直接投递。
- **规格**：MODIFIED「Periodic Feedback and Surprise」—— 惊喜以**真实可代办**为前提 + 无可代办不产出 +
  节拍同源 + 失败不阻断 + 三新场景。
- **转出**：`MicrotaskRunner` 接线（E26 的另一半）→ change `0087`；pet 控制面（`/pet [cmd]`）→ change `0088`。

---
## ADR-0082：pet 任务一次性、空闲自治睡眠与微任务真实化

- **背景**：账本 E26 的另一半 —— `MicrotaskRunner` 零生产调用方且其「产出」是**预制文案**（谎称「看了看命令历史」
  「发现一条系统小提示」，投出即谎报）；且 `wake()` **不消费任务**（`_tasks` 不减少）、空队列时**编造**一个
  「闲逛探索」任务 ⇒ 宠物**永不休眠、永在做假事**。用户诉求③「干完无任务也可以自己睡觉」正落在此。
- **决策**：
  ① **任务一次性** —— `wake()` 消费队首（`popleft`），队列清空即空闲。规格「重复简单任务」读作「宠物**支持**
     这类可重复的琐事（不断被派发）」，**非**「同一任务实例永远重复」；既有「不出队 + 空队列编造任务」是**实现选择**，
     非规格明文，且与「干完睡觉」直接冲突。已否决「保留不出队 + 另设 `clear` 才入睡」。
  ② **空闲 = 让行态（`_yielding`）** —— 不新增枚举（规格明文「仅四态」「让行复用 orchestration `SUSPENDED`」）。
     宿主驱动（`0083`）**零改动**：入睡后唤醒抛 `PET_YIELDING`，驱动按既有预期态 `skipped` 跳过；
     快照已含 `yielding` ⇒ 恢复后仍睡着；**新任务 `dispatch()` ⇒ 清让行态自动唤醒**（与 doze/resume 同构）。
     已否决「新增 `SLEEPING` 枚举态」（与规格冲突 + 改驱动/快照/断言全额税）。
  ③ **微任务真实化** —— 与 `0086` 同口径「返回值必须有事实依托」：`terminal_walk` 读命令历史**只报条数**
     （历史可能含密钥/隐私 ⇒ **绝不外泄内容**）、不可读/空 ⇒ `None`；`system_hint` `os.getloadavg()` 真探，
     负载 **< CPU 数**（不显著）⇒ `None`（不打扰）；`nonsense_comment` 无 `comment_writer` ⇒ `None`。
     探测函数可注入（缺省真探，同 `sleep`/`clock` 注入先例）。已否决「保留预制文案」（正是 E26 记名的谎报）。
  ④ **触发点 = 空闲入睡前的过渡点，且有通知面才跑** —— `_go_idle()` 内触发一次；无 `notifier` 不跑（同 `0086`
     「无 notifier 不跑惊喜」），失败 fail-soft 不阻断入睡。已否决「每次唤醒都跑」（不空闲也摸鱼、唤醒成本翻倍）。
  ⑤ **注入面走可调用体** —— `PetSession` 收 `microtasks: Callable[[], str | None]`（组合根传 `runner.run`），
     会话层不 import 具体微任务实现（同 `notifier`/`busy` 惯用法）。
- **规格**：MODIFIED「Background Pet Session Lifecycle」（任务出队 / 空闲入睡 / 新任务唤醒 + 3 新场景）+
  MODIFIED「Pet Micro-tasks」（真实产出 + 空闲触发 + 2 新场景）。
- **转出**：pet 控制面（`/pet [cmd]`：`sleep`/`wake`/`assign` 动词）→ change `0088`（本变更已落定其底层语义）。

## ADR-0083：pet 控制面单门面、寻址不猜与同进程作用域

- **背景**：用户诉求① —— 前台（WebUI / CLI / app）**随时** `/pet [cmd]` 查看状态、让它停止工作 / 换一件活 / 睡觉；
  底层语义已由 `0086`（惊喜真实化）/ `0087`（任务一次性、空闲入睡、`dispatch` 自动唤醒）落定，本变更只补**控制面**。
  控制动词有**两个宿主面**（CLI `pet <verb>`、`UIAPILayer.pet_command`），各自分发即两份真源。
- **决策**：
  ① **单一门面 `PetControl`**（verb → 会话操作 + 寻址）收口，CLI 与 `UIAPILayer` 都只调用它；门面**无状态**（持
     `PetManager`）、构造廉价 ⇒ 组合根就地构造，**不给 `Runtime` 数据类加字段**（其字段集被多测试隐式断言）。
     已否决「两侧各写一份 verb 分发」（同 `0079`／`0086` 反复回避的双真源坑）。
  ② **只复用既有会话操作**：`sleep→suspend` / `wake→resume` / `assign→dispatch` / `stop→PetManager.stop` /
     `status→snapshot()` 过滤。**不新增 `PetSession` 公开 API**（不读私有），控制面是**适配**而非新语义。
  ③ **寻址不猜**：单宠物默认（免记 id）；多宠物未指定 ⇒ `PET_TARGET_AMBIGUOUS` **列出可选 id**（赌错宠物是
     **静默的错操作**）；指定但未注册 ⇒ `PET_NOT_FOUND`。**对照 `PetManager.stop()` 的静默 no-op** —— 那是
     「注入式批量驱动」的容错取向；控制面是**人显式操作**，静默成功会让人以为宠物睡了、其实没动。
  ④ **动词名 `wake` = `resume()`**（**显式记录命名陷阱**）：与 `PetSession.wake()`（**执行一次任务**）语义不同。
     仍取 `wake` 因用户前台语汇是 `sleep`/`wake` 成对，且作用面不同（控制动词 vs 会话内部方法），接口文档并列写明。
     **已否决**改名 `resume`（更精确但丢失用户语汇）。
  ⑤ **`status` 不外泄偏好与任务正文**：由 `snapshot()` **过滤**（id / state / sleeping / pending / wake_count / fault），
     控制面是**观测面**，无须把主人偏好与任务文本投给任何前台客户端（对齐「密钥只引用不读取」的隐私取向）。
  ⑥ **作用域 = 本进程已注册会话**：`PetManager.list()` 返回本进程内存，另一进程 `pet run` 常驻驱动**不重读**注册表
     ⇒ 跨进程控制今天不通。用户裁决「**仅同进程**」：**有意不做**跨进程，避免造出「改了盘却没驱到 live 会话」的假象。
     将来若做，`PetControl` 是**唯一扩展点**。
- **规格**：ADDED「Pet Control Surface」（动词 / 寻址 / 状态字段 / 拒绝 / 同进程 + 6 场景）。
- **前置**：`ADR-0081`（惊喜真实化，`0086`）、`ADR-0082`（任务一次性 + 空闲入睡 + `dispatch` 自动唤醒，`0087`）。
- **转出**：跨进程控制（注册表 → live 会话的驱动通道）→ 未排期。

---
## ADR-0084：可观测性生产导出器装配（JSONL + 缓冲包装，注入优先）

- **背景**：账本 C4（Phase 20 §1）—— `build_runtime` 未注入 tracer 时 `Tracer()` **不传 exporter**，缺省
  `NoopExporter` ⇒ **生产零导出**；而规格 Requirement「全链路日志」要求「系统 SHALL 记录…结构化」，
  Requirement「遥测缓冲与导出重试」要求导出失败降级不阻塞主循环。导出器实现（JSONL/Console/Noop/Buffered）
  **全部已具备且已测**，缺的只是**组合根装配**（与 Phase 19 反复记的「实现已落地、缺生产触达点」同型）。
- **决策**：
  ① **缺省导出面 = `BufferedExporter(JSONLExporter($CORE_STATE_DIR/traces.jsonl))`**：JSONL 满足「结构化记录」，
     外层缓冲满足「导出失败降级不阻塞主循环」（`BufferedExporter.emit` 内 `except` 降级 + 指数退避，绝不抛给 loop）。
     **裸 `JSONLExporter` 已否决** —— 磁盘满 / 权限不足时会从 `end_trace` 抛进 loop，直接违反规格场景。
  ② **落 `$CORE_STATE_DIR/traces.jsonl`**：与 checkpoints / memory / pets / mcp-endpoints 同一状态目录约定
     （新增 `_trace_path()`，**随既有 `_*_path` 风格**，不顺手抽公共 helper —— 避免越界改 5 处既有函数）。
  ③ **注入优先**：`build_runtime(..., tracer=)` 形参不动，只填 `else` 分支；宿主 / SUT 替换导出面的接缝保持。
  ④ **`JSONLExporter.__init__` 自建父目录**（镜像 `FileBackend.__init__`）：否则导出目标目录不存在时事件**静默丢弃**
     —— 不能依赖「缺省 memory 后端恰好建过该目录」这条隐式耦合。
  ⑤ **不扩面**：不加配置开关（要换导出面走注入；规格未要求可配）、不给 `Runtime` 加字段（其字段集被多测试断言）、
     不引入 OTel/Prometheus SDK（第三方依赖，与 ADR-0044「核心零三方依赖」红线相关，另案裁决）。
- **规格**：MODIFIED「全链路日志」（补组合根装配 + 注入优先 + 2 场景）。
- **前置**：`ADR-0043`（MCP SDK 按 transport 分流 —— 同「零依赖优先、SDK 另案」取向）。
- **转出**：OTel/Prometheus 指标导出器 + 告警规则（需第三方 SDK）→ Phase 19 §5 凭证 / 依赖半。

---
## ADR-0085：git 生产后端 = stdlib subprocess 直调 CLI（零三方依赖 + 错误不回显）

- **背景**：账本 C2（Phase 20 §1）—— git 抽象（`GitBackend` Protocol）、核心操作（`GitClient`）、.git 保护、
  高危审批**全部已落地且已测**，唯一缺的是**生产后端实现**：`build_backend()` 直接抛「离线未接」，
  `GitBackend` 在生产**无任何实现**。`git-architecture.md` §1 明文「Git 独立为 capability（**非 tool**）」
  ⇒ 无循环工具面待接，缺的就是底层适配器本身。
- **决策**：
  ① **stdlib `subprocess` 直调 `git` CLI**（不引 gitpython / dulwich）：`git-interface.md` §3 已列的首选项，
     且对齐 `ADR-0044`「核心零三方依赖」红线。
  ② **`cwd` 归属后端实例**（构造参数，缺省 `Path.cwd()`）：13 项原语的多数作用于「当前仓库」，
     `init` / `clone` 完成后把 `cwd` 指向新仓库 —— 与真实「一次会话绑定一个仓库」一致。
  ③ **新增 `GIT_COMMAND_FAILED`**：既有 4 码（AUTH / TIMEOUT / WORKTREE_DIRTY / CONFLICT）都不覆盖
     「本地子命令非零退出」（硬套 `GIT_WORKTREE_DIRTY` 是语义滥用）。**纯加法**，既有码语义与测试不变。
  ④ **错误信息不回显原始 stderr**：`_classify` 只按特征**归类**（认证 / 冲突 / 其余），异常文本是**固定中文提示**。
     git 的 stderr 可能含 `https://user:token@host/...`，对齐规格 R3「不泄露凭据与私有仓库地址」与全局
     「密钥只引用不读取、绝不进日志/记忆」。凭据交给环境中的 git credential helper，本模块不接触、不落盘。
  ⑤ **`merge` 冲突走结果而非异常**：非零退出且 `git diff --name-only --diff-filter=U` 非空 ⇒
     `MergeResult(merged=False, conflict_files=[...])`（对齐 Protocol 与接口 §1）；非零且非冲突 ⇒ 抛 `GitError`。
  ⑥ **不改装配面（**偏离 phase-20 §4.1 原记**）**：不做组合根装配、不加 `git` CLI 入口 —— 消费者（coding 工作流）
     **尚未存在**，此刻塞进 `Runtime` 或加 CLI = **无消费者的空接缝**（与 §2 对 E27 的判定同理）。装配待消费者
     出现时并入该消费者的 change。
  ⑦ **不动远程可靠性半**：只保证错误**归一**（超时 → `GIT_REMOTE_TIMEOUT`），不实现退避重试 / 连接释放策略
     （无远程消费者，YAGNI）；远程凭据 keychain 归 Phase 19 §5。
- **影响**：`GitClient()` 现在真的可用；`tests/test_git.py::test_no_backend_raises` 断言的行为**被本变更有意改变**
  （缺省后端不再是错误），替换为「缺省工厂给出 subprocess 适配器」；其余 git 测试零改动。
- **规格**：MODIFIED「GitClient 抽象接口与依赖注入隔离」（补缺省后端 + 归一错误码 + 2 场景）。
- **前置**：`ADR-0026`（Git 独立为 capability）、`ADR-0044`（核心零三方依赖）。
- **转出**：远程凭据 keychain 集成（R3 凭据半）+ 远程重试 / 连接释放（R5）→ Phase 19 §5；组合根装配 → 待消费者 change。

---

## ADR-0086：ci_cd 门禁执行器 = stdlib subprocess 直跑 GATE_COMMANDS

- **背景**：账本 C3（Phase 20 §1/§4.2）—— 注入面（`pipeline.py:40-41`）与四道门禁命令基准 `GATE_COMMANDS`
  均已就位，但生产**缺省**执行器 `build_gate_executor` 对**任何**门禁都直接抛「离线未接」⇒「交付流水线」
  在生产**恒不可用**（与 Phase 19 反复记的「实现已落地、缺生产触达点」同型）。
- **决策**：
  ① **执行器 = `SubprocessGateExecutor`（可调用对象）**，类型满足既有注入面 `Callable[[Gate], GateResult]`
     ⇒ 缺省装配与注入替换**同一接缝**；工厂 `build_gate_executor(**kw)` 与 git 的 `build_backend()` 同形。
     **不改注入面为 Protocol**：单一实现，无收益的抽象升级（YAGNI）。
  ② **stdlib `subprocess` + `shlex.split`、不经 shell**：命令是自家常量却仍免注入面与 shell 语义差异；
     零第三方依赖（ADR-0044）。
  ③ **失败归一为 `GateResult(passed=False)` 而非抛**：「跑不起来」（工具缺失 / 超时）与「跑失败」（非零退出）
     对上都是**该门禁未通过**，交 `CICDPipeline` 既有阻断路径；**未知门禁类型仍抛 `GATE_FAILED`**
     （那是调用/配置错误，非门禁结果 —— 与 `CICDPipeline.gate` 同口径）。
  ④ **`reason` 含**有界**输出尾部（≤2 000 字符）**：规格明文「返回失败门禁与**原因**」，只给退出码无信息量。
     **与 `ADR-0085` 有意不同** —— 门禁输出是本地工具自身诊断文本（无凭据面），git stderr 可能含带凭据的远程地址。
  ⑤ **超时缺省 600s**（可注入）：全量 pytest 留足余量，同时杜绝无限挂起（对齐 R5 对远程的取向）。
  ⑥ **不动 `GATE_COMMANDS`**（Phase -1 固化基线，被既有测试逐条断言形状）：本变更只补「怎么跑」。
     **已知接受项**：本仓四门可执行体不在 PATH ⇒ 缺省执行器在本仓会如实判「工具缺失 / 未通过」（**正确**行为），
     命令基准 / PATH 假设的调整是**另一次决策**。
  ⑦ **不做组合根装配 / 不做 `ci gate` CLI**（**偏离 phase-20 §4.2 原记**）：`ci_cd` 在 `src/` 内**零调用方**，
     消费者（交付编排）未出现；且 CLI 会给出一个**在本仓必然失败**的门面 ⇒ 装配与 CLI 并入消费者出现的 change
     （同 `ADR-0085` 对 git 的判定）。
- **影响**：`CICDPipeline()` 缺省路径**真的可用**；`tests/test_ci_cd.py` **零改动**（全部显式注入 executor）。
- **规格**：MODIFIED「交付流水线」（补生产缺省执行器口径 + 2 场景）。
- **前置**：`ADR-0044`（核心零三方依赖）、`ADR-0085`（同批 C 类代码半，同「不造空接缝」判定）。
- **转出**：真实制品仓库通道（`CHANNEL_UNREACHABLE`，凭证半）→ Phase 19 §5；`ci gate` CLI + `GATE_COMMANDS`
  的 PATH/命令基准决策 → 待消费者变更。

---

## ADR-0087：skillhub 接入 CLI（`skill search` / `skill install`）+ 技能库与组合根同源

- **背景**：账本 C5（Phase 20 §1/§4.4）—— `SkillHubClient` / `MarketIndex` / `TrustVerifier` / `SkillPublisher`
  **全部实现、DI 完整**，但**零生产调用方**：`_skill_search(SkillLibrary(), q)` 搜的是**新建的空库**
  （`SkillLibrary()` 无路径 ⇒ 进程内一次性）⇒ `skill search` **恒空**；`skill install` 只是
  `plugin install --kind skill` 的别名（其 `--source` 参数**声明了却零消费**）；`skill remove` 同样作用于空的一次性库
  ⇒ **永远删不掉运行时真正注册的技能**。
- **决策**：
  ① **触达点 = 既有 `skill` 子命令**（不新增命令面）：`search` → `SkillHubClient.search`，
     `install` → `SkillHubClient.download`（先签名校验后注册 draft），错误归一为 stderr + 退出码 1。
  ② **技能库与组合根同源**（`SkillLibrary(path=$CORE_STATE_DIR/skills.json)`，经 `entry._build_skill_library()`）：
     这是 C5 **成立**的前提而非附带改动 —— 否则「已安装」是**谎报**（写进一次性库、下个进程消失），
     `skill remove` 也永远删不掉真技能（同 E21/E22「单一真源」取向）。**不抽公共 helper 到 runtime**：
     该约定已是两处 `_*_path` 实现，抽公共函数会引入新依赖方向，与既有「各层各自持有 `_*_path`」风格不符
     （同 `ADR-0084` 对 `_trace_path` 的处置）。
  ③ **构造留缝**：`_build_skillhub_client(library)` 缺省 = 空 `official` 源 + `TrustVerifier` + `fetcher=None`；
     测试注入**内存 index + fetcher** 即端到端验证两条路径（ledger 的「注入内存 MarketIndex 即可离线验证」）。
  ④ **`skill search` 补 `--source`**：`install` 侧**早就有**此参数（此前零消费），搜索侧补齐才使多源在 CLI 上
     **对称可达**（否则第三方源只能装不能搜）。
  ⑤ **`_skill_search` 改「搜市场」不视为回归**：今日的本地库搜索**恒空**（无路径库），改后至少如实报「未找到」，
     市场接入后立即可见。
  ⑥ **不动 `core/skillhub/` 源码**（实现早已齐备）、不动 `plugin install` 的本地路径安装。
- **规格**：MODIFIED「技能市场与技能发现」+「签名校验与可信下载」（CLI 触达点 + 技能库同源 + 3 场景）。
- **影响**：CLI 行为变更三处（search 搜市场 / install 走市场下载 / remove 作用持久库）；
  `tests/test_entry.py::test_skill_remove_missing` 继续通过（`conftest` 已按测试隔离 `CORE_STATE_DIR`）。
- **前置**：`ADR-0044`（核心零三方依赖）、`ADR-0085`/`ADR-0086`（同批 C 类代码半）。
## ADR-0088：插件四源解析器 = 执行层 stdlib 实现（`core-plugin.json` 约定 + 临时工作区可逆）

- **背景**：账本 C6（Phase 20 §1/§4.5）—— `PluginInstaller` 四钩子 DI 完整、`InstallDispatcher` 已真装、
  `LOCAL_PATH` 已真；但 `GIT_REPO` / `MARKET_REGISTRY` / `MCP_ENDPOINT` **一律抛「未接入 resolver」**。
  规格「插件来源与安装」明文要求四类来源、场景「四类来源安装」已存在 ⇒ **规格为真、实现为假**；
  且 `plugin install` 入口**已存在**却把来源**硬编码**为 `local-path`（自述能力与实际能力不符）。
- **决策**：
  ① **解析器落执行层 `core/plugins/sources.py`**，`plugin_registry` 的 `_default_resolve` 保持「未接入」空壳 ——
     基座（`BASE_MODULES`）只依赖彼此 + stdlib，真实外部解析属**执行层**职责（`InstallDispatcher` 已兼
     resolver + installer 双责）。
  ② **零三方依赖（ADR-0044）**：git-repo 复用 **change 0090** 的 `core.git` stdlib subprocess 后端（不新写
     shell out、不引 gitpython）；market-registry 走 stdlib `urllib.request`（同 `tools/builtin.py`、
     `judgment/provider.py` 既有口径）。
  ③ **`MANIFEST_FILENAME = "core-plugin.json"`**（仓库根目录）：仓内零既有 manifest 文件名约定（全仓检索无命中），
     故定一个带命名空间前缀的可发现常量，作为 git-repo 来源的**对外契约**写入接口文档与规格。
  ④ **临时工作区可逆（P2）**：克隆落 `tempfile.TemporaryDirectory`，`with` 退出即删 —— 解析**零残留**、不写 `$CORE_STATE_DIR`。
  ⑤ **回显脱敏 `_safe`**：沿用 `ADR-0085` 红线，异常文本中的地址经 `urlsplit`/`urlunsplit` **剥掉 userinfo 与 query**；
     市场凭据的正道是**注入 fetcher 携带**（不进 URL），`_safe` 是纵深防御第二层。**不用 `parts.port`**
     （畸形端口会 raise），改 `netloc.rpartition("@")[2]`。
  ⑥ **mcp-endpoint 解析期零网络**：只做端点串 → `{"name", "url"}`（端点名复用 `core.mcp.default_endpoint_name`，不另立解析）；
     可达性归 install 期 `MCPClient.add`，与 `mcp add`「先连通验证再落盘」同口径，避免「解析成功但装不上」双重语义。
  ⑦ **CLI `plugin install --source`**：补齐**既有入口的既有契约**（`PluginSource` 四值 + 规格四源），缺省 `local-path`
     向后兼容 —— 与 C5 的 `skill search --source` 同性质，**不是**新增命令面（对比 `ADR-0085`/`ADR-0086` 拒绝的
     「无消费者的新入口」）。
  ⑧ **顺带修 `_build_installer` 技能库同源**：原用 `SkillLibrary()`（无路径 ⇒ 进程内一次性库），`plugin install --kind skill`
     装完即丢（同 `ADR-0087` 的根因族）；改 `_build_skill_library()`（`$CORE_STATE_DIR/skills.json`）。**mcp/cli 分支不受影响**
     （工具面本就进程内；MCP 端点持久化归端点注册表，不经此处）。
  ⑨ **缺省外部边为「真实现」而非 `None`**（异于 `ADR-0087` skillhub）：git-repo / market-registry 的**成功路径可完全离线验证**
     （本地仓库克隆 / `file://` 文档），无需凭证；skillhub 缺省 `None` 是因其市场索引自带签名与健康语义，插件市场侧无此结构。
- **规格**：MODIFIED「插件来源与安装」（四源发现契约 + 3 场景）。
- **影响**：`InstallDispatcher.__init__` 增 2 个 keyword-only 注入缝（纯加法）；`_plugin_install` 增 1 个内部参数；
  既有 `plugin install` 用例继续通过（缺省 source 不变）；`plugins` 不在 `tests/test_architecture.py` 的任何分层名单
  或 `forbidden` 映射内 ⇒ 新增 `core.git` 依赖不受门禁约束，依赖方向（执行适配层 → 能力横切）正确。
- **前置**：`ADR-0044`（核心零三方依赖）、`ADR-0085`（git stdlib 后端 —— 本变更的克隆边复用它）、`ADR-0087`（同批 C 类代码半）。
- **明确不做**：`mcp add` 改走 `MCP_ENDPOINT` 来源（无收益重构）；`install_tool` / `list_tool` / `uninstall_tool` 接线
  （`src/` 内**零生产注册**，属**安全决策**：模型可发起安装 ⇒ 需审批/沙箱口径；非 C6 症状，记入账本后续行）；插件市场
  索引语义（`skillhub` 的 `MarketIndex` 已有，插件侧无消费者）。
- **转出**：真实市场鉴权凭据 + 真实 git 远端凭据 + MCP 端点真实连通 → Phase 19 §5 凭证半。

---

## ADR-0089：对话会话注册表落盘 = `core/ui/sessions.py`（读透 + 写时合并，非「载入一次」）

- **背景**：真机活 LLM 冒烟暴露 —— `UIAPILayer._sessions: dict[str, str]`（`core/ui/api.py`）是**进程内 dict**，
  `create_session` 生成的 `uuid4().hex` 只在本进程有效。后果：`session create` 建 id → **另起进程**
  `run --session <id>` ⇒ `UI_SESSION_NOT_FOUND`（已实测）；CLI 建的会话在 WebUI（`serve`）不可见（9 端点无会话枚举）。
  而**记忆本身已落盘**（`memory.jsonl`，召回 `MemoryStore.read(query)` 查询驱动、不按 session 过滤，
  跨进程召回实测成立）⇒ 缺的只是「id → 有效」这层注册表的持久化。此项正是 change `0048` 的 Non-goals 明文延后项。
- **决策**：
  ① **落 `core/ui/sessions.py`，不入基座**：消费方只有 `UIAPILayer` 与 `entry._session`；`ui` 是接入层顶点包
     （反向依赖黑名单仅 `{ci_cd, im, git}`），新模块只用 stdlib + `core.persistence`（顶层中性 IO 模块，
     `skills/library.py` 已有同向先例）⇒ 零架构风险。
  ② **读透 + 写时合并**（本变更核心）：照抄 `SkillLibrary` 的「ctor `read_state` 载入一次、之后纯内存」会**双失灵** ——
     长驻 `serve` 进程启动早于 CLI `session create` ⇒ 永远看不到新会话；两进程各持内存副本整体重写 ⇒
     last-writer-wins 互相抹除。故 `exists` / `list` **每次 `read_state`**、`create` 走 **read → merge → write**。
     文件仅几十字节，`write_state` 本身是 tmp + `os.replace` 原子写，成本可忽略。
  ③ **文件名 `conversations.json`**：与 `sessions.jsonl`（`HarnessHost` 连接记录，`session-{N}` 另一套 id 空间）
     **名与义均不同**，避免同名异物。
  ④ **`path=None` ⇒ 纯内存**：与 `SkillLibrary` / `persistence` 房型一致；`UIAPILayer()` 无参构造仍得内存注册表
     ⇒ 既有 `UI_SESSION_NOT_FOUND` 断言与全部既有测试语义**逐条不变**（纯加法、后向兼容）；
     **只有显式 `registry=SessionRegistry(path=...)` 才落盘**（`conftest.py` 已隔离 `CORE_STATE_DIR`）。
  ⑤ **单点注入 `entry._build_ui`**：四入口（`_repl` / `_serve` / `_app` / `_run`）**全部**经此装配点，
     故 CLI 建的会话、`serve` 进程、REPL、`--app` 看到的是**同一文件**。
  ⑥ **注册表为派生状态**：文件缺失 / 损坏 ⇒ 空注册表启动（不阻断），与 `persistence` 同一降级口径。
  ⑦ **fail-closed 不变**：持久化**不放宽**校验 —— 未登记 id 仍抛 `UI_SESSION_NOT_FOUND`。
- **规格**：ADDED「会话注册表持久化与跨入口共享」（3 场景）。
- **影响**：`UIAPILayer.__init__` 增 1 个 keyword-only 参数（纯加法）；`create_session` / `_require_session` 内部实现替换
  （**外部契约不变**：仍返回 32 位 hex、仍抛同错误码）；`fastapi_serve.py` 新增 `GET /sessions`（端点 9 → 10）；
  既有测试缺省装配行为不变 ⇒ **零破坏**；`tests/test_architecture.py` 对 `ui → core.persistence` 无禁名单交集。
- **已知边界**：**不引入文件锁** —— 会话创建是人工操作、频率极低，两进程在同一毫秒内 read→write 的极端竞态
  （丢一条）**接受**（WSL 上 flock 语义有坑，且属过度工程）。
- **明确不做**：`session remove` / 上限裁剪（无消费者；删除牵出「`memory.jsonl` 中该 session 条目怎么办」，
  属独立议题）；重命名 `sessions` 命令（列 `HarnessHost` 连接记录，是另一套 id 空间，改名会破 CLI 契约基线，
  仅以 help 文案消歧）。
- **转出**：跨进程一致性协议 / 注册表与 `memory.jsonl` 的对账 → 后续按需（见账本）。

---

## ADR-0090：auto-approve = 权限层全放行（gate 顶部短路 + guard 分支感知），非「与 interactive 同判」

- **背景**：真机活 LLM 冒烟暴露 `auto-approve` 权限档**名实不符** —— 与 `interactive` 判定**逐行相同**，
  非交互入口（`run` / `serve` / `--app`，无 approver）下一切不可逆工具**全被 fail-closed 拒绝**。两因叠加：
  ① `PermissionModeGate.authorize` 只在 read-only / high-risk-block 改变判定，其余**回落 `PolicyEngine.authorize`**
  （对 HIGH_RISK 返回 `approval_required=True`）⇒ `guard._to_gate` 翻成 `confirm`；
  ② `PermissionGuard.confirm` 的 `if self._is_write(coeffects) and not reversible: return confirm`（`guard.py:57`）
  **完全不看权限档**。顺带真 bug（同类根因「子串匹配」）：`PolicyEngine` 只读词表含 `"ls"`，而工具 id 命名空间前缀
  `"tools."` 含子串 `"ls"` ⇒ **所有 `tools.*` 被判 READ**（含 `tools.file_write`），deny-by-default 兜底失效。
- **决策**：
  ① **`auto-approve` = 权限层全放行**（用户裁决）：`PermissionModeGate.authorize` **最前**短路返回
     `Decision(True, ...)`，不调用 `classify`（模式不关心风险等级）。**必须顶部短路**而非只改 guard ——
     否则 HIGH_RISK 的 `approval_required` 仍会经 `_to_gate` 变成 `confirm`（名实不符的另一半）。
  ② **`PermissionGuard` 记 `self._mode`**（`PermissionModeGate.mode` 公开属性，构造后不变），不可逆写分支加
     `and self._mode is not PermissionMode.AUTO_APPROVE`。两处**缺一不可**（confirm 门有两条独立来源）；
     `loop/default.py::_allow` 调的就是注入的同一 `PermissionGuard`，无需改动。
  ③ **全放行仅限权限层，不越过正交红线**：`PermissionGuard` 的 guardrail 分支保留在不可逆写分支**之前**
     （缺省装配 `guardrail=None`）⇒ 无人值守缺省即成立，且不牺牲 JEV 红线。**否决**「顶部早期 `return auto`」
     的激进写法（会连 guardrail 一起绕过）。
  ④ **模式语义归 gate，不改 `PolicyEngine`**：它是**模式无关**的风险引擎，`PermissionModeGate` 注释即此分层；
     把模式耦合进分级会污染 deny-by-default 的语义。
  ⑤ **只读判定改按语义词元**：删 `_READ_TOKENS` 的 `"ls"`（唯一出现在命名空间前缀里的短词元；`cat`/`get` 等
     不在任何工具 id 前缀中，保留）；新增模块常量 `_DELEGATE_COEFFECT = "agent:delegate"`，在**两段 HIGH_RISK
     判定之后、WRITE 扫描之前**以 `in coeffect`（list 元素**等值**匹配）判 READ —— 保风险信号优先，
     且**不放宽为 `agent:` 前缀**（将来任何 `agent:*` 仍 HIGH_RISK）。
  ⑥ **`core/tools/safety_gate.py` 不改**：它是 `ToolProvider` 的缺省 `confirm_gate`，**运行时不用它**
     （`runtime` 注入 `PermissionGuard`）；为它加 mode 会新增注入面、与 `PermissionGuard` 职责重复（两份模式语义
     真源）、且破 `tests/test_tool_use.py` 既有断言。
- **规格**：MODIFIED「权限模式」（正文重写为全放行 + 「与红线正交」新场景；read-only / interactive /
  high-risk-block 三场景原样保留作锚）+ MODIFIED「分级权限体系」（词元判定 + 字面量豁免，3 新场景）。
- **影响**：`PermissionModeGate.authorize` 唯一对外变化在 AUTO_APPROVE 档（其余三档逐字不变）；
  `PermissionGuard` 增 `self._mode`（纯加法）；`PolicyEngine.classify` 仅 `tools.*` 与 `agent:*` 变化。
- **有意行为变化（更正确，非回归）**：`high-risk-block` 下 `code_run` 由「走审批」变**无条件阻断**、
  `read-only` 下由 confirm 变 `PERMISSION_DENIED`（改前 `code_run` 靠 `"ls"` 误判 READ，正解是 HIGH_RISK）；
  `tools.<未知>` 由 READ 误判变 HIGH_RISK（deny-by-default 正解）。以上无既有测试断言。
- **明确不做**：给 `SafetyGate` 加权限档；改 `PolicyEngine.authorize`；「auto-approve 顶部 return」；
  改动 `_WRITE_TOKENS` / `_HIGH_RISK_TOKENS` 其余词元（无证据，避免顺带重构）。
- **已知边界（无人值守前置条件，change `0096` 补记）**：auto-approve 解的是**权限层**的门，端到端无人值守仍需
  ① **不配 judgment**（`guardrail` 仅当 `judgment.provider` 存在时注入，缺省 `None` ⇒ 无红线；一旦配了，
  `noul=False` 仍 `deny` —— 这正是 0095 有意保留的正交红线，不被全放行越过）；② **不用 MCP http/streamable 传输**
  （`permission.sandbox.host_allowlist` 缺省空 = fail-closed 全拒；`tools.web_fetch` 与 `tools.code_run` 不经该策略）。
  进化结晶门与权限档零耦合（`engine.py:136`「不引入低风险自动结晶」）⇒ 无人值守下进化循环照跑，但不自动结晶。

---

## ADR-0091：token 预算由模型上下文窗口**派生**（减固定输出头寸），非独立开关；非法取值校验期阻断

- **背景**：`TOKEN_BUDGET_EXCEEDED` 的阈值与「单任务最大循环次数」此前是 `DefaultLoop` 的**写死 ctor 缺省**
  （`token_budget=65536` / `max_rounds=10`，`loop/default.py`），而组合根四处 `DefaultLoop(...)`
  （主 / 子 agent / 神兽 / 宠物 loop）**都不传参** ⇒ 用户既不能经 CLI/env/yaml 调，也没有 UI 入口。
  「Context Window Size」（模型上下文窗口，如 128k）在配置里**根本不存在**，预算与之**完全脱钩** ——
  换一个大窗口模型，预算仍卡在写死的 65536（浪费上下文）；换一个小窗口模型，预算仍是 65536（爆窗风险）。
  用户诉求：三面可配（CLI 参数 / 配置文件 / WebUI 设置页），未配则回落代码内部预设缺省。
- **决策**：
  ① **预算由窗口派生，不新开 `loop.token_budget` 开关**（用户裁决）：`token_budget = context_window - output_reserve`
     （仅当 `context_window > 0`），`output_reserve` 缺省 `8192`；未配窗口 ⇒ 回落内置缺省 `65536`
     （**与变更前逐位一致**，行为等价性可验证）。理由是**少一层会与窗口矛盾的开关** —— 显式预算键一旦与
     窗口不一致，就产生「窗口 8k 却配了 128k 预算」这类无解歧义；派生式无此病。
  ② **口径取「减固定输出头寸」而非按比例**：模型调用一次要同时装下**输入（prompt/记忆/历史）与输出（推理+回答）**，
     而预算是**输入侧**压实阈值。窗口是二者的共享上限，故可用预算 = 窗口 − **为输出保留的头寸**。
     比例口径（如 `0.8 × 窗口`）隐含「输出随窗口线性增长」，但输出需求与窗口**不成比例**（128k 窗口的答案
     不会比 8k 窗口长 16 倍）；固定头寸与「推理档位」实际占用量级一致，且**可解释**（差额就是留给输出的）。
  ③ **三键走 ConfigSpec 单一真源**：`llm.context_window` / `loop.output_reserve` / `loop.max_rounds`
     ⇒ CLI flag / env / yaml **三面自动生成**，优先级链 CLI > env > yaml > 缺省。`llm` 是结构化段 ⇒
     `context_window` 进 `LLMConfig`；`loop` 照 §2.4/§2.6 先例**驻留 `extra`**（不新增结构化段）。
  ④ **校验期拒绝，绝不静默兜底**：`context_window` 非 `0`/≥1 整数（**显式排除 `bool`** —— `isinstance(True, int)`
     为真）、`output_reserve` 非 ≥0 整数、`max_rounds` 非 ≥1 整数，一律在 `validate_schema` 判错、**阻断启动**；
     并**交叉校验** `context_window > output_reserve`。**为何必须阻断**：`token_budget <= 0` 在 loop 里的语义是
     「**关闭** token 维度」（`loop/default.py` 的 `_should_compact` 与硬停分支），静默兜底会把一个配置错误
     伪造成「预算维度失效」（更危险的**静默降级**）；宁可启动失败也不掩盖。
  ⑤ **组合根注入，不做运行期热更新**（本 change 边界）：`build_runtime` 经 `config.loop_limits()` 读出后注入
     四处 `DefaultLoop(...)`。热更新（改配置即改**运行中** loop 的上限）归 change `0099`，WebUI 设置页归 `0100`。
- **已知局限（须长期记在案）**：`ctx.token_used` 是 `len(str(...))//4` 的**粗估**（非模型回报的权威用量）
  ⇒ 无论哪种口径都只是**近似**控制，不是精确窗口管理。真正的精确口径需接入模型 usage 回报，属后续项。
- **影响**：`LLMConfig` 增 `context_window`（纯加法，缺省 `0` 保持旧行为）；`ConfigManager` 增 `loop_limits()`
  （照 `circuit_breaker()` 形状）与两条校验器；`_KNOWN_EXTRA_SECTIONS` 加 `"loop"`；组合根四处 `DefaultLoop(...)`
  补传参；`entry._key_to_patch` 接受 `loop.` 前缀且 `write_patch` 对 `extra.loop` **浅合并**。
  **未配置时全链路行为与变更前逐位一致**（`10` / `65536`）。
- **明确不做**：把 `ContextCompactor._ROUND_THRESHOLD`（轮数维度触发，`context/compactor.py`）纳入本项 ——
  它独立于此议题，避免混入；新增显式 `loop.token_budget` 键（见 ①）；本 change 内做热更新 / 前端（见 ⑤，
  分别归 `0099` / `0100`，三者顺序不可换：先有可配项，才有可热更的项，才有可编辑的界面）。
- **规格**：MODIFIED「错误与预算控制」（loop）+ MODIFIED「LLM 提供商配置（必选）」/ ADDED「循环预算配置」（configuration）。

---

## ADR-0092：LLM 配置「保存」与「hydrate」双入口；落盘原子提交 + 能力协议热生效

- **背景**：规格「LLM API 可配置」要求 UI 保存后**写入后端配置源并立即生效**，而 `UIAPILayer.set_llm_config`
  只改内存（归档 change `0003` 明文 deferred）。但 `set_llm_config` 同时被**启动期** `entry._build_ui` 调用，
  把 runtime 解析出的 LLM 配置 hydrate 进 API 层 ⇒ 若让它落盘，「读配置」会变成「写配置」
  （每次 `core-agent run` 都重写 config.yaml）。此外 loop 的预算上限只在**装配期**注入（ADR-0091 ⑤），
  保存配置对**运行中**的循环无效；`PUT /llm-config` 也缺 `context_window` / `output_reserve` 字段。
- **决策**：
  ① **入口分离**：`set_llm_config`（启动期 hydrate，纯内存）语义**不变**；新增
     `apply_llm_config(cfg, *, output_reserve=None, max_rounds=None)` 承载「用户显式保存」
     （校验 → 落盘 → 重读）；HTTP `PUT /llm-config` 走后者。一个名字无法同时表达两种相反意图。
  ② **一次 patch、原子落盘**：`llm` 与 `loop` 两段组**单个** patch 提交 ⇒ 不存在「llm 写了、loop 没写」的中间态。
     `ConfigManager.write_patch` 由 `write_text`（**先截断再整写**）改为 tmp + `os.replace`
     （`0062` `CheckpointStore` / `0074` 端点注册表同款，stdlib 零依赖）。**为何必须改**：非原子写中途失败留
     半写文件 ⇒ 调用方「重读回滚」这条路**自身失效**（回滚读到坏文件）；改后失败路径旧文件**逐字不变**。
  ③ **热生效走能力协议，不焊死 `DefaultLoop`**：`core/loop` 定义 `@runtime_checkable LimitsConfigurable`
     （仅 `set_limits(*, max_rounds=None, token_budget=None)`），`UIAPILayer` 以 `isinstance` 探测后调用，
     **不支持者静默跳过**（loop 是可替换策略插件，换插件不该让「保存配置」失败）。`DefaultLoop` 两值在**每轮**
     判定处读取（轮数上限 / 硬停 / 压实）⇒ 纯赋值即**下一次**生效，无需重建循环。
  ④ **推给 loop 的值取 `config.loop_limits()` 派生结果**，UI 层**不重算**「窗口 − 预留」（否则是第二个派生真源）。
     仅**无配置源**（裸 `UIAPILayer`）时降级为就地派生 + 纯内存，且 `get_loop_limits()` 返回 `None` ——
     **不假装**有生效值。
  ⑤ **GET 回显「生效值」，PUT 收「旋钮」**：旋钮是输入、预算是可观测结果；回显 `token_budget` 才回答用户
     「窗口配了生效了吗」。失败语义统一：非法取值 / 落盘失败 ⇒ `UI_LLM_CONFIG_INVALID`（HTTP 400），
     **内存与 yaml 均回退原值**（`apply_change` 先校验后替换）。
- **影响**：`UIAPILayer` 增 `apply_llm_config` / `get_loop_limits`；`DefaultLoop` 增 `set_limits`；`core/loop`
  导出 `LimitsConfigurable`；`write_patch` 原子化；新增错误码 `UI_LLM_CONFIG_INVALID`（→ 400）；
  `PUT`/`GET /llm-config` 字段扩展。`set_llm_config` 的既有调用方（`entry._build_ui`）**零改动**。
- **明确不做**：多进程并发写的文件锁（单用户桌面场景，`os.replace` 已保证不半写）；新增显式
  `loop.token_budget` 键（见 ADR-0091 ①）；前端设置页（归 change `0100`）。
- **规格**：MODIFIED「LLM API 可配置」（ui）。

---

## ADR-0093：SPA 产物**可选**挂载（缺则纯 API）+ sidecar spawn 口径

- **背景**：`ui/spec.md` 早已定死 Web = Svelte 单 SPA、Desktop = Tauri 壳 + sidecar（ADR-0014/0015），
  但本仓**从无前端产物**：`build_app` 不挂任何静态文件 ⇒ `serve` 打开根路径 404；
  `DesktopBridge._default_start` 直接 raise ⇒ `core-agent app` 必失败（账本 C8 代码半未落地）。
  同时 `python -m core.entry` 因缺 `__main__` 守卫**静默空转**（退出 0、无输出）—— 若拿它当 sidecar 的调用面，
  壳会「以为拉起来了」而实际什么都没有。
- **决策**：
  ① **产物可选，非硬依赖**：`build_app` 末尾按 `frontend/dist/index.html` 是否存在分流 —— 有则
     `StaticFiles(directory=..., html=True)` 挂 `/`，无则不挂（纯 API 模式）。**为何**：后端本就可独立运行
     （`build_app` 的既有测试不带任何前端产物），`serve` 不该因**没跑过 npm** 而启动失败；这也让 CI 的
     Python 四门与前端构建**彻底解耦**（前端构建归验证节、不归门）。
  ② **挂载注册在最后**：Starlette 的路由按**注册顺序**匹配，显式路由（`/session`、`/llm-config`…）先注册、
     `Mount("/")` 最后注册 ⇒ 既有端点优先命中，不被静态兜底吞掉。该顺序是**契约**，由测试锁死
     （防止将来有人把 mount 提到最前）。
  ③ **产物用相对路径（`base: "./"`）**：同一份 `dist/` 既要被 FastAPI 挂在 `/`，也要能被桌面壳以 `file://`
     加载 —— 绝对路径 `/assets/...` 在 `file://` 下必 404。这是规格「Web 与桌面 100% 一致」的**物理前提**。
  ④ **sidecar spawn 口径与既有子进程执行器一致**（同 `0090` `SubprocessGitBackend` / `0091`
     `SubprocessGateExecutor`）：`subprocess.Popen([...])` **列表形式**（不经 shell 解释 ⇒ 无注入面）、
     `sys.executable` 而非字面量 `python`（sidecar 必须与被拉起方**同解释器**，venv 下 `python` 未必是同一个）、
     失败（`OSError`）归一为 `UiError(UI_SIDECAR_FAILED)` **不静默成功**（否则用户以为桌面起好了）。
     argv 固定为 `-m core.entry serve --host 127.0.0.1 --port <port>`。
  ⑤ **`-m core.entry` 必须真的可运行**：补 `if __name__ == "__main__"` 守卫。调用面存在性由子进程
     `--help` 实测（非 mock），因为「模块能 import」与「模块能当入口跑」是两回事。
- **限制（已知且明示）**：
  - **Rust 壳未纳入四门构建验证**（本环境无 `cargo-tauri`），`src-tauri/` 只做开窗口 / 挂 SPA / 启 sidecar
    三件事，**打包安装包未验证**。
  - 桌面窗口直接指向 sidecar 源（`http://127.0.0.1:<port>`）⇒ 与 Web **同源**、SPA 零改写；代价是
    **端口须一致**（壳侧 `CORE_PORT` / CLI `app --port` 缺省均为 8000），且壳在起窗前需探测端口就绪（已实现）。
  - 设置页的 `${VAR}` 前端校验只是**少一次无谓往返**，**不是安全边界**（后端照样拒明文，见 ADR-0092 ⑤）。
- **影响**：`fastapi_serve` 增 `_DIST_DIR` 常量与末尾静态挂载；新增错误码 `UI_SIDECAR_FAILED`（→ 500）；
  `DesktopBridge` 增 `port` 可选参数（`start_impl` 保持 1 参，既有注入方零改动）；`entry` 增 `app --port`
  与 `__main__` 守卫；新增 `frontend/`（Svelte + Vite）与 `src-tauri/`（Tauri v2）。
- **明确不做**：TTS（账本 C7）与多模态上传（与「LLM 配置能生效」无因果）；引 UI 组件库（原生 Svelte 够用）；
  前端路由库（两页签一个状态足够）。
- **规格**：MODIFIED「Web 界面访问」/「桌面打包」（ui）。

---

## ADR-0094：进化信号走既有 trace 通道（收尾回调 + 模块归因字段），不纳入 `PluginRegistry`

- **背景**：审计发现进化引擎的 **plugin 维度整条接线未打通**：①`EvolutionWorker.on_trace_complete`
  是全仓唯一的 trace 完成登记入口，却**零生产调用方**，而 loop 收尾只调 `cold_path()`（无参、不带
  `trace_id`）⇒ `_completed` 恒空 ⇒ 冷路径在生产永不运行；②`TraceEvent` 无模块字段、`kind` 词表无
  「架构模块失败」通道，`_to_traces` 的 `plugin_id` 绑的是**工具名** ⇒ 即便 trace 通了，loop 自身的
  失败（轮数/token 预算耗尽）也无法归因。原稿曾计划「在 `PluginRegistry` 上加质量信号接口 + `promote`」。
- **决策**：
  ① **不纳入 `PluginRegistry`**（口径裁决）：`PluginRegistry` 全仓只在 `PluginInstaller` 内部默认构造
     （`installable.py:93`），组合根**没有 `registry` 变量**（原稿写法会直接 `NameError`）；`FAULTED`
     只在注册表驱动的 `load/unload` 失败时产生，而内部模块不经它加载 ⇒ 「纳入」买不到任何一条验收，
     反而要给 `evolution.{collector,diagnoser,evaluator,validator,worker}` 5 个零 `generation/schema/
     coeffects` 的算法类补 `load/unload` = `pass` 的**空转生命周期**（**ADR-0054 明确拒绝过的形态**）。
  ② **信号走既有 trace 通道**：`Diagnoser.diagnose` 本就从 `t.plugin_id` 逐条计分 ⇒ **不需要新载体**，
     缺的是**生产端的归因事件**。补三件：收尾回调（让 trace 流进 worker）、模块归因字段（让失败可归因）、
     适配通道（把归因事件采为证据）。
  ③ **回调与冷路径是两个独立节律**：`cold_path` 按 `maintenance_interval`（缺省 900s）节流，语义是
     「跑一轮 cycle」；`trace_observer` 按**轮**、语义是「登记一条已完成 trace」（只登记、不触发、不阻塞）。
     合并会把 `EvolutionTrigger` 的「累计 N 条 trace」退化成「累计 N 个 interval」。
  ④ **回调必须在「本轮全部遥测之后」调用**：`_maintain`（冷路径）在本行**之前**执行 ⇒ 若回调在前，
     同轮 `maybe_run → _collect → clear()`（`worker.py:67`）会消费掉尚未记录 `loop_finished` 的 trace，
     使该事件**永不再被采集**。放在最后 ⇒ 本 trace 由**下一次**冷路径机会消费，事件完整。
  ⑤ **`module_id` 是可选字段**（dataclass 默认 `None`）：既有四类 `kind` 的记录 / 序列化 / 消费语义
     **逐字不变**；`kind` 词表**不扩**（`module_id` 是「谁」、`kind` 是「什么事」，二者正交）。
  ⑥ **只接一处、只注入主 loop**：本 change 只让 loop 在**自身失败**时写 `module_id="loop.default"`；
     只注入主 loop 的回调（子 agent / 神兽 / 宠物 loop 不注入）——`_completed` 是**无锁列表**，
     避免多 loop 并发追加。
- **限制（已知且明示）**：
  - **工具级 trace 仍缺**：`action_completed` 作为 `LoopEvent` 外发却**不 `_trace`**，
    `TraceLogger.log_tool_call` 零生产调用方 ⇒ evolution 的 **skill 分支在产线仍无输入**
    （技能维度主线由 `turn_observer` → SOP/技能反馈承载，未断）。**转出账本**，本 change 不做。
  - **13 个内部模块未纳入注册表**：等「真的会产出新一代插件实现（模型生成代码 / 人工提交补丁 → 新
    `Plugin` 对象）」那个 Phase 再做——那时 `promote(plugin: Plugin)` 才有语义。
  - **未达 `EvolutionTrigger` 阈值时 `_completed` 会缓慢累积**（每轮一条）：这是**既定语义**
    （热路径只登记），由下一次触发统一消费。
- **影响**：`TraceEvent` 增 `module_id: str | None = None`；`DefaultLoop` 增 `trace_observer` 注入面与
  `_notify_trace_complete`，`_trace` 增可选 `module_id`，`loop_finished` 失败轮带归因；
  `EvolutionWorker._to_traces` 增模块归因通道（`task_type="module_health"`）；
  `build_runtime` 在主 loop 注入 `worker.on_trace_complete`（evolution 关闭时不注入）。
- **规格**：MODIFIED「执行循环」（loop）/「全链路日志」（observability）/「经验采集」（evolution）。

---

## ADR-0095：归因驱动提案 kind + 架构级结晶结局诚实化（`accepted` 而非 `published`）

- **背景**：ADR-0094 让 trace 带上**模块归因**（`plugin_id=<内部核心模块 id>`），但归因在**提案阶段被
  抹平**：①`Proposer.__init__(*, kind: Literal["skill","plugin"] = "skill")` 把 `kind` **静态固化**，
  `risk_level` 同点派生（`proposer.py:35`），而组合根 `Proposer()` **不传参**（`runtime.py:450`）⇒
  产线**每一个候选都是 `skill`/`low`**，模块归因白白流失；②`_crystallize_plugin` 只往 L3 写一条
  `MemoryEntry`，却返回 `EvolutionOutcome(status="published")`（`engine.py:271`）⇒ CLI 打印
  「已确认并发布：published」（`entry.py:1022`），而**没有任何可发布产物**。
- **决策**：
  ① **`kind` 由诊断归因驱动**：新增归因白名单 `INTERNAL_PLUGIN_IDS`（13 个内部核心模块 `plugin_id`，
     `evolution/plugin_ids.py`）——`target_plugin` 命中 ⇒ `plugin`/`high`，否则 ⇒ `skill`/`low`。
     原构造参数降级为**显式覆盖**（`kind=None` 表示按归因判定），既有 `Proposer(kind=…)` 调用语义不变。
  ② **取「枚举白名单」而非前缀启发式**（`loop.*` / `evolution.*` 前缀 + 排除）：前缀规则要靠**否定表**
     兜住 `composition.*` / `im.gateway` / `memory.store` 等非同族成员，判定逻辑随之变成「白名单 + 黑名单
     + 例外」，可读性与可验证性都更差；枚举是**单一真源 + 逐元素一致性用例**（扫全仓
     `plugin_id = "..."` 声明比对，新增模块漏登记即红）。
  ③ **常量落在 `evolution` 包内**（不在 `runtime` / `observability`）：它是**进化引擎的归因判据**，
     唯一消费者是 `Proposer`；放组合根会让 `runtime` 反向依赖领域知识，放 `observability` 会把
     「谁算架构模块」的**政策**塞进**机制**层。
  ④ **架构级结晶结局为 `accepted`**（新词，`EvolutionOutcome.status` 词表 +1）：语义 = **人工已批准、
     待人工实施**。本仓**没有**「自动生成并装配新一代 `Plugin` 对象」的生产者（见 ADR-0094 限制②），
     所以批准**确实**不产出任何发布物 —— 那就**不谎报 `published`**。技能级分支**一字不动**（确有技能入库
     ⇒ 仍 `published`）。
  ⑤ **不复用既有词**：`pending` 语义是「未确认」、`manual` 语义是「系统级 / 无人可归因」，复用会让
     下游（CLI / UI / 台账）**无法区分「已批准待实施」与「尚未确认」** —— `accepted` 是**新状态**，
     需要新词。
  ⑥ **L3 留痕与观察期开窗保留**：`accepted` 只改**结局词**，不改副作用（候选仍写 L3，仍开观察窗口）。
     观察期判的是「批准/发布之后是否回归」，与是否有产物**无关**。
  ⑦ **`accepted` 不回灌 `run_cycle`**：`run_cycle` 的结局停留在 `pending`（未确认），`accepted` 只从
     `crystallize` 产出 ⇒ 不改任何**自动**路径的判定（人工门一步不放宽）。
- **限制（已知且明示）**：
  - **架构级候选仍无「实施」能力**：`accepted` 的诚实化只解决「不谎报」，**不**制造实现生产者；
    真正落地仍需「模型生成代码 / 人工提交补丁 → 新 `Plugin` 对象」的 Phase（同 ADR-0094 限制②）。
  - **`INTERNAL_PLUGIN_IDS` 是归因白名单，不是 `PluginRegistry` 成员名单**（无注册表驱动的
    `load`/`unload` 生命周期）；命名空间与工具 id（`tools.*`）互不相交。
- **影响**：新增 `src/core/evolution/plugin_ids.py`；`Proposer.__init__` 签名 `kind: … | None = None`、
  `propose` 内归因判定；`_crystallize_plugin` 返回 `accepted`；`EvolutionOutcome.status` 词表 + `accepted`；
  `entry._evolve_confirm` 结局文案按分支（架构级「已批准（待人工实施）」）；既有 4 处架构级断言改
  `accepted`（`test_evolution.py` / `test_phase15.py` / `test_evolution_pending.py` ×2）；新
  `tests/test_evolution_attribution.py`（7 例）。
- **规格**：MODIFIED「模块级提案」/「架构级候选强制人工审批（HITL confirm gate）」（evolution）。

---

## ADR-0096：trace 生命周期**责任分区**（Tracer 只保在途、留存归消费者），非环形缓存 / 推送 sink

- **背景**：`Tracer` 的 `_events` **只增不减** —— `end_trace` 只 `emit` 不清理（`tracer.py:39-43`，原实现）
  且 `loop` 收尾从不调 `end_trace`（`loop/default.py` 收尾块无该调用）⇒ ①每轮 trace 的事件**永久驻留**
  （**无界内存增长**）；②导出器这条**落盘真路径在生产上从未被打通**（只有测试显式调 `end_trace`）。
  但「`end_trace` 直接 `pop`」会**静默回退** change 0101/0102：`EvolutionWorker.on_trace_complete` 只
  **登记 id**，真正的 `replay` 发生在**下一次冷路径** `maybe_run → _collect`（`worker.py:85`），而收尾
  顺序是「消费上一批 → 记 `loop_finished` → 回调登记本轮」⇒ 收尾 `pop` 时**本轮事件尚未被读取**。
- **决策**：
  ① **责任分区**：`Tracer` 只保留**在途**（未封口）链路；`end_trace` = `emit` + `pop`（交付导出器 +
     释放内存）；**已完成**链路的留存归**消费者**——`EvolutionWorker.on_trace_complete` 在**回调时刻**
     取 `replay` **快照**自持，`_collect` 遍历快照（不再回读 Tracer）。
  ② **`replay` 口径收窄为「在途」**：已完成任务的**事后回溯以落盘遥测（JSONL）为真源**。理由：回溯的
     价值在**事后复盘**，而这正是导出器存在的目的（本 ADR 干的就是打通它）；且本仓一贯**不留双真源**
     （参见 phase-19 E19 裁决）；用户面无任何 `replay` 读者（无 CLI / UI）。
  ③ **收尾顺序成为规格约束**：「记录本轮全部遥测 → trace 完成回调 → `end_trace` 封口」，**反序**会让
     回调回放空链路 ⇒ 进化证据链**静默**回退 `no_evidence`（单测全绿）。故 loop 规格写明顺序，并加
     回归守护用例（`test_loop_seals_after_trace_observer_snapshot`）。
  ④ **不采纳「有界环形缓存保留最近 N 条已完成」**：新增 `N` 旋钮 + 淘汰语义，而 `N` **只为测试存在**
     （消费者已走快照）⇒ 无生产消费者的可配性，且制造**内存 + 落盘双真源**。
  ⑤ **不采纳「`end_trace` 直接推送 sink / observer」**：「谁封口谁通知」形式更整齐，但要**推翻刚发布的
     0101 接线与 ADR-0094**（拆掉 loop 的 `trace_observer`），内存特性与采纳方案**完全相同** ⇒ 纯审美收益。
  ⑥ **`Exporter` 协议不增 `flush`**：协议面只有 `emit`（`exporter.py:22-25`），`BufferedExporter.emit`
     内部即 flush（`:83-89`）⇒ `end_trace` 只需 `emit(events)`（订正 phase-22 §2.2 步骤 4 的「→ flush」措辞）。
  ⑦ **不改 evolution 的批触发语义**：`EvolutionTrigger(threshold=10)` 要第 10 次 `maybe_run` 才真跑、
     `_completed.clear()` 只在真跑后执行，这是**有意**的批语义（攒够再驱动一次 cycle）。但快照让
     `_completed` 由「id 列表」变「事件列表」，内存曲线**变重** ⇒ 验收须含**有界断言**（不随轮次无界增长）。
- **限制（已知且明示）**：
  - **`end_trace` 后 `record` 到已封口 id 会重建条目**（`record` 用 `setdefault`）：本 change 不额外设防，
    依赖驱动方（loop）按序调用；错序行为由规格 + 回归用例守护。
  - **事后回溯须读落盘**：`Tracer.replay` 不再服务已完成链路，需跨进程 / 事后复盘时读
    `$CORE_STATE_DIR/traces.jsonl`（本 change 未新增读回 API）。
- **影响**：`observability/tracer.py`（`end_trace` 改 `pop`、docstring / 模块 docstring 口径）；
  `loop/default.py`（新增 `_start_trace` / `_end_trace`，`astream` 开轮改用、收尾在回调后封口）；
  `evolution/worker.py`（`_completed: list[list[TraceEvent]]`、回调取快照、`_collect` 遍历快照）；
  测试迁移（`test_observability.py` / `test_loop.py` / `test_phase13.py` / `test_evolution*.py`，
  由「封口后 `replay` 断言」改为「捕获导出器断言」；`_RecordingTracer` 桩补生命周期面）。
- **规格**：MODIFIED「链路追踪」（observability）/「执行循环」（loop）。

---

## 变更追踪

| 编号 | 关联文档 |
|---|---|
| ADR-0001 ~ 0003 | 03-interfaces/plugin-registry-interface.md |
| ADR-0004 | 02-modules/memory.md |
| ADR-0005 | 02-modules/evolution.md |
| ADR-0006/0008 | 05-development/development-guide.md |
| ADR-0007 | 02-modules/mcp.md |
| ADR-0009 | 02-modules/permission.md |
| ADR-0010 | 02-modules/observability.md |
| ADR-0011 | 02-modules/skills.md |
| ADR-0012 | 02-modules/context.md |
| ADR-0013 ~ 0015 | 06-ui-frontend/ui-architecture.md |
| ADR-0016 ~ 0017 | 07-mcp-server/mcp-server.md |
| ADR-0018 ~ 0020 | 08-im-gateway/im-gateway.md |
| ADR-0021 | 02-modules/llm-provider.md |
| ADR-0022 ~ 0023 | 09-distributed/distributed.md |
| ADR-0024 | 02-modules/composition.md |
| ADR-0025 | 11-rag/rag-architecture.md |
| ADR-0026 | 12-git/git-architecture.md |
| ADR-0027 | 01-architecture/data-model.md |
| ADR-0028 | 03-interfaces/deployment-interface.md |
| ADR-0029 | 02-modules/core-profile.md |
| ADR-0030 | 02-modules/orchestration.md |
| ADR-0031 | 02-modules/deployment.md |
| ADR-0032 | 02-modules/durability.md |
| ADR-0033 | 02-modules/llm-provider.md, 02-modules/tool-use.md, 02-modules/loop.md, 02-modules/orchestration.md |
| ADR-0034 | 02-modules/llm-provider.md, 06-ui-frontend/ui-architecture.md, 08-im-gateway/im-gateway.md, 12-git/git-architecture.md |
| ADR-0035 | 02-modules/skillhub.md, 02-modules/skills.md |
| ADR-0036 | 03-interfaces/ci-cd-interface.md |
| ADR-0037 | 03-interfaces/plugin-registry-interface.md, 03-interfaces/mcp-interface.md, 03-interfaces/tool-use-interface.md |
| ADR-0038 | 03-interfaces/cli-ops-interface.md, 03-interfaces/configuration-interface.md, 03-interfaces/permission-interface.md |
| ADR-0039 | 03-interfaces/pet-mode-interface.md |
| ADR-0040 | 03-interfaces/rag-interface.md, 03-interfaces/mcp-interface.md, 03-interfaces/git-interface.md |
| ADR-0041 | 03-interfaces/beast-mode-interface.md |
| ADR-0042 | 03-interfaces/judgment-interface.md |
| ADR-0043 | 03-interfaces/mcp-interface.md |
| ADR-0044 | 03-interfaces/llm-provider-interface.md |
| ADR-0045 | 03-interfaces/memory-interface.md, 03-interfaces/configuration-interface.md |
| ADR-0046 | 03-interfaces/memory-interface.md, 03-interfaces/context-interface.md, 03-interfaces/loop-interface.md |
| ADR-0047 | 03-interfaces/memory-interface.md, 03-interfaces/loop-interface.md |
| ADR-0048 | 03-interfaces/skills-interface.md, 03-interfaces/loop-interface.md |
| ADR-0049 | 03-interfaces/skills-interface.md, 03-interfaces/judgment-interface.md, 03-interfaces/context-interface.md |
| ADR-0050 | 03-interfaces/skills-interface.md, 03-interfaces/loop-interface.md |
| ADR-0051 | 03-interfaces/evolution-interface.md, 03-interfaces/permission-interface.md, 02-modules/evolution.md |
| ADR-0052 | 03-interfaces/evolution-interface.md, 02-modules/evolution.md |
| ADR-0053 | 03-interfaces/skills-interface.md, 02-modules/skills.md |
| ADR-0054 | 03-interfaces/evolution-interface.md, 03-interfaces/loop-interface.md, 02-modules/evolution.md |
| ADR-0055 | 03-interfaces/loop-interface.md, 03-interfaces/constraints-interface.md, 02-modules/constraints.md |
| ADR-0056 | 03-interfaces/pet-mode-interface.md, 02-modules/pet.md |
| ADR-0057 | 03-interfaces/mcp-interface.md, 03-interfaces/permission-interface.md, 02-modules/mcp.md |
| ADR-0058 | 03-interfaces/evolution-interface.md, 02-modules/evolution.md |
| ADR-0059 | 03-interfaces/configuration-interface.md |
| ADR-0060 | 03-interfaces/beast-mode-interface.md, 02-modules/beast-mode.md |
| ADR-0061 | 03-interfaces/skills-interface.md, 02-modules/skills.md |
| ADR-0062 | 03-interfaces/constraints-interface.md, 03-interfaces/tool-use-interface.md, 02-modules/constraints.md, 02-modules/tool-use.md |
| ADR-0063 | 03-interfaces/configuration-interface.md, 02-modules/configuration.md |
| ADR-0064 | 03-interfaces/llm-provider-interface.md, 02-modules/llm-provider.md |
| ADR-0065 | 03-interfaces/configuration-interface.md, 02-modules/configuration.md, 02-modules/pet.md, 02-modules/beast-mode.md |
| ADR-0066 | 03-interfaces/constraints-interface.md, 03-interfaces/configuration-interface.md, 02-modules/constraints.md |
| ADR-0067 | 03-interfaces/configuration-interface.md |
| ADR-0068 | 03-interfaces/permission-interface.md, 03-interfaces/configuration-interface.md, 02-modules/permission.md |
| ADR-0069 | 03-interfaces/configuration-interface.md, 02-modules/configuration.md |
| ADR-0070 | 03-interfaces/mcp-interface.md, 02-modules/mcp.md, 07-mcp-server/mcp-server.md |
| ADR-0071 | 03-interfaces/mcp-interface.md, 02-modules/mcp.md, 02-modules/cli-ops.md |
| ADR-0072 | 03-interfaces/mcp-interface.md, 02-modules/mcp.md, 07-mcp-server/mcp-server.md |
| ADR-0073 | 03-interfaces/mcp-interface.md, 02-modules/mcp.md, 07-mcp-server/mcp-server.md |
| ADR-0074 | 03-interfaces/mcp-interface.md, 02-modules/mcp.md |
| ADR-0075 | 03-interfaces/configuration-interface.md, 00-product/user-guide.md |
| ADR-0076 | 03-interfaces/pet-mode-interface.md, 02-modules/pet.md |
| ADR-0077 | 03-interfaces/pet-mode-interface.md, 02-modules/pet.md |
| ADR-0078 | 03-interfaces/pet-mode-interface.md, 02-modules/pet.md, 00-product/user-guide.md |
| ADR-0079 | 03-interfaces/evolution-interface.md, 02-modules/evolution.md, 00-product/user-guide.md |
| ADR-0080 | 03-interfaces/configuration-interface.md |
| ADR-0081 | 03-interfaces/pet-mode-interface.md, 02-modules/pet.md |
| ADR-0082 | 03-interfaces/pet-mode-interface.md, 02-modules/pet.md |
| ADR-0083 | 03-interfaces/pet-mode-interface.md, 02-modules/pet.md, 03-interfaces/ui-interface.md |
| ADR-0084 | 03-interfaces/observability-interface.md, 02-modules/observability.md |
| ADR-0085 | 03-interfaces/git-interface.md, 12-git/git-architecture.md |
| ADR-0086 | 03-interfaces/ci-cd-interface.md, 02-modules/ci-cd.md |
| ADR-0087 | 03-interfaces/skillhub-interface.md, 02-modules/skillhub.md |
| ADR-0088 | 03-interfaces/plugin-registry-interface.md |
| ADR-0089 | 03-interfaces/ui-interface.md |
| ADR-0090 | 03-interfaces/permission-interface.md |
| ADR-0091 | 03-interfaces/configuration-interface.md, 03-interfaces/loop-interface.md |
| ADR-0092 | 03-interfaces/ui-interface.md |
| ADR-0093 | 06-ui-frontend/ui-architecture.md |
| ADR-0094 | 03-interfaces/observability-interface.md, 03-interfaces/loop-interface.md, 03-interfaces/evolution-interface.md |
| ADR-0095 | 03-interfaces/evolution-interface.md |
| ADR-0096 | 03-interfaces/observability-interface.md, 03-interfaces/loop-interface.md, 03-interfaces/evolution-interface.md |
