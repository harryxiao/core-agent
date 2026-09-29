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
- **后果**：✅ 更换任意三方模块仅新增适配器、不动架构，替换语义可被「替换 X → 调用方零改动」测试锚点验证（llm-provider 已有 TC-LLM-03、im 已有 TC-IM-01，rag/mcp/git 待补）；⚠️ MAL 是约定而非强制机制，需接口文档与 spec 持续自查；后续新增三方边界（ui 的 FastAPI、im 的平台 SDK、git 的底层库）须按四条落契约。

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
- **决策**：新增横切 capability judgment——① 决策原语抽象：choice（选项路由）/score（评分筛选）/noul（空判断）三类原语作为统一决策入口，供 loop/orchestration/evolution 决策点调用；② JEVProvider 懒加载，经 api_key/base_url/model 建 HTTP 客户端，适配 System One 协议（state + typed questions → typed answers + probability + confidence），不新增三方依赖（JEV 为 HTTP API）；③ DecisionRouter（loop 决策点用 choice）、Compactor（记忆压实用 score）、Guardrail（约束守卫用 noul）三处接线；④ 置信度回退：confidence 低于配置阈值回退主 LLM 重新决策，并标注回退轨迹；⑤ 决策审计：每次决策轨迹（输入 state、原语类型、选项、结果、置信度、是否回退）落 observability 链路。
- **后果**：✅ 决策点从生成式 LLM 解耦，获得结构化置信度 + 可回退下限 + 决策轨迹可审计（供进化/审批消费）；⚠️ 决策小模型只适用「选择/评分/空判断」结构化决策，开放生成仍走主 LLM；JEV 为外部 HTTP API，需网络可达与密钥配置，无内置兜底（低置信度回退主 LLM 即为质量下限保障）。

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
