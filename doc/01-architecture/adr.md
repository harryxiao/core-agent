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
     coeffects` 的算法类补 `load/unload` = `pass` 的**空转生命周期**（**订正**：原括注「ADR-0054 明确
     拒绝过的形态」为**误引** —— ADR-0054 讲冷路径驱动面；实质依据即本决策三条论证，见 ADR-0100）。
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
    （技能维度主线由 `turn_observer` → SOP/技能反馈承载，未断）。**转出账本**，本 change 不做
    （**已由 ADR-0100 关闭**：生产者接线到 loop 非终止动作分支）。
  - **13 个内部模块未纳入注册表**：等「真的会产出新一代插件实现（模型生成代码 / 人工提交补丁 → 新
    `Plugin` 对象）」那个 Phase 再做——那时 `promote(plugin: Plugin)` 才有语义
    （**ADR-0100 裁决：不纳入** —— 重开条件即本条所述的生产者）。
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

## ADR-0097：rag 主链路接线用 stdlib `sqlite3` 落盘向量库；维度不一致**拒绝**而非静默截断

- **背景**：①rag 的 7 个类（`VectorStore` / `IngestionPipeline` / `Embedder` / `Retriever` /
  `RagGenerator` 等）**零生产调用方** —— 组合根不装配、CLI 无入口（死代码）；②规格「默认实现为
  `sqlite-vec`」离线**不可得**（需另行安装的扩展），且「与既有 SQLite 生态统一」的前提**为假**
  （全仓 `src/` 无任何 sqlite 使用）；③`_cosine_similarity` 用 `zip(a, b, strict=False)` ⇒ 维度不同的
  两向量**静默按短边截断**比较，产出无意义相似度 —— 而「先离线 ingest（128 维 HashEmbedder）、后配
  `llm.embedding_model` 再 search」是**可达**路径；④`IngestionPipeline._hashes` 是**进程内** dict，而
  CLI 每次调用都是新进程 ⇒ 增量判定形同不存在（每次全量重建 + 重新 embedding）；⑤`llm.api_key` /
  `provider` / `model` / `endpoint` 是 `validate_schema` 的**必需**项 ⇒ 空配置必然 `ConfigurationError`，
  `build_runtime` **走不到「未配 LLM」**（草案里「未配置 LLM 的 `rag ask` 报错」在装配链上不可达）。
- **决策**：
  ① **落盘用 stdlib `sqlite3`**（`SqliteVectorStore`），而非三方 `sqlite-vec`（离线不可得 + 违反「尽量
     不依赖三方库」）、亦非 JSON 文件（向量以浮点数组整文件重写，每次 `put` 全量重写、随规模退化）。
     表结构 = `chunks`（块 + 向量 BLOB）/ `documents`（文档内容指纹）/ `meta`（`dim`），落盘
     `$CORE_STATE_DIR/rag-index.db`；行级写入与 `DELETE WHERE doc_id` 天然支持增量重建。
  ② **维度守护**：首个 `put` 定档 `meta.dim`，此后 `put`/`search` 维度不符即
     `RAGError(INDEX_CORRUPT, "… 须重建索引")` —— **不**静默截断（备选「静默跳过异维块」会让检索**静默
     变空**，更难诊断；「各存各维度混用」则跨维度余弦无意义）。
  ③ **文档指纹随索引落盘**（`documents` 表）：`VectorStore` 抽象补 `record_document` / `document_hash`，
     hash 判定改由**存储侧**承载 ⇒ 跨进程成立、单一真源（删进程内 `_hashes`）。`ingest` 语义合并为
     **upsert**（返回本次写入块数，无变更 ⇒ 0），`refresh` 退化为 `ingest(...) > 0` 的布尔外壳；
     embedding 失败仍发生在 `delete` **之前**（旧索引降级契约不变）。
  ④ **`RagService` 门面收口装配**：`core/rag/service.py` 组合 `IngestionPipeline` + `Retriever` +
     可选 `RagGenerator`，组合根装配挂 `runtime.rag`、CLI（`rag ingest|search|ask`）只调用门面 ——
     不让装配知识渗进 CLI 层、也不与 `runtime` 形成两处真源。生成器缺失（服务层未装配）⇒ 新错误码
     `GENERATION_UNAVAILABLE`（**不**借 `EMBEDDING_FAILED` 误标、**不**抛裸 `RuntimeError`）。
  ⑤ **embedding 语义优先、离线降级**：配 `llm.embedding_model` ⇒ `LLMEmbedder`（与 memory 通路共用同一
     `embed_provider`，不重复构造 provider）；未配 ⇒ `HashEmbedder` 离线降级基线 + CLI 打印降级提示。
     依据 memory 既有裁决（`HashEmbedder` 是降级基线不完善，语义走 `LLMEmbedder`，**不引入本地语义模型**）。
  ⑥ **明示不做**：不把 RAG 注入 loop 推理链（属特性，牵动 context 预算与 prompt 装配）；不做 ANN
     （规模未到门槛，保持暴力余弦）；不做索引并发隔离。
- **限制（已知且明示）**：
  - **单进程假设**：`SqliteVectorStore` 未开 WAL、无跨进程写互斥（并发 ingest 同一索引无隔离保证）。
  - **暴力余弦**：检索复杂度 O(N)（全表扫描 + 进程内打分），规模上量须换 ANN 实现（经抽象替换）。
  - **「无生成器」的可达面是服务层**：CLI 装配链因 LLM 配置必需而**总有**生成器；该错误码由
    `RagService` 的 API 面承载，CLI 只做「结构化错误 → stderr + 退出码 1」的统一收口。
  - **`HashEmbedder` 检索质量是降级基线**：仅字符 n-gram 相似度，语义召回弱于 embedding 模型；
    且其 128 维与远端模型维度不同 ⇒ 换后端须重建索引（由 ② 的拒绝行为强制暴露，不静默错算）。
- **影响**：`rag/vector_store.py`（`SqliteVectorStore` + 抽象补两法 + `InMemoryVectorStore` 同步）、
  `rag/service.py`（新）、`rag/errors.py`（+`GENERATION_UNAVAILABLE`）、`rag/ingest.py`（upsert 化）、
  `rag/__init__.py`（导出）；`runtime.py`（`_rag_index_path()`、`embed_provider` 提前共用、`Runtime.rag`）；
  `entry.py`（`rag` 命令族 + `_HANDLERS`）；测试（`tests/test_rag.py` 追加、新 `tests/test_rag_wiring.py`）；
  **文档失真订正**：`02-modules/rag.md`、`11-rag/rag-architecture.md`、`00-product/requirements.md`
  （CORE-RAG-R1/R3）、`04-testing/test-cases.md`（TC-RAG-04/10）、`doc/README.md` 索引行。
- **规格**：MODIFIED「本地向量库存储」「本地 Embedding」「存储与 Embedding 依赖注入隔离」（rag）；
  MODIFIED「运维命令集」（cli-ops）。

---

## ADR-0098：skillhub 供给侧接线以**落盘目录为单一真源**（删 `_published`）+ 发布即制品入库；不加 `published` 消费闸门

- **背景**：①供给侧三件套（`SkillPublisher.publish` / `review`、`MarketIndex.put`）**零生产调用方** ——
  组合根不装配、CLI 无入口（死代码）；②而 CLI 是**一次性进程**，供给侧的**两处状态都在进程内**：
  `MarketIndex._sources`（内存 dict）与 `SkillPublisher._published`（`skill_id → source` 内存 dict）
  ⇒ 上个进程 `publish` 的条目下个进程 `search` 看不到、下个进程 `review` 判「未发布」。
  ⇒ **只补 CLI 入口不解决问题**，会得到一条「看似闭环、实则每步空转」的链路（同 change 0074
  mcp 端点、change 0104 rag `_hashes` 的同一教训）；③`review` 的 `_published` 是**第二真源** ——
  「发布到哪个源」这个事实**已经写在目录里**（`MarketSkill.source` 随条目落盘）；④目录按规格只存元数据
  （「不拉取完整技能体」），而消费侧 `download` 需要 fetcher 提供技能体 ⇒ 本地市场需要**制品库**。
- **决策**：
  ① **目录落盘**：`MarketIndex(path=…)`，形状 `{"sources": {<name>: {"skills": {<id>: <dict>}}}}`，
     经 `core.persistence.write_state` 原子写；`put()` 即落盘且为**唯一写路径**（发布与审核共用，
     不新增 `save()` 第二入口）。装载缺失 → 静默空态；损坏 / 结构不符 → `warnings.warn` **降级为空目录**
     （同 0064/0074 口径：状态损坏不阻断启动）；装载后恒 `setdefault("official", …)`。
     缺省 `path=None` ⇒ 纯内存，**既有单测与组合根行为逐字不变**。
  ② **删 `SkillPublisher._published`**，`review` 改为 `index.locate(skill_id)` 跨源定位（未找到 ⇒
     `SKILL_NOT_ACTIVE`，**错误码与语义不变**，既有用例仍绿），改动后经 `index.put` 回写。
     `locate` 是**查找**不是路由 ⇒ 不做健康探测。
  ③ **发布 = 元数据上架 + 制品入库**：`SkillPublisher(artifacts: SkillLibrary | None)`，制品入库放在
     `publish` **内部**（否则「发布」语义散成两处，别的发布入口必漏）。顺序：先 `index.put`
     （源不存在即 `SOURCE_NOT_FOUND`，**此时不留半份制品**）再 `artifacts.register(replace(skill))`
     —— 存**副本**，避免审核改写波及其他持有者（本地技能库）。
  ④ **审核通过同步制品并重新签名**：注入 `artifacts` 时把制品本体 `version` 提升到市场版本后再
     `verifier.sign(body)` 覆盖 `market.signature` ⇒ 市场签名与制品内容**始终一致**，末端验签
     （`download` 的 `verify(skill, market.signature)`）仍成立；制品库缺席时仅目录版本提升。
     `VersionManager` 的 `path` 落盘于 `$CORE_STATE_DIR/skill-versions.json`（与组合根同源）⇒ 审核跨进程可续。
  ⑤ **明示不做**：
     - **`published` 消费闸门**（install 仅限已审核技能）：phase-22 §4.2 验收序列为
       publish → search → install（**中间无审核步骤**），且既有 CLI 用例市场项状态非 `published`
       ⇒ 加闸门是**新增契约**而非「接线」。
     - **`skill market list` 子命令**：`MarketIndex.list` 已在生产路径上（`SkillHubClient.search` 内部调用）。
     - **新错误码**：既有 `SIGNATURE_INVALID` / `SKILL_NOT_ACTIVE` / `SOURCE_NOT_FOUND` / `PUBLISH_REJECTED` 已足。
     - **远端市场 fetcher**（网络 + 凭据）：仍为**凭证半**；本次接的是**本地**市场制品库（离线、零凭据）。
- **影响**：`skillhub/index.py`（`path` + `_load/_persist` + `locate`、`put` 落盘）、
  `skillhub/publisher.py`（删 `_published`、`artifacts` 注入、`_sync_artifact` 重签名）；
  `entry.py`（`_build_market_index` / `_build_market_artifacts` / `_build_publisher` / `_market_fetcher`
  + `_build_skillhub_client` 注入 + `skill publish` / `skill review` 子命令）；
  测试（`tests/test_skillhub.py`、`tests/test_skillhub_cli.py` 追加，含跨进程续接与制品篡改反例）；
  文档（`03-interfaces/skillhub-interface.md` §2/§3/§4、`02-modules/skillhub.md` §3.1/§3.3/§4、
  `04-testing/test-cases.md` TC-SKH-*、`coding-plan/contracts_summary.md`）。
- **规格**：MODIFIED「技能市场与技能发现」「签名校验与可信下载」「技能发布与审核流」（skillhub）。

---

## ADR-0099：`notes` 作为 L2 **文档化真相层**（canonical Markdown，不建向量库）；Consult 走 loop 只读钩子、Update 复用既有收尾观察者

- **背景**：三个缺口 —— ①**没有文档化真相层**：记忆中只有 RAG 的**扁平切片**（`MemoryStore` +
  `FileBackend`，按分数取片段），没有「一篇一主题、可人读可 diff、最新即权威」的载体；
  ②**没有循环纪律载体**：Consult → Build → Update 无处落地（读了什么、写回哪、谁保证不重不漏）；
  ③**外部插件装不上**：`PluginRegistry` 是**进程内注册表**，外部「operator-memory」类插件无装载面。
  ⇒ 决策：做成**第一方能力**（而非等外部插件）。
- **决策**：
  ① **新增 L2 能力包 `src/core/notes/`**（models / backend / store / errors），**不并入 `memory`**：
     真相层与切片层是**两种读法**（前者「按主题读全篇」，后者「按分数取片段」），合并会让
     `MemoryStore` 背上两套语义。`rag` 仍是检索底座，**本次零改动**。
  ② **canonical = 单目录 Markdown，一篇一文件**（缺省 `$CORE_STATE_DIR/notes`）：H1 标题 +
     `- id/- tags/- source/- updated_at` 元数据 + `## Search Queries`（词法关键词）+ `## Notes` 正文。
     渲染 / 解析互为逆（同一解析器还原全部字段 ⇒ **不丢字段**）。
     **MVP 不切三分区**（人写区 / 沉淀区 / 归档区在无真实用户前是空壳）。
  ③ **后端实现既有 `MemoryBackend` Protocol，签名与语义不改**：`put` **覆盖式**（同主题二次写 =
     第二次内容，不拼接 —— 「最新最权威」是**有意**语义），先写 `*.md.tmp` 再 `os.replace`
     （**原子**：替换前中断不留半截 canonical 文件）。缺省后端可换（Protocol 注入）⇒ 不绑死文件系统。
  ④ **检索保持纯词法，不建向量库**：标题 / tags / `## Search Queries` / 正文按
     `命中词数 ÷ 词数` 打分降序。**中文按 2-gram 切词**（CJK 无词界，整词包含会让「部署流程怎么走」
     这类**任务句**几乎永不命中 ⇒ 实现期实测后修正），英文与非 CJK 段保持整词包含。
     切词只在 `MarkdownBackend` 内，**不动 `skills` 的路由口径**。
  ⑤ **Consult 走 loop 的只读钩子**：`NotesConsult = Callable[[str], str]`（loop 不 import notes ——
     架构红线，生产侧注入组合根闭包 `NoteStore.digest`）。摘要在**任务前**写入 `LoopContext.notes`
     （**加法字段**，缺省空串 ⇒ 不注入），由 `LLMPlanner._system_prompt` 渲染为「相关笔记」块。
     **不自动全量注入正文**：digest = 命中笔记节选（每篇 ≤200 字符）+ 全量**标题清单**，总量
     ≤1200 字符（token 有界）。钩子抛错**只降级留痕**（`notes_consult_failed`），不改本轮结局。
  ⑥ **Update 复用既有 `TurnObserver`，不新增第二个收尾钩子**：成功轮的（任务, 行动/结果序列）
     已经过该钩子 ⇒ 再开一条「笔记写回」回调会得到**两个节律、两处真源**。`NoteStore.observe_turn`
     把「解决过程」覆盖式写回 `slug_topic(task)` 主题；**失败轮不写**（失败信号仍归技能迭代），
     空 slug 跳过（不写盘、不报错）。
  ⑦ **内置循环技能由组合根构造**（`skills.<area>.<name>` 口径的 `skills.notes.consult_build_update`
     注册进 `SkillLibrary`），**不下沉 `notes` 包** —— 否则 L2 真相层**向上依赖 L3 skills**
     （已有架构用例固化该红线）。
  ⑧ **明示不做**：**feature gate**（`notes` 恒装配，不入 `GATABLE_MODULES` —— 真相层不是可选玩法）；
     `plugin_registry` 纳入内部模块（欠账见 phase-21 §1.4②，本 change 不夹带）；`MemoryStore` /
     `FileBackend` / `rag` 改动；`operator-memory` 本体；CLI 之外的写入口。
  ⑨ **连带登记**：`INTERNAL_PLUGIN_IDS` **13 → 14**（+ `notes.store`）—— 该白名单与仓内
     `plugin_id = "..."` 声明**逐元素一致**（0102 的守护用例）；不对称登记会让 `notes.store` 的
     缺陷被误归因为「技能级」而绕过人工审批。
- **影响**：新增 `src/core/notes/`（models / backend / store / errors）；`loop/default.py`
  （`NotesConsult` 别名 + `_consult_notes` + ctor kwarg）、`loop/protocol.py`（`LoopContext.notes`）、
  `loop/planner.py`（「相关笔记」块）、`runtime.py`（`_notes_path` / `_notes_workflow_skill` /
  `note_store` 装配 + 三处 `DefaultLoop` 注入）、`entry.py`（`notes list|show|search`）、
  `evolution/plugin_ids.py`（+1 id）；测试（`tests/test_notes.py`、`tests/test_notes_loop.py`，
  `tests/test_architecture.py` 反向依赖集 + `notes`，`tests/test_phase13.py` 桩打分器改为**按 id 点名**）；
  文档（`03-interfaces/notes-interface.md`、`02-modules/notes.md`、`04-testing/test-cases.md` TC-NOTE-*、
  `coding-plan/contracts_summary.md`）。
- **已知局限**：①digest 只保证「命中 + 清单」，**无相关性保证**（词法可负相关）；②`_score`
  对标题与正文**同权**，长正文易压过标题命中（**已由 ADR-0100 分区加权关闭**）；③覆盖式更新**无历史版本**（回溯交给 git）；
  ④`observe_turn` 以任务首行 slug 定主题 ⇒ 措辞不同的同一任务会**另起主题**（主题分裂优于
  覆写他人结论的错合并）；⑤`notes` 未纳入注册表 ⇒ 无 `load/unload` 生命周期语义（同 **E31** ——
  ADR-0100 **裁决为「不纳入」**，`plugin_id` 只作归因对象身份）。
- **规格**：ADDED「canonical Markdown 真相层与可插拔后端」「Consult → Build → Update 循环纪律」
  「结构化错误码与既有链路不变」（notes）。

---

## ADR-0100：工具调用遥测的**生产方**接线（E30）；`plugin_id` = **归因对象身份**、内部核心模块**不**纳入 `PluginRegistry`（E31 裁决）；`notes` 检索**分区加权**（E32）

- **背景**：三处「消费侧就绪、供给侧空转 / 口径不诚实」的缺口 —— ①**E30**：`_to_traces` 的
  `tool_call` 通道就绪，但其唯一生产者 API `TraceLogger.log_tool_call` 全仓**零生产调用方**；loop 的
  `action_completed` 只作 `LoopEvent` 外发、从不进遥测 ⇒ 技能维度的进化证据**永不产生**。
  ②**E31**：`INTERNAL_PLUGIN_IDS` 的 14 个内部核心模块未纳入 `PluginRegistry`，账本长期记为「欠账」，
  但**补全即空转** —— 注册表全仓仅 `PluginInstaller` 内部默认构造、**无任何消费方**；14 个模块里仅 8 个
  具 Plugin 六件套，其 `load`/`unload` 全 `return None`、`check()` 7/8 恒真（真检查仅 `evolution.engine` /
  `composition.resolver`）⇒ 补全后仍无信号、无行为。③**E32**：`notes` 的 `_score` 把
  `note_id / title / tags / Search Queries / 正文` 拼成一个 haystack **同权**计数 ⇒ 长正文顺带提及
  即可压过标题精确命中（ADR-0099 已知局限②）。
- **决策**：
  ① **E30 —— 生产者放 loop、经生产者 API 产出**：`DefaultLoop` 在 ctor 由注入的 `tracer` 建
     `TraceLogger`（缺省 `None` ⇒ 不产）；`astream` 在**非终止动作**完成后、与 `action_completed`
     **同判据同点**调 `_log_tool_call`。载荷 `tool` = 工具 id / `args` / `result = {"ok", "output"}` /
     `latency_ms`，参数与输出复用既有节选函数（≤400 字符 ⇒ 事件面**有界**，与事件载荷**同源同界**）。
     **经 `log_tool_call` 而非直接写事件**：否则「生产者 API 零调用」的账目继续挂着、载荷形状两处漂移。
     遥测**先于** `yield`：不依赖消费方继续拉取生成器。消费侧 `_to_traces` **零改动**。
     `TraceLogger.log_tool_call` 的 `args` 注解放宽为 `dict | str`（反映既有节选实情，运行期无变化）。
  ② **E31 —— 裁决：不纳入、不补空转**（ADR-0094 决策①的重申，并把口径钉进规格）：`plugin_id` 在内部
     核心模块上表示**归因对象身份**（进化引擎**监控谁**、缺陷**定位到谁**），**SHALL NOT 蕴含**注册表
     成员身份；模块自身的失败证据经**模块归因遥测通道**（`TraceEvent.module_id`）承载，采集与诊断
     **不要求**该模块在注册表可查。**重开条件**：出现「真的会产出新一代 `Plugin` 对象」的生产者
     （模型生成 / 人工提交补丁）—— 届时 `promote(plugin: Plugin)` 才有语义；change 0102 把架构级结晶
     裁决为 `accepted`（待人工实施）= 系统自认短期内没有该生产者。**不采纳**「登记式最小实现 + 诚实
     标注」：诚实标注在**有消费者、只是输入不足**处成立（如 0102 `accepted`、0103 落盘 JSONL 为真源）；
     此处**零消费者**，标注只把 documented gap 换成 documented no-op，并留下「这些算法类有生命周期
     语义」的错误暗示。**连带更正（引用订正）**：账本（`phase-24.md` §2.2 / `phase-21.md` §1.3）与
     ADR-0094 决策①的括注均把该否决归因到「**ADR-0054 明确拒绝过的形态**」—— 一手核实 **ADR-0054 全文
     无此裁决**（其主题是冷路径驱动面；`adr.md` 中「空转」仅出现于 ADR-0055/0065 的别处语境）。该否决的
     实质出处就是 **ADR-0094 决策①** 自身的三条论证（零消费者 / 形态即空转 / 前置条件未满足），旁证为
     ADR-0065「不造空转闭包」。账本与 ADR-0094 括注同步订正。
  ③ **E32 —— 分区加权**：`_score` 改 `Σ(字段权重 × 该字段命中词数) ÷ 词数`，权重 `title 3× / tags 2× /
     Search Queries 2× / note_id 1× / 正文 1×`（模块常量，便于调参 —— 但不做成配置项：无消费者）。
     命中判据（纯词法包含、CJK 2-gram 切词）与 `search` 返回结构、`MemoryBackend` 契约**均不改**：
     打分**不再 ≤ 1**，仅用于 `> 0` 过滤与降序排序、**不外露** ⇒ 语义安全。**不采纳**「按字段命中率
     归一」：会让「长正文命中 1 词」与「标题命中 1 词」重新等权，正是本 ADR 要修的病。
- **影响**：`src/core/loop/default.py`（+`_trace_logger` / `_log_tool_call` / `astream` 非终止分支；
  语句数 +3 ⇒ `astream` 的 `noqa` 增 `PLR0915`，同 `orchestration/scheduler.py` 先例）；
  `src/core/observability/tracer.py`（`log_tool_call` 的 `args: dict | str` 注解 + docstring）；
  `src/core/notes/backend.py`（`_score` 分区加权 + 3 个权重常量 + 模块 docstring）；
  `src/core/evolution/plugin_ids.py`（docstring 由「欠账」改**裁决 + 重开条件**）；测试（新
  `tests/test_tool_trace.py` 5 例、`tests/test_notes.py` +3 例）；文档
  （`03-interfaces/observability-interface.md` §2、`03-interfaces/evolution-interface.md` §4.1、
  `02-modules/notes.md` §3.3、`04-testing/test-cases.md`）。
- **已知局限**：①加权是**启发式**排序（词法命中强度，非相关性 / 语义）；②`latency_ms` 是 loop 侧
  墙钟计时，非工具内生指标；③工具调用遥测只在**非终止动作**产出（终止动作 = 纯回复，不是工具调用，
  不产 —— 与 `action_completed` 同判据）。
- **规格**：MODIFIED「异步流式执行」（loop）/「经验采集」（evolution）/「canonical Markdown 真相层与
  可插拔后端」（notes）。

---

## ADR-0101：插件安装链路的**工具面闭环**（E33 三工具接线 + 对称 `uninstaller`；E34 `cli.*` coeffect 声明补正；E35 CLI 安装走完整生命周期）

- **背景**：`coding-plan/phase-25.md` §1 一手复核发现三处**接线不一致**（规格均已在位，实现未跟上）——
  ①**E33**：`tool-use` spec 明文要求系统提供 `install` / `uninstall` / `list` 三个插件安装工具，但组合根
  `build_runtime` 只注册 5 个内置工具与 `tools.delegate`，三工具**从未接进生产工具面**（全仓仅
  `tools/__init__` re-export 与注入式单测调用；`pet/safety` 的不可逆集合甚至已把它们列为「真实工具 id」
  ——悬空引用）⇒ 规格承诺的对外能力**生产不可达**。②**E34**：`CLIAdapter.adapt` 产出的 `cli.*` 工具
  `coeffects=[]`，而 handler 走 `subprocess.run` **真派生进程** ⇒ 声明不实；且空 coeffect 被 MCP 默认
  暴露面判据（`⊆ {"filesystem:read"}`，空集视为只读）判为只读 ⇒ `cli.*` 工具**默认进对外暴露面**
  （与 change 0076「跨边界能力默认不出」的收窄意图相反；确认门亦因 `process:spawn` 不属高危、`reversible=False`
  的判据只认含 `write` 的 coeffect 而不触发）。③**E35**：`entry._plugin_install` 只走
  `discover → install → register`，**跳过 `verify` / `activate`**，而 `installable` 声明与 `plugin-registry`
  spec「插件来源与安装」要求的是七步链、同链路的 `tools.install` 走全链 ⇒ 两条路径语义分叉。
- **决策**：
  ① **E33 —— 三工具接进生产工具面、与 `Runtime.installer` 同一实例**：在 `build_runtime` 内、`installer`
     构造**之后**注册 `install_tool(installer)` / `uninstall_tool(installer)` / `list_tool(installer)`。
     **同一实例是关键**：`install_tools` 工厂在缺省参时自造 `PluginInstaller()`（一次性注册表）—— 若注册
     时不注入组合根 `installer`，装进去也读不到（同 `entry._build_installer` 曾用一次性 `provider` 的缺陷
     形态）。**连带补 `uninstaller=dispatcher.uninstall`**：`Runtime.installer` 此前只注入了
     `source_resolver` + `installer`、**漏注入 `uninstaller`**，`tools.uninstall` 只从 `_assets` 摘账、不做
     kind 分发的真实回退（skill 移除 / cli·mcp 工具摘除）—— 接线后才暴露，故同批修。三工具的
     `coeffects`（`install`/`uninstall` = `["filesystem:write"]` + `reversible=False`）**不变** ⇒ 经
     `SafetyGate` 仍走「写 + 不可逆」确认门（非交互入口 fail-closed）。
  ② **E34 —— 只改声明、不改行为**：`cli_adapter.py` 工具声明由 `[]` 改 `["process:spawn"]`（对齐
     `code_run` 的规范拼写）⇒ 默认暴露面判据为假、`cli.*` 不再默认对外暴露。**不加 `filesystem:write`**：
     会因 `reversible=False` 新触发写类确认门、改变既有 CLI 安装流程的审批行为，属另一议题。
  ③ **E35 —— CLI 路径补齐 `verify` / `activate`**：`_plugin_install` 在 `install` 前补
     `verify(item, signature)`、`register` 后补 `activate(plugin_id)`，与 `tools.install` 同链。CLI 一次性
     进程仍适用（`installable.activate` = `load` + `activate`，`StubPlugin` 两侧 no-op）；今日 `_build_installer`
     未注入 verifier（`_default_verify` 恒真）⇒ **净效果是补齐链条**，非行为变更。
- **耦合（决策记录的核心理由）**：**接线 E33 会让 E34 变活** —— `InstallDispatcher` 持**生产** `ToolProvider`，
  一旦经审批执行 `tools.install --kind cli`，`cli.*` 工具会注册进生产工具面；若声明仍为空，同一进程的
  `mcp serve` 会把它**默认放出**。故 E33 与 E34 **必须同批交付**（本 change 即如此），否则等于把「声明不实的
  派生进程能力」默认对外开放。
- **影响**：`src/core/runtime.py`（`PluginInstaller` 补 `uninstaller=` + 注册三工具 + import 三个工厂）；
  `src/core/plugins/cli_adapter.py`（coeffect 声明 + 注释）；`src/core/entry.py`（`_plugin_install` 补两步）；
  测试（`tests/test_install_tools.py` +3 例、`tests/test_phase16.py` +1 例并给 CLI 用例注入 `process:spawn`
  resolver、`tests/test_entry.py` +1 例、`tests/test_phase13.py` 工具 id 精确集合断言补三 id）；文档
  （`04-testing/test-cases.md` TC-PLUGIN-04/05/06）。
- **已知局限**：①E35 的 `verify` 今日恒真（无 verifier 注入）—— 补齐的是**链条形状**，签名校验的**实效**须
  待注入真实 verifier（skillhub 侧）后才有意义；②`tools.install` 接入后，MCP 默认暴露面新增 `tools.list`
  （只读、`coeffects=[]`）—— 这正是 `mcp/spec.md` 场景「默认面排除跨边界工具」所**期待**的（此前该场景只在
  测试夹具里成立，现于生产成立）。
- **未做（明示）**：**E36**（`plugin install --kind cli|mcp` 持久化）—— 规格**无**持久化条款，属
  「未接线/取舍」，须**规格先行**、单独立项（形状可照 `mcp-endpoints.json` / change 0074），本 ADR 不涉。
- **规格**：**中性**（无 spec delta）—— `tool-use`（三工具 + coeffect 契约）、`plugin-registry`（七步链）、
  `mcp`（默认暴露面）均已要求本变更的内容，本 change 是实现回归契约。

---

## ADR-0102：插件安装账本**落盘** + 按 `kind` 路由的单一视图（E36 收口；`plugin-installs.json`；装配期重建）

- **背景**：`coding-plan/phase-25.md` §1.4 记 **E36**（`plugin install --kind cli|mcp` 的安装结果**进程内即失**），
  当时判「规格无持久化条款 ⇒ 规格先行、单独立项」；ADR-0101「未做（明示）」条明确挂账。一手复核（`/tmp/e36`，
  2026-10-05，真实进程）发现缺口**比账本记载更宽**：

  | 操作（跨进程） | 改前实际 | 证据 |
  |---|---|---|
  | `plugin install --kind skill` | ✅ 写 `skills.json` | 状态目录出现该文件 |
  | `plugin install --kind cli` | ✅ rc 0 但**一个字节都不落盘** | 状态目录只有 `skills.json` |
  | `plugin list` | ❌ 恒「（无已安装资产）」 | 账本 `PluginInstaller._assets` 是**进程内字典** |
  | `plugin uninstall <id>` | ❌ 恒 `UNINSTALL_NOT_FOUND` | 同上 |

  即缺口不限于 cli/mcp 的**物化**：**安装账本整体不落盘** ⇒ `list` / `uninstall` 对**所有** kind 都跨进程失效
  （skill 只是「物化」侥幸落进 `skills.json`，账本仍空）。规格侧同步补齐——`plugin-registry` ADDED
  「插件安装持久化」（7 场景，含 mcp 委派、装配期重建、损坏降级）。
- **用户裁决（2026-10-05，二选一问答）**：
  ① **mcp 真源 = 委派**（新账本只记 skill / cli；`kind=mcp` 路由到既有 `mcp-endpoints.json`，`list` 合并两视图），
  **不**把端点表并入统一账本；② **装配期 = 重建物化**（`build_runtime` 读回账本并经同一安装管线重建），
  而非「只让 `list` 说得出口」——否则 `list` 说已安装、运行时工具面却没有 = **谎报**（本仓反复钉的诚实口径）。
- **决策**：
  ① **账本形状**：新 `$CORE_STATE_DIR/plugin-installs.json`，单文件 JSON + `version` 字段 + **原子写**
     （tmp + `os.replace`）+ 损坏与残缺条目 `warnings.warn` **降级跳过**（不静默丢弃、不阻断启动），
     形状逐条对齐 `mcp-endpoints.json`（ADR-0071）。**状态非配置**：由安装动作写入，不进 `ConfigSpec`。
     **不复用** `core/persistence.read_state/write_state`：它对损坏**静默**降级为 `None`，与本规格「降级**告警**」
     相悖（同一个「不静默丢弃」的口径）。
  ② **按 `kind` 路由、不统一收敛**（`PluginInstallStore`）：`kind=mcp` → `MCPEndpointRegistry`，其余 → 本账本；
     `records()` 合并两处为**单一视图**，`SHALL NOT` 同一资产两处记账。理由：端点表不是「插件账本的分片」，
     它承载**连接句柄语义**（先 `initialize` 握手再落盘、重名拒绝以护住另一个端点的配置）；统一收敛要把两套
     语义压成一套，且要重做握手次序——ADR-0071 的取舍保留。
  ③ **写点收在 `PluginInstaller`**（而非 `InstallDispatcher`）：`register` → `store.put`、`uninstall` →
     `store.remove`、构造期经 `store.records()` 水合 `_assets`。收益是 **CLI 与运行时（`tools.install`）两条
     入口自动一致**（两条路径注入同一个 store），不再有「CLI 装了 / Agent 装了 / 只有一个跨进程可见」的分叉。
     **反例（为何不写在 dispatcher）**：装配期会**重放**账本，`_install_mcp` 若顺带落盘则会撞端点表的重名拒绝
     ⇒ 每条 mcp 记录都在装配期「安装后落盘失败」被跳过，等于把端点装配成哑的。
  ④ **装配期只重建本账本**：`build_runtime` 在既有端点循环**之后**读 `PluginInstallRegistry(...).list()` 逐条
     `dispatcher.install`（skill → 技能库 upsert；cli → 工具面注册），**单条失败只告警跳过**（照端点先例）。
     mcp 归上面的端点循环 ⇒ 同一资产不两处装配。`list` / `uninstall` 走 store 的**合并视图**：与装配期的双循环
     **同源不同形**（视图合并、装配分治）。
  ⑤ **upsert 而非重名拒绝**（账本侧）：安装动作本身就是 `plugin_id` 的权威来源，无「静默覆盖会丢另一个配置」
     之虞 ⇒ 重装即升级。端点表也补 `put()`（同名覆盖）供委派使用，`add()` 的重名拒绝语义**不变**。
  ⑥ **卸载幂等 + 顺序**：`_uninstall_skill` 容忍技能已不在（账本条目可能陈旧）——`SkillLibrary.remove` 的裸
     `KeyError` 在本 change 后**可达**，故同批修；`register` **先落盘再入内存**（落盘失败则整体失败、不留半份登记），
     `uninstall` **物化回退成功才清账**（失败则下次仍可重试）。
- **耦合（决策核心理由）**：**依赖方向锁死了水合的形态**。`plugin_registry` 是 L0 组合基底，**不得** import
  `core.tools`（L1）⇒ ①持久化钩子只能在 `installable.py` 声明为 `InstallStore` **Protocol**（结构型，由组合根注入
  `plugins.installs` 的实现）；②水合要在 `PluginRegistry` 里**登记**一个插件（否则走生命周期时 `unload` / `state`
  抛「插件未注册」`NOT_ACTIVE`），而 `StubPlugin` 住在 L1 ⇒ L0 侧自带最小载体 `_HydratedPlugin`（manifest 来自
  **不可信状态文件**，故三个字段按类型兜底：坏字段降级为默认值，绝不让一条坏记录阻断构造）。
- **影响**：新增 `src/core/plugins/installs.py`；`src/core/mcp/endpoints.py`（+`put` / +`EndpointRecord.from_manifest`）；
  `src/core/plugin_registry/installable.py`（+`InstallStore` / +`_HydratedPlugin` / +`store=` 水合与落盘钩子）；
  `src/core/plugins/install.py`（`_uninstall_skill` 幂等）；`src/core/entry.py`（`_build_installer` 注入 store——
  `_plugin_list` / `_plugin_uninstall` / `plugin install --kind mcp` **无需改动**，经 store 自动一致）；
  `src/core/runtime.py`（installer 注入 store + 账本重建循环）。测试：新 `tests/test_plugin_installs.py`（20 例）、
  `tests/test_entry.py` / `tests/test_mcp_endpoints.py` / `tests/test_install_tools.py` 各追加端到端与装配期用例。
- **已知局限**：①`installed()` 读**构造期水合的内存副本** ⇒ 同一进程**运行中**被另一进程装的东西不可见（跨进程
  可见性的口径是「新进程读盘」，同端点表）；若需单进程实时，可在 `installed()` 每次读盘（代价：每次 list 都读盘）。
  ②mcp 类资产的账本身份**即端点名**（`plugin_id` 与 manifest `name` 不一时以端点名为准）。③`plugin install --kind mcp`
  走的仍是 `_build_installer` 的**裸** `MCPClient`（无沙箱策略），而 `mcp add` 用 `host_allowlist` 的 fail-closed 策略
  —— 属 E36 之外的**既有**面，本 change 未动，**登记**待议。
- **未做（明示）**：**不**把 `mcp-endpoints.json` 并入本账本；**不**改 `mcp add|list|remove` 的 CLI 语义（重名仍拒绝、
  仍先握手再落盘）；**不**新增 capability、**不**改 `PluginInstaller` 既有公开签名（只加可选 `store=`）。
- **规格**：**非中性** —— `plugin-registry` **ADDED**「插件安装持久化」（账本落盘 / 按 kind 路由单一视图 /
  装配期重建 / list·uninstall 真源 / 7 场景）。

---

## ADR-0103：beast / pet 专属记忆命名空间的**接线收口**（E37 + E38 + E39；规格中性）

- **背景**：`coding-plan/phase-26.md` §1 逐条一手复核，发现三条「规格已声明、实现未接线」的缺口
  （规格均**已在位**，属覆盖完整性收敛，非新需求）：

  | 缺陷 | 规格条款 | 改前实际（证据） |
  |---|---|---|
  | **E37** 神兽独立命名空间断裂 | `beast-mode` spec `:54`「独立记忆命名空间（`MemoryEntry.source = beast.<agent_id>`，与主 Agent `source=loop` 隔离）」 | 落记忆路径是 `DefaultLoop.remember`，`source="loop"` **硬编码**（`loop/default.py:485`，改前）且 ctor 无注入面 ⇒ 组合根 `_beast_loop` 无从指定 ⇒ 神兽轨迹**混入主记忆** |
  | E37（污染面） | `beast-mode` spec `:89` 记忆分区封存 | `read` 无来源过滤（`memory/protocol.py:49` / `store.py:90`）⇒ 主 loop 上下文装配（`context/assembler.py:61`）读到神兽中间产物 |
  | E37（归组面） | `beast-mode` spec `:99` 自动回归 | `TaskHandoff` 无 `session_id`（`orchestration/models.py:62`）⇒ 神兽条目 `session_id` 空串，压实按会话聚合时与主线**未归组**条目同组 |
  | **E38** 封存「无实现」 | `beast-mode` spec `:89` | 见下「判据订正」 |
  | **E39** 宠物偏好追踪断裂 | `pet-mode` spec `:75/:77-85`（`source=user` 落 L2）/ `:231-234`（生产入口激活并观察偏好） | `PetSession.observe`（`session.py:187`）**零生产调用方** ⇒ `_preferences` 恒空、`surprise()` 恒 `None` ⇒ R6/R7 在生产**不可达** |

- **判据订正（一手复核，两条 —— 账本原文与规格原文不一致处，以规格为准）**：

  | 账本原文 | 规格原文 | 订正 |
  |---|---|---|
  | E38「实现 seal / recall（按 source 冻结一段轨迹 / 召回封存记忆）」 | `beast-mode/spec.md:89`「记忆分区封存（`source=beast.*` **不再被主 loop read 命中**）」——**无 API 条款** | 封存是**效果**条款：由 E37 的 read 侧排除落地，**不新造 seal/recall API**；召回（复位）早已由 `Manual Recall` + `summon` 收尾的 `session.recall()` 实现。`beast/models.py:20` 注释「已召回（记忆分区封存）」即该语义的文档 |
  | E39「在 `PetSession.wake`（`:146/149`）及交互反馈路径调用 `observe`」 | `pet-mode/spec.md:231-234`「**生产入口激活**一只宠物**并观察主人偏好** ⇒ 偏好以 `source=user` 写入共享 L2」 | 观察点落在**主人原话入口**（激活 / 换活），**不在 `wake()`**：唤醒时宠物只在跑自己的任务，无主人行为可观察；且合成 goal 会**谎报**偏好（违反 R7 / 账本 E26） |

- **决策**（**命名空间 = 写入侧 `source` 注入 + 读取侧来源排除**，一条原则贯穿）：
  ① **`DefaultLoop(source: str = "loop")` 注入面**：`remember` 用注入值替代硬编码。**缺省 `"loop"` 逐字不变**
     （主 Agent 语义向后兼容，红线）；神兽 loop 由组合根注入 `source=beast.<agent_id>`，与
     `BeastSession.remember` 的 source 口径**同一写法**。
  ② **读取侧排除在 `MemoryStore.read`**：仅关键字参数 `exclude_source_prefixes: tuple[str, ...] = ()`，
     在**排名与预算截断之前**过滤候选 ⇒ 被排除项**不吃预算**、**不被 `reuse_count += 1` 强化**
     （若放在截断后过滤，被排除项会白占预算并污染结晶阈值依据）。**缺省 `()` ⇒ 检索语义逐字不变**（红线）。
  ③ **`TaskHandoff.session_id` + `handoff` 转交**：`MultiAgentRouter.handoff` 调
     `arun(handoff.task, session_id=handoff.session_id)`；`BeastManager.summon` 传 `beast.agent_id`
     ⇒ 神兽条目按**自身会话**归组（`session_id` 是既有协议参数，故恒传；见下「不对称」）。
  ④ **`DynamicAssembler(exclude_source_prefixes=…)** 透传；组合根为主 loop 的装配器传 `("beast.",)`
     ⇒ 主 loop read 不命中任何神兽分区（E38 封存的效果面）。
  ⑤ **E39：`PetSession.observe_owner(text)`**（**fail-soft**：非空文本转 `observe`，异常静默跳过）
     接在**主人原话入口**三处：`PetActivator.activate_from_cli`（`rest` 非空时）、`activate_from_nl`（`user_input`）、
     `PetControl.assign`（`goal`，派发成功后）。`observe` 自身的异常面（`PET_PREFERENCE_WRITE_FAILED`）**不变**
     —— 供库层直接调用、不吞异常；生产入口则**绝不因偏好落库失败而中断激活/派发**。

  > **不对称的两处调用形态（有意，各附理由）**：
  > - `DynamicAssembler` **仅在排除非空时**才把 `exclude_source_prefixes` 传给 `read`（空则调两参形态）——
  >   `exclude_source_prefixes` 是**本 change 新增**的协议成员，空参不传可让**既有** `MemoryStore` 实现
  >   （含 8 处测试替身与第三方后端）零改动，把「缺省不变」落到实处。
  > - `handoff` **恒传** `session_id` —— 它是 `LoopPlugin` **既有**协议参数（`loop/protocol.py:97`），
  >   符合协议的 loop 早已接受；`tests/test_phase14.py` 的 `_FakeLoop` 是不符合协议的陈旧替身，**同批补签名**。

- **影响**：`src/core/loop/default.py`（`__init__` +`source`，`remember` 用之）；`src/core/memory/protocol.py` /
  `store.py`（`read` +`exclude_source_prefixes`）；`src/core/context/assembler.py`（ctor 同形参数 + 透传）；
  `src/core/orchestration/models.py`（`TaskHandoff` +`session_id`）/ `router.py`（转交）；
  `src/core/beast/manager.py`（`summon` 传 `session_id`）；`src/core/runtime.py`（`_beast_loop` 注入 `source`；
  主 loop 装配器传排除）；`src/core/pet/core/session.py`（+`observe_owner`）/ `activator.py` / `control.py`（接线）。
  测试：新 `tests/test_memory_namespace.py`（16 例：写入面 / 排除面（含预算与强化口径）/ 归组面 /
  两条生产端到端 / 三条反例）；`tests/test_phase14.py`（`_FakeLoop.arun` 补协议签名）。
  接口文档：`loop-` / `memory-` / `context-` / `orchestration-` / `beast-mode-` / `pet-mode-interface.md`。
- **已知局限（明示）**：① 主 loop 与神兽 loop **共享同一** `DynamicAssembler` 实例 ⇒ 神兽自身的上下文装配
  亦不命中 `beast.*`（规格只要求主 loop 不命中；神兽产物在自动回归时即封存，无场景要求神兽 recall 自身分区。
  若要按 loop 分装配器，需拆实例——本 change 不扩面）。② 压实摘要（`_commit_summary`）的 `source` 恒为
  `"compaction"`（`tests/test_memory.py:275` 已断言该口径）⇒ 神兽分区被压实后的**摘要**仍可被主 loop 读到
  —— 按 source 命名空间隔离的**残留缺口**，登记待议（修它要动该断言，属另一个口径决定）。
- **未做（明示）**：**不**改 `BeastSession.remember`（会话级 API 保留，生产轨迹由 loop 写入，同口径不互相代笔）；
  **不**改 `observe` 的异常面；**不**在 `wake()` 内 observe；**不**新造 seal/recall API；
  **不**新增 capability、**不**改任何 Requirement。
- **规格**：**中性** —— `.openspec.yaml` 置 `schema: spec-driven` + `skip_specs: true`；
  `beast-mode` / `pet-mode` 两 spec **零改动**（三条缺陷均为「实现回归既有契约」）。

---

## ADR-0104：质量门禁的**工具面**（change 0111 / phase-27 切片 S1；单一真源复用 + 执行器注入 + 诚实 coeffect）

- **背景**：`coding-plan/phase-27.md` 记 E42「门禁工具缺位」。一手复核**订正判据**（§3.1）：
  **门禁执行器早已存在** —— 单一真源 `ci_cd/pipeline.py:25` `GATE_COMMANDS`（lint/typecheck/test/build）、
  生产执行器 `SubprocessGateExecutor` / `build_gate_executor`（ADR-0086 / change `0091`）、结构化结果
  `GateResult`。真缺口只有一处：**没有工具面**（`runtime.py` 改前连 `ci_cd` 都未引用）⇒ Agent 无法经
  工具调用通道触发门禁。
- **决策**：

  | # | 决策 | 理由 |
  |---|---|---|
  | ① | **只补工具面，不新写执行器** | 另起一套 `gate_run` 执行器＝第二份门禁真源，即 change `0105` 删 `_published`、`0103` 收窄 `replay` 时反复钉的「双真源」反模式 |
  | ② | 门禁名与门禁命令取自 `GATE_COMMANDS`**单一真源**（组合根 `tuple(GATE_COMMANDS)` 注入，schema `enum` 由其生成） | 门禁名单只有一处；新增门禁自动同面可见 |
  | ③ | **执行器经构造参数注入**（`gate_run(*, gates, run_gate)`） | `tools` 是 L1、`ci_cd` 是 L5 ⇒ 工具层**不 import** 交付流水线层；结果面只需 `passed`/`reason` 两个属性（结构协议 `GateOutcome`），`GateResult` 天然结构兼容 ⇒ L1 也不必反向依赖 L5 模型 |
  | ④ | coeffects **诚实声明** `["process:spawn","filesystem:write"]` + `reversible=False` ⇒ 照旧走确认门 | change `0108`（E34）刚修掉「声明不实」：跑门禁＝spawn 子进程 + 写 `__pycache__`/`.pytest_cache`。**否决**「白名单命令 ⇒ 只读免审批」——白名单的是**命令名**，不是**被执行的代码**（`pytest` 即执行仓库任意代码） |
  | ⑤ | 未知门禁名在**处理器内** fail-closed（不触达执行器） | `constraints.Validator` 只校验 required/type，**不校验 `enum`** ⇒ 不能把白名单托付给 schema |
  | ⑥ | **只挂主工具面** | 子 Agent / 宠物 loop 的 `builtin_tools` 注入点不动（不扩散越界暴露面；`_pet_tools` 白名单本就排除它） |
  | ⑦ | `timeout_s=660.0`（> 执行器内部 600 上界） | 避免工具层先于门禁自身超时；全量 `pytest` 不会撞上 60s 缺省 |

- **S2 改判（同批复核，登记不改代码）**：`phase-27.md` §5.4 把 S2（`proposer` delta 补
  `suggested_patch`/`acceptance`）记为「✅ 中性」，复核后**改判不纳入**：① `delta` 现仅被
  `engine._crystallize_skill` 读 `issue`/`schema` 两键，新增键**无任何读取方** ⇒ 与 E31 裁决
  「不给空转生命周期」同型；② `suggested_patch` 无规格依据、无生产者（`Proposer` 是 `DiagnosisReport`
  的纯函数）；③ 真消费方是 **S0 的 `EvolutionExecutor`**（patch 建议与验收判据是它的输入）⇒ 并入 S0
  一并定字段与其消费者，避免此刻造「写而不读」的字段。
- **判据订正（两条，登记入 `phase-27.md` §3.2 / §5.4）**：① `module_id` **无需新增** ——
  `GenerationCandidate.target_plugin` 即模块身份（独立字段，非 `delta`）；② `delta["schema"]` 是
  **读而不写**的既有键（`proposer.py:38` 只写 `issue`）⇒ 归入 S0 的候选字段口径一并定。
- **影响**：`src/core/tools/builtin.py`（+`GateOutcome` / `gate_run`）；`src/core/tools/__init__.py`（导出）；
  `src/core/runtime.py`（`build_gate_executor()` + 门禁名→`Gate` 适配 + 注册主工具面）。
  测试：新 `tests/test_gate_run_tool.py`（7 例：定义契约 / 结构化返回 / 失败原因 / 确认门零调用 /
  未知门禁零调用 / 真执行器通过 / 真执行器非零退出）、`tests/test_gate_run_wiring.py`（2 例：生产面可达 +
  门禁名与单一真源逐字一致）；`tests/test_phase13.py`（生产工具面期望集 +1）。
  接口文档：`03-interfaces/tool-use-interface.md` §3；用例：`04-testing/test-cases.md` TC-TOOL-07。
- **未做（明示）**：**不**做 S0（`EvolutionExecutor` 与 `features.evolution_executor` 装配裁剪须先
  phase-27 §5.2 规格 + ADR）；**不**改 `evolution/spec.md:203/215` 的边界；**不**做 S2；
  **不**在 `builtin_tools` 注入点扩面。
- **规格**：`tool-use/spec.md` **ADDED**「质量门禁工具」（4 场景）—— 新工具即新 Requirement
  （先例 change `0028` 为插件安装三工具写入 `tool-use` 需求；change `0108` 的「规格中性」成立于
  该需求**已在位**，此处不成立）。

---

## ADR-0105：自改代码的安全边界 —— 原生执行器 `EvolutionExecutor`（change 0112 / phase-27 切片 S0）

- **背景**：`core_harness_architecture.md:150-153/158` 承诺「验证通过 ⇒ **产出不可变世代**」「稳定技能
  **提升为插件（记忆→代码）**」，而 `evolution/spec.md` 的「架构级候选强制人工审批」把这**同一个分支**
  明文否掉（`accepted` = 「已批准、**待人工实施**」，「无架构产物被发布、无世代被晋升」）。phase-27
  §2 已把这件「矛盾」改判为 **RSI 能力扩展提案**（非缺陷修复），并完成裁决：**DS1** 允许自动实施但
  **缺省 `false`（fail-closed）**、**DS2** 保留人工复核、**DS3** 验证门**冻结**、**DS4** 规格**必改**
  （先例 change `0067`，**非** `skip_specs`）。本 ADR 记录落地形态与安全边界。
- **决策**：

  | # | 决策 | 理由 |
  |---|---|---|
  | ① | 门控落点 = `features.evolution_executor`，判据用 **`is_enabled`（缺省 `false`）** | **订正 DS1-a**（`phase-27.md:106` 原记「加进 `runtime.GATABLE_MODULES`」）：该元组由 `is_disabled`（`features.<m> is False`，**缺省不关**）消费 ⇒ 放进去等于**缺省开**，与 DS1 的 fail-closed 相反。`is_enabled` 的既有 docstring 本就写着「缺省关闭，未显式开启的模块不加载、不初始化」⇒ 本切片给它**首个生产消费者** |
  | ② | **两级名单**：`GATABLE_MODULES`（缺省装配）**逐字不动** + 新 `OPT_IN_MODULES = ("evolution_executor",)`（缺省关）；派生 `KNOWN_FEATURE_MODULES = 二者之并` 注入配置层 | 一个名单**不能**承载两种缺省语义（同一名字一个缺省）。分开承载 ⇒ 既有门控名单的缺省开口径与 `tests/test_feature_gating.py:84` 的逐元素断言**零改动**；并集供「未知功能开关」告警（否则 E20① 会为新开关误报拼写错） |
  | ③ | 触发形态 = **操作面显式驱动**（`core-agent evolve implement <cid> [--dry-run]`），**两阶段**：筹备（补丁 → 范围守卫 → 应用 → 跑冻结门 → **回退**）→ 人工复核 → 落地 | **否决**原设计的「冷路径 `_cold_path` → `drain()`」：① `ColdPath = Callable[[], None]` 是**同步**调用，唯一调用点在 `DefaultLoop._maintenance`（`loop/default.py:359-363`）⇒ 在智能体**一轮收尾处**同步跑四道门禁（单门超时上界 600s）等于**阻塞热路径**，与 `worker.py` 明写的「热路径只取快照、不阻塞」直接冲突；② `evolve confirm` 是**一次性 CLI 进程**，跑完即退，冷路径**永不命中** ⇒ 筹备是**死路径**。操作面同步执行同时满足 R2「独立任务面」（**不进任何工具面**、与 `evolve confirm` 同形，比「冷路径后台步」更贴） |
  | ④ | 制品（补丁 / 被改文件原内容 / 各门结论）落**既有候选台账**（`PendingItem.implementation`），**不**新建第二个持久化库；落地时候选状态置 `implemented` | 第二库的候选生命周期必须与台账一致 ⇒ 两个文件必然**同步撒谎**（change `0105` 删 `_published`、`0103` 收窄 `replay` 反复钉的「双真源」反模式）。且操作面是**一次性进程** ⇒ 结论若只活在 stdout，跨进程**不可查**（`implemented` 会变成不可观察的谎） |
  | ⑤ | 验证门独立性（R1）= **冻结 `GATE_COMMANDS` 单一真源** + **复用**组合根既有 `gate_executor`/`_run_gate`（`runtime.py:377-382`）+ **范围守卫** | 执行器**不得**自选门禁命令、**不得**第二次 `build_gate_executor()`（同进程两个门禁执行器 = 稀释「单一真源」）。守卫用**白名单**形态（`src/core/` 内的 `.py`，减去**信任集**：`ci_cd/**`、`permission/**`、`evolution/**`、`configuration/**`、`runtime.py`、`entry.py`、`persistence.py`）⇒ 未来新增的验证装置**构造性**被覆盖，而非靠枚举追补；另拒绝绝对路径 / `..` / 非 `.py` |
  | ⑥ | 补丁路径 SHALL 由**候选归因**（`target_plugin` ∈ `INTERNAL_PLUGIN_IDS`）经**约定** `src/core/<点转斜杠>.py` 解析，且目标文件**必须存在** | 守卫只校验路径**形状**是不够的：归因到 `loop.default` 的候选，其补丁可被作者指向 `src/core/notes/store.py`。约定已一手核实 **14/14** 命中，并加**派生不变量测试**守护（否则改个文件名就让执行器指向不存在的路径） |
  | ⑦ | 崩溃安全 + 漂移拒绝：原内容**先随制品落盘再应用**；应用／跑门／回退包在 `try/finally`；落地前校验目标文件当前内容与筹备时记录的原内容**一致**（不符 ⇒ `IMPLEMENT_STALE`） | `EffectTracker` 是**纯进程内** undo 栈，中途 `KeyboardInterrupt`/OOM 会把补丁留在工作树里，而下次启动 `PendingQueue._load` 只恢复台账、**不检测脏树**（fail-open）。落盘制品同时充当「被复核的那一份」（LLM 非确定 ⇒ 落地 SHALL 消费被复核的制品，**不重新产出**） |
  | ⑧ | HITL 边界（R3）：`confirm` 批「做什么」、复核批「改得对不对」，**两道关都不打折**；复核单 `op="evolution.implement"`，与 `confirm` 的 `"evolution.publish"` **可区分**，且目标须一致 | 「不把人工审核自动化」是红线；自动化**实施**不等于移除人工关。`op` 可区分 = 「不得跨阶段复用同一张审批单」的可执行形态 |
  | ⑨ | 世代语义（R4）：`EvolutionOutcome.status` **+1** `implemented`；`crystallize` 的**返回值与文案逐字不动**（恒 `accepted`），既有用例保持绿 | change `0102` 刚把 `published` → `accepted` 诚实化（**不谎报发布**）；新增「已实施」只能**新增**词表项，SHALL NOT 悄悄改回 `published` |
  | ⑩ | 不动既有 `Validator()` / `Evaluator()` 恒通过桩 | 它们是**另一件事**（生产验证门名副其实化），波及既有 `confirm`/`crystallize` 与观察期基线 ⇒ 列已知局限，不并入本切片 |

- **为何不违反 `CORE-EVO-R3`「过验证门前不进入运行」**：筹备窗口内进程内模块**已加载、不重入 loop**；
  窗口内不启动任何常驻进程 —— 起子进程的只有门禁本身，而**那正是「过门前的检验」**，不是「进入运行」；
  补丁在人工复核落地之前不成为运行系统的行为（且落地后 `git` 工作树变更即可见、`EffectTracker` 有 undo）。
- **影响**：
  - 新增 `src/core/evolution/executor.py`（`PatchProposal` / `GateOutcome` 结构协议 / 范围守卫 +
    归因一致性 / `EvolutionExecutor.prepare|commit`）、`src/core/evolution/author.py`
    （`patch_author_with(llm, read_source)`，照 `summarize_with` / `sop_writer_with` 惯用法由组合根注入）。
  - 改动 `evolution/models.py`（`ImplementationRecord` + 词表 +1）、`evolution/errors.py`
    （**+2**：`IMPLEMENT_REJECTED`（未确认 / 守卫拒绝 / 未筹备 / 回退失败）与 `IMPLEMENT_STALE`
    （工作树漂移）；未过门复用既有 `GATE_REJECTED`、复核缺失复用既有 `CONFIRM_REQUIRED`）、
    `evolution/pending.py`（制品字段 + 落盘往返，
    `record()` **保留**既有制品不静默抹掉）、`runtime.py`（`OPT_IN_MODULES` / `KNOWN_FEATURE_MODULES`
    + 门控装配 + `Runtime.evolution_executor`）、`entry.py`（`KNOWN_FEATURE_MODULES` 注入 +
    `evolve implement` 三件套 + `_sign_approval(op=…)`）。
  - 测试：新 `tests/test_evolution_executor.py` / `_wiring.py` / `_cli.py` / `test_evolution_author.py`；
    扩 `tests/test_feature_gating.py`（不动 `:84`）；`tests/test_evolution.py` **只增不改**（钉 R4）。
  - 文档：`03-interfaces/evolution-interface.md`（§3.2 / §4 / §5 词表与错误码）、
    `03-interfaces/configuration-interface.md` + `02-modules/configuration.md`（两谓词用途栏与
    装配裁剪契约补「缺省关名单」）、`04-testing/test-cases.md`。
- **已知局限（照实登记，不隐瞒）**：
  1. 生产 `Validator()` / `Evaluator()` **仍是恒通过桩**（`runtime.py:589-590`〔行号随 `0115`/`0116` 加行漂移，
     `0112` 落地时记作 `:564-574`〕：缺省 `review` 恒真、
     `tests` 返空 dict ⇒ `passed` 恒真；无 `score_fn` ⇒ 留出分/基线/margin 恒 0、`verdict` 恒 `publish`）
     ⇒ 既有 `confirm`/`crystallize` 路径的「过门」**不构成真实检验**，本切片的冻结门是当前**唯一**真门。
     故新 Requirement 只承诺**冻结门**，**不**承诺留出评测参与实施验证。
  2. 物理隔离**未落地**：隔离只到「操作面 + subprocess 门」，**不是**独立工作树 / 容器（R2 仅部分落地）。
  3. `commit` 记录了 undo，但**未**新增 CLI 回退入口（沿总纲「回滚 = 卸载上一代」的完整形态留后续）。
  4. 门禁自身产生的副产物（`build` 门的 `dist/`、`pytest` 的 `.pytest_cache`/`__pycache__`）**不**纳入
     `EffectTracker` 回退 —— 它们不是被实施产物，属门禁的执行痕迹（**不**谎称「一切副作用可逆」）。
  5. 门禁跑的是**全量既有测试**而范围守卫**禁止**改测试 ⇒ 当前表达力约等于「行为保持的重构 / 新增模块」，
     会改变既有可观测行为的补丁**过不了门即回退**（fail-closed 的诚实结果，非缺陷）。
- **与 E31 的关系（不改判）**：E31（13 个内部模块未入 `PluginRegistry`）的重开条件是「出现需要被
  `promote` 的 `Plugin` 对象」。本切片产出的制品是**源文件补丁**（`PatchProposal`），**不是** `Plugin`
  实例 ⇒ `promote(plugin)` 依旧无生产方，**未**触发重开；`INTERNAL_PLUGIN_IDS` 在此只作**归因白名单**
  使用（沿用 change `0102` 的定位：它是归因对象身份，**非**注册表成员）。
- **规格**：`evolution/spec.md` **MODIFIED**「架构级候选强制人工审批（HITL confirm gate）」（结局诚实
  bullet 加限定语）+ **ADDED**「架构级候选的原生实施（可选）」；`configuration/spec.md` **MODIFIED**
  「功能开关（feature flag）」（补第二条极性）。**非** `skip_specs`。

---

## ADR-0106：任务结果可见性走**查询面**（change 0113 / phase-28 E46）

- **背景**：`coding-plan/phase-28.md` §1.3 登记 E46「结果可见性」。一手复核发现**账本原写修法两半都撞车**，
  且两半**同型** —— 结果对象**已经到手**，被**上层消费点丢弃**：
  - beast：`beast/manager.py:71` `await handoff` 已拿到 `LoopResult` → `:74` 存 `session.last_result`
    （repo-wide **零读者**）；`entry.py:1750-1751` `_summon` 只打印状态。
  - pet：`pet/core/session.py:153` `wake()` **已** `return result`，`driver.py:67` **丢弃返回值**
    （`WakingSession` Protocol 注释明写「驱动只取其副作用」）；会话只留 `_last_trace_id`。
- **决策①：beast 走查询面，**否决**「落 L2」。** 账本原写「`recall()` 前经 `session.remember()` 落 L2」
  **自败**：`runtime.py:564` 主 loop 装配 `exclude_source_prefixes=("beast.",)`，`beast-mode/spec.md:89`
  **明文**「记忆分区封存（`source=beast.*` 不再被主 loop read 命中）」⇒ 落进去主 Agent **永远检索不到**，
  写了等于没写。故**不动记忆语义**（命名空间与封存条款**逐字不变**）——「允许神兽产物回流主记忆」是
  **另一件事**，需单独规格变更 + 裁决，本 change **不做**。
- **决策②：pet 走**独立查询面**，**否决**改 `status`。** 账本原写「`status`/`snapshot` 暴露正文」**违已有
  Requirement**（非实现缺口）：`pet-mode/spec.md:249`/`:255` 明文「`status` SHALL 返回结构化字段…**SHALL NOT
  外泄主人偏好与任务正文**」。故新面**独立**（`PetControl.result`），`status` 返回面**逐字不变**，
  并加守护测试钉住六键集合。（`snapshot()` 含 `preferences`/`tasks[].goal` 是**持久化面**的有意设计，
  隐私过滤**故意**做在控制面这层 —— 两层**均不改**。）
- **决策③：接出已到手的，不新造数据流。** `BeastSession.result_summary()` **只读取用**既有 `last_result`；
  `PetSession.wake()` **在会话内**自留一份 `last_result`（**不进 `snapshot`**、不落盘）；查询面**不缓存、
  不落库、不复制** ⇒ 无第二真源。
- **决策④：单一门面 + 诚实。** pet 查询进既有 `PetControl`（`pet-mode/spec.md:244-245` SHALL 单一门面），
  CLI `pet result` 与 `UIAPILayer.pet_command` **复用同一实现**；寻址复用既有 `_resolve`（三分支同口径）。
  两侧无结果时 SHALL 报「无结果」，**SHALL NOT** 编造正文（phase-19「不谎报」同判据）。
- **已知局限（照实登记）**：
  1. 结果**不落盘**：只**本进程**、只**最近一次**；进程重启即失（与 `status` 同界，规格已写明）。
  2. `pet result` 暴露任务正文 —— 这是**新暴露面**（规格新 Requirement 明写），但**未**放宽 `status` / `snapshot`
     任何一层；观测面（metrics/log）**不**接入该面。
  3. beast 侧**无** UIAPI 面（本 change 未新造），呈现仅经 `summon` CLI 与 `result_summary()`。
  4. `PetWakeDriver` 仍**不消费**返回值（`WakingSession.wake() -> object` 契约不改）—— 留存责任放在会话内，
     驱动零改动（避免扩 Protocol 面）。
- **规格**：`beast-mode/spec.md` **ADDED**「Task Result Visibility」；`pet-mode/spec.md` **ADDED**
  「Task Result Query」。**非** `skip_specs`。

---

## ADR-0107：按会话隔离记忆 —— 读侧机制 + 写入侧归属闭合（change 0114 / phase-28 E47）

- **背景**：用户要求「WebUI / CLI 可开 N 个主题各异的会话，**会话之间内容肯定隔离**」。一手复核发现
  缺口比账本记载的**更宽**：账本原记「读侧不过滤会话」（一项），实为 **1 处读侧 + 4 处写侧归属 +
  1 处绕过通道 + 2 处 id 覆盖**：
  - **读侧（R）**：`session_id` 在 `memory/protocol.py:32` / `loop/default.py` 的 `remember` /
    `store.py` 的会话摘要处**写入**，但喂给 LLM 的唯一检索路径
    `planner._system_prompt` → `DynamicAssembler.build` → `MemoryStore.read` **从不消费**它
    （唯一过滤是来源前缀排除，生产只接了 `("beast.",)`）⇒ **A 会话沉淀的事实会进 B 会话的 system prompt**。
    `ui/api.py:174` 的「只返回本会话」是读后 Python 过滤，**只盖展示面**。
  - **写侧（W1–W4）**：压实产物 `compaction.fact.{i}` **每次压实从 0 重数**（后一次静默覆盖前一次）
    且无 `session_id`；`skills.miss.{n}` 把**本轮任务原文**写全局条目，且经 `planner._skill_hints`
    **每轮推理**触达（⇒ 普通聊天每轮任务原话进全局记忆）；宠物 `self._loop.run(goal)` 缺省空标识
    ⇒ 轨迹与主线未归属条目**同形不可区分**；编排 `profile.loop.arun(goal)` 无会话 + `run_task`
    **有 session_id 却不传** ⇒ 子任务轨迹全局化。
  - **绕过通道（W5）**：`ctx.notes`（`_consult_notes` → `NoteStore.digest`）与会话隔离**零交集**。
- **决策①：隔离点在 `MemoryStore.read` **内部**，与 `exclude_source_prefixes` 同点（排名/预算之前）。**
  否决「装配器后置过滤」：后置过滤时被滤项**已吃预算、已被 `reuse_count` 强化**，与既有排除条款
  口径**不自洽**，且装配器不是唯一读取方（`memory.compact()` 内部也读）。同点即同语义：被滤项
  不吃预算、不被强化。`read(query, budget, *, exclude_source_prefixes, session_id)` 三参形态下，
  **两者皆缺省时仍走两参调用**（逐字兼容既有 2 参 `read` 替身）。
- **决策②：非空标识 ⇒ 「本会话 + 全局层」；**空标识 ⇒ 不过滤**（承认 fail-open）。** 「全局层」=
  未归属（`session_id == ""`）条目 + L0 人格 + **文档化笔记层**。空串不是「某个会话」，而是
  **未归属调用者**（CLI 库层直调、`memory.compact()` 内部读、非 UI 调用方）⇒ 施加过滤既无依据
  也破兼容。与既有 `exclude_source_prefixes` 的「缺省空 ⇒ 逐字一致」**同构**。**承认这是 fail-open**：
  专属分区在**未归属读**路径上不生效（主 loop 的读一直带会话标识，故生产路径上不 fail-open）。
- **决策③：归属原则（本 change 的仲裁线）。** **执行轨迹按发起会话归属**：主 / 子 / 神兽 / 宠物 loop
  的 `remember`、压实产物、路由未命中。**刻意知识留全局层**：L0 人格、**文档化笔记**（`notes`）、
  `pet.observe` 的 `source="user"` 主人偏好 —— 后者是**被有意记录的知识**，不是某一轮对话的残留。
  用户对 `notes` 作**显式**裁定：不参与隔离，并加**可执行的守门用例**（内省 Consult/写入面参数名）。
- **决策④：条目 id 带会话键（缺省 `default`）。** 沿用 store 内**既有**口径
  `key = session_id or "default"`（先例 `_commit_summary` 的 `compaction.summary.{key}`），**不另造第二套**。
  `compaction.fact.<key>.<i>` / `compaction.open.<key>.<i>` / `skills.miss.<key>.<n>` ⇒ 跨会话不再同名覆盖。
- **决策⑤：不上每会话实例；不动 `LoopPlugin.perceive` 协议签名。** phase-19 E2 / change `0048` 已裁
  「会话标识透传 + 单店按会话归组」，**否决**每会话 `(loop, memory)` 实例 ⇒ 本 change 只给既有读写路径
  补会话维度。会话标识经 `LoopContext.session_id`（新增字段）**随上下文包传递**至推理期（装配检索 +
  技能路由）；`perceive` **协议面保持一参**（实现层加可选 kwarg 即结构满足），避免逼所有替身改签名。
  技能路由注解放宽为 `Callable[..., list[SkillHint]]`（既有 1 参闭包/替身仍可赋值）。
- **已知局限（照实登记）**：
  1. 存量 `memory.jsonl` 的未归属历史条目**成为全局层**（对任何非空会话可见）—— 向后兼容的代价。
  2. `notes` **不隔离**（显式裁定）：笔记是刻意知识，跨会话共享。
  3. **同一会话内连续压实 / 跨进程重启**的 id 仍会复用覆盖（`{key}.{i}` 的 `i` 单次调用内递增、
     `skills.miss` 计数进程内递增）—— **既有缺陷**，登记 `phase-28.md` 残留面，本 change 不扩范围。
  4. 未归属读（`session_id == ""`）路径上**专属分区 fail-open**（见决策②）。
- **规格**：`memory` **ADDED**「按会话隔离的检索」；`context`（动态上下文构建 / 上下文自动压实）、
  `loop`、`skills`、`pet-mode`、`orchestration`、`ui`、`notes` 各 **MODIFIED**。**非** `skip_specs`。

## ADR-0108：对话转录**另立存储**（非记忆层级）+ 历史经 `LoopContext.history` 回灌（change 0115 / phase-28 E49）

- **背景**：change `0114` / ADR-0107 让 `session_id` 成为**推理期记忆检索**的归属维度；但用户要的
  「开 N 个会话、**查看记录**、**继续聊天**」还缺三块，且**互相耦合**：
  1. **无转录**：`DefaultLoop.perceive`（`loop/default.py:411` 附近）是 `ctx.messages` 的**唯一**构造点，
     只装 `[{"role":"user","content":user_input}]`；`planner._build_request` = 一条 system + 全部
     `ctx.messages`、**零截断** ⇒ **刷新即失忆**，「继续聊天」无从谈起。
  2. **看不到记录**：`GET /sessions` 从未被 SPA 调用，也没有按会话取历史的端点。
  3. **列表不可用**：注册表条目只有 `{session_id, mode, created_at}` —— 32 位 hex 肉眼不可辨。
- **决策①：转录**新建**（`memory/transcript.py`），不复用 L2 记忆。** 八条实证，任一条即否决：
  (a) L2 排名是**倒排 + 温度**，**无时序保证** ⇒ 回放会乱序；(b) **user 原文从未写入 memory**
  （`remember` 只落模型答复与工具观察）⇒ 无从「重建」历史；(c) 既有注入摘要裁剪到 `[:2048]`；
  (d) 读侧过滤是 `session_id in ("", sid)` ⇒ 会**灌入全局层**；(e) 读路径带 `reuse_count += 1`
  ⇒ **回放会扭曲 `_decay_score`**（记忆被「历史回放」反复强化）；(f) 随 `budget` 的**跳选**不可复现；
  (g) `forget` 把低分条目**迁 L4** ⇒ 对话会被遗忘机制吞掉；(h) L2 线性膨胀触发节流。
- **决策②：转录落盘 = 单文件 + 逐行 `O_APPEND`。** `os.open(path, O_APPEND|O_CREAT|O_WRONLY)` +
  单次 `os.write` 整行 —— POSIX 追加对**小于 PIPE_BUF** 的整行写是原子的，跨进程并发追加不写坏行；
  `Path.open("a")` 带缓冲、**跨进程不原子**，故不用。**否决**每会话一文件：多一层目录生命周期，
  且会产生「会话已建、消息文件未建」的**中间态**。与记忆**同店形态**（单店 + `session_id` 列），
  不翻案 change `0048`（否决每会话存储实例）。
- **决策③：`history` 是 `LoopContext` 的**新字段**，**不**前置进 `ctx.messages`。** 实证：`ctx.messages[0]`
  被**四处**当「本轮任务」——`default._task_text:87`、`default._echo:540`、`planner._task:183`；
  `ctx.messages[1:]` 被 `_action_steps:95` 当动作序列。前置即**同时打破四处**，且技能路由 / 动作抽取
  会把历史当本轮动作。
- **决策④：转录**只存** `(user 原话, 最终 assistant 回复)` 两行，**不存** `ctx.messages`。** `ctx.messages`
  含 `role="tool"` 观察（`_record_observation` 写入），而 `planner._to_messages:192` → `stdlib_provider:196`
  是**逐条 1:1** 发 `{"role", "content"}`、**不带 `tool_calls` 信封** ⇒ 把历史 `role="tool"` 回放给
  OpenAI 兼容端点**大概率 400**。按 (user, reply) 存/灌同时解决 **wire 格式 / token 体积 / 标题抽取**。
- **决策⑤：`title` / `updated_at` **从转录派生**，**不写注册表**。** 先例 ADR-0098（删 `_published`，
  拒第二真源）：标题是**读模型**，落进 `conversations.json` 即第二真源。派生面在
  `TranscriptStore.summaries()`；`api.list_sessions` 注入转录时**逐条附齐** `title`（无用户消息 ⇒
  空串）与 `updated_at`（无转录 ⇒ 回落注册表 `created_at`）—— 消费方**无需为缺键特判**；**未注入**
  转录 ⇒ 条目形状逐字不变（只增不减）。
- **决策⑥：`LoopContext.history` 的**双重上界** = `min(最近 N 轮, token 切片)`，切片 = `token_budget // 2`。**
  否则历史自身可能 ≥ `token_budget` ⇒ **第 1 轮就跑完立即 `TOKEN_BUDGET_EXCEEDED`**，且
  `_should_compact` 从首轮起按 token 维**误触发**。留一半给本轮消息 / 系统提示 / 工具观察。
  历史 token 按**既有** `len // 4` 口径计入 `token_used`（预算终止与压实**看得见**历史）。
- **决策⑦：落盘时点 = `perceive` 落 user 行 + `astream` 收尾**在 `self.remember(...)` **之前**落 reply，
  且**门控 `not limit_reason`**。 `astream` 收尾处 `if limit_reason:` 会把 `ctx.reply` **覆盖为合成串**
  （`f"{limit_reason}: 本轮终止"`）⇒ 此时落盘即**谎报模型原话**。录在 `remember` 之前 ⇒ 记忆写入炸掉
  也不丢对话（两处**各自** `try/except` 降级 + `warnings.warn`，不阻断主流程）。**不动** `EffectTracker`：
  既有 `remember` 同样不经它 —— 据实写明，**不假装可逆**。
- **决策⑧：`loop.history_turns` 走**独立访问器** `ConfigManager.history_turns()`，**不**扩 `loop_limits()` 元组。**
  后者被 **20+ 处**解包断言钉死（`limits[0]` / `limits[1]`），且会话回灌与**预算派生**无语义关系，
  塞进同一元组是**概念污染**；先例 `permission_mode()` / `sandbox_host_allowlist()` 同为标量访问器。
  `0` = 关闭回灌（合法值，用于「只要隔离不要上下文」的部署）。经 `LimitsConfigurable.set_limits`
  **加第三 keyword** 热推（扩展而非另立协议）：本仓 `_merge_patch` 源码注释把「报成功却不生效」
  显式列为**缺陷类**，故保存配置必须**同时**落盘与生效。
- **决策⑨：L4 措辞校正属本 change（先修旧账，也是新 Requirement 的前提）。** canonical
  `memory/spec.md:9` 把 L4 写作「**原始会话**」，与**同文档** `:119`（压实归档层）、`:181`（遗忘归档层）
  及实现（`forget` 迁 L4、检索降权 `relevance.py:24` `"L4": 0.2`）**自相矛盾**。「转录」这一新概念
  要进 `memory` 包，必须先消掉同一文档里「L4 才是原始会话」的误导性表述。
- **已知局限（照实登记）**：
  1. **注册表进程内锁不跨进程**：同进程多线程 `create` 已互斥（`RLock`）；**跨进程**同刻并发创建
     不受保护（`ui/spec.md` 已据实收窄，不再声称跨进程安全）。
  2. **转录单文件随会话数线性增长**，读单会话需全扫文件（当前规模无碍；分片留待真实压力）。
  3. **有界牺牲**：超出 N 轮 / 超出 token 切片的历史**不回灌**（不做摘要压缩，避免引入「回灌的是
     摘要还是原话」的新歧义）。
  4. **历史与 reason 阶段 L2 检索的重复**：`remember` 落的主 loop 条目 `source="loop"`、同 `session_id`，
     装配器只排除 `("beast.",)` ⇒ 同会话过往轮次**今天就已**作为「相关事实」进 system prompt；
     本 change 只是加了**时序完整**的第二份。**不修**（判据：改变检索行为超出本 change 范围）。
     修法备查：reason 阶段排除 `("beast.", "loop")` —— `store.py:111` 已支持多前缀且该点**先于**
     排名/预算。
  5. `conversations.json` 丢失/损坏 ⇒ 注册表**空态启动**，转录成为**孤儿数据**但端点按既有
     **fail-closed 拒绝**（`ui/spec.md` 的未登记拒绝**不放宽**）。
- **规格**：`memory`（MODIFIED「分层记忆模型」L4 校正 + ADDED「对话转录持久化（非记忆层级）」）、
  `loop`（MODIFIED「执行循环」）、`configuration`（MODIFIED「循环预算配置」）、`ui`（ADDED「会话转录的
  读取面」+ MODIFIED「会话注册表持久化与跨入口共享」）。**非** `skip_specs`。

---

## ADR-0109：会话转录的**消费面**接线 —— Web 右栏列表 + CLI `session show` / `--session` 续聊（change 0116 / phase-28 E49）

- **背景**：ADR-0108 只交付**机制**（转录落盘、读取端点、派生标题、有界回灌）。**零消费方** ⇒ 机制
  悬空（`api.js` 无 `listSessions`、`Chat.svelte` 的 `lines` 是纯内存 `$state`、`repl.py` 硬编码
  `api.create_session("cli")`）。本 ADR 记录**接入既有机制**时的四处取舍。
- **决策①：CLI 续聊复用**同名** `--session <id>`（顶层 flag），不新造参数名。** 既有先例
  `run --session`（`entry.py` `_add_run_parser`）语义相同（复用既有会话、不新建）。`argparse` 子解析器
  的默认值只在属性**缺席**时套用 ⇒ 与 `run --session` 同 `dest` **不冲突**（已由既有用例覆盖）。
- **决策②：`CLIBridge.connect_impl` 签名扩为 `Callable[[UIAPILayer, str], None]`。** 会话标识必须到达
  `build_app`（今天硬编码新建），而**不**绕过 `CLIBridge`（绕过即让 `cli_bridge` 沦为死代码，
  破「三模桥接」的单一入口）。代价是与注入点对齐（测试替身两处）。
- **决策③：Web 端**显式新建**取代首条消息**惰性**建会话。** 惰性路径会在每次打开页面留下 32 位 hex 的
  **空会话**，与「列表记录了当前已创建会话」直接冲突 ⇒ 无选中会话时发送被拒绝并提示，由「新建会话」
  按钮显式创建。**呈现层**承担 `updated_at` 降序排序（后端响应形状不动，ADR-0108 的兼容承诺不破）。
- **决策④：续聊时把既有转录**渲染进 TUI 时间线**。** 否则按 `--session` 进来看到空时间线、以为没接上
  （模型有上下文、界面没显示 ⇒ 误导）。复用既有 `.echo`/`.hint` 样式与 `escape`，**不新增渲染通道**。
- **已知局限**：① 会话列表全量拉取 + 前端排序，会话数很大时无分页（与 ADR-0108 的单文件全扫同源）；
  ② SPA 无 JS 测试基建 ⇒ 前端靠 `npm run build` + 离线冒烟验证（四门禁覆盖 Python 侧）；
  ③ 未选中会话时发送被拒是**有意**的 UX 代价（换取列表不留空会话）。
- **规格**：`cli-ops`（ADDED「会话命令族与交互入口续聊」）、`ui`（ADDED「Web 会话列表与切换」）。
  **非** `skip_specs`。

---

## ADR-0110：未命中记录 id **内容派生** + 记忆排除面的**例外面**；神兽放行自身命名空间（change 0117 / phase-30 分支 A）

- **背景**：`coding-plan/phase-30.md` 承接 Phase 28 收口后的三条剩余项（E48 / E44 / E45-隔离），2026-10-06
  用户裁决「全部按建议」⇒ **分支 A**（**E48-b + E54 同一 change**），另三条（E48-a / E44 / E45-隔离(i)）
  **登记为有意行为**（零代码，见下「登记项」）。两条代码项同属**派生 / 接线副作用**，非规格违约
  （未放宽任何既有约束）。
- **决策①：未命中记录 id 由**任务内容**派生（`blake2b(task, digest_size=8)`），弃用 `len(self.misses)` 计数。**
  计数是**进程内**状态 ⇒ 重启后重数，新的未命中会 upsert **覆盖**上一进程留下的同会话条目（事件记录真丢
  数据）。内容派生后：跨进程稳定；同会话重复未命中**同一任务** ⇒ **幂等刷新同一条**（未命中清单本就按任务
  去重，供技能沉淀，且天然有界）。用 `blake2b` 而非 `hash()` —— 后者对 `str` 有**逐进程随机盐**
  （`PYTHONHASHSEED`），跨进程不稳定等于没修。先例：同包 `skills/sop.py:_skill_id_for`。
- **决策②：`misses` 保留 `list` 类型，只做**原地裁剪**（`del` 切片）至 `_MISS_WINDOW = 64`。**
  换 `deque(maxlen=N)` 会静默打断 6 处既有断言（`deque([...]) == [...]` 为 `False`）；裁剪保持类型与对象
  身份，断言逐字通过。该列表**无生产消费方**（全仓仅 `router.py` 自身 + 测试断言）⇒ 定为**诊断窗口**，
  沉淀判定不依赖它。
- **决策③：记忆排除面（`exclude_source_prefixes`）增**例外面** `allow_source_prefixes`，语义为「命中排除
  **且**未命中放行 ⇒ 剔除」。** 封存（`source=beast.*`）须保留，但神兽需要读**自己**的轨迹 ⇒ 需要
  「排除 A 类、放行其中 B」这一维度，而 `startswith(tuple)` 只能整体放行或整体排除。缺省两参数均为空元组
  ⇒ 检索语义逐字不变；排除面为空时放行面**不产生任何效果**（无排除即无所放行）。
- **决策④：神兽用**派生装配器**（`DynamicAssembler.with_allow_source_prefixes`），不原地改、不另建。**
  主 loop 与神兽**共用**一份装配器配置（`runtime.py:559-567` 一次性构造），原地改会波及主 loop（破封存
  红线）；**派生**保证「同一配置 + 换放行面」，且 `build_runtime(assembler=…)` 注入路径下神兽拿到的是
  **同一配置**的变体，而非用 `profile` 重建的第二真源。主装配器的 `exclude_source_prefixes=("beast.",)`
  **逐字不动**。
- **决策⑤：放行项是**精确的自身 `agent_id`**（如 `beast.qinglong`），他兽仍被排除。** 隔离语义由此从
  「兽↔主」扩到隐含的「兽↔兽」（今天由 `beast.` 前缀 + 会话过滤并存保证）。
- **判据订正（相对 phase-30 §2.4 修法①的原文）**：原文含「排除 `loop` 与**他兽**前缀」一项，勘察后**不纳入
  排除 `loop`**：① 不解决 E54；② 只能摘掉主 loop 一个来源（主 L2 事实还来自 `context` 压实 / `skills` /
  `orchestration` / `pet`）⇒ **隔离面不一致**；③ 与 `memory/spec.md`「按会话隔离的检索」明文（推理面
  **必须保留全局层**，否则人格与笔记进不了 prompt）相悖。⇒ 只做最小面：**放行自身、他兽仍排除、主侧
  可见面逐字不变**。
- **登记项（本 change 零代码改动，随 ADR 落账）**：① **E48-a** 压实产物 `compaction.fact.{key}.{i}` 同会话
  覆盖 —— 判为**刷新式派生**（facts 由**当前**记忆重派生，新批次取代旧批次；反向若「保留历史」**须同时**
  引入有界淘汰，否则 L2 随压实次数线性膨胀）；② **E44** 压实 ≠ 压缩（`_compact` 不裁 `ctx.messages`）——
  **有意行为**（预算三层可配 + 跨轮历史已由 change `0115` 有界回灌 + 摘要替换违「不谎报」+ 超预算以
  `TOKEN_BUDGET_EXCEEDED` 显式终止；先例 phase-19 E6）；③ **E45-隔离(i)** 主与兽**同读全局层**
  （`session_id == ""`，含 L0 人格与 `notes`）—— 用户「严格隔离 + **保留全局层**」裁决的有意结果，
  不重复裁决。
- **已知局限**：① 放行面是**前缀**匹配 ⇒ 若未来出现「一个 `agent_id` 是另一个的前缀」的命名（今天
  `beast.<拼音>` 不会），放行自身会连带放行他者 —— 须改精确匹配；② 内容派生后同一会话对同一任务只留
  **一条** ⇒ 丢失「未命中**次数**」频次信息（本来无人消费；如需要须另立计数列，不复用 id）；
  ③ `misses` 窗口裁剪后「全量未命中」不可回溯（诊断面牺牲；事件面以 L2 条目为准）；
  ④ 神兽仍读不到**他兽**命名空间（**有意**，与封存同向）。
- **规格**：`skills`（MODIFIED「技能路由」）、`memory`（ADDED「来源前缀排除与放行（读取面）」）、
  `beast-mode`（MODIFIED「Independent Sub-Agent with Shared Capability」）。**非** `skip_specs`。

---

## ADR-0111：宠物记忆**独立命名空间**（`source="pet"` + 主侧封存 + 自身放行）（change 0118 / phase-30 §8-A）

- **背景**：`coding-plan/phase-30.md` §8-A 登记的**唯一待裁决项** —— `_pet_loop`（`runtime.py`
  `_pet_loop()`）构造 `DefaultLoop` 时**不传 `source=`** ⇒ 宠物自治轨迹以默认 `source="loop"` 落库，
  与主 Agent **同命名空间**。2026-10-06 用户裁决「**物接独立命名空间，先做**」，取向＝与 phase-26 神兽
  **同型**（标注 + 封存 + 自放行）。**契约面**：`pet-mode` spec 此前只钉了宠物轨迹的**会话归属**
  （`session_id`）与主人偏好 `source=user` 的全局层地位，**未规定轨迹命名空间** ⇒ 本 change 是**新增能力**
  ⇒ **规格先行**（`pet-mode` MODIFIED，**非** `skip_specs`；先例 change `0028`）。与 phase-26 神兽**不可
  类比**：`beast-mode` spec `:54` 早已明写「独立记忆命名空间」，那次断的只是**接线**。
- **决策①：修的是**可达泄漏**，不是命名整洁。** 泄漏路径：`MemoryStore.read` 的会话过滤**仅在
  `session_id` 非空时生效**（change `0114` 语义，空串 **fail-open**）。主 Agent 以**未带会话**方式运行
  （CLI 一次性 `run`、库层直调 `DefaultLoop()`）时，宠物轨迹（`session_id=宠物会话 id`）**不被会话面挡住**，
  且因 `source="loop"` 也不被来源面挡住 ⇒ **被主 Agent 读成自身 L2 事实**（system prompt 污染）。补上
  `source` 维度后，排除面成为该路径下的**唯一防线**。
- **决策②：命名空间取**常量 `"pet"`**，而非 `pet.<个体 id>`（订正 §8-A 决策点①的原文表述）。** 宠物 loop 是
  **单实例共享**（一只 `pet_loop` 被 `PetManager` 的 factory 复用于所有宠物会话）—— `source` 在 loop
  **构造期固定**，无法承载个体 id。故 **`source` = 子系统身份**、**`session_id` = 个体身份**（哪只宠物）。
  与神兽不同（神兽**每兽一个 loop 实例** ⇒ `source=beast.<agent_id>` 天然带个体），但两者语义闭合：
  `source` 划 **Agent 身份**，个体粒度由 `session_id` 承载 —— 规格明写二者**同时成立、互不替代**。
- **决策③：排除前缀用**裸根** `"pet"`。** 命名空间字符串就是 `"pet"`，`startswith("pet.")` **不命中**自身。
  全仓 `source` 字面量全集 = `loop` / `beast.<id>` / `user` / `core-profile` / `evolution` / `skills` /
  `context` / `notes.turn` —— **无一以 `pet` 开头** ⇒ 裸前缀无语义误伤。
- **决策④：宠物用**派生装配器**（`with_allow_source_prefixes("pet")`），不原地改。** 与 ADR-0110 决策④
  同机制：主 loop、神兽、子 Agent **共用**同一份装配器配置，原地改放行面会波及全体（破封存红线）；
  派生保证「同一配置 + 换放行面」。主装配器的 `"beast."` **逐字不动**（phase-26 E37/E38/E39 红线），
  仅**追加** `"pet"`。
- **决策⑤：宠物**只放行自身**，不放行神兽。** 派生实例的排除面仍是 `("beast.", "pet")`、放行面仅 `"pet"`
  ⇒ 宠物读不到 `beast.*`（后台自治体之间亦不混同）。**神兽装配面**由同一配置派生 ⇒ 亦不命中 `pet`：
  语义一致，且**今日无实际行为变化**（神兽读取恒带 `session_id=beast.<agent_id>`，宠物条目本就被会话
  过滤挡下）—— 据实写明，不夸大为行为变更。
- **决策⑥：主人偏好通道逐字不动。** `PetSession.observe` 的 `source="user"`（刻意知识、全局层，
  spec `:233/:239`）不受命名空间封存影响 —— 排除面只加 `"pet"`，不触碰 `user`。
- **已知局限**：① 命名空间是**常量** ⇒ 若未来改为「每宠物独立 `(loop, memory)` 实例」（change `0048` 已裁
  否决），须重开本条（改 `source=pet.<id>` + 逃逸放行面）；② 排除面是**前缀**匹配 ⇒ 若未来出现以 `pet`
  开头的**其他**来源命名，会被**静默封存**（今天全集已穷举，无此风险）；③ 主 Agent **未带会话**时不再
  看到宠物自治所得 —— 这是**本 change 的目的**，但意味着「宠物发现 + 主线复用」需**显式**经主人偏好或
  `notes` 等全局层通道，**无隐式捷径**；④ **未**改 `DefaultLoop.remember` 的 `id=f"loop.{trace_id}"` 硬编码
  （与神兽同型：神兽条目亦为 `id=loop.<trace_id>` + `source=beast.*`；change `0048`/phase-26 有意保留）。
- **规格**：`pet-mode`（MODIFIED「Pet Session Runtime Wiring」，+4 Scenario）。**非** `skip_specs`。

---

## ADR-0112：结晶面门的**数据面** —— 基准集/基线落盘 + 真实留出评分（change 0119 / phase-31 切片 1）

- **背景**：`coding-plan/phase-31.md` 立账的 RSI 能力缺口 G1–G5。用户 2026-10-06 裁决 §4.1 六点：
  ① **立账为能力缺口**（非「装配选择」）、⑥ **拆两次**（先 G4+G3 数据面，后 G1+G2 判定面）—— 本 ADR
  记**切片 1**。一手缺口：`evaluator.py` 的 `BenchmarkRegistry` 只建**进程内 dict**（无 `path`）⇒ 基准与
  基线跨进程蒸发；`_held_out_score` 无 `score_fn` 时**返 `0.0`**；`baseline_score` 未注册 ⇒ **`0.0`**
  ⇒ `held_out(0.0) < baseline(0.0) - margin(0.0)` **恒假** ⇒ **恒 `publish`**；全仓 `set_baseline` /
  `score_fn=` **零生产调用点**；`runtime.py` 是 `Validator(), Evaluator()` **无参**（连注入点都没有）。
  **契约面**：`evolution` spec 三处 Requirement 此前**未写**「留出分由谁产出 / 基准从哪来 / 无法评测
  怎么办」⇒ 本 change 是**新增条款** ⇒ **规格先行**（`evolution` MODIFIED ×3，**非** `skip_specs`）。
- **决策①：数据面与执行面**分离**。** 基准集与基线是**数据**（人工/运维注册、落 `$CORE_STATE_DIR` 单文件、
  跨进程可读）；基准样本的**执行器**（`task_type` → 可调用体）是**受信代码**，由**组合根或运维注入**、
  **不随数据面落盘**。理由：落盘的数据可被任何写文件者改动 —— 若执行器也随之落盘，「注册基准」就等同
  「注入代码」，数据面沦为代码注入面（破 phase-31 §6 自我弱化防线）。分离后注册只改**评测口径**、
  改不了**执行语义**。
- **决策②：口径版本随**候选台账**落盘，投放（`crystallize`）时校验（`GATE_CALIBER = 1`）。**
  此为裁决 ⑤ 的落地形态，**判据订正两点**（见下方 (a)）：载体是 `GenerationCandidate.caliber`（提案时
  盖现口径、随 `PendingQueue` JSON 落盘），判定点是 `crystallize`；缺该字段的**落盘旧行解析为 `0`**
  （＝口径字段引入前）⇒ 一律拒绝（**不** fail-open）。拒绝走结构化错误 `GATE_CALIBER_STALE`，措辞
  **SHALL NOT** 记为「未过门 / 退化」（那些判定在旧口径下并未发生）。
- **决策③：无法评测 ⇒ `freeze`（第三态），与 `rollback` 语义分离。** 留出分**不可得**（候选无绑定基准 /
  基准无样本 / 执行器未注册 / 未注册基线）时判 `EvalReport.verdict="freeze"`；`run_cycle` 记
  `EvolutionOutcome.status="frozen"`（**词表 +1**，先例 ADR-0100 `accepted`）；`crystallize` 遇 freeze
  报告 ⇒ `EVAL_FROZEN`「候选无法评测、未过留出评测」。**SHALL NOT** 把「无法评测」记成 `rollback`
  （那是「已判退化」，无证据不得如此声称）。同批把 `EVAL_REGRESSED` 的措辞由「候选留出集退化」改为
  「候选未过留出评测」（原措辞把「未过」与「退化」混同）。
- **决策④：阈值口径 = 已注册基线即**绝对阈值**；未注册基线归入「无法评测」。** 判定面只用
  `baseline_of() -> float | None`（未注册 ⇒ `None`）；`baseline_score()`（缺省 `0.0`）**保留**供旧
  调用方读，但**不再**充当判定阈值 —— 未注册基线**不再**被静默当作 `0.0` 的「宽松阈值」放行。
  `margin` 构造参数**逐字不动**（缺省 `0.0` = 分毫不许退）。
- **决策⑤：组合根暂**不接执行器**，产线恒 `frozen`（据实，不含糊）。** `runtime.build_runtime` 注入
  落盘 `BenchmarkRegistry` + `BenchmarkScorer(registry)`（`runners` 空）；生产无通用任务执行器面 ⇒
  每个候选判 `frozen`（**不再凭空 publish**）。这是裁决 ① 的**有意结果**：fail-closed 优先于「看得出
  在动」；接真实执行器是**另一 change**（reopen 条件见已知局限①）。
- **判据订正 3 条**：**(a)** 裁决 ⑤ 原文「门加口径版本字段 / 历史候选集体未过门」—— 一手核实后订正：
  ① `crystallize` 读的是台账里**已记录**的结论、**不重算** ⇒ 「历史候选在新口径下集体未过门」结构上
  **不会发生**；② 真实危害方向**相反** —— 是「历史候选带着**旧口径（桩）产出的假通过**结论被投放」
  （候选过了人工 `confirm` 即进 `crystallize`，其 gate/eval 是桩给的 `passed=True` / `verdict="publish"`）。
  故守卫设在**「记录 → 投放」之间**（台账盖章 + 投放校验），**同一机制闭合两个方向**，仅订正载体与
  判定点。**(b)** 「绝对阈值起步」= `margin` 保持缺省 `0.0`、**注册的基线分就是阈值**（不给 `margin`
  换默认值 —— 换默认值会同时改观察期容差语义面）。**(c)** 结局词表 +1 `frozen` 是**诚实化**（非新增
  能力）：不改它则「无法评测」被 `run_cycle` 的「非 publish 一律 rollback」**谎报为退化**。
- **已知局限**：① **生产未接执行器 ⇒ 所有候选恒 `frozen`**（**reopen 条件**：接入真实任务执行器面并
  把 `runners` 注入组合根）；② **无 CLI 注册面**（运维注册 = 落盘状态文件 + 库函数 `register` /
  `set_baseline`）；③ 落盘走 `write_state` 原子写，但**无跨进程锁**（注册/设基线只发生在启动期与运维期，
  照实登记、不假称安全）；④ `freeze` 报告的 `held_out_score` 记 `0.0` **无意义**（消费者 SHALL 只认
  `verdict`）；⑤ `_held_out_score` 无打分器由原返 `0.0` 改为返 `None` —— 既有依赖「无 `score_fn` ⇒
  0.0」的调用方须改（全仓无生产调用方，仅测试）。
- **规格**：`evolution`（MODIFIED「验证门」+2 Scenario、「留出评测」+2 Scenario、「评测基建」+3
  Scenario）。**非** `skip_specs`。

---

## ADR-0113：结晶面门的**判定面** —— 真实 review + 真实运行时测试（change 0120 / phase-31 切片 2）

- **背景**：`coding-plan/phase-31.md` 立账的 RSI 能力缺口 G1–G5。用户 2026-10-06 裁决 §4.1 六点，
  ⑥ **拆两次** —— 切片 1（数据面，ADR-0112）已闭；本 ADR 记**切片 2（判定面 G1 + G2）**。一手缺口：
  `validator.py` 的 `_review_pass` 恒 `True`、`_no_tests` 返 `{}`（空 dict 的 `all()` 为 **真**）且二者
  是 `__init__` 的**缺省** ⇒ 验证门**恒通过**；`runtime.py` 是 `validator=Validator()` **无参**（连注入点
  都没有）。引擎**确实消费** `gate.passed`（`engine.py` 不通过即 `status="rejected"`）⇒ 缺口**不在接线**
  在**产出的值恒为常量** ⇒ 「不合格候选被挡在门外」这句承诺不成立、`rejected` **生产不可达**（G5）。
  **契约面**：`evolution` spec「验证门」此前只写「SHALL 对候选执行 review + 运行时测试」而**未写谁产出这两个
  判据** ⇒ 本 change 是**新增条款** ⇒ **规格先行**（`evolution` MODIFIED，**非** `skip_specs`）。
- **决策①：判定面留在 `run_cycle` 的 `validate` 阶段（冷路径），不挪到操作面。** `if not gate.passed:
  return rejected` 是 spec「通过才允许发布」的**唯一**落点；把它挪到 `confirm`/`crystallize` 会让该分支在
  生产**仍然不可达**（候选恒定 `pending`、拒绝改由投放报错表现）—— 正是本 Phase 要消除的形态（G5 验收锚点）。
  **代价如实登记**：冷路径在 loop 收尾**同步**跑子进程门禁（`pytest -q` 数十秒）+ 一次 review 模型调用；
  仅当「维护节拍（缺省 900s）到点 **且** 触发阈值命中 **且** 确有可归因证据」时发生，但确实推迟该轮收尾。
- **决策②：review 的生产者 = 结构化审查者（组合根注入的模型调用）+ **fail-closed** 判定。**
  `build_review_prompt` 渲染候选**自身是否自洽**的判据面（`kind` / `target_plugin` / `delta`），模型调用
  经 `review_with(_llm_text)` 注入 —— 复用 `author.py` 已建立的接缝（ADR-0045 依赖方向：prompt 文本属
  evolution 域，evolution **不 import 任何 LLM 抽象**）。判定只认**首行以「通过词」起首**（`PASS` / `通过`）；
  空输出 / 词表外 / 调用抛异常 ⇒ **未通过**（不得以「看不懂」当通过）。审的是**自洽性**而非「收益」（收益
  无留出集不得声称）；也不评实现细节（那是实施面的事）。
- **决策③：运行时测试的生产者 = 门禁命令单一真源 `GATE_COMMANDS` **按标记派生**的子集。**
  新增 `CRYSTALLIZATION_GATE_MARKS`（门名 → 可读理由；**只标门名、不复制命令字符串**）+ `crystallization_gates()`
  按**真源顺序**派生（标记命中未注册门名 ⇒ `CiCdError(GATE_FAILED)`，fail-closed —— 标记与真源漂移必须
  炸出来、不得静默少跑一门）。结晶面取两道：`lint`（`ruff check`，轻量静态门，亚秒级）与 `test`（`pytest -q`，
  行为回归门）；`typecheck`（`pyright`）与 `build`（`uv build`）**不进**结晶面 —— 类型卫生与打包属**交付面**
  判据，与「该候选能否发布」无因果关系且成本高（phase-31 §6 红线：门禁**单一真源**不另立）。执行面复用
  `SubprocessGateExecutor`（「跑不起来」与「跑失败」同归为该门未通过，不外抛）。
- **决策④：缺省 `Validator()` = **不得放行**（fail-closed），与切片 1 的 `Evaluator()` 缺省同型。**
  未注入生产者 ⇒ `GateReport.passed=False` 且理由据实写明「未注入生产者」；只注入一半判据同样不得放行。
  理由：spec「**通过才**允许发布」在「无判据」时**不得**成立；留着 fail-open 缺省等于把 G1/G2 留在类里等
  下一个装配者踩。**顺带**：`review` 未过时 **fail-fast**（不再跑子进程门禁）—— 门已未过，不做无谓开销。
- **决策⑤：口径版本递增 `GATE_CALIBER` 1 → 2。** 判定口径真的变了（两个判据从恒真桩换成真判据）⇒ 按
  ADR-0112 决策② 的机制，**旧口径候选**（= 按恒通过桩判定的候选，含切片 1 时落入台账者）在 `crystallize`
  时被 `GATE_CALIBER_STALE` 拒绝，须按现口径**重新提案**；历史结论**不重算**（同机制，无新代码）。
- **判据订正 3 条**：**(a)** 判定面**位置**不是自由选择：phase-27 §7 记「同步四门阻塞 ⇒ 改操作面显式驱动」
  是针对**实施面**（`EvolutionExecutor`，其门跑的是**候选专属产物**）的处置，**不可照搬**到结晶面（其门跑
  **仓库级回归**、且 `rejected` 分支只此一处）—— 见决策①；作废「把验证门挪到操作面」这一原设修法。
  **(b)** 结果载体 `test_results` **保持 `dict[str, bool]`**（不塞失败原因字符串）：`validate` 用
  `all(test_results.values())` 汇总结论，值里若混入非空**字符串**会被当成真值 ⇒ **失败读成通过**（与 G2 同源
  的语义陷阱）；失败原因不进门报告（要看的是「哪道门没过」，review 面文本另有 `GateReport.review`）。
  **(c)** 「未过门 ⇒ 教训写回 L2/L3」（spec 场景「未过门丢弃」的后半句）本 change **不做**：`run_cycle` 的
  `rejected` 分支今日即不写记忆，属既有形态，不夹带（该场景前半句「丢弃候选」已满足）。
- **已知局限**：① **冷路径同步跑子进程门禁**（每轮维护节拍命中时约数十秒；`pytest -q` 单次 ≈40s），
  **reopen 条件** = 冷路径异步化（独立 change），本 change 不假称无代价；② **review 质量取决于模型与词表** ——
  词表只认首行起首词，模型若先寒暄再给 PASS 会被判未过（**有意** fail-closed：宁可漏报不误放）；③ 结晶面门禁
  是**仓库级**基线健康检查，与**候选内容无关**（技能级候选本无代码产物）；候选**专属**产物的验证仍在**实施面**
  （`EvolutionExecutor` 冻结门，spec「门禁独立性」），两门不同源、不互替；④ **生产未配模型 ⇒ 候选恒
  `rejected`**（**有意**：无审查判据即不得发布；组合根按既有约定注入模型调用，配置面与其它 DI 接缝一致）；
  ⑤ 既有依赖「缺省 `Validator()` 即通过」的用例须**改判**（7 个测试文件，逐处显式注入过门替身；读数器仍
  是真 `Validator`，`validate` 的汇总逻辑不打折）。
- **规格**：`evolution`（MODIFIED「验证门」+5 条生产者/诚实条款 + 5 Scenario：「未注入生产者不得放行」
  「review 判定不可解析不得放行」「结晶面门禁子集按标记派生」「运行时测试未过则门未过」「结晶面门禁经独立
  执行面运行」）。**非** `skip_specs`。

---

## ADR-0114：子任务**运行态实时回流** —— `subtask_progress` 事件（change 0121 / phase-29 change A：E51）

- **背景**：`coding-plan/phase-29.md` 的缺口 **E51**（用户需求②「串行/并行都需 CLI + web/app 动态显示子
  agent 主题 + 运行状态」的**数据面**）；phase-29 §6 已裁决该 Phase 拆 A/B/C/D 四 change，本 change 是最小的
  **A**。一手缺口：`scheduler.py` 的 `_run_subtask` 以 `await profile.loop.arun(goal)` **只取终态** `LoopResult`
  ⇒ 子 Agent 的动作/步进中间态在**编排层被吞**，CLI/Web 只能看到「开始 / 完成」两个离散点。**通道面**：
  `Emit` 早已是 `_run_subtask` 形参、`_fan_out` 已透传、`run` 已排水（`asyncio.Queue`）、`api.py` 的 `run_task`
  已把编排事件映射为 `task.*` SSE ⇒ **外送通道与消费面均已存在**，缺的只是**产出**。契约面：`orchestration`
  spec「任务入口与进度事件」的进度事件词表**无运行态事件** ⇒ 本 change **规格先行**（MODIFIED，**非** `skip_specs`）。
- **决策①：复用既有通道，不另建旁路。** 回流与 `subtask_started` / `subtask_completed` **同源同序**（同一条
  `emit` → `run` 排水 → `run_task` 映射链）。新事件 `subtask_progress` 载荷 = `task_id` / `subtask_id` /
  `event`（内层事件类型）/ `data`（白名单载荷）/ `ts`。**不**新增 emit 参数、**不**改 `_fan_out` 结构。
- **决策②：里程碑 + **封闭白名单**载荷。** 只回流三类里程碑：`action_started` / `action_completed` /
  `step_completed`；**显式排除**模型流式原文 `reply_delta`（既洪泛又暴露未定稿原文）。载荷按内层事件类型
  **白名单取键**（`_PROGRESS_FIELDS`：动作开始 → round / tool_id / args；动作完成 → round / tool_id / ok /
  duration_ms / output；步进完成 → round / failed）；**表外类型（含未来新增）一律不外发**、内层载荷里多带的
  字段（如疑似凭据）一律不取。守「密钥只引用不读取、绝不进日志/记忆/**事件面**」。
- **决策③：终态归一抽为共享实现 `core.loop.collect_result`，`DefaultLoop.arun` 改为其薄壳。**
  `astream` 的「三态归一」（`loop_finished` 取载荷 / `loop_failed` 归 `failed=True` 且回复取 `reason` /
  未达终态不抛）现在有**两个**消费者（`arun` 与编排层），两处各写一遍必然漂移。抽为**纯函数**后语义单一真源；
  该函数**不**进 `LoopPlugin` 协议（不得迫使所有实现新增方法）。**代价如实登记**：编排层由 `arun` 改走
  `astream` ⇒ **5 处测试替身**须从 `arun` 迁到 `astream`（`test_orchestration._TrackingLoop` /
  `_FixedReplyLoop`、`test_phase14._FakeLoop`、`test_phase15._FakeLoop`、
  `test_session_isolation._SessionRecordingLoop`）+ `test_orchestration` 的**帧序列断言**改为忽略回流事件。
  **不提供**「无 `astream` 则回落 `arun`」的兜底 —— `astream` 是协议成员，为测试替身留生产分支不划算
  （`default.py` 的 planner 降级不属此列：`planner=` 是**公开可注入**的裸 callable，确有非流式实现）。
- **判据订正 2 条**：**(a)** 内层键名取 `event` / `data`，**不取** phase-29 §3.2 草记的 `event_type` /
  `payload` —— 后者会造出 `LoopEvent.payload["payload"]` 的嵌套同名，读侧写 `event.payload["payload"]["…"]`
  易错且不可读。**(b)** phase-29 §0.6 记「E51 层面零改动」**不完全**：外送通道确实零改动，但**协议声明面**
  与**测试替身面**有真实改动 —— `LoopPlugin.astream` 原声明为 `async def … -> AsyncIterator[LoopEvent]`
  （= 待 await 的**协程**返回迭代器），与实现（`async def` + `yield` **异步生成器**）**形态不符**；此前
  无任何经 `LoopPlugin` 类型变量的 `async for` 调用 ⇒ 该声明从未被检验。本 change 是第一个消费者，故
  **按实现订正声明**（stub 形式：`def astream(…) -> AsyncIterator[LoopEvent]`），并**顺带**删去 `api.py` 中
  为绕开该不符而写的 `cast`。
- **已知局限**：① 回流只到**编排层事件面**为止 —— **CLI/TUI 呈现**（折叠块展开细节）与 **HTTP 面 + 前端**
  （`POST /task` SSE 路由、任务区视图）分别是 phase-29 **change D / change B**，本 change **不**触；②
  `subtask_progress` 的量级随子 Agent 循环轮数增长（已由「只回里程碑 + 排除 `reply_delta`」压到每轮至多 3 条），
  但**无**节流/采样（消费方按需丢弃；若未来成患，reopen = 事件面加节流）；③ 内层摘要（`args` / `output`）
  的**截断口径**沿用 `default.py` 的 `_MAX_ACTION_EXCERPT`，本 change **不**另设上界；④ 「进入子 agent 会话 /
  回到主 Agent」不在本 change（子 agent 消息流**无数据源** —— 转录只注入主 loop，change `0115` 明文）。
- **规格**：`orchestration`（MODIFIED「任务入口与进度事件」+3 条口径 + 3 Scenario：「子任务运行态实时回流」
  「载荷白名单与非里程碑不外发」「回流不改变终态判定」）。**非** `skip_specs`。

---

## ADR-0115：编排任务的 **HTTP 面与 Web 任务区**（change 0122 / phase-29 change B：E53）

- **背景**：`coding-plan/phase-29.md` 的缺口 **E53**（用户需求②「CLI 和 web/app 都动态显示子 agent 主题 +
  运行状态」的**消费面**）。change `0121`（ADR-0114）已产出运行态事件，但**无处可见**。**判据订正**：
  phase-29 §0.6 原把 E53 归因为「`fastapi_serve` 无 subtask 消费 ⇒ 缺事件转发」，复核后**转发层已在**
  （`api.py` 的 `run_task` 早已把编排事件映射为 `task.*` SSE，且 change `0121` 的新事件**零改动**即已随之透出）；
  **真缺口 = ① HTTP 面未暴露**（`fastapi_serve.py` 的 11 端点**无 `/task` 路由**；`run_task` 的生产消费者
  **只有 CLI** `repl.py` 的 `/task`）+ **② 前端为零**（3 视图、`lib/api.js` 无 task 导出）。契约面：`ui` spec
  **无一条**规定编排任务在 HTTP 面的暴露与 Web 呈现 ⇒ 本 change **规格先行**（**ADDED**，新能力，先例
  change `0028`；**非** `skip_specs`）。
- **决策①：只补 HTTP 暴露，**不碰**转发层。** 新增 `POST /task`（SSE），复用 `UIAPILayer.run_task`
  ——与 `/run` 同型：异步生成器 ⇒ 会话校验 / 编排器缺失在**首帧**才抛，故在 `stream()` 内捕 `UiError`
  转**错误帧**（`UI_SESSION_NOT_FOUND` / `UI_ORCHESTRATOR_UNSET`），不裸抛、不静默成功。注册在
  `StaticFiles` 挂载**之前**（与既有 11 端点同序 ⇒ 不被静态兜底吞掉）。端点计数 **11 → 12**。
- **决策②：任务区与会话列表**并列不混池**。** SPA 右栏在会话列表**之上**新增 `TaskPanel` 区块，二者
  **同列而各自独立**（`App.svelte` 用 `.rail` 容器承载两个块，`SessionList` 零改动）。判据：任务是**在途**
  运行态、会话是**持久**记录，**生命周期不同**——混池会把「运行中的任务」误当「可切换的会话」。
  **排布取「同列独立区块」义**，**不取**「替换/覆盖会话列表」义（后者会让在途任务挤掉会话导航，与「不混池」
  所防的问题同型）。子任务行 = 标题（`subtask_started.goal`）+ 状态徽标（待执行 / 运行中 / 完成 / 失败）
  + `<details>` 可展开详情（里程碑行由 `subtask_progress` 的 `event`/`data` 转写、验收标准、完成 / 失败理由）
  —— **全部取自既有事件载荷，不建第二数据源**。
- **决策③：收尾回落，且**不**建子 agent 会话切换。** 任务收尾（`task_finished` / `task_failed`）⇒ 该任务
  **移出在途列表**（任务区回落至空态）并以**一次性提示**呈现终态，**不**进入会话列表（任务不产生会话）。
  **「进入子 agent 会话 / 主-子焦点切换」不实现**：子 Agent 消息流**无数据源**（转录只注入主 loop，
  change `0115` 明文；`ctx.messages` 不跨回合），硬做必须**先裁决**与 `0115` 边界的冲突（phase-29 §7 红线②）。
  故本 change 的「详情」**只**指既有事件载荷内可见的字段。**范围订正**：phase-29 §3.3 草记 Web 侧含
  「主/子切换」，按此收窄（§4 裁决点③已认可只对 CLI 收窄、对 Web 只定「复用右栏位置、不混池」）。
- **已知局限**：① **前端无 JS 测试基建** ⇒ 「并列不混池 / 标题·状态·详情 / 收尾回落」三条**无自动化回归**，
  以 `npm run build` + 手工冒烟验收（端点面**有** pytest 回归）；② 任务区**不持久**：刷新页面即丢失在途任务
  （任务在途态只在事件流上，无落盘；要持久须先裁决任务态归属，登记后续）；③ 任务区**单任务串行**（`busy`
  期间启动按钮禁用），与 CLI `/task`「不可并发放任务」同口径，但**无**服务端并发守门（多客户端可并发派发）；
  ④ 子任务详情**只显示事件载荷已有字段** ⇒ 子 Agent 的模型原文与逐轮动作**不可见**（有意：`reply_delta`
  不外发，见 ADR-0114）。
- **规格**：`ui`（**ADDED**「任务编排的 HTTP 面与 Web 任务区」+ 6 Scenario：「HTTP 派发任务并流式呈现进度」
  「未登记会话标识被拒绝」「编排器未注入时报结构化错误」「任务区与会话列表并列不混池」「子任务标题与状态
  可见、详情可展开」「任务收尾后回落」）。**非** `skip_specs`。

---

## ADR-0116：难易度感知的同波次调度策略（change 0123 / phase-29 change C：E50）

- **背景**：`coding-plan/phase-29.md` 的缺口 **E50**（§0.6 判据「`Subtask` 无 difficulty 字段 + 波次划分只看
  依赖」）。引入前 `Subtask` 字段仅 `id/goal/acceptance/depends_on/priority`，`_build_waves` 的波次**纯依赖
  拓扑**（`level[sid] = 1 + max(依赖层号)`），同波次无依赖子任务一律按 `max_concurrency` 并发扇出 ⇒
  「依据任务难易度动态决策串行 or 并发」（用户需求①）**无载体也无决策点**。契约面：`orchestration` spec
  只规定「并行扇出」，**无**难易度与策略条款 ⇒ 本 change **规格先行**（`orchestration` **ADDED**「难易度
  感知的调度策略」= 新能力，先例 change `0028`；`configuration` ADDED「编排调度配置」；**非** `skip_specs`）。
- **决策①：缺省沿用拓扑并发（用户裁决，2026-10-06）。** phase-29 §4 裁决①/§7① 原写「缺省 = **全串行**」
  （理由是难度为模型自报弱信号、`max_concurrency` 未接线 ⇒ 不得把不可靠信号直连并发开关）——该缺省与
  spec「并行扇出」条款及既有并发用例（`test_run_fanout_bounded_concurrency` 等）**字面冲突**，属**能力回归**，
  故提请裁决。用户选 **「缺省沿用拓扑并发」**：策略 `off`（缺省）时同波次并发**逐字不变**（上限
  `max_concurrency`），仅 `difficulty` 策略**收窄**。§4① 的**用意保留**（弱信号不得**强制**降级并发），
  但其**字面**（缺省即串行）**订正**；既有「并行扇出」条款与并发用例**一律不动**。
- **决策②：粒度 = 波次，不是子任务。** 含 `hard` 的波次**整体**串行（按优先级降序逐个），而非「hard 子任务
  单独串行、同波次 easy 仍并发」——后者会让同波次部分并发部分串行，**无拓扑依据**且并发峰值不可判定。
  判据取自 phase-29 §0.5.3 的**三判据先行**（依赖拓扑硬约束 → 难易度 → 并发上限保护）；「模型自主判依赖」
  延后（§4 裁决②）。
- **决策③：依赖拓扑仍是硬约束。** 策略只改 `_fan_out` 的 `Semaphore` 上限（`_wave_limit`），**SHALL NOT**
  触碰 `_build_waves` 的波次划分 ⇒ 有依赖的子任务**必**分属不同波次，DAG 与断点续跑语义零回归。
- **决策④：难易度**归一**、配置键**校验**——口径有意不同。** 难易度是模型在拆解 JSON 里**自报**的弱信号，
  其非法值（`"urgent"` / `1` / `null`）**归一**为 `medium` 而非剔除子任务：对齐 `_parse` 既有口径
  （非法项剔除 / priority 非整数取 0），且**剔除会放大**成整次拆解失败，代价不对等。归一含**去空白 + 小写**
  （`"HARD"` ⇒ `hard`）——字面不等即降级为 `medium` 会**静默削弱**信号，比归一更差。反之
  `orchestration.difficulty_policy` / `max_concurrency` 是**人类配置**，写错必须**校验期阻断启动**
  （不静默退化成缺省）。两处口径不同是**有意**，写入规格与注释。
- **决策⑤：`max_concurrency` 由组合根注入（不接线即空转）。** `TaskScheduler` 构造缺省 `4` 恰与既有行为
  **同值** ⇒ 不接线也**不暴露**（上限判据空转，与账本 E15「可注入但唯一调用点不传参」同型）。故
  `runtime.py` 装配时**显式**传 `max_concurrency=config.orchestration_max_concurrency()` 与
  `difficulty_policy=config.orchestration_difficulty_policy()`，并以用例钉死**接线**（断言
  `runtime.orchestrator._max_concurrency` 等于**配置值**，非构造缺省）。
- **已知局限**：① 策略**只收窄不放大** ⇒ 无法「强制并发」；② 波次级粒度 ⇒ 同波次一个 `hard` 会拖慢其余
  子任务（保守取舍，代价上界 = 波次内子任务数）；③ 难易度是**模型自报**信号、**无校准**（弱信号，不可
  确定性验证 ⇒ 用例打桩 planner）；④ 策略**不改**验收 / 重试语义（`hard` 无额外重试）；⑤ 策略**不做**
  CLI / Web 可视化（仅配置面可见；消费面见 ADR-0114/0115）；⑥ §0.5.3 的「模型自主判依赖」与 phase-29
  gap①（主 loop 丢弃多余 call，登记为 **E55**）**不在本 change**。
- **规格**：`orchestration`（**ADDED**「难易度感知的调度策略」+ 7 Scenario：「缺省策略维持既有并发」
  「难易度策略下含 hard 的波次串行」「难易度策略下无 hard 的波次并发」「难易度缺省与非法值归一」
  「难易度大小写与空白归一」「难易度随计划持久化往返」「并发上限与策略由配置注入」；**MODIFIED**
  「子任务拆解」——仅订正 `LLM 拆解产出子任务 DAG` 场景的字段枚举（+`difficulty`），Requirement 正文
  **逐字保留**）+ `configuration`（**ADDED**「编排调度配置」+ 3 Scenario：「编排键经 ConfigSpec 声明」
  「缺省取内置默认值」「非法取值校验期拒绝」）。**非** `skip_specs`。

---

## ADR-0117：TUI 子任务运行态与里程碑详情（change 0124 / phase-29 change D：E52）

- **背景**：`coding-plan/phase-29.md` 的缺口 **E52**（用户需求②「串行/并行都需 CLI + web/app **动态显示子
  agent 主题 + 运行状态**」的 CLI 半；§0.6 判据「`ui/repl.py:604` 只读折叠块、无会话切换」）。**一手复核**
  （2026-10-06）把缺口**收窄**为一点：`repl.py:_add_task_widget` 的分支只到 `subtask_completed`，**无**
  `subtask_progress` 分支（无 `else` 兜底）⇒ 里程碑事件到达即被**静默丢弃**；另一面是 `_open_subtask`
  的标题在收尾前**无运行态标记**（「在跑」只能靠「还没出现 ✓/✗」推断）。**数据面早已就绪**：编排层
  `_emit_progress`（change `0121`）已按白名单外发 `subtask_progress`，`api.run_task` 已加 `task.` 前缀
  透传，Web 侧 `TaskPanel.svelte`（change `0122`）已在消费同一载荷 ⇒ 缺的**只是 TUI 消费面**。
  §3.3 已把本 change **收窄**为「只读详情 + 实时状态」，「进入子 agent 会话 / 回到主 Agent」明文**不在**
  本 change（§7 红线②：子 agent 消息流**无数据源**——转录只注入主 loop，change `0115`）。
- **决策①：消费面接线，不新建旁路、不新建数据源。** 里程碑**只**从既有 `task.subtask_progress` 载荷取，
  与 Web 侧同一事件面（SHALL NOT 另造事件面）——沿 change `0121` / `0122` 口径。
- **决策②：里程碑文本复用既有动作行口径（`format_action_event`），不新写一套。** 工具类里程碑显示
  **友好名 + 耗时**（`tools.code_run` ⇒ `Bash`），与主 loop 的动作行**同一呈现口径**；其实现只取
  `tool_id / ok / duration_ms`，**从不**输出 `args` / `output` ⇒ 天然满足「用户可见层不暴露内部 id 与
  原始参数」（既有红线，`_TOOL_NAMES` 注释与 `test_tui_action_widget_lifecycle` 同口径）。轮次级里程碑
  （`step_completed`，动作行不覆盖）落「第 N 轮完成 / 失败」。
- **决策③：只追加到**既有**折叠块；无对应块 ⇒ 静默忽略。** 里程碑先于 `subtask_started` 到达（或子任务
  标识未知）时**不新建块**、不抛裸异常、不影响其它子任务 —— 对齐 `_complete_subtask` 既有的 `entry is None`
  早退口径。白名单**表外**类型**不落空行与占位**（不谎报里程碑）。
- **决策④：TUI 不预生成「待执行」条目（与 Web 的**有意**差异）。** Web 任务区是**清单式面板**（`plan_ready`
  即按 `subtasks` 铺出全部条目，含 `pending`）；TUI 时间线是**对话流**（按事件发生次序追加）⇒ 预生成 N 条
  空折叠块会把时间线变成半个面板。故 TUI 的子任务条目仍在 `subtask_started` 时创建，运行态由**标题徽标**
  承载（`⟳` 运行中 ⇒ `✓/✗` 收尾 ⇒ 「已完成（续跑跳过）」）。
- **决策⑤：不触 `format_task_event` ⇒ 非交互 CLI 输出逐字不变。** 该函数是 `core-agent task`
  （`entry.py:_stream_task`）与 TUI **共用**的单行格式化器；把里程碑塞进去会**扩大**非交互入口的输出粒度
  （今天每事件一行、无里程碑行）。本 change 的呈现只落 **TUI 折叠块**，非交互 CLI 口径**不动**。
- **判据订正（相对 phase-29 §6 表 D 行，2 条）**：① 「可验证性：**低**（Textual 无测试基建）」**不成立**
  —— 本仓**已有** headless Textual 基建（`app.run_test()` + `pilot.press` 驱动输入、`_timeline_text` 取
  时间线全量文本、断 `Collapsible.Contents.display` 折叠态），`test_task_subtask_collapsible_lifecycle` /
  `test_tui_action_widget_lifecycle` / `test_task_command_busy_rejects_concurrent` 即其现成用例；本 change
  的 4 条验收**全部**由同类用例钉死 ⇒ 实为**高**。② 「依赖 A 的呈现面」表述偏松：A 交付的是**数据面**、
  本 change 是**消费面**，且 B 已在 **Web** 侧完成等价消费（`milestone(ev)`）⇒ 本 change 的呈现口径可
  **直接对照 Web 实现**，无需新造判据。
- **已知局限**：① **不做**「进入子 agent 会话 / 主-子焦点切换」（无数据源，§3.3 登记后续）；② TUI 不预生成
  待执行条目（决策④）⇒ 未开工的子任务**不出现**在时间线（与 Web 面板不同）；③ 折叠块**默认收起**，里程碑
  须手动展开 ⇒ 需求②的「**动态显示**」在 TUI 是「按事件实时追加、按需展开」，与 Web 面板「常显」不同；
  ④ 详情文本**无截断上限**（有界于白名单粒度：每轮至多 3 类事件）；⑤ 非交互 `core-agent task` 入口
  **不呈现**里程碑（决策⑤，有意）。
- **规格**：`ui`（**ADDED**「TUI 子任务运行态与详情」+ 4 Scenario：「子任务运行中可见状态徽标」
  「里程碑事件展开可见」「表外事件不呈现」「里程碑先于折叠块到达时静默忽略」）。**非** `skip_specs`。

## ADR-0118：TUI 子 Agent 焦点视图（change 0125 / phase-33 切片 B：E61）

- **背景**：`coding-plan/phase-33.md` 立账的 **E61**（用户原始需求①「**进入子 agent 查看状态，查看完成
  也可以选择回到主 Agent**」）。phase-29 四 change 已交付「**只读详情**」（`0122` Web 任务区 / `0124` TUI
  折叠块里程碑），但「**主/子来回切换**」被明文列为 non-goal（`0124` proposal §Non-goals）⇒ 落差是
  **「焦点」本身**：单子任务过滤视图 + 进入 / 返回导航。**一手复核**（2026-10-06）：`compose()` 只有单一
  内容区 `#timeline`（无「另一视图」可切）；子任务标题/状态/详情**均已在主时间线折叠块内**（`_open`），
  缺的只是「单独看它」的通道。2026-10-06 用户裁决：**形态 = 焦点视图（presentation-only）**、
  **交互范围 = CLI 内嵌面板 + main/subagent 来回**、**切换方式 = 命令 + F2**、**Web 沿用 `TaskPanel`**。
- **决策①：焦点视图 = presentation-only 消费面接线，不新建数据源。** 面板**正文**直接读焦点折叠块详情
  的**已渲染文本**（`str(detail.render())`）、标题读折叠块 `box.title` ⇒ 与主时间线**同一份**呈现物，
  零新增事件、零新增载荷、零子 Agent 消息流（**不触** change `0115`「转录只注入主 loop」边界，phase-29
  §7 红线②）。成功切换**零时间线写入**（呈现层切换不改内容）⇒「返回后主时间线逐字不变」是可断言的硬性质。
- **决策②：视图切换只改 `display`，绝不 unmount 时间线。** `_add`（`repl.py:358`）与尾段热更新
  `_touch_tail` / `_freeze_tail` **无条件** `query_one("#timeline")` ⇒ 一旦 `remove()` 掉时间线，流式/
  里程碑/终态落地的路径会集体崩溃。故 `#panel` 与 `#timeline` **互斥 `display`**（两者都在 DOM 中）。
  初始隐藏**命令式**置于 `on_mount`（与既有 `#spinner` 同法）—— Textual 的 `display` setter 有
  「遗忘原始值」的 TODO，用 CSS `display: none` 会在切回时丢失意图。
- **决策③：焦点**绑定 widget 身份**，不绑定 sid 字符串。** `self._open` **跨任务从不清空**，而子任务
  标识（`"1"` / `"s1"`）**逐任务复用** ⇒ 若以 sid 判「当前焦点是否即该详情」，会把**上一任务**同 sid 的
  陈旧条目误认作当前焦点。故存 `_focus_box` / `_focus_detail` **对象引用**，刷新守卫一律用 `is` 比对
  （`_progress_subtask` 末尾 + `_complete_subtask` **两个出口**：skipped 早退与正常收尾）。
- **决策④：`task_started` 与审批挂起**强制**回主视图。** 计划头（`◍ 任务 …`）与审批提示（`⚠ 需审批`）
  都**写进时间线**；若此刻时间线被隐藏，提示不可见 ⇒ **视觉死锁**（尤其审批为模态：不响应就永不收尾）。
  故 `_ask_approval` 首行与 `_add_task_widget` 的 `task_started` 分支各置 `_set_focus("")`。
- **决策⑤：焦点命令**先于**忙态拒绝拦截（运行中可用）；成功零时间线写入。** `_handle_focus_command`
  在 `on_input_submitted` 中位于忙态检查**之前**（裁决明确「任务运行中亦可用」——而 `/task` 正是长时间
  忙态的唯一来源，若排在忙态之后则该功能在最需要时不可用）。失败的提示（用法 / 未找到）仍落时间线；
  普通（非焦点）输入在忙态**之后**回主视图（忙态拒绝不改变视图状态）。
- **决策⑥：Web 不做焦点视图（**有意**不对称）。** 用户裁决「Web 沿用 phase-29 已落地的 `TaskPanel`」：
  Web 侧是**面板式**布局（右栏任务区逐子任务呈现标题 + 状态 + `<details>` 可展开详情，且可与会话列表
  并列查看），其「进入子任务」的信息收益低于终端（终端时间线是**单列对话流**，聚焦才能独占视野）。故
  本 change **零 Web 改动**、零编排层改动、零事件面改动，`format_task_event`（非交互 `core-agent task`
  共用）**逐字不动** —— 非交互 CLI 输出不变。
- **判据订正（相对 phase-33 §1 原稿，2 条）**：① 原 (b)「只读详情 + 状态（复用 `subtask_progress` 载荷）」
  与已落地件（`0124` 折叠块里程碑 / `0122` Web 任务区）**逐字同义** ⇒ 照做即 **0 增量**（以「复用既有
  载荷」之名**重复登记**＝谎报进度）；**重定义**后的真增量是**「焦点」本身**（单子任务过滤 + 进入/返回
  导航）。② 焦点须**绑定 widget 身份**而非 sid（决策③）—— 该陷阱在原稿中未被识别。
- **已知局限**：① 聚焦的子任务**收尾后仍留在焦点视图**（标题转 `✓/✗`、正文补 `判定：`），而**任务级**
  `✔ 任务完成（…）` 行不在面板内 ⇒ 须 `F2` 回主视图可见（面板标题常驻「/main 或 F2 返回主视图」提示）；
  ② 焦点是**即时快照**：`/focus 1` 若早于 `subtask_started 1` 到达 ⇒ 按未知拒绝（**无**「延迟聚焦」半开态，
  避免半开状态机）；③ `Ctrl+B` 打断提示在聚焦时写进被隐藏的时间线（纯视觉，不影响打断语义）；
  ④ 审批挂起时焦点命令被审批分支先行拦截（**模态语义，正确**）—— 由决策④的强制回主视图兜底。
- **规格**：`ui`（**ADDED**「TUI 子 Agent 焦点视图」+ **6** Scenario：「聚焦显示子任务框且主时间线不可见」
  「返回主视图后主时间线内容逐字不变」「聚焦期间随里程碑与收尾实时刷新」「未知子任务标识不切换视图」
  「焦点命令在任务运行中可用」「焦点面板不泄露内部标识与原始参数」）。**非** `skip_specs`（新需求块，
  先例 change `0028` / `0124`；`0124` 的「主-子焦点切换 SHALL NOT **在本 Requirement 内**」逐字保留 ——
  本条是**另立**的后续需求）。

---

## ADR-0119：子任务失败态传播（假成功收口）（change 0126 / phase-34 E63）

- **背景**：`coding-plan/phase-34.md`（全系统架构走查缺陷账本）标记的**最高危真缺陷 E63**。编排器
  `scheduler.py:_run_subtask` 只认**验收门**结论（`verify.passed`），**丢弃**子 Agent 循环的失败态
  （`result.failed`）—— 而 `LoopResult.failed` 语义即「目标未达成 / 异常终止 / 预算耗尽」（`loop/
  protocol.py:24`）。无验收标准时验收门退化为「回复非空即通过」⇒ **执行失败 + 非空合成回复 = 假成功**，
  失败的子任务被登记为完成并推进后继波次。**对照正解**：`delegate` 路径（`runtime.py:797`）早已是
  `{"ok": not result.failed, "reply": ...}` —— 编排路径**漏了同一条**（同一失败信号，一处消费一处丢弃）。
- **决策①：执行失败态并入验收门判据（fail-closed），`ok = verify.passed and not result.failed`。**
  验收门本义（LLM 对照 / 离线非空降级 / 判定器不可用 fail-closed）**逐字不变**；本 change 只是给它加
  一条**前置收窄**：执行单元返回失败态时，无论验收门是否本会通过，一律判**不通过**。判据合并为单行
  真值，`subtask_completed.ok` 与 fan-in 推进共用同一真值，**单一判据、无旁路**。
- **决策②：新增结构化错误码 `SUBTASK_EXECUTION_FAILED`，**不**复用 `SUBTASK_VERIFY_FAILED`。**
  假成功的**根因**是「执行失败被误读为验收通过」；若失败码仍叫「校验失败」，日志 / trace 会把
  「循环未达成」读成「验收标准未达」，**掩盖真因**。新增为**纯追加**枚举成员：波级 `task_failed` 收口
  仍按既有 `SUBTASK_VERIFY_FAILED` 汇总失败子任务列表（与「哪一条执行失败」正交）；`subtask_completed`
  载荷形状**零变更**（`ok` 仍 `bool`）。
- **决策③：失败理由不互相覆盖。** 验收本就失败 ⇒ 保留 `verify.reason`（真因是验收）；仅「验收本会过
  但执行失败」⇒ 理由记为「子任务执行未达成目标」。两条失败因由正交，不掩盖。
- **已知局限**：① 编排**不做重试**——本 change 只把失败**如实暴露**为 `RECOVERING` 收口 + `task_failed`，
  有限次重试 / 重规划仍属「子任务校验通过才推进」既有 Scenario 的**未落地**部分（另账，不在本 change）；
  ② 目标循环若**既失败又回复为空**，失败码取 `SUBTASK_VERIFY_FAILED`（验收先失败）—— 两条因由同真时
  以验收码呈现，语义等价（均为不推进）。
- **规格**：`orchestration`（**MODIFIED**「子任务验收门」——补「执行失败态 fail-closed」+「失败态传播
  `ok = 验收通过 且 执行未失败`」口径 + **1** Scenario「执行失败态不因非空合成回复通过」）。**非**
  `skip_specs`（规格此前**空白**，非违约口径）。

---

## ADR-0120：落地只认门禁全过的制品（fail-closed 收口）（change 0127 / phase-34 E69）

- **背景**：`coding-plan/phase-34.md` 登记的 **E69**（低危、**fail-open 潜伏**）。`EvolutionExecutor.
  commit` **从不读 `record.gated`** —— 全仓 `gated` **只有写**（`executor.py:171` 筹备产物 / `:205`
  落地产物）**无读**。两个「待复核」访问器（`executor.staged:215-218`、`pending.staged`）的谓词**只有
  `not committed`**，尽管 `models.py:79-80` 与 `pending.staged` 的 docstring 都写着「`gated` 标记『门禁
  全过、可复核』—— `commit` **只认**前者为真者」「待复核制品（**门禁已过**、尚未落地）」。**可达窗口**：
  门禁执行**抛异常**（或进程在门禁跑动中被杀）⇒ `_run_gates` 的 `finally` 已回退工作树，但
  `clear_implementation`（只在「门禁返回失败」分支调用）**不跑**，而制品早在 `:152` 就 `attach_
  implementation` + `flush` 落盘 ⇒ 台账留下一条 `gated=False` 残留；此时工作树与 `record.before`
  **一致**（已回退）⇒ 重启后**漂移校验通过**、复核单可正常签发 ⇒ **从未跑过门禁的补丁被永久应用**。
- **决策①：判据只加在**读取面**（两个「待复核」访问器），不在 `commit` 里另立分支。** `gated` 的语义
  已由模型 docstring 与 `pending.staged` docstring 定义为「待复核」的**构成要件**（缺它就不是待复核）
  ⇒ 把判据收在访问器即**单点**生效：`commit`（落地面）与 `evolve pending`（呈现面）**同时**正确，
  不产生「同一制品在 A 面可复核、B 面不可复核」的双口径。`commit` 因此无须新增分支 —— 未过门时
  `staged()` 返 `None`，落的正是既有的「没有待复核制品，先 `--dry-run`」拒绝路径。
- **决策②：拒绝理由沿用既有 `IMPLEMENT_REJECTED`，不新增错误码。** 失败因由是「没有可复核的制品」，
  与「未筹备直接落地」是**同一件事**（`staged` 为 `None`），操作面提示（先筹备）也正是本窗口的正解；
  新增码只会让同一处置路径分叉出两个名字。**不**改 `IMPLEMENT_STALE`（漂移是另一条判据，两者正交）。
- **决策③：不静默丢弃残留制品。** `gated=False` 的记录**仍留在台账**（`implementation_of` 可见），
  本 change 只让它**不可复核 / 不可落地**——留痕优于抹掉（抹掉会让「筹备中断过」这一事实消失）。
  **不**顺手给 `_run_gates` 的异常路径补 `clear_implementation`（见已知局限①）。
- **已知局限**：① 门禁中断后**没有**「自动清账」——残留制品要等**下一次筹备**被 `_reject_drifted_
  worktree` 作废（工作树与 `before` 一致 ⇒ 走 `clear_implementation` 重新筹备）；本 change 只保证它
  **不构成放行路径**，不负责回收。② `records`/`implementation` 的**跨进程**重读取决于台账落盘（既有
  能力，本 change 未改）。③ 呈现面过滤会让「台账有记录、`evolve pending` 不列」在**异常残留**时出现
  —— 这正是规格要求（未过门 = 非待复核），落地报错信息已指向重新筹备。
- **规格**：`evolution`（**MODIFIED**「架构级候选的原生实施（可选）」——「复核」bullet 补「**待复核**
  仅指门禁全过的制品」，「落地」bullet 补「SHALL 只认门禁全过的制品 / 未过门 ⇒ `IMPLEMENT_REJECTED`
  / SHALL NOT fail-open」+ **1** Scenario「未过门的残留制品不被放行落地」）。**非** `skip_specs`
  （规格此前未写这条判据，非违约口径）。

---

## ADR-0121：可逆效应账的清账与幂等（change 0128 / phase-34 E67）

- **背景**：`coding-plan/phase-34.md` 登记的 **E67**（中危）。`plugin_registry/effect_tracker.py:61-78`
  的 `rollback` **只撤不清**：撤销成功后既不移除 `_effects[id]`、也不清 `_by_trace[trace]`，且**无
  `clear` 方法**。后果二：① 对同一 `trace_id` **再滚一次**，快照仍含全部 `EffectId` ⇒ **undo 被二次
  调用**（P2「可逆」退化为**非幂等**）；② `_effects` 只增不减，`runtime.py:343` 的**全进程单例** tracker
  内存**无界增长**。可达面：`fault_tolerance.py:138` `Rollback.on_failure`、`loop/default.py:284` 与
  `:523`、`durability/manager.py:148` 均按 trace 回滚 —— 任何「同一 trace 被回滚两次」的路径（重试 /
  恢复 / 中断后收尾）都会走到。规格面：`grep -rn EffectTracker doc/openspec/specs/` **仅** `evolution`
  间接提及，该能力**无 canonical 归属** ⇒ 补 **ADDED Requirement**（**非** `skip_specs`）。
- **决策①：清账放在 `rollback` 内部（隐式），另给 `clear`（显式）。** 回滚的语义就是「这一轮到此结束」：
  账目留着既无待撤销项、又让幂等失效 ⇒ 撤销成功即出账；而 `clear(trace_id=None)` 覆盖「只想**丢弃**
  账目、**不执行**撤销」的场景（调用方已另行恢复现场），两者职责不同、不可互相替代。
- **决策②：撤销失败者留账隔离，且其 trace 键不因清账而删。** 失败项须继续可见于 `audit`（留痕优于
  抹掉）、并由 `undo_failed` 报告；trace 映射只在**已无未了结项**时删键（避免空键残留）。
- **决策③：不可逆效应随清账一并出账（不永久留账）。** 它从未被撤销、也无失败可隔离；若留下，
  「账目 SHALL NOT 无界增长」会在**最易触发**的路径（每次 `code_run` 记一条不可逆效应）上失效。
- **已知局限**：① **未回滚**过的 trace 仍按原设计留账（账目随 trace 数增长）—— 本 change 只保证
  「已回滚的 trace 彻底出账」，不做 TTL / 上限淘汰。② 已出账的 `EffectId` 再 `replay` 抛 `KeyError`
  （与「未知 id」同型，不另立错误码）。③ undo 闭包仍在**不持锁**处调用（保留既有「撤销闭包可重入
  tracker」的设计），故并发同 trace 双回滚不在本 change 的保证范围内（顺序重复回滚已幂等）。
- **规格**：`plugin-registry`（**ADDED**「可逆效应追踪（清账与幂等）」—— 账 / 回滚 / 清账三件套的 SHALL
  口径 + **4** Scenario：出账与幂等 / 账清空且 trace 隔离 / 失败留账隔离 / 显式清账不触发 undo）。

---

## ADR-0122：写类工具按次快照，撤销闭包自带身份（change 0129 / phase-34 E64）

- **背景**：`coding-plan/phase-34.md` 登记的 **E64**（**高**）。`tools/builtin.py:105-118`（write）与
  `:136-147`（patch）在**闭包外**声明 `snap: dict`，每次调用**覆写同一份**；`undo()` 读同一共享
  `snap` ⇒ 两次调用记录的两条 Effect **共用同一个 undo 闭包对象**，逆序撤销两次都在还原**最后一次**
  的快照。而 `runtime.py:397` 五个内置工具**只构造一次、跨 loop 复用** ⇒ 同一会话两次写不同文件即
  **恢复错文件**（P2 崩于最常用工具）。跨 trace 更糟：`t1` 写 A、`t2` 写 B 后只回滚 `t1`，会去还原
  **B**（触及本不该动的 trace）。规格 `tool-use/spec.md`「时间旅行回滚」已 SHALL「沿历史逆序执行各
  写类工具的撤销函数，**状态恢复到检查点**」—— 现状**违反**该 Scenario。
- **决策①：撤销闭包**自带身份**（每次调用生成一份绑定自身快照的闭包），而非「每次压栈、undo 弹栈顶」。**
  三条路可选：① 共享栈 + 弹栈顶 —— **跨 trace 仍错**（栈顶未必是本 trace 那次）；② 让 `EffectTracker`
  按 trace 分组调用 —— 但 `undo()` **无参**、闭包无法自辨身份；③ **每次调用生成闭包**（取此）。差别在
  「谁持有身份」：让闭包**自带**（捕获自己的快照）比让调用方**推断**更稳，且不需要 `EffectTracker` 的
  任何接口变更。
- **决策②：`Tool.undo` 由闭包改为「工厂」。** 固定闭包读**共享状态**是根因；要「按次」就必须让调用方
  **每次取一个** ⇒ `Callable[[], Callable[[], None]]`（空栈时返回 no-op 闭包）。`EffectTracker`
  （change `0128` 的清账/幂等语义）与 `_restore`（`:282-292`）**逐字不动**。
- **已知局限**：① 快照仍在**进程内**（跨进程时间旅行由 `durability` 的检查点承担，本 change 不扩）。
  ② 并发**同一**工具实例的调用不在保证范围：`file_write` / `file_patch` 的 handler 为**同步**，
  `provider._call` 与其后的取闭包之间无 await（`:164-168`）⇒ 「压栈 → 取闭包」在同一事件循环步内完成，
  不存在交错窗口；若将来有 await 型写工具，须重新评估。③ 撤销闭包若未被取用（handler 成功但调用方
  未记录），该快照留栈至下次取用——由「写入**成功后**才压栈 + 取闭包紧随返回」将其窗口压到最小。
- **规格**：`tool-use`（**MODIFIED**「撤销与时间旅行回滚」—— 正文补「撤销函数 SHALL 按次生成 / 同一
  工具实例跨调用 SHALL 各持独立快照 / 撤销第 N 次 SHALL 恢复该次内容」+ **2** Scenario「同一工具多次
  写入各自独立回滚」「跨 trace 不串」）。**非** `skip_specs`（按次快照这一构成要件此前未写）。

---

## ADR-0123：配置写回记可逆效应，同 trace 回退内存与磁盘（change 0130 / phase-34 E68）

- **背景**：`coding-plan/phase-34.md` 登记的 **E68**（中高）。`manager.apply_change`（`:529-550`）把内存配置
  变更记为可逆效应（`op="config_apply"`，`trace_id="config"`），但**落盘**的 `write_patch`（`:555-569`）
  `tmp.write_text` + `os.replace` **完全不记账**。配置变更实际作用于**两处状态**（内存 `AppConfig` +
  `config.yaml` 文件），可逆账只覆盖其一 ⇒ 按 `trace_id="config"` 回滚**只回退内存**，磁盘留新值，下次
  `load()` 把已回滚的变更**复活**。违反 P2（一切副作用可逆）。注意**不是**「原子写没做」——`0099` 已用
  tmp + `os.replace` 保证不留半写；缺的是**写回这件事本身没有撤销记录**。
- **决策①：`write_patch` 在 `os.replace` 之前记一条 `Effect(op="config_write_patch", trace_id="config")`，
  undo 恢复写盘前的 yaml 原文字节。** 与 `apply_change` **同 trace** ⇒ 一次 `rollback("config")` 同时回退
  内存与磁盘。记账在替换**之前**：`os.replace` 原子，若它抛出则 yaml 仍是旧值，undo 写回旧值即幂等。
- **决策②：undo 恢复**原文字节**，不重新 dump。** 重 dump 会改写文件格式，并可能把 env/cli 覆盖层写进
  yaml（`write_patch` docstring 早已写明「只合并用户 patch，不落 env/cli 覆盖与明文密钥」）。原文字节是
  **唯一的精确逆**。
- **已知局限**：① **本 change 不新增配置回滚的生产入口**（`EffectTracker.rollback("config")` 今日无调用方
  —— `entry._config_set:560-563` 与 `ui/api.py:288-305` 的「回滚」都是**重读 yaml** 而非滚账）。本 change
  只补齐**可逆契约**，无回滚入口 ⇒ **行为零变化**，账目先于消费者就位（同 change `0128` 的 `clear()`）。
  ② 写盘前文件**必存在**（`_read_yaml` 守门），故 `_restore_yaml(None)`（删除文件）为**对称兜底**、当日
  不可达。③ 只覆盖 `write_patch` 一处写盘点；若将来出现其他直接改 yaml 的路径须另行登记。
- **规格**：`configuration`（**MODIFIED**「配置校验与生效」—— 正文补「写回 yaml 的变更 SHALL 记录可逆效应，
  undo 恢复写盘前原文，SHALL 使磁盘态与内存态一并回退」+ **1** Scenario「写回可逆：回滚恢复磁盘原文」）。
  **非** `skip_specs`。

---

## ADR-0124：压实按会话收窄，记忆分档口径改两档（change 0131 / phase-34 E66 + E78）

- **背景**：两条账一并收口。**E66**（高）：Web「压缩本会话记忆」实际压**全库**。`ui/api.py:211-220` 的
  `compact(session_id)` 把 `session_id` **按位置**传给 `MemoryStore.compact(query="", budget=4096, ...)`
  ⇒ 该字符串落进 **`query`** 形参（只影响排序相关性），而聚合范围**始终全量**（`_summarize_sessions()`
  遍历 `_episodic_groups()` 的全部会话）⇒ 用户点「压缩本会话」，系统顺手**提炼并归档他会话条目**，
  跨会话记忆泄露/破坏，违反会话隔离。**E78**（低，规格漂移）：`memory/spec.md`「温度分层检索」写
  **热/温/冷三档**，实现与全部文档只有**热/冷两档**（`core/memory/__init__.py:3` 自述「热/冷」）——
  温层从无语义定义、无任何代码路径。
- **决策①：`MemoryStore.compact` 增**仅关键字**形参 `session_id: str = ""`，语义为**聚合范围收窄**，
  与 `query` 语义无关。** 非空 ⇒ `_summarize_sessions(session_id)` → `_episodic_groups(session_id)`
  只收该会话条目（重要度打分写回随之只覆盖该会话）；空串 ⇒ **全量**（逐字与既有行为一致）。选
  **可选关键字形参**而非新增方法：调用点二处各取所需 —— `ui/api.py` 传会话（收窄），
  `loop/default.py:412` 的节拍压实 `memory.compact()` 不传（保持全量节拍语义）。
- **决策②：`ui/api.py.compact` 改传 `session_id=session_id`**（不再按位置传）。修的是**传参语义**，
  不是 API 形状 —— `compact(session_id)` 对外签名逐字不变，`compact` 的**用户可见行为**由「压全库」
  变为「压本会话」，符合入口名与用户预期。
- **决策③：规格「温度分层检索」**三档删温层、改**热/冷两档**。** 温层无 SHALL 语义承载物（无实现、
  无文档定义、无测试）⇒ 保留它只会制造「规格说三档、代码只两档」的持续漂移。删除即把规格拉回
  与实现同构，属**规格追随事实**的口径校正（非降低要求：删的是**从未被满足且无定义**的条文）。
- **已知局限**：① 收窄只作用于 `_summarize_sessions`/`_episodic_groups` 的**聚合范围**；`compact` 的
  `query`（相关性打分决策）仍走全库 `read` —— 决策分是**咨询性返回值**（不产生写入副作用），今日
  无跨会话副作用，故本 change 不动；若将来决策分参与写入须另行收窄。② `_episodic_groups` 的
  `session_id` 形参**缺省空串**以保「未归属调用者 = 全量」，与 `read(session_id="")` 的既有约定同构。
- **规格**：`memory`（**MODIFIED**「记忆压实」—— `compact` SHALL 接受可选 `session_id`，非空只聚合该
  会话、SHALL NOT 跨会话提炼/迁移，空串保持全量 + **1** Scenario「压实按会话收窄，不触他会话」；
  **MODIFIED**「温度分层检索」—— 三档改**热/冷两档**，删温层条文）。**非** `skip_specs`。

---

## ADR-0125：流式增量以专类型帧推送，与终态分型（change 0132 / phase-34 E65）

- **背景**：`coding-plan/phase-34.md` 登记的 **E65**（中高，用户可见）。`UIAPILayer._map_event` 把
  `reply_delta`（增量）与 `loop_finished`（终态）**都**映射为 `loop.result`，只靠**载荷形状**区分
  （增量 = dict `{text}`，终态 = `LoopResult` 对象）。TUI/CLI 认这个隐式约定（`repl.py:69-79` 判
  「类型 = `loop.result` 且载荷是 dict」；`entry.py:1461-1463` 同判据跳过），**Web 侧没认**：
  `Chat.svelte:44-51` 对每个 `loop.result` 取 `payload.reply ?? message ?? JSON.stringify(payload)`
  并**追加新行** ⇒ 增量帧每帧渲染一段 **JSON 字面量**、终态另起一行，回复被埋在 JSON 垃圾里。
  根因是**一型两形**：靠载荷形状分流，任何新消费者只要不照抄 TUI 判据就会踩坑（Web 即此）。
- **决策①：拆型 —— `reply_delta` ⇒ `loop.delta`（专类型，载荷恒 `{"text": …}`），
  `loop_finished` 仍是 `loop.result`（载荷 `LoopResult`）。** 分流**只看类型**，不再看形状；
  一型一形，消费者的判据从「类型 + 形状」降为「类型」。与既有 `loop.action_started` /
  `loop.action_completed` 的拆型先例同取向（事件类型表示载荷形状）。
- **决策②：同 change 对齐**全部消费方**（一条链不可拆，避免半改状态）**：`repl.py::_event_delta`
  / `_format_event` 改判 `loop.delta`（`loop.result` 的 dict 分支随共型消失 —— 生产上
  `loop.result` 只由 `loop_finished` 产出，载荷必为 `LoopResult`）；`entry.py::_stream` 增量跳过
  判据改判类型（**呈现逐字不变**）；`Chat.svelte` 增量**尾部追加**（首帧新建、其后原地拼接、
  终态帧原位收口），与 TUI `_show_delta` / `_flush_live` 同语义。
- **决策③：规格钉住「增量帧与终态帧 SHALL NOT 共用一个类型」+「前端 SHALL 以文本追加」** ——
  把「一型两形」这个**根因**写进规格，而非只描述「前端别渲染 JSON」（后者是症状）。
- **已知局限**：① 对外 SSE 帧类型是**客户端可见契约**，本 change 是一次**破坏性变更**
  （`loop.result` 不再承载增量）—— 仓内消费方已全部对齐，仓外未知消费者须同步；规格已把口径钉死。
  ② 前端 Svelte 无 JS 测试基建 ⇒ 追加逻辑记 `doc/04-testing/test-cases.md` **手工验收项**
  （Python 侧只覆盖帧类型与载荷形状）。③ 断线重连的**补帧**（重连后重放已丢弃的增量）不在本
  change 范围（既有 Scenario 语义不变）。
- **规格**：`ui`（**MODIFIED**「Web 界面访问」—— 正文补「流式增量 SHALL 以专类型帧推送、
  SHALL 与终态帧区分；前端 SHALL 以文本追加呈现、SHALL NOT 逐帧新建行或序列化 JSON」+ **1**
  Scenario「增量帧以文本追加（非逐帧 JSON）」）。**非** `skip_specs`。

---

## ADR-0126：技能 draft → active 走显式启用路径（change 0133 / phase-34 E72）

- **背景**：`coding-plan/phase-34.md` 登记的 **E72**（中，用户可见）。技能安装链路**只进不出**：
  `skillhub/client.py:66` 下载校验通过后恒置 `status="draft"`，`skills/router.py:98` 候选集只放行
  `active` / `gray`，而全仓**没有** `draft → active` 的迁移路径（`SkillLibrary` 只有
  register / lookup / remove / check_preconditions）。CLI `skill install` 打印「需本地显式激活后
  可用」，却**没有**任何命令能激活 —— 装完的技能永不被路由，是死胡同。规格侧同此痕迹：
  `skillhub/spec.md` 的「下载默认 draft」Scenario 与 `skillhub-interface.md:35` 都写「需显式激活
  后可用」，`SkillHubErrorCode.SKILL_NOT_ACTIVE` 亦指向一扇不存在的门。
- **决策①：启用是 `SkillLibrary` 的一等 API（`activate(skill_id, *, effect_tracker=None)`），
  不新造组件。** 状态迁移与落盘本就是技能库的职责（register / remove 都在此）；放别处会绕开
  `_persist()`，启用跨进程即失效。
- **决策②：幂等 + 未知 id 抛 `KeyError`（不静默创建）。** 已 `active` 再启用以 no-op 返回，不重复
  登记效应；未知 id 沿用 `lookup` / `remove` 的 `KeyError` 口径，**不扩错误码表**（`SKILL_NOT_ACTIVE`
  是审核路径的码，`publisher.py:70` 在用，语义不同，勿混用）。
- **决策③：路由放行集**逐字不变**（仍 `active` / `gray`）。** 本 change 只补**迁移路径**，不扩大
  放行集、不自动启用 —— 否则「显式启用」这一步等于取消（安全默认：外来技能须经本地显式动作方可
  被路由）。SOP 提炼仍走自己的 `status="active"` 直发（维度1 低风险自动发布），不经过本路径。
- **决策④：可逆性走既有接缝（注入 `effect_tracker` 才登记，未注入不记）。** 与 `SopExtractor` 的
  `_track` / `_undo` 同型：效应 `op="skills.activate"`，undo 恢复启用前状态；CLI 侧无追踪器 ⇒
  不登记（零行为变化）。
- **已知局限**：① 启用**只**做 draft→active；`deprecated` 技能被启用会置回 `active`（undo 记录
  原状态故可回滚），「降级后能否复活」的语义未在本 change 收敛（无生产调用方，留待需要时立规）。
  ② 启用**不做**签名/可信度的再校验 —— 校验发生在下载期（`TrustVerifier`），启用作用于**已在本地
  库中**的技能，重启后无从复验（与 register 的既有口径一致）。
- **规格**：`skills`（**ADDED**「技能启用（draft → active）」—— 入口 / 放行集不变 / 幂等 / 未知 id
  拒绝 / 可逆 + **6** Scenario）＋ `skillhub`（**MODIFIED**「签名校验与可信下载」—— 把「需显式
  激活后可用」的悬空指认接到启用路径上，4 Scenario 逐字保留）。**非** `skip_specs`。

---

## ADR-0127：skillhub 源不健康以官方源结果回退（change 0134 / phase-34 E80）

- **背景**：`coding-plan/phase-34.md` 登记的 **E80**（规格漂移）。`skillhub/spec.md`
  「多源路由与健康回退」**一句之内自相矛盾**：正文写「源不健康时**回退官方源**」，紧随的
  Scenario 又写「THEN 标记源不健康并**回退官方源**，返回 `SOURCE_UNHEALTHY`」。实现
  （`index.py:134-140`）与测试（`test_skillhub.py:41`）**都只选后半句** —— 探测失败即
  `raise SOURCE_UNHEALTHY`，**无任何回退动作**（异常文本里的「（回退官方源）」是空头承诺）。
  后果：「多源路由」在生产上退化为**单源**（任一非官方源抖动 ⇒ `skill search --source S` 直接失败）。
- **决策①：拆矛盾句 —— 不健康 ⇒ 回退官方源**并以其结果响应**；回退目标亦不可用 ⇒
  `SOURCE_UNHEALTHY`。** 该口径由用户 2026-10-06 裁决（「回退成功即返回官方源结果」）：回退是
  **降级成功**而不是错误，只有**无可用源**才是错误。`SOURCE_UNHEALTHY` 的语义因此收窄为
  「无可用源」（官方源自身不健康，或回退目标亦不健康）。
- **决策②：回退只发生在**取数面**（`list` / `route`），`health()` 仍如实探测不回退，`download` /
  `locate` 仍不经健康探测。** 三者职责不同：`health` 是**诊断面**（回退会掩盖它要报告的事实）；
  `locate` / `download` 是**查找**（审核方无需知道技能发布到哪个源，`locate` docstring 已立此口径）。
  实现上 `_ensure_healthy` 由「抛错闸门」改为「**返回可用源名**」，`list` / `route` 用该名取结果
  —— 回退的语义落在返回值上，而非异常。
- **决策③：回退发生时标记该源不健康（写入 `self._health`）。** 规格 Scenario 明写「标记源不健康」，
  且这是回退的**可观测痕迹**（否则回退静默发生，运维无从知道 S 源已失效）。
- **已知局限**：① 回退是**单次**的（不做重试、不做多级回退链）—— 非官方源只回退到官方源一个目标
  （与规格「回退官方源」的字面一致）；② `SOURCE_UNHEALTHY` 的**对外语义变了**：旧行为下「非官方源
  不健康」也会返回它，现在只在**无可用源**时返回 —— 仓内消费方仅 `client.search`（异常归一为
  stderr + 退出码 1，CLI 侧表现不变），无其他契约面。
- **规格**：`skillhub`（**MODIFIED**「多源路由与健康回退」—— 矛盾句拆解 + 「标记不健康」入正文，
  + **2** 新 Scenario「回退目标亦不可用」/「官方源自身不可达」，「源不可达回退」Scenario 的 THEN
  改为「返回官方源结果」，「源不存在」逐字保留）。**非** `skip_specs`。

---

## ADR-0128：分级按完整词元 + 高危审批门用 `APPROVAL_REQUIRED`（change 0135 / phase-34 E76）

- **背景**：`coding-plan/phase-34.md` 登记的 **E76**（规格漂移）。两处**规格/文档早已立规、代码未跟上**：
  ① `permission/spec.md`「分级权限体系」SHALL 依据**语义分词**（完整词元）判定、命名空间或无关子串的
  偶然命中 SHALL NOT 影响等级，`03-interfaces/permission-interface.md` §2 更以 change `0095` 立下同一契约
  —— 但 `policy.py` 的实现一直是**裸子串** `tok in op_l`：`tools.target`（含 `get`）、
  `tools.category_sync`（含 `cat`）、乃至**目标侧** `/var/log/target` 都被误判为 `read` ⇒
  「无法归类 → deny-by-default」的兜底在命名空间前缀下**失效**（`tools.*` 一族本可全被漏判）。
  ② `permission/errors.py:18` 定义 `APPROVAL_REQUIRED`（错误码表口径「高危操作需人工审批」），
  但 `src/` **零 raise**（死码）；而唯一的高危审批门 `GitClient._require_approval`
  却抛 `PERMISSION_DENIED`（「无权限」）—— **事由张冠李戴**。
- **决策①：`classify` 按词元集合命中，不做任意子串匹配。** 操作与目标先经 `_tokens` 按 `._:-/`
  切成**小写词元集合**（命名空间 `.`、路径 `/`、snake / kebab / coeffect 式 `_` `-` `:`），
  三个词元表转为 `frozenset` 后以集合交判定。判定顺序逐字不变（高危词元 → 高危 coeffect 前缀
  → 字面量委托豁免 → 写词元 → 只读词元 → 兜底 HIGH_RISK）。**目标侧同样切词** ——
  `tok in target_l` 的旧写法与操作侧是同一个缺陷。
- **决策②：`APPROVAL_REQUIRED` 的生产 raise 落点 = 高危 git 审批门。** 「缺审批」与「无权限」是两件事：
  前者应 `APPROVAL_REQUIRED`（错误码表原文），后者才 `PERMISSION_DENIED`。改 `_require_approval`
  抛 `APPROVAL_REQUIRED`，该码自此有**真实可达的 raise 落点**，非死码。
  **判据订正（明示偏离计划原文）**：计划原文写「`authorize` 的 `approval_required=True` 无审批时
  `raise`」——**未采纳**：`PolicyEngine.authorize` 对 HIGH_RISK **返回**
  `Decision(approval_required=True)` 是 loop confirm 门的**契约**（`guard._to_gate` 据此翻成
  `confirm` 走审批通道，`provider.py` / `loop/default.py` 依此 fail-closed），改成抛异常会**打断
  审批流**并令 `guard` 的 `approval_required` 分支成为新死分支 —— 以「消除死码」之名造新死码，
  得不偿失。同一错误的另一处（`git._require_approval`）才是该码的**正确语义落点**。
  **又一处订正**：计划所列测试例 `tools.list` **不**判 `read` 与实现自洽性矛盾 —— 词元 `list`
  本就是只读词，切词后 `tools.list` **应判 `READ`**（这是正确结果，不是缺陷）；真正的子串陷阱是
  `tools.target` / `tools.category_sync` 一类**词元非只读但含子串**的标识，测试据此改写。
- **已知局限**：词元表仍是**白名单**（`_READ_TOKENS` 等）——词元不在表内者一律落 deny-by-default
  HIGH_RISK，因此 `tools.stats`（词元 `stats` ≠ `stat`）从「子串误判 READ」变为「**保守地**判高危」；
  这是**有意**的 fail-closed 取舍（宁可多要一次审批，不放过一次误放行），新动作词入表即回归精确。
- **规格**：**无 delta** —— 两条均为「实现回归既有契约」（spec `分级权限体系` / 错误码表早已声明），
  故 `.openspec.yaml` 置 `skip_specs: true`（先例 `0110` / `0083`）。**非** 新增 Requirement。

---

## ADR-0129：composition 覆盖可回退 + 覆盖值拒布尔（change 0136 / phase-34 E75 + E70）

- **背景**：`coding-plan/phase-34.md` 登记的 **E75**（设计缺失）+ **E70**（真缺陷）。
  ① `composition/spec.md`「层叠解析」SHALL「解析结果可逆、可回退」、Scenario「确定顺序解析」THEN
  写明「卸载时可回退到覆盖前状态」，「patch.yml 用户覆盖」的「覆盖冲突兜底」亦要求「报错并回退到
  覆盖前状态」—— 但 `resolver.py:106-108` 把覆盖应用到 `merged` 后**丢弃了 `merged` 本身**，
  `ResolvedSet` 只留覆盖后 `plugins` 与 `overrides`，且全包**无 revert / undo API** ⇒
  规格的「可回退」是**无路径可达的死条款**。② `apply_patch` 以 `isinstance(override, int)` 判覆盖值，
  而 `bool` 是 `int` 子类 ⇒ YAML `true` / `false` **静默**落为 generation `1` / `0`，
  绕过「值类型不支持则报冲突」的兜底。
- **决策①：`ResolvedSet` 增必填字段 `layered`（覆盖前分层结果）。** `resolve()` 原样携带 `merged`；
  取**必填**而非默认 `[]`：`ResolvedSet` 的构造点全仓仅 `resolver.py` 两处（grep 实证，无既有调用方受损），
  而默认值会让手工构造漏传时 `revert` **静默清空全部插件** —— 必填把「解析结果必然知道自己被覆盖前的状态」
  变成类型层事实。
- **决策②：`ProfileResolver.revert(resolved) -> ResolvedSet` 为**纯函数**。** 返回**新** `ResolvedSet`
  （`plugins = layered`、`overrides = {}`、`layered` 原样携带），**不改实参** ⇒ 对回退结果再回退
  **结果不变**（幂等）。**不**经 `EffectTracker`：`resolve` / `revert` 同属无状态组合代数（L5 唯一静态层），
  不产生副作用；需跨调用持久的调用方自行持有 `ResolvedSet`。门面 `CompositionEngine.revert` 透出。
  回退范围**只到 patch 覆盖**（回到 bundle 层叠结果），层叠本身的回退（换 profile / 换 bundle）
  不在本账，属 `BundleDistributor` 面。
- **决策③：覆盖值拒布尔，沿用 `PATCH_CONFLICT`。** 判据订正为
  `not isinstance(override, int) or isinstance(override, bool)` —— 不新增错误码（复用「值类型不支持」既有分支）。
- **已知局限**：`layered` 是**覆盖前快照**而非可再解析的引用，回退后若要换 patch 需重新 `resolve`；
  布尔拒绝使「generation = 0/1 的合法场景」不可由 YAML 布尔表达（须写字面量 `0` / `1`）——
  这是**有意**取舍：布尔语义（开关）与代际编号（版本）本就不是同一件事。
- **规格**：`composition/spec.md` **MODIFIED「层叠解析」**（保留覆盖前分层结果 + 回退幂等 + 覆盖值须整数
  generation、布尔按 `PATCH_CONFLICT` 拒绝），原「确定顺序解析」Scenario 逐字保留，新增 2 Scenario。

---

## ADR-0130：beast 三入口接线收口 + 领域错误分码归一（change 0137 / phase-34 E74）

- **背景**：`coding-plan/phase-34.md` 登记的 **E74**（设计缺失）。`beast-mode/spec.md`
  「Three-Entry Activation」SHALL 三入口召唤（`/summon` 斜杠 / `summon` CLI / WebUI 自然语言）
  且「三入口最终落到同一 `BeastSession` 生命周期」，但**生产只有 CLI 一条通**：
  `BeastActivator` 的 `activate_from_slash` / `activate_from_nl` / `recall_from_slash` /
  `recall_from_nl` **全仓零调用方**；`entry.py` 构造 `UIAPILayer` 时未注入 `beast_activator`；
  `repl.py` 斜杠命令只有 `/focus` `/main` ⇒ `/summon` 被当普通对话发给 loop。契约方法层完备、
  生产接线缺席 —— 本 ADR 把 `phase-17.5.md:45` 的「三入口已实现」订正为**契约层实现**。
- **决策①：入口接线只落 `UIAPILayer` 面，不新增 HTTP 端点。** 三入口中的两个（TUI 斜杠 / WebUI
  自然语言）经 `UIAPILayer.beast_command` / `activate_beast` 落到注入的 `runtime.beast_activator`
  —— 与 pet 的 `activate_pet` / `pet_command`（change `0088`）**同型**：WebUI 侧是**消息驱动**，
  自身不是端点。这也正是 **E82 判为假阳性**的同一判据（规格未要求 pet/beast HTTP 端点）。
- **决策②：`activate_beast` 为 `async`（神兽激活 = 异步 handoff）。** `BeastManager.summon` 走
  `MultiAgentRouter.handoff` 并 `await` 全程，故方法与 `beast_command` 同为协程；`recall` 路径同步，
  但在同一 facade 内统一为 `async`（调用方不必按 verb 分形）。
- **决策③：领域错误在 API 边界**分码**归一（不并作一码）。** `BeastError` 与 `OrchestrationError`
  是**兄弟类型**（无继承关系），召回在岗检查可抛 `BeastError` ⇒ 只捕 `OrchestrationError` 会把裸领域
  异常漏进 TUI worker（`repl` 只捕 `UiError`）。故按**用户可见语义**分两码：无匹配神兽
  （`NO_AGENT_MATCH`）⇒ `UI_BEAST_NOT_FOUND`；状态冲突（`BEAST_ALREADY_MANIFEST` 重复召唤 /
  `BEAST_NOT_MANIFEST` 无在岗可召回）⇒ `UI_BEAST_STATE_INVALID`。**较原计划多一码**（计划写三条）：
  「无此兽」与「有此兽但不在岗」是两类用户动作纠错，合码会把「换名字重试」与「等它回来」混为一谈。
- **决策④：斜杠解析为纯函数 `_parse_beast_command`，缺目标不发起激活。** `/recall` **不带**任务位元；
  `/summon` 无神兽时只提示用法并复位忙态（不吞参数错误、不调 activator）。呈现与 CLI `summon` 同口径：
  一行状态 + **有结果才打印**一行结果（`result_summary()` 只读查询面，不检索、不落 L2、不编造）。
- **已知局限**：WebUI 自然语言的**意图解析**仍为骨架启发式（`_resolve_nl` 取首个词元，
  `activator.py` 自注「Agent 理解意图 deferred」）—— 本 change 只把入口接通，不接 LLM 意图理解
  （属 phase-17.5 遗留，不在 phase-34 二十五条账内）。生产 `BeastManager` 恒带 router ⇒ `summon`
  完成即自动回归，此后 `/recall` 报状态冲突（与 pet/TUI 的忙态语义一致；「任务在途时手动召回」
  是并发入口下的真实用途）。
- **规格**：**无 delta**（`beast-mode/spec.md`「Three-Entry Activation」/「Manual Recall」两 Scenario
  早已是硬 SHALL，实现侧纯背离 ⇒ conformance 修复）⇒ `.openspec.yaml` 写
  `schema: spec-driven` + `skip_specs: true`（先例 `0110` / `0083` / `0135`）。

---

## ADR-0131：git 远程断线重试 + 高危原语补面（change 0138 / phase-34 E79）

- **背景**：`coding-plan/phase-34.md` 登记的 **E79**（规格已 SHALL、代码纯背离）。`git/spec.md`
  「远程操作可靠性」SHALL「断线自动重试（retry，**指数退避**）」，Scenario 要求「按指数退避自动
  重试，达上限后失败并保持工作区一致」—— 而 `subprocess_backend.py` 的 `clone` / `pull` / `push`
  各**单次** `_run`，一次网络抖动即整操作失败。「与 permission 沙箱协作」SHALL 高危操作（强制推送、
  **删除远程分支**、**历史改写**）走审批链 —— 而 `client.py` **只有** force-push 走审批，另两原语
  在 13 项里**根本不存在**（无实现、无门）。
- **决策①：重试只覆盖远程三原语（`clone` / `pull` / `push`），经新私有 `_run_remote`。** 本地原语
  （`commit` / `status` / `merge` …）仍走 `_run`（本地失败重试无意义，且 `merge` 的冲突语义不能
  被重试掩盖）。首次成功路径与旧实现**逐字等价**（不重试即成功 ⇒ 零可观察差异）。
- **决策②：指数退避可注入（`sleep` / `backoff` / `attempts`），默认 `time.sleep` + `0.5s` + 3 次。**
  注入睡眠使测试**零真实等待**且能断言退避序列（`0.5, 1.0`）；不引随机 jitter —— 上限仅 3 次、
  面向单机 CLI，抖动收益不抵测试确定性损失（记为已知局限）。
- **决策③：超时**不**重试，认证失败**不**重试，冲突**不**重试。** 三类**显式**排除，理由是语义而非
  惰性：① **超时** —— spec「远程超时」Scenario 明写「中止该操作并返回超时错误，不无限挂起」，
  与「自动重试」字面冲突，本 change 取**超时优先中止**（`subprocess.TimeoutExpired` 在 `_invoke`
  即被转为 `GIT_REMOTE_TIMEOUT` 抛出，不经重试循环）；② **认证失败** —— 凭据不会在 0.5s 内自愈，
  重试只是把明确报错延迟 3 倍（spec「认证失败」Scenario 要求「明确报错」）；③ **冲突** —— 需人工
  解决，重试不可能变好。故 `_is_retryable` 只放行「`GIT_COMMAND_FAILED` **且** stderr 命中瞬态
  特征（`could not resolve host` / `connection reset` / `connection refused` / `rpc failed` /
  `early eof` / `network is unreachable` …）」一类 —— 瞬态判据**先于**通用归类，故「非仓库目录」
  这类确定性 `GIT_COMMAND_FAILED` **不**被重试（`_invoke` 一次）。
- **决策④：删除远程分支 / 历史改写复用同型审批门（泛化 `_require_approval(op, reason)`）。**
  三处高危各持**互异 op id**（`git.push(force)` / `git.delete_remote_branch` /
  `git.rewrite_history`），非交互（无回调）恒未批 ⇒ `AccessControlError(APPROVAL_REQUIRED)`
  且**在触碰后端前阻断**（与 force-push 同判据：缺审批非无权，见 change `0135` / ADR-0128）。
  两原语的最小真实形态：删远程分支 = `git push <remote> --delete <branch>`；历史改写 =
  `git commit --amend -m <message>`（**确属**历史改写，非本地提交）。
- **已知局限**：① 退避为**同步阻塞** `time.sleep`（worker 线程内），无 async 化 —— 本模块是同步
  subprocess 后端，async 化属另一面改动；② 重试**上限 3 次 / 无 jitter**（见决策②）；③ `rewrite_history`
  只覆盖**最近一次**提交改写（`--amend`），交互式 rebase 等更广改写面未纳入（够 spec Scenario 所需，
  超出即过度设计）。
- **规格**：**无 delta**（`git/spec.md`「与 permission 沙箱协作」`:61-67` + 「远程操作可靠性」
  `:69-91` 早已是硬 SHALL，实现侧纯背离 ⇒ conformance 修复）⇒ `.openspec.yaml` 写
  `schema: spec-driven` + `skip_specs: true`（先例 `0110` / `0135` / `0137`）。

---

## ADR-0132：Harness Host 心跳 + Desktop 端口单点与安装包开启（change 0139 / phase-34 E81 + E83）

- **背景**：`coding-plan/phase-34.md` 登记的 **E81**（设计缺失）与 **E83**（设计缺失）。
  E81：`deployment/spec.md`「客户端断线与会话清理」SHALL「检测客户端断开（**含心跳**/超时判定）」，
  Scenario「连接超时回收」的前提是「客户端**长时间无活动**」—— 但 `deployment/host.py` 的
  `last_seen` **仅 `accept` 赋值**，全类**无 touch / heartbeat** ⇒ `reap` 只能按「接入时刻」计时，
  一个**始终活跃**的长连客户端照样被判超时回收（「按活动计时」无从表达）。
  E83：`ui/spec.md`「桌面打包」SHALL 打包三平台可执行安装文件，而 `src-tauri/tauri.conf.json`
  ① 窗口 `url` **硬编码** `http://127.0.0.1:8000`，与 `main.rs` 尊重 `CORE_PORT` 的 sidecar 启动端口
  **可漂移**（内核换端口 ⇒ 壳指向空地址白屏）；② `bundle.active=false` ⇒ **产不出安装包**。
- **决策①：心跳以 `touch(session_id) -> bool` 落在 `HarnessHost`，只认在连会话。** 刷新 `last_seen`
  即 `True`；未知 / `DISCONNECTED` / `EXPIRED` ⇒ `False` 且**不复活** —— 心跳是**保活**语义，
  **不是复活**语义：若允许心跳把已回收会话拉回 `CONNECTED`，清理就形同虚设（断线客户端只要再发一次
  心跳即复权），与「回收该客户端会话与连接资源」的 SHALL 相悖。
- **决策②：`touch` 成功即持久化。** 与 `accept` / `disconnect` / `reap` 同口径（四处皆 `_persist`）。
  若不落盘，进程重启后重载的是**陈旧** `last_seen` ⇒ 活跃会话被按旧时刻误回收，正是本账要修的病。
  代价是心跳触发全量重写（JSONL 行数 = 会话数，量级极小）—— 记为已知取舍。
- **决策③：Desktop 端口**单点**取自 `CORE_PORT`，配置**不再出现端口**。** `tauri.conf.json` 的
  `app.windows` 清空（`url` 一并去掉），改由 `main.rs` 的 `resolve_port()` 解析一次，
  **同一变量**供 `spawn_sidecar` 与 `open_window`（`WebviewWindowBuilder` + `WebviewUrl::External`）
  使用 ⇒ 「壳与 sidecar 端口漂移」在结构上不可能（此前是两处独立字面量）。
  壳仍只做三件事（开窗 / 挂 SPA / 启 sidecar，ADR-0015），不含业务逻辑。
- **决策④：`bundle.active: true` + `targets: "all"`。** 三平台安装包构建改为**显式开启**；
  `targets: "all"` 而非枚举清单 —— 缺平台工具链时由 Tauri 跳过该 target（枚举清单会在无该平台
  依赖时直接失败）。实际产物为**手工验收**项（本仓四门禁无 Rust/打包面）。
- **已知局限**：① **驱动面** —— `HarnessHost.touch` / `reap` 今日**无生产驱动**（`entry._serve`
  注册一个 `serve` 会话后阻塞于 uvicorn，从不 reap）；本 change 与 `0138` 同类：补的是**规格 SHALL 的
  机制**，**驱动接线**不在 E81 闭账范围，登记为残留口径（不静默当作已完成）。② **心跳频率**
  由调用方决定，本 change 不引入后台心跳线程（避免在阻塞式 `serve` 路径里加并发面）。
  ③ **Rust 面验证强度** —— 四门禁不含 Rust；本次拟以 `cargo check` 为额外验证（非门禁，
  不入 CI 口径），但**本轮未跑通**（本地 vendored 依赖树与 `Cargo.lock` 版本不一致 ——
  `tauri-build` 锁定 2.7.1 而缓存为 2.5.6；`--offline` 直接解析失败，联网取包在本环境 13 分钟
  零进展后中止）⇒ **壳编译未经编译验证**，与安装包产出一并归**手工验收**（`test-cases.md` §55）。
- **规格**：**无 delta**（`deployment/spec.md:59-70` 与 `ui/spec.md`「桌面打包」早已是硬 SHALL，
  实现侧纯背离 ⇒ conformance 修复）⇒ `.openspec.yaml` 写 `schema: spec-driven` + `skip_specs: true`
  （先例 `0110` / `0135` / `0137` / `0138`）。

---

---

## ADR-0133：信息地图装配接线（change 0140 / phase-34 E77）

- **背景**：`context/spec.md`「信息地图」SHALL 把长文档转为目录索引、**模型按需跳转取详情**、
  「不把全文塞入窗口」，并以「地图定位与按需取详情」「地图失效重建」「重建失败二阶兜底」三 Scenario
  定格实现面。实现侧纯背离：`DynamicAssembler.build()` **从不读** `_info_map`（装配包无目录层）；
  `fetch_detail()` **零生产调用点**（模型无通道取详情）；`InfoMap._linear_scan()` **死码**
  （`index()` 恒同写 `_docs` + `_maps` ⇒ `lookup` 的「地图缺失」分支不可达）。账本 E77 判「构造了却从不查」。
- **决策①：目录层进装配包，且**真进提示词**。** `ContextPack` 增 `pointers`（`{doc_id, section,
  summary, pointer}`，`pointer = doc_id#section`），由 `build()` 读地图后注入（每文档上界
  `_MAX_POINTERS_PER_DOC = 8`）；`LLMPlanner._system_prompt` 渲染「文档目录（按需取详情，勿请求全文）」块
  ⇒ 「先定位指针」这一步在产线**真的发生**。缺省空 ⇒ 未接地图时装配/预算/提示词路径逐字不变。
- **决策②：消费面用**只读工具**，且取数器注入。** 新增 `tools.context_read`（`coeffects=[]` +
  `reversible=True` ⇒ 自动放行）承载「模型按需取详情」；`fetch_detail` 作为**取数器由组合根注入**
  （与 `gate_run` 的执行器注入同理 ⇒ **工具层不依赖 context 层**，L1 不反向依赖 L2 上下文工程）。
  工具 id 含 `read` 词元 ⇒ 权限分级按**完整词元**判只读放行（若命名不带 read 词元，会被
  deny-by-default 判高危 —— 实施期实测确认，见「验证」）。
- **决策③：二阶兜底给一个**显式门**，并把「受控」落成常量。** `InfoMap.register(doc_id, content)`
  = 仅登记**原文**、不建索引 ⇒ 该文档 `lookup` 走 `_linear_scan`（受控分段线性扫描）。
  `_linear_scan` 段数设硬上界 `_MAX_SCAN_SEGMENTS = 20` —— spec「**受控**分段线性扫描」的「受控」不再是形容词。
  与 `index()` 的分工是**一阶/二阶**：`index` = 原文 + 索引；`register` = 仅原文（**索引不可用**态）。
- **决策④：产线**非空转**。** `build_runtime` 建 `InfoMap` 并把 Core.md「## 项目信息」段索引为
  文档 `core-profile` 注入装配器 ⇒ 地图在产线非空、`build()` 的读取与工具的取详情都有真实对象
  （否则只是「接入了一条永远为空的链路」）。工具注册在 `if assembler is None` **之外** ⇒
  注入装配器的调用方（`build_runtime(assembler=...)`）同样拿到消费面。
- **已知局限**：① **指针摘要语义** —— `_build_pointers` 的 `summary` = 章节名（既有语义，本 change
  **不改**）⇒ `context_read` 对索引态文档返回章节名、对原文态（线性扫描）返回该段原文；
  「用 LLM 提炼要点摘要」不属 E77（另账），本 change 不假装解决。② **指针目录不计入
  `token_used`** —— `BudgetManager._measure` 口径不变（避免预算回归面），指针规模由
  `_MAX_POINTERS_PER_DOC` / `_MAX_SCAN_SEGMENTS` 双重上界约束；若将来目录层变厚，须并入预算测量。
  ③ **`rebuild_if_stale` 语义未改**（条目缺失仍抛 `MAP_STALE`）—— 「重建失败」的二阶兜底由
  `register` 态表达，不改既有异常契约。
- **规格**：**无 delta**（`context/spec.md`「信息地图」+ 三 Scenario 早已是硬 SHALL，实现侧纯背离
  ⇒ conformance 修复）⇒ `.openspec.yaml` 写 `schema: spec-driven` + `skip_specs: true`
  （先例 `0110` / `0135` / `0137` / `0138` / `0139`）。

## ADR-0134：core-profile 题词模板落为骨架产出物（change 0142 / phase-34 E85）

- **背景**：`core-profile/spec.md`「题词模板」SHALL「提供 Core.md 题词模板（骨架）」并给了「全局级模板产出」
  /「项目级模板产出」两 Scenario，但仓库里**没有任何模板产出物**（`find` 未命中、无专门测试）⇒ 该 SHALL
  既不可验证也不可使用；用户编写 `Core.md` 的唯一依据是题词规范（纯文字），看不出**分区标题必须逐字写成
  什么样**。这不是无害的文档欠账：分区标题是**运行时解析器**的判据（`profile.py:16-19` `_SECTION_HEADERS`），
  未知标题落 `unknown`、空分区一并 ⇒ `SECTION_INVALID` 告警并**跳过该分区**（spec「格式非法告警跳过」
  允许跳过）⇒ 用户凭直觉写「## 宪法」「## 人格设定」会导致整段预设**被静默跳过**且难以察觉。
- **决策①：把「提供模板」落为仓库内**具名静态产出物**。** `templates/Core.global.md`（落向
  `~/.core/Core.md`）与 `templates/Core.project.md`（落向 `<project>/Core.md`）—— 规格 MODIFIED 时
  写明路径与落向，使这条 SHALL 可被**逐条核对**（此前无对象可核）。
- **决策②：骨架与解析器**逐字对齐**，并把这一点做成 Scenario。** 新增 Scenario「骨架复制即被解析器
  接受」：以骨架**原文**（未改写）跑 `SectionParser` + `Validator` ⇒ 分区 kind 正确且**零 `SECTION_INVALID`**。
  于是「标题逐字」「分区非空」两个易错点在测试里**同时被钉住**，而不是靠文档提醒用户。
- **决策③：注入说明用 HTML 注释 / 引用行，不用普通文本。** 解析器 `_is_content` 会跳过 `<!--` 与 `>`
  开头的行 ⇒ 说明与用法**不进**注入内容；否则说明文字会被当成人格/宪法条目注入（自伤）。
- **决策④：不提供 CLI scaffold（`core-agent profile init`）。** 落盘式 scaffold 引入覆盖语义与可逆副作用，
  且会触碰 CLI 动词基线（30 动词 + 14 flag 的逐条 diff 断言，`test_phase13`）——本账只要求「提供模板骨架」
  ⇒ 静态产物即满足（YAGNI）。若将来确需 CLI 落盘，另立账。
- **已知局限**：① **骨架占位行是「内容行」** —— 解析器要求分区非空，故 `- 必须：<…>` 这类占位行**计入**
  注入内容，用户复制后须改写或删除（注释已就地说明，题词规范的「建议不超过 50 行」兜底）。
  ② **发现路径仅仓库目录 + `test-cases.md` §58** —— 未补用户手册章节（不在 E85 账内）。
  ③ **不做编码校验**：骨架是否为合法 UTF-8 由 pytest 读文件本身覆盖，未另设 schema 校验。

---

## ADR-0135：bundle 内容哈希口径归一 —— 发布入参改制品清单（change 0143 / phase-34 E84-a）

- **背景**：同一概念「bundle 发布哈希」在仓内有两套口径，且 **wired 的一方是退化口径** ——
  composition `packager.py:18-21 content_hash`（由**制品内容** `plugin_id@generation` 派生）全仓
  **零引用**；CLI `release publish` 走 `entry.py:1034-1036 _content_hash` = `sha256(版本名)[:16]`
  （哈希取自**元信息**，自注「CLI 无真实制品内容」）。后果是发布记录里的哈希**与「保证跨部署一致」
  的语义正好相反**：内容不同、名字相同 ⇒ 同哈希；名字不同、内容相同 ⇒ 异哈希。规格侧
  `composition/spec.md`「bundle 分发格式」只 SHALL「bundle 携带哈希 / 校验失败拒绝引入」，
  **未**把「哈希由制品内容派生」写成 SHALL ⇒ 退化口径**无据可依却唯一在跑**。
- **决策①：口径入规格（MODIFIED「bundle 分发格式」）。** 写明：哈希 SHALL 由制品内容（
  `plugin_id@generation` 有序逐项以 `|` 连接取 SHA-256）派生；**内容相同 ⇒ 哈希相同，内容不同 ⇒
  哈希不同**；SHALL NOT 以版本名 / 清单文件名等**元信息**充当内容哈希。规范形入规格是为了守住
  「跨部署一致」 —— 只要算法留白，两处实现就会再次漂移（本账就是这么来的）。
- **决策②：发布入参由「版本名」改「bundle 制品清单路径」。** 发布必须交出**制品内容**，否则无从
  派生内容哈希；沿用仓内既有约定 —— `plugin install <asset> --source local` 的 `_resolve_local`
  即把位置参数当 **manifest JSON 路径**（`plugins/install.py:68-75`）。清单（`plugin_refs` +
  可选 `name`）是 bundle 内容的载体，**不是新发明的格式**。
- **决策③：清单读取落在 composition（`BundlePackager.load_manifest`），不内联进 CLI。** CLI 的
  契约是「解析 + 路由，不内联命令逻辑」（`entry.py` 模块 docstring）⇒ 读清单 + 构造 `PluginRef` +
  取内容哈希属组合层职责；CLI 只注入 `ReleaseInfo(version=bundle.name, hash=bundle.hash)`。
  复用既有 `pack()` ⇒ 真口径**单一真源**，不复制哈希算法。
- **决策④：清单非法一律 `BUNDLE_INVALID`，不新增错误码、不退化。** 缺失 / 非法 JSON / 顶层非对象 /
  `plugin_refs` 非列表 / 引用项缺字段 ⇒ 结构化拒绝且**既有发布记录不变**（`ReleaseManager` 尚未
  `publish` 即抛出）—— 这是本账的**核心行为变更**：宁可拒绝，也不产「哈希取自版本名」的假账。
- **已知局限**：① `ReleaseInfo.hash` 目前**无任何消费方**（deployment 侧 `grep .hash` 零读）⇒
  本 change 只保证「写进去的是真口径」，**不保证**有谁在验它（那属另账）。② 清单只覆盖
  `plugin_refs` + 可选 `name`；bundle 的 `deps`（循环依赖检测）与显式版本不在清单面内
  （`pack()` 版本仍为 `1.0.0`）。③ CLI 位置参数语义变更 ⇒ 已同步 `cli-contract-baseline.md`
  动词表与 `deployment-interface.md` §3。
- **规格**：`openspec/specs/composition/spec.md`「bundle 分发格式」（MODIFIED，+2 Scenario）；
  接口面 `03-interfaces/composition-interface.md` §4/§5、`03-interfaces/deployment-interface.md` §3。

---

## ADR-0136：时间旅行回滚补生产入口（CLI `time-travel`）（change 0144 / phase-34 E73）

- **背景**：`durability/spec.md`「时间旅行」是**硬 SHALL**（「将执行态回滚到**任意历史检查点**……
  与 tool-use 副作用级 EffectId undo 栈协同，不新建撤销机制」），两个 Scenario 明确要求
  「**上层请求**回滚到某个历史检查点」⇒ 执行态恢复 + 沿历史逆序撤销写类副作用。实现侧
  `durability/manager.py:132-149 TimeTravel.rollback()` **完整**，`runtime.py:853` 以生产真源
  构造（`CheckpointStore(_checkpoint_path())` + 与 `tools` / `memory` **共享**的 `EffectTracker`）、
  `:1033` 注入 `Runtime`，检查点持久化本身也在用（`task --resume` 依赖）——**唯独「上层请求」
  这一环全仓零生产调用方**（只有 `test_durability` / `test_phase15` 直调）⇒ 能力存在但**用户不可达**
  （死面）。故本账定性为**设计缺失**而非实现缺陷（E73 行口径）。
- **决策①：补**一个**顶层 CLI 动词** `core-agent time-travel <checkpoint-id>`（不改 `rollback` 一行）。
  理由：规格要求的是「上层**请求**」这一环，CLI 是本仓既有的「上层请求」形态；命令面 32 → 33
  只增不改，既有动词 / flag / 行为逐字不变。
- **决策②：入口经 `build_runtime(_config_manager(args))` 取 `runtime.time_travel`，不另起存储真源。**
  与 `task` / `run` 同一组合根 ⇒ 同一 `$CORE_STATE_DIR/checkpoints.jsonl`、同一共享 `EffectTracker`
  （`test_phase15` 已把 `tools._tracker is time_travel._effect_tracker` 钉住）。**不**在 CLI 内联
  构造 `CheckpointStore(_checkpoint_path())`：那会把「检查点落哪」复制成两份口径（`entry` 只做
  「解析 + 路由」）。
- **决策③：失败 fail-closed、回执不吹。** 未知检查点 ⇒ `DurabilityError(CHECKPOINT_NOT_FOUND)`
  转 `回滚失败: …` + 退出码 1（不静默、不伪造成功）；成功 ⇒ 打印回滚到的检查点 id、恢复状态键数、
  撤销集（`state["trace_ids"]`）条数 —— 数字取**快照真值**，不臆造「已撤销 N 条」。
- **决策④：撤销集语义不动。** `rollback` 的撤销集 = 该点快照 `state["trace_ids"]`（既有设计，
  `test_phase15` / `test_durability` 锚定），本 change **不**改成「差异集」或按时间戳切分 ——
  E73 是**接线**账，语义变更属另账（见已知局限①）。
- **已知局限**：① 「沿快照**差异**逆序」的规格措辞与实现的「按快照 `trace_ids` 集回滚」**未完全
  对齐**（实现无「检查点之后的 trace」这一信息，`Effect` 只在 `EffectTracker` 内按 trace 聚合）
  ⇒ 保持既有语义并在接口面记明，改语义须另立账。② `Effect.undo` 是**进程内闭包**、不可持久化
  ⇒ 一次性 CLI 进程内撤销循环**空转**（快照恢复与失败语义仍生效）；撤销协同在**同进程**入口
  （`serve` / REPL / 同一 runtime 内的 `task`）生效。③ 命令面计数 32 → 33 ⇒ 已同步
  `cli-contract-baseline.md`（§1/§2.12）、`user-guide.md`、`entry.py` docstring。
- **规格**：`openspec/specs/durability/spec.md`「时间旅行」（**无 delta** —— 硬 SHALL 早已在，
  本 change 为 conformance ⇒ `skip_specs`）；接口面 `03-interfaces/durability-interface.md` §4、
  `coding-plan/cli-contract-baseline.md` §2.12。

---

## ADR-0137：Think 思考过程回显链路（change 0145 / phase-32 E56~E60）

- **背景**：`phase-32.md` 提案的「聊天窗口 Think 思考过程回显」是**一条链全断**：provider 解析
  **丢** `reasoning_content`（E56）⇒ planner 的 `astream` 协议**无**思考通道（E57）⇒ loop
  永不 emit `loop.reasoning`（E58）⇒ `ui/api.py::_EVENT_MAP` 未登记该类型（E59）⇒ 三端不渲染
  （E60）。五层任缺其一则用户**不可见**，故五处 delta 必须**一次落齐**（不可拆 change）。
- **决策①：口径归一收在 provider 层，单内部字段 `thinking`。** `LLMResponse` / `LLMChunk` 各增
  `thinking: str = ""`；`stdlib_provider._thinking_text(message)` 双键归一 —— **`reasoning_content`
  优先**（GLM / DeepSeek 系），`reasoning` **兜底**（OpenAI o 系），两者皆缺 / 非字符串 ⇒ 空串。
  理由：差异只发生在**一家 SDK 的字段名**上，归一化放得越靠上游，下游（planner / loop / UI）
  越不必知道「是哪家」。**绝不掺入 `content`** —— 思考原文与回复正文是两个语义，混进 `content`
  会被下游当作回复落进转录（破红线）。
- **决策②：通道用**新增 dataclass item**，不改 `str` 协议。** `loop/protocol.py` 增
  `Thinking(delta: str)`（frozen）；`LLMPlanner.astream` 返回型扩为
  `AsyncIterator[str | Action | Thinking]`。理由：`astream` 既有两种 item（`str` 回复增量 /
  `Action` 终态）承载的是**互斥语义**（增量 vs 终态），若用「带标记的 str」表达思考会污染既有
  判据（`chunk.content.startswith("{")` 的工具调用嗅探、`reply_stream` 判定）；新增类型让
  `isinstance` 分流**显式且零歧义**，且既有消费方（`default.py::_reason_events`）的 `str` / `Action`
  分支逐字不动。
- **决策③：开关挂在 planner 实例，且**只注入主 planner**。** `LLMPlanner(show_thinking=False)`
  （缺省关）；`runtime.py:597` 主 planner 注入 `app.llm.show_thinking`，**子任务 / 神兽 / 宠物
  planner 不注入**。理由：①缺省关 ⇒ 事件面与既有缺省**逐字一致**（`show_thinking and chunk.thinking`
  短路，零 `Thinking` 产出）；②「思考原文**不上**子任务回流通道」这条红线由**注入面**天然保证，
  不依赖 `scheduler._PROGRESS_FIELDS` 白名单去兜 —— 白名单是**第二道**防线（`loop.reasoning`
  不登记，见决策⑤）。
- **决策④：`_reason_events` 增 `Thinking ⇒ loop.reasoning` 分支，并把 `streamed` 判据收窄
  为**只认 `reply_delta`**。** 原判据 `streamed = streamed or item.type.startswith("reply")` 在
  思考事件出现时会把 `streamed` 置真 ⇒ **吞掉**终态全文补发（用户看到半句）。收窄为
  `item.type == "reply_delta"` 后：思考事件**不**参与「是否已流式」判定，终态补发照旧。这是本
  change **修掉的既有隐患**（开关开启时才会显形）。
- **决策⑤：`_EVENT_MAP` 登记 `loop.reasoning` 为**恒等映射**。** `ui/api.py::_EVENT_MAP` 是
  显式契约表（SSE 类型 → 前端事件名）；`_map_event` 对未登记类型本有**恒等兜底**，故严格说
  登记**非行为必需** —— 但显式登记使「该类型是**有意**透传，不是漏登记走了兜底」在代码面**可读**，
  并被 `test_ui.py` 以**契约表断言**钉住。三端渲染一律**折叠块默认收起**（TUI 单块 `▸ 思考`、
  同轮增量归并；Web `<details>`；APP 同构）。
- **已知局限**：① 第一步「**实测** glm-5.3 实际流式字段名」被**凭据物化**阻断（`config.yaml`
  密钥只引用不读取、绝不回显）⇒ 双键归一按 **GLM/DeepSeek 系 `reasoning_content` + OpenAI o 系
  `reasoning`** 的公开口径落地，**真端点字段取证转为手工验收项**（记 `04-testing/test-cases.md`
  TC-THINK-05）。若实测字段名不在两键之内，只需扩 `_thinking_text` 的键位（单点）而无涉链路。
  ② 前端 (Svelte) 无 JS 测试面 ⇒ `Chat.svelte` 渲染同记手工验收项（TC-THINK-04）。③ 思考原文
  **不进**转录 / 记忆 / 日志 / 事件持久化（守 change `0115` 边界，`test_loop.py` 以红线断言钉住
  `_RecordingMemory.written` 不含思考文本）。
- **规格**：`llm-provider`「默认实现与配置归一化」（MODIFIED）、`loop`「异步流式执行」
  （MODIFIED）、`ui`「思考过程回显（Think）」（**ADDED**）、`configuration`「LLM 提供商配置（必选）」
  （MODIFIED）；接口面 `03-interfaces/llm-provider-interface.md`、`03-interfaces/loop-interface.md`、
  `03-interfaces/ui-interface.md`、`00-product/user-guide.md`。

---

## ADR-0138：TUI 流式 Markdown 表格整块解析（change 0146 / 账本 E88）

- **背景**：TUI 流式回复中的 **Markdown 表格**渲染为**竖线原文**（`E88`）。根因**不在** `Markdown`
  控件（`repl.py:214-219` 用 Textual `Markdown`，v8.2.8 **内建**表格渲染），而在 `_show_delta`
  （`repl.py:461-479`）的**按行固化**策略：`len(text) >= _TAIL_SPLIT` 或 `text.endswith("\n")`
  时立即 `_freeze_tail`，把尾段固化成**独立**块（append-only、之后不再重渲染）。而 Markdown 表格
  **必须整块**（表头行 + `|---|` 分隔行 + 数据行，**中间无空行**）方能被解析 ⇒ 逐行流式时**表头行
  一到达即被固化**为「只有表头、无分隔行」的孤立块（解析器判为普通段落），后续分隔行 / 数据行各自
  固化为新块 ⇒ 表格**永拼不齐**。代码**已**对**代码围栏**做了同类保护（`_in_open_fence`，
  `repl.py:481-485`，`_TAIL_FENCE_CAP` 兜底），**唯独没覆盖表格** —— 属**机制疏漏**：表格与围栏
  同属「**须跨行整体解析**」的结构，保护机制同源，本 change 即补齐。
- **决策①：判据收在新静态方法 `_in_open_table`，与 `_in_open_fence` **同型**。** 两处
  「是否处于未闭合结构块内」的判定并置、同签名（`text -> bool`），新读者可一眼看清「围栏 / 表格」
  是一类东西的两种实例。理由：本 change 的**最小正确**修法是补一个平行判据，而非重构分段器。
- **决策②：表格判据 =「当前块**每行**含 ≥2 个 `|`」。** 自尾向前取**当前块**（连续**非空**行，
  遇空行即止；行终止用的**单个尾 `\n`** 不算空行），当且仅当**每行**都含 ≥2 竖线时判为「未闭合
  表格块」。理由：Markdown 表格行（含 `|---|` 分隔行）**恒**含 ≥2 竖线，而普通散文**罕见**；
  「单竖线散文」（如 `见 foo|bar`）不误判。
- **决策③：**围栏判定优先于表格**。** `_in_open_fence` **先判**，围栏**内**的 `|` **不作**表格
  （代码块里写 Markdown 表格语法是合法内容，不应触发表格延后逻辑）。这与既有围栏分支的**优先序**
  一致，围栏路径**逐字不动**。
- **决策④：未闭合表格块**延后固化**，仅超硬上限兜底。** 新增常量 `_TAIL_TABLE_CAP = 8000`（与
  `_TAIL_FENCE_CAP` 同口径）；`_show_delta` 在**围栏分支之后、常规分支之前**插入**表格分支**
  （与围栏**同型**）：未闭合 ⇒ `_touch_tail` 延后；`len(text) >= _TAIL_TABLE_CAP` ⇒ `_freeze_tail`
  兜底。理由：块**闭合**（出现空行或块外内容开始）后方恢复常规固化，未闭合缓冲**有界**。
- **决策⑤：**只加表格分支，常规路径逐字不动**（零回归）。** `_TAIL_SPLIT` 常规路径与
  `_freeze_tail` / `_touch_tail` / `_flush_live` 语义**不变**；表格分支只在「当前块每行 ≥2 个 `|`」
  时生效，普通回复（无竖线）走既有路径，行为与缺省**逐字一致**。
- **已知局限**：① **判据近似** —— 散文行含 ≥2 个 `|`（如 `a | b | c`）会**过度延后**固化
  （**有界**：超 `_TAIL_TABLE_CAP` 兜底）；极罕见，本 change 接受。② **Web 端不渲染 Markdown**
  —— `frontend/src/views/Chat.svelte` 以**纯文本** `{line.text}` 呈现（**无** markdown 渲染器），
  表格在 Web 恒显竖线原文；那是「**无渲染器**」而非**分段 bug**，属**另一端、更大特性**，
  **不在本 change 面**。③ **其它跨行结构**（列表 / 引用块）**未**纳入本 change —— 本次只对齐
  用户点名且与围栏**机制同源**的**表格**。
- **规格**：`ui`「CLI 友好交互」（MODIFIED，新增 Scenario「流式结构化块整体解析」）；接口面
  `03-interfaces/ui-interface.md`、测试面 `04-testing/test-cases.md`、台账 `coding-plan/known-risk.md`。

---

## ADR-0139：TUI 流式回显合帧节流 + 表格整块延后渲染（change 0147 / 账本 E89）

- **背景**：TUI 流式回显「**阶梯式**、表格**逐行**绘制、不够丝滑」（`E89`）。两条并列根因（均在
  `src/core/ui/repl.py`，**非** Markdown 控件缺陷）：① **逐 delta 全量重解析** —— `_show_delta`
  每收到一个 SSE delta 就立即 `_touch_tail` → `Markdown.update(text)`；Textual 的 `update()` 是
  **整篇 re-parse + 全量 re-layout**，且被 `Markdown.lock` **串行化** ⇒ 尾段越长每 delta 代价越高
  （尾段 O(n²)），delta 密集时渲染队列积压 ⇒ 肉眼即「一卡一卡」；② **未闭合表格逐行重排** ——
  change `0146` 已让表格**整块固化**，但未闭合期间仍每 delta `_touch_tail` 重绘，而 Markdown 表格
  **列宽按内容自适应** ⇒ 每加一行整表列宽重算 ⇒ 表格区逐行「抽动」。**对照参考**：Claude Code 的
  TUI 是 **Ink（React for CLI）** —— `state → 虚拟树 → reconciler diff → 只重写变化的终端行
  （frame diffing）` + **节流/合批**渲染。本 change 只取其中**两条可直接落地的精髓**（合帧节流 +
  整块延后渲染），**不引入** React/diffing 运行时（与「架构最优、不踩红线、尽量不依赖三方库」
  冲突；Textual 自有布局/滚动，帧级 diff 无收益）。
- **决策①：合帧节流 —— delta 只入缓冲，固定节拍合并渲染一次。** `_show_delta` 改为**仅**追加
  `_live_buf`/`_tail_buf` + 置 `_tail_dirty`，并**懒启动** `_tail_timer =
  set_interval(_TAIL_FLUSH_S, self._flush_tail)`（`_TAIL_FLUSH_S = 0.04`，与 `_spin_timer` **同型**：
  空闲不空转）。新 `_flush_tail()` 在**合并后的缓冲**上跑原分支体（围栏 / 表格 / 常规）⇒ 渲染次数与
  delta 速率**解耦**，尾段 O(n²) 降为「每 40ms 一次」。`Timer.stop()` 会 **cancel** tick 任务，
  无残留排队。
- **决策②：时序闸收在 `_add`（唯一挂载漏斗），而非 `_run_turn` 分支前。** `_flush_tail` 具备
  **重入安全**（`_flushing` 闸）+ **幂等**（`_tail_dirty`），故 `_add` 可在挂**非尾** widget 前
  **无条件**调用它。理由：`_add` 是**全部** widget 挂载的唯一漏斗 ⇒ 比在 `_run_turn` 非 delta 分支前
  flush **覆盖更全** —— 还覆盖 `action_barge_in`（`:452-455`，Ctrl+B 中途打断）与 `_ask_approval`
  （`:443-444`，审批门中途挂起）这两条**在 turn 中途**才挂 widget 的路径（挂起文本须在挂件**之上**）。
  终止性：重入深度**恒为 1**（`_flush_tail` 内 `_add` 见 `_flushing=True` 直接跳过）。
- **决策③：未闭合表格**延后渲染**（不绘制中间态）。** `_flush_tail` 的表格分支由「`_touch_tail`
  热更新」改为「**直接返回**」：未闭合表格**不渲染**，待块**闭合**（空行 / 块外内容）或超
  `_TAIL_TABLE_CAP` 后**一次整块成型**（列宽只算一次）。**围栏分支维持 `_touch_tail`**（代码应流式
  可见，不回退）。理由：表格的中间态**必然错排**（列宽随内容变）⇒ 画了也要重画，不如不画。
- **决策④：`_flush_live` 停表 + 清脏，**不**调 `_flush_tail`。** 收尾停 `_tail_timer`、置
  `_tail_dirty = False`，再走既有 `if self._tail_buf: self._freeze_tail(...)`。理由：`_freeze_tail` 已
  覆盖「已热更新的尾块」与「仅缓冲未渲染的尾段」（**含被延后的未闭合表格**）⇒ 中断/异常
  （`_run_turn` 的 `finally`）**不丢字**；若改调 `_flush_tail` 则可能**先 touch 一块再 freeze 一块**
  （双重渲染）。
- **决策⑤：常规路径逐字不动（零回归）。** `_touch_tail` / `_freeze_tail` / `_in_open_fence` /
  `_in_open_table` / `_TAIL_SPLIT`（**语义不变**，只改为在**合并缓冲**上求值 ⇒ 只会**更少、更大**的
  冻结块，布局抖动**严格减少**）/ `_run_turn` / `_live_buf` / `_last_reply` **不动**。
- **已知局限**：① **未闭合长表格有「无可见进度」窗口** —— 自表头到达至闭合（或超 `_TAIL_TABLE_CAP`
  = 8000）之间**屏幕上不出现该表**；如不可接受，出路是加占位 `Static("…生成中")`，**不**回退
  `_touch_tail`。② **40ms 节拍为常量非配置项**（无 CLI / env 面）—— YAGNI，调整改一处常量。
  ③ **Web / APP 端不适用** —— `frontend/src/views/Chat.svelte` 以**纯文本**呈现（无渲染器），
  属**另一端**。
- **规格**：`ui`「CLI 友好交互」（MODIFIED，新增 Scenario「流式回显合帧与表格延后渲染」＋合帧/延后
  条文）；接口面 `03-interfaces/ui-interface.md`、测试面 `04-testing/test-cases.md`、台账
  `coding-plan/known-risk.md`。

---

## ADR-0140：记忆压实「增量滚动摘要」（change 0148 / 账本 E90）

- **背景**：审查外部参考件 `Agent-Memory.md`（本地 Agent 长对话记忆压缩方案）后**取精华弃糟粕**，
  立账 `E90`/`E91`/`E92`。**`E90` 是唯一会真实损害长会话质量**的项：当前记忆摘要为「**批式重提炼 +
  固定 id 原地覆盖**」，**不是**参考方案的「现有摘要 + 新片段 → 合并」。**根因（三处，均在
  `src/core/memory/`）**：① `store.py:369` `_episodic_groups()` **只收 `kind=="episodic"`** ⇒ 旧摘要
  （`kind=="semantic"`）**不进 prompt**；② `store.py:391` 摘要 **id 写死** `compaction.summary.<key>`
  ⇒ 新一轮摘要**原地覆盖**上一轮；③ 被覆盖的原摘要所引条目**已迁 L4**（`store.py:401-402`）⇒
  **长会话早期结论逐轮稀释直至丢失**。且该行为已被**接口文档写成明文契约**
  （`03-interfaces/memory-interface.md` §3「摘要式压实」表：`id` = `compaction.summary.<session_id>`
  「同会话重复压实为**覆盖**，不增长」）⇒ 本 change 是**规格 + 接口双重口径**变更。
- **决策①：滚动合并 —— 既有摘要**以 `MemoryEntry` 形态**并入投喂材料。** `_summarize_sessions`
  投喂前取该会话既有摘要条目（`id == f"compaction.summary.{key}"`，`key = sid or "default"`，自
  `_all_entries()` 取），组成 `material = [prior, *entries] if prior is not None else entries` ⇒
  `summarizer(material)`；`build_prompt` 把既有摘要条目（判据 `"summary" in entry.tags`）渲染为显式
  「现有摘要」槽位。理由：既有摘要本就是 store 里的 `kind=="semantic"` 条目 ⇒ **不需为摘要单开参数**，
  **`Summarizer = Callable[[list[MemoryEntry]], str]` 契约不变**、`MemoryStore.__init__` 与组合根
  `summarize_with(_llm_text)` 装配**零改动**。
- **决策②：保持固定 id —— 滚动的是**内容**，不是**条目数**。** 摘要条目 `id` 仍为
  `compaction.summary.<key>`、每会话**至多一条**。新条文与接口「不增长」的**条目数**口径**相容**
  （改的是内容语义，非 id 形态）；亦**不新增** `MemoryEntry` 字段、**不引入**版本化 id ⇒ 不违背既有
  接口合同。
- **决策③：既有摘要**只入摘要器、不入迁移列表**（不得被迁 L4）。** `_commit_summary(sid, entries,
  summary)` 的第二参**仍只传本轮 `entries`** ⇒ 既有摘要条目被**吸收**进新摘要，**不**被归档。
  理由：既有摘要若同时被迁 L4，则会**从 L2 消失**，下一轮 `_all_entries()` 取回不到它 ⇒ 滚动**断裂**。
- **决策④：专设 `_MAX_SUMMARY_CHARS = 2000`。** 既有摘要的节选上界**独立于** `_MAX_ENTRY_CHARS = 400`
  （后者只管**单条新事件**）。理由：既有摘要若同受 400 字截断，滚动**依然丢结论** ⇒ 专设上界是**修复
  生效的前提**；仍为常量 ⇒ token **有界**（不引入配置面，YAGNI）。
- **决策⑤：**不改** `write()` 的 undo 语义。** 压实效应**共用** `trace_id = f"compaction.<key>"` ⇒
  回滚恒为**该会话全量压实一并逆转**（摘要移除 + 原条目迁回 L2），与规格「压实可撤销」Scenario
  **一致** ⇒ **非本次引入、非缺陷**（`_undo_write` 删条目不恢复旧值一事，在本共用 trace 口径下无实际
  危害；改语义另立账）。同理**不动** `_below_gate` 价值门控、`_score_importance` 打分写回、
  `_commit_summary` 的 id/tags/trace、`_episodic_groups`、`read`/`write`/`migrate`/`forget`、
  `Summarizer` 别名、`MemoryEntry` 字段、`context/compactor.py`。
- **已知局限**：① **覆盖写不支持单轮回滚** —— 压实效应**共用** `trace_id = f"compaction.<key>"`，回滚为
  **该会话全量**（既有口径，非本次引入）；若将来需**单轮**回滚摘要，须先改「共用 trace」口径。
  ② **摘要质量取决于注入模型** —— 未注入摘要器则**降级不写**（既有行为，非本次引入）。③ **既有摘要超
  `_MAX_SUMMARY_CHARS`（2000）即被截断** —— 有界优先（token 有界）；超长会话的极早期结论仍可能被
  截断，属**有界性代价**。
- **规格**：`memory`「记忆压实」（MODIFIED，新增 Scenario「滚动合并既有摘要（不丢失）」＋滚动合并条文）；
  接口面 `03-interfaces/memory-interface.md`、模块面 `02-modules/memory.md`、测试面
  `04-testing/test-cases.md`、台账 `coding-plan/known-risk.md`。

---

## ADR-0141：常驻（pinned）笔记 —— 任务级硬约束锚（change 0149 / 账本 E93）

- **背景**：`notes`（canonical Markdown 真相层，ADR-0099）承载「刻意知识」，但其 Consult 只在 **query 命中**
  时注入正文；未命中仅进 ≤1200 字**标题清单**（`NoteStore.digest`）。长任务中期的硬约束（「对外接口必须 HTTPS」）
  **不保证每轮在场** —— 取决于当轮 query 是否命中。每轮**恒注入**的此前只有 L0 宪法（**全局、非任务级**）。
  审查外部参考件 `Agent-Memory-LongTask.md`（跨月级任务记忆方案）后**取精华弃糟粕**立账 `E93`（其「里程碑锚定」
  ＝高保真硬约束永久置顶于 System Prompt 最前端）；同源不同层的 `E94`（摘要→canonical 提升**触发**）
  是 change `0150`/ADR-0142，**依赖**本 change。
- **决策① 注入架构 = 独立块**：新增 `LoopContext.pinned_notes` 字段 + `LLMPlanner._system_prompt` 新增
  **独立块**「常驻笔记（任务级硬约束，逐轮生效，勿违背）」，位置**紧随宪法规则、先于**相关事实/文档目录/相关笔记。
  **不并入**既有「相关笔记」块 ⇒ 命中面与常驻面**分列**，spec delta 得以**纯 ADDED**（无需重述既有 3 条 Requirement
  的 5 条 Scenario）。
- **决策② 钩子 = 零参**：`PinnedNotesConsult = Callable[[], str]`（对比 `NotesConsult = Callable[[str], str]`）。
  **签名即契约** —— 无任务文本入参 ⇒ 常驻注入**与当轮任务无关**、不因 query 未命中而缺席；误传任务文本会
  TypeError ⇒ 测试以「有内容即证零参调用」钉住。
- **决策③ 标记面 = 元数据 + CLI**：`NoteEntry.pinned` ＋ canonical 行 `- pinned: true`（**未置位不输出** ⇒
  既有文件逐字不变、`render_note` 零回归）＋ `notes pin/unpin`。解析**宽容**（`true/yes/1/on`，大小写不敏感），
  无法识别一律 False（**fail-closed**：手误绝不意外置常驻）。`set_pinned` **幂等**（同值不写盘、不 bump
  `updated_at`），真变更走**唯一** `update()` 原子覆盖写路径。
- **决策④ 专设 `_MAX_PINNED_CHARS = 4000`**（独立于 `_MAX_DIGEST_CHARS = 1200`）：常驻注入为**正文全文**
  （非 `_MAX_EXCERPT_CHARS=200` 的节选），若共用 digest 上界则摘要会**吞掉**常驻；独立上界使常驻面**有界**
  （token 有界，P5）又不与命中面互相挤占。`pinned_digest` **无 query 入参**、按 `note_id` 升序
  （**确定性** ⇒ 块字节跨轮稳定）、空正文笔记不占块、块内**不含** `updated_at`。
- **决策⑤ 三 loop 同注入**：组合根 `Runtime.build_runtime` 的 `_pinned_notes` 闭包注入**主 loop / 子任务 loop /
  神兽 loop** 三处 —— 子任务与神兽同须遵守任务级硬约束（与 `notes_consult` 的注入面**完全同构**）。
  loop **不 import notes**（架构红线），常驻源取用失败 ⇒ 降级置空 + 留痕 `pinned_notes_consult_failed`、
  **不改变本轮结局**（与 Consult 同口径）。
- **决策⑥ planner 装配顺序显式化**：宪法/相关事实/文档目录原同处一个 `if assembler is not None` 块内，
  常驻块须**紧随宪法规则**且**不依赖装配器**（缺省未装装配器亦须在场）⇒ 把 `pack` 求值提到块外（
  `pack = ... if assembler else None`），随后按
  `宪法规则 → 常驻笔记 → 相关事实 → 文档目录 → 相关笔记 → 可用技能 → 可用工具` 顺序 append。
  **语义逐字不变**，仅在 `_system_prompt` 函数内使顺序显式化（本 change 面内）。
- **决策⑦ `observe_turn` 原样携带 `pinned`**：任务后写回重建 `NoteEntry` 时**必须**携带既有 `pinned`
  （否则一轮 slug 命中常驻笔记 ⇒ 标记被静默抹除 —— 恰是 E93 的失效形态）；"逐轮写回不得抹除常驻标记"。
- **已知局限**：① 常驻正文**每轮进模型上下文** ⇒ **绝不**可把密钥/凭据写进常驻笔记（已入 proposal 风险节与
  proposal 红线）；② 总量有界于 `_MAX_PINNED_CHARS` 但**无 per-note 上限** —— 多篇各自很长时仍受总量约束，
  末篇可能被截断；③ notes 写操作**不接** `EffectTracker`（canonical 文档层的**既有取舍**，ADR-0099；
  pin/unpin 走同一 `update()` 路径 ⇒ 与既有写入面**一致**，非本次引入）；④ 常驻层是**全局**文档层 ⇒ 跨会话共享
  （与既有「刻意知识不参与隔离」一致，**非**缺陷）。
- **规格**：`notes`（**ADDED** Requirement「常驻（pinned）笔记（任务级硬约束锚）」＋ 6 Scenario）；
  接口面 `03-interfaces/notes-interface.md`、模块面 `02-modules/notes.md`、测试面
  `04-testing/test-cases.md` §65、台账 `coding-plan/known-risk.md`。

---

## ADR-0142：会话摘要提升为 canonical 常驻笔记（change 0150 / 账本 E94）

- **背景**：`coding-plan/known-risk.md` `E94` —— change `0148`（滚动摘要）后，回喂既有摘要按
  `_MAX_SUMMARY_CHARS = 2000` 取**前** 2000 字（旧端）⇒ 长时程下**早期硬约束缓慢稀释**（ADR-0140 局限②）。
  缓解物已有（`notes` 不参与压实 + L0 宪法 + 信息地图 pointers），但「硬约束提升进 notes」**只靠技能纪律
  `skills.notes.consult_build_update` 自觉，无强制、无触发点**。与 `E90`（change `0148` 已修）**同源不同层**：
  E90 修**摘要内**稀释，E94 补**摘要 → canonical 提升**。**依赖** change `0149` / ADR-0141（常驻 pinned 笔记；
  其背景已预留 E94 = change `0150` / ADR-0142）。
- **两处源码订正（否决「自动触发」判据的实证）**：① **`MemoryEntry.importance` 对摘要条目恒为 `0.0`** ——
  `_score_importance`（`store.py:326`）只对 `_episodic_groups`（只收 `kind=="episodic"`，`store.py:371`）打分，
  摘要在其后由 `_commit_summary`（`store.py:394`）以 `MemoryEntry(...)` **默认参数**创建 ⇒
  「摘要 `importance ≥ 阈值`」是**死判据**（永不触发）；下轮 `_episodic_groups` 仍排除它（`kind=="semantic"`）。
  ② **循环内压实是「全量」而非会话级** —— `default.py:447` 调 `self._memory.compact()`（**无 `session_id`**）⇒
  一次压实为**所有**有 L2 episodic 的会话写摘要 ⇒ 「压实后钩子按 `ctx.session_id` 提升刚写的摘要」**范围错配**。
- **决策①：触发 = 显式（CLI 动词），不做自动压实后钩子。** 新增 `core-agent notes promote <session-id>
  [--as <note_id>] [--title <title>]`。理由：(i) `notes` 规格身份是「**被有意文档化**的刻意知识，**不是某一轮
  对话的残留**」（`notes/spec.md:62-63`）⇒ 自动把 LLM 生成的会话摘要灌进全局 canonical 层，等于把「对话残留」
  自动升格为「刻意知识」，**须 MODIFY 哲学条文**；显式动词下「谁运行 `notes promote`」本身即「有意」的证据 ⇒
  **天然符合**该哲学、规格**纯 ADDED**。(ii) 自动触发**无可行判据**（见上两处订正）。(iii) E94 的缺口字面是
  「**无触发点**」，显式动词**正是**一个确定性、零 LLM 调用、零噪音的触发点。弱点：无人在场的长任务不自动提升 ——
  本仓对该场景的既定答案是「操作者 / 上层一次性配置」（E93 同模式）。
- **决策②：表征 = 每会话一条，`note_id` 确定性派生，覆盖式幂等。** `note_id = --as 或 f"session-{slug_topic(session_id)}"`
  ⇒ 同会话重复提升**必然命中同一条**、走**唯一写路径** `NoteStore.update()`（`store.py:104`）覆盖 ⇒ 不产生第二条、
  无界增长不可能；`--as` 为可选逃生口（**不**引入主题合并判据 —— 与既有「主题分裂优于错合并」取舍一致）。
- **决策③：提升即自动置常驻（`pinned=True`）。** 达成 E94 的原始目标「长任务硬约束**每轮在场**」（常驻 = 每轮
  无条件注入，承 ADR-0141）；受 `_MAX_PINNED_CHARS = 4000` 有界（token 有界，P5）。**⚠️ 密钥红线告示**：常驻正文
  每轮进模型上下文 ⇒ 因触发**显式**，操作者**须在提升前 review 摘要内容**，**绝不**提升含密钥 / 凭据的摘要。
- **决策④：提升写操作不接 `EffectTracker`。** 承 ADR-0099 / ADR-0141 —— notes 写面即**不入可逆效应面**；提升复用
  同一 `update()` 路径 ⇒ 与 `pin/unpin` / `observe_turn` **一致**；可逆性由 canonical 文件本身（重提升 / 编辑 /
  删除 + git）体现。
- **决策⑤：新增只读访问器 `MemoryStore.summary_for(session_id)` 而非复用 `audit(trace_id=...)` 的 id 约定。**
  委托私有 `_existing_summary`（`store.py:385`）⇒ 摘要 id 约定**单一真源**；零新状态、零写入、零效应；对比
  `audit` 后按 id 过滤会把 id 约定**复制到第二处**（`entry.py`），违单一真源；对比「新增通用 `get(entry_id)`」更窄（YAGNI）。
- **已知局限**：① **显式触发 ⇒ 无人在场的长任务仍不自动落 canonical** —— 与「刻意知识」哲学一致；**自动触发
  另立账**（若做，唯一可辩护形态是「只提升跨过 `_MAX_SUMMARY_CHARS` 截断边界的会话」+ 幂等覆盖 + 不自动 pin，
  但需 MODIFY 哲学条文 + 新增 loop 钩子）。② **自动置常驻** ⇒ 提升正文每轮进上下文；与既有常驻笔记**共享**
  `_MAX_PINNED_CHARS = 4000` 预算，多篇互相挤占、末篇可能截断（承 ADR-0141 局限②）；操作者须 review（红线）。
  ③ 提升写操作**不接** `EffectTracker`（承 ADR-0099）⇒ 无 `undo`。
- **规格**：`notes`（**ADDED** Requirement「会话摘要提升（promotion）」＋ 6 Scenario）；`memory`「记忆压实」
  （**MODIFIED**，新增只读访问器 `summary_for` 条款 ＋ Scenario「按会话读取既有摘要（只读）」）；接口面
  `03-interfaces/{memory,notes}-interface.md`、模块面 `02-modules/{memory,notes}.md`、测试面
  `04-testing/test-cases.md` §66、台账 `coding-plan/known-risk.md`。

---

## ADR-0143：笔记写入来源守护（change 0151 / 账本 E95）

- **背景**：`notes` 是**刻意文档化的权威真相层**（canonical Markdown，覆盖式「最新即权威」，ADR-0099）。
  但两条写路径**无条件覆写**目标主题、**不看主题由谁产生**：① **逐轮写回 `observe_turn`**（`store.py:191`）
  每成功轮把「`## 解决过程` + 步骤列表」覆盖式写回 `slug_topic(task)`，覆写时**只保留 `tags` / `pinned`**，
  `content` 与 `title` **全量替换** ⇒ 人工撰写 / promotion 产出的笔记只要 `note_id` 撞上任务 slug，正文即被
  **静默替换**；若该笔记 `pinned`，**标记保留、内容被换** ⇒ 此后每轮「任务级硬约束」块注入的就是步骤列表
  （E93 常驻语义被静默污染）。② **提升 `promote_session_summary`**（`promote.py:24`）无条件覆写派生
  `session-<slug>`、强制 `pinned=True`、改写 `source`，撞同 id 人工笔记**无守护、无提示**。这是**一条缺失的
  写入安全契约**，而非理论风险（①为真缺陷）。
- **决策①：来源守护 —— 一条主题只由产生它的那条写路径覆写。** 这是 `observe_turn` 既有「保留 `tags` /
  `pinned`」意图的**完成**（同一件事的延伸），**不是**新增语义。
- **决策②：`observe_turn` 撞外来源 ⇒ 改道派生主题，而非丢弃本轮沉淀。** 覆写前读既有笔记；若
  `existing.source != "notes.turn"` ⇒ **不改写该主题**，本轮沉淀落到首个**不冲突**的派生主题
  `<topic>-<n>`（`n` 为 2 起、取首个「不存在或来源为 `notes.turn`」者）。取舍：对比「返回 `None` 并留痕」，
  改道**既不覆写外来源正文、也不丢本轮沉淀**，且**有界**（同一派生主题后续轮次复用、覆盖式写回，不无谓
  增长）。来源为 `notes.turn`（或主题不存在）的既有行为**逐字不变**。
- **决策③：`promote` 撞非 `notes.promote` 来源 ⇒ 拒绝（除非显式 `--as`）。** 派生 id 撞车且未给 `--as`
  ⇒ **不写盘**、返回 `None`、CLI **非零退出**（复用既有「空 slug ⇒ `None` + 非零」口径，**不新增错误码**）。
  显式 `--as <note_id>` ⇒ 视为**显式授权**，照常覆写（不受守护约束）。取舍：对比「总是覆写」（原行为，
  静默毁人工笔记）与「总是拒绝」（`--as` 逃生口失效），**区分显式与派生**最贴合「误覆写要可见」。
- **已知局限**：① **仍无历史版本 / CAS / 三路合并** —— 来源守护堵住**跨来源**误覆写主因，但**同来源**
  自覆写仍是无历史的「最新即权威」（承 ADR-0099 局限③；回溯交给 git）。② **最小可回溯
  （`notes/.history/<id>/<ts>.md`）不做** —— 引入新目录 / 新生命周期面，留待另立账。③ `promote` 的撞车
  拒绝与「空 slug」**共用 `None` 返回** ⇒ 上层靠文案区分，未拆独立错误码（承「不新增错误码」）。
- **不推翻**「覆盖式（最新即权威）」契约 —— 只约束**跨来源**覆写；**不删除**任何笔记（承 memory 层
  「降权/归档而非删除」取向）；**不接** `EffectTracker`（承 ADR-0099）。
- **规格**：`notes`「Consult → Build → Update 循环纪律」（**MODIFIED**，追加来源守护条款 ＋ Scenario
  「逐轮写回不覆写外来源笔记（来源守护）」）；`notes`「会话摘要提升（promotion）」（**MODIFIED**，追加
  撞车拒绝条款 ＋ Scenario「撞非 promotion 来源 ⇒ 拒绝且不写盘（来源守护）」）；接口面
  `03-interfaces/notes-interface.md`、模块面 `02-modules/notes.md`、测试面 `04-testing/test-cases.md` §67、
  台账 `coding-plan/known-risk.md`。

---

## ADR-0144：loop token 记账覆盖全量装配（change 0152 / 账本 E96）

- **背景**：`DefaultLoop` 的预算闸门（`token_budget` → `TOKEN_BUDGET_EXCEEDED`，`default.py:311`）比的
  左值是**猜测值** `ctx.token_used`，而该值**只累加三样**：① 本轮 user 输入 `len // 4`（`perceive`）；
  ② 回灌历史 `_history_tokens`（逐条 `content` 取 `len // 4`）；③ 每步工具输出 `len(str(data)) // 4`
  （`observe`）。**完全不计** planner 装配的 **system prompt 全块**（宪法 / 常驻笔记 / 相关事实 /
  笔记 digest / 技能 / **工具 schema**，`planner.py:_system_prompt`）、助手 action JSON、observation
  JSON 包装。⇒ 记账的是**远小于真实提示词**的子集：固定前缀越大漏得越多；又 `len // 4` 对 **CJK
  约 4× 低估**（1 汉字 ≈ 1+ token 被算作 0.25）。合成后果 —— **闸门偏晚、甚至不触发**，真实风险是
  撞厂商 `context_length_exceeded` 400，而非优雅的 `TOKEN_BUDGET_EXCEEDED`。这是**记账口径缺陷**，
  非行为违约：规格只写「累计 token 消耗超过预算即终止」，**未**规定口径（故先改规格再改代码）。
- **决策①：记账 SHALL 覆盖装配进本轮提示词的全部内容** —— 回灌历史 + 本轮消息（含动作 / 观察
  回灌）+ planner 装配的系统提示与工具 schema。`perceive` / `observe` 统一经 `_context_tokens(ctx)`
  （口径同共享估计器 `context.estimate_tokens`，跨条累计、每条至少 1），**取代**原「本轮输入 + 历史
  + 每步 data」三处各算各的写法（`_history_tokens` 随之删除）。
- **决策②：provider 实报为下界、探针经 duck-typing 消费。** `LLMPlanner` 记录最近一次装配的观测并
  暴露 `last_prompt_tokens()`：取 `max(装配全量估算, usage.prompt_tokens)`（实测权威，只会抬升）；
  loop 侧经 `getattr(planner, "last_prompt_tokens", None)` 探针（与既有 `astream` 探针**同型**），
  最终记账 `max(_context_tokens, 探针值)`。取舍：对比「只估算」，实报数字**零成本可得**
  （`LLMResponse.usage` 本就已解析、此前**零消费**）且天然纠正 CJK 偏差；对比「引入三方 tokenizer」，
  本方案**零新依赖**（承「核心零三方运行时依赖」）。
- **决策③：探针缺失 / 异常 ⇒ 退化为纯估算，不阻断本轮。** 既有替身、`lambda` planner、缺省回显
  planner **零改动**（鸭子类型：探针不存在即视为无观测）。取舍：对比「要求 planner 必须实现探针」，
  后者会破坏全部既有 planner 注入面与测试替身。
- **不改**阈值语义（预算终止与压实同取 `token_budget`）与窗口派生规则（`context_window -
  output_reserve`，**ADR-0091 维持**）；**不改**共享估算器 `context.budget.estimate_tokens`（波及
  context 打包与转录切片，另议）；**不引**三方 tokenizer。
- **已知局限**：① **估算器仍是 `len // 4` 的粗略模型** —— provider 实报可纠正（有 usage 时），但
  流式响应 `LLMChunk` **不携带 usage** ⇒ 流式路径只能靠估算（另见 **E97**：窗口来源与动态获取）。
  ② **不改** `_should_compact` 的触发条件 —— 其轮数维度比的是 `ctx.rounds`（**工具步数**，上限
  `max_rounds`）而非对话轮数 ⇒ 「按轮触发压实」实践上基本不触发，唯一真触发仍是 token 阀（另议）。
  ③ **不改**「模型真实窗口的动态获取」（`llm.provider` 仍是死标签；E97 另立账）。
- **规格**：`loop`「错误与预算控制」（**MODIFIED**，追加记账口径条款 ＋ 2 Scenario「记账计入系统提示
  与工具 schema」/「provider 实报为记账下界」）；接口面 `03-interfaces/loop-interface.md`、模块面
  `02-modules/loop.md`、测试面 `04-testing/test-cases.md` §68、台账 `coding-plan/known-risk.md`。

---

## ADR-0145：会话摘要「首次越界」半自动提升（change 0153 / 记忆三面路线图 G3）

- **背景**：0150（ADR-0142 / E94）已给出**显式**提升路径（`notes promote <session-id>`），并把
  「由 loop 压实**自动**触发」**明文判为不做**（`notes` 规格 Scenario「不自动触发（设计裁决护栏）」）。
  ADR-0142 **局限①** 同时预登记了自动提升的**唯一可辩护形态**：只提升**跨过**滚动上界
  （`MAX_SUMMARY_CHARS`）的会话 + 幂等覆盖 + **不自动 pin**。本条即兑现该形态。
- **可辩护理由（信息论而非偏好）**：滚动合并投喂摘要器时**按 `MAX_SUMMARY_CHARS = 2000` 取前 2000
  字**（`summarize.build_prompt`）⇒ 摘要**一旦越过该上界**，下一轮滚合并即**丢弃**上界之外的既有
  结论 —— **信息正在被不可逆销毁**。此刻把**刚好完整的**摘要（首次越界那一版，尚未被稀释）交付上层
  落 canonical 真相层，是**止损**（canonical 层无自动清理、沉淀后只读、可回溯）。
- **决策①：触发面由「仅显式」扩为「显式 **或** 首次越界半自动」，判据与频次严格限定。** 仅当
  `MemoryStore._summarize_sessions` 发现某会话摘要**首次越过**上界（既有摘要长度 ≤ 上界「或该会话
  尚无既有摘要」而本次产出摘要长度 > 上界）时，于 `_commit_summary` **之后**把**本次产出的**摘要条目
  交付注入的提升钩子**一次**；**已越界**的会话**不再**交付（避免以已稀释的后继摘要覆写完整内容）。
  取舍：对比「跑一轮压实就自动写盘」，后者会放大覆写面积（0150 否决的正是它）；本方案把自动写盘
  面收窄到「信息正在被销毁」的**唯一时刻**。
- **决策②：`notes` 侧新增 `pin: bool = True` 形参，半自动路径传 `pin=False`。** 显式路径（CLI）
  缺省 `True` **逐字不变**；半自动产出是**普通** canonical 笔记（只经 Consult 命中面与 digest 注入），
  **不**自动置常驻、**不**占常驻预算、**不**以硬约束身份逐轮进场（承 ADR-0142 局限① 明文）。
- **决策③：memory 只报边界、notes 才落盘（零反向依赖）。** `MemoryStore` 新增可选注入
  `summary_promoter`（契约 `SummaryPromoter = Callable[[str, MemoryEntry], object]`，缺省 UNWIRED），
  **不 import** notes；组合根（`runtime`）构造闭包 `promote_session_summary(note_store, ..., pin=False)`
  注入。⇒ 依赖方向 `notes → core.memory` 维持（0150 既有）。上界常量由模块私有的
  `_MAX_SUMMARY_CHARS` **公开为 `MAX_SUMMARY_CHARS`**（现为 memory 与交付判据的**跨模块契约**）。
  钩子 UNWIRED（缺省）⇒ 不交付、行为**逐字不变**（既有约 60 处 `MemoryStore(...)` 调用点零改动）；
  钩子抛错 ⇒ **降级**（`warnings.warn` 留痕，不牵连压实的写回与迁移）；`session_id` 为空串 ⇒ 不交付。
- **不改**上界**数值**（2000）与节选**取前**方向（ADR-0140 的面）；**不**新增 `notes` 错误码、**不**接
  `EffectTracker`（承 ADR-0099 canonical 层取舍）；**不**引三方库 / LLM 调用。
- **已知局限**：① **判据依赖「既有摘要条目」的可见性** —— 若上层以别处（非 `compaction.summary.<sid>`）
  保存过摘要，越界判据可能错判；本仓摘要唯一写路径为 `_commit_summary`，故暂无该面。② **半自动产出
  不自动 pin** ⇒ 它**不**保证每轮在场，只作 canonical 沉淀与 Consult/digest 命中面（**有意**：见
  ADR-0142 局限①，避免自动提升的笔记以硬约束身份逐轮占据常驻预算）。③ **一次语义**意味着若首次越界
  的那版摘要**本身**已不完整（LLM 产出质量所致），canonical 层拿到的是那一版；后续更完整的摘要
  **不会**回填（避免以稀释版覆写）—— 返工需**显式** `notes promote`（人工判断）。
- **规格**：`memory`「记忆压实」（**MODIFIED**，追加上界可见性 + 提升钩子条款 ＋ 3 Scenario）、
  `notes`「会话摘要提升（promotion）」（**MODIFIED**，触发面扩 + `pin` 分路径 +
  Scenario「不自动触发（设计裁决护栏）」判据细化 + 2 新 Scenario）；接口面
  `03-interfaces/memory-interface.md` / `03-interfaces/notes-interface.md`、模块面
  `02-modules/memory.md` / `02-modules/notes.md`、测试面 `04-testing/test-cases.md` §69、
  台账 `coding-plan/known-risk.md`。

---

## ADR-0146：常驻笔记预算 —— 显式优先级 + 整篇纳入 + 超限可见（change 0154 / 记忆三面路线图 G1）

- **背景**：0149（ADR-0141 / E93）给了**常驻（pinned）笔记**（任务级硬约束锚，每轮无条件注入），
  但其**局限②** 自认「总量有界于 `_MAX_PINNED_CHARS`(4000) 但**无 per-note 上限** —— 多篇各自很长时
  **末篇可能被截断**」。现状 `pinned_digest()` 是「按 `note_id` 升序拼接后 `[:4000]` **字符切片**」，
  两个缺陷都落在**硬约束**语义上放大：① **半篇** —— 切片可把某篇**从中间切断**，半截硬约束可能
  **语义反转**（「必须 A，除非 B」被切成「必须 A」），比缺席更危险；且被切的是**哪一篇**由
  `note_id` 字典序决定（`zzz-*` 被系统性饿死、`aaa-*` 恒在场）。② **静默** —— 谁没进场、谁被切半，
  无留痕、无 CLI 可见面 ⇒ 操作者以为约束在生效。
- **决策①：在场判据改为**显式优先级**（操作者的决定，不踩 `note_id` 字典序）。** `NoteEntry` 新增
  `pin_priority: int = 0`；canonical 行 `- pin_priority: <n>` **仅非 0 时输出**（仿 0149 的 `pinned`
  行先例 ⇒ 既有文件渲染输出**逐字不变**，`render_note`/`parse_note` 仍互为逆）；`parse_note`
  **解析失败 ⇒ 0**（fail-closed：手误**绝不**意外抬到高优先级）。`pinned()` 次序由 `note_id` 升序
  改为 **`pin_priority` 降序、同优先级 `note_id` 升序**（仍**确定性**）。
- **决策②：装配改为**整篇纳入**，绝不半篇。** `_assemble_pinned()` 按次序整篇纳入，任一篇整篇放不下
  即**整篇排除**且其后各篇**不再尝试**（在场集合 = 优先级次序的**前缀**；低优先级不得越过被排除者
  挤入 —— 否则「优先级决定在场」被破坏）。**唯一例外**：次序**首篇**即便自身超预算**仍整篇纳入**
  —— 常驻块 SHALL NOT 因单篇超限而**整体为空**（硬约束全灭比超预算更糟）。空正文常驻笔记**预先滤除**：
  既不占块、也**不计**未进场。
- **决策③：超限**可见**（不静默）。** `pinned_digest()` 在**注入块超预算**时（发生排除，或单篇超限
  致块超上界）经 `warnings.warn` 留痕（列出未进场 id；无整篇可排除时明示单篇超限）；新增**只读**
  访问器 `pinned_overflow() -> list[str]`（次序同 `pinned()`；首篇超限者**不在其列**，它在场）；
  CLI 新增 `notes pinned` 报出「在场 / 未进场」，`notes pin <id> [--priority N]` 设优先级。
  `notes list` 输出**逐字不变**（未进场篇目的报出面是 `notes pinned`）。
- **`set_pinned(note_id, *, pinned=True, priority=0)`**：幂等判据由「`pinned` 未变」扩为「`pinned` 与
  `priority` **皆**未变」（同值 ⇒ 不写盘、不 bump `updated_at`）；**清常驻同时归零优先级**（退出常驻面
  即不再有优先级）；逐轮写回（`observe_turn`）SHALL NOT 抹除 `pinned` 与 `pin_priority`。
- **不改** `_MAX_PINNED_CHARS` 数值（4000）；**不**在 pin 时**拒绝**超预算置位（超限是**告警 + 可见**，
  非硬失败）；**不**新增 `notes` 错误码、**不**接 `EffectTracker`（承 ADR-0099 canonical 层取舍）；
  **不**引三方库。
- **已知局限**：① **单篇自身超上界时块可超上界**（首篇例外，**有意**：保硬约束不空）—— 该情形**有
  留痕**但**仍超预算**，缓解靠操作者拆小常驻笔记。② **`pin_priority` 与 `pinned` 正交** ⇒ 手工把
  `- pin_priority: N` 写进一篇**未**常驻的笔记不产生任何效果（`pinned()` 先滤 `pinned`），但该行会被
  原样保留、`notes pinned` 不显示（它只列常驻）。③ **无 per-note 上限**：一篇很长的常驻笔记（未自超
  上界但很大）会吃掉大半预算、把后续低优先级篇整批挤出 —— 这是**优先级语义的正确后果**，且**有留痕**。
  ④ **同优先级仍回落到 `note_id` 字典序**打破平局 —— 仅是**平局**的确定性 tie-break，不再决定
  「谁在场」（差异化由显式优先级承担）。
- **规格**：`notes`「常驻（pinned）笔记（任务级硬约束锚）」（**MODIFIED**，追加 `pin_priority` /
  优先级次序 / 整篇纳入 / 超限可见条款 ＋ 4 新 Scenario，**保留**全部 5 个既有场景名）；接口面
  `03-interfaces/notes-interface.md`、模块面 `02-modules/notes.md`、测试面
  `04-testing/test-cases.md` §70、台账 `coding-plan/known-risk.md`。

## ADR-0147：结构化关键事实抽取 —— 密钥引用式 + fail-closed 脱敏（change 0155 / 记忆三面路线图 G4）

- **背景**：账本 **E92** —— 外部参考件 `Agent-Memory.md` 的 M4「结构化信息并行抽取」提出四类实体
  Schema（`user_preferences` / `project_constraints` / `completed_tasks` / `key_facts`），本仓只有
  `MemoryEntry.kind ∈ {episodic, semantic}` + `tags`。**落地红线**：参考示例把**密钥明文**写进长期记忆
  （`Agent-Memory.md:35` `"value": "sk-xxxxxxxxx"`），与本仓红线「**密钥只引用不读取、绝不进日志/记忆**」
  **直接冲突** ⇒ 本 change 的中心不是覆盖面，而是**把该红线做成真代码**。
- **决策①：实体归属 —— 四类里只取 `key_facts`（用户拍板）。** 其余三类**各有既有归属**，不重复建面：
  `project_constraints` → `notes` 常驻笔记（**操作者显式**置的任务级硬约束锚，ADR-0146）；
  `completed_tasks` → `notes.observe_turn`（任务后写回主题文档，ADR-0143）；`user_preferences` →
  L0 Core Profile（用户**自述**人格）。⇒ 本能力只补「**自动抽取的、可检索的关键事实**」这一维。
- **决策②：注入面与既有接缝同构。** `MemoryStore(key_fact_extractor=...)`，契约
  `KeyFactExtractor = Callable[[list[MemoryEntry]], list[KeyFact]]`（缺省 UNWIRED）；新增
  `core/memory/extract.py`（`KeyFact` 数据类 + `build_extract_prompt` / `parse_key_facts` /
  `extract_with(llm)`），照 `summarize.summarize_with` 先例 —— **memory 不 import 任何 LLM / rag 抽象**，
  模型调用由 L5 组合根注入（`runtime` 复用同一 `_llm_text` 接缝）。**抽取与摘要各自独立**：`compact`
  的会话循环在「摘要器**或**抽取器」注入时运行，两者互不依赖。
- **决策③：信任边界在 store，不在注入方。** 脱敏由 memory 侧在**落库前**对抽取器的**每一条**结果
  **无条件**执行（`_plan_key_facts`：先**整批**归一化，任一失败 ⇒ **整批不写**、不留半批）。
  组合根注入的抽取器**不构成**信任边界 —— 「靠 prompt 让模型别写密钥」是**不可审计**的保证。
- **决策④：脱敏方向恒为 over-redact，fail-closed。** `value` 命中密钥形态（已知令牌前缀族 / 私钥块 /
  JWT / `key[:=]value` 赋值式 / 长随机串兜底）⇒ **强制** `<redacted>`；给出 `ref`（形如
  `coeffect:<名称>`）⇒ `value` **一律** `<redacted>`（有引用即不留明文，即便原值看似正常）；
  **裸密钥无可用引用 ⇒ 整条丢弃**（「记不住引用就不记」）并 `warnings.warn` 留痕（**含实体名、
  不含取值**）。**先脱敏后截断**（截断不得使明文逃逸）；单次条数有界
  `MAX_KEY_FACTS_PER_COMPACT`(8)，`entity` / `value` 长度有界 `_MAX_FACT_CHARS`(200)。
- **决策⑤：落库形态与可撤销。** `id="keyfact.<实体 slug>"`（**同实体至多一条**、覆盖式更新、条目不增长）、
  `kind="semantic"`、`source="extraction"`、`trace_id="compaction.<sid>"`（**与压实同 trace** ⇒ 按该
  trace 回滚即与摘要、迁移**一并**逆转）、`tags=["key_fact","entity:<slug>",("ref:…")?,("session:<sid>")?]`。
  **条目属全局层**（`session_id` 置空、**不**参与会话隔离 —— 实体事实是**跨会话**长期知识），产生它的
  会话只作 `tags` 溯源标注（承 notes「刻意知识不参与会话隔离」取向）。
- **不改** `read` / 排名 / 预算 / 压缩口径；**不加** CLI（关键事实是普通 semantic 条目，经既有 `read` /
  `audit` 可见，`memory maintain` 即触发面）；**不做**输入侧（episodic 事件文本）的密钥过滤 —— 该面承
  既有摘要路径同口径，**不在本 change 扩面**；**不引**三方库（仅 `re` / `json`）。
- **已知局限**：① **脱敏是启发式**（前缀族 + 长随机串 + 赋值式），**不能保证**穷尽未知密钥格式 ⇒ 方向取
  over-redact 缓解，但**非**形式化保证；② **误伤**：正常长标识符（长哈希 id、长 base64 片段）可能被
  脱敏 ⇒ 可接受（安全侧）；③ **抽取质量**取决于注入的模型与 prompt，`parse_key_facts` **不可解析即不抽取**
  （宁缺勿滥）；④ **输入侧仍会把事件文本送给模型**（摘要 / 抽取共用）⇒ 若对话里出现密钥，其**明文仍进入
  LLM 请求**（既有面，本 change **未**扩面也**未**收口）；⑤ 关键事实**跨会话可见**是**有意**语义
  （长期知识），但**不**参与遗忘的 `session_id` 归组 ⇒ 其生命周期由 L4 层与手工维护承担。
- **规格**：`memory` **ADDED**「结构化实体抽取（关键事实）」；接口面
  `03-interfaces/memory-interface.md` §3、模块面 `02-modules/memory.md`、测试面
  `04-testing/test-cases.md` §71、台账 `coding-plan/known-risk.md`（**E92 已修**）。

## ADR-0148：记忆三面职责边界 —— rag 定位「辅助本地知识库，不注入主链路」（change 0156 / 记忆三面路线图 G5）

- **背景**：记忆三面（`memory` / `notes` / `rag`）职责重划的**最后一站 G5**。用户裁决倾向（原始三问之③）：
  「长期记忆重要信息走 **Notes**，**rag 做辅助 + 本地知识库查询**」。**现状即答案** —— rag 已是辅助本地
  知识库（CLI `rag ingest|search|ask` **一次性**驱动）、**不**注入 loop（ADR-0097 ⑥）、**不**做结构化
  实体抽取（该面已由 change `0155` 归 **memory**）。缺的是把**三面边界 + 不注入主链路**写成**单一目视
  可达、且可守护**的定位。
- **决策①：三面职责边界（各归其位、互不重叠）。** `memory` = **经验轨迹**（L2 episodic/semantic，自动
  压实/固化/遗忘）＋ **关键事实**（`key_facts` 结构实体，跨会话，change `0155`）；`notes` = **主题文档**
  （canonical Markdown 真相层，Consult/常驻注入）；**`rag`** = **外部知识文档**（分块 + 向量，按需 top-k，
  按内容哈希增量重建）。三面**互不越界**：memory 不做知识文档语义检索、rag 不做经验记忆与实体抽取。
- **决策②：rag 定位为辅助按需，不注入 loop 主链路（承 ADR-0097 ⑥，并把它从「ADR 决策内一条」升为
  「文档定位 + 可执行守护」）。** 主链路与三面兄弟（`loop` / `context` / `memory` / `notes`）**不得**
  `import core.rag`；`core.rag` 仅由**组合根**（`runtime` 装配 `runtime.rag`）与 **CLI**（`entry` 的
  `rag` 命令族）引用。守护：`tests/test_architecture.py::test_rag_not_imported_by_reference_chain`
  （沿既有 Phase 边界守护同构，stdlib `ast`、零三方依赖 ⇒ 把定位由**散文**固化为**可执行不变量**）。
- **决策③：门槛钉死。** 若要令 RAG **参与 loop 上下文**（占固定窗口 / 进系统提示装配）⇒ **须先改
  ADR-0097 ⑥** —— 那是**特性**（牵动 context 预算与 prompt 装配），**不是**本定位的自然延伸；跨门槛
  须经「**改 ADR → 开规格变更**」，**不得**以「主链路直接 `import rag`」绕过（守护即为此设）。
- **不改** rag 既有裁决（`HashEmbedder` 离线降级基线 / 不引本地语义模型 / 暴力余弦不换 ANN —— 承
  `rag-offline-embedder-decision` 与 ADR-0097）；**不改**任何规格行为（**规格中性**：`.openspec.yaml`
  `spec-driven + skip_specs: true`）；**不加** rag 代码 / CLI / 行为（**零 `src/` 改动**）。
- **已知局限**：① **守护只覆盖「直接 import」** —— 若以**间接**路径（共享工具模块转发、动态 `importlib`）
  令主链路触及 rag，守护不察（**刻意**：抓最常见的直连退化，非形式化隔离）；② **定位另一侧无守护** ——
  `memory` / `notes` 是否越界「兼做知识文档检索」无自动门禁（只护 rag 一侧）；③ **门槛靠人守** ——
  ADR-0097 ⑥ 的修改本身是人的动作、无自动门禁；④ **三面边界表是「当前」分工** —— 若某一面未来扩能
  （memory 加向量 / notes 加实体），须**同步更新**本 ADR 与三处文档。
- **规格**：**无**（规格中性，`skip_specs: true`）；文档面 `11-rag/rag-architecture.md` §1.1、
  `02-modules/rag.md` §1.1、`03-interfaces/rag-interface.md` §0、测试面 `04-testing/test-cases.md`
  §19（TC-RAG-14）、守护 `tests/test_architecture.py`、台账 `coding-plan/known-risk.md`（§3）。

### ADR-0148 附记（change `0189` / 台账 E126）：**另一侧**门禁 —— memory / notes 不得兼做知识文档检索

- **补（本 ADR 局限② 收口）**：局限②「定位另一侧无守护」由 `tests/test_architecture.py::
  test_memory_notes_api_excludes_document_corpus_dimension` 补上 —— `memory` / `notes` 的**公开面**
  （公开函数 / 方法 / 类名 ＋ 形参名）经 stdlib `ast` 走查后，**不得**出现「外部文档语料」词元
  （`document(s)` / `doc(s)` / `chunk(s)` / `corpus` / `ingest` / `pdf` / `retrieve` / `rag`；
  `snake_case` / `camelCase` 均切分）—— 知识文档检索面归 `rag`（本 ADR 决策①）。另以
  `test_rag_guard_chain_covers_corpus_free_faces` 钉住「两面仍在决策② 的守护链 `_REFERENCE_CHAIN`
  内」：否则摘掉一个面即可让两侧守护**同时**失效。
- **局限收窄**：② ⇒ 收窄为「**间接路径**（共享工具转发 / 动态 `importlib`）与**非公开面**（局部变量 /
  私有名）不察」；③ ⇒ 由「门槛靠人守」改为「**门槛靠人守 ＋ 一条最小机器绊线**」—— 越界的**直接退化**
  必触门禁，指向决策③（**先改 ADR、再开规格变更**）。①④ 逐字不变。
- **刻意不收录 `vector` / `embed`**：`memory` 的语义记忆面**合法**使用嵌入（`_vectors` 缓存 /
  `HashEmbedder` / `LLMEmbedder`），那**不是**「外部文档语料」维度；收录会把既有合法面判红
  （见 change `0189` design.md D3）。**不重复**既有两条守护（决策② 的 rag 侧守护 ＋
  `tests/test_session_isolation.py::test_notes_api_has_no_session_dimension` 的会话维度侧）。
- **规格**：**无**（规格中性，`skip_specs: true`）；**零 `src/` 改动**。改动面
  `tests/test_architecture.py`、`04-testing/test-cases.md` §102、`coding-plan/known-risk.md`
  （§1 `E126` 已闭 ＋ §3）。

## ADR-0149：TUI 续聊转录按 Markdown 渲染（change 0157 / 账本 E98）

- **背景**：用户 2026-10-07 实测 —— TUI（`core-agent` 直接跑）里 agent 输出带代码围栏的 demo，
  「回显依然是正常明文逐行输出」。根因：`src/core/ui/repl.py` 有**两条**渲染 agent 回复的路径，
  **只有实时流式**那条以 Markdown 呈现 —— ① 实时（`_show_delta` → `_flush_tail` → `_freeze_tail`，
  尾段**始终** `Markdown` widget ⇒ 围栏成代码块、表格成表格，E88/E89 已修）；② 续聊载入既有转录
  （`on_mount`，`repl.py:391-400`）把 agent 回复喂给 `Static(..., markup=False)` ⇒ **纯文本逐行**，
  围栏退化为字面 ` ``` `。**同一回复换个入口进来就变样**。
- **决策①：单一渲染口径 —— 「agent 回复」以 Markdown 渲染，与入口无关。** 续聊铺入分支的 agent 回复
  改挂 `Markdown(...)`（与实时路径**同一** widget 类、同一格式），SHALL NOT 降级为 `Static` 明文。
  规范面：`ui` spec「CLI 友好交互」由「渲染格式（仅流式）」扩为「**流式 ∨ 续聊载入**同格式」
  （MODIFIED + 1 Scenario）。这是**同一 Requirement 的漏面**补齐，非新特性。
- **决策②：用户消息回显**保持既有 `❯` 前缀行（`Static` + `markup=True` 逐字转义）—— 单行前缀非
  Markdown 面，不改。**既有转录内容** SHALL NOT 被改写，仅**呈现格式**与实时路径对齐；加载语义
  （复用既有会话 / 未登记 fail-closed）**不动**。
- **决策③：不动实时流式路径。** `_show_delta` / `_flush_tail` / `_in_open_fence` / `_in_open_table` /
  合帧节流**零触碰** —— 它已正确；本 change 只修**第二条入口**。
- **已知局限**：① **Web / Desktop SPA 仍无 Markdown 渲染**（`frontend/src/views/Chat.svelte` 纯文本，
  `<li>` + `white-space: pre-wrap`）—— 属**另一端**（承 E88 局限②），若要做须另开 change（牵动前端
  依赖面）；② **续聊回放按「每条历史回复一个 `Markdown` widget」挂载** —— 长会话挂载数随历史条数线性
  增长（与实时路径「每固化段一块」**同量级**，**未新增**渲染机制）；若未来有体量问题，属续聊**加载面**
  另议；③ **无跨端一致性门禁** —— 本 change 只护 TUI 一侧，「续聊回放的格式与实时一致」由**同 widget
  类**的**构造**保证，无自动断言跨端比对。
- **规格**：`ui`「CLI 友好交互」**MODIFIED**（+ 1 Scenario）；文档面 `03-interfaces/ui-interface.md` §2、
  测试面 `04-testing/test-cases.md` §72（TC-RESUMEMD）、台账 `coding-plan/known-risk.md`（§1 E98 / §3）。

## ADR-0150：TUI 代码块背景可辨识（change 0158 / 账本 E98 后续）

- **背景**：用户 2026-10-07 续报（承 change 0157）—— 「是颜色没有变化，和主框颜色没差异，无法识别」。
  change 0157 解决的是**格式面**（续聊入口退化为明文，走回 `Markdown`），本缺陷在**视觉面**：
  Textual `MarkdownFence` 默认样式为 `background: black 10%`（半透明黑），本仓 TUI 为**深色**主题
  （`core`，`dark=True`、`ansi=False`）⇒ 主背景 `#121212` 上叠加合成为 `#101010`，
  **WCAG 相对亮度对比度 ≈ 1.02** ⇒ 块的**边界不存在**。字色 `rgb(210,210,210)` 只管文字、不产生背景区隔。
  ⇒ 「围栏渲染为代码块」在**语法层**成立（0157 已保证），在**视觉层**不成立 —— 等同没渲染。
- **决策①：规格补「可辨识」为硬约束，而非只要求「渲染为代码块」。** `ui`「CLI 友好交互」
  **MODIFIED**：代码块背景 SHALL **不透明**、且与 TUI 主背景的 **WCAG 相对亮度对比度 SHALL ≥ 2.0**；
  深色主题下 SHALL NOT 以**近透明**深色叠加充数。该条款正是本缺陷长期存在的原因 ——
  「渲染对了但看不见」此前无 SHALL 兜底（渲染面与视觉面在规格里被混为一谈）。
- **决策②：取 `$surface-lighten-3`（本主题解析为中性灰 `#4F4F4F`，与 `#121212` 对比度 ≈ 2.3），
  而非「真浅灰」。** 理由：语法高亮 token 色由 `HighlightTheme` 的**主题变量**给出
  （`$text-primary` / `$text-accent` / `$text-warning` / `$text-success` / `$text-secondary`，
  本主题均解析为**亮色** `#E5A590` 系），且 token span 会**覆盖**基色 `color` ⇒ 浅底 + 亮字**不可读**；
  若真上浅底，必须**先改主题** `$text-*` 变量面（波及全部用 `$text-*` 的控件）——另议，本 change 不做。
  在「可辨识」与「不牺牲高亮」之间取**深灰**为最大公约数。
- **决策③：纯样式改动，落在 `ReplApp.CSS` 一处。** 不改渲染路径（0157 已统一两条入口为 `Markdown`）、
  不改主题、不改表格样式、不引三方库。app 级 CSS 与 widget `DEFAULT_CSS` **特异性相同** ⇒ 后者（app）胜出，
  这是 Textual 的既定级联规则，非侥幸。
- **已知局限**：① **深灰在部分操作者眼里仍偏暗**（若期望「浅灰」），颜色集中于一条规则、一行可调
  （`$surface-lighten-3` → 更亮 token 或显式色值）；② **对比度门禁按 `$background` 计算** ——
  若主题背景色改暗/改亮，阈值需重估（测试会先红，属**有意**的护栏）；③ **未覆盖 `:ansi` 分支**
  —— `MarkdownFence:ansi { background: transparent; }` 存在，但本主题 `ansi=False` ⇒ `:ansi` **不匹配**；
  若未来启用 ANSI 主题，本条 SHALL 重新评（测试按解析后的样式断言，届时会红）；④ **未做跨端一致性** ——
  Web / Desktop SPA 的代码块视觉属另一端（承 ADR-0149 局限① / E88 局限②）。
- **规格**：`ui`「CLI 友好交互」**MODIFIED**（+ 1 Scenario）；文档面 `03-interfaces/ui-interface.md` §2、
  测试面 `04-testing/test-cases.md` §73（TC-CODEBG）、台账 `coding-plan/known-risk.md`（§1 E98 / §3）。

## ADR-0151：TUI 斜杠命令浮层与补全 —— 单一真源 + 呈现层只管补全（change 0159）

- **背景**：用户 2026-10-07 报「TUI 启动后输入 `/` **没有任何提示**」—— 命令全靠记忆，无发现性。
  期望对齐 Claude Code：`/` 弹命令清单、键盘选择；带参数的命令再弹**二级**清单（如 `/focus` 列子任务标识）；
  并要**内联幽灵补全**。根因：TUI 斜杠命令**全部硬编码**在 `ReplApp.on_input_submitted` 的分支链里
  （`/task` `/focus` `/main` `/summon` `/recall`），**无命令注册表** ⇒ 既无可枚举清单，也无「单一真源」可言。
- **决策①：命令清单收敛为**单一真源**（模块级 `_COMMANDS` + `_Command`），浮层据此呈现。**
  真源与分发的**绑定靠可执行守护**：`test_registry_commands_are_all_dispatchable` 逐条驱动规范形态，
  断言**无一落进普通对话** ⇒ 任一条「只登记、未接线」（如尚未进表的 `/resume`）即红。
  **不改**分发链的结构与提示串（那会改到多处以断言逐字为准的行）—— 真源管**清单**，分发管**行为**，各司其职。
- **决策②：浮层是**纯呈现层** —— 采纳只改写输入框，SHALL NOT 提交、SHALL NOT 改语义。**
  `_accept_palette_selection` 的采纳判据是「高亮项是当前输入的**严格前缀延伸**」（`fill != value and
  fill.startswith(value)`）；不满足（无高亮 / 文本相同 / 非前缀）即返回 False，回车按**既有**分发链继续
  ⇒ 完整命令（`/main`）、未知前缀（`/zzz`）、普通消息、`/focus` 的**忙态豁免**、审批 y/n 语义**逐字不变**。
  **唯一的**有意行为变更：输入是命令的**严格前缀**（如 `/ta`）且按 Enter ⇒ 补全为 `/task `（不提交）；
  这是本需求的**目标面**，已在规格写明。
- **决策③：`on_key` 接管 `↑`/`↓`/`Tab`/`Esc`，且**仅在浮层呈现时**。** 实测（承重，勿凭直觉）：
  `Tab` **不是空键** —— App 默认「焦点后移」会把它从输入框带走，且声明 `BINDINGS` **无效**
  （默认焦点后移仍胜出），只有 `on_key` + `event.prevent_default()` 才扣得下；故浮层另以
  `class _PaletteList(OptionList, can_focus=False)` 作**双保险**（即便漏掉某分支，`Tab` 也进不去浮层）。
  `Enter` **只在一处处理**（`on_key` 与 `Input.Submitted` **同触**，两处都写会**重复执行**）⇒ 采纳落在
  `on_input_submitted`，`on_key` 对 `Enter` 显式放行。浮层关闭时**一律放行** ⇒ 既有按键行为逐字不变。
- **决策④：不引 `Screen`/`ModalScreen`/`layers`/`push_screen`，沿仓库既有 `display` 翻转惯用法**
  （`_set_focus` 对 `#panel`/`#timeline` 的做法）；`#palette` 默认 `display: none`，候选非空时翻转。
  **零新增 api**：二级清单的参数候选取**既有** `self._open` 的键（在途子任务标识），SHALL NOT 新建第二数据源。
- **决策⑤：幽灵补全与浮层候选**同源**（复用同一 `_candidates` 取口）。** 语料随上下文变化
  （子任务标识会增长）⇒ `use_cache=False`；候选区分大小写（默认 casefold 会与 `Input` 按长度切取的
  幽灵文本**错位**）⇒ `case_sensitive=True`。`→` 由 `Input` **原生**采纳，无需另接。
- **已知局限**：① **仅前缀匹配**（无子串/模糊）；② **无鼠标选择**（键盘驱动，`action_select` 未用）；
  ③ **`/summon` `/recall` 无二级**（参数在 TUI 无可枚举且零新增 API 的来源）；④ **无「无匹配」占位**
  （无候选即收起浮层）；⑤ **`Tab` 在浮层**关闭**时仍走 App 默认焦点后移**（既有行为，本 change 未改）；
  ⑥ **未覆盖 Web / Desktop**（斜杠命令浮层属 TUI 端）；⑦ **不做命令历史**（`↑` 调上一条输入，另议）。
- **规格**：`ui`「CLI 友好交互」**MODIFIED**（+ 6 Scenario，既有 7 Scenario 措辞逐字不改）；
  文档面 `03-interfaces/ui-interface.md` §2、测试面 `04-testing/test-cases.md` §74（TC-CMDPAL）、
  台账 `coding-plan/known-risk.md` §3。

## ADR-0152：TUI 会话切换 —— 运行中切会话 + 与启动续聊同一铺入路径（change 0160）

- **背景**：承 0159（用户同一诉求「`/resume` 选会话 → 还原内容」；0159 只做浮层，`/resume` 刻意未进真源
  —— 登记而不接线会被 0159 的**单一真源可执行守护**判红）。今日 TUI 的会话**只能由启动旗标
  `--session <id>` 选定**：运行中无从切换，操作者事先也无从得知有哪些标识可用
  （`UIAPILayer.list_sessions()` 数据已就绪，TUI 未消费）。
- **决策①：`session_id` 由闭包变量改为实例字段。** 原为 `build_app(api, session_id)` 的闭包变量，
  在 `_run_turn` / `_run_task_turn` **两处按轮**读取。构造时经 `ReplApp(session_id, history)` 注入，
  切换即改 `self._session_id`。**代价**：`__init__` 不再无形参（既有测试只经 `build_app` 构造，零影响）。
- **决策②：切换与启动续聊**共用**同一条铺入路径**（`_replay_history`，自 `on_mount` 提出）。
  理由：0157/ADR-0149 刚把「回复从哪条入口进来都得同格式」立成硬约束 —— 若切换另写一份铺入循环，
  该约束立刻出现**第二个**可能漂移的实现点。用户消息 `❯` 回显、agent 回复走 `Markdown` 的口径因此
  只有一处。
- **决策③：先验证、后落地（fail-closed 的关键形态）。** 若「先清时间线、后读转录」，读取失败就会留下
  **空时间线 + 旧会话**的半切换态 —— 用户以为切过去了，实际没有。故 `api.session_messages(sid)`
  （未登记即 `UiError`）**先于任何状态改动**调用；失败则时间线 / 标识 / 呈现态**逐字不变**，仅落一行错误。
- **决策④：切换排在忙态检查**之后**、回主视图与回显**之前**。** 前者：切换与在途轮次并发会改写
  `self._session_id` 与时间线（在途轮的回复将落进被清空的时间线）⇒ 与既有「忙态拒绝新消息」同口径。
  后者：切换不产生 `❯ /resume <id>` 回显（回显会落进**刚被清空**的时间线，语义混乱）；切换的落痕是
  `↻ 续接会话 <id>（N 条历史已载入）`（与启动续聊同一行文）。
- **决策⑤：会话候选取既有 `list_sessions()`，且只在**需要它**时取。** `_Command.arg_source`（真源字段）
  分派二级候选来源：`subtask` ⇒ `self._open` 键；`session` ⇒ `list_sessions()`（显示行 = 标题 · 标识 ·
  更新时间）。`_candidates` **按真源字段**而非命令名字面量判定是否读会话面 ⇒ 键入 `/ta` 之类的每一击
  都不会去读会话面。会话候选按**显示行前缀**（大小写不敏感）或**标识前缀**（逐字）收窄 —— 标题可读、
  标识可粘。
- **已知局限**：① **只切既有会话**（不新建 / 不删除 / 不重命名）；② **切换即清时间线**（含启动欢迎行，
  历史滚动位置不保留，`Ctrl+Q` 式回看须再切回）；③ **不做每会话视图隔离**（`_open` / `_actions` 等
  呈现态是**全局单份**，切走即清 —— 切回原会话不恢复其折叠块展开状态，只按转录重铺）；
  ④ **会话无上限裁剪**（`list_sessions()` 全量列出，长清单靠前缀收窄）；⑤ **未改 Web / Desktop**
  （承 ADR-0151 局限⑥，跨端一致属另一端）；⑥ **更新时间为本地时区分钟粒度**（`%m-%d %H:%M`，
  跨时区阅读有歧义）；⑦ **不做「切换即续跑」**（切到有在途任务的会话不会恢复其编排视图）。
- **规格**：`ui` **ADDED** Requirement「TUI 会话切换（`/resume`）」+ 4 Scenario（切换并还原 /
  未登记 fail-closed / 无参数只提示 / 忙碌拒绝）；文档面 `03-interfaces/ui-interface.md` §2、
  测试面 `04-testing/test-cases.md` §75（TC-RESUME）、台账 `coding-plan/known-risk.md` §3。

## ADR-0153：只读诊断源 —— `doctor` / `status` 实现追上规格（change 0162）

- **背景**：`cli-ops` 规格的「状态查询命令」Scenario 早已承诺 `status` / `doctor` **返回运行状态 /
  健康诊断**（`doc/openspec/specs/cli-ops/spec.md:20`），实现却是桩 —— `cli_ops/dispatcher.py:87-93`
  对二者一律 `return "ok"`。今天 `core-agent doctor` 对**任何**环境都打印 `ok`：既无诊断价值，也不能
  当退出码判据用。用户 2026-10-07 诉求「TUI `/` 浮层要能执行 doctor / status 等只读命令」**以本
  change 为数据底座**（浮层命令要落真东西，先得有只读诊断源）。
- **决策①：单独立只读诊断包 `core/diagnostics`，一切句柄**依赖注入**。** 包内**不猜路径**、**不 import
  `core.runtime`**（`test_architecture.py::test_runtime_is_sole_composition_root` 是硬红线）、**不 import
  `core.ui`**（`ui` 将反向引用它，避免环）。`Deps` 是**纯数据**（全部可选句柄），由调用方装配：
  CLI 经 `entry._diag_deps`，TUI 后续经 `UIAPILayer`（0163）。理由：诊断若自建 runtime 就会成为**第二个
  组合根**，与 P1「无特权核心」和既有组合根单一性直接冲突。
- **决策②：配置检查复用既有 `ValidationResult`，不自建第二套。** `ConfigManager.validate_schema`
  已产出 `ValidationResult(ok, errors, warnings)`（`configuration/models.py:87-93`）—— 诊断把它**映射**成
  `Check` 项。理由：校验口径只能有一处；自建会立刻漂移（与 ADR-0149「同格式只有一处实现」同源纪律）。
- **决策③：单一产出、多消费面。** `collect_doctor` / `collect_status` 产 `Report`，`render` 产行；
  CLI 今天打印，TUI（0163）复用同一份 —— SHALL NOT 各写一份检查逻辑（写进规格）。
- **决策④：`doctor` 退出码由「恒 0」改为「有 `fail` 项即非零」。** 诊断命令的价值就在**判据**；
  恒 0 等于没有诊断。**代价**：若有外部脚本依赖 `core-agent doctor` 恒 0，需适配 —— 此为**有意**变更，
  规格已写明「存在 fail 项 ⇒ 退出码非零」。`status` 仍恒 0（概览是信息面，不是判据）。
- **决策⑤：密钥面只出「引用名 + 布尔结论」。** 诊断项**只**经 `ConfigManager._resolvable(ref) -> bool`
  （`manager.py:402`，**只返回 bool、不返回明文**）与 `${VAR}` 引用名呈现；**SHALL NOT** 打印解析结果。
  列表视图同理收紧：MCP 端点**不打印 `EndpointRecord.args`**（`mcp/endpoints.py:53-65`，其 `args` 可能是
  `--token <value>` 形态）—— 只出 name / transport / source。理由：红线「密钥只引用不读取、绝不进日志/记忆」
  在诊断面上同样成立，而「把配置打印出来看看」是最容易破线的一种实现。
- **决策⑥：不动 `cli_ops/dispatcher.py`。** 其 `status()` 的 `"ok"` 分支自此不再被 CLI 触达，但它与
  `cli-ops-interface.md`、`tests/test_cli_ops.py` 仍是既有面 —— 删改属越界；改由 `entry._HANDLERS`
  把这两个动词路由到真实现，`_ops` 只留 `start/stop/restart`。
- **已知局限**：① **只判「可读 / 存在」，不探活性** —— 不建 MCP 连接、不真调 LLM ⇒ 「配置有效」**不等于**
  「端点可达」（活性探针是另一件事，见既有 `probe`）；② `status` 的资产 / 端点数取自各自落盘账本
  （跨进程一致，但账本陈旧时数字陈旧）；③ **本 change 只接 CLI**，TUI 浮层命令属 0163；
  ④ `doctor` 退出码语义变更（见决策④，**有意**）；⑤ `CLICommandDispatcher.status("status")` 自此不可达
  （不改不删，见决策⑥）；⑥ **其余运维动词仍未注册**（`kill` / `logs` / `version` / `help` / `install` /
  `uninstall` / `list` / `info` / `auth` / `permission-mode` / `gateway` —— 台账 E100 挂账）；
  ⑦ **未覆盖 Web / Desktop**（只读诊断面属 CLI / TUI，跨端一致属另一端）。
- **规格**：`cli-ops` **ADDED** Requirement「自检诊断（`doctor`）与运行状态（`status`）」+ 4 Scenario；
  文档面 `03-interfaces/cli-ops-interface.md`、测试面 `04-testing/test-cases.md` §76（TC-DIAG）、
  台账 `coding-plan/known-risk.md` §1 E100 / §3。

## ADR-0154：TUI 只读命令族 —— 真源驱动分发 + 诊断源单接缝（change 0163）

- **背景**：TUI 斜杠命令浮层（change `0159` / ADR-0151 立的**单一真源** `_COMMANDS`）只有 6 条命令，
  **运维 / 诊断类一条都没有** —— 而 CLI 侧的实现早已齐备（`config` / `mcp` / `skill` / `notes` /
  `sessions` 等 handler）。用户 2026-10-07 诉求「`doctor`/`status`/`sessions`/`config`/`mcp`/`skill`
  等也能在浮层里选到并执行」，口径是**只读 / 诊断优先**。change `0162` 已建好只读诊断源
  （`core/diagnostics` / ADR-0153）—— 本 change 是它的**第二个消费面**。
- **决策①：把「命令名 → 处理器」写进真源（`_Command.handler: str = ""`）。** 0159 立真源的初衷是
  「登记与分发**只有一份**」，但当时处理器仍旧**硬编码**在 `on_input_submitted` 的分支链里：
  新增命令要**改两处**（真源 + 分支链），忘一处即「浮层可选、回车无声」。⇒ 真源增 `handler` 字段
  （**处理器方法名**），`_dispatch_registered(text)` 在忙态检查后**按真源分发**；`handler` 为空者
  （`/task` `/focus` `/main` `/summon` `/recall` `/resume`）**仍走既有分支链**，其语义 / 提示串 /
  次序**逐字不变**。守护：`test_registry_commands_are_all_dispatchable` **扩到 13 条**（真源每条命令的
  规范形态都必须被分发链**消费** ⇒ 只登记未接线即红）+ 新增 `test_registry_handlers_resolve`
  （每条 `handler` 在 app 上**解析得到** ⇒ 登记名笔误即红）。
- **决策②：只读命令**不豁免忙态**。** `/focus` 有忙态豁免（呈现层切换，运行中亦可用），只读命令**没有** ——
  与 `/resume` 同侧（排在忙态检查**之后**）。理由：只读命令要**往时间线插块**，而忙碌中时间线正被流式
  尾段渲染器（`_show_delta` / `_touch_tail`）占用 ⇒ 并发插入与合帧节流互踩（承 ADR-0139 的时序闸语义）。
- **决策③：只读命令不进对话、不回显。** 提交后**不**落 `❯` 回显行、**不**调 `run_loop` / `run_task`，
  只落**一条结果块**（`Report` → 逐行文本、`markup=False`）—— 与 `/focus` / `/main` / `/resume` 同侧。
  理由：这些是**查看**动作，不是对话轮次；进转录会污染会话语义与 token 预算。
- **决策④：`Deps` 经 `UIAPILayer` **单一接缝**注入，装配仍在组合根。** `UIAPILayer.__init__` 增
  `diagnostics: Deps | None`（**一个**形参，不是 9 个新句柄）+ `diagnostics()` 访问器；`entry._build_ui`
  （**唯一**构造点，repl / serve / app / run 四入口共用）注入。`repl.py` 因此**只**取 `Deps` 与纯函数
  （`collect_*` / `render` / 五张视图），**不装配任何句柄**、**不猜路径**。`/status` 的「内置工具数」
  在 TUI 面对**真实** `runtime.tools` 计数（CLI 面为 builtin-only，**有意不同**：CLI 不装配 runtime，
  装配需要有效配置，恰是诊断要绕开的）。
- **决策⑤：`/sessions` 与 CLI `sessions` **同名异义**（明写）。** CLI 的 `sessions` 列 Harness Host
  的**连接记录**，TUI 的 `/sessions` 列**会话注册表**（与 `/resume` 二级候选**同源**：`_diag_deps`
  的 `sessions` 句柄 = `SessionRegistry.list`）。两者**都**保留原语义，各自服务自己的面 —— 在规格、
  `03-interfaces/ui-interface.md` 与本 ADR 局限中明写，避免同名误读（**不**改名以迁就对方）。
- **决策⑥：只读命令**无参数面**。** 真源中其 `arg=""`；带参数提交 ⇒ 只提示、**不执行**（只读命令
  不需要参数，猜参数是投机）。未登记前缀（`/zzz`）**分发命运不变**（普通消息进对话）。
- **已知局限**：① **只读** —— 不做 `config set` / `mcp add|remove` / `skill install|remove` /
  `plugin install`（写操作命令面另立账）；② **命令清单仍是内存真源**（非配置驱动、无插件注册命令面）
  ⇒ 第三方扩展命令需改代码；③ `/sessions` **只列不切** —— 切换走 `/resume`，两命令并存（清单与切换
  分离，`/sessions` 不提供二级候选）；④ **诊断源未接线时命令只给提示**（不崩，但也不降级为简版诊断）；
  ⑤ **未覆盖 Web / Desktop**（斜杠命令面仍只属 TUI，承 ADR-0151 局限⑥同源缺口）；
  ⑥ **`_dispatch_registered` 只认无参形态** —— 带空格即提示，故「命令 + 参数」的只读扩展需先改本决策。
- **规格**：`ui` **ADDED** Requirement「TUI 只读诊断命令」+ 6 Scenario（浮层列出并可采纳 / 执行落结果块
  且不进对话 / 零副作用 / 忙碌中拒绝 / 输出不含密钥值 / 带参数与未登记前缀走既有路径）—— ADDED 只追加
  canonical 末尾，**既有 Requirement 逐字不改**；文档面 `03-interfaces/ui-interface.md` §2、测试面
  `04-testing/test-cases.md` §77（TC-READONLY）、台账 `coding-plan/known-risk.md` §3。

## ADR-0155：hooks（钩子）架构 —— 复用接缝的事件扩展点（change 0164）

- **背景**：全仓**没有**钩子能力，也**没有任何规格**承诺它。`architecture-overview.md:181` 在
  「关键约束」里点了「事件总线」这个词，实现与规格**双双缺席**；已有的横切接缝**只有两个**写进规格
  （`loop` 规格「横切中间件插入」：`middlewares` 可否决 / `action_observers` 仅观察），另三个口子
  （`turn_observer` / `trace_observer` / `cold_path`）只在 `runtime.py` **代码注入**、无声明面；
  **缺**轮前（`turn.before`）、会话起止（`session.*`）、记忆写入（`memory.write`）三个口子。
  用户 2026-10-07 诉求「hook 架构设计缺失-需要归一个 openspec」，口径是**只出规格 + ADR**。
- **决策①：**不建事件总线**，复用既有接缝。** 7 个事件里 3 个（`tool.before` / `tool.after` /
  `turn.after`）**已有**规格收口的接缝可挂；总线的收益（多播 / 解耦）在**单一消费者**（钩子执行器）
  场景下是**净开销**（多一层间接与生命周期），且会成为「第二个分发中心」，与 P1 无特权核心相悖。
  ⇒ 规格**明写**「SHALL NOT 引入通用事件总线」；将来出现**多**独立消费者再改本 ADR。
- **决策②：缺的三个口子以「新增注入形参」落地，不在既有机制里硬插分支。** `turn.before` 需一个与
  `turn_observer` **对称**的 loop 注入形参（**不**挪 `middlewares` —— 它是**动作**面、不是轮面）；
  `session.*` 落**组合根**（会话生命周期是组合根职责，UI 层不持钩子）；`memory.write` 在
  `MemoryStore` 增**观察者** DI 形参（与既有 `summarizer` / `key_fact_extractor` **同构**）。
  ⇒ 设计稿把每个事件逐条标「既有 / 待新增」，防实现者在 loop / store 里硬插分支破坏分层。
- **决策③：两形态同一失败语义（外部命令 + 内置回调）。** 外部命令 **argv 列表、不经 shell**
  （承 ADR-0093 ④ sidecar 口径）、**单事件 JSON 投递 stdin 后即 EOF**（无需长驻与握手）；
  内置回调为组合根注入的 `Callable`。**退出码**：`before` 类 `0`=放行、**非 0=阻断**；
  `after` 类**仅留痕**（与既有观察者链同语义：观察者抛错降级为遥测、不改结局）。
- **决策④：fail-closed 默认。** `before` 类钩子**超时 / 无法执行 / 回调抛错** ⇒ 按该项 `on_error`
  处置，**缺省 `block`**（与 permission 的 fail-closed 同一姿态；`allow` / `warn` 是操作者的**显式**选择）。
  `timeout_s` 缺省 5s、**硬上限 60s**（超上限按上限截断并告警 —— 不接受无界超时）。
- **决策⑤：不可逆性是**显式例外**。** 钩子副作用**不纳入** `EffectTracker`（外部命令不可撤销）——
  这是本系统对 P2「一切副作用可逆」的**唯一显式例外**，不写在别处、只写在规格与 ADR 里；
  规格**建议**钩子默认只读，写操作型钩子由操作者自担。审计面：每次调用落 trace（`kind="hook"`，
  `event` / 命令 **basename** / 退出码 / 时长 / `blocked_by`），**不留**完整 argv 与输出正文。
- **决策⑥：声明面「标量三面、清单只落 yaml」。** `hooks.enabled` / `hooks.timeout_s` /
  `hooks.on_error` 三个标量经 **`ConfigSpec` 单一真源** ⇒ 自动获得 CLI flag 与环境变量形态，
  优先级链 **CLI flag > env > `config.yaml` > 默认值**；**钩子清单** `hooks.entries`（列表）
  **只从 `config.yaml` 结构化段读** —— `ConfigSpec` 是**键 → 标量**的映射、**列表不入**
  （与 `permission.sandbox.host_allowlist` 用逗号串、mcp 端点另存 `mcp.json` **同源**的既有取舍）。
  `hooks.enabled` 缺省**关闭**（未显式开启不加载、不执行）。
- **已知局限**：① **未实现** —— 本 change 只出契约（台账 **E101** 挂账，实现另立 change；
  **已由 ADR-0259 / change 0269 闭合** —— 实现局限转记该 ADR）；
  ② **清单不入三面**（ConfigSpec 是标量映射的既有取舍）；③ **无优先级 / 无多播语义** —— 同事件多钩子
  按**声明序**执行、**任一** before 钩子阻断即终局（不设权重、不做「否决覆盖」）；
  ④ **载荷脱敏 ⇒ 钩子看不到密钥原始值**（需检查密钥本体的策略属 permission 面，不是钩子面）；
  ⑤ **不可逆**（唯一显式例外，见决策⑤）；⑥ **不覆盖 Web / Desktop**（声明面属配置面，跨端一致另议）。
- **规格**：新建 capability **`hooks`**（`## ADDED Requirements` 四条：钩子事件面与载荷 / 钩子形态与接缝 /
  钩子失败处置与安全边界 / 钩子声明面，共 10 Scenario）；设计稿
  `doc/openspec/changes/archive/2026-10-07-0164-hooks-architecture/design.md`、模块文档
  `doc/02-modules/hooks.md`、台账 `coding-plan/known-risk.md` §1（E101）+ §3（本 ADR 局限行）。

## ADR-0156：推理输出协议的容错与失败可见（change 0166）

- **背景**：用户 2026-10-08 实测「跑着跑着后面执行都突然无法正常执行」。trace
  `14683edf49554534a414f7695dfa3797` 给出**反例**：模型回的内容是**完全正确**的动作 JSON
  （`tools.code_run`、参数合法），只是形态为「解释文字 + 换行 + JSON」；`planner._parse` 只按
  **首字符是否 `{`** 做布尔判定 ⇒ 整段当**最终答复** ⇒ **零执行**、**零报错**，本轮还记成成功
  （`step_completed.failed=false`、`_notify_turn(ok=True)`），且 trace 里**没有** `tool_call` 痕迹。
  更糟的是**反馈污染**：下一轮模型看到自己的「动作」被接受而无配对工具结果 ⇒ 编造提交号与测试数。
  两个独立缺陷缺一不可：**① 识别面太窄**、**② 失败面被抹平**（终止动作恒 `failed=False`，
  「没执行」与「正常收尾」无从区分）。载荷本身**从不畸变**（26 轮抽样里无一处参数形态错），
  ⇒ 不是「模型回得烂」，而是**容错为零 + 静默吞掉**。
- **决策①：只认**尾部**动作 JSON，不全文扫描。** 新增纯函数 `_trailing_json_object`
  （`json.JSONDecoder().raw_decode` 自每个 `{` 起试解、**要求其后仅剩空白与 Markdown 围栏符**）。
  判据**必须收在文末**：模型解释协议时会**引用**动作 JSON 作示例（trace 已有此形态），
  全篇扫描会把「解释」当「执行」——**宁可漏检，不可误判**。真实事故的形态（解释在前、动作在后）
  正是模型自然而然的行文次序，尾部覆盖已足。围栏包裹的尾部 JSON **同等识别**（模型爱加 ```` ```json ````）。
- **决策②：命中即复用既有动作协议，**解析层不写第二份校验**。** 尾部对象**只要求含非空 `tool_id`**
  即交 `_from_dict` ⇒ 走与纯 JSON 路径**同一套**语义。参数校验的单一真源在工具调用链
  （`ToolProvider` → `constraints.Validator`）—— 解析层再写一遍 required / enum 检查就是第二份副本
  （本仓明令避免，参见 `gate_run` 在处理器内补偿 `enum` 的两处既有注释）。未注册 / 参数不合法的工具
  由链上回结构化错误（**可见**失败），不由解析层猜。
- **决策③：`Action.failed` 仅对终止动作有意义。** 新增 `failed: bool = False` 字段，语义**限定**为
  「**推理产出不可用**」（解析失败 / 模型调用失败）。非终止动作（工具调用）**不用**本字段 ——
  工具失败属 ReAct 多轮自愈的正常面，**不改**其既有口径（`ActionResult.failed` 语义逐字不动）。
  消费点三处、**不新造状态**：`act()` 终止分支透出 ⇒ `observe()` 的 `trajectory.ok` /
  `step_completed.failed`；`arun` 收尾并入 `_notify_turn(ok=…)` 与 `loop_finished.failed`。
- **决策④：失败标记**不改变终止语义**。** 解析失败**照旧**以回复收尾（`loop_failed` 仍**只**由
  `limit_reason` 触发），变的只是**成败核算**。⇒ 与既有规格「合成终止不写入转录」「循环自身失败
  带模块归因」两条**互不干扰**：合成文案仍进转录（下一轮模型可见，既有口径），转录追加逻辑**零改动**。
  **不置位**的同族终止动作（审批拒绝 `decline()` / `pet/safety` 阻断）本次**明确不动** ——
  属**审批**语义，与「推理产出不可用」不同源。
- **决策⑤：系统提示**加严**（辅助，非兜底）。** `_SYSTEM_PROMPT` 补一句：工具调用 JSON SHALL
  单独成块、SHALL NOT 与正文混写、SHALL NOT 用代码块包裹。这是**降低触发频率**的辅助手段
  （`_parse` 的容错才是兜底），对既有「输出格式二选一」表述是**加严**而非替换，不改任何解析语义。
- **零回归边界**：纯 JSON 路径、原生 `tool_calls` 优先序、普通文本答复末行、流式 `reply_stream`
  首字符判定、`limit_reason` 语义、转录追加 —— **逐字不改**（逐条在 `tests/test_loop_output_protocol.py`
  有对应断言）。
- **已知局限**：① **非尾部**动作 JSON 仍按答复处理（漏检为已知取舍，见决策①）；
  ② 尾部 JSON 若**确为**「示例引用」则会被执行 —— 缓解面是既有的授权/审批链 + 事件面可见 + 工具可逆，
  解析层不做语义猜测；③ 解析失败的**合成文案仍进转录**（既有口径，下一轮模型可见），本次不动；
  ④ **仅 `loop` 面** —— 子任务 / 编排层的输出解析不在本 change 范围。
- **规格**：`doc/openspec/specs/loop/spec.md` **ADDED** Requirement「推理动作解析与失败可见」
  （5 Scenario：混写正文的动作 JSON 被识别 / 围栏包裹的尾部动作 JSON 被识别 /
  非动作 JSON 的自然语言回复不被误判 / 解析失败使本轮失败 / 纯 JSON 与原生工具调用路径零回归）——
  ADDED 只追加 canonical 末尾，**既有 Requirement 逐字不改**；文档面
  `doc/02-modules/loop.md`、`doc/03-interfaces/loop-interface.md` §3、测试面
  `doc/04-testing/test-cases.md` §78（TC-PARSE）、台账 `coding-plan/known-risk.md` §3。

## ADR-0157：收尾与维护中的同步模型调用 —— 在循环边界卸载（change 0167）

- **背景**：`~/.core/state/traces.jsonl` 里 `maintenance_failed` 遥测共 26 条，分布在 6 轮中为
  `1/1/8/2/3/11` —— 恰为 `max(0, rounds − 9)`（`_ROUND_THRESHOLD = 10`）。根因：组合根注入的
  `_llm_text` 是**同步**接缝（内部 `LLMProvider.completion()` = `asyncio.run(acompletion)`，见
  `provider.py`），却被 loop 在**事件循环线程内同步调用**（轮内压实 / 收尾钩子 `turn_observer` /
  维护节拍含冷路径）：CPython 的 `asyncio.run` 检测到运行中的循环即抛 `RuntimeError`，被三段各自的
  `except Exception` 降级链吞成一条遥测。后果是**静默的**：会话摘要（G3 `0153` 的输入）与结构化
  关键事实抽取（G4 `0155`）**在生产路径上从未成功落库**，SOP 提炼 / 技能迭代 / 进化 review 同理。
- **决策①：在 loop 边界把**整段**工作卸载到工作线程（取 A，弃 B、C）。** 三处调用点改为
  `await asyncio.to_thread(self._compact, …)` / `await asyncio.to_thread(self._notify_turn, …)` /
  `await asyncio.to_thread(self._maintain, …)`（`astream` 是 async generator，`await` 合法）。
  - **弃 B**（改 `_llm_text` / `completion` 令其在有循环时另起线程跑并**同步等待**）：调用方仍在
    事件循环线程上同步阻塞等**数秒**网络往返 ⇒ 把「必抛」换成「卡死」（UI 冻结），且对全部五处
    接缝统一改，而其中三处（SOP / 迭代 / 进化）从 CLI 一次性进程调用时**现状即正确** ⇒ 属投机改面。
  - **弃 C**（把 `summarizer` / `turn_observer` / `cold_path` 全 async 化）：触及 4 个 Protocol 与
    全部调用方（含 skills / evolution / memory 三包）⇒ 为**一个线程边界**付重构级代价；若将来确需
    async 化，应先立 ADR。
- **决策②：A 是**回到设计前提**，不是「把线程当补丁」。** `http_pool.py` 声明空闲连接存于
  `threading.local()`、不跨线程共享；**ADR-0064 决策②** 明文「provider 的同步传输本就在工作线程上跑
  （`asyncio.to_thread` / `run_in_executor`），同一线程的连续调用即复用」。⇒ 同步接缝在工作线程上执行
  是本仓 LLM 传输层的**设计意图**（`stdlib_provider` 与 `builtin` 工具已是 `asyncio.to_thread` 惯例）。
- **决策③：三个私有方法**保持同步**，DI 契约零变更。** `_compact` / `_notify_turn` / `_maintain`
  的签名与内部 `try/except` 降级链**逐字不动**（只有调用点变）⇒ 直接调用它们的测试与既有代码**零影响**，
  遥测事件名（`maintenance_failed` / `turn_observer_failed` / `cold_path_failed`）与文案零回归；
  四个注入接缝（`turn_observer` / `cold_path` / `summarizer` / `key_fact_extractor`）仍为同步 callable。
  卸载的是**执行线程**，不变的是**接口与语义**。
- **决策④：整段卸载，不拆更细。** 「只卸载含模型调用的那一半」需把组合根的 `on_turn` 闭包或
  `_maintain` 的两件事**从内部切开** —— 收益（省一次线程跳，~ms）远小于代价（面变大、语义变复杂）。
  取「整段卸载」：边界清晰、语义零变化；「不含模型调用」的收尾段（如 `memory.forget`）被一并卸载，
  代价可忽略（相对其内模型的秒级往返）。
- **零回归清单**：终止语义、`step_completed` / `loop_finished` / `loop_failed` 的**顺序与载荷**、
  三段降级链、转录追加（`remember` / `_append_transcript` 不在卸载面内）、维护节拍状态
  `_last_maintenance` 语义（单写者：同一循环实例，无并发）—— 逐条不变（`tests/test_loop_offload_threads.py`
  有对应断言）。
- **顺带收益**：原本被吞掉的失败**仍会被吞**（降级链不变），但**不再发生** —— 压实摘要与关键事实、
  SOP 提炼、技能迭代、进化 review / patch 会**真的产出** ⇒ G3（`0153`）与 G4（`0155`）两条已收口
  能力**首次在生产路径上生效**。
- **已知局限**：① **交叉会话并发写未加锁** —— 卸载期间事件循环可推进其他会话的 loop 任务，而
  `MemoryStore` / `EffectTracker` 等共享状态**无锁**；该竞态**先于本 change 存在**（既有同步路径同样
  无锁，只是窗口更小），本 change **不引入也不消除**，消除需给 store 加锁或按会话分片（另议）；
  ② **无超时 / 无取消** —— `to_thread` 不提供取消，工作线程里的模型调用卡住时本轮收尾会**等它**，
  缓解面是 `LLMProvider` 既有 `timeout_s` 与失败降级链（另议）；③ **只覆盖三处已确认边界** ——
  若将来新增「循环内同步模型调用」站点（新观察者 / 新维护步骤）需同样卸载，本条**无自动门禁**；
  ④ **线程跳一次的成本非零**（三处各一次 `to_thread`）；⑤ **不改 `completion()` 薄壳** —— 从同步
  上下文（CLI 一次性进程）调用仍是既有语义，从事件循环内直接调用仍是**错误用法**（本 change 只把
  loop 侧用法改对，未加防呆断言）。
- **规格**：`doc/openspec/specs/loop/spec.md` **ADDED** Requirement「收尾与维护工作的执行线程」
  （5 Scenario：收尾钩子在工作线程 / 冷路径在工作线程 / 轮内压实不阻塞事件循环 / 含同步模型调用的
  压实产出真的落库 / 降级语义零回归）—— ADDED 只追加 canonical 末尾，**既有 Requirement 逐字不改**；
  文档面 `doc/02-modules/loop.md`、`doc/03-interfaces/loop-interface.md` §4、测试面
  `doc/04-testing/test-cases.md` §79（TC-OFFLOAD）、台账 `coding-plan/known-risk.md` §1（E103）+ §3。

## ADR-0158：诊断视图列对齐按**显示宽度**（change 0165）

- **背景**：TUI `/notes` 输出乱。`render_notes` 用 `\t` 拼三列（note_id / title / 时间戳），而
  TUI 的呈现层是 `Static(..., markup=False)` **纯文本**（不解释制表符宽度）⇒ 列随 note_id 长度参差，
  行前缀缩进叠加后观感更乱。用户实测所报。
- **决策①：列宽按**显示宽度**计算，**不**按字符数。** 新增 `_display_width(text)`
  （`unicodedata.east_asian_width(char) in "WF"` ⇒ 2 列，否则 1 列）与 `_pad(text, width)`。
  必要性有**实测反例**：`f"{v:<{w}}"` 只按 `len()` 补齐，而中日韩字符在等宽终端占 **2 列** ——
  清单 `a/短`、`longer-id/一个较长的标题`、`zz/ascii title` 三行**字符长度全等 36**，
  **显示宽度 37 / 43 / 36** ⇒ 时间戳列落在第 37 / 43 / 36 列，**根本没对齐**。本仓笔记标题以中文
  为主 ⇒ 按字符数补齐等于没做，规格「等宽终端下各数据列对齐」的目标句落空。
- **决策②：对齐发生在**渲染层**（`diagnostics/views.py`），不换 TUI 组件。** 诊断视图的既有契约是
  「只读、与 `doctor`/`status` **同源同形状**」⇒ 换 `DataTable` 会把对齐耦合进 TUI，且 CLI / Web
  两条同样消费 `Report` 的路径得不到同一格式。渲染层补齐 ⇒ 三端一致、`Report` 接口零变更。
- **决策③：分隔符为两个空格，弃 `\t`。** 制表符宽度由终端自定（正是本次缺陷根源），且 `\t` 在
  跨列拼接时无法与补齐共存。
- **决策④：歧义宽（Ambiguous）字符按 1 列。** `"WF"` 不含 `A` ⇒ `±`、`→` 一类按 1 列计，与多数
  现代终端默认一致；若终端按双宽渲染歧义字符，含此类字符的行会有 1 列偏移（已知局限，见下）。
- **范围**：本 change **只改 `render_notes`**。`render_sessions`（`\t`）、`render_mcp`（`\t`）与
  `render_config` 的 `\t` 形态**同缺陷但在范围外**（proposal 明写「各自独立提案」）—— 记 §3 局限。
  **（后续）已由 change `0168` / ADR-0159 覆盖**：全部列表型视图改走模块级 `align.py`，
  两把助手自此**非** `views.py` 私有。
- **兼容性**：`Report` 接口与 `render_notes` 签名零变更；既有断言
  （`test_render_notes_marks_pinned` 的 `"alpha" in out` / `"常驻" in out`）在新格式下逐字仍成立；
  空清单（`（空）`）与句柄缺失（`未接线`）两条早退路径不受影响。
- **已知局限**：① **歧义宽字符按 1 列**（上文决策④）；② **超长 title 会拉长整行**（列宽取清单内
  最长显示宽度，无截断 / 无换行 —— 笔记清单规模有限，暂可接受）；③ **只覆盖 `render_notes`** ——
  `render_sessions` / `render_mcp` 仍 `\t` 参差（**已由 change `0168` / ADR-0159 闭合**）；
  ④ **未做 TUI 端列宽自适应 / 截断**（终端宽度感知属呈现层，本 change 不做）。
- **规格**：`doc/openspec/specs/cli-ops/spec.md` **ADDED** Requirement「诊断视图列对齐」
  （3 Scenario：笔记清单等宽列 / **含中日韩字符的清单仍对齐** / title 回退对齐）—— ADDED 只追加
  canonical 末尾，**既有 Requirement 逐字不改**；测试面 `doc/04-testing/test-cases.md` §80
  （TC-NOTES-ALIGN）、台账 `coding-plan/known-risk.md` §1（E104）+ §3。

## ADR-0159：诊断视图对齐 —— 上提为模块级**单一实现** + 两形态入口（change 0168）

- **背景**：ADR-0158（change 0165）修好了 `render_notes`，但把两把助手（`_display_width` / `_pad`）
  留在 `views.py` **私有**，且**只改了这一个视图**。诊断源里其余 5 处列表型视图仍以 `\t` 拼列
  （`render_sessions` ×2 / `render_config` ×7 / `render_mcp` ×2 / `render_skills` ×2 /
  `collect_status` ×8）—— 消费面（TUI `Static(markup=False)`、CLI `print`）**都不解释制表符**，
  根因与 0165 逐字相同；用户复查 0165 时据此追问。
- **决策①：对齐上提为**模块级**公开助手（新 `core/diagnostics/align.py`），做**单一实现**。**
  `0165` 的私有助手位置有一处**结构性后果**：`checks.py` 的 `collect_status` **够不着** ⇒ 若各处
  自修，必然出现第二份「列宽怎么算」的实现。本仓反复消掉的正是这种双份真源（同 0159 的
  `_COMMANDS`、0162 的 `builtin_tools()`），故上提而非复制。模块只依赖标准库
  `unicodedata` —— **不引 `wcwidth` / `rich`**（本仓「尽量不依赖三方库」）。
- **决策②：两形态两个入口（`align_rows` / `align_pairs`），**不**合成一个带模式参数的函数。**
  两形态的**不变量不同**：表格型要求**每列**对齐（多列独立求宽），键值型只要求**值的起始列**对齐
  （标签列求宽、值不补）。合一就得加「哪些列参与求宽」的开关 —— 正是被消掉的复杂度；两个入口各
  5~8 行，各自可读。`align_rows` **行末不补**（`i == len(row) - 1` 原样出）⇒ 无尾随空白。
- **决策③：`align_pairs` 接受 `str` 条目并原样透出** —— 技能视图的 `· <标识>（<状态>, <版本>）`
  明细行夹在键值行之间、不参与补齐。**这是刻意的混合形态**：使 `render_skills` 只维护**一个有序
  条目列表**（已装段 + 目录段拼起后**一次**对齐）。若按段各自对齐，「标签列宽」会被算成两段各自的
  最大值 ⇒ 同一视图里 `已装技能库` 与 `市场目录` 起始列错开，正是要修的观感。
- **决策④：`render_notes` 回填共用助手，常驻标记**并入时间戳格**（不是第四列）。** 列数恒为 3：
  第四列若为空串，`_SEP` 之后会留下**尾随两空格**；并入末格则「一条笔记一行、列数不随常驻与否变化」，
  且与 `0165` 的行文本**逐字一致**（`<ts> [常驻 优先 N]`，标记前一个空格）。
- **决策⑤：范围＝诊断源**全部**列表型视图（`0168` 一次做干净）。** 分两轮各改几个视图会让同源缺陷
  在中间态并存（用户复查时看到的正是这个中间态）。`doctor` 的 `Check` 明细**不在范围**——它是
  **单行项**（`✓/!/✗ <名>：<明细>`），不是列表。TUI / CLI 的消费点**零改动**（它们只吃 `Report`）。
- **兼容性**：`Report` / `Deps` / 六个视图**签名零变更**，`render` 的「标题 + 2 空格缩进」不变；
  既有松散断言（`"s1" in out` 等）与三条降级路径（`（空）` / `未接线（句柄未注入）` / 配置不可用单行）
  逐字不变。**密钥红线不变**：`render_config` 的「密钥引用」行由三列变二列（`${VAR}` 与结论以两个
  空格相连），仍**只出引用名 + 结论**、不含任何取值。
- **已知局限**：① **歧义宽字符按 1 列**（`"WF"` 不含 `A`：`±` / `→` 一类）—— 承 ADR-0158 局限③，
  本 change **不裁决**；② **超长字段拉长整行**（无截断 / 换行 —— 列表规模有限，同 0165 取舍）；
  ③ **测试助手的「2+ 空格分列」解析**：若某**值**内含 2+ 空格会被拆成多格 —— 值均为单空格形态
  （`max_rounds=N, token_budget=M` / `a=on, b=off`），无实例，且与「列间 2 空格」的视图约定同源。
- **规格**：`doc/openspec/specs/cli-ops/spec.md`「诊断视图列对齐」**MODIFIED** —— 作用域由
  「`render_notes`」扩为「诊断源**全部**列表型视图」，明写两形态与各自口径；既有 3 Scenario
  **逐字保留** + 新增 2（会话与 MCP 端点清单等宽列 / 键值型视图标签列对齐）。测试面
  `doc/04-testing/test-cases.md` §81（TC-ALIGN-ALL）、台账 `coding-plan/known-risk.md` §1（E105；
  并回填 E104 与 ADR-0158 局限③ 的闭合）。

## ADR-0160：TUI 步骤块 —— 缺省**缩略**（末尾 N 行）+ 三态手势 + 目标摘要（change 0169）

- **背景（用户实测）**：TUI 发一句话后「默认只有『思考中...』」，看不到实时思考；工具动作「点击箭头
  只有看到结果」而看不出在干什么；且长行**不自动换行**。逐行核实四点根因：
  ① `repl.py:1003` 思考块建时 `collapsed=True`（事件流本身是**通**的：`show_thinking` 已开）；
  ② `repl.py:973` 工具块同样 `collapsed=True` 且**标题不带目标**；
  ③ `repl.py:401` 的 `.hint { width: auto }` 用在折叠区正文 `Static` 上 —— Textual 下 `width: auto`
  的 `Static` 宽度 = **最长行宽**，超出部分被祖先 `overflow-x: hidden` **裁掉而非折行**；
  ④ `repl.py:1008` 每来一个思考 delta 就 `str(detail.render()) + text` **全文重拼 + 重解析**（O(n²)），
  是「实时」不可得的第二个原因。
- **决策①：以 `Collapsible` 的**子类** `_StepBlock` 承载，不新造控件。** 三点理由：既有时间线测试助手
  （`tests/test_repl.py` / `tests/test_ui.py` 的 `_timeline_text`）按 `isinstance(child, Collapsible)`
  遍历 ⇒ 子类**天然命中、零改动**；折叠语义（`.-collapsed > Contents{display:none}`、`DOMNode.display`
  为其 property、切换后 `call_after_refresh(scroll_visible)` 自动滚入视野）由 Textual 维护、不重造；
  与仓内 `_PaletteList(OptionList)`、`_PaletteSuggester(Suggester)` 的子类化惯例一致。类**定义在
  `build_app` 内**（textual 全仓懒 import，ADR-0040 MAL 隔离）。
- **决策②：三态物理落点 —— 缩略 = `collapsed=False` + 正文切末尾 N 行；全文 = `collapsed=False` +
  全量；收起 = `collapsed=True`。** Textual **没有**「只显示末尾 N 行」的样式能力：`max-height` 裁
  **顶部**、`overflow-y` 给的是滚动而非窗口。故末尾窗口必须落在 **Python 切片**（`_render_body()`），
  样式层只负责**宽度**与**颜色**。这一分工是「三态」能成立的前提：折叠态由 Textual 管，**窗口态**由
  语言层管。
- **决策③：缺省取**缩略**而非收起 ⇒ 规格「思考过程回显（Think）」SHALL 被 MODIFIED，把写死的
  「**缺省收起**」**分端化**（TUI 缩略 / Web + APP 逐字保留收起）。** 这是本 change **唯一**触碰规格
  规范句的地方：原句把三端缺省形态写成了同一约束，TUI 改缺省形态即与之冲突。三态机制（窗口 N、
  手势、标题口径）**只在**新增的「TUI 步骤块（缩略 / 全文 / 收起）」Requirement 定义**一处**，
  「Think」条改为**指向**该条 ⇒ 不落两份真源。
- **决策④：工具目标摘要取**白名单结构性字段**（`path` / `url` / `script` / `gate` / `pointer`），
  单行、有界，**只**读既有 `action_started` 载荷的 `args`。** 这是「TUI 子任务运行态与详情」既有红线
  （SHALL NOT 暴露内部 `tool_id` 与原始参数）在**主时间线**上的**同一延伸**：友好名（`_tool_name`，
  `repl.py:132-148`）之上补一个**结构性**目标，**正文类**参数（`content` / `old_content` /
  `new_content`）在标题里**永不出现**。既不新建第二数据源，也不放宽既有「不暴露原始参数」口径。
- **决策⑤：正文折行 = 新 class `.step-body { width: 1fr }`，**不复用 `.hint`**。** 两条 class 规则同
  优先级会互相打架（`.hint` 的 `width: auto` 与目标规则并存 ⇒ 结果依赖声明次序，脆）。`Collapsible.Contents`
  自带 `padding: 1 0 0 3` ⇒ **L 形缩进是原生的**，本仓只需在正文首行补 `└ ` 角标、续行补两空格
  （同为 2 字符 ⇒ 与原生 3 列缩进叠加后同列对齐）。
- **决策⑥：`format_action_event` **逐字不动**（`repl.py:160-172`）。** 它是 CLI（`entry.py`）与
  TUI 子任务里程碑（`_progress_subtask`）**共用**的取口，且 6 处测试断言依赖其**逐字**输出
  （`⏺ Bash ✓ (1.5s)` 等）。目标摘要**只**加在 TUI 步骤块**标题**（`_add_action_widget`）⇒
  CLI 呈现与子任务里程碑零回归。
- **决策⑦：append-only 行缓冲消 O(n²)（思考实时性的前提）。** `_lines: list[str]` + 末元素为未完成行，
  每次 `feed(text)` 只**追加**；`_render_body()` 才做（有界的）行切分与拼接。原实现每 delta 全文重拼 +
  重解析，长思考流越跑越卡 —— 与「实时」直接冲突。
- **决策⑧：「CLI 友好交互」的 Scenario「折叠块展示」（`ui/spec.md:122-125`「长内容默认折叠，用户可
  展开/收起」）**相容，该 Requirement 逐字不改**。** 缩略**就是**该「折叠」在本 change 的具体形态：
  超出有界行数的部分默认不可见、点开可见 ⇒ 语义未变，只是把「折叠」从「全隐」细化为「末尾窗口 +
  剩余行数提示」。**不改**该条，避免为一个已有约束再写一遍。
- **手势的实现依据（Textual 8.2.8 源码核实）**：`CollapsibleTitle._on_click` 先 `event.stop()` 再
  `post_message(Toggle())` ⇒ 点标题**只**走原生折叠、**不会**冒泡到正文分支；正文路径
  `Static → Collapsible.Contents(Container) → Collapsible` **全程无 `stop()`**（只有标题停）⇒
  Click 必达 `_StepBlock.on_click`。`Collapsible.__init__(*children, title=…, collapsed=…)` 是普通
  构造器 ⇒ 自定义 `__init__` 合法。
- **兼容性**：CLI / Web / APP 呈现零改动，转录 / 记忆 / 日志 / trace **零改动**（思考原文仍 SHALL ONLY
  经事件面呈现）；`format_action_event` / 子任务折叠块 / 子 Agent 焦点视图 / `_flush_tail` 系列
  （回复流式的合帧节流**专供回复**，步骤块不参与、不争 `scroll_end`）/ `_reset_turn_state` 口径
  **逐字不变**；`_StepBlock` 是 `Collapsible` 子类 ⇒ 既有 `_timeline_text` 助手与全部 `isinstance`
  断言零回归。事件面与 `loop` / `cli-ops` / `observability` 规格**零改动**。
- **已知局限**：① **`file_write` / `file_patch` 标题无目标** —— 其正文参数使 `args` 超过事件面既有的
  **≤400 字符**上界（`_args_excerpt`，`loop/default.py:78-83`；`loop/spec.md:239` 与 `observability`
  tracer 的「`args` 允许为节选字符串」契约）而**退化为字符串**，TUI 不解析 repr 故取不到 `path`
  （其路径仍会出现在 `└` 输出摘录）。根治需把 `loop` 的 args 节选改为「恒为映射、逐值有界」，牵动
  `observability` 既有契约 ⇒ **另立 change**，本 change 记入台账；② **`code_run` 目标取 `script`
  首行** ⇒ 操作者自填内联凭据会被显示（与终端显示命令**同等**暴露度；步骤块**不落盘**）；③ 缩略窗口
  恒**跟随最新**（与既有回复尾段行为一致）；④ **不改**子任务折叠块与焦点视图；⑤ Web / APP 维持缺省收起。
- **规格**：`doc/openspec/specs/ui/spec.md` —— 「思考过程回显（Think）」**MODIFIED**（缺省形态分端；
  既有 2 Scenario 逐字保留 + 1 条改写）+ 「TUI 步骤块（缩略 / 全文 / 收起）」**ADDED**（6 Scenario）。
  测试面 `doc/04-testing/test-cases.md` §82（TC-STEP-BLOCK）、接口文档 `03-interfaces/ui-interface.md` §2、
  台账 `coding-plan/known-risk.md` §1（E106）。

## ADR-0161：未闭合的动作载荷 —— 识别面收紧 + 失败可见 + 原始产出可诊断（change 0170）

- **背景（用户实测）**：TUI 里出现整段 `{"tool_id": …}` **当正文**打印、且该轮**零执行零报错**。
  trace 取证（`9ae2ae1fe3b34329a8cfaf028e722200`）：载荷本身**从不畸变**、模型动作 JSON **完全正确**，
  形态是「解释文字 + 换行 + 动作 JSON」；致命处在于该轮动作 JSON 的**外层对象未闭合**（模型产出被
  截断或写坏，末态括号深度 = 1）。全库统计：56 轮中 5 轮回复含 `"tool_id"`，其 13 条 `step_completed`
  **全部 `failed=False`** —— 失败率 ≈9%、**100% 静默**。
- **根因（承 0166 / ADR-0156 的取向空洞）**：0166 定「尾部**可解析**且含非空 `tool_id` 的对象」为唯一
  容错形态，明文**宁可漏检不误判**。外层动作被截断时，尾部最末一个「可解析且其后无剩余」的对象**不是
  动作而是它的内层 `args`**（本例恰好闭合）⇒ `embedded.get("tool_id")` 为假 ⇒ 落兜底
  `Action(args={"reply": text})`，整段 JSON 变正文且 `failed=False`。**同一缺陷在「内容以 `{` 开头」的
  路径早已可见**（`json.loads` 失败 ⇒ `LLM_PLAN_PARSE_FAILED`）—— 只因前缀多了一段解释文字，就从
  「失败可见」变成「静默成功 + JSON 当正文」。本 change 把两者对齐。
- **决策①：新判据为「自**最后一次** `"tool_id"` 回退至其外层 `{`，做**字符串感知**的括号深度扫描，
  深度**从未**回到 0 即命中」（形态 4）。** 要区分的是两种「尾部不是动作」：**闭合**的示例对象
  （含/不含 `tool_id`）＝模型在**说** ⇒ 自然语言回复（0166 口径不变）；**未闭合**的 `"tool_id"` 结构
  ＝模型在**做**、只是产出坏了 ⇒ **失败态终止动作**（本 change）。判据**严格、不启发式**：闭合的尾部
  对象一律不命中（承 0166「只认尾部、宁漏勿误」）。
  - **弃「`raw_decode` 报错且位置在文末」**：`Unterminated string` 的 `pos` 指向**字符串开头**而非
    文末，而「长 `content` 被截断」正是主场景 ⇒ 必然漏检。
  - **弃「遍历每个 `{` 起 `raw_decode`」**：无法区分「截断」与「正文里恰好不配对的 `{`」。
  - **取最后一次标记**：截断必发生在文末，最后一次即当事结构（若最后一次已闭合而更早一处未闭合，
    按答复处理 —— 记入局限）。
  - 判据实现拆为 `_never_closes(text, start)` 纯扫描 + `_unclosed_action_payload(text)` 定位，二者
    均满足仓内「if/else 嵌套 ≤3」架构门禁。
- **决策②：`Action` / `LoopResult` 增尾字段 `raw_output: str = ""` 承载**有界原始产出**，**不复用
  `args`**。** `args` 是**工具参数面**（终止动作的 `args` 会成 `ActionResult.data`），塞诊断字段会污染
  该面。传递链：`planner._parse` → `action.raw_output` →（`act` 不读它；`astream` 内 `action` 仍在作用
  域 ⇒ 局部 `raw_output` 直取）→ `LoopResult.raw_output`（呈现面）→ `loop_finished` trace `raw_output`
  （诊断面，条件键）。**不变量**：`ctx.reply` 只取 `data["reply"]` ⇒ 转录（`_append_transcript`）与记忆
  （`remember(..., {"reply": ctx.reply})`）**天然不含**原始产出，**无需门控代码**；终止动作**不回灌**
  `ctx.messages` ⇒ 原始产出**不进**下一轮提示词。上界 `_RAW_OUTPUT_MAX = 4096`（**含**截断提示行 ⇒
  总长受上界约束，非「上界 + 提示」）。
- **决策③：消费 `finish_reason` 使**成因可辨**。** `LLMResponse.finish_reason` 早已存在且 `stdlib` 已
  填，planner 从不读；`LLMChunk` **无**该字段、`_map_chunk` **丢弃**它 ⇒ 流式（TUI 主用）无信号。
  故 `LLMChunk` 增尾字段 `finish_reason: str = ""`（缺省空洞零影响）、`_map_chunk` 取
  `choices[0].finish_reason`；`planner._parse(content, *, finish_reason="")`：`"length"` ⇒ 提示明示
  **被截断**，否则 ⇒ **未闭合（疑似截断或写坏）**，二者**失败语义相同**。`astream` 累积末个非空
  `chunk.finish_reason`（`getattr` 取值 ⇒ 第三方 provider 自有形块不致破）。
  - **Non-goal：不下发 `max_tokens`**。截断上游是「`_build_request` 至今不下发 `max_tokens` ⇒ 端点用
    自身缺省限额」；以 `loop.output_reserve` 驱动该字段看似顺理成章，但**部分端点会拒绝过大的
    `max_tokens`（400）**，属独立兼容性决策 ⇒ 另立台账项（E107 附注）。本 change 只保证「截断
    **看得见、归得因**」。
- **决策④：呈现面承 0169 —— `_StepBlock.__init__` 增 **关键字** 形参 `collapsed: bool = False`（既有
  调用点零改动）；TUI 在 `loop.result` 载荷（`LoopResult` 透传）携带非空 `raw_output` 时挂
  `_StepBlock("⚠ 未能解析的模型原始输出", collapsed=True)`。** 该块**缺省收起**，与思考块/工具块的
  缺省缩略态**有意不同**：正文是未解析的原始载荷（可能被截断或写坏），缺省收起以免污染时间线。分支
  置于 `_format_event` **之前**（后者对 `LoopResult` 返回 `None`）；`continue` 后**不落** `❯` 回显。
  原始产出**只在此处呈现**：不进转录 / 记忆 / 笔记 / 日志。
- **兼容性**：形态 1/2/3 与自然语言回复路径**逐字不变**（含缺 `tool_id`/`reply` 时的
  `LLM_PLAN_PARSE_FAILED` 文案）；`decline()` / `pet` 审批语义**不置** `failed`（非推理产出不可用）；
  终止语义不改（解析失败照旧以回复收尾、`loop_failed` 仍只认 `limit_reason`）；工具失败口径不改
  （ReAct 自愈面）。`Action.raw_output` / `LoopResult.raw_output` / `LLMChunk.finish_reason` 均为
  **尾字段带缺省** ⇒ 全部既有构造点零改动。
- **已知局限**：① 判据只认**最后一次** `"tool_id"` 标记（更早未闭合、最后闭合 ⇒ 按答复处理）；
  ② 未闭合是**结构**判据、不解释成因（信号不可用时不下断语）；③ 原始产出上界 4096 字符，超长截断；
  ④ **不发 `max_tokens`** ⇒ 端点缺省限额导致的截断**仍会发生**，本 change 只使其**可见**；
  ⑤ Web / APP 不呈现该折叠块（SPA 零改动）。
- **规格**：`doc/openspec/specs/loop/spec.md` —— 「推理动作解析与失败可见」**MODIFIED**（+ 形态 4 +
  判据 + raw_output/成因措辞 clauses；既有 5 Scenario 逐字保留 + 3 新增）；`llm-provider/spec.md`
  —— 「流式增量携带终止原因」**ADDED**（2 Scenario）；`ui/spec.md` —— 「TUI 折叠呈现未能解析的模型
  原始输出」**ADDED**（2 Scenario）。测试面 `doc/04-testing/test-cases.md` §83（TC-UNPARSED-ACTION）、
  接口文档 `03-interfaces/loop-interface.md` / `llm-provider-interface.md` / `ui-interface.md` §2、
  台账 `coding-plan/known-risk.md` §1（E107）。

## ADR-0162：notes 逐轮写回 —— 行动序列改人类可读 + 有意义闸门（change 0171）

- **背景 / 用户实测（2026-10-08）**：文档化记忆（notes）的逐轮写回把 canonical 知识库塞进
  **不可读原文转储**且**琐碎轮次也入库**。逐条取证（读代码）：
  ① `loop/default.py::_action_steps` 把首条 user 消息之后的每条上下文消息渲染为
  `f"{role}: {content}"`，而 `content` 正是 `_record_observation` 写死的 `json.dumps(...)`
  （助手动作 `{"tool_id":…, "args":…}` / 工具观察 `{"data":…}`）⇒ `## 解决过程` 逐字为 JSON 转储 +
  整篇工具输出（无界）；② `runtime.py::on_turn` 在**每个**成功轮无条件调 `observe_turn`，
  **无有意义判据** ⇒ 一句「你好」也成篇；③ 主题键取 `slug_topic(首条 user 消息)` ⇒ 每句不同措辞
  各成一篇（叠加来源守护派生 `<topic>-N`）。
- **决策 ①「行动序列全局改人类可读」（不设 notes 专属投影）**：`steps` 有**两个**消费者
  （`sop_extractor.observe` 经 LLM 提炼 / `note_store.observe_turn` 逐轮写回），若只在 notes 路径
  二次投影则渲染逻辑两份、SOP 仍吃 dump。改为在 `_action_steps` **全局**渲染
  「工具名（参数摘要）→ 结果节选」⇒ 单一实现、SOP 输入一并变干净。SOP 提炼器对 `steps` 只做
  「拼进 prompt」，其阈值 / 分组键 / 入库逻辑以 `task` 为键、与 step 文本形态无关 ⇒ 可接受。
- **决策 ②「渲染契约：人类可读 + 有界」**：工具名取 `tool_id` **原样**（不发明命名策略 —— 友好名
  映射是展示层政策，loop 不复制）；参数摘要 `key: value` 升序逗号连接，`str` 值超 `_MAX_STEP_VALUE`(80)
  截断、标量直出、**容器型只报 `<type len=N>`（绝不 dump 正文）**；结果节选复用既有 `_output_excerpt`
  (`_MAX_ACTION_EXCERPT`=400)，`{"error":…}` 加「错误：」前缀；整行 `line[:_MAX_STEP_LINE]`(300) 兜底；
  非 `{"tool_id": str}` 形态静默跳过（渲染失败绝不外溢 —— 收尾降级链仍在）。
- **决策 ③「有意义闸门落在存储侧 `observe_turn`」**：判据 `if not ok or not steps: return None`
  （与既有 `ok=False` / 空 slug 守卫同处、同口径、可单测，对任意注入方一致生效）；**不改** `on_turn`
  （其仍无条件调用，由被调方自守）。纯文字回复轮按 `_record_observation` 的 `is_terminal` 早退，
  `steps` 天然为空 ⇒ 判据可判。
- **决策 ④「派生增殖不改」**（用户裁决）：`_derived_turn_topic` 与来源守护**逐字不变**；闸门 ③ 消除
  「纯聊天轮成篇」这一主噪音源，残留多为真实任务轮（每篇一份沉淀、派生链同主题复用）。
- **接口不变**：`TurnObserver` / `turn_observer(task, steps, ok)` 签名与调用点**逐字不变**，只改
  `steps` 的内容渲染；`observe_turn` 签名不变。终止语义 / 事件序 / 转录追加 / 遥测 / 降级链零回归。
- **局限**：① 参数摘要对深层嵌套参数只报类型与规模 ⇒ 可能「看不出改了什么」（按工具语义字段白名单
  属展示层政策，**不**下沉 loop —— 记入台账另议）；② 工具名保留 `tools.` / `mcp.` 命名空间前缀（未美化）；
  ③ 结果节选为 `str()` 形态（dict 结果呈 Python repr 而非 JSON）；④ 闸门以「有无工具动作」为判据、
  **不**判「有无新结论」⇒ 无信息量的工具轮仍写回（覆盖式写同一主题、不增长）。
- **规格**：`doc/openspec/specs/notes/spec.md` —— 「Consult → Build → Update 循环纪律」**MODIFIED**
  （+ 可读正文 + 有意义闸门 clauses；既有 6 Scenario 逐字保留 + 2 新增）；`loop` / `cli-ops` /
  `observability` 规格零改动。接口文档 `03-interfaces/loop-interface.md` §3（行动序列渲染契约）/
  `notes-interface.md` §3；模块 `02-modules/loop.md` §3.4；测试 `04-testing/test-cases.md` §84
  （TC-NOTES-WRITEBACK）；台账 `coding-plan/known-risk.md` §1（E108）。

## ADR-0163：关键事实抽取端质量 —— 同批归并 + 解析失败可观测 + 取值首尾保留（change 0172）

- **背景 / 用户实测（2026-10-08）**：关键事实抽取（G4，change 0155 / ADR-0147）在**抽取端**有三处质量缺口，
  经读代码逐条取证 —— ① **同批同 slug 重复**：`_plan_key_facts` 只做脱敏 + 有界、**不做**批内去重 ⇒
  模型在同一次压实里对「同一实体」给出多条（大小写 / 连字符变体，`slug_entity` 折叠后同 slug）时，后写者
  **覆盖**先写者（同 `id` 幂等覆盖），且额度按落库前条数计 ⇒ 抽取条数被**无声**挤占；② **解析失败静默**：
  `parse_key_facts` 不可解析恒返回 `[]`，与「模型明确给出 `[]`」**不可区分** ⇒ 抽取器**哑失败**、端到端
  只见「无关键事实」，无从判断是模型没抽到还是输出格式崩了；③ **取值只留头部**：`value[:_MAX_FACT_CHARS]`
  为头截断，而关键事实取值常「**头定名、尾定值**」（如 `部署环境：prod-cluster-…-shanghai`）⇒ 尾部信息量的
  部分被丢。
- **决策 ①「同批归并落在 `_plan_key_facts`、只留首条」**：增 `seen: set[str]`（按 `slug_entity` 归一）
  ⇒ 同 slug 后继条**归并**（不入 `plan`）、记入 `deduped`（**独立**于因密钥 `dropped` 的留痕 —— 二者语义不同、
  不可复用同一列表）；**保留首条**（模型通常先给主事实，不引入「优先级」字段）；归并后**条数计额**
  （`break` 仍在**入 plan 后**判 ⇒ 同批重复**不**挤占额度）。跨压实的「重复抽取」**不**走此路，由同实体
  幂等覆盖处理（规格既有、逐字不变）。
- **决策 ②「解析失败在 `extract_with` 闭包补告警、契约零变更」**：`parse_key_facts` 的**返回契约不变**
  （不可解析仍 `[]`）—— 失败判别落在 `extract_with` 的 `_extract` 闭包：`not facts and text.strip() and
  _json_array(text) is None` ⇒ 「有输出但**无 JSON 数组**」才 `warnings.warn`。**合法空数组 `[]`**（模型
  明确无可抽）**不**告警（防误报）。留痕**只报失败事实与文本长度、不含输出正文** —— 正文可能含明文密钥（红线）。
- **决策 ③「`value` 首尾保留、总额度不变」**：新增 `_truncate_value`（`len > _MAX_FACT_CHARS` 时头 / 尾各
  `(_MAX_FACT_CHARS - 1) // 2` 字符、中以 `…` 连接），**只用于 `value`**；`entity` / `ref` 维持头部截断
  （尾部无信息）；总额度仍 ≤ `_MAX_FACT_CHARS`(200)、**先脱敏后截断**次序不变（截断不得使明文逃逸）。
- **被原稿误判为缺陷的项（本 change **不**采纳）**：① 「跨批重复累积」—— 规格既有「同实体幂等覆盖」已按 `id`
  归一，**非**缺陷；② 「`content[:400]` 截断丢信息」—— 全库**无**此代码，真实上界是 `_MAX_FACT_CHARS`(200)
  （已由决策 ③ 处理），`_MAX_ENTRY_CHARS`(400) 只是**入 prompt 的事件节选**（token 有界，非落库形态）；
  ③ **不得**给「长随机串」密钥形态加 URL 白名单 —— 会开密钥外泄口子（红线）。
- **切出**：0173「密钥形态 URL 白名单」**建议不做**（红线）；0174「主题归并」属 L5 组合根职责、非 memory 端。
- **接口不变**：`KeyFactExtractor` / `MemoryStore(key_fact_extractor=)` / `extract_with` / `parse_key_facts` /
  `scrub_key_fact` 签名与调用点**逐字不变**；`KeyFact` 结构不变；脱敏仍**无条件**在 store 侧执行。终止语义 /
  事件序 / 转录追加 / 降级链 / 压实可回滚（同 trace）零回归。
- **局限**：① 首尾保留扩大截断后可见面 ⇒ 对脱敏完备性要求更高（不改脱敏启发式，方向仍 over-redact）；
  ② 归并只消**同批**重复，跨批仍靠幂等覆盖（不合并为「历史值」）；③ 归并丢弃的取值**不进**任何记忆面（有损）；
  ④ 解析失败留痕**不含**模型输出正文（排查须回看 trace，不以牺牲红线换可诊断性）；⑤ 数组存在但元素**全**不合规
  时不告警（`_json_array` 非 `None`）；⑥ `MAX_KEY_FACTS_PER_COMPACT`(8) **未**放宽（同批归并已缓解挤占）。
- **规格**：`doc/openspec/specs/memory/spec.md` —— 「结构化实体抽取（关键事实）」**MODIFIED**
  （+ 同批归并 + 解析失败判别口径 + `value` 首尾保留；既有 8 Scenario 逐字保留 + 3 新增）；接口
  `03-interfaces/memory-interface.md` §3；模块 `02-modules/memory.md`；测试 `04-testing/test-cases.md`
  §85（TC-EXTRACT-QUALITY）；台账 `coding-plan/known-risk.md` §1（E109）。`loop` / `notes` / `cli-ops` 零改动。

## ADR-0164：记忆材料与引用语义 —— 行动序列另立条目 + `ref` 只认 `coeffect:`（change 0173）

- **背景 / 用户实测取证（2026-10-08）**：关键事实抽取（G4，change 0155 / ADR-0147，经 0172 / ADR-0163
  修抽取端质量）在生产落库的 `memory.jsonl` 上复查，24 条 `key_fact` 里 **8 条正常 / 16 条被抹成
  `<redacted>`**。逐条回看那 16 条：其 `ref` 全是模型**自造的出处说明**（`round1:热带水果有哪些`
  / `会话事件` / `证据链第1条` / `分析结论`），**不是** `coeffect:<名称>`；而 `scrub_key_fact` 的判据是
  「有 `ref` ⇒ `value` **一律** `<redacted>`」⇒ **纯自伤**：那些取值**不是**密钥，本可原样保留。
  同时按会话回看材料（该会话的 L2 episodic 条目 = `remember()` 写的 `round N ok` + **回复散文**）：
  **24/24** 条 keyfact 的实体**全部**产自**散文**，无一条来自工具调用或结果 —— 而实体名里出现
  `round 5 执行结果` / `round 6 执行结果`，反证材料里**没有**「做了什么、得到什么」。
- **决策 ①：`ref` 只认 `coeffect:<名称>` 形态，其余**视为无引用**。判据放在 **store 侧**
  （`_is_coeffect_ref`）—— 注入的抽取器**不构成信任边界**（0155 既定原则），prompt 收紧只是辅助。
  「视为无引用」而非「整条丢弃」：正常取值**原样保留**、不落 `ref:` 标签；密钥形态取值仍走既有
  **fail-closed 整条丢弃 + 留痕**（自造引用**不能**为明文密钥背书）⇒ **两个方向都不放松**，
  方向仍是 over-redact。**这一条是「放宽」**：本 change 使**更少**的东西被抹，但**不**使任何
  密钥形态之物逃逸。`_is_coeffect_ref` 同时**覆盖**了旧的「像密钥的 `ref` 弃用」判据（密钥形态
  必然不满足 `coeffect:` 形态）⇒ 一条判据两义，非丢失。
- **决策 ②：行动序列**另立一条** L2 条目（`loop.steps.<trace_id>`），**不**插进既有轨迹条目。
  证据：抽取器对**每条** L2 条目只取前 `extract._MAX_ENTRY_CHARS`(400) 字符入 prompt
  （`build_extract_prompt` 逐条截断后才拼行），而**全部** 24 条 keyfact 的实体都产自轨迹条目的
  **散文** ⇒ 把行动序列插到既有条目**开头**会把那段散文顶出窗口，**很可能把仅有的好结果一起弄坏**。
  另立 ⇒ 两条各占一窗，既有散文抽取**零风险**，材料里也确有「行动与结果」。轨迹条目
  `id`/`tags`/`content` **逐字不变**（`test_memory_namespace` 等既有调用零回归）；行动序列条目与
  轨迹条目**同 `trace_id`**（按 trace 一并可逆）、**同 `session_id`**（压实归组口径一致）、
  `kind` 取缺省 `episodic`（自然成为压实材料）。
- **决策 ③：判据**提为公开**（`looks_like_secret` + 新增 `redact_secrets`），loop 侧复用。**
  loop 直接调 `extract._looks_secret` 会**跨模块私有边界**；`core/memory/__init__.py` 已有
  `REDACTED` 等公开导出的先例 ⇒ 上提后 loop 走 `from core.memory import …`，**依赖方向不变**
  （loop → memory 是既有合法方向）、私有面不破，且判据**只有一处定义**。`scrub_key_fact` 改用
  改名的公开判据 ⇒ **行为逐字不变**（纯重命名 + 新增 `redact_secrets`）。
- **决策 ④：脱敏粒度 = **子串替换**（`redact_secrets`），不是整行抹除。** 行动序列一行是
  「工具名（参数摘要）→ 结果节选」，整行抹除会连**工具名**一起丢，而「做了什么」正是要保留的信息；
  逐 pattern 命中即换 `<redacted>`，保留结构。
- **接口面**：`Loop.remember` 增**仅关键字**形参 `steps: Sequence[str] = ()`（`default.py` 实现 +
  `protocol.py` 声明同步）；缺省 `()` ⇒ **行为与变更前逐字一致**（既有调用与测试零回归）。
  `MemoryStore` / `KeyFactExtractor` / `TurnObserver` / `MemoryEntry` 签名与调用点**逐字不动**。
  新增模块级常量 `_MAX_MEMORY_ENTRY = 2048`（轨迹条目与行动序列条目**共用**，既有 `[:2048]`
  字面量一并改用 ⇒ 单一真源，行为不变）。
- **规格**：`memory`「结构化实体抽取（关键事实）」**MODIFIED**（`ref` 形态判据 + 材料口径指针，
  **既有 10 Scenario 逐字保留** + 2 新增：非 `coeffect:` 形态 `ref` 视为无引用 / 该形态 + 密钥取值
  ⇒ 整条丢弃）；`loop`「执行循环」**MODIFIED**（行动序列另立条目，**既有 21 Scenario 逐字保留**
  + 3 新增：另立一条 L2 条目 / 条目脱敏且有界 / 无工具调用不另立条目）。
- **被本 ADR 更正的先前判断**：起草期初稿把 `memory/spec.md:359` 的「（即「行动与结果」产生的事件）」
  读成「L2 内容须含工具调用序列」的**规范句**、据此称 D-A 是「兑现既有承诺」—— 该括号实为**解释
  episodic 条目是什么**（承「无行动不记忆」）⇒ D-A 是**新增行为**，措辞已在 proposal 更正留痕。
- **局限**：① 脱敏判据是**启发式**（不符合任何 `_SECRET_PATTERNS` 的内联凭据仍会入 L2 并落盘；
  根治需在工具侧打标）② `ref` 只认前缀 ⇒ 未来若要支持 `coeffect:` 之外的真实引用源（如 `env:`）
  需另立 change ③ 每轮多一条 L2 条目 ⇒ 压实材料条数与 token 成本上升（有界）④ `_MAX_ENTRY_CHARS`
  **未**放宽（靠另立条目绕开窗口竞争；单条超 400 字符仍只看前 400）⑤ 既有 16 条错误条目**不**由本
  change 清理（同实体重抽幂等覆盖自然刷新）⑥ 非 `coeffect:` 引用被弃用**不**发 `warnings.warn`
  （视作正常路径；规格只要求「整条丢弃」时留痕）—— 留痕与否可由后续 change 决定。

## ADR-0165：失效关键事实的运维修复 —— 按会话重抽 + 删除 + 备份兜底（change 0174）

- **背景**：ADR-0164（change 0173）修好了**判据**，但**已写坏的条目仍在库里**：生产 `memory.jsonl`
  24 条 `key_fact` 里 **16 条**取值被抹成 `<redacted>`，其 `ref` 是模型自造的出处说明。这些条目**已无
  任何可用信息**，却仍被检索命中并注入上下文（`keyfact.榴莲` 的 `reuse_count` 已达 **36**）⇒ 判据修复
  **止不住既有污染**。前置实证（只读 dry-run，`memory.jsonl` 前后 sha256 一致）：两来源会话的材料仍在
  （episodic 原文已归档 L4，`_all_entries()` 经 `backend.search("")` 读全层）、`build_runtime` 已注入
  `extract_with(_llm_text)` ⇒ 同材料重抽即得**每会话 8 条明文**、零假 `ref`、无 `round N 执行结果` 类垃圾。
- **决策 ①：以**会话**为执行单位，不是以条目为单位。** 材料只能是会话的（该会话的 episodic 条目），
  故「识别 → 重抽 → 清理」三层都按会话组织。无 `session:` 标签的失效条目**不可修复**（无材料可重抽）
  ⇒ **不删**（存疑即留），报告标明。
- **决策 ②：顺序恒为「**先重抽、成功后才清理**」，且删除**排除本次已写入的 id**。** `_write_key_fact`
  的 id 是 `keyfact.<slug>`（同 slug 即**覆盖式更新**）；实证重抽会产出与旧条目同 slug 的实体（`榴莲`
  / `泰国`）⇒ 若按「该会话全部 keyfact id」删除，会把**刚修好的条目自己删掉**。故待删集合 = 该会话全部
  旧 keyfact **减去**本次写入集。顺序上「先落新、后删旧」⇒ 任何一步失败时库里要么旧状态、要么新旧并存，
  **不会**出现「旧已删、新未落」的空窗。
- **决策 ③：清理范围 = 该会话**全部旧** keyfact（不止失效者）。** 实证重抽产出的**实体名与当年不同**
  （`表格显示不出的根因` vs `表格显示问题根因`、`Textual版本` vs `Textual 依赖版本`）⇒ slug 不重合 ⇒
  旧条目**不会被覆盖**；只删「仍呈失效形态者」会留下**死条目**继续参与检索。
- **决策 ④：旧条目**删除**，不迁 L4。** 本仓既有清理口径 `forget()` 是迁 L4（可逆），此处**不沿用**
  —— 实测归档**止不了血**：`read()` → `backend.search()` **无层过滤**（L4 同样进候选），层权重只是
  **加性**项 `_W_LAYER × priority`（L4 `0.2` vs L2 `0.6`，差 `0.08`），而 `reuse_count` / `importance`
  是**乘性**调制 ⇒ `reuse_count=36` 的放大足以盖过加性差距。可逆性改由**备份文件**
  `$CORE_STATE_DIR/memory.repair.<时间戳>.jsonl`（与 `memory.jsonl` 同目录、同格式）承担 —— 一次性 CLI
  进程内的 `EffectTracker` undo 随进程结束即失效，**不能**作为持久可逆性。备份**不引入新明文面**：被删
  条目取值恒为 `<redacted>`（密钥形态取值当初即被整条丢弃、从未落库）。
- **决策 ⑤：三处 **fail-closed**（宁可不修，不可修坏）。** 抽取器**未注入** / 该会话重抽**抛错** /
  备份文件**写入失败** ⇒ 均**不删**（备份失败时已落的新条目保留 —— 它是正确信息，只是旧条目不清理）。
  另：重抽返回**合法空数组** ⇒ 视为**重抽成功**（模型明确无可抽）⇒ 旧条目**仍删**（它们已无信息）。
  待删集合为空 ⇒ 跳过备份与删除（不产生空备份文件）。
- **决策 ⑥：材料口径去**层过滤**。** 复用 `_episodic_groups` 的判据（`kind == "episodic"`）但**去掉**
  `layer == "L2"` —— 当年抽取时它们还是 L2，压实后**已归档 L4**，沿用层过滤会取到空材料。材料口径其余
  部分与当年**逐字一致**（同条目、同 `build_extract_prompt` 每条 400 字符窗口）—— 这是「重抽能复现
  同样实体」的前提。
- **CLI 形态**：`memory repair-keyfacts [--dry-run]`，缺省**执行**（与 `memory maintain` / `evolve
  implement --dry-run` 同族：装配运行时 → 动作 → 打印报表 → 不改变运行态）。`_memory()` 由「只认
  maintain」改为**分派表** `_MEMORY_COMMANDS`。**不**引入自动/定时触发（须另立 change）。
- **规格**：`memory` **ADDED**「失效关键事实的运维修复」（+7 Scenario，落在既有 `memory` 能力内 ⇒
  capability 数不变）；`cli-ops` **MODIFIED**「运维命令集」（+1 Scenario，**既有 9 条逐字保留**）。
- **落点**：`store.py`（`RepairReport` + `repair_stale_key_facts` + `_stale_key_facts` /
  `_material_for_session` / `_group_stale_by_session` / `_repair_session` / `_delete_entry` /
  `_restore_entry` / `_repair_backup_path`）/ `core/memory/__init__.py`（导出 `RepairReport`）/
  `entry.py`（子命令 + 分派表 + 报表）。`protocol.py` / `backend.py` **零改动**（删除走既有
  `MemoryBackend.delete`）；`core.memory` 仍**不** import `core.notes` / `core.loop`。
- **局限**：① 删除是**不可逆的持久动作**（备份文件是唯一回滚路径，且**不自动清理**）；② 重抽结果
  **不确定** —— 同一材料两次调用可能给出不同实体名与取值，产出的新事实**可能少于**旧条目数 ⇒ 修复后
  信息面**不保证等量**；③ 备份文件含旧条目原文，与 `memory.jsonl` 同暴露度（承 ADR-0164 局限①：脱敏是
  启发式）；④ 不可修复类（无 `session:` 出处）**只报告不动作**，永远留在库里；⑤ 只覆盖 keyfact 这一面
  （摘要 / 迹条同类问题不覆盖）；⑥ **不做实体名映射** ⇒ 命名漂移不可避免。

## ADR-0166：修复备份「一次操作一份」——备份/删除提出会话循环（change 0175）

- **背景**：ADR-0165（change 0174）首次**实跑**（生产 2 个会话）当场暴露：`_repair_session` 把「落备份 +
  删除」放在**每会话循环体**内 ⇒ 备份文件数 = 会话数（实落 `memory.repair.20261008-234522.jsonl` 2 行 +
  `…234545.jsonl` 5 行）。两个后果：① `RepairReport.backup_path` 是**标量**，循环里**后写覆盖前写** ⇒ 报告
  只显示**最后一份**，第一份成为**孤儿**（用户回滚时会漏）；② 与规格句「落**一份**备份文件」**不符**。
  附带缺陷：备份失败只阻断**该会话** ⇒ 一次操作可能**部分删除**。
- **决策 ①：一次操作**恰好一份**备份。** 把 `_repair_session` 的**后半段**（备份 + 删除）提出循环 ⇒
  `repair_stale_key_facts` 提为三段式：① **收集**（每会话重抽 + 落新）→ ② **备份**（全部会话待删条目
  **合并**为一份、**共用同一时间戳**）→ ③ **删除**（统一）。`_repair_session` → `_collect_session`
  （返回 `bool`：该会话是否重抽成功），另立 `_doomed_key_facts`（一次扫描求并集）与
  `_backup_then_delete`（备份相 + 删除相）。
- **决策 ②：`doomed` 求值推迟到**全部会话落新之后**。** `written` 本就**跨会话累积**（单例 set、逐会话
  update）⇒ 推迟后 `written` 只会**更大**、`doomed` 只会**更小** ⇒ 只会**更少删**、不会误删。差异仅在
  「会话 A 的新 id 恰好等于会话 B 的旧 keyfact id」这一跨会话同 slug 情形：现状会删，新形态**不删**
  （那条 id 上此刻是 A 会话给出的新值）—— 是**正确的收紧**。
- **决策 ③：备份失败 ⇒ **跨会话一并阻断**（操作级全或无）。** 一份备份就是**整次操作的回滚面**：它没落成
  ⇒ 谁的旧条目都别删（`skipped["backup_failed"] = sorted(report.sessions)`）。判据是「失败的**作用域**是否
  等于操作的**作用域**」：**抽取失败**是**材料级/会话级**（该会话没有可用的新信息，不该因它阻断别的会话）
  ⇒ **保持会话级**；**备份失败**是**操作级** ⇒ 升为全或无。两种失败下**已落的新条目都保留** —— 它们是正确
  的脱敏事实，且 `_write_key_fact` 走唯一写路径、本就有 `EffectTracker` 可撤销。
- **决策 ④：文件名与格式**零改动**。** 仍 `$CORE_STATE_DIR/memory.repair.<时间戳>.jsonl`、每行
  `asdict(entry)` ⇒ 人工回滚口径不变；`RepairReport.backup_path` **保持标量**（此后不再被覆盖，字段无需改形
  ⇒ CLI 打印零改动）。`doomed` 并集为空 ⇒ 不落备份、不删除（不产生空备份文件，承 ADR-0165）。
- **红态证据（实现前）**：新增用例 `test_two_sessions_share_one_backup` **失败** —— 且失败形态比预期更锋利：
  两次调用落在**同一秒** ⇒ **同一路径** ⇒ 第二会话的备份**静默覆盖**第一会话的 ⇒ 文件恰好 1 个但内容只有
  会话 2 的待删条目（**会话 1 的回滚面被覆盖清除**）。另一新增用例 `test_backup_failure_blocks_every_session`
  为**等价守护**（现状的「目录不可写」缺陷对两会话**同时**生效 ⇒ 实现前后皆绿），诚实记之。
- **规格**：`memory` **MODIFIED**「失效关键事实的运维修复」—— 备份句追加「**每次操作恰好一份**（跨会话的
  待删条目**合并**写入、**共用同一时间戳**；SHALL NOT 每会话各落一份）」、失败句改为「⇒ SHALL NOT 删除
  **任何**条目（fail-closed；**跨会话一并阻断**，无部分删除）」；改 1 Scenario（多会话 GIVEN）+ 加 1 Scenario
  （「待删条目跨会话合并为一份备份」）⇒ 7 → **8** Scenario。`cli-ops` / 其余能力**零改动**。
- **落点**：`store.py`（`_collect_session` / `_doomed_key_facts` / `_backup_then_delete` / 三段式
  `repair_stale_key_facts`）。`RepairReport` / `_repair_backup_path` / `_delete_entry` /
  `_group_stale_by_session` / `entry.py` / `core/memory/__init__.py` **零改动**。
- **局限**：① 备份失败即整次不删 ⇒ 一个坏目录（磁盘满 / 权限错）会让**所有**会话都修不成（以「不修」换
  「不错删」，方向恒为保守）；② **已产生的历史多份备份不合并/不清理**（本次实跑那两份是既成事实的回滚面，
  动它们才是风险）⇒ 库里仍存多份旧备份，本 change 只保证**此后**每次操作恰好一份；③ 跨会话同 slug 时
  **最后一个会话胜**（同 slug 只有一条），报告里该 id 只出现一次、用户**看不出**发生了覆盖；④ `doomed`
  并集顺序 = 会话遍历序 × 会话内 `_all_entries()` 序，**不保证稳定**（回滚按行不按序 ⇒ 不影响正确性）；
  ⑤ 承 ADR-0165 全部局限（重抽不确定 / 命名漂移 / 启发式脱敏等）。

## ADR-0167：notes 写回效应闸门 —— 纯读轮不落盘（change 0176）

- **背景**：用户 2026-10-09 实测：逐轮写回仍把**纯读型工具轮**整篇塞进 canonical 知识库
  （`web_fetch` 抓的网页正文、`file_read` 的一次性排查产物）。change 0171 的「有意义闸门」判据是
  `if not ok or not steps: return None` —— 只看 `steps` **是否为空**（挡纯文字回复轮），而
  `loop._action_steps` 对**所有**工具动作一律产出行 ⇒ 「调过 `web_fetch`/`file_read`」即满足写回条件。
- **决策 ①：判据为「本轮含至少一个成功的**写效应**工具动作」（确定性、零 LLM）。** 写效应工具集
  `_WRITE_EFFECT_TOOLS` = `file_write` / `file_patch` / `code_run` / `gate_run` / `install` /
  `uninstall`（文件系统写 / 代码执行 / 质量门禁 / 插件注册表效应）。**不**引入 LLM importance 评分 ——
  与 0171 闸门同处同口径、可单测、无新依赖注入面，且用户实测的垃圾笔记来源**全部**是纯读轮。
  与「无行动不记忆：只沉淀**行动与结果**」一致 —— 「行动」须有**持久化效应**，而非仅「有信息流入」。
- **决策 ②：判据落在存储侧 `observe_turn`（与 0171 同位）。** 对被注入的任意 `turn_observer` 一致生效，
  不改 `on_turn`（其仍无条件调用，由被调方自守）。
- **决策 ③：`loop._action_steps` 不改（架构红线）。** steps 仍**完整**产出（SOP 提炼需要完整行动
  序列）；工具名从行**前缀解析**（`_tool_of_step`：行首至首个 `（`，再剥 `tools.` 前缀）—— 不引入
  loop↔notes 新接口，loop **不** import notes、notes 也**不** import loop。**已否决备选**：loop 侧给
  steps 附带结构化元数据（更稳健，但要改 `TurnObserver` 接口签名、影响所有注入方，超出最小改动面）。
  **容错**：行不以已知工具名开头 ⇒ 保守判定为**无写效应**（宁漏写、不滥写）。
- **决策 ④：写效应动作**失败**不计入（行含 `错误：`）。** 失败标记取自 `loop._summarize_result` 对
  `{"error": …}` 的渲染前缀；`code_run`「成功」与 `gate_run`「通过」**同一条规则**覆盖（都归约为
  「无 `错误：`」）。与「只沉淀**验证过的**行动与结果」一致。
- **红态证据（实现前）**：新增 7 用例**全红** —— 4 条纯读参数化用例（`web_fetch`/`file_read`/
  `context_read`/`list`）+ 写效应失败 + 非工具行形态（`["跑测试", "上线"]`）+ loop 侧纯读轮
  （`test_loop_pure_read_turn_does_not_write_note`，实落 `查一下资料.md`）；写效应正例同期全绿。
- **连带调整（既有用例口径）**：闸门依赖 steps 的**工具行形态**，而 7 个既有 `test_notes.py` 用例、
  `test_notes_pinned_budget.py` 1 例、`test_notes_loop.py` 2 例的 steps 是**散文占位**（`["滚动更新"]`）或
  只读替身（`tools.echo`）—— 均改为**工具行形态的写效应 steps**（断言不变量不变）。新增 `_write_tool()`
  替身（id 落在写效应集内，`coeffects=[]` 以免离线 run 因缺 `CoeffectResolver` 得 `COEFFECT_MISSING`
  而被闸门判为失败）。
- **规格**：`notes` **MODIFIED**「Consult → Build → Update 循环纪律」—— 追加**效应闸门**段（既有 8
  Scenario 逐字保留 + 3 新增：纯读轮不写回 / 写效应失败不计入 / 含写效应轮正常写回）⇒ 8 → **11**
  Scenario。`loop` / `memory` / `cli-ops` 零改动。
- **落点**：`src/core/notes/store.py`（`_WRITE_EFFECT_TOOLS` / `_TOOL_ID_PREFIX` / `_ERROR_MARKER` /
  `_tool_of_step` / `_has_write_effect` / `observe_turn` 闸门）。接口签名、`NoteEntry`、`MarkdownBackend`
  零改动。
- **局限**：① 判据靠**解析 steps 行前缀**（渲染契约的隐式耦合）—— 若 `_action_steps` 行格式变更，闸门
  会静默退化为「无写效应」（保守方向，不滥写）；② 工具名为**白名单快照**，新增写效应型工具须同步
  `_WRITE_EFFECT_TOOLS`（否则该类轮次**静默不写回**）；③ 「上下文变更」型效应（如 `context_write` 若
  存在）不在集内 —— 本 change 只覆盖**持久化**效应；④ `错误：` 判据是**行内子串**匹配，若某写效应的
  **参数摘要**恰含该子串会被误判为失败（方向保守）；⑤ 只覆盖 canonical notes 这一面，memory 侧 keyfact
  抽取**不受本闸门约束**（纯读素材按设计归其沉淀）。

## ADR-0168：记忆质量闭环 —— importance 写入侧闸门 + 复用强化衰减 + 自适应抽取上限（change 0177）

- **背景**：`importance` 字段在检索/遗忘评分里被**消费**（乘性因子），但**写入路径从不生产它** ——
  现有唯一产出点是**压实固化**对**存量**条目打分写回（`_score_importance` / `_write_importance`），
  属**事后修正**而非入库门槛。同时：① 抽取条数上界是**死值** 8（`MAX_KEY_FACTS_PER_COMPACT`），
  长会话被硬性截断；② 遗忘评分对「被检索复用过的条目」不设延缓，好条目与新条目同速衰老。
  三处构成同一个「记忆质量闭环」缺口：**入口不筛、出口不保、容量不随规模伸缩**。
- **决策 ①：写入侧闸门为**可选依赖注入**（`importance_scorer: ImportanceScorer | None`，缺省 UNWIRED）。**
  与 `summarizer` / `key_fact_extractor` / `summary_promoter` 同一「缺省不启用」纪律 —— **缺省时写入
  逐字不变**（不评分、不拒收、不降层、无留痕），由 L5 组合根注入具体评分器。memory 域**不 import**
  任何 LLM/rag 抽象（ADR-0045 依赖方向不变），评分器签名 `(MemoryEntry) -> float` 纯函数。
- **决策 ②：三分支阈值为常量、无 LLM 二次判断。** 分 < `_IMPORTANCE_FLOOR`(0.2) ⇒ **拒收**（不写、
  无效应、`warnings.warn` 留痕，返回 `None`）；`[_IMPORTANCE_FLOOR, _IMPORTANCE_AMBIT)` ⇒ **降层 L4**；
  ≥ `_IMPORTANCE_AMBIT`(0.4) ⇒ 按意向层入库并**写回** `importance`。写回走 `EffectTracker.record`
  （可逆），`trace_id` 取**条目自身 trace** ⇒ 随条目写入一并回滚。
- **决策 ③：降层 = 两步、双 trace（可撤销语义的硬约束）。** `EffectTracker.rollback` 按**逆序**撤销
  ⇒ 若降层的「写入 + 迁移」**同 trace**，回滚会先 `_undo_migrate`（迁回意向层）再 `_undo_write`
  （**删除**条目），条目消失，与「回滚即按**原意向层**恢复」不符。故：先按**意向层** `write`（条目自身
  trace），再 `migrate(意向层→"L4", trace_id=f"gate.{id}")`（降层另记专 trace）；`rollback(f"gate.{id}")`
  只撤销降层 ⇒ 迁回意向层。（`_persist` 从 `write` 提为独立方法，供闸门分支复用。）
- **决策 ④：衰减调制**只**落遗忘评分 `store._decay_score`，不落**检索排序。** freshness 项改为
  `freshness ** (1 / (1 + log1p(reuse_count)))`（复用越多，新鲜度衰减越慢）。`relevance.recency_decay`
  是**检索**（`rank`）与**遗忘**（`_decay_score`）**共用**的函数 —— 若在此处调制会连带改变检索排序，
  故调制必须落在 `_decay_score` **内部**，`recency_decay` / `rank` **逐字不动**。`reuse_count=0` 时
  `1/(1+0)=1.0` ⇒ `freshness ** 1.0 == freshness`（`pow(x,1.0)==x` 逐位相等，无需特判分支）。
- **决策 ⑤：抽取上限自适应、只放宽不收紧。** `key_fact_cap(n) = clamp(ceil(n × 0.25), 8, 16)`
  （`n` = 本次压实聚合的 episodic 条数）。下限取**既有死值 8** ⇒ **任何会话长度下名额都不收紧**；
  `KEY_FACTS_RATIO`/`MIN`/`MAX` 为常量、不引入 LLM 判断。实现面：`_plan_key_facts` 增 `cap` 形参，
  两个调用点（`_extract_key_facts`、`_collect_session`）传 `key_fact_cap(len(...))`；`extract.py` 两处
  `max_facts` 默认值与 `KEY_FACTS_MIN` 对齐；`MAX_KEY_FACTS_PER_COMPACT` 保留为**兼容别名**（语义等于下限）。
- **红态证据（实现前）**：Layer A `ImportError: cannot import name 'KEY_FACTS_MAX'`；Layer B 两条判别性
  用例在旧公式下**红**（99 天龄 + `reuse_count=1`：旧评分 ≈0.017 < 阈值 0.05、新评分 ≈0.11 ≥ 阈值）；
  Layer C `ImportError: cannot import name '_IMPORTANCE_AMBIT'`。新增 14 个测试函数（A 3 定义/10 用例、
  B 5、C 6）共 **21 用例**，全绿。
- **规格**：`memory` **MODIFIED**「记忆遗忘」（新增 reuse 延缓衰减）+ **MODIFIED**「结构化实体抽取
  （关键事实）」（上限自适应）+ **ADDED**「写入侧重要度闸门（importance write gate）」。
  **「温度分层检索」不改** —— 衰减调制只作用于**遗忘评分**，检索排序公式逐字不变（决策 ④）。
- **落点**：`src/core/memory/extract.py`（`key_fact_cap` / `KEY_FACTS_*`）、`src/core/memory/store.py`
  （`ImportanceScorer` / `_IMPORTANCE_FLOOR` / `_IMPORTANCE_AMBIT` / `importance_scorer` 构造形参 /
  `_gate_score` / `_persist` / `write` 闸门 / `_write_importance(*, trace_id)` / `_decay_score` 调制）、
  `src/core/memory/__init__.py`（导出同步）。
- **局限**：① 闸门**不区分来源** —— 内部写（摘要 / 关键事实）亦经闸门；若注入的评分器对短摘要打分偏低，
  可能误拒内部产物（缺省 UNWIRED ⇒ 现状不受影响，但启用后需评分器覆盖内部形态）；② 评分器抛错 /
  返回界外值 ⇒ **降级放行**（保守方向：宁写不拒），选择此方向因「写入失败」比「低质写入」更难恢复；
  ③ 阈值为**常量启发式**（0.2 / 0.4），非数据拟合；④ 衰减调制是**进程内** `reuse_count`（检索强化不落盘
  以避免写放大，见既有实现）⇒ 重启后复用计数归零、延缓效果随之归零；⑤ `key_fact_cap` 的 `MAX=16` 为
  经验上界，超长会话仍受 16 条封顶；⑥ 留痕只报**条目 id**、绝不回显条目正文（密钥红线）。

## ADR-0169：三层会话滑窗 —— 短（原文）/ 中（滚动摘要）/ 长（会话摘要）按比例压缩（change 0178 / 账本 E115）

- **背景**：日常会话记忆有两个**并存**缺陷。① **摘要从不进 prompt**：`MemoryStore.summary_for` 唯一
  调用者是 CLI（`entry.py`），会话摘要产出了也**从不注入任何 LLM 请求**；`planner._system_prompt` 没有
  「历史摘要」块。② **日常会话根本不产摘要**：`_maintain` 只做 `forget()` + 冷路径，`memory.compact()`
  的三处调用者（CLI / Web「压缩本会话」/ loop `_compact`）在无工具的日常聊天里**恒不触发**（`_should_compact`
  的轮数维度取自**每轮工具步计数** `ctx.rounds`）。③ **窗口静默截断无补偿**：`_load_history` →
  `transcript.tail(sid, history_turns, max_tokens=token_budget//2)` 从新到旧累计、超预算即 `break` ⇒
  **丢最旧、无摘要替换** ⇒ 超 `history_turns` 轮即失忆。④ **无分层**：单条固定 `history_turns=20` + 单个
  `token_budget//2` 切片。
- **决策 ①：三层语义与归属。** 短层 = 最近 `short_turns` 轮**原文逐字**（转录行）；中层 = 紧随其前的
  `mid_turns` 轮 → **模型滚动摘要**（既有 `Summarizer` 通道，产物 `compaction.mid.<session>`）；长层 =
  **会话整体摘要**（既有 `compaction.summary.<session>`，**不新增产物**）。中层材料取**转录**而非 L2 轨迹
  条目 —— 轨迹行只含 `round N ok/failed` + 回复散文、**不含用户提问**，且 `_commit_summary` 会把来源迁 L4。
- **决策 ②：策略与机制分离。** 配额（纯函数）落新模块 `src/core/context/window.py`
  （`WindowPlan` + `plan_window`，只依赖 stdlib、零 I/O、零模型调用）；切分（机制）落
  `TranscriptStore.window()`。方向由依赖规则决定：`context/compactor.py` 已 import `core.memory`，
  `memory.transcript` **不得**反向 import `core.context`（ADR-0045）⇒ `window()` 只收**裸 int**，
  解包由 `default.py` 做。
- **决策 ③：比例配额为常量、不新增配置键。** 短 / 中 / 长 = `0.5 / 0.3 / 0.2`（模块常量
  `_SHORT_SHARE` / `_MID_SHARE` / `_LONG_SHARE`，与 `_ROUND_THRESHOLD` / `MAX_SUMMARY_CHARS` 同纪律）；
  历史预算沿用既有 `token_budget // 2` 口径。clamp：轮数或预算非正 ⇒ **全零**（关闭回灌）；分层时
  `short ≥ 1`、`short + mid ≤ history_turns`、配额随总量**单调不减**。`loop.history_turns` 仍是**唯一**
  用户可调旋钮（三层配比随之等比缩放）。
- **决策 ④：中层物化 = 只读转录桩 → 既有摘要通道。** `MemoryStore.summarize_slice(session_id, entries,
  *, max_chars)` 收**临时桩**（不在库中，**绝不落库**），经**既有摘要器**滚合并为**一条**
  `compaction.mid.<session>`（`source="compaction"`、`kind="semantic"`、`trace_id` 同 id）；写前无条件
  `redact_secrets`、有界 `max_chars`；**不 migrate** 任何来源（区别 `_commit_summary`）。`build_prompt`
  （「现有摘要」槽 + 逐条复述）**零改动**即复用 ⇒ 满足「复用既有 summarize 通道、不新造 prompt/格式」。
  未注入摘要器 / 桩为空 / `max_chars` 非正 ⇒ 返回 `None`、**零写入零效应**。
- **决策 ⑤：触发点 = 既有 off-loop 维护节拍加会话参数。** `_maintain(trace_id, session_id="")` 四步、
  各自 `try/except` 降级留痕（`maintenance_failed`）：① `compact(session_id=…)`（仅 `session_id` 非空；
  **首次**让日常会话路径产出 `compaction.summary.<sid>`）② `_materialize_mid(session_id)` ③ 既有
  `forget()` ④ 既有冷路径。调用点改 `asyncio.to_thread(self._maintain, trace_id, ctx.session_id)`
  （仍 off-loop，承 ADR-0157）。**不改** `_should_compact`（其轮数维度是死的属既有账 E96 局限）。
- **决策 ⑥：摘要作为独立系统块注入，不折入 `history` / `messages`。** `LoopContext` 增两个独立字段
  `summary_long` / `summary_mid`（承 notes / pinned_notes 的分列先例）；`_system_prompt` 块次序：
  系统提示 → 宪法规则 → 常驻笔记 → **历史摘要（长期）** → **历史摘要（中期）** → 相关事实 → …；
  `.strip()` 非空才加块 ⇒ 空时 prompt **逐字不变**。token 计入 `_context_tokens`（**非空守卫**，
  守护 `estimate_tokens("") == 1` 陷阱）⇒ 无探针的纯 callable planner 亦可见；与探针 `max()` 取大、**不双计**。
- **冷会话逐字兼容（硬约束）**：`tiered = bool(summary_long or summary_mid)` ⇒ 冷会话
  `plan_window(tiered=False)` 返回「短层 = 全部 `history_turns` + 全部预算、中层零」⇒ 请求**逐字等于今天**。
  门控与 `_load_history` **完全同形**：`history_turns<=0` / `session_id==""` / 未注入 `transcript` ⇒
  不读摘要、不注入。
- **落点**：`src/core/context/window.py`（新增）、`src/core/context/__init__.py`（导出）、
  `src/core/memory/transcript.py`（`_truncate_newest` 提取 + `window()`）、`src/core/memory/store.py`
  （`_entry_by_id` / `mid_summary_for` / `summarize_slice`）、`src/core/memory/protocol.py`（Protocol 同步）、
  `src/core/loop/protocol.py`（两字段）、`src/core/loop/planner.py`（两条件块）、`src/core/loop/default.py`
  （`_window_plan` / `_load_summaries` / `_load_history` / `_materialize_mid` / `_maintain` / `_context_tokens`）。
- **规格**：`loop` **MODIFIED**「执行循环」（窗口条款 → 三层滑窗；维护节拍条款 → 四步）；
  `context` **ADDED**「三层窗口比例分配」；`memory` **MODIFIED**「记忆压实」+ **MODIFIED**「对话转录持久化
  （非记忆层级）」。既有 Scenario 全部逐字保留。
- **局限**：① **成本** —— 日常会话路径每节拍（既有 900s 节流）最多 ~2–3 次额外模型调用（会话压实 +
  中层摘要），是「摘要从不进 prompt」修复的必然代价，由节流 + **中带为空即不调用**缓解；② **短层在分层
  激活时收窄**（缺省 20 → 短 10 轮原文，有意：预算有限，更老原文由摘要承接）；③ **CJK 欠估不修**
  （`estimate_tokens = len//4`，承 ADR-0144 明文的「不改编、另议」+ 账 E96/E97）⇒ 短带实际容纳原文偏多、
  整轮预算闸门偏晚；④ **密钥面** —— 中层摘要输入是会话原文（可能含密钥），产物写回 L2 前 `redact_secrets`
  （方向 over-redact）；「对话原文进 LLM 请求」是既有面（ADR-0147 局限④）；⑤ **热路径读放大** ——
  `perceive` 每轮新增两次全库扫描（`summary_for` / `mid_summary_for`），与既有 `read()` 同量级，且仅在
  `history_turns>0 ∧ session_id ∧ transcript ∧ memory` 时才读；⑥ **重复暴露** —— 中层产物会同时经
  `read()` 进「相关事实」块，与新增「历史摘要（中期）」块**可能重复**，本 change **不去重**（若实测明显另立
  账「压缩产物从事实检索面排除」，参照 `exclude_source_prefixes`，`("beast.",)` 红线不动）；⑦ **节拍实例级、
  会话无关** —— 多会话进程中每节拍只有「正巧活跃」的会话被刷新（可接受）；⑧ `_should_compact` 的「轮数维度
  是死的」**仍未修**（E96 局限②）—— 本 change 走 `_maintain`，不改 `_should_compact`。

## ADR-0170：失败经验的独立沉淀面 —— 轮级失败另立 L2 条目 + 压实材料排除（change 0179 / 账本 E116）

- **背景**：`remember()`（`loop.default`）每轮只写两条 —— 轨迹条目（`tags=["loop","trajectory"]`，散文里
  **含** `round N failed <error>` 行）与行动序列条目（`tags=["loop","steps"]`）。失败**没有**独立判据
  （全 `src/` 无任何 `fail*`/`error` 标签）⇒ 「失败经验」无法作为**一类检索对象**。同时
  `SopExtractor.observe` 对 `ok=False` **直接丢弃**、docstring 自陈「教训沉淀走 **memory/evolution 通道**」
  —— 而该 memory 通道**从未存在**（`Crystallizer.dissolve` 的 `["dissolved","lesson"]` 条目在 `src/` 内
  无调用方；evolution 侧对 memory **只写不读**，`Diagnoser` 只吃 `Trace.success`）。更糟的是：压实材料
  唯一来源 `_episodic_groups()` 只按 `kind=="episodic" and layer=="L2"` 筛、**无 tags 判据** ⇒ 失败轮
  条目必被摘要吸收，随即由 `_commit_summary` 迁 L4（检索权重 0.6 → 0.2），失败证据被**摘成中性总结**。
- **决策 ①：另立第三条条目，既有两条逐字不变。** `failed=True` 时在 `loop.<trace>` / `loop.steps.<trace>`
  之外写 `loop.failure.<trace_id>`（`layer="L2"` / `kind="episodic"` / `tags=["loop","failure"]` /
  同 `trace_id` 同 `session_id` / `source=self._source`）。**另立而非合并**——同 ADR-0164（行动序列）理由：
  抽取器对每条 L2 条目只取前 400 字符入 prompt，合并会把既有散文顶出窗口。
- **决策 ②：范围＝轮级失败，且 `remember` 三参数**（`failed` / `reason` / `task`，均 keyword-only、缺省
  ⇒ 逐字一致）。轮级失败＝**终止动作失败** / **轮次或 token 预算终止**（`limit_reason`）/ **推理产出不可解析**
  （`turn_failed`）；调用点即 `failed=bool(limit_reason) or turn_failed`。**轮内自愈的工具失败不入**失败条目
  （仍在行动序列条目里）——「失败轮」而非「失败步」是用户 2026-10-10 裁决的口径，避免 ReAct 自愈过程被记成失败。
- **决策 ③：豁免判据落 `_episodic_groups()`，用 **tag** 而非 source 前缀。** 新增模块常量
  `_PRESERVE_TAGS = frozenset({"failure"})` + 该函数内一处 `continue`。选此处因它是打分（`_score_importance`）、
  摘要（`summarizer`）、关键事实抽取（`_extract_key_facts`）**三者的唯一材料源** ⇒ 一处排除三处生效。
  选 **tag** 而非 source：`rank` / `_decay_score` **完全不看 tags** ⇒ 零排序副作用；而 `source` 是命名空间
  （`loop` / `beast.<id>` / `pet`），动它等于动 `exclude_source_prefixes=("beast.","pet")` 红线（phase-26）。
- **决策 ④：只豁免压实，**不**豁免遗忘（有界）。** `forget()` **逐字不动** ⇒ 失败条目仍按自然衰减
  （`_FORGET_THRESHOLD=0.05`，零复用下 ≈19 天）归档 L4。**不新增条数上界常量**——有界性由既有遗忘曲线承担
  （用户裁决②）。压实豁免 ≠ 遗忘豁免，二者在 `store` 内是两条互不相干的路径。
- **决策 ⑤：注入面零改动。** 不新增 planner 块、不加上下文预算记账、不动 `_system_prompt` 次序 ——
  失败条目靠**既有按相关度检索**命中（用户裁决③）。故本 change 不改 `context` / `LoopContext`。
- **决策 ⑥：内容＝任务 + 原因 + 失败轮次 + 失败动作，逐行脱敏、整体有界。** 新模块级纯函数
  `failure_digest(trajectory, steps, *, reason="", task="")`：首行 `任务：{task}`（非空才加，有界
  `_MAX_STEP_LINE`）、次行 `失败：{reason}`（空 ⇒ 恒定兜底 `_FAILURE_REASON_FALLBACK`）、随后复用
  `_trajectory_line` 渲染 `ok is False` 的轮次行、再追加 `steps` 中含 `_FAILURE_STEP_MARK`（`"错误："`）的行；
  逐行 `redact_secrets`、整体截断 `_MAX_MEMORY_ENTRY`（与 `loop.steps` 条目**同源纪律**）。**`raw_output` 不入**：
  ADR-0161 明定其 SHALL NOT 进记忆，失败条目不得成为旁路。判据用 `item.get("ok") is False`（**不是** falsy 判断）
  —— 末条合成的 `{"reply": ...}` 无 `ok` 键，用 falsy 判断会把终止回复误当失败轮。
- **红态证据（实现前）**：Layer A `ImportError: cannot import name 'failure_digest'`；
  Layer B 缺失 `loop.failure.*` 条目；Layer C `test_compact_skips_failure_entries_but_archives_plain_ones`
  在旧 `_episodic_groups` 下**红**（`seen == [['e0','loop.failure.t1']]`）。三层共 **18 用例**（A 5 / B 10 / C 3），全绿。
- **规格**：`loop` **MODIFIED**「执行循环」（本轮失败时记忆步**再另立一条** `loop.failure.<trace_id>`；未失败 ⇒ 不写）
  + `memory` **MODIFIED**「记忆压实」（压实材料 SHALL 排除带 `failure` 标签的条目；**遗忘路径不受此豁免**）。
  既有 Scenario 逐字保留：loop 36 → 39、memory 记忆压实 17 → 19。`skills` **不动**——失败仍不进 SOP，
  本 change 让 `sop.py` docstring 承诺的那条通道**第一次真实存在**。
- **落点**：`src/core/loop/default.py`（`_FAILURE_REASON_FALLBACK` / `_FAILURE_STEP_MARK` / `failure_digest` /
  `remember` 三参数 + 第三条写入 / 调用点传参）、`src/core/loop/protocol.py`（`LoopPlugin.remember` 签名同步）、
  `src/core/memory/store.py`（`_PRESERVE_TAGS` + `_episodic_groups` 一处 `continue`）。
- **局限**：① 只覆盖**轮级失败**；轮内自愈的工具失败不入失败条目（仍在 `loop.steps` 条目里）——按用户裁决；
  ② **记忆面 → 诊断面仍无桥**：`Diagnoser` 只吃 `Trace.success`、`src/core/evolution/` 对 memory **只写不读**
  ⇒ 失败条目目前只服务**检索/上下文**，**不驱动进化**（另立账）；③ 失败条目最终仍会被**遗忘**归档 L4
  （`_FORGET_THRESHOLD=0.05`，衰减缓慢）；④ 用户**任务原文首次进入 L2 记忆面**（为让条目自解释、可被检索命中）；
  与转录 / notes 同源、逐行脱敏；⑤ 若注入 `importance_scorer`（生产缺省 UNWIRED，见 `runtime.py:384-393`），
  失败条目仍受写入侧闸门约束（可能降层/拒收）；本 change **不豁免**（不触碰 0177 的闸门语义）；
  ⑥ 失败条目**不进摘要** ⇒ 会话整体摘要不含失败内容；失败信息仍可经**同轮的轨迹条目**进入摘要
  （有意：摘要不该被失败噪音主导）；⑦ 跨会话「同类失败」仍只能靠语义相似命中
  （`loop.failure.<trace_id>` 按 session 隔离读取）；⑧ 运维修复的按会话重抽材料
  (`_material_for_session`, **全层**判据) **仍含**失败条目 ⇒ 理论上可从失败条目抽 key_fact（仅运维触发，不落常规路径）。

## ADR-0171：语义记忆去重 —— 提升产物退出 Consult 命中面（change 0180 / 账本 E117）

- **背景**：**同一份会话摘要在同一次请求里经两条通道重复注入**。通道 A（记忆侧）：`loop.default` 每轮
  `summary_for(session_id)` 读 L2 条目 `compaction.summary.<sid>`（`source="compaction"`）→ `ctx.summary_long`
  → planner「历史摘要（长期）」块（**全文**、滚动最新）。通道 B（笔记侧）：`runtime._promote_summary`
  （半自动唯一生产接线）→ `promote_session_summary(..., pin=False)`（`notes/promote.py`：正文即
  `## 会话摘要（提升自会话 sid）\n\n{summary.content}`）→ canonical 笔记 `session-<slug>`
  （`source="notes.promote"`）→ `NoteStore.digest()`（`consult()` 命中节选 + `list()` 全量清单标题）
  → `ctx.notes` → planner「相关笔记」块。⇒ 提升产物是**摘要的副本**（同一份内容的派生），半自动路径把它当
  「知识条目」注入 prompt，与记忆侧**当前滚动摘要**同场 —— 既重复 token，又让**陈旧冻结快照**与**最新摘要**
  并列（语义噪声）。用户 2026-10-10 复盘选定此账为 ①。
- **决策 ①：让位方向＝提升产物退出 Consult 命中面，记忆侧长期摘要块留任。** 两条通道都可让位，但**记忆侧**的
  长期摘要块**每轮在场且持续滚动最新**（会话连续性的承载体，0178 三层滑窗的锚），**notes 侧**的命中面是
  **词法触发**（任务不命中即缺席）且内容是**提升时刻的冻结快照**：让位方应是**信息更弱**的一侧（用户裁决①）。
- **决策 ②：退出粒度＝只退「命中的笔记」节选，「笔记清单」标题保留。** 提升产物**不再**以**正文节选**进命中面，
  但仍以**标题**在清单在场（存在性可见 ⇒ 操作者/模型仍知「本会话有留档」；digest 契约最小改）。用户裁决②。
- **决策 ③：判据落 `source`，非 `tag`。** 新增模块常量 `_ARCHIVE_SOURCES = frozenset({PROMOTE_SOURCE})`，
  `digest()` 命中集合加一处来源过滤（`note.source not in _ARCHIVE_SOURCES`）。选 **source** 而非 tag：source 是
  **canonical 内持久字段**且已是**来源守护面**（`notes.turn` / `notes.promote` 的覆写判据），而 tags 是**人工可编辑**
  的 front-matter（抹掉即排除失效）。同 0179 选 tag 的**反向**理由 —— 0179 怕动 source 触碰 `exclude_source_prefixes`
  红线（那是 **memory** 命名空间），此处 source 是 **notes** 内自有字段，无此耦合。
- **决策 ④：排除只落在 `digest` 注入面；`consult` / `search` / `list` / `pinned_digest` 口径逐字不变。**
  `digest` 是**注入**面（进 prompt），`consult`/`search` 是**检索**面（CLI `notes search` 仍须搜得到）。
  ⇒ 「排除仅落在 digest」（不变量 I4）。**显式**提升路径（CLI `notes promote`、缺省 `pin=True`）**正文仍每轮
  经常驻块在场**（`notes.md` §3.5.1 红线：操作者须 review 后再提升；跨会话语义所需）——本 change 只去掉其
  **节选**重复，正文不动（局限①）。
- **决策 ⑤：loop / memory 零改动。** 去重完全落在 notes 的注入面：`default.py` / `planner.py` / `protocol.py` 与
  `memory/` 逐字不动。⇒ 会话侧结构保证「历史摘要（长期）」块仍是该会话摘要的**唯一 prompt 通道**（不变量 I6）。
- **决策 ⑥：为何不做会话级去重（只在本会话内排除）。** notes 层**不得**接受会话维度 —— 这是红线，且
  `tests/test_session_isolation.py` 参数化盖住 `digest`/`pinned`/`pinned_digest`/`pinned_overflow`/`set_pinned`
  ⇒ 去重只能按**类别**（来源）而非按会话。「本会话的提升产物、在他会话仍作为命中节选在场」在类别判据下**不成立**
  —— 任一会话的提升产物一律不进命中面（是**更保守**的排除面）。
- **红态证据（实现前）**：`test_store_digest_excludes_archived_source_from_hits` /
  `..._even_when_pinned` 在旧 `digest` 下红（命中节选仍含提升正文「先备份再滚动更新」）；
  `test_notes_loop` / `test_memory_summary_promotion` 端到端红（`ctx.notes` / `digest` 含提升正文）。
  **`test_..._consult_search_list_unchanged...` 生而绿**（守不变量 I4，非驱动变更）。三层共 **6 用例**（A 3 / B 2 / C 1），
  全绿；全量基线 **2119 → 2125**。
- **规格**：`notes` **MODIFIED**「Consult → Build → Update 循环纪律」（Consult 的**命中节选面** SHALL 排除**归档
  来源**笔记；此类 SHALL 只以**清单标题**在场，正文 SHALL 不注入；`consult`/`search`/`list` 检索语义 SHALL 逐字不变）
  + `notes` **MODIFIED**「会话摘要提升（promotion）」（半自动产出定位＝**归档留档物**，正文不进 prompt 命中节选，
  仅以清单标题在场，可经操作者**显式 `pin`** 后由常驻通道在场；显式路径 `pin=True` 语义不变）。既有 Scenario 逐字
  保留：notes 39 → 42（+3 Scenario）。`memory` / `loop` **不动**（契约无变化）。
- **落点**：`src/core/notes/store.py`（`PROMOTE_SOURCE` 公开常量 + `_ARCHIVE_SOURCES` + `digest()` 一处过滤）、
  `src/core/notes/promote.py`（`from .store import PROMOTE_SOURCE`，删本地字面量 `_PROMOTE_SOURCE`，两处引用替换
  —— 单一真源，无环：promote → store 单向）。
- **局限**：① **显式**提升仍存在「本会话内」双在场：常驻块（冻结全文，跨会话语义所需，规格明文授权）与
  「历史摘要（长期）」块（滚动最新）并列 —— 本 change 只去掉其**节选**重复，不去正文（去正文＝拆掉显式路径的
  跨会话用途）；② 提升产物仍以**标题**占 `_MAX_DIGEST_CHARS`(1200) 预算（用户裁决②：存在性保留）；
  ③ 判据依赖 canonical 内 `- source:` 行：操作者手工删该行即排除失效（canonical 可编辑的固有面）；
  ④ 未做「同源去重」的一般化：`key_fact` vs 笔记结论（②）、`observe_turn` 写回 vs `loop.<trace>` 条目（③）仍属另账
  —— 本 change 只闭 ①。

## ADR-0172：写入侧重要度闸门的生产接线与内部产物豁免面（change 0181 / 账本 E118）

- **背景**：写入侧重要度闸门的**契约与实现齐备** —— `ImportanceScorer` 契约（`memory/store.py:74`）、
  构造形参（`:173`/`:182`）、闸门（`write()` 先评分再落库）与 `_gate_score`（UNWIRED / 抛错 / 界外三态降级）
  全在，但 **`runtime.py` 构造 `MemoryStore` 时无 `importance_scorer=` 实参** ⇒ 生产环境该闸门**永远**走
  「UNWIRED ⇒ 不评分」路径（同 `summarizer` / `key_fact_extractor` 早已组合根注入相对照，这是**唯一**漏接的
  记忆接缝）。同时闸门**对全部经 `write()` 的条目评分**，而**内部派生产物**同样过闸门：会话摘要与中层摘要
  （`source="compaction"`）、上下文压实产物（`source="context"`）、结构化关键事实（`source="extraction"`）
  —— 一旦注入 LLM 评分器，一条**由系统管道从已准入材料派生**的摘要就可能被判低价值而拒收/降层 ⇒
  ADR-0168 局限①由「理论风险」变为**真实路径**。
- **决策 ①：评分器经工厂注入，接缝与 `summarize_with` / `extract_with` 同形。** 新模块
  `src/core/memory/importance.py` 提供 `score_with(llm: Callable[[str], str]) -> ImportanceScorer` —— memory
  **不 import 任何 LLM / rag 抽象**（ADR-0045 单向），prompt 文本属 memory 域，模型调用由 L5 组合根注入
  （复用既有 `_llm_text` 闭包，摘要/抽取/补丁/评分**四条** DI 接缝同一来源）。
- **决策 ②：失败方向恒为放行 —— 工厂不兜底、不 clamp。** 输出无可用数值 ⇒ 抛 `ValueError`（交闸门既有异常
  路径降级放行）；界外值 ⇒ **原样返回**（交闸门既有界外路径）。工厂内 clamp/兜底会把「模型没给分」静默成
  「给了 0 分」而**误杀**条目 —— 与 `_gate_score` 的「界外/异常 ⇒ 不评分」口径一致。异常消息**只含输出长度**，
  绝不回显正文（密钥红线）。
- **决策 ③：豁免面按 `source` 判据，与 `_ARCHIVE_SOURCES` / `_PRESERVE_TAGS` 同一「模块常量排除面」惯用法。**
  `_GATE_EXEMPT_SOURCES = frozenset({"compaction", "context", "extraction"})`。选 **source** 而非 kind：误杀
  风险来自「**谁**产生了它」（系统管道派生 vs 有机写入），而 `kind`（episodic/semantic）是**内容分类**——
  摘要/中层摘要/关键事实皆 semantic，若豁免 semantic 则未来**有机** semantic 写入（人工/导入）也被豁免。
- **决策 ④：豁免 = 只缩小评分面，不引入新分支。** `write()` 单行：
  `score = None if entry.source in _GATE_EXEMPT_SOURCES else self._gate_score(entry)`。`score is None` 已由既有
  路径处理为「不评分、不拒收、不降层、不写 `importance`」（与 UNWIRED 逐字同路径）⇒ 零新增行为分支。
  `_gate_score` / 阈值常量 / 迁移与写回路径**逐字不动**（豁免在**调用点**短路，不进打分器）。
- **决策 ⑤：配置开关缺省关，接线零扰动。** 新键 `memory.importance_gate`（`ConfigSpec`，default=False，
  ADVANCED，`map_to="memory.importance_gate"`）；`_KNOWN_EXTRA_SECTIONS` **不动** —— `_known_sections()`
  已并入「ConfigSpec 声明段的 `map_to` 前缀」，声明段自动进白名单，故 `memory:` 段不报「未知配置段」。
  独立访问器 `importance_gate()`（同 `history_turns()` 先例），取值归一与 feature flag 同集、集合外归一为
  **关闭**（非结构化段不阻断启动 ⇒ 方向恒为「不评分」）。`runtime`：`importance_scorer=score_with(_llm_text)
  if config.importance_gate() else None` ⇒ 缺省与变更前**逐字一致**。
- **决策 ⑥：loop / context / notes / evolution 零改动。** 豁免面与接线只落 memory 与组合根；
  `evolution` 经 `MemoryBackend.put` 直写、`notes` 走独立存储 ⇒ 二者既不被本闸门评分、也不受豁免面影响。
- **红态证据（实现前）**：`test_gate_exempts_internal_derived_sources`（3 参数）在旧 `write()` 下红
  （恒低分 ⇒ 派生条目被拒收/降层）；`tests/test_memory_importance.py` 全文件导入即红（模块不存在）；
  `test_spec_declares_importance_gate` / `test_build_runtime_wires_scorer_when_enabled` 在旧配置面下红
  （`importance_gate` 属性不存在 / 组合根不注入）。**`test_gate_exempt_face_does_not_cover_organic_writes`
  生而绿**（守豁免面不覆盖有机写入，非驱动变更）。三层共 **21 用例**（A 5 / B 9 / C 7），全绿；
  全量基线 **2125 → 2146**。
- **规格**：`memory` **MODIFIED**「写入侧重要度闸门」—— 追加「**内部/派生产物豁免**：条目 `source` 属豁免面
  ⇒ SHALL NOT 经评分（不拒收、不降层、不写 `importance`），其写入 SHALL 与该条目不注入评分器时逐字一致」
  + 2 Scenario（内部派生产物豁免评分 / 非豁免来源仍受评分）。既有 6 Scenario 逐字保留：memory 87 → 89
  （+2 Scenario）。`loop` / `context` / `notes` / `configuration` **不动**（配置键属接线细节，归本 ADR）。
- **落点**：`src/core/memory/importance.py`（新：`score_with` + `build_score_prompt` + 首个数值解析）、
  `memory/store.py`（`_GATE_EXEMPT_SOURCES` + `write()` 一处短路 + docstring）、`memory/__init__.py`（导出）、
  `configuration/manager.py`（`ConfigSpec` + `importance_gate()`）、`runtime.py`（接线 + import `score_with`）。
- **局限**：① 豁免面按 `source` 判据 —— **新增派生来源须同步登记**（漏登记 ⇔ 该来源被评分），
  由 `test_gate_exempt_face_is_the_pipeline_sources` 钉住常量内容以制造同步摩擦；② 评分器为**逐条目** LLM 调用
  ⇒ 开启后写入延迟随条目数上升（受 `_MAX_SCORED_PER_COMPACT`=20 口径约束于压实路径，**不**含通用 `write()` 面）；
  ③ `evolution`（`MemoryBackend.put` 直写）**不**过闸门 ⇒ 既不被评分，也不受豁免面保护（其写入无评分语义）；
  ④ 开关为**生产缺省关**：本 change 只闭「接线缺口」，闸门在生产是否常开属运行策略（LLM 成本 vs 记忆质量的
  权衡），未在本 change 决策；⑤ `_flag` 归一为**宽松**（集合外 ⇒ 关闭而非阻断启动）：与非结构化段「未做校验」
  口径一致，代价是 `memory.importance_gate: maybe` 这类笔误**静默关闭**（方向落在安全侧：不评分）。

## ADR-0173：压实触发的诚实化与配置注入（change 0182 / 账本 E119）

- **背景**：`Compactor.should_compact(self, rounds, token_used, budget)`（`context/compactor.py`）参数写作
  `rounds`、判据写作「轮数达到阈值」，但实参是 `ctx.rounds`（`loop/default.py:452` 触发点），而
  `LoopContext.rounds` 是**本轮内已记账的工具动作步数**（`observe()` 内自增；`perceive()` 每用户轮重造
  `LoopContext` ⇒ 每轮自 `0` 起算）。两个后果：① **命名撒谎** —— 读者据「轮数」推断，会误判触发时机与
  `loop.max_rounds` 的关系（`known-risk.md` E96 另注即此）；② **该维度事实上是死的** ——
  `_ROUND_THRESHOLD = 10` 与 `loop.max_rounds` 缺省 `10` **恰好相等**，而循环顶在
  `ctx.rounds >= max_rounds` 时先 `break` ⇒ 触发检查点**永远等不到** `rounds == 10`，唯一活维度只剩 token
  预算；且阈值是模块常量、**无配置键** ⇒ 用户无法把它调到上限以下让该维度生效。
- **决策 ①：诚实化止于「触发面」，`LoopContext.rounds` 不改名。** 压实器侧一律改口「工具步数」：
  形参 `rounds` → `steps`、常量 `_ROUND_THRESHOLD` → `_STEP_THRESHOLD`、构造 kwarg
  `round_threshold` → `step_threshold`、docstring/异常文案同步。**不**改 `LoopContext.rounds` 字段名：
  它是公开 dataclass 字段，被 planner 提示装配、事件载荷（`step_completed.round`）、观测面与多处断言引用，
  改名是**跨模块重命名**、超出本条 change 的局部化边界（P3）。该事实**写进规格条款**
  （「`ctx.rounds` —— 每轮自 `0` 起算，**非**对话轮数」）而非留在代码注释 ⇒ 下一位读者在规格上就能看到。
- **决策 ②：阈值默认 `6`，让步数维度**能**提前触发。** 触发检查在 `observe()` 之后（此时 `ctx.rounds >= 1`），
  终止判据是 `ctx.rounds >= max_rounds`（缺省 `10`）⇒ 阈值**必须严格小于**上限才可能提前触发；缺省 `6`
  相对 `10` 留 4 步余量：长工具链任务能在中途压实，短任务（步数 < 6）不被拖进压实（每次压实含 LLM 摘要，
  有真实成本）。阈值 `>= max_rounds` 是**合法退化配置**（语义仍是「至少压实一次」，只不再提前），故
  **不**做跨键校验 —— 该退化行为写进规格 Scenario，不留暗坑（与同段三键「非法即阻断」口径的**有意不同**：
  这里没有「非法」，只有「不提前」）。
- **决策 ③：默认值两地各一份 + 测试钉住一致性。** `configuration` 不得 import `context`（分层方向），
  反向 import 只为拿一个默认值不划算 ⇒ `_DEFAULT_COMPACT_STEPS = 6`（`manager.py`）与 `_STEP_THRESHOLD = 6`
  （`compactor.py`）**同值两地**，先例 `_DEFAULT_PERMISSION_MODE` / `_DEFAULT_HISTORY_TURNS`。
  以 `test_config_default_matches_compactor_default` 把它钉成**受门禁约束的两地**（而非侥幸同值）。
- **决策 ④：每轮至多压实一次 —— 执行态标记置于 `astream` 局部，不进 `LoopContext`。** 阈值小于上限时
  `步数 >= 阈值` 在阈值步之后**步步为真** ⇒ 无闸门则一轮内最多 `max_rounds - threshold + 1` 次 `_compact`
  （每次含 LLM 摘要 + 关键事实抽取）—— 成本放大且语义重复（同轮同份历史被反复摘要）。故
  `astream()` 循环外置局部 `compacted = False`，触发点改 `if not compacted and self._should_compact(ctx)`，
  压实后置真。**不进 `LoopContext`**：它是本轮**调度决策**（执行态），非上下文事实；放进公开数据契约会污染
  语义，且 `observe()` 造新 ctx 时需额外搬运。`astream()` 是唯一循环体（`run()` 委托它）⇒ 一处覆盖全路径；
  局部变量随轮自然重置（I4）。这一改动让既有
  `test_loop_default_wiring_compacts_exactly_once_at_round_ten` 的「恰好一次」由**巧合**（阈值 == 上限）
  变为**规格保证**。
- **决策 ⑤：配置键与访问器。** `ConfigSpec("loop.compact_steps", "--loop.compact-steps",
  "CORE_LOOP_COMPACT_STEPS", default=6, map_to="loop.compact_steps", exposure=ADVANCED)` ⇒ 三面齐备、入优先级链；
  `loop` 段已在 `_known_sections()` 白名单内（`map_to` 前缀合并）⇒ `_KNOWN_EXTRA_SECTIONS` **不动**。
  独立访问器 `compact_steps()`（同 `history_turns()` 先例）：**不**并入 `loop_limits()` 二元组（其 arity 被多处
  解包断言钉死）；取值已过校验 ⇒ 只做 env/CLI 字符串归一、不设二次兜底。`_loop_errors` 增一条「须为 ≥1 的
  整数」，`bool` 非法，**阻断启动**（静默兜底会把配置错误变成运行时的诡异行为）。
- **决策 ⑥：组合根注入，缺省零扰动。** `runtime.py`：`ContextCompactor(memory=memory,
  step_threshold=config.compact_steps())`；`config is None` 时访问器回落 `6` ⇒ 构造值等于模块缺省 ⇒
  与「不注入」**逐字一致**。
- **被改写的规格条款（有意，见 design.md）**：`context`「上下文自动压实」canonical **无触发判据句** ⇒ delta
  **新增**一段（工具步数 or token、每轮至多一次）并把首个 Scenario 的 GIVEN 由「轮数」改为「**工具步数**」
  （措辞诚实化，场景语义不变）；「三层窗口比例分配」括注「不新增配置键」写于**配额分配面**，改为「本**配额
  分配面**不新增配置键 —— 压实**触发**阈值是另一面」，**消除字面冲突**、行为条款逐字保留；`configuration`
  「循环预算配置」由「三项」改「四项」并在同句追加默认值与校验口径（同 Requirement 条款增补，非新需求）。
- **落点**：`src/core/context/compactor.py`（常量与形参更名 + 判据 docstring）、
  `src/core/loop/default.py`（`compacted` 标记 + 触发点短路 + `_should_compact` 文案）、
  `src/core/configuration/manager.py`（`_DEFAULT_COMPACT_STEPS` + `ConfigSpec` + `compact_steps()` +
  `_loop_errors` 一条）、`src/core/runtime.py`（构造实参）。
- **局限**：① `LoopContext.rounds` 仍是「工具步数」的**历史名**（决策①）—— 诚实化只覆盖压实触发面与配置面；
  ② 缺省 `6` 是**启发式**取值（非实测调优）：过小 ⇒ 短工具链任务也压实（模型成本），过大 ⇒ 接近上限后
  退回「不提前」，与 token 维度的**相对权重**未做评测；③ 阈值 `>= max_rounds` 时该维度**静默退化**为
  「与终止同刻」，无告警（有意：合法配置，但用户可能以为它仍会提前）；④ 「每轮至多一次」是**每用户轮**
  粒度 —— 跨轮（同一会话连续两轮）各自可压实一次，本 change 未限制 ✓；⑤ 压实仍**只有轮级触发**：
  无「关键信息密度」类内容判据（沿用既有的 token/步数双阀）。

### ADR-0174：流式令牌用量与请求侧输出上限（change 0183）

**背景。** `known-risk.md` §1 E97 余项之一：`LLMChunk` 无 `usage` 字段、`_map_chunk` 从不解析；
而**流式是默认推理路径**（`planner.astream` 优先），非流式只在 provider 缺 `astream` 时退化 ⇒
`_last_prompt_tokens` 在流式下**只有装配估算、从不被端点实报抬升**，两条路径记账口径不一致。
同时 `LLMRequest.max_tokens` 是死字段（`_build_body` 支持下发、无调用方填）⇒ 配置项
`loop.output_reserve` 只是**记账假设**（预算派生 `窗口 − 预留`），模型侧无上界。

- **决策 ①：`LLMChunk.usage: TokenUsage | None = None`，未携带时 `None` 而非零值。** 零值会被读成
  「提示词 0 token」并在观测面与「端点未上报」不可分辨。新字段带缺省值 ⇒ 所有既有构造点零改动。
- **决策 ②：解析点在 `choices` 早返**之前**（本 change 唯一的实现陷阱）。** OpenAI 兼容端点把用量
  放在**末块**，而该末块 `choices` 是**空数组**（只报账、不产内容）；照现状早返则用量永远丢失。
  故新增 `_map_usage` 并**两处**调用（早返分支与正常分支），早返分支 `content=""` 逐字不变 ⇒
  **事件面零变化**，只是这类块开始携带用量。规格明文写死这一形态（「SHALL NOT 因 `choices` 为空而丢弃」）。
- **决策 ③：非流式那条路径逐字保留。** `_map_response` 的 `usage.get(..., 0)` 零值口径、请求体形状
  均不动；规格明文「SHALL NOT 改变非流式 `LLMResponse.usage` 的既有解析」。`_map_usage` 与
  `_map_response` 取值同源但**不共用**：前者必须能表达「未上报」。
- **决策 ④：`stream_options={"include_usage": True}` 只下发给流式请求。** 非流式响应本就带 `usage`
  ⇒ 多发该字段无意义（规格 Scenario 明文「非流式请求体不含 `stream_options`」）。已知局限见下。
- **决策 ⑤：消费方实报**抬升下界**（`max`），完成量**纯观测**。** `astream` 循环体**首行**消费 ——
  必须早于 `if not chunk.content: continue`，否则末块（`content=""`）的用量被跳过。
  `_last_prompt_tokens = max(估算, prompt_tokens)` 与 `_complete` 的既有句式是同一句话的两种到达方式
  （一次性 vs 增量）⇒ 合并后两路径**同一语义**。`completion_tokens` 记入 `_last_completion_tokens` +
  新增同型 duck-typing 探针 `last_completion_tokens()`，**不参与**任何判定：预算闸门看的是**下一轮**的
  提示词占用，本轮已花出的完成量无可行动作。`getattr(chunk, "usage", None)` ⇒ 第三方替身（自有形块、
  无该字段）不破，与既有 `finish_reason` 的 `getattr` 处置同型。
- **决策 ⑥：`max_tokens` 构造期注入点，`> 0` 才下发（`≤ 0` 与 `None` 同义）。** 归一在构造期完成，
  调用方无需判空。`≤ 0` 是配置面能写出的合法值，语义上「上界为 0」使模型无法产出 ⇒ 视为未注入比
  「下发 `max_tokens: 0` 让端点 400」更诚实。缺省 `None` ⇒ 请求形状**逐字不变**。
  **为什么 `> 0` 就下发是安全的**：`loop.output_reserve` 已是预算派生的**同一个量**，派生本已假设
  「输出至多占预留这么多」，下发只是把**记账假设**变成**端点上界**；配置错时端点是**响亮 400**，
  且该配置本已使预算派生错误 ⇒ 本条让配置错误**提前暴露**而非引入新风险。
- **决策 ⑦：组合根注入 + 独立访问器（无新配置键、无 configuration 规格变更）。**
  `ConfigurationManager.output_reserve()` 读既有键 `loop.output_reserve`（缺省 `8192`），
  **不**加 ConfigSpec、**不**改 `loop_limits()` 的 arity（其二元组解包断言被多处钉死）——
  同 `history_turns()`（0115）/ `compact_steps()`（0182）的纪律。`runtime.py` 注入**四个 loop**
  的全部 planner（主 / 子 agent / 神兽 / 宠物）—— 它们本就同源同参（共享 `max_rounds` / `token_budget`），
  预留是 loop 级量 ⇒ 只注主 planner 会使同配置下四条链路请求形状不一致。
- **被改写的规格条款。** `llm-provider` **新增**两条 Requirement（「流式增量携带令牌用量」4 Scenario +
  「请求侧输出上限按预留注入」2 Scenario）—— canonical 8 req / 18 scen ⇒ **10 req / 24 scen**
  （既有标题零丢失）。本 change **不**改 `configuration` 规格（无新键）。
- **落点**：`src/core/llm_provider/models.py`（`LLMChunk.usage`）、
  `src/core/llm_provider/stdlib_provider.py`（`_map_usage` + 早返前解析 + `stream_options`）、
  `src/core/loop/planner.py`（`max_tokens` 注入点 + `_observe_usage` + `_last_completion_tokens` +
  `last_completion_tokens()` + `astream` 首行消费）、`src/core/configuration/manager.py`
  （`output_reserve()`）、`src/core/runtime.py`（四处 planner 注入）。
- **测试**：provider 面 4（用量三态 + 请求体两态）、planner 面 6（实报抬升 / 未上报不抬升 /
  完成量观测 / 注入下发 / 非正不下发 ×3）、配置与接线 3（访问器缺省 / 读同一键 / 组合根注入）。
  基线 **2163 → 2176**（**+13**）。
- **局限**：① **拒绝 `stream_options` 的端点会在流式路径报错**（走既有 `LLMError` 路径，响亮失败、
  非静默降级）—— 该字段不在 OpenAI 规范的早期版本里，非 OpenAI 兼容的自研端点可能不识；无「首轮探测
  后降级」机制，亦即**无自动回退**；② `max_tokens` 注入**默认生效**（缺省预留 `8192`）：模型输出上限
  **低于**预留值的端点会 400 —— 本 change 未内置「按模型推导输出上限」（那是 `0184` 的 known-model 面，
  且只覆盖 `context_window`）；③ `completion_tokens` 只是**记下来**，无消费者 —— 未接入 metrics /
  成本核算（观测面有值、无出口）；④ 用量只取**末块**：若端点逐块上报累计用量，本实现只认最后一个
  （`max` 抬升使之无害，但中间值不落）；⑤ `_last_prompt_tokens` 仍是**单轮**观测量，无跨轮累计。

## ADR-0175：已知模型窗口表与 provider 审计标签（change 0184 / 账本 E121）

**背景 —— 两个「配置面说了、系统不听」的缺口**（同批用户裁决「E97 余项 = 全做」，与 `0183` 同源）。
① `llm.context_window` 缺省 `0` 时 `loop_limits()` **直接回落常量 `65536`** ⇒ 跑 `gpt-4o`（128k）
与跑 `claude-*`（200k）拿到同一份预算，用户不显式配窗口就永远用不到模型真实窗口（闸门**偏早**，
偏保守但白扔窗口）；② `LLMResponse.provider` 在 `_map_response` **硬编码 `"stdlib"`**、组合根构造
`StdlibLLMProvider` **不传** provider ⇒ 即便 `llm.provider: litellm`（该键**必填**、校验非空），
审计标签仍是 `"stdlib"` —— 规格「模型调用审计」要求「标注 provider / model」，**标注与实际不符**。

- **决策 ①：窗口表是「有序子串表 + 未命中返回 0」的纯常量/纯函数。** 新模块
  `src/core/configuration/model_windows.py`：`_KNOWN_CONTEXT_WINDOWS: tuple[tuple[str, int], ...]`
  + `known_window(model) -> int`。用 **tuple 而非 dict**：**顺序即特异性**（更具体的前缀须排在更笼统
  的前缀之前，首个命中胜出），dict 不表达优先级。返回 `0` 而非「随便给个数」—— `0` 是「**不知道**」的
  诚实表达，由调用方统一回落既有缺省，不为未收录模型编造数字。
- **决策 ②：窗口来源三态且**显式优先**，只留一处减法。** `loop_limits()` 改为：`llm.context_window > 0`
  优先；否则 `known_window(llm.model)`；两者皆 `≤ 0` ⇒ **不做窗口派生**，回落常量预算 `65536`。
  归一后再统一 `window - output_reserve` ⇒ **减法只有一处**（原 `if/else` 双分支各自返回，口径分散）。
  三条路径中**只有**「表命中且未显式配置」是**有意的**行为变更，另两条**逐字兼容**。
- **决策 ③：`_window_reserve_errors` 不动。** 它校验的是**显式配置**的窗口（`llm.context_window > 0`）；
  表推导出的窗口是我们自己的常量、不经用户配置面 ⇒ 无需再过「窗口 > 预留」闸门（局限见下）。
- **决策 ④：表不引入配置键（不是第二真源）。** 无新 ConfigSpec / CLI / env / yaml 面；表是 `llm.context_window`
  的**推导来源**，不是与之并列的第二个配置入口。规格明文写死这条纪律与优先级。
- **决策 ⑤：provider 标签改在**生产点**，而非 runtime 事后改写。** `StdlibLLMProvider(provider="stdlib")`
  构造参数 + `self._provider = provider or "stdlib"`；`_map_response` 用 `self._provider`。`LLMResponse`
  由 provider 产出、经 `_audit` 回调与调用方消费 ⇒ **生产点说谎则下游全在说谎**，只有改生产点能保证
  「响应面所见即配置面所见」。`provider or "stdlib"`（而非裸 `provider`）：`llm.provider` 虽必填，但
  `StdlibLLMProvider()` 的**裸构造**（registry `default()`、测试替身）不传该参，空串同理 ⇒ 必须自守，
  不把空标签写进审计。缺省值 `"stdlib"` 使**未注入的构造点行为逐字不变**。
- **被改写的规格条款。** 两处 **MODIFIED**（非新增）：`configuration`「LLM 提供商配置（必选）」
  改写 `context_window` 句为「未配置时 SHALL 按 `model` 从内置表推导（子串匹配，大小写不敏感），
  未命中 SHALL 回落内置缺省」+ 新增一段（优先级：显式 > 表 > 缺省；表纪律：只收录有据模型 / 不新增配置键
  / 非第二真源）+ **3 新 Scenario**；`llm-provider`「模型调用审计」补「`LLMResponse.provider` SHALL 反映
  **实际使用的 provider 标识**：接受构造期注入、SHALL NOT 硬编码；注入为空时回落自身身份」+ **1 新 Scenario**。
  canonical：`configuration` 53 → **56** scen（10 req 不变）；`llm-provider` 24 → **25** scen（10 req 不变）。
  **既有 Requirement / Scenario 标题零丢失**（归档脚本断言）。
- **落点**：`src/core/configuration/model_windows.py`（新）、`src/core/configuration/manager.py`
  （`loop_limits()` 窗口三态 + import）、`src/core/llm_provider/stdlib_provider.py`（`provider` 构造参数 +
  `self._provider` + `_map_response`）、`src/core/runtime.py`（主 provider 注入 `app.llm.provider`）。
- **测试**：表面 2（族命中 / 未收录返回 0）、预算面 3（按模型推导 / 显式优先 / 未命中回落）、
  provider 面 3（注入反映配置 / 缺省回落身份 / 空串回落身份）、组合根接线 1。
  基线 **2176 → 2185**（**+9**）。归档后 `openspec validate --all` **31 passed / 0 failed**。
- **局限**：① **表是静态常量、不随端点能力自更新** —— 新模型族需改代码（无「按端点 `/models` 探测」
  机制；那会引入网络依赖与启动期不确定性）；② 子串匹配**无边界语义**：模型名里恰好含 `claude` / `gpt-4o`
  等子串的**非该族**模型会被误纳入（如自建 `my-gpt-4o-clone`）—— 表「小而实」使风险有界，但存在；
  ③ 表推导出的窗口**不过** `_window_reserve_errors` 闸门：若用户配了**荒谬的大** `output_reserve`
  （大于表推导窗口），派生预算会 `≤ 0`（在 `DefaultLoop` 侧语义是「关闭 token 维度」）⇒ **静默关闸**。
  显式配窗口时该情形被校验期拒绝，表推导路径**无此保护**；④ 本 change **不**按模型推导**输出上限**
  （ADR-0174 局限②留的坑仍在）：`max_tokens` 仍取 `loop.output_reserve` 常数；⑤ 表只覆盖
  `context_window` 一项，`embedding_model` 等其他模型相关面不参与；⑥ provider 标签只改
  `StdlibLLMProvider` —— 第三方 `LLMProvider` 实现若自产 `LLMResponse` 且自有硬编码标签，本 change
  **管不到**（规格只约束「实际使用的 provider 标识」，实现自证）。

## ADR-0176：压缩产物退出事实注入面（change 0185 / 账本 E122）

**背景 —— 同一份正文经两条通道进场。** 会话长期摘要（`source="compaction"`，`store.py:655`）与
中层摘要（`store.py:461`）的正文，已由 `planner.py:326-331` 的「历史摘要（长期）/（中期）」**专块**
每轮注入一次；但两者 `source` 不在装配器的排除面内 ⇒ `_gather_facts` 又经「相关事实」面**再注入一次**。
后果有二：① **预算浪费**（同一份正文吃掉两份事实面配额）；② 语义上更坏的 **虚假置信** —— 同一内容以
两条独立条目出现，读者会读成「两条彼此印证的证据」。`notes` 规格（`notes/spec.md:58-70`）早有同型纪律
「同一份内容 SHALL NOT 经两条通道重复注入同一次请求」，本 change 是把该纪律**推广到压缩产物面**。

- **决策 ①：轴选 `MemoryEntry.source`（**不是** `id`）。** 计划稿给的实参是
  `("compaction.summary.", "compaction.mid.")` —— 那是 **id** 前缀；而排除面的比较对象是 `entry.source`
  ⇒ 传 id 前缀**一条都匹配不上**，change 会**静默变成空操作**（「绿灯的无操作」是最坏的回归形态）。
  核实：树中 `source == "compaction"` 的条目**恰好两条**（mid `store.py:461`、summary `store.py:655`），
  而压实产出的事实 / 未决是 `source == "context"`（`compactor.py:101/115`）⇒ `("compaction",)` 是
  **可证正确且最小**的选择器，且恰好就是计划稿想划的**那条分界线**（「有专块承载的」vs「无专块承载的」）。
- **决策 ②：新增**独立参数**，不往既有封存元组里塞第三项。** `exclude_source_prefixes`（封存面）与
  本排除面**理由不同**：前者是「该命名空间对本 agent **永不可见**」（phase-26 红线），后者是
  「**已由别处注入**，故此处不重复」。合并会让 `with_allow_source_prefixes` 的派生继承**纠缠**神兽放行语义，
  且会让 phase-26 红线元组**不再逐字**。分参 ⇒ 封存元组**字面不动**，两类排除各自可断言、可回滚。
- **决策 ③：过滤落在**读后**（`read()` 结果上），不推进 `read()` 内部。** 排除是**装配面**的关注点，
  不是**检索语义**：`MemoryStore.read` 的排名 / 预算 / 复用强化对**其他**消费者（抽取素材、检索素材、
  CLI 查询）必须逐字不变 —— `compaction.*` 条目仍须可被 `read()` 取回。代价：被挡条目**已吃掉事实面预算**
  （有界：每会话长期 / 中期各一条），见局限①。
- **决策 ④：缺省空 ⇒ 不建过滤、路径逐字不变。** `self._exclude_fact_sources = ()` 时
  `_gather_facts` 走**原返回**语句（无新分支进入）；`with_allow_source_prefixes` 派生装配器**继承**本排除面
  （放行面是封存面的例外面，与事实面去重无关，故不参与）。
- **决策 ⑤：规格落 `context`（MODIFIED ×1），不落 `memory`。** 被改的是**装配面的注入步骤**，
  `memory` 的 `read` 契约**未动** —— 规格该写在行为实际发生变化的能力上。

**被改写的规格条款。** `context/spec.md`「动态上下文构建」**MODIFIED**（非新增）：追加「装配 SHALL 另支持
可选的事实面排除面 `exclude_fact_sources`（按 `source` 前缀；缺省空 ⇒ 逐字一致）…… 该排除 SHALL **只**落在
注入步骤：`read` 的检索语义 / 排序 / 预算 / 复用强化 SHALL 逐字不变 …… 无专块承载的压缩产出（`source`
为 `context`）SHALL 不受影响」+ **1 新 Scenario**「压缩产物不进事实面」。canonical：`context` 162 → **177** 行，
**6 req 不变**，scen 21 → **22**。**既有 Requirement / Scenario 标题零丢失**（归档脚本断言 5 条全过）。

- **落点**：`src/core/context/assembler.py`（模块级 `_matches_any` + `exclude_fact_sources` 构造参数 +
  `self._exclude_fact_sources` + 派生继承 + `_gather_facts` 读后前缀过滤）、
  `src/core/runtime.py`（主装配器 `exclude_fact_sources=("compaction",)`；**封存元组逐字不动**）。
- **测试**（+6，`tests/test_context.py`）：排除生效（长期 / 中期摘要退出事实面、`context` 派生物留下）/
  缺省逐字一致（回归锚）/ **前缀**语义（`("compaction.",)` 带点匹配不到裸 `compaction`）/ 派生继承 /
  `read()` 仍可取回摘要（检索语义回归锚）/ 组合根接线（`_exclude_fact_sources == ("compaction",)`
  **且** `_exclude_source_prefixes == ("beast.", "pet")` 逐字不动）。基线 **2185 → 2191**（**+6**）。
  归档后 `openspec validate --all` **31 passed / 0 failed**。
- **局限**：① **预算近似** —— 被挡条目在 `read()` 内**已消耗**事实面配额（过滤发生在读后）：本 change
  **不**回收那份预算，只是不把它注入 prompt。因每会话长期 / 中期摘要**各至多一条**，浪费有界；
  ② **仍可能要两次**：`session_id` 为空时「历史摘要」专块的键与事实面条目键不同源（专块按当前会话键取，
  若条目属他会话则专块取不到、事实面又已排除）⇒ 理论上存在**两边都不显示**的窄缝 —— 需 `session_id`
  非空才成立，属既有会话维度设计的边缘；③ **前缀语义无边界**：`("compaction",)` 也会挡掉未来任何以
  `compaction` 开头的**新** source（若将来引入「**未**由专块承载的 compaction 产物」，须显式改排除面或
  改其 source）—— 表「小而实」使风险有界，但存在；④ 本 change **不**处理 `loop.steps.<trace>` 原始步序
  的同型问题（其 `source` 不同、动因不同）—— 另立 `0186`。

## ADR-0177：原始步序素材退出事实注入面（change 0186 / 账本 E123）

**背景 —— 声明角色与消费面不符。** `loop.steps.<trace_id>`（`src/core/loop/default.py:819-831`）是每轮
「工具动作（参数）→ 结果节选」的**原始行动序列**，其**声明角色**是**抽取器素材**（`_write_trajectory`
docstring 明文：另立该条是为让抽取器仍能看到原始序列 —— 抽取器对每条 L2 条目只取前
`extract._MAX_ENTRY_CHARS`(400) 字符）。但它的 `source` 与 `loop.<trace_id>`（轨迹）、
`loop.failure.<trace_id>`（失败摘要）**同为** `"loop"` ⇒ 只要与任务检索命中，这条**未消化的原料**
就会被 `DynamicAssembler._gather_facts` 当「相关事实」**注入 prompt**，而它的信息**已由**同轮轨迹条目
（+ 可检索 `reply`）与（失败时）失败摘要承载 ⇒ 同一份材料在两个面各出现一次、且其中一次是**噪声**。

- **决策 ①：轴取 `MemoryEntry.tags`（**不**取 `source`，也**不**取 `id`）。** 三个 `loop.*` 条目的
  `source` **逐字相同**（`source=self._source == "loop"`）⇒ **来源面天然不可分**：沿用 `0185` 的
  `exclude_fact_sources` 无论传什么前缀都会**要么全挡要么全不挡**（传 `("loop",)` 会把轨迹与失败摘要
  一起杀掉 —— **过挡**）。区分判据只有 `id` 前缀（`loop.steps.`）或标签（`"steps"`，`default.py:827`）。
  取 **tags**：它是条目的**显式分类声明**、比 id 命名约定更表意，且与 `memory._PRESERVE_TAGS`
  （同为 tags 面排除，change `0179`／ADR-0170）**同型** ⇒ 装配面由此**同时镜像 memory 的两条既有
  排除惯用法**：来源面 ← `_ARCHIVE_SOURCES`（change `0180`）、标签面 ← `_PRESERVE_TAGS`。
- **决策 ②：并列新轴，不并入 `exclude_fact_sources`。** 两参数**判据与理由皆不同**（来源命名空间
  vs 条目分类标签），且轴**互不覆盖**（见 ①）。合成一条会让两面的语义纠缠、断言不可分。构造器已有
  `exclude_source_prefixes` / `allow_source_prefixes` 的并列先例（`PLR0913` 豁免即为此设）。
- **决策 ③：交集语义。** `exclude_fact_tags` 为 `frozenset[str]`，命中判据是 `entry.tags` 与之**有交集**
  （**整体相等**比较，非前缀 —— 与来源面前缀语义**不同**，故独立模块级 helper `_shares_any_tag`，
  与 `_matches_any` 并列）。空标签永不命中；多标签条目**任一**命中即挡。
- **决策 ④：过滤落**读后**（与 `0185` 同构）。** 排除是**装配面注入步骤**的关注点，非**检索语义**：
  `MemoryStore.read` 的排名 / 预算 / 复用强化对**其他**消费者 —— 尤其**声明消费者**关键事实**抽取器** ——
  必须逐字不变 ⇒ `loop.steps.*` 经 `read()` **仍可召回**。代价与 `0185` 同：被挡条目已吃掉事实面预算
  （有界：每轮至多一条），见局限①。
- **决策 ⑤：缺省空 ⇒ 逐字不变；派生装配器继承。** `frozenset()` 时过滤子句恒假 ⇒ 返回与既往逐字相同；
  `with_allow_source_prefixes` 派生装配器**继承**（与 `0185` 的 `exclude_fact_sources` 继承同构）。
- **决策 ⑥：规格落 `context`（**不**落 `memory`）。** 被改的是**装配面的注入步骤**；`memory` 的 `read`
  契约与「条目角色」定义**均未动**（`loop.steps.*` 的素材角色是 `loop` 侧 docstring 的既有声明）。
  ⇒ 写在行为实际发生变化的能力上：`context`「动态上下文构建」**MODIFIED**（与 `0185` **同一**
  Requirement 追加**标签**面条款）。`memory` 的两条惯用法在规格与 ADR 中**交叉引用**、其文本不改。
- **（③）`key_fact` vs 笔记结论记为**设计上非重复**（本 change **不**引入跨模块匹配）：`key_fact` 是
  **结构化实体**（`entity:` 面）、笔记结论是**规范散文知识**（canonical Markdown 真相层）—— 不同面、
  不同消费方式，重复不成立。仅登记结论。

**被改写的规格条款。** `context/spec.md`「动态上下文构建」**MODIFIED**（非新增）：追加第二事实面排除面
「`exclude_fact_tags`（按 `tags` **交集**；缺省空 ⇒ 逐字一致）…… 声明角色为**素材**的条目 SHALL NOT 进
注入面 —— 原始行动序列（`tags` 含 `steps`）SHALL NOT 被注入 prompt，其信息 SHALL 由同轮轨迹 / 失败摘要
承载 …… 该排除**只**落注入步骤：`read` 语义 / 排序 / 预算 / 复用强化 SHALL 逐字不变（抽取器仍可见）」
+ **1 新 Scenario**「原始步序素材不进事实面」。canonical：`context` 177 → **196** 行，**6 req 不变**，
scen 22 → **23**。**既有 Requirement / Scenario 标题零丢失**（归档脚本 5 断言全过）。

- **落点**：`src/core/context/assembler.py`（模块级 `_shares_any_tag` + 构造参数 `exclude_fact_tags`
  + `self._exclude_fact_tags` + 派生继承 + `_gather_facts` 读后交集过滤，与来源面**同一**过滤语句）、
  `src/core/runtime.py`（主装配器 `exclude_fact_tags=frozenset({"steps"})`；来源面 / 封存面逐字不动）。
- **测试**（+5，`tests/test_context.py`）：排除生效（原始步序退出、轨迹 / 失败摘要留存）/
  缺省逐字一致（回归锚）/ **交集**语义（多标签任一命中即挡、空标签不挡、`steps2` 不挡 —— **非前缀**）/
  `read()` 仍可取回原始步序（抽取器素材回归锚）/ 组合根接线（`_exclude_fact_tags == frozenset({"steps"})`
  **且** `_exclude_fact_sources == ("compaction",)` **且** 封存元组逐字不动）。
  **附带**：`0185` 的 `_fact_spy` 假条目补 `tags` 字段（原 double 缺 `MemoryEntry` 的必填字段，
  新过滤面使该缺漏**暴露**为 `AttributeError`）—— 双重现在是**忠实**的。
  基线 **2191 → 2196**（**+5**）。归档后 `openspec validate --all` **31 passed / 0 failed**。
- **局限**：① **预算近似** —— 被挡条目在 `read()` 内已消耗事实面配额、本 change **不**回收（每轮至多
  一条 ⇒ 有界）；② **标签是自律声明** —— `"steps"` 由 `loop` 写入侧赋予、**无强制门禁**：将来若有
  **别的**条目也打 `"steps"` 标签而**应**进事实面，会被顺带挡掉（判据是**标签**，非条目身份）；
  ③ **不处理 notes 侧**：`observe_turn` 写回与 `loop.steps.*` 同源（皆 `_action_steps(ctx)`）却无对账 ——
  本 change 只处理事实注入面一侧，「同源一致性」不引入跨模块匹配；④ **不**处理 `key_fact` vs 笔记结论
  （记为设计上非重复，见 ③）。

## ADR-0178：`reuse_count` 落盘持久化（change 0187 / 账本 E124）

**背景 —— 「测试绿、语义错」：判据选在了进程内可见性上。** `MemoryStore.read()` 命中条目时
`entry.reuse_count += 1`，原注释自陈「复用即强化（**进程内强化，不落盘避免写放大**）」。但
`FileBackend.search`（`backend.py:45-62`）返回的是 `self._entries.values()` 的**同一批对象引用**
（非副本）⇒ 那行自增**就地改了后端的内存对象**，只是**没有** `_persist()`。后果：同进程内
`audit()`（走 `_backend.search("")`）**能**看到新值（故既有 `test_read_reinforces_reuse_count` 一直绿），
**磁盘 JSONL 却始终是旧值** ⇒ 进程结束即丢。而该计数**不止**用于当场排序：`_decay_score`
（`store.py:105-115`）以 `freshness ** (1 / (1 + log1p(reuse_count)))` 调制遗忘曲线
（`memory` 规格明文「复用越多衰减越缓」）⇒ **跨会话复用强化全部丢失**：一条真正被反复召回的记忆，
重启后 `reuse_count` 回到 0、衰减不再被延缓，**最该留的东西反而先被归档** —— 与「记忆即进化轨迹」
的中心隐喻直接相悖。

- **决策 ①：落盘只加一处 `put`，**不**碰 `_hot`。** 新增私有 `_reinforce(selected)` 取代 `read()` 末尾的
  裸循环：对**选中**条目 `self._backend.put(entry)`。**不**把条目插入 `self._hot` —— `_hot` 是**写入侧**
  热字典（`_persist` / `_migrate` / `write` 等五处写入），若读路径也填充，`_hot` 会随**每个被读到的
  条目**无界增长 ⇒ 把「读」变成「隐式缓存」，超出本 change 意图（不变量 I6）。
  *对象同一性*：因后端 `search` 返回同引用，`put(entry)` 只是「同一对象 + 触发 `_persist()`」，
  无序列化往返；`_hot` 中若有同一 id 的对象，也是**同一对象**，不存在两处状态分叉。
- **决策 ②：undo 还原**原值**（非 `-= 1`）。** 每条记
  `Effect(op="memory.reuse", target=entry.id, trace_id=f"reuse.{entry.id}")`，undo 取**还原为捕获的
  `previous`**：若同一 trace 已被回滚、或并发下有多次强化，「还原原值」是**幂等**的、不会把计数
  打成负数（`-= 1` 在重复回滚下会**过减**）。查表顺序照 `_undo_migrate`：`_hot.get(id)` →
  `_backend.get(layer, id)` → 都没有（条目已被删除）⇒ **静默返回**。闭包以**默认参数**绑定
  `entry_id` / `layer` / `value`（避免 ruff `B023` 循环变量晚绑定）。
- **决策 ③：有界批量 —— 只写 `_truncate` 选中的条目。** `read()` 末尾的循环本就只遍历 `selected`
  （非选中候选**从不**自增）⇒ 本 change **不扩大**写入面，只把「已自增」这件事持久化。写放大上界 =
  每次读取的选中条目数（由 `budget` 决定）。
- **决策 ④：规格落 `memory`（**是** `memory`，与 0185/0186 不同）。** `0185`/`0186` 改的是**装配面的
  注入步骤**（故落 `context`）；本 change 改的是 **`MemoryStore.read` 自身**的语义（「复用强化」由
  进程内变持久）⇒ 规格该写在**行为发生变化**的能力 `memory`「温度分层检索」。`context` 侧零改动。
- **显式不做：不加节流 / 批合并配置键。** 写放大已被决策 ③ 限定在选中集内，加配置是**投机性可配置性**
  （违反「最小」）；若将来实测到热点，再以独立 change 引入（并附度量证据）。亦**不改** `summary_for` /
  `mid_summary_for` —— 它们是**不同的**只读取数面（不经 `read()`），其「零写入 / 零效应」契约逐字不动
  （既有测试继续守护）。

**被改写的规格条款。** `memory/spec.md`「温度分层检索」**MODIFIED**（非新增）：保留原条款全文 + 追加
「命中条目的复用强化 SHALL **落盘持久化** …… `reuse_count` 的递增 SHALL 写入持久后端（SHALL NOT 只
存在于进程内）…… 写回 SHALL **只**覆盖本次检索**选中**（进入结果预算）的条目（非选中候选 SHALL NOT
被写、SHALL NOT 被强化 —— 与既有语义逐字一致）⇒ 写放大有界于选中集。每条写回 SHALL 记录**可撤销
效应**（按 trace 回滚即把 `reuse_count` 还原为强化前的值）」+ **1 新 Scenario**「复用强化跨会话持久」。
canonical：`memory` 721 → **734** 行，**13 req 不变**，scen 89 → **90**。**既有 Requirement / Scenario
标题零丢失**（归档脚本 4 断言全过）。

- **落点**：`src/core/memory/store.py`（`read()` 末尾裸循环 → `self._reinforce(selected)`；
  新私有 `_reinforce`（`store.py:252`）+ `_undo_reuse`（`store.py:970`，形状照 `_undo_migrate`））。
  `src/core/context/` / `src/core/runtime.py` / 后端**零改动**。
- **测试**（+4，`tests/test_memory.py`）：跨会话保持（同 backend 新建 store ⇒ `reuse_count` 仍为强化值，
  **非**退回 0）/ 未命中不写（回归锚：无候选 ⇒ 零 `put`、零效应 —— 计数 `put` 的 `_PutCountingBackend`）/
  写回可回滚（`rollback("reuse.e1")` ⇒ 后端**与重新装载的磁盘文件**皆还原为 0）/ 有界（预算只容一条、
  两条候选 ⇒ 仅选中者被强化，落选者 `reuse_count` 不变、无 `reuse.*` 效应）。
  既有 `test_read_reinforces_reuse_count` 继续绿（回归锚）。基线 **2196 → 2200**（**+4**）。
  归档后 `openspec validate --all` **31 passed / 0 failed**。
- **局限**：① **写放大仍在**（本 change 有意接受）—— 每次命中检索都对每个选中条目**整文件重写**
  （`FileBackend._persist` 序列化全部条目）⇒ 读密集场景下磁盘 IO 随检索次数线性增长；当前**不加**节流
  （见「显式不做」），若实测成热点需另立 change 引入批合并 / 脏标记；② **还原面是值不是事件** ——
  undo 记录的是**前值**而非「减一」：并发（多线程同 id 命中）下若先记 A(0→1) 再记 B(1→2)，回滚 B 得 1、
  回滚 A 得 0（正确）；但若**交错**记录（A 捕 0、B 捕 0、A 写 1、B 写 1 覆盖），回滚后可能落在 1 而非 0 ⇒
  强一致需外部串行化，本 change **不**引入锁（`FileBackend.put` 自身有 `RLock`，但读-改-写横跨 `read()`
  与 undo）；③ **不改 `_hot` 的既有填充面**（决策 ①）：故 `audit()` 与磁盘在**读路径**上仍可能有
  「`_hot` 中对象被外部就地改动」的窗口 —— 本 change 只保证 `read()` 自己的写回成对（内存 + 磁盘）。

## ADR-0179：记忆面 → 诊断面桥（change 0188 / 账本 E125）

**背景 —— 失败摘要「已沉淀、无人读」。** 轮级失败已由 `loop` 另立为 L2 条目
`loop.failure.<trace_id>`（`src/core/loop/default.py:833-846`，`tags=["loop","failure"]`，正文来自
`failure_digest(...)`：任务 + 失败原因 + 失败轮次与失败动作），但**没有任何读者**：
`Diagnoser.diagnose(traces, prior)`（`src/core/evolution/diagnoser.py`）只看 `Trace.success` 与
`Trace.plugin_id` —— 归因线索**只有结构化面**；`src/core/evolution/` 对 memory 是**只写不读**
（`engine.py` 只用 `memory` / `memory_crystallizer` 做回写）。⇒ 系统**已经**沉淀了人类可读的失败
叙述，而进化闭环的起点（缺陷定位）看不到它：**归因报告与失败摘要之间缺一条读取桥**。

- **决策 ①：依赖倒置注入 reader（**不** import memory）。** `Diagnoser.__init__` 增**可选**接缝
  `failure_lookup: Callable[[str], str | None] | None = None`，与 `summarize_with(llm)` /
  `extract_with(llm)`（memory 侧）/ `review_with(llm)`（evolution 侧）**同一接缝纪律**。
  注：`evolution → memory` 在 ADR-0045 下**本就允许**，且 `EvolutionEngine` 已持 `memory=backend`
  ⇒ 注入**不是**为绕方向限制，而是因为 `Diagnoser` 是**纯归因单元**（无状态、可单测）—— 把后端塞进
  它会扩大其依赖面、使单测必须造后端；注入一个 `Callable` 把「取回摘要」的**机制**留在组合根。
- **决策 ②：新增可选字段，**不**动 `issue`。** `DiagnosisReport` 增
  `failure_notes: list[str] = field(default_factory=list[str])`。不改 `issue` 的理由：它是**判定叙述**
  且被 `Proposer.propose` 原样带进候选 `delta={"issue": …}` ⇒ 往它追加摘要会改既有字段语义、
  并改候选载荷（范围外）。新增字段 ⇒ 既有构造 / `==` 比较 / 消费面**逐字不变**。
- **决策 ③：有界 + fail-open。** 每条**失败** trace 至多取回一条；单条截断 `_MAX_NOTE_CHARS`(400)、
  总数封顶 `_MAX_FAILURE_NOTES`(3)（截断保留**先到**的失败证据，比后到可预期）。查询抛错 ⇒ **吞掉**
  （该 trace 无 note），诊断照常 —— 与 embedder 降级 / 摘要器不可用降级**同纪律**。空白 / `None`
  **不**入列（不留空串占位）。**归因判定（`target_plugin` / `confidence` / `evidence` / `issue`）
  逐字不变**：桥只**增补**证据面。
- **决策 ④：组合根 lookup 走 `MemoryBackend.search("")`，**不**走 `MemoryStore.read`。**
  `read` 是**语义检索**（相关性排序 + 预算 + 复用强化），且 change `0187` 后**带写副作用** ——
  用「按 id 精确取一条失败摘要」去驱动诊断，语义上就不该借道检索面、更不该借道产生副作用。
  `search("")` 无查询词 ⇒ 纯枚举、**零写入零效应**。**按 id 精确**（`loop.failure.<trace_id>` 是
  `loop` 侧显式 id 约定）：同一 trace 还可能有轨迹 `loop.<trace_id>` 与步序 `loop.steps.<trace_id>`，
  三者 `source` **同为** `"loop"`（见 0186）⇒ 按 source/tag 取「第一条」不成立。**层无关** ⇒ 条目被
  `forget` 迁 L4 后**仍可读**（L4 是层级，不是墓碑）。

**被改写的规格条款。** `evolution/spec.md`「对比诊断」**MODIFIED**（非新增）：保留原 3 条 bullet 全文 +
追加「已沉淀失败摘要 SHALL 可用时并入报告 …… 依赖倒置注入的可调用体（**非** import）…… 按
`loop.failure.<trace_id>` 取回并并入 `DiagnosisReport.failure_notes` …… SHALL **有界**（单条截断、
总数封顶）且 SHALL NOT 改变 `target_plugin` / `confidence` / `evidence` / `issue` 的判定 —— 桥只增补
证据面 …… 缺省未接线 ⇒ `failure_notes` 恒空、诊断与既往**逐字一致**；查询抛错 ⇒ 降级」+
**1 新 Scenario**「已沉淀失败摘要并入诊断报告」。canonical：`evolution` 657 → **668** 行，**16 req 不变**，
scen 83 → **84**。**既有 Requirement / Scenario 标题零丢失**（归档脚本 4 断言 + 块内逐行子序列断言全过）。

- **落点**：`src/core/evolution/models.py`（`DiagnosisReport.failure_notes`）、
  `src/core/evolution/diagnoser.py`（`failure_lookup` 接缝 + `_with_failure_notes` 私有助手 +
  四个返回分支统一经它挂摘要）、`src/core/runtime.py`（模块级 `_failure_lookup(backend)` 闭包 +
  `Diagnoser(failure_lookup=…)`）。`memory` / `context` / `loop` **零改动**。
- **测试**（+6）：`DiagnosisReport` 新字段缺省 ⇒ 相等语义不变（回归锚）/ 未接线 ⇒ `failure_notes` 恒空
  且归因判定逐字不变（回归锚）/ 接线后并入摘要且**只查失败** trace（spy 记录入参）/ 查询抛错降级
  （判定不变）/ 有界（500 字截断至 400、5 条封顶 3 条）/ 组合根接线端到端（`runtime.memory` 写
  `loop.failure.T1` ⇒ 接缝取回正文 ⇒ `diagnose` 报告含该摘要且归因不变；未沉淀 ⇒ `None`）。
  基线 **2200 → 2206**（**+6**）。归档后 `openspec validate --all` **31 passed / 0 failed**。
- **局限**：① **摘要未进候选载荷** —— `failure_notes` 只落在 `DiagnosisReport`（经
  `EvolutionOutcome.diagnosis` 对运维/观测可见），而 `Proposer.propose` 仍只取 `issue` 组 `delta`
  ⇒ 摘要**暂不驱动**候选内容（消费面另议）；② **归因算法未用摘要** —— 桥**不**参与分数竞争
  （仍是「证据计 1.0 + 先验破并列」）⇒ 摘要眼下是**诊断面可读性/可归因性**的增强，而非判定输入；
  ③ **只覆盖 `Diagnoser` 通道** —— `engine._diagnose` 的**显式目标**路径直接构造报告、不经
  `Diagnoser` ⇒ 该路径无 `failure_notes`（它本就不看失败证据）；④ **按 id 约定耦合** ——
  `loop.failure.<trace_id>` 这一构造在 `loop`（写入侧）与 `runtime`（读取侧）各出现一次，
  无单一真源常量守护（若 `loop` 侧改约定，桥**静默**取不到 ⇒ 退化为「无 note」，不报错）。

## ADR-0180：检查点会话归因 + task 路径会话接线（change 0190 / 账本 E127）

**背景 —— 长任务断点链路上的三重会话身份不调和。** 2026-10-11 长任务评估取证：① 检查点会话
元数据**恒为占位谎言** —— `CheckpointFn` 回调签名无 session 形参（`src/core/orchestration/
scheduler.py:32-34`）⇒ 组合根 `_write_checkpoint` 对每个检查点写死 `"default"`
（`src/core/runtime.py` `create_checkpoint(task_id, "default", …)`）；② CLI `task` 入口**完全无会话
身份** —— `entry._task` → `_stream_task` → `orchestrator.astream` 不传 `session_id` ⇒ 子任务轨迹 /
记忆 / 转录全落**全局未归属**（`scheduler._run_subtask` 空则不传第二实参），与 REPL `/task`（发起
会话归因）与 Web 任务入口（同）行为不一致；③ 续跑若另铸新会话，同一任务轨迹将**分裂**在两个会话
下。结构根因是 ①（回调签名），②③ 是其在入口层的两个表现 —— session 在两个回调调用点均在
`astream` 作用域内，扩签名是**最小**结构修正。

- **决策 ①：回调签名扩第 4 参（非新状态）。** `CheckpointFn` / `DoneFn` 增尾参
  `session_id: str`（空串 = 未归属，与 `astream` / `Loop.remember` 既有口径同构），两个调用点
  （波次收拢 / 终态）透传 `astream` 形参——**不加新字段、不加新状态、不加新回调**。这是**破坏性
  接口变更**：全仓实现方仅组合根一处 + 测试替身三处，影响面已枚举并同步。
- **决策 ②：写真值，不写占位。** `_write_checkpoint` 用实参原值（`create_checkpoint(task_id,
  session_id, …)`）：非空写真会话、空串照传 = 诚实的「无会话」。全仓无任何消费方依赖
  `"default"` 字面值（grep 无 `== "default"` 判据；测试中该字面值仅作 create 入参，非读取断言）
  ⇒ 从谎言到真话是**纯修正**。REPL `/task` 与 Web 入口本就传 session ⇒ 其检查点自动获得真会话
  （零额外改动）。
- **决策 ③：CLI fresh 铸会话走共享注册表、直接构造不建 UI。** `_task` 无 `--resume` 时经
  `SessionRegistry(path=_state_path("conversations.json")).create("cli")` 铸会话——与 `run` CLI
  （`api.create_session("cli")`）**同注册表、同 mode**（`session list` 可见、`--session` 续接
  可用）；**不**借道 `_build_ui`（`task` 入口不需要 UI 装配，且那会二次 `build_runtime`）。
- **决策 ④：resume 复用检查点会话；旧占位值视作未归属、不迁移。** `--resume` 取最新检查点的
  `Checkpoint.session_id` 元数据（dataclass 既有字段，durability 层零改动）：`sid and sid !=
  "default"` ⇒ 复用（同一任务跨续跑不分裂）；否则传空串（未归属，行为与既往 CLI task **逐字
  一致**）+ stderr 明示提示。旧数据不迁移——`"default"` 是既成事实，视作未归属即兼容。
- **决策 ⑤：「最新检查点」读取不在本 change 动。** `--resume` 仍取 `list_checkpoints` 末元素
  （文件序）；与 `restore` 的 ts 序对齐属 change `0191`（同批下一条），改动点互不重叠。

**被改写的规格条款。** `orchestration/spec.md`「断点续跑」**MODIFIED**（检查点携带发起会话标识 +
SHALL NOT 写占位值条款 + 1 Scenario「检查点携带发起会话标识」）；「任务入口与进度事件」
**MODIFIED**（新增 bullet「任务入口会话归因」+ 2 Scenario「CLI 新任务铸会话归因」/「CLI 续跑复用
检查点会话」）。`cli-ops/spec.md`「会话命令族与交互入口续聊」**MODIFIED**（一次性任务入口铸会话入
同一注册表条款 + 1 Scenario）。既有 Requirement / Scenario 标题**零丢失**。

- **落点**：`src/core/orchestration/scheduler.py`（类型别名 + 2 调用点）、`src/core/runtime.py`
  （`_checkpoint` / `_finalize` / `_write_checkpoint`）、`src/core/entry.py`（`_task` /
  `_stream_task`）。`durability` 存储层 / 子 Agent 循环 / 记忆 / 转录**零改动**（归因由生产方修正，
  消费方无感）。
- **测试**（+6）：回调收到发起会话标识（fresh 非空 + 缺省空串）/ 组合根写真值 / CLI fresh 铸会话且
  `astream` 收到（经注册表 mode `cli`）/ resume 复用检查点会话 / 旧 `"default"` 视作未归属 + 提示；
  既有替身补第 4 参、既有 resume 用例补 `session_id` 元数据（断言不变量不变）。
- **局限**：① **CLI `task` 无 `--session` flag** —— 显式指定既有会话属会话命令族面（无诉求，
  YAGNI）；② **`"default"` 视作未归属是启发式归一** —— 若操作者真有个会话 id 恰为 `"default"`
  会同样被视作未归属（`SessionRegistry` 铸的是 uuid4 hex，实践不撞）；③ **检查点会话元数据目前
  无检索面** —— `list_checkpoints` 不按 session 过滤（消费面出现时再加索引）；④ 跨进程 undo /
  trace_ids 消费面承 ADR-0136 既有局限，不在本 change。

## ADR-0181：恢复呈现接线 —— 启动扫描+呈现、降级不炸全扫、续跑取最新（change 0191 / 账本 E128）

**背景 —— 崩溃恢复能力齐备却无人触发。** 2026-10-11 长任务评估取证：① `Runtime.recover()`
（`src/core/runtime.py:183-185`）**零生产调用方** —— 扫描检查点、对无 `done` 标记任务
`restore`+`resume` 的能力齐备，但没有任何入口调用 ⇒ 未完成任务跨进程重启后无人知晓；②
`_recover_incomplete`（`runtime.py:1133-1139`）对每个未完成任务调 `recovery.restore`，而
`restore` 在「该任务检查点全部无有效快照」时**整体 `raise DurabilityError(CHECKPOINT_NOT_FOUND)`**
（`manager.py:119-123`），调用点**无 try/except** ⇒ 单个不可恢复任务**中断整轮扫描**（与首轮
`get_snapshot` 对 corrupt 的捕获口径 `runtime.py:1125-1128` **方向相反**）；③ 两种「最新检查点」
定义并存 —— CLI `--resume` 取 `cps[-1]`**文件序**（`entry.py:1720`）vs `restore` 取 **ts 序**
（`manager.py:102-106`）⇒ 续跑可能取到非最新检查点。

- **决策 ①：呈现不重执行（守 P2）。** `resume()` 现状**无 replay 回调**时即纯扫描
  （`manager.py:123-129`：仅把句柄记入幂等集，`replay is None` 则空转）⇒ `runtime.recover()`
  本身零副作用。本 change **不**给 `resume()` 加 replay 面 —— 启动时调 `recover()` 后**只呈现**
  未完成任务（告警 + 提示 `task --resume <id>`），**绝不**自动重新执行（用户裁决①：副作用不自动
  重放；自动续跑另批，需审批面配合）。呈现只报 **task id**，不回显任务正文 / 记忆 / 密钥。
- **决策 ②：恢复句柄携带 task id（自然载体）。** `RestoreHandle` 增 `task_id` 字段（放第 2 位，
  紧跟 `handle_id`）⇒ 呈现「哪些任务未完成」直接取自句柄，**无需**旁路扫描 / 二次查库。构造点全仓
  **唯一一处**（`manager.py:113`，全用关键字）⇒ 破坏性变更影响面最小。
- **决策 ③：降级不炸全扫（对齐既有 corrupt 口径）。** `_recover_incomplete` 对 `recovery.restore`
  包 `try/except DurabilityError` ⇒ 跳过该任务 + `warnings.warn`（只报 task id），其余任务照常返回
  续跑句柄。与首轮 `get_snapshot` 的 corrupt 捕获**同口径**：单点损坏不阻塞恢复。
- **决策 ④：入口接线面最小（`serve` + CLI `task`）。** CLI `task`（**新任务**路径）与 `serve`
  启动调呈现；`serve` 经 `_build_ui(surface_recovery=True)` 传入（`repl`/`app`/`run` 不传 ⇒
  输出面**逐字不变**）；`task --resume` **不**呈现（已是显式续跑动作，再报是噪音）。呈现只读，
  不写检查点 / 记忆 / 注册表。
- **决策 ⑤：「最新检查点」统一为 ts 序。** CLI `--resume`（`entry.py:1720`）由 `cps[-1]` 改
  `max(cps, key=lambda cp: cp.ts)`，与 `CrashRecovery.restore` **同口径**。正常追加落盘时落盘序 =
  时间序 ⇒ 行为逐字不变；仅二者不一致时**修正**为取真正最新。

**被改写的规格条款。** `durability/spec.md`「崩溃恢复」**MODIFIED**（纯扫描语义 + 降级跳过 +
句柄标识任务条款 + 2 Scenario「启动扫描呈现未完成任务」/「不可恢复任务不阻塞整体扫描」）。
`cli-ops/spec.md`「会话命令族与交互入口续聊」**MODIFIED**（入口启动呈现 + `--resume` ts 序条款 +
2 Scenario「入口启动呈现未完成任务」/「续跑取时间戳最新检查点」）。既有 Requirement / Scenario
标题**零丢失**。

- **落点**：`src/core/durability/models.py`（`RestoreHandle` 加字段）、`src/core/durability/manager.py`
  （`restore` 构造补 `task_id`）、`src/core/runtime.py`（`_recover_incomplete` 包 try/except + 告警）、
  `src/core/entry.py`（`_surface_incomplete` + `_build_ui(surface_recovery=…)` + `_serve` + `_task` +
  `--resume` ts 序）。`scheduler` / `resume()` 语义 / `repl`/`app`/`run` 入口**零改动**。
- **测试**（+5 新增 + 3 处既有用例补断言）：新增 `_recover_incomplete` 坏任务降级跳过（其余照常 +
  告警）/ `task` 启动呈现 + 空库静默 + `--resume` 取 ts 最新 / `serve` 启动呈现；既有
  `test_durability_crash` / `test_runtime_recover_restores_incomplete_skips_done` 补 `handle.task_id`
  断言。
- **局限**：① **呈现为「提示」而非「托管」** —— 未完成任务不被自动跟踪 / 提醒刷新（P2 下的诚实
  取舍）；② **无 `--list-incomplete` 独立只读命令** —— 呈现只在 `serve`/`task` 启动时被动触发
  （消费面出现时再加）；③ **`recover()` 的检查点扫描为全量** —— 无索引 / 无缓存（任务规模上限内
  可接受）；④ 跨进程撤销 / trace_ids 消费面承 ADR-0136 既有局限，不在本 change。

## ADR-0182：轮内压实会话化 —— 同一循环消除双口径、trace 归因按会话（change 0192 / 账本 E129）

**背景 —— 同一条循环里两套压实口径。** 2026-10-11 长任务评估取证：① `DefaultLoop._compact`
裸调 `self._memory.compact()`（`src/core/loop/default.py:668`）⇒ 空 `session_id` = **全量聚合**，
把**所有会话**的 L2 episodic 条目一并提炼归档；而同循环的维护节拍 `_maintain`
（`default.py:584`）却**会话化**（`compact(session_id=session_id)`）⇒ 同实例两条路径**口径相反**，
一个正在跑的长任务会话触发轮内压实会**顺手提炼他会话条目**（跨会话串扰）；② `store.py:421-424`
的 `compact` 契约注称「空串……供**循环内节拍压实**使用」，但节拍路径**其实传 session**
（`default.py:584`）⇒ justification **失真**；③ `Compactor.persist` 用**常量** `trace_id="compaction"`
（`compactor.py:102/:116`），而记忆侧其他压实 trace 恒为 `f"compaction.<key>"`
（`store.py:670`/`:773`/`:486`/`:631`）⇒ 回滚归因过粗、且与同会话其他压实产物**不共组**（违反 P3）；
④ `_compact`（`default.py:651`）与 `ContextCompactor.compact`（`compactor.py:44`）docstring 称
「**多轮历史**提炼」，实输入却是 `ctx.messages`（**仅本轮**，`protocol.py:54` 明禁折入 history）。

- **决策 ①：轮内压实会话化（只改调用面）。** `_compact` 第 668 行改
  `self._memory.compact(session_id=ctx.session_id)` ⇒ 与维护节拍**同口径**。`MemoryStore.compact`
  的**空串全量实现逐字不动**：空会话轮（`session_id=""`）`compact(session_id="")` ≡ 裸调
  `compact()` ⇒ 既有行为**逐字不变**（`test_loop.py:583` 无会话压实测试不受影响）；全量语义
  **保留给显式调用**（CLI / 运维命令面）。修的是「循环内顺手提炼他会话」这一串扰缺陷。
- **决策 ②：persist trace 会话键化。** `key = session_id or "default"`（compactor `:92` 已有）
  ⇒ persist 两处常量改 `f"compaction.{key}"`，与 store 既有口径**逐字一致**。回滚按
  `compaction.<sid>` 即撤销该会话的压实产物、并与同会话会话摘要 / 关键事实**共组**（一次回滚
  整批撤销同一压实波次）。**消费面核对**：time-travel 撤销集取自检查点 `state["trace_ids"]`
  （`entry.py:865` / `manager.py:147`，运行期遇到即记），**不硬编码**该常量；全仓**无测试**断言
  persist `trace_id == "compaction"`（断言的是条目 **id** 与 store 侧 trace）⇒ 零消费面被打破。
- **决策 ③：诚实化（沿 `0182` 先例）。** `_compact` / `ContextCompactor.compact` docstring 改
  「**本轮**消息 + 工具 I/O 提炼；**多轮历史**由**三层滑窗**（change 0178）与记忆压实承载」；
  `store.py:422-423` 契约注改「空串全量语义保留给**显式调用**（CLI / 运维）」。
- **决策 ④：provenance 死面只注记不活化（显式不做）。** `compact` 读 `entry.get("id")` 产
  `source_ids` → `persist` 写 `from:<id>` tag；但 `ctx.messages` 条目**无 `id`**
  （`{"role","content"}`）⇒ 循环内 `source_ids` **恒空**、`from:<id>` **恒不触发**（仅测试手造
  `{"id":…}` 激活）。**注记**该事实，**不**扩输入面为多轮历史（扩面 = 多轮 token 成本 + 去重
  新决策，Non-goal；多轮历史已由三层滑窗 `0178` + 记忆压实承载）。

**被改写的规格条款。** `memory/spec.md`「记忆压实」**MODIFIED**（归约范围口径：空串全量保留给
**显式调用**、**循环内路径**一律会话化 + 1 Scenario「循环内压实一律按本轮会话聚合」）。
`loop/spec.md`「执行循环」**MODIFIED**（轮内压实的**记忆固化步骤**按本轮会话收窄 + 1 Scenario
「轮内压实按会话收窄聚合」）。`context/spec.md`「上下文自动压实」**MODIFIED**（产物 `trace_id`
携带会话键 + 1 Scenario「压实产物 trace 携带会话键」）。既有 Requirement / Scenario 标题**零丢失**。

- **落点**：`src/core/loop/default.py`（`_compact` 传 `session_id` + docstring）、
  `src/core/context/compactor.py`（`trace_id` 会话键化 + docstring + provenance 注记）、
  `src/core/memory/store.py`（仅契约注）。`MemoryStore.compact` 实现 / `_maintain` /
  `summarize_slice` / key-fact 抽取**零改动**。
- **测试**（+5 新增，另 1 处既有用例改口径）：轮内压实只聚合本轮会话（他会话条目层级 / 内容不变）、
  空会话轮全量回归、persist `trace_id` 会话键（空 / 非空）、docstring 诚实化文案。
- **局限**：① **provenance（`from:<id>`）仍为死面** —— `ctx.messages` 无 `id`，循环内恒不触发
  （只注记，活化需扩输入面，另批）；② **空会话轮仍是全量聚合** —— 诚实保留（显式调用语义），
  非本 change 修复对象；③ **`_maintain` 的多会话公平性**承 ADR-0169⑦ 既有局限（节拍状态驻留实例、
  只有「正巧活跃」的会话被刷新），不在本 change。

## ADR-0183：滚动摘要首尾保留 —— 越界不再销毁尾部（结论所在）（change 0193 / 账本 E130）

**背景 —— 滚动摘要越界即无声销毁尾部。** 2026-10-11 长任务评估取证：`build_prompt`
（`src/core/memory/summarize.py:48`）把既有摘要投喂摘要器时用 `prior.content[:MAX_SUMMARY_CHARS]`
—— **纯头部截断**。长任务里摘要持续滚动增长，一旦越过 `MAX_SUMMARY_CHARS=2000`，**尾部**（最新
结论 / 决策所在）**永不再进 LLM** ⇒ 下一轮融合产出「前半段 + 新事件」，尾部内容被**无声、不可逆
销毁**（长任务失忆的隐蔽来源）。且 `store.py:700-703`（`_deliver_promotion`）以「既有摘要首越上界」
为交付 canonical 真相层的判据 ⇒ 修法**必须保触发语义逐字不变**。此外 `_below_gate` 跳过会话
（`store.py:118-125` / `:579-580`）**无任何留痕**，运维无从判断「为何我的会话没产摘要」。

- **决策 ①：首尾保留（`_elide_summary`）。** 未越界**逐字**全文（兼容性红线）；越界渲染
  「**首部** ＋ 省略标记（标明中略字数）＋ **尾部**（`_SUMMARY_TAIL_CHARS=800`）」，
  首部 = `MAX_SUMMARY_CHARS - 尾长 - 省略标记长` ⇒ 三段相加**恰为上界**：上界（token 有界）
  **不破**，`MAX_SUMMARY_CHARS` 的「投喂节选上限」语义**保真**；尾部逐字保真 ⇒ 最新结论不再进
  黑洞。marker 长度仅由「上界之外的字数」决定（与首部选择无关）⇒ 单趟确定性、无循环收敛问题。
- **决策 ②：触发语义逐字不动。** `_deliver_promotion` 的越界判据读 `len(prior.content)`（条目
  **全体长度**）与 `len(summary)`，**不读节选** ⇒ 首尾保留**不触碰**该判据。`_commit_summary`
  落库**仍不截断**（canonical 存全文、投喂有界 —— 两条边界**正交**，本 change 只动「投喂」那条）。
- **决策 ③：价值闸留痕（只报会话键）。** `_summarize_sessions` 因 `_below_gate` 跳过会话时补
  `warnings.warn`，**只报会话键**（`{sid!r}`），**绝不**回显摘要 / 事件正文（承「密钥只引用不读取」
  红线）；不改变门控判据与结果（跳过行为逐字不变）。
- **决策 ④：mid 提升通道显式不做。** mid 层由 `summarize_slice(session_id, entries, max_chars=…)`
  预截断（`store.py:477`），是**有界瞬态层**；canonical 逃逸由**长期摘要提升**（change 0153）承载
  —— 本条保长期摘要「越界不销毁尾部」后，该提升路径即在正确前提上成立。

**被改写的规格条款。** `memory/spec.md`「记忆压实」**MODIFIED**（节选**首尾保留**条款 —— 含
「越界判据读全体长度」+ **价值门控留痕**条款 + 2 Scenario「摘要越界首尾保留（尾部不销毁）」/
「价值门控跳过留痕（只报会话键）」）。既有 20 Scenario 标题**零丢失**。

- **落点**：`src/core/memory/summarize.py`（`_SUMMARY_TAIL_CHARS` + `_elide_summary` + `build_prompt`
  用）、`src/core/memory/store.py`（价值闸跳过补 `warnings.warn`）。`MAX_SUMMARY_CHARS` 值 /
  `_deliver_promotion` / `_commit_summary` / `summarize_slice`（mid）**零改动**。
- **测试**（+4 新增）：越界含尾段 + 中略标记 + 节选 ≤ 上界 / 未越界逐字不变 / 极大摘要槽位有界 /
  价值闸留痕只报会话键（断言不含正文）。回归：`test_memory_summary_promotion` / `test_notes_promote`
  既有越界提升用例全绿。
- **局限**：① **中略区仍不可逆丢失** —— 首尾保留只保**尾**，中段（越界部分）仍不进 LLM（canonical
  完整副本由提升钩子落真相层承载，见 `0153`）；② **`omitted` 是「上界之外的字数」** 的近似提示
  （真实中略 = 该值 + `len(marker)`），为人类可读提示、非契约；③ **mid 层无提升通道**（有界瞬态，
  显式不做）；④ 价值闸留痕**每轮每会话一条** —— 长任务高频跳过时会刷屏（属可观测性噪音，非缺陷）。

## ADR-0184：摘要注入与历史回放解耦 —— 关原文回放不再连坐关记忆注入（change 0194 / 账本 E131）

**背景 —— 摘要在两种「关历史」语义下被连坐。** 2026-10-11 长任务评估取证：`DefaultLoop._load_summaries`
（`src/core/loop/default.py:888-894`）的门控含 `self._history_turns <= 0` ⇒ 用户把 `loop.history_turns`
设为 `0`（关闭**历史原文回放**，长任务省 token 的常见配置：只要摘要、不要原文）时，**摘要注入也被静默
关掉** ⇒ 长任务的记忆注入**整条消失**且**无留痕**。且该门控的注释（`:885`）自称「与 `_load_history`
**完全同形**」—— 但 `_load_history` 受 `history_turns` 管是它的**本职**（经 `_window_plan` 算出的
`plan.short_turns`），摘要通道**不该**受此连坐：规格 `loop/spec.md`「执行循环」的 Scenario
「分层摘要作为独立系统块注入」**不带** `history_turns` 条件 ⇒ **实现偏离规格**。

- **决策 ①：门控只留本职判据。** 删去 `self._history_turns <= 0` 一项 ⇒ 剩 `transcript is None` /
  `memory is None` / 空标识。这三项是**摘要读取**的本职前置（摘要经 memory 取、转录是滑窗载体），
  不在解耦对象内。
- **决策 ②：缺省行为逐字不变（兼容性红线）。** `LoopConfig.history_turns` 缺省 `20 > 0` ⇒ 被删条件
  **恒假** ⇒ 删后门控**等价**；仅在用户**显式**设 `history_turns=0` 时行为改变（历史带空、摘要照进）
  —— 恰是修的对象。
- **决策 ③：两条通道各自据本职判据。** `_load_history` 仍用 `plan.short_turns <= 0` 判空，`plan` 由
  `_window_plan` 从 `history_turns` 算出（`history_turns=0` ⇒ `short_turns=0` ⇒ 历史带**自然**为空）；
  配额算法（`plan_window` 短 0.5 / 中 0.3 / 长 0.2）与预算记账 **零改动**。
- **决策 ④：既有测试的错锚订正。** 既有 `test_history_replay.py::test_summaries_gated_like_history`
  的 `(0, "s1", True)` 参数组**把实现缺陷固化为断言**（「关回放 ⇒ 摘要亦不注入」）—— 与规格 Scenario
  相悖 ⇒ 拆为 `test_summaries_gated_on_session_and_transcript`（只留空标识 / 无转录两组）+
  `test_summaries_injected_when_history_replay_disabled`（新行为锚）。

**被改写的规格条款。** `loop/spec.md`「执行循环」**MODIFIED**（+「两层摘要注入与历史回放开关**解耦**」
条款 + Scenario「关闭历史回放仍注入摘要」）；canonical `loop` scen **78 → 79**、**6 req 不变**。
既有 Scenario 标题**零丢失**。

- **落点**：`src/core/loop/default.py`（`_load_summaries` 门控删一项 + docstring 诚实化）。
- **测试**（净 +2：**+3 新增** / 1 组参数拆分 **-1**，2227 → **2229**）：`history_turns=0` 摘要仍注入
  （兼断历史带为空）/ 缺省回归逐字不变 / 空标识与无转录音仍门控 / docstring 断言。
- **局限**：① **`_load_summaries` 仍要求转录已注入** —— 摘要读取当前以 `self._transcript` 存在性作
  前置（属既有设计，本 change 只解耦 `history_turns`；「无转录也要摘要」是另一决策，未做）；
  ② **`history_turns=0` 时摘要 token 仍计入预算记账**（正确但意味着纯摘要配置下预算可能被摘要吃满，
  属既有记账口径）；③ 本 change **不**动三层滑窗配额与 `tiered` 判据。

## ADR-0185：长任务端到端门禁 —— 「产出 → 注入」两端接线补锚（change 0195 / 账本 E132）

**背景 —— 前五条各修一环，但无端到端锚。** 本批次 `0190`~`0194` 修了长任务链路的五个缺口，但
**没有任何用例**把「产出 → 注入」接起来：`test_loop.py` 的压实用例只断言**记忆态**
（`compaction.summary.s1` 存在），`test_history_replay.py` 的注入用例**手播**摘要条目 —— 二者之间
「**上一轮压实的产物真的进了下一轮推理的 system prompt**」**无锚**。越界首尾保留（`0193`）与解耦
（`0194`）同理只在**单元 / 上下文对象**层断言，**装配后**形态无锚 ⇒ 回归时「哪一环断了」无法从
端到端视角发觉。

- **决策 ①：真材实料。** 用真 `DefaultLoop` + 真 `MemoryStore`（假摘要器离线）+ 真 `TranscriptStore`
  + 桩 `LLMProvider`（只记录请求 + 返回定稿回复，不模拟推理）⇒ 零三方依赖、零网络。
- **决策 ②：三条锚。** ①压实产物 → 下一轮 system prompt（turn1 以 `token_budget=1` 触发轮内压实，
  turn2 复用同一 loop 断言 prompt 含产物字串）；②越界尾部 → **摘要器 prompt**；③关历史回放 →
  摘要仍进装配后 prompt。
- **决策 ③：锚点位置订正（初始设计错误并已改正）。** 初版把「越界首尾保留」的锚点放在**循环注入的
  system prompt**，实测**证明失败** —— `_elide_summary` 约束的是**摘要器 prompt**（压实**输入**），
  循环注入 system prompt 的既有摘要是**逐字**的（只受预算记账约束）。锚点已移正到摘要器 prompt。
  **此订正本身即证据**：若不做 e2e，该误解不会被发现。
- **决策 ④：门禁必须能咬（反证）。** 端到端门禁最大风险是**空过**（无论实现如何都绿）。逐条**临时
  回退**目标行为并确认转红：①`_compact` 的 `memory.compact` → `pass` ⇒ 红；③`_elide_summary` 改回
  纯头截断 ⇒ 红；④`_load_summaries` 恢复 `history_turns <= 0` 闸 ⇒ 红；复原后全绿 ⇒ 三条锚**均能咬住**
  其目标行为。
- **决策 ⑤：不重复已有锚。** CLI `--resume` 会话端到端已由
  `test_entry.py::test_task_resume_reuses_checkpoint_session`（change `0190`）承载 ⇒ **不重写**；
  本 change 只补真正缺失的三条。

**规格中性判定。** 零 `src/` 改动、零行为改动 ⇒ 无 spec delta，`.openspec.yaml` `skip_specs: true`
（沿 `0156` / `0189` 先例）。

- **落点**：`tests/test_longtask_e2e.py`（新，3 用例）；`git diff --stat src/` **为空**。
- **测试**：+3（2229 → **2232**）。
- **局限**：① **不覆盖 CLI `--resume` 会话端到端**（已由 `0190` 的既有锚承载，避免重复）；
  ② **桩 provider 不模拟推理** —— 只验装配形态，不验模型行为；③ **轮内压实经预算维度触发**
  （`token_budget=1`），非步数维度 —— 步数维度的触发锚仍由 `test_loop.py` 承载；④ e2e 只在
  **进程内**跑（跨进程断点续跑仍承 `0190`/`0191` 的既有边界）。

## ADR-0186：任务完成回调卸载 —— 收尾回路不阻塞事件循环（change 0196 / 账本 E133）

**背景 —— 为接重活先腾出安全位置。** `TaskScheduler` 在 `astream` 协程内**同步**调用完成回调
（`scheduler.py:290-292`）。当前无症状（`runtime._finalize` 只落一份检查点、廉价文件 IO），但
**下一 change（0197）**要在该回调里接**任务级 SOP 提炼**（一次**模型调用**）—— 一旦如此即**精确
复现 E103 / ADR-0157 缺陷类**：事件循环上的同步模型调用，阻塞流式产出、拖垮同波次并发，且被降级
链静默吞掉（无留痕）。⇒ 按 **P3（进化局部化与可归因）**，把「回调在哪跑」与「回调做什么」拆成
**两条独立 change**：0196 先只改**执行线程**，0197 再改**语义**。

- **决策 ①：`asyncio.to_thread` 卸载（一处调用点）。** `DONE` 分支的 `self._on_done(...)` 改为
  `await asyncio.to_thread(self._on_done, task_id, outcomes, plan, session_id)`。**先例**：
  `loop/default.py:466-468` 已把每轮观察回调如此卸载（change 0167 / ADR-0157）——本 change 把同一
  纪律补到**编排收尾回路**。调用时机与次数（`DONE` 后一次）、顺序（`task_finished` 之前、检查点
  之后）、终态判定与事件载荷 **逐字不变**。
- **决策 ②：** **不**卸载 `_checkpoint`（`scheduler.py:261-262`）。**判据**是「是否承载模型调用」
  而非「是否同步」——`_checkpoint` 只做既有廉价文件 IO，改它属超范围（P3：改一条、可归因一条）。
- **决策 ③：规格落点。** `orchestration`「异步执行单元契约」**MODIFIED**：原文段落 + 既有 3 Scenario
  **逐字保留**，新增 bullet「收尾回路不阻塞」（回调 SHALL 经 `asyncio.to_thread` 卸载）+ Scenario
  「完成回调不阻塞事件循环」。canonical scen **49 → 50**、req **11 不变**。
- **落点**：`src/core/orchestration/scheduler.py`（一处调用点；`asyncio` 已 import）。
- **测试**（+2，2232 → **2234**）：① 回调在**工作线程**执行（`threading.get_ident()` ≠ 主线程 ident，
  红：变更前等于）；② **回调内阻塞不冻结事件循环**（回调在工作线程等一个由事件循环协程释放的事件；
  若同步则循环冻结、释放协程永不推进 ⇒ 回调超时转红）。
- **局限**：① `_checkpoint` 的**同步文件 IO 仍在事件循环上**（见决策 ②；廉价、未接模型调用，
  登记为可接受）；② 卸载**不改变**回调并发度 —— 多任务并发时各回调各占一个工作线程，线程池
  上限由 asyncio 缺省值（`min(32, cpu+4)`）约束；③ 本 change **不**引入回调超时 / 异常处理变更
  （回调异常仍按其自身路径降级，语义不变）。

## ADR-0187：任务级过程输入 —— SOP 提炼接入长会话任务粒度（change 0197 / 账本 E134）

**背景 —— 只有「单轮」一半，长任务永远提炼不出 SOP。** SOP 提炼的观察面此前**只有单轮**
（`loop/default.py:113-135` `_action_steps(ctx)`：本轮的「工具（参数）→ 结果」行）。长任务跨多轮：
每轮**各自成样本**、且任务文本**逐轮不同** ⇒ 归组键漂移（`_group_key` 的词元签名逐轮变化）⇒
**永不达阈**（`_SOP_MIN_SAMPLES=3`）。⇒ 提炼单位上移一格：以**编排任务**为粒度、以**任务过程**
（任务目标 + 各子任务步序）为观察对象。这是「Procedural = 基于长会话**任务过程**提炼」缺口的
**采集面**收口；与本 ADR 姊妹条 **ADR-0188（发布面：自动质量门）** 各改一条、互不耦合（P3）。

- **决策 ①：接入点复用 `DoneFn`，不新增接缝。** `orchestration/scheduler.py:33-35` 的完成回调
  `(task_id, outcomes, plan, session_id)` **只在成功达成 `TaskState.DONE` 时调用一次**
  （`scheduler.py:290-292`）——与 SOP「**只吸收成功轨迹**」语义天然对齐，**无需**任何失败过滤代码。
  该回调自 change 0190（ADR-0180）起已带 `session_id`（会话归因免费获得），自 change 0196
  （ADR-0186）起**已卸载出事件循环** ⇒ 在本回调里跑一次模型调用是安全的（这正是 0196 存在的理由）。
- **决策 ②：步序**不回读** `SubtaskOutcome.reply`，回读 L2 条目。** `reply` 截断 2000 字
  （`_MAX_HANDOFF_CHARS`）**不足以承载步序**；真正的步序在 `loop.steps.<trace_id>` L2 条目
  （写入时**已脱敏**，`loop/default.py:830` `redact_secrets(step)` ⇒ 新路径**不引入**任何新的密钥
  暴露面）。连接键 = 检查点 `state["trace_ids"]` → `SubtaskOutcome.trace_id`。
- **决策 ③：读取零效应，沿 `_failure_lookup` 范式。** 新增 `runtime._steps_lookup(backend)`：
  走 `MemoryBackend.search("")` 按 id 精确取条目（**不经** `MemoryStore.read` ⇒ 不强化
  `reuse_count`、不落盘；与 `runtime.py:289-308` 同形）。**任何**读取面走 `read` 都会改写 `reuse_count`
  ⇒ 是**副作用**，违 P2。
- **决策 ④：复用 `observe` + 第二实例 + `namespace`，不新增提炼方法、不改 `observe` 签名。**
  两个实例（同库、**异**样本文件、**异**命名空间）而非一个实例加参数：因为两路**步序语义不同**
  （任务级承载**子任务骨架**、单轮承载**工具调用行**），混组会产出**浑浊 SOP** —— 隔离是**正确性**
  要求，不是洁癖。`SopExtractor.__init__` 增 keyword-only `namespace: str = ""`；`_group_key` 的
  **最终键**在非空时前缀化（`task::<key>`）。缺省 `""` ⇒ **逐字不变**（单轮路径零改动）。
- **决策 ⑤：命名空间是**双向**隔离（防「反向泄漏」）。** 只把最终键前缀化**不够**：任务级产物的
  `task_types` 是 `task::report summarize`，而 `terms_of` 按非字母数字切分 ⇒ 单轮面对
  "summarize report" 的观察会**词法命中**任务级键并**采纳带前缀的键**，把单轮样本灌进任务级组。
  ⇒ 增设 `_same_namespace()`：词法复用**只在同命名空间内**进行（非空命名空间 ⇒ 只认
  `"<ns>::"` 前缀键；空 ⇒ 只认**无** `::` 的键）。两向（正向复用、反向泄漏）同时封死。
- **决策 ⑥：聚合是纯函数、上界是常量。** `runtime.compose_task_steps(plan, outcomes, lookup)`
  按 `plan.order` 遍历子任务 → `outcomes` 取 `trace_id` → `lookup(tid)` 取步序 → 拼「子任务 <目标>：<步>」
  行；无 trace / 无步序者**跳过不炸**。上界：单行 `_MAX_TASK_STEP_CHARS=400`、全体
  `_MAX_TASK_STEPS_CHARS=2000`（超界**提前收敛**，不聚满）。纯函数 ⇒ 离线可断言，无需模型。
- **决策 ⑦：规格落点。** `skills`「SOP 提炼（skill extraction）」**MODIFIED**：原文 + 既有 **7
  Scenario 逐字保留**，新增 bullet「任务级过程输入」（含**样本隔离**硬约束）+ 2 Scenario
  （「任务达阈值提炼为任务级 SOP」/「任务级与单轮样本不混组」）。canonical scen **45 → 47**、
  req **10 不变**。`orchestration` 规格**零改动**（复用既有 `DoneFn` 契约，未新增语义）。
- **落点**：`src/core/skills/sop.py`（`namespace` + `_same_namespace` + `_apply_namespace`）；
  `src/core/runtime.py`（`_steps_lookup` / `compose_task_steps` / 第二实例 `sop_task_extractor`
  （`sop-task-samples.json` / `namespace="task"`）/ `_finalize` 接线）。
- **测试**（+7，2234 → **2241**）：`test_skills.py` 3（组键前缀化确定性 / 缺省逐字不变 / 任务级与单轮
  **不混组**且 `skill_id` 不同）；`test_task_sop.py` 4（`_steps_lookup` 按 id 取回 / **零效应**
  （`reuse_count` 前后皆 0）/ `compose_task_steps` 依 `plan.order` 且跳过无 trace 者 / 聚合上界
  （单行截断 + 提前收敛））。
- **局限**：① **续跑已 `DONE` 的任务会二次触发** `_on_done` ⇒ 同一条成功轨迹被记**两次样本**
  （跨进程无去重面；去重需读检查点，属**另一**缺陷面，本 change **不修**，已登记 `known-risk.md`）；
  ② 任务级观察面只在**编排**路径生效（单轮对话不经 `DoneFn`，仍走原单轮面）；
  ③ 门未过时的**样本清理**属 0198（ADR-0188），本 change 只做采集；
  ④ 任务级 SOP 的**行为质量**由 0199（ADR-0189）端到端锚定。

## ADR-0188：SOP 自动质量门 —— 提炼产物的发布闸门（change 0198 / 账本 E135）

**背景 —— 发布的另一半缺口：提炼即 `active`，无任何质量判定。** `SopExtractor.observe` 拿到
非空文本后**直接**以 `status="active"` 发布（`skills/sop.py`）。`doc/03-interfaces/skills-interface.md`
§6 早已明文登记该缺口「无 judgment 质量门」。长任务过程输入接通后（change `0197`），任务级
样本文本更长、语义更不可控 ⇒ 「自动发布 + 无判定」的组合风险抬升：一次低质提炼会把**空泛 /
不可复用**的文本以 `active` 身份推进**路由放行集**，且**被拒亦无留痕**。这是
**Procedural = 提炼/验证/沉淀** 中段「**验证**」一环的落地；与 ADR-0187（同类姊妹条，改的是
**采集面**）各改一条、互不耦合（P3 进化局部化与可归因）。

- **决策 ①：门的形状 = 纯 callable（`SopGate = Callable[[str, str], bool]`）。** 沿用
  `SopWriter = Callable[[str], str]` 的既有依赖方向：skills 定义**契约**、judgment 提供**实现**、
  组合根**注入**（ADR-0048）。skills **不** import judgment（否则判定依赖下沉进技能层）。
- **决策 ②：判定用 noul 原语，落 `judgment/skills.py`。** 门问的是「**是否**可发布」= 布尔
  ⇒ `DecisionPrimitive.NOUL`，镜像 `Guardrail`（同「注入 `DecisionRouter` 统一决策、不内联 JEV」
  的范式）。`state={"task": …}`、`questions["noul"]["action"]={"kind": "publish_sop", "sop": …}`
  —— 门**必须**看到正文才能判质量；该载荷进既有 `DecisionTrace` 观测面（与 `Guardrail` 把
  `action` 交给 trace **同口径**，未新增暴露面）。**judgment 规格零改动**：新用途、不新增能力。
- **决策 ③：fail-open（**两层**守卫，各有职责）。** ① `SopGate` 守**自身**判定故障：路由抛异常 /
  答案缺 `noul` 键 ⇒ 吞异常返回 `True`（镜像 `SkillMatcher._score_one`）；② `observe._gate_ok`
  守**契约边界**：门是**任意注入**的可调用，其故障**不得**冒泡进 `_finalize` → 编排收尾回路
  （规格明文「提炼失败 SHALL NOT 中断 Agent 主流程」）。**方向判据**：有结论 ⇒ 以结论为准（拒是
  本 change 的收益面）；**无结论** ⇒ 放行（门是**新增**的刹车，不能让判定故障把「一直正常发布」
  的路径变成**静默不发布**）。**已知边界**：`DecisionRouter` 自身**不冒泡**（provider 不可达即回退
  主 LLM，其答案——含主 LLM 亦不可用时给出的 `False`——都是一次**有结论**）⇒ 该情形门**拒**，
  每次拒有 `warnings.warn` 留痕故不静默；本 change **不**改路由语义。
- **决策 ④：未过 ⇒ 不发布 + **清组** + 留痕**只报组键**。** 清组（`del self._samples[key]` +
  `_persist()`）与「达阈值提炼后清组」同构 —— 否则同批已判不合格的样本会在下一条到达时**再触发
  一次**提炼（+ 判定）调用；代价是需重攒（有意：宁可重攒，不做无效重判）。留痕
  `warnings.warn(f"SOP 质量门未过，不入库（组键 {key}）")` **只报组键、绝不回显提炼正文**
  （密钥红线从严）。未入库 ⇒ **无效应可回滚**（与「入库登记撤销」不冲突）。
- **决策 ⑤：接线只在**任务级**实例，且**仅在 JEV 配置时**。** `gate=sop_gate_with(router) if
  jev is not None else None` —— 沿仓内惯例（`Guardrail(router) if jev is not None else None`）。
  **只挂任务级**：动因是 0197 新接的面（样本更长、语义更不可控），改单轮面属**超范围**（P3）。
  缺省（无 JEV）⇒ `gate=None` ⇒ 发布路径**逐字不变**。
- **决策 ⑥：规格落点。** `skills`「SOP 提炼（skill extraction）」**MODIFIED**：原文 + 既有 **9
  Scenario 逐字保留**，新增 bullet「自动质量门」（缺省不启用 / 未过 ⇒ 不入库 + 清组 + 只报组键 /
  判定故障 ⇒ fail-open / 不得引入人工确认）+ 2 Scenario。canonical scen **47 → 49**、req **10 不变**。
- **落点**：`src/core/skills/sop.py`（`SopGate` 别名 / `gate` kwarg / `_gate_ok` / `observe` 门分支）；
  `src/core/judgment/skills.py`（`SopGate` + `sop_gate_with`）；`src/core/judgment/__init__.py`（导出）；
  `src/core/runtime.py`（任务级实例接线）。
- **测试**（+8，2241 → **2249**）：`test_skills.py` 4（门拒 ⇒ 不入库 + 清组 + 留痕**只报组键**
  （断言正文不在告警）/ 门放行 ⇒ `active` 入库且门看到（任务, 正文）/ 未注入门 ⇒ 发布不变 /
  门抛异常 ⇒ fail-open 放行）；`test_judgment.py` 4（noul 真/假映射 + 载荷断言 / `decide` 抛 ⇒
  放行 / 答案缺 `noul` ⇒ 放行）。
- **实测订正（红测救回一个误判）**：初版两条 fail-open 用例走「provider 抛错」⇒ **转红** ——
  `DecisionRouter` **不**冒泡异常而是**回退主 LLM**（桩回退返回空串 ⇒ `_parse_yes("")` = `False`
  ⇒ 门**拒**）。⇒ 用例改为直接桩**路由层**，并把该边界写进决策 ③（**门只看路由层之外的故障**）。
- **局限**：① **拒即丢批** —— 清组令该组**重新累积**（阈值重新计满才可能再提炼；若门持续拒，
  该组永不产出技能，只见告警）—— 有意（宁无技能，不发布低质技能）；② **只挂任务级实例** ——
  单轮面仍无门（承 0197 决策⑤ 的局部化口径，另议）；③ **判定面自身降级为「有结论」**（决策③
  已知边界）；④ **门是单次布尔判定** —— 无评分阈值 / 无多次投票 / 无产物改写（属另立账）；
  ⑤ **告警频率** —— 每次门未过一条（长任务高频被拒时会刷屏，属可观测性噪音）。

## ADR-0189：Procedural 端到端门禁 —— 「任务过程 → 技能资产」链补锚（change 0199 / 账本 E136）

**背景 —— 三段各自有单元锚，但无端到端锚。** 批次 `Phase 37` 前三条各修链路一环：`0196` 只改
完成回调的**执行线程**（锚在 `test_orchestration.py` 的线程 ident）、`0197` 新增任务级**采集面**
（锚在 `test_task_sop.py` 的纯函数 `compose_task_steps`）、`0198` 新增**发布面**门（锚在
`test_skills.py` 的 `SopExtractor` 门分支）。**三者之间**——「**真 `TaskScheduler` 跑完一个成功
任务后，真组合根装配的任务级提炼器真的把 SOP 入进真技能库**」——**无任何用例断言** ⇒ 回归时
「哪一环断了」无法从端到端视角发觉（与 ADR-0185 同型缺口）。

- **决策 ①：真材实料，只桩两个外部面。** 真组合根（`build_runtime`）+ 真 `TaskScheduler`
  （保留真注入的 `on_done=_finalize`）+ 真 `MemoryStore`（任务过程步序走 `runtime.memory.write`
  真实写入路径）。**只桩**模型接缝（`llm.completion`）与子 Agent 执行单元（`LoopPlugin.astream`）
  —— 二者是**链路之外**的外部面；替 `TaskScheduler._decomposer` 的 planner / `._router` 等于桩
  模型与执行单元，**不**桩被测链路。**刻意的非桩项**恰是 `0197`/`0198` 的改动面：`_finalize`
  闭包、任务级 `SopExtractor` 实例、`compose_task_steps`、`_steps_lookup`、`SkillLibrary`、门接线。
- **决策 ②：四条锚（含防空过）。** ①任务过程 → 技能资产（3 次 `DONE` ⇒ 入库；**并**断言 2 次时
  **不入库**）；②拒绝门 ⇒ 零入库 + **恰一次**留痕；③无门 ⇒ 照常入库（与 ② 成对 ⇒ 门是唯一差异）；
  ④捕获真实投喂提炼器的 prompt ⇒ 含 `loop.steps.<trace>` 正文、**不含** `SubtaskOutcome.reply`
  （ADR-0187 决策「读 L2 而非 reply」的**代码化**反证）。
- **决策 ③：门禁必须能咬（反证实测）。** 逐条临时回退并记录：①`_finalize` 去 `observe` ⇒ 4 红；
  ②任务级实例去 `namespace="task"` ⇒ **仅**锚 1 红（`task_types[0]` 无 `task::` 前缀）；③实例
  `gate=None` ⇒ **仅**锚 2 红（`Emitted warnings: []`）；④`compose_task_steps` 读 `outcome.reply`
  ⇒ **仅**锚 4 红（prompt 含子 Agent 回复）。复原后 4 绿 ⇒ 每条锚均咬住其目标行为。
- **决策 ④：两处桩漂移坑（实测踩到并已解决，值得留痕）。** ⓐ **状态机身份是 `task_id`** —— 同一
  编排器实例复用已 `DONE` 的 id 抛 `INVALID_TRANSITION: done → verifying` ⇒ 每次 `run` 用新
  `task_id`（归组键取自**目标** `plan.goal`，与 id 无关 ⇒ 样本仍累加同组）。ⓑ **子任务 trace_id
  需确定性** —— 桩 `LoopPlugin` 按**目标文本**映射 trace_id（`{"run alpha": "t1", …}`），与
  `loop.steps.<trace_id>` 条目一一对应，且兼容同波次并发扇出。
- **决策 ⑤：不重复既有锚。** `0196` 的线程 ident / 阻塞不冻结循环（`test_orchestration.py`）、
  `0197` 的 `compose_task_steps` 边界与 `_steps_lookup` 零效应（`test_task_sop.py`）**均不重写**；
  本 change 只补真正缺失的**端到端**四条。

**规格中性判定。** 零 `src/` 改动、零行为改动 ⇒ 无 spec delta，`.openspec.yaml` `skip_specs: true`
（沿 `0156` / `0189` / `0195` 先例）。

- **落点**：`tests/test_procedural_e2e.py`（新，4 用例）；`git diff --stat src/` **为空**。
- **测试**：+4（2249 → **2253**）。
- **局限**：① **桩子 Agent 不真跑循环** —— 不验 `loop.steps` 的**写入**侧（已由 loop 既有用例承载），
  只验其**回读**与装配；② **不覆盖续跑二次触发**（`0197` 已知局限：已 `DONE` 任务续跑会再提交一次
  样本，跨进程无去重面，属另立账）；③ **进程内跑**（跨进程断点续跑仍承 `0190`/`0191` 边界）；
  ④ **门只在任务级实例上验**（单轮面无门，承 `0198` 决策⑤ 局部化口径）。

## ADR-0190：压缩轴口径裁决 —— 轮 / 步两轴不可互换（change 0200 / 账本 E137）

**背景 —— 规格已分别如实记录两轴，但二者关系从未裁决，且有实测前科。** 系统内并存两个时间轴：
**步轴**（`LoopContext.rounds`，每用户轮新建上下文 ⇒ 自 `0` 起算）驱动**轮内**压实触发
（`Compactor.should_compact(steps, token_used, budget)`，阈值 `loop.compact_steps` 缺省 `6`）；
**轮轴**（`loop.history_turns` 缺省 `20`）驱动**跨轮**三层滑窗分层
（`plan_window(turns, budget, tiered=)`，切分单位是转录**用户角色行**）。二者各自有规格
（`上下文自动压实` / `三层窗口比例分配`），但**「不可互换」从未被写成要求**。前科：
change `0182` / ADR-0173 正是把**轮内步数**误读作**对话轮数**的一次诚实化订正；而 `compact_steps`
缺省 `6` 恰好落在外来蓝图（`memory-4-layer-architecture.md` §4.1）「Tier 2 自第 6 轮开始」的
字面区间上 ⇒ **同一误解极易复发**。

- **决策 ①：两轴分工，各自唯一旋钮，不可互换。** 步轴 → 轮内压实触发；轮轴 → 跨轮历史分层。
  `loop.compact_steps` **只**是步轴阈值，SHALL NOT 读作轮轴边界；因步轴每轮归零，
  「`compact_steps = 6` ⇒ 对话第 6 轮」在系统内**不可计算**（无任何用户轮计数器）。裁决写入
  `context` 规格新要求「压缩轴口径（轮 / 步两轴不可互换）」+ 4 Scenario。
- **决策 ②：蓝图的字面 tier 边界 `0-5 / 6-20 / 21+` 不采纳，只采纳其结构。** 理由三条：
  ⓐ 会造出**第二套冲突边界** —— 现有分层是**比率相对**的（短 `0.5` / 中 `0.3` 随 `history_turns`
  缩放，`history_turns=40` 时短层即 `20` 轮，字面 `0-5` 无法并存）；ⓑ `三层窗口比例分配` 明禁在
  **配额分配面**新增配置键；ⓒ 蓝图自身即标注 Tier 2「可配置」⇒ 采纳**三区分工的结构**、不采纳其
  **数值**。蓝图的 Tier 1/2/3 **语义上映射到轮轴**（短/中/长三层已一一对应）；步轴是蓝图**没有**
  的更细轮内机制，**不得**塞进 Tier 边界。
- **决策 ③：只裁决，不改代码。** 零 `src/` 改动（`git diff --stat src/` 为空）：不新增配置键、
  不改任何阈值或配比、不重构 `plan_window` / `Compactor` —— 本 change 只**断言**其既有语义。
- **决策 ④：守护测试是执行面，Scenario 是耐久锚。** 裁决类要求若只写文档会退化成说明文 ⇒
  要求里每条 SHALL 均由 `tests/test_axis_units.py` 断言：步轴（**不可满足的 token 预算**下单看
  步数：`6` 真 / `5` 假）+ 轮轴（`plan_window` 的短层轮数在 `20`/`40` 两点为 `10`/`20` ⇒ 随总量
  等比缩放）。**隔离一个 `or` 判据的单侧**时以「不可满足」而非「零值」排除另一侧 —— 见下局限①。
- **决策 ⑤：不重复既有锚。** `tests/test_context_window.py` 已钉住**某一点**的份额数值
  （20 轮 ⇒ 短 10 / 中 6）；本 change 钉的是**跨两点**的**缩放关系** —— 后者才是「轮比率」与
  「字面边界」的**判别式**（字面边界下两点会相等）。

**规格影响**：`context` **ADDED** 一条要求（4 Scenario）；既有 6 条 Requirement 的 Scenario
**全部逐字保留**（不做 MODIFIED）。

- **落点**：`doc/openspec/specs/context/spec.md`、`tests/test_axis_units.py`（新，2 用例）、
  `doc/04-testing/test-cases.md` §113、`coding-plan/known-risk.md`；`git diff --stat src/` **为空**。
- **测试**：+2（2253 → **2255**）。
- **局限**：① **判据单侧隔离的坑（实测订正）** —— 初版以 `budget=0` 想「排除 token 维度」⇒
  **转红**：判据是 `token_used >= budget`，`0 >= 0` **恒真** ⇒ token 维度反而**恒触发**；正解是
  用**不可满足**的大预算（`0 < 10**9` 恒真为假）。**零值不等于「关掉」一个 `or` 的某一侧。**
  ② **本 change 不产生行为** ⇒ 守护测试的**价值全在反证**（改成轮读法 / 字面边界即转红，已实测
  2 红），不能以「测试是绿的」单独证明任何事；③ **不覆盖蓝图 Tier 数值的可配置化** —— 若未来
  确需字面边界，须另立 change 并先改 `三层窗口比例分配`（本 ADR 明确不采纳）。

## ADR-0191：上下文区块配比 —— 五区块 / 80-20 安全线（change 0201 / 账本 E138）

**背景 —— 三处预算各自为政，且 loop 的预算从未到达 planner。** 外来蓝图
（`memory-4-layer-architecture.md` §3.3）给出上下文窗口「黄金配比」：系统提示 `20%` / 记忆 `15%` /
窗口 `30%` / 归档 `15%` / 缓冲 `20%`。本仓三处预算互不知晓：ⓐ `loop_limits()` 的
`token_budget = 上下文窗口 − loop.output_reserve`（**总量**，不划分）；ⓑ `_window_plan` 的
`token_budget // 2`（只覆盖历史一面）；ⓒ `LLMPlanner._system_prompt` 的**字面量 `2048`**
（与 ⓐ 无任何关系）。**ⓒ 是真缺陷**：用户改 `llm.context_window` / `loop.output_reserve`，
事实注入面**纹丝不动**。

- **决策 ①：配比收敛为确定性纯函数，纪律逐条镜像 `plan_window`。** 新增
  `src/core/context/blocks.py`：模块常量 `_SYSTEM_SHARE/_MEMORY_SHARE/_WINDOW_SHARE/_ARCHIVE_SHARE
  = 0.20/0.15/0.30/0.15`；`plan_blocks(total_budget, *, enabled) -> BlockPlan | None` ——
  **零 I/O、零模型调用**，只依赖 stdlib。五份额为**模块常量**（本**配额分配面**不新增配置键，
  同 `_STEP_THRESHOLD` / `_SHORT_SHARE` 纪律）。
- **决策 ②：20% 缓冲是「上界」，靠「不分配」实现，不是新的减法。** 总预算**已是**扣除输出预留后
  的值（`loop.output_reserve` 已在 `loop_limits()` 的派生中扣过）⇒ 若缓冲再实现为
  `total × 0.8` 的运算，**同一次预留会被扣两遍**。故 `reserve_tokens` 取**余数**
  （`total − (system + memory + window + archive)`）：五块之和**恰为** `total`，且因四个可用块
  均**向下取整**，缓冲恒 `≥ 0.20 × total`。这是外部蓝图模型与本仓模型**唯一重叠、唯一可能被
  重复计数**之处，故在规格里写成 SHALL NOT。
- **决策 ③：`None` ≠ 全零 —— 刻意偏离 `plan_window`。** `plan_window` 预算非正时返回
  `WindowPlan(0,0,0,0)`，因其消费者**就是**那个机制（全零 = 关闭回灌，**有语义**）。`plan_blocks`
  的消费者是**提示词预算**：此处「零配额」与「无配额」语义不同（前者会被当作 `budget=0` 传下去），
  唯有 `None` 能表达「**不接管**，沿用你的既有字面量」。
- **决策 ④：唯一消费者是「记忆 / 事实注入面」，其余四块**仅具咨询性**。** 五区块**不映射**到
  `_system_prompt` 的**十**个块 —— 把五份额摊到十块是**提示词契约重写**，不是一次 change
  （本 change 不做第 11 个块、不改提示词块序）。接通方式：`LoopContext.token_budget: int = 0`
  （`perceive()` 置为 `self._token_budget`）+ `LLMPlanner(block_plan=False)` 构造参 +
  `_system_prompt` 经 `_fact_budget(ctx)` 取额度。**开关缺省关** ⇒ `enabled=False` ⇒ `None` ⇒
  仍字面 `_FACT_BUDGET = 2048` ⇒ 今日提示词**逐字不变**。
- **决策 ⑤：开关在「启用面」，合法。** `loop.block_plan`（缺省 `False` + 独立访问器 + ConfigSpec
  行 + `_loop_errors` 校验期拒绝非法字面量）。规格只在**配额分配面**禁新键；本键与 `0182` 的
  `loop.compact_steps`（压实**触发**阈值）同性质 —— `三层窗口比例分配` 原文已明文许可
  「触发阈值是另一面」。注入面与 `max_tokens` 同型：组合根算一次，注入**四个 loop 的全部 planner**。

**规格影响**：`context` **ADDED** 一条要求「上下文区块配比（五区块 / 80-20 安全线）」（5 Scenario）；
既有 7 条 Requirement **逐字保留**（不做 MODIFIED）。

- **落点**：`src/core/context/blocks.py`（新）、`context/__init__.py`、`loop/protocol.py`、
  `loop/default.py`、`loop/planner.py`、`configuration/manager.py`、`runtime.py`、
  `tests/test_context_blocks.py`（新，8 用例）、`doc/04-testing/test-cases.md` §114、
  `coding-plan/known-risk.md`、`doc/02-modules/context.md`。
- **测试**：+8（2255 → **2263**；批次预估 +7，实为 +8 —— 多出的一条是
  「开关开了但 `token_budget` 未接线 ⇒ 仍字面」的**两重保险**锚）。
- **局限**：① **四个非事实块的配比不驱动任何行为** —— `BlockPlan` 的 `system/window/archive`
  三字段今日仅供观测，本 ADR **不**声称系统已按五区块分配窗口（只声称「配比已表达、**一个面**已
  接线」）；② **不覆盖 `_window_plan` 的 `// 2`** —— 窗口面已有独立口径，统一它属另一个 change
  （会动历史回灌预算，回归面更大）；③ **块内不做二级分配** —— 「记忆」份额在关键事实 / 关系
  （`0203`）/ 摘要之间不细分（`cap` 有界）；④ **回归锚的订正**：`tests/test_infomap_wiring.py:48`
  与 `tests/test_phase13.py:185` 看似钉住 `2048`，实则**各自显式传参**去测装配器契约、从不观察
  `_system_prompt` 传了什么 ⇒ 真正的逐字锚必须是**新的**（桩装配器捕获 `build(budget=)`），
  已补并反证（忽略开关 ⇒ 该锚转红）。

## ADR-0192：情景链 —— 时序相邻标注 + 零效应只读链（change 0202 / 账本 E139）

**背景 —— 情景记忆只有「点」没有「线」。** 每轮沉淀的 L2 条目共享 `trace_id` ⇒ 只有**同轮隐式**
关联，**跨轮关系为零**；全仓也没有按会话重建**时序链**的读取面。外来蓝图
（`memory-4-layer-architecture.md` §2）的情景维要求「相邻事件可追溯」。

**先做诚实评估 —— 不做 LLM 因果推断。** 仓内**不存在**确定性的**因果**事实：没有任何环节记录
「第 N+1 轮失败是因为第 N 轮做了什么」。推导它**只能**靠 LLM 推断，而 LLM 推断：**不可测正确性**
（只能测形状）、**非可逆**（需新增写路径）、**新增脱敏面**（模型生成的失败归因散文正是密钥易泄处，
参 `diagnoser.py:_MAX_NOTE_CHARS`），且 `Diagnoser` 现按 `plugin_id` 归因、**时序前驱不增加信号**。
⇒ 沿 ADR-0041 同理由拒绝先例，**不做**。只做**确定性**两件事。

- **决策 ①：标注只说「时序相邻」，不说「因果」。** `loop.failure.<trace_id>` 的 `tags` 追加
  `after:<前一已记忆轮 trace>`。命名取机制本名而非 `caused_by:`（沿 ADR-0173「按机制本名命名」
  先例），并把「因果**不作**推断」写成规格的 **SHALL NOT** —— 一条只表时序相邻的断言**不得**被
  读作归因。
- **决策 ②：标注挂在**既有失败条目**上（标签），不新开条目、不改 `MemoryEntry` 字段。**
  ⓐ 独立条目 `loop.cause.<tid>`：否 —— 每次失败多一次写入换一个字符串，且会作为 `episodic` L2
  进入压实材料；ⓑ 新增 `MemoryEntry` 字段：否 —— `MemoryEntry` 是跨 `MemoryBackend` 的**线上
  形状**，`FileBackend` 持久化需迁移；ⓒ **标签**：采纳 —— 同 `id` 幂等、`forget` 的 L2→L4 迁移
  原样存活、零 schema 变更，且**消费面本就是标签驱动**（`_PRESERVE_TAGS` / `exclude_fact_tags` /
  `assembler._shares_any_tag`）。
- **决策 ③：前序取自进程内实例状态，刻意不做记忆读。** `DefaultLoop._last_trace: dict[str, str]`
  （按 `session_id` 键），在 `remember` **末尾**更新（登记的是**上一**轮 ⇒「上一已记忆轮」口径
  由此钉死）；`remember` **只有一个调用点** ⇒ 全流程**一个维护点**。**不做记忆读**：`MemoryStore.read`
  会强化 `reuse_count`（**新副作用**），`MemoryBackend.search("")` 返回**写序**而非 `ts` 序 ⇒
  零新 I/O、零新效应。
- **决策 ④：只读链 `session_chain` 恒可用，且零效应。** `MemoryStore.session_chain(session_id="")`
  → `list[ChainNode]`（`entry_id / trace_id / ts / failed / after`，**只携带链路语义、不含正文**），
  按 `ts` 主序重建该会话情景链。刻意走 `_all_entries()`（冷 + 热）而**非** `read()` ⇒ 零 `_reinforce`、
  零效应。**未**并入 `MemoryStore` Protocol —— 与 `repair_stale_key_facts` 同处置（读面为具体类
  方法，Protocol 收窄）。
- **决策 ⑤：开关在「写入面」，读取面不受门控。** 构造参 `DefaultLoop(causal_links=False)` +
  配置 `loop.causal_links`（缺省 `False` + 独立访问器 + ConfigSpec 行 + `_loop_errors` 校验期拒绝
  非法字面量）。`False` ⇒ **无 `after:` 标签** ⇒ 失败条目**逐字不变**；而 `_last_trace` 的维护是
  零 I/O 零效应 ⇒ **不受门控**（会话中途开启亦立即可用），门控只覆盖标签的**写入**。

**规格影响**：`memory` **ADDED** 一条要求「情景链（时序相邻标注）」（5 Scenario）；既有 13 条
Requirement **逐字保留**（不做 MODIFIED）。**两处必断言的不遮蔽**：`failure` 标签仍在 ⇒
`_episodic_groups`（压实材料唯一来源）**仍排除**该条目；无 `steps` 标签 ⇒ 失败条目**仍进**「相关
事实」注入面 —— 新标签**不得**意外遮蔽任一面。

- **落点**：`src/core/loop/default.py`、`src/core/memory/store.py`（`ChainNode` / `session_chain`）、
  `src/core/memory/__init__.py`（导出）、`src/core/configuration/manager.py`、`src/core/runtime.py`、
  `tests/test_loop_causal_link.py`（新，7 用例）、`doc/04-testing/test-cases.md` §115、
  `coding-plan/known-risk.md`、`doc/02-modules/memory.md`。
- **测试**：+7（2263 → **2270**，与批次预估一致）。
- **局限**：① **前序表是进程内实例状态** —— 跨进程重启、以及三路 loop 实例（main/sub/beast）
  之间**链路会断**（只读面以 `ts` 为主序、写序为次序，如实登记）；② **标注只说「相邻」不说
  「因果」** —— 不向 `Diagnoser` 提供前驱，时间相邻**不**构成归因；③ **`session_chain` 未进
  Protocol**（读面为具体类方法）；④ **`Diagnoser` 前驱接线未做** —— 需对 `evolution/spec.md`
  「对比诊断」做约 36 行逐字 MODIFIED（本批最高风险规格编辑）⇒ 登记为遗留，不并入本 change。

## ADR-0193：实体关系抽取 —— 三元组 + 双语闭合谓词白名单（change 0203 / 账本 E140）

**背景 —— 语义记忆只有「点」没有「边」。** 结构化抽取（change 0155 / 路线图 G4）落的是**扁平**
`keyfact.<slug>`（`content="<entity>: <value>"`）—— 有**实体**、无**关系**；全仓对 `MemoryEntry`
grep `relation/edge/triple/graph` **零命中**，`MemoryBackend` 亦只有
`get/put/search/list_index/delete`。外来蓝图（`memory-4-layer-architecture.md` §1）的语义维要求
「实体间可遍历的边」——这是**唯一的能力级缺口**。

**D1 独立类型 `Relation(head, predicate, tail)`，不给 `KeyFact` 加字段。** `KeyFact` 是已发布契约
（`KeyFactExtractor = Callable[..., list[KeyFact]]`）；加宽它会动摇 `parse_key_facts` /
`scrub_key_fact` / `_plan_key_facts` 与 `test_memory_key_facts.py` 全部 30 条用例。独立类型是**加法**。

**D2 谓词 = 中英双语**闭合白名单** + 归一化（用户裁决）。** 规范谓词为英文（
`depends_on / part_of / uses / causes / blocks / owns / implements / related_to`），中文变体
（`依赖/属于/导致/使用…`）**归一化到规范谓词**后落库。表外 ⇒ **丢弃并留痕**。理由：谓词若开放，
则（a）「图」不可遍历；（b）成为**第四个无界自由文本字段** —— 新的密钥携带面；（c）同三元组幂等
去重的**基数失控**。双语表是「可用」与「有界」的折中：纯中文会话 drop 率显著下降，代价是词表维护
面翻倍、归一化规则更重（登记为局限）。

**D3 脱敏 `scrub_relation` 返回原因码，且**密钥判定先于谓词归一化**。** 顺序即安全：若先归一化，
密钥形状的**原始谓词**会走「未知谓词」分支、被**原样回显**进留痕。规则：`head`/`tail`/`predicate`
任一 `looks_like_secret` ⇒ **整条丢弃**（`"secret"`）；空实体 ⇒ 丢弃（`"empty"`）；表外 ⇒
丢弃（`"predicate"`）；否则头截断 `_MAX_FACT_CHARS`。**两处消费一个判据**（`extract.py` 的
`redact_secrets` / `looks_like_secret`），沿 `loop/default.py` 复用先例。
**留痕恒 over-redact**：`_relation_label` 对**三段一律** `redact_secrets` —— 关系与 keyfact 的
有意不对称（keyfact 的实体名**不可能**是丢弃原因，而关系的**实体名正是**原因之一）。
**不设 ref 逃生口** —— 关系没有 `coeffect:` 可引用之物。

**D4 `relation_cap` **别名到** `key_fact_cap`（`0.25/8/16` 同形）。** 全仓**一把调参旋钮**；
另起第二组常量会让「事实面一共能装多少」变成两个互不知情的数字。

**D5 存储**完全复用 `_write_key_fact` 的形状。** `id = f"relation.{slug(head)}--{pred}--{slug(tail)}"`、
`content = f"{head} --{pred}--> {tail}"`、`tags = ["relation", f"entity:…", f"predicate:…"]`
（`session:<key>` 视同 keyfact）、`source="relation"`、`kind="semantic"`、`session_id=""`、
`trace_id=f"compaction.{key}"` ⇒ **同 `id` 幂等覆盖**、同 `_GATE_EXEMPT_SOURCES` 豁免（不过
importance 闸门）、同 `Effect(op="memory.write", trace_id="compaction.<key>", undo=…)` ⇒
**回滚 `compaction.<key>` 连带撤销关系**，免费。必须走 `MemoryStore.write`，**不开新写入路径**。
`kind="semantic"` 是**承重**的：`_episodic_groups` 只收 `kind=="episodic" and layer=="L2"`
⇒ 关系**不回喂**压实材料。`id` 长度（3 × `slug(48)` ≈ 105–150 字符）已实测经 `FileBackend`
往返 —— `id` 是 JSONL **字段**（非文件名），无路径长度约束。

**D6 注入面复用既有「相关事实」块，不加第 11 个提示词块。** `_gather_facts` 以
`exclude_fact_sources=("compaction",)` 读 L2，而关系 `source="relation"` ⇒ **自动**被检索并经
`planner.py` 既有的「相关事实：」块渲染 —— 零管线改动、零新块序契约、与 `0201` 区块工作零冲突。
代价：关系与关键事实**争同一份额度**，提示词中除 `-->` 渲染外不可区分。要分开就是**另一个
change**（新块 = 提示词契约变更，且必须在 `0201` **之后**）。

**D7 DI 接缝 + 配置门（用户裁决：缺省关、显式开启）。** `MemoryStore(relation_extractor=…)`，
缺省 `None` ⇒ UNWIRED ⇒ `_extract_relations` 立即返回 ⇒ 压实**逐字不变**。与 `key_fact_extractor`
**刻意分离**（合并会改 0155 的提示词字节）。配置 `memory.relation_extract` 缺省 `False`；组合根
`relation_extractor=extract_relations_with(_llm_text) if config.relation_extract() else None`。
**这刻意偏离 `0155`**（keyfact 抽取器在组合根**无条件**接线）：代价是开箱即用时该能力**惰性**；
换来的是「无配置 ⇒ 既有路径逐字不变」这一全仓不变量。

**D8 架构门禁自动覆盖。** `test_memory_notes_api_excludes_document_corpus_dimension` AST 走查
`src/core/memory/**/*.py` 的**公开**标识符（函数/方法/参数/类名）对 `_CORPUS_DIMENSION_TOKENS`
⇒ 新增公开名（`Relation` / `scrub_relation` / `normalize_predicate` …）**自动**受检，无相撞 ⇒
**零新门禁测试**、零 `src/` 门禁改动。

- **落点**：`src/core/memory/extract.py`（`Relation` / `RelationExtractor` / `RELATION_PREDICATES`
  / `normalize_predicate` / `build_relation_prompt` / `parse_relations` / `scrub_relation` /
  `extract_relations_with` / `relation_cap`）、`src/core/memory/store.py`（构造参 / `_extract_relations`
  / `_plan_relations` / `_record_relation_drop` / `_relation_label` / `_write_relation` /
  `_GATE_EXEMPT_SOURCES` 补 `"relation"`）、`src/core/memory/__init__.py`、`src/core/configuration/manager.py`、
  `src/core/runtime.py`、`tests/test_memory_relations.py`（新，23 用例）、`tests/test_memory.py`
  （豁免面守护同步登记）、`doc/04-testing/test-cases.md` §116、`coding-plan/known-risk.md`、
  `doc/02-modules/memory.md`。
- **测试**：+24（2270 → **2294**；含参数化展开，高于批次预估的 +12/+16）。
- **反证**：① 摘掉 `_summarize_sessions` 里的 `_extract_relations(...)` 调用 ⇒ 11 红；② 摘掉
  `scrub_relation` 的密钥判定 ⇒ 2 条密钥锚红（`DID NOT WARN`）。复原 ⇒ 全绿。
- **局限**：① **每次压实多一次模型调用**（2× 抽取延迟；压实是冷路径，接受）；② **事实预算三分**
  （关键事实 / 关系 / 摘要各争 `key_fact_cap` ⇒ 有界，但这也是未来可能需要独立块的原因）；
  ③ **双语白名单上线初期仍会在长尾表达上 drop** —— 这正是**预期的可观测信号**（留痕带原始谓词）；
  ④ **无图存储 / 无遍历 API**：关系以普通 L2 条目 + 标签约定承载，不做 `MemoryBackend` 扩展
  （接口变更 + 迁移成本，且当前**零消费者**）。

## ADR-0194：语义遗忘面 —— 派生事实参与衰减，摘要类永久豁免（change 0204 / 账本 E141）

**背景 —— 语义记忆只增不减。** `MemoryStore.forget()` 的守卫（`store.py:622`）是
`entry.kind != "episodic" or entry.layer != "L2" ⇒ continue`，`kind="semantic"` 条目**永不遗忘**。
这不是实现疏漏，而是**规格写死的**：`memory/spec.md:391-392` 的「记忆遗忘」SHALL 明文「semantic
条目、L0 元策略与 L3 技能 SHALL 不受遗忘影响」，且 Scenario `提炼产物与元策略不被遗忘`
（`spec.md:423-426`）断言其不变。后果：结构化抽取的 `keyfact.*`（`source="extraction"`）与
`relation.*`（`source="relation"`）**只增不减**；`read()`/`_gather_facts` 无层过滤（L4 仅加性降权）
⇒ 陈旧派生事实持续占注入预算。四类记忆「语义」一类的**遗忘面缺半**。

**D1 收窄既有 `记忆遗忘` 的豁免面，不新开遗忘面。** 语义条目的归档语义与 episodic **完全同构**
（同一衰减评分 / 同一阈值 / 同一 L4 去向 / 同一可撤销效应）。新开一个「语义遗忘」要求会复制这四样
中的每一样，并留下**两套可漂移的判据**。收窄既有要求 = 在**同一条判据**上多放行一类条目 ⇒
改动面仅**一处布尔守卫**、零新评分逻辑。这也是本仓**首次**对一条既有 Requirement 做
**MODIFIED**（全量替换）—— 风险最高，靠 `openspec validate` + 手工归档断言
（0 Requirement-header / 0 Scenario-title 丢失）兜底。

**D2 豁免边界 = `{compaction, context}` vs `{extraction, relation}`（用户裁决②）。** `source`
取值经 grep 核实（`store.py:604,806` 的 `compaction`、`compactor.py:109,123` 的 `context`、
`store.py:899` 的 `extraction`、`store.py:963` 的 `relation`）—— 恰是 `_GATE_EXEMPT_SOURCES` 的
四成员**二分**。**摘要类永久豁免**：会话/中层摘要与压缩产出是「**已准入材料的派生骨架**」，遗忘
它们会丢失记忆的结构。**派生事实类参与**：实体/关系三元组是可再抽取、可衰减的**细节层**。
**关键澄清**：**豁免评分（`_GATE_EXEMPT_SOURCES`）≠ 豁免遗忘** —— 前者管「写入时过不过 importance
闸门」，后者管「衰减时归不归档」，二者是**不同面**，本 ADR 是后者的首次裁决。

**D3 开关缺省关、显式开启（用户裁决④）。** 构造参 `semantic_forgetting: bool = False` + 配置
`memory.semantic_forgetting`（缺省 `False`）。缺省关 ⇒ 派生事实条目与摘要类**同**不受影响 ⇒ 既有
路径**逐字不变**（沿 `0181`/`0202`/`0203` 先例）。**`forget()` 签名不动** ⇒ 三处零参调用点
（`loop/default.py:601,685`、`entry.py:1206`）逐字不变。

**D4 守卫用短路布尔，判据常量模块级。** `_FORGETTABLE_SEMANTIC_SOURCES = frozenset({"extraction",
"relation"})`（与 `_GATE_EXEMPT_SOURCES` 并列，注释点明二者是不同面）。`forget()` 守卫改
`forgettable = entry.kind == "episodic" or (self._semantic_forgetting and entry.kind == "semantic"
and entry.source in _FORGETTABLE_SEMANTIC_SOURCES)` —— 缺省关时 `and` 首项即假 ⇒ 退化为
`entry.kind == "episodic"` ⇒ **与旧守卫逐字等价**；短路布尔**不新增 `If` 嵌套层级**（守
`test_control_flow_nesting_max_three`，`0203` 教训）。归档仍走既有
`migrate(entry.id, "L2", "L4", trace_id=f"forgetting.{entry.id}")` + `_decay_score` +
`_FORGET_THRESHOLD`。

**D5 零既有测试破坏（实测）。** 既有遗忘用例全走缺省构造 `MemoryStore()` ⇒ 派生事实仍不被遗忘 ⇒
逐字不变（核验 `test_memory.py` / `test_loop.py` / `test_skills.py` 无一处翻转该新参）。⇒ 反证
**必须显式翻转构造参**（`False` vs `True` 对同一陈旧条目给出相反结果），否则新旧路径不可区分。

- **落点**：`src/core/memory/store.py`（`_FORGETTABLE_SEMANTIC_SOURCES` / 构造参 / `forget()` 守卫
  / docstring）、`src/core/configuration/manager.py`、`src/core/runtime.py`、
  `tests/test_semantic_forgetting.py`（新）、`doc/04-testing/test-cases.md` §117、
  `coding-plan/known-risk.md`、`doc/02-modules/memory.md`。
- **规格**：`memory` **MODIFIED**「记忆遗忘」+ **ADD** 3 Scenario（canonical 15 req 不变 /
  108 → 111 scen）。
- **反证**：摘掉 `self._semantic_forgetting and` 短路项 ⇒ 「缺省关」零回归锚转红；复原 ⇒ 全绿。
- **局限**：① **归档 ≠ 移出注入面** —— `read()`/`_gather_facts` 无层过滤、L4 仅加性降权 0.2 ⇒
  归档派生事实**仍可被注入**（与 episodic 遗忘**同一既有语义**；语义事实 `session_id=""` 为全局层
  ⇒ 跨会话注入亦不受会话过滤）；② **只归档「不再被重抽」的事实** —— `_write_key_fact` /
  `_write_relation` 每次压实**新建**条目并经 `_persist` 刷新 `ts` ⇒ 活跃重抽的事实永不陈旧
  （期望性质），代价是**反复出现却无用**的事实不会被遗忘 + 重抽**重置 `reuse_count`**。

## ADR-0195：SOP 技能退役 —— 连续迭代退化自动退役 + 粘性防复活（change 0205 / 账本 E142）

**背景 —— 程序记忆只进不出。** `Skill.status` 的取值域已含 `"deprecated"`（`models.py:26`），但
`src/` 内**无任何生产路径**会置它。四处取证：① `SkillIterator.decide()`（`iteration.py:135`）在 A/B
退化时**只丢草稿**，注释明写「不置 deprecated」；② `EvolutionEngine.dissolve` 的 id 前缀硬编码
`skills.evolution.`（`engine.py:227`）⇒ **永不命中** `skills.sop.<hash>`；③ `SkillLibrary` **无
`deprecate`/`retire` 面**；④ 唯一 id-agnostic 的 `SkillCrystallizer.dissolve` 是**死代码**（`src/`
内零构造）。后果：SOP 技能一经自动 `active`（`sop.py:127`，维度1「低风险自动发布」）即**永久
可路由** —— 与 P2「一切副作用可逆」及「失败即沿反方向溶解」的隐喻相悖。

**D1 触发器 = 迭代连续退化（用户裁决③：自动、不依赖人工）。** A/B 定夺**已经**算出「新版本更差」
这个信号（`result.winner != draft`）——缺的只是**把它累计起来**。同一信号单次出现是方差、**连续**
N 次出现才是趋势。计数折叠进 `decide()` 既有分支（`result.winner` 与 `draft` 本就在局部）⇒
**运行时钩子零改动**（`runtime.py:628` 的 `decide(skill)` 调用点逐字不变）、零新评分逻辑、零新
会话面。阈值 `RETIRE_AFTER_DEGRADATIONS = 3`（与 `_ITERATE_MIN_SAMPLES` 同量级）；一次提升
（新版本落地）SHALL 使计数**归零**（「连续」的字面语义，抖动不累积）。

**D2 退役面 = `SkillLibrary.deprecate`（镜像 `activate`）。** 唯一既有「改 status + 落盘 + 可逆
效应」的正路模板是 `activate`（`library.py:84-99`）：逐字镜像 ⇒ 未知 id 抛 `KeyError`、已退役
**幂等**返回、`_track_deprecation` 复用既有 `_restore_status`（带 `contextlib.suppress(KeyError)`
的幂等守卫）。效应 trace `skills.deprecate`，回滚即恢复退役前 `status`。**不物理删除**：技能仍在库
中，路由候选放行集只含 `active`/`gray`（`router.py:98`）⇒ 自动**退出注入面**，可回滚、可显式复活。

**D3 粘性防复活（用户裁决⑤）= `sop.py::observe` 守卫，不改 `register`。** 已退役的
`skills.sop.<hash>` SHALL NOT 因**同组键重抽**（`_skill_id_for` 由组键确定性哈希）无声复活为
`active`；复活 SHALL 仅经**显式** `SkillLibrary.activate`。守卫放 `observe()` 而非
`SkillLibrary.register` —— 后者的「同名覆盖」是**通用契约**，`_load` 恢复、beast 神通、notes
工作流技能、evolution 结晶产物**四处**都依赖它，改它会波及三面（超出本 change 范围）。守卫动作 =
跳过 `register` + 清组（免同批样本反复触发提炼调用）+ `warnings.warn` **只报组键**（绝不回显正文，
密钥红线）。

**D4 开关缺省关、显式开启（用户裁决④）。** 构造参 `retire_after: int | None = None`（`None` =
关闭 = 缺省）+ 配置 `skills.retirement`（**全仓首个 `skills.*` 键**，缺省 `False`）。缺省关 ⇒
两个 `if self._retire_after is not None` 均假 ⇒ `decide()` **逐字不变**（`_degradations` 恒空）。
`skills` 为非结构化段 ⇒ 集合外取值归一为关，不阻断启动（同 `memory` 段先例）。

**D5 ADR-0011 边界调和（关键）。** ADR-0011（`:89`）把「溶解」划归 evolution；ADR-0052 已为
evolution 结晶插件补齐「观察期回归自动溶解」，但那条路依赖**留出集基准**，而生产 `Evaluator` 无
基准 ⇒ `freeze`（`runtime.py:793-796`）⇒ 对 SOP **结构性不可达**。本 change 的退役是 **`skills`
自有的、反馈驱动（迭代退化）的、限定于 `skills.sop.*`** 的生命周期动作 —— 与 evolution 的「留出集
回归」**判据不同**（连续退化 vs 绝对分差）、**对象不同**（SOP 技能 vs 结晶插件）、**数据源不同**
（执行成功率 vs 留出集）⇒ **不重叠**。ADR-0011 的「evolution 负责结晶/溶解、skills 负责版本/灰度/
路由」分工**不变**：本次是 skills **治理面**内部的「停用」动作，不是「产物如何产生」的溶解。

**D6 零既有测试破坏（实测）。** `SkillIterator` 既有用例全走缺省构造（不传 `retire_after`）⇒
`_retire_after=None` ⇒ 退化分支只 `del drafts[draft]`、不碰 `status` ⇒ 逐字不变。⇒ 0205 零既有
测试破坏（2310 基线 + 17 新 = 2327）；反证**必须显式翻转** `retire_after`。

- **落点**：`src/core/skills/library.py`（`_DEPRECATE_TRACE` / `deprecate` / `_track_deprecation`）、
  `src/core/skills/iteration.py`（`RETIRE_AFTER_DEGRADATIONS` / 构造参 / `_degradations` /
  `decide()` / `_count_degradation`）、`src/core/skills/sop.py`（`observe` 防复活守卫 / `_is_retired`）、
  `src/core/configuration/manager.py`、`src/core/runtime.py`、`tests/test_skill_retirement.py`（新）、
  `doc/04-testing/test-cases.md` §118、`coding-plan/known-risk.md`、`doc/02-modules/skills.md`。
- **规格**：`skills` **MODIFIED**「技能迭代闭环」（定夺 bullet 收窄为**单次**失败 + 前向引用）+
  **MODIFIED** Scenario `A/B 退化丢弃新版本`（GIVEN 收窄、标题不动）+ **ADDED**「SOP 技能退役」
  + 6 Scenario（canonical 10 → 11 req / 49 → 55 scen）。
- **反证**：① 摘掉 `decide()` 退化分支的 `self._library.deprecate(...)` ⇒ 连续退化 / 可撤销两锚
  转红；② 摘掉 `sop.py` 防复活守卫 ⇒ 防复活锚转红。两处复原 ⇒ 全绿。
- **局限**：① **退役不可自动复活**（粘性，用户裁决⑤）—— 复活需显式 `SkillLibrary.activate`；
  ② **连续退化计数是进程内状态**（跨进程重启归零）⇒ 「连续」为进程内语义（同 `0202` 前序表）；
  ③ **可回滚仅当注入 tracker**（`runtime.py:581` 已注入；未注入时仍改状态但不记效应，与 `activate`
  同口径）；④ **三处既有旁路各置 `status` 却不共享本次 trace**（`VersionManager._deprecate` /
  `SkillCrystallizer.dissolve`（死代码） / `EvolutionEngine.dissolve`）—— 本 change **不动**；
  ⑤ **`SkillLibrary._index` 既有重复 bug**（`_index` 无条件 append，`library.py:129`）本 change
  **不修**（超范围，仅登记）。

## ADR-0196：记忆后端落盘耐久 —— 原子写 + 逐行容错（change 0206 / 台账 E143）

**背景 —— 全仓唯一「写非原子＋读不容错」双无防护面，恰是写入频率最高的主库。** 六能力走查
（2026-10-11）发现的唯一启动级硬伤：`FileBackend._persist`（`memory/backend.py:81-86`）
`path.write_text` 全量重写**非原子**（写中途被杀 ⇒ 半写/截断）；`_load`（`:70-79`）对
`json.loads` **零容错**（半写后的下次启动 `MemoryEntry(**json.loads(line))` 直接抛异常 ⇒
`build_runtime` 起不来 ⇒ 客户端整体不可用）。对照组：`CheckpointStore` 早已双防护
（`durability/store.py:97-99` tmp＋`os.replace`；`:107-110` 坏行跳过）；而 `memory.jsonl`
每轮 `remember`、压实、抽取都写——暴露度最大、防护最薄。

**D1 原子写 = 镜像 `persistence.write_state` 的写法，不复用本体。** `write_state` 对 payload 做
`json.dumps`，JSONL 已是拼接串 ⇒ 复用会二次编码。只镜像 **tmp ＋ `os.replace`** 模式（与
`CheckpointStore._persist` 同型）。失败点从「目标文件」移到「tmp 文件」⇒ 目标不动；tmp 残骸
在下次写入被覆盖（同 CheckpointStore 口径，不额外清理）。

**D2 容错面 = `ValueError | TypeError`，单次汇总告警只报计数。** `json.JSONDecodeError` ⊂
`ValueError`（半行/坏 JSON）；`MemoryEntry(**record)` 对缺字段/多字段抛 `TypeError`（结构不符
行）。**不收 `OSError`**——读失败（权限/IO）仍炸启动：环境问题 ≠ 数据损坏，静默吞掉权限错误
会把「全库不可读」伪装成「空库」。告警在 `_load` 末尾**汇总一次**（`损坏 N 行`＋文件名），
**绝不回显行内容**（条目可能含敏感信息，密钥红线的同族纪律）。

**D3 为什么缺省生效、无开关（本批 9 个 change 的唯一例外）。** 这是**缺陷修复**而非新行为：
完好文件的行为**逐字不变**（往返逐字节不变锚）；损坏文件从「启动崩溃」变为「跳过坏行」。给
「起得来」加开关等于允许用户把客户端关成砖——开关保护的是「既有路径不变」承诺，而既有路径
（崩溃）本身就是被修复的对象。对照 `0207`~`0214`：那些是**新行为**，须缺省关。

**D4 坏行寿命 = 到下次写为止。** 坏行不会自行修复，但任一写操作触发 `_persist` 即以完好集合
**全量覆盖**之。失效记忆条目的**修复面**另有 0174 运维动词（按会话重抽 + 删除 + 备份），本
change 不越界。

- **落点**：`src/core/memory/backend.py`（`_persist` / `_load`）、
  `tests/test_memory_backend_durability.py`（新）、`doc/04-testing/test-cases.md` §119、
  `coding-plan/known-risk.md`、`doc/02-modules/memory.md`。
- **规格**：`memory` **ADDED**「记忆后端落盘耐久（backend durability）」+ 4 Scenario
  （canonical 15 → 16 req / 111 → 115 scen）。
- **反证**：实现前实录 3 红（半写丢库 / 坏行炸启动 ×2）—— 旧实现的失败点落在目标文件上
  （截断即全丢）；新实现落 tmp 上。两锚复原（`_load` 去容错 / `_persist` 去原子）即回红。
- **局限**：① `.tmp` 残骸不清理（同 CheckpointStore）；② 坏行告警每次构造后端一次，不区分
  「同一坏行反复出现」；③ `search("")` 的层过滤在 `MemoryStore` 侧而非 backend 侧（既有行为，
  不动）。

## ADR-0197：恢复扫描入口全覆盖 —— 一旗补接线、机制不重造（change 0207 / 台账 E144）

**背景 —— 能力在，接线不全（六能力走查「重启恢复」硬伤②）。** `0191`（ADR-0181）立了
「启动扫描未完成任务并呈现」：`_surface_incomplete`（`entry.py:436-448`）调 `runtime.recover()`
（纯扫描、无 replay ⇒ 零副作用），有未完成任务则告警 + 提示 `task --resume`，**只报 task id**。
但 `0191` 只接了**两个**入口：`serve`（`:507`）与 `task` fresh（`:1766`）。`REPL` / `run` /
`app` / `mcp serve` **四个入口启动时静默** ⇒ 从 REPL 或桌面壳进入的用户看不到「上次有任务没
跑完」。这是六能力走查中「动态记忆/重启恢复」一项的硬伤②：**能力在，接线不全**。

**D1 一旗补接线，不新造机制 —— `_build_ui` 的 `surface_recovery` 旗早已就位。**
`0191` 为 `serve` 建好了机制：`_build_ui(..., surface_recovery: bool=False)`
（`entry.py:452/:469-470` 内 `if surface_recovery: _surface_incomplete(runtime)`）。走 `_build_ui`
的三个入口（`repl` `:499` / `run` `:1688` / `app` `:523`）**一旗即成**——本 change 是接线补全，
**非新能力**。故规格只 **MODIFIED**「崩溃恢复」（不 ADD 新 Requirement）。

**D2 `mcp serve` 显式补调，不走 `_build_ui`。** 它自建 runtime（不需求 `UIAPILayer`）⇒ 无法用
旗；在 `build_runtime` 之后、`MCPServer(...)` 构造之前**显式**调 `_surface_incomplete(runtime)`
（`entry.py:775`）——顺序上「呈现先于协议就绪」，用户先看到告警再进服务。

**D3 呈现面 = stderr 单一，机制既有即满足协议约束。** `_surface_incomplete` 的实现已是
`warnings.warn` + `print(..., file=sys.stderr)` ⇒ 对 `mcp serve`（stdio transport，**stdout 是
协议流**）**零额外改动**即满足「SHALL NOT 污染 stdout」约束。呈现**只报 task id**
（`:445-448`），不回显任务正文 / 记忆 / 密钥——密钥红线的同族纪律。

**D4 仍不自动重执行 —— 守 P2 与 `0191` 纯扫描语义。** 本 change 只补「呈现覆盖面」，`recover()`
的纯扫描语义（无 replay 回调 ⇒ 零副作用）**逐字不动**；续跑仍由用户显式 `task --resume`。
「呈现先于协议就绪」不改变「扫描先于执行」——恰是 `0191` 的既定次序，只是入口补齐。

- **落点**：`src/core/entry.py`（`_repl` `:499` / `_app` `:523` / `_run` `:1688` 三处旗 +
  `_mcp_serve` `:775` 显式调用）、`tests/test_entry.py`（+6 用例）、`doc/04-testing/test-cases.md`
  §120、`coding-plan/known-risk.md`、`doc/02-modules/cli-ops.md`。
- **规格**：`durability` **MODIFIED**「崩溃恢复」（全量替换 narrative，补「全部交互入口」句 +
  **ADD** Scenario「全部交互入口启动扫描呈现」；其余 7 Scenario 逐字保留）—— canonical
  **4 → 4** req（MODIFIED 不增 Requirement）/ **13 → 14（+1）** scen。
- **反证**：摘旗（`repl`/`run`/`app` 去 `surface_recovery=True`）＋摘 `mcp serve` 显式调用 ⇒
  4 个「入口呈现」参例全红（实测 `4 failed`）；复原即 6 passed。
- **局限**：① 测试桩 runtime 需具备 `recover()`（本 change 为旧桩 `tests/test_entry.py`
  `_patch_fake_runtime` 与 `tests/test_phase13.py` `_FakeRuntime` 补 `recover → []`，非生产改动）；
  ② `recover()` 扫描面仍未覆盖「轮级检查点」（`0214` 另立）；③ `serve` 既有呈现不受影响（同旗
  同函数）。

## ADR-0198：保留策略接线 —— 缺省关、只接两通道、落盘后清理（change 0208 / 台账 E145）

**背景 —— 库齐备、生产零调用。** `RetentionManager.apply(policy)`（`durability/retention.py:25-49`）
三通道（数量上限 / 时间窗口 / 存储配额）＋ `pin`/`unpin`（`:51-55`）API 齐备、规格已写
（`durability/spec.md`「生命周期与保留策略」，含 pinned 保护），但**生产零调用** —— 每次波次 / 任务
完成都 `create_checkpoint` 追加快照（`durability/manager.py:32-54`，`put` 追加非覆盖）而**无人清理**
⇒ `checkpoints.jsonl` 无限增长。且 `0214`（主 loop 轮级检查点）会把写入频率显著抬高 ⇒ 本 change
**先行**铺好清理面。

**D1 只接两通道，存储配额不接。** `storage_quota` 通道的 `apply` 在「全部 pinned 仍超配额」时抛
`RETENTION_QUOTA_EXCEEDED` ⇒ 接进 `_write_checkpoint` 会让**检查点落盘这条路径可能炸**（写检查点
本该是尽力而为的持久化，不该因配额把主流程打断）。故 `storage_quota` 与 `RetentionPolicy.strategy`
字段（无消费者）**留库能力**，仅登记。暴露的两键：`durability.retention.max_count`（int ≥1）与
`durability.retention.time_window_s`（float ≥0）。

**D2 接线点 = 落盘之后，永不误删刚写者。** `RetentionManager.apply` 在 `_write_checkpoint` 内
`create_checkpoint` **之后**调用：新检查点已在库中、其 `ts` 最大 ⇒ 数量上限的「清理最旧」永不会
命中刚写的那个。时间窗口判据 `cp.ts < now - window` 对刚写者恒假（`ts ≈ now`）⇒ 同理安全。

**D3 访问器返回原始值对，不返回 `RetentionPolicy` —— 守底座边界。** `configuration` 是**底座模块**
（`test_architecture.py:58` `BASE_MODULES`）⇒ **不得** import 能力层 `durability`（`RetentionPolicy`
在 `durability.models`）。故访问器 `retention_limits() -> tuple[int | None, float | None]`；`timedelta`
装配留在组合根。先例：`max_concurrency()` 返回 int、`loop_limits()` 返回 tuple（均不返回能力层类型）。

**D4 缺省关 ⇒ 零清理、逐字不变。** 两键皆缺省 ⇒ `retention_limits()` 返回 `(None, None)` ⇒ 组合根
`retention_policy = None` ⇒ `_write_checkpoint` 内 `if retention_policy is not None` 短路 ⇒ **不清理
任何检查点**。守全仓不变量「新行为缺省关 ⇒ 既有路径逐字不变」（对照 `0206`：那是缺陷修复、唯一例外）。

**D5 非法值阻断启动。** `_retention_errors` 镜像 `_circuit_breaker_errors`：`max_count` 须为 **≥1 的
整数**（`bool` 拒收；`0` 拒收 ⇒ 不会意外「清空全部未 pinned 检查点」）、`time_window_s` 须为 **≥0 的
数值**（`bool` 拒收）；**两键皆缺省合法**（= 不清理）。非法值进 `validate_schema` errors ⇒
`ConfigurationError` 阻断启动。

- **落点**：`src/core/configuration/manager.py`（两 ConfigSpec + `retention_limits()` +
  `_retention_errors`）、`src/core/runtime.py`（`_write_checkpoint` 落盘后 `apply`）、
  `tests/test_retention_wiring.py`（新）、`doc/04-testing/test-cases.md` §121、
  `coding-plan/known-risk.md`、`doc/02-modules/durability.md`、`doc/02-modules/configuration.md`。
- **规格**：`durability` **MODIFIED**「生命周期与保留策略」（全量替换 narrative + **ADD** Scenario ×3；
  既有两 Scenario 逐字保留）—— canonical **4 → 4** req（MODIFIED 不增）/ **14 → 17（+3）** scen。
- **反证**：摘 `_write_checkpoint` 的 `retention.apply` 调用 ⇒ 三个重载用例红（`test_max_count_prunes_oldest`
  / `test_time_window_prunes_expired` / `test_pinned_checkpoint_survives_pruning`，实测 `3 failed`）；
  复原即 13 passed。缺省关用例（`test_default_off_never_prunes`）在接线缺失时**恒绿** ⇒ 单独不构成
  证据，其价值在于**与三例成对**（防「缺省即清理」的越界）。
- **局限**：① `max_count` 过小会清理未完成任务的旧检查点（续跑回退更早，非整体丢失，且用户显式配置）；
  ② 每次落盘后 `apply` 需 `list_checkpoints` + 排序（O(n log n)）—— 检查点写入本在波次/轮次边界
  （非主循环热路径），可接受；③ `storage_quota` 与 `strategy` 未接（D1）；④ 清理**不逐条记可逆效应**
  （`store.delete` 直接落盘，与既有 `RetentionManager` 行为一致 —— 保留策略是**生命周期管理**而非
  用户数据的可撤销操作，规格未要求可逆）。

## ADR-0199：容错件接线 —— Retry 进生产、Fallback/Pipeline 留库（change 0209 / 台账 E146）

**背景 —— 四件有规格、生产零调用、两件连测试都没有。** `constraints/spec.md`「容错中间件」点名
熔断 / 降级 / 重试 / 回滚四件；`fault_tolerance.py` 四件齐备、`middleware.py` 的 `Pipeline` 齐备，
但 `RetryPolicy` / `Fallback` / `Rollback` / `Pipeline` **生产零调用**，其中 `Fallback` / `Pipeline`
**零测试**。熔断早已接线（change 0052），其余三件是死代码。本 change 把**重试**接进生产、给
`Fallback` / `Pipeline` 补首测、并把**回滚维持既有单一路径**。

**D1 只接 Retry，理由是形状与语义。** `Pipeline` / `Fallback` 的失败面是**异常形状**（核心抛异常 →
逆序 `on_failure`），而 `DefaultLoop.act` 是**结果形状**（返回 `ActionResult(failed=...)`，不抛）。
硬接需人为把结果翻译成异常再翻回来 —— 且 `Fallback` 的降级回复会（a）**静默抑制**
`default.py:458-459` 的 trace 回滚（该回滚以 `result.failed` 为触发）、（b）**终结 loop 杀死 ReAct
自愈**（注释 `:439` 明写工具失败不判轮失败）。故 `Fallback` / `Pipeline` 为**保留库能力**（接口齐备
+ 首测覆盖），**不接生产**。降级回复上线若需要，另立 change。

**D2 注入方式 = `act_wrapper` 构造参，包裹 `act` 本体。** 重试是**在同一动作上重复尝试**，语义上
包 `act` 而非绕行事件流 —— `action_started` / `action_completed` 仍按**单次 `_act` 调用**各记一条
（重试不额外发事件），`middlewares` / `action_observers` 在 loop 侧逐次生效、语义不变。
`DefaultLoop.__init__` 里 `self._act = act_wrapper(self.act) if act_wrapper else self.act`；
`None` ⇒ `self._act is self.act` ⇒ 既有路径**逐字不变**。

**D3 显式白名单 + 仅可逆工具 + 惰性查表。** 只有 `{TIMEOUT, EXECUTION_FAILED}` 重试（未来错误码
**fail-closed**）；策略性拒绝（`INVALID_ARGS` / `COEFFECT_MISSING` / `GATE_DENIED` /
`IRREVERSIBLE_BLOCKED` / `NO_TOOL_PROVIDER`）天然不在白名单 ⇒ 不重试。**仅可逆工具**重试：不可逆
工具的「部分外写」被重试会放大 → 封死。可逆集合**惰性**从 `provider.active_tools()`
（`provider.py:77-79`，`ToolDef.reversible`）建 frozenset，**只在失败路径**算一次并缓存。

**D4 耗尽原样返回 —— 不降级、不改码。** 判停复用 `RetryPolicy.should_retry`（次数上界**单一真源**，
适配层不复制该逻辑）；适配层传一个非 `ConstraintError` 的轻量异常 `RetriableToolFailureError` 承载
失败码（`should_retry` 对 `ConstraintError` 恒 False，故不能用它）。耗尽时**返回最后一次失败结果
原样** ⇒ 保住 `:458-459` 回滚与 `:439`「工具失败不判轮失败」。`RETRY_EXHAUSTED` 码仍不使用。

**D5 重复副作用已核 —— 效应只在成功后记。** `provider.ainvoke` 的 `tracker.record`
（`provider.py:136-149`）在 `_call` **成功之后**才执行 ⇒ 重试期间失败的尝试**不记效应**，不会双
记账。测试断言「flaky 第 2 次成功 ⇒ `rollback().reverted == 1`」。

**D6 访问器返回原始整数 —— 守底座边界。** `configuration` 是底座模块（`BASE_MODULES`）⇒ 不得
import 能力层 `constraints`。故 `retry_attempts() -> int`（缺省 `0` = 关）；`RetryPolicy` 由组合根
装配（同 `retention_limits()` 先例）。键 `constraints.retry_attempts`（`--constraints.retry-attempts`
/ `CORE_CONSTRAINTS_RETRY_ATTEMPTS`，ADVANCED 暴露面）。

**D7 Rollback 不重复接入 —— 单一路径。** 规格「失败回滚」Scenario 已由 loop 级 `rollback(trace_id)`
（`default.py:458-459`，以 `result.failed` 触发、撤销本轮 trace 下全部可逆副作用）满足。再经
`constraints.Rollback` 接一次是**第二条路径**（同语义两处实现 ⇒ 双撤销风险）。故 `Rollback` 留库
能力、不接。

**D8 宠物不接。** 沿 `runtime.py:1146` 隔离注记（宠物流量不应污染主线/神兽的容错态），三 loop
（主 / 子 / 神兽）接、宠物不接 —— 与熔断链同口径。

- **落点**：`src/core/loop/fault_adapter.py`（新：`FaultChain` / `build_fault_chain` /
  `RetriableToolFailureError`）、`src/core/loop/protocol.py`（`ActFn` Protocol）、
  `src/core/loop/default.py`（`act_wrapper` 参 + `self._act` + `:437`）、
  `src/core/configuration/manager.py`（ConfigSpec + `retry_attempts()` + `_retry_errors`）、
  `src/core/runtime.py`（`_fault_wrapper` + 三 loop 注入）、`tests/test_fault_wiring.py`（新）、
  `tests/test_constraints.py`（Fallback/Pipeline 首测）、`doc/04-testing/test-cases.md` §122、
  `coding-plan/known-risk.md`、`doc/02-modules/constraints.md`、`doc/02-modules/loop.md`。
- **规格**：`constraints` **MODIFIED**「容错中间件」（全量替换 narrative + **ADD** Scenario ×5；
  既有 7 Scenario 逐字保留）—— canonical req **不变**（MODIFIED 不增）/ scen **+5**。
- **反证**：摘 `_wrapped` 内重试循环（只留首次调用）⇒ `test_reversible_flaky_retries_then_succeeds`
  / `test_execution_failure_retries_then_succeeds` / `test_exhausted_returns_last_failure_as_is` 红；
  摘可逆门（`action.tool_id not in self._reversible_ids()` 恒假）⇒ `test_irreversible_tool_not_retried` 红。
- **局限**：① 遥测 `duration_ms`（`default.py:442`）跨整个 `_act` ⇒ **含退避时长**（语义为端到端
  耗时）；② `TIMEOUT` 的**部分外写**既有风险被重试放大 —— **只对可逆工具重试**即缓解（不可逆不重试）；
  ③ `RETRY_EXHAUSTED` 码仍不使用（D4 原样返回语义无需改码）；④ 重试不重发 `action_*` 事件 ⇒ 观测面
  只见一条「动作耗时较长」；⑤ `retry_attempts` 语义为**尝试次数上界含首次**（= `RetryPolicy.max_attempts`）。

## ADR-0200：rag 文档进信息地图 —— 生产侧接线、fail-soft 读侧、先滤后截（change 0210 / 台账 E147）

**背景 —— 目录面早通、来源只有一处。** `InfoMap` 的两个入口（`index` = 原文 + 目录索引、
`register` = 仅原文）生产只在组合根接了一处：Core.md 项目信息段（`runtime.py:713-721`，
change `0140` / 账本 E77）。context spec「信息地图」的**千页级业务文档**场景（`context/spec.md:71`）
从未兑现 —— 而 rag 摄取（`ingest.py:52-64`）恰好把整份文档切块写入落盘向量库，**原文就在库里**。

**D1 改的是生产侧，不是装配器。** 目录面（`DynamicAssembler._gather_pointers`）早已在消费
`InfoMap.documents()`：逐文档 `lookup(doc_id, task)` 取任务匹配指针。缺的是「**谁往地图里放文档**」。
故本 change **零改动** `context/` 包内代码。这也是 **ADR-0097⑥**（rag 参与 loop 上下文的**唯一合法
路径**是组合根注入）下的正确落点：`context` 不 import `rag`、`rag` 不 import `context`，
桥只能由组合根搭（`tests/test_architecture.py:326-347` 守护，零改动即过）。

**D2 `index` 而非 `register`。** `register` 只缓存原文 ⇒ `lookup` 走二阶线性扫描兜底
（段数上界 20 ⇒ 千页文档只看得到头 20 段），语义上退化为兜底路径。要兑现「先定位指针再按需取详情」
必须**有目录** ⇒ 用 `index`。

**D3 块文本按数字后缀拼回 —— 定长切片 ⇒ 无损。** `_build_chunks` 按定长 `chunk_size` 切片、
`chunk_id = f"{doc_id}#{i}"`（`i` = `enumerate` 下标）⇒ **按块序号升序拼接 = 原文**。
按 `chunk_id` **字典序**拼则踩 `#10 < #2` 陷阱（逐字符比较：`"1" < "2"`）⇒ 错序。故排序键取
**数字后缀** `int(chunk_id.rpartition("#")[2])`；不可解析者排最后并按 id 定序（确定性）。
`document_ids()` 亦 `ORDER BY doc_id` ⇒ 上限截断是**确定性**的（否则 DB 行序不定，「谁进谁不进」不可测）。

**D4 读侧访问器 fail-soft 缺省（非 `abstractmethod`）。** `VectorStore` 是**对外契约**
（规格「存储与 Embedding 依赖注入隔离」：第三方实现可替换 sqlite）。加抽象方法 = **破坏性变更**
（既有第三方实现一 import 就 `TypeError`）。故基类给缺省实现返 `[]` ⇒ 既有实现**零改动**即静默
no-op：目录面拿不到 rag 文档但**不炸**。这与 `0209` 重试白名单的 **fail-closed** 方向**相反** ——
因为此处的失败语义是「少一块能力」（增益面）而非「多做一次副作用」。

**D5 文档数硬上限 `_RAG_INFO_MAP_MAX_DOCS = 16`。** 目录层指针块**不受预算裁剪**：
`_gather_pointers` 对每文档取 `lookup(...)[:_MAX_POINTERS_PER_DOC]` —— 上界是**每文档**条数，
**没有**跨文档总量上界。N 个 rag 文档 ⇒ 每步注入 O(N) 行。替代方案「给 `BudgetManager` 加按块
记账」被**否决**（改预算器影响面远超本缺口；`plan_blocks` 纪律 `0201` 刚立，不宜同批再动）。
以文档数上限换有界性 —— 取值与「一份千页文档」同阶。

**D6 先滤后截 —— 上限是「rag 文档总量」的上界。** `core-profile` 不占配额：先截后滤会让被跳过的档
白占一个名额（实测 21 档时先截后滤 ⇒ 实入 15 ≠ 16）。实现为
`[d for d in doc_ids if d != _CORE_PROFILE_DOC_ID][:16]`。

**D7 跳过 `core-profile`。** 该文档已由 `profile.context` 分支以**真源**（Core.md 原文，带
`# {section}` 头）建索引；rag 库里若有同名摄取副本，再 `index` 会用**块拼回文本**覆盖真源
（丢 `#` ⇒ 建不出 heading 指针）。故显式跳过（`_CORE_PROFILE_DOC_ID`，`runtime.py:386`）。

**D8 逐文档降级不炸。** `_index_rag_docs` 对每文档独立 `try/except Exception: continue`；
`document_ids()` 整体失败则全部不进。理由：地图是**增益**面，装配必须成功 —— 一份坏档不得让整个
runtime 起不来。此处**连告警都不发**（该路径每次装配都走，逐次告警会刷屏）；坏档可见性由 rag
自身的检索面错误码承担。

- **落点**：`src/core/rag/vector_store.py`（`VectorStore.document_ids` / `chunk_texts` 缺省 +
  `SqliteVectorStore` / `InMemoryVectorStore` 实现 + `_chunk_order` / `_UNORDERED_CHUNK`）、
  `src/core/configuration/manager.py`（ConfigSpec `context.rag_info_map` + `rag_info_map()`）、
  `src/core/runtime.py`（`rag_store` 局部 + `_index_rag_docs` + `_RAG_INFO_MAP_MAX_DOCS`）、
  `tests/test_rag_wiring.py`（增补）、`doc/04-testing/test-cases.md` §123、`coding-plan/known-risk.md`、
  `doc/02-modules/rag.md`、`doc/02-modules/context.md`。
- **规格**：`context` **MODIFIED**「信息地图」（全量替换 narrative + **ADD** Scenario ×3；既有 3
  Scenario 逐字保留）＋ `rag` **MODIFIED**「本地向量库存储」（全量替换 narrative + **ADD**
  Scenario ×1；既有 3 Scenario 逐字保留）—— canonical: context **8 → 8** req / **33 → 36** scen（「信息地图」条内 Scenario **3 → 6**）；
  rag **7 → 7** req / **14 → 15** scen。
- **反证**：摘 `others[:_RAG_INFO_MAP_MAX_DOCS]` 的上限切片 ⇒ `test_index_rag_docs_caps_...` 红
  （实测 `1 failed, 13 passed`）；摘 `if config.rag_info_map():` 守卫 ⇒
  `test_rag_info_map_flag_off_leaves_catalog_unchanged` 红（实测 `1 failed, 13 passed`）；两次复原
  ⇒ 14 passed。
- **局限**：① **CLI 摄取 → 运行中进程不可见** —— InfoMap 是**进程内**对象，`rag ingest`（另一进程）
  写的是**落盘向量库** ⇒ 运行中的 serve 要**重启**才把新档建进地图（同 `skills.json` 先例）；
  ② `fetch_detail` 只回 `pointers[0].summary`（既有契约非本缺陷）；③ **全语料进内存** ——
  `InfoMap.index` 把原文缓存于 `self._docs` ⇒ 上限档数的全文常驻内存（上限即兜）；
  ④ 超 16 档只看到前 16（按 `doc_id` 序）—— 上限策略是**确定性截断**而非按重要性挑选；
  ⑤ `chunk_texts` 依赖「块 id 以 `#<数字>` 结尾」这一 `ingest` 的**实现约定**（另一种
  VectorStore 实现若换 id 形状，须自行按序返回）。

## ADR-0201：情景链读侧进只读诊断面 —— 注入可调用、呈现有界、类型零变更（change 0211 / 台账 E148）

**背景 —— 写侧通了、读侧不通。** change `0202` / ADR-0192 立了 `MemoryStore.session_chain`
（零效应只读：按 `ts` 主序重建某会话的情景链，节点携带 `entry_id / trace_id / ts / failed / after`），
并把 (f) 只读链重建写进了 `memory/spec.md:769`。但**全仓零生产消费者** —— `session_chain` 只被自己的
单测调用。六能力走查中「有规格无接线」死代码的一支：链只在测试里可读，运维面（TUI 只读命令族 /
CLI 诊断源）看不到「哪些轮失败、链条怎么接的」。

**D1 落 `core.diagnostics`，不落 `memory` / `ui`。** 诊断包是 `0162` 立的**只读诊断源**
（`doctor` / `status` / 六张列表视图的**单一**产出方，「SHALL NOT 各写一份检查逻辑」）。`session_chain`
是**读取面**、无行为开关 ⇒ 属「呈现」而非「能力」：加在 `memory` 包内会多一个无人消费的公开方法；
加在 `ui` 包内则 CLI 侧拿不到，且 `ui` 反向引用 diagnostics ⇒ 写进去**成环**。故落 `views.py`，
与 `render_sessions` / `render_notes` **同形**（`_sealed` 包裹 ⇒ 空 ⇒ `（空）`、读取异常 ⇒ 一行说明、
**视图不抛**）。

**D2 句柄是「注入的可调用」而非 store 对象。** 沿 `Deps` 既有惯例（`SessionsHandle = Callable[[], ...]`，
`deps.py:30`）：`chain: ChainHandle | None`，`ChainHandle = Callable[[str], list[ChainNode]]`。
注入的是 `runtime.memory.session_chain` **本身**（bound method）⇒ 诊断包只认**签名**，
**不建 store 实例**、**不引 `core.runtime`**（硬红线，`test_runtime_is_sole_composition_root`）。
`ChainNode` 为**类型标注**而 import 是允许的：`diagnostics` 与 `memory` 同属 `CAPABILITY_MODULES`
（`tests/test_architecture.py:63-90`），`deps.py` 早已 import `core.notes` / `core.skills`。

**D3 呈现有界且不含正文。** `ChainNode` 契约刻意**不含正文**（`store.py:121-125`：「本类不得成为
第二条注入通道」）⇒ 视图天然只有链路语义，**不需要**再设脱敏闸。**有界**：单会话只取**最近**
`_MAX_CHAIN_ROWS = 20` 节（`nodes[-20:]`）—— 理由同 `0210` 的文档数上限：只读视图的输出**整体进
时间线块**，长会话的链可以无界增长；「最近 N 节」是诊断视角的正确默认（最新状态最有用）。

**D4 零效应由既有实现原样承载。** `session_chain` 走 `_all_entries()`（冷区 + 热区）而**非**
`read()` ⇒ 不触发 `_reinforce`。本 change **不触碰** `memory` 包任何一行 ⇒ (f) 的零效应保证
**原样**成立，新视图只是**消费方**。

**D5 为何不扩 `ChainNode` 带 `session_id`（计划期修正）。** 计划草稿写「按会话分组，`session_chain("")`
不过滤再分组」，但 `ChainNode` **不含** `session_id`（`0202` 交付的节点契约只承载链路语义），
而分组恰需它。**否决**「给节点加字段」：那会把**呈现需求**反向渗进能力层，并迫使 `0202` 的 (f)
重写。改用**已有**的 `Deps.sessions` 句柄（`_diag_deps` 恒注入 `SessionRegistry(...).list`）
逐会话取链 ⇒ 同一效果、**类型零变更**。会话面缺失（某调用方只注入 `chain`）⇒ 退回**不过滤**的一节
（`session_id=""`，即 `session_chain("")` 语义）。

**D6 生产侧接线 = 裸店（免 runtime）。** `_diag_deps`（`entry.py:540-570`）注入
`MemoryStore(backend=FileBackend(_state_path("memory.jsonl")))` 的 `session_chain` ——
先例 = `_memory_summary`（`:1632-1637`，**同一路径助手、同一裸构造**）。免 runtime 是刻意的：
装配 runtime 需要**有效**配置，而「配置坏了」恰是最该跑诊断的场景（ADR-0153 决策①）；
`session_chain` 零效应 ⇒ 诊断面「不产生副作用」的红线保持。

- **落点**：`src/core/diagnostics/deps.py`（`ChainHandle` + `Deps.chain`）、
  `src/core/diagnostics/views.py`（`_MAX_CHAIN_ROWS` + `render_chain` + `_chain_sessions`）、
  `src/core/diagnostics/__init__.py`（导出）、`src/core/entry.py`（`_memory_chain()` + `_diag_deps` 注入）、
  `src/core/ui/repl.py`（`/chain` + `_show_chain`）、`tests/test_diagnostics.py` / `tests/test_repl.py` /
  `tests/test_entry.py`（增补）、`doc/04-testing/test-cases.md` §124、`coding-plan/known-risk.md`、
  `doc/02-modules/memory.md`、`doc/03-interfaces/ui-interface.md`。
- **规格**：`memory` **MODIFIED**「情景链（时序相邻标注）」（全量替换；narrative 补 **(g) 只读呈现面**
  ＋ **ADD** Scenario ×2「只读诊断面呈现链」/「句柄未注入或空链时不抛」；既有 (a)–(f) 与 5 个 Scenario
  **逐字保留**）—— canonical: memory **16 → 16** req / **115 → 117** scen（「情景链」条内
  Scenario **5 → 7**）。
- **反证**：摘 `/chain` 命令登记 ⇒ palette ×2 ＋ 只读块用例红（实测 `3 failed, 22 passed`）；
  摘 `_diag_deps` 的 `chain=` 注入 ⇒ 接线用例红（`1 failed, 96 deselected`）；把 `render_chain`
  的句柄分支短路为 `if True: 未接线` ⇒ 链用例 ×6 红（`6 failed, 104 deselected`）；三次复原
  ⇒ 逐字节相同（`diff -q` 三文件）。
- **局限**：① **`/chain` 无参数** —— 只读命令族（`0163`）的 `handler` 直分发**无参数面** ⇒ 只能看
  「各会话的最近 N 节」，按会话钻取需带参命令（未做）；② **只呈现** —— 不提供跳转到条目正文的入口；
  ③ **CLI 无 `chain` 子命令** —— 句柄在 CLI 入口同样被注入（`_diag_deps` 单点）⇒ 未来加子命令是
  **一行**；④ 会话分组依赖 `Deps.sessions`（注入面缺失时退化为单节不过滤）。

## ADR-0202：结晶通路 —— runner 注入语义 / OPT_IN 门控 / CLI 注册面（change 0212 / 台账 E149）

**背景 —— 「技能→插件」被 freeze 卡死。** change `0119`（数据面 / 执行面分离）交付了
`BenchmarkRegistry`（基准集 + 基线，JSON 单文件落盘、跨进程可读）与 `BenchmarkScorer(benchmarks,
runners=...)`：**接收**执行器字典，但 `runners` 是**由组合根注入**的受信代码，**不落盘**。而
`runtime.py:837` 构造 `BenchmarkScorer(benchmarks)` 时**未传 `runners`**，且**全仓无**生产
`register` / `set_baseline` 面 ⇒ `BenchmarkScorer.__call__` 永远在「无绑定基准 / 无样本 / 无 runner」
三态下返 `None`（`evaluator.py:281-286`）⇒ `Evaluator` 判 `freeze` ⇒ `EvolutionEngine.crystallize`
抛 `EVAL_FROZEN`（`engine.py:180-185`）。后果：**「技能→插件」生产不可达**，观察期回归后的自动溶解
（`ADR-0011`）也随之不闭环 —— 六能力走查中「SOP 进化上半场通、下半场断」的那处**能力级真缺口**。

**D1 runner 挂 `general` 兜底子 profile，不挂主 loop。** runner 要跑一轮真模型调用；挂**主 loop** 会
成递归：`_maintain → _cold_path → scorer → runner → 主 loop.arun → _maintain …`（今日仅靠 900s
节拍闸挡住，脆）。挂**子 loop**（`runtime.py:968-972` 的 `general` 兜底子 profile）⇒ 子 loop 无
`cold_path` / `trace_observer`（`:887-906`）⇒ **无递归路径**；`transcript=None` ⇒ 样本间上下文
**零漂移**；绕开 router 关键词路由的非确定性。**代价如实记**：测的是**子 Agent 形状**（见 D6）。

**D2 门控极性 = OPT_IN（缺省关）。** 沿用第二条极性名单（`0112` 立）：`OPT_IN_MODULES +=
("evolution_benchmark_runner",)`，访问器 `config.is_enabled(...)`（fail-closed：只有显式 `true` 才开）。
理由 = **「注册基准 ≠ 同意执行」**：基准是数据、可被人随便写入，但**跑基准会烧模型 token** —— 故
执行面必须**单独**显式开启。**旗关（缺省）⇒ `runners=None` ⇒ 今日 `freeze` 判定逐字不变**（即便
基准 + 基线都已落盘：`test_gate_off_still_freezes_despite_registered_benchmark` 是**强锚**、非空转）。
旗开 ⇒ `runners = {"module_health": _bench_runner, "tool_use": _bench_runner}`（worker 只产这两个
`task_type`，`worker.py:109/:128`）传进 `BenchmarkScorer(benchmarks, runners=runners)`。

**D3 闭包晚绑定引用 `general_agent`。** `BenchmarkScorer` 在 `runtime.py:837` 构造，而 `general_agent`
在 ~`:1026` 才赋值 ⇒ 嵌套 `_bench_runner(sample)` **闭包**引用它（评测只发生在 build 之后，届时已绑定）。
**已用 pyright 探针证实**（v1.1.409 对「引用后赋值的外层局部」报 0 错误）⇒ **无需**改 `BenchmarkScorer`
API、无需可变 holder。为可测性把逻辑**拆两截**：模块级 `_run_bench_sample(loop, sample)`（可用假 loop
单测）+ 嵌套 `_bench_runner(sample)`（补上晚绑定的 `general_agent.loop`）。

**D4 `_run_coro` —— 在所有调用方的线程里跑协程。** 评测发生在**冷路径线程**（`to_thread` 内、**无**
运行中事件循环）或 `evolve run` CLI 主线（无循环）⇒ 模块级 `_run_coro`：`get_running_loop()` 抛
`RuntimeError` ⇒ 直接 `asyncio.run`；若**恰好**在循环里 ⇒ 单线程池兜（`ThreadPoolExecutor(1)`）。
**全调用方已核**：今日无「循环内」调用方，兜底只为契约完整。`_run_bench_sample` 的返值**精确匹配
scorer 语义**（`evaluator.py:239-244`）：`result.failed` ⇒ `None`（完成度 0）、否则 `reply`；异常
**冒泡**（`evaluator.py:215` 认可的 freeze 语义，**不吞成 0 分**）。**会话隔离**：`session_id="bench"`
防样本产物以 `loop.<trace>` 落进全局记忆层（`_BENCH_SESSION`）。

**D5 CLI 注册面**。`evolve benchmark {register|set-baseline|list}`（`_add_evolve_parser` 加层）——
**数据面免 runtime**：`BenchmarkRegistry(path=_state_path("evolution-benchmarks.json"))`，先例
`_notes_store`。`register <benchmark_id> --plugin-id <id>`（**必填**：plugin 绑定才激活评测
`evaluator.py:230`，也是基线键）`--task-type module_health --samples <path.json>`（`[{"input",
"expected"}]`）；`set-baseline <plugin> <score>`；`list`。CLI help 注明 `expected` 须与期望回复
**逐字相等**（缺省只评 completion）。

**D6 已知局限。** ① **注册后运行中的 runtime 重启才见** —— registry 在构造期加载；② **样本串行跑在
维护线程**（分钟级阻塞风险，由门控 + 小样本数兜）；③ **测的是子 profile 形状 ≠ 主 loop**（D1 的
代价）；④ **`_crystallize_plugin` 仍只登记不产真插件**（`plugin_ids.py:11-18` 有意裁决，**不在本批**）；
⑤ 无 runner 的 `task_type` 仍 `freeze`（fail-closed 保持）。

- **落点**：`src/core/runtime.py`（`OPT_IN_MODULES` 加名、`_BENCH_SESSION` / `_run_coro` /
  `_run_bench_sample` 模块级 helper、`_bench_runner` 闭包 + `runners` 门控、`evaluator=` 接
  `runners=runners`）、`src/core/entry.py`（`_add_evolve_parser` 的 `benchmark` 子解析器、
  `_evolve` dispatch、`_benchmark_registry` / `_benchmark_register` / `_benchmark_set_baseline` /
  `_benchmark_list`）、`tests/test_benchmark_runner.py`（新 ×10）、`tests/test_feature_gating.py`
  （`test_opt_in_whitelist_members` 重命名 + 断言扩为两成员）、`doc/04-testing/test-cases.md` §125、
  `coding-plan/known-risk.md`、`doc/02-modules/evolution.md`。
- **规格**：`evolution` **MODIFIED**「评测基建」（全量替换；补 3 bullets —— **执行面语义** /
  **执行面门控（缺省关）** / **注册操作面**，＋ **ADD** Scenario ×3「执行面门控关闭时不注入（逐字回到现状）」/
  「执行面门控开启时经真实执行产出留出分」/「CLI 注册面只写数据面且被评测可见」；既有 5 bullets 与
  6 Scenarios **逐字保留**）—— canonical: evolution **16 → 16** req / **84 → 87** scen
  （「评测基建」条内 6 → 9）。
- **反证**：**两组**，(A) 门控强制为开（`if True`）⇒ `2 failed, 8 passed`（`test_gate_off_*` 两例红）；
  (B) 摘 `runners=runners` 实参 ⇒ `2 failed, 8 passed`（`test_gate_on_*` 两例红）；两次复原 ⇒
  逐字节相同（`diff -q` vs 备份，"RESTORED-OK"）并复测 10 passed。
- **局限**：见 D6。来源另见 `doc/openspec/changes/archive/2026-10-11-0212-evolution-crystallize-path/design.md`。

## ADR-0203：文档→摘要 —— 入口侧桥 / 显式旗即 opt-in / 双守护免费获得（change 0213 / 台账 E150）

**背景 —— 「原始文档 → 可持久化摘要」没有入口。** 六能力走查确认：`rag ingest`（`entry.py`）
只做「分块 → embedding → 落索引」，`rag ask` 是**一次性**问答、**不落盘**；系统里的「总结」**全是
会话结晶**（记忆压实 / 提升）。目录层（`0210` 的 InfoMap）答「有哪些文档」、检索层（rag）答
「哪段相关」，唯独**「这份文档讲了什么」**这一**结论层**缺失 —— 每次都要重新 `ask`（烧 token、
零沉淀）。本 change 补该入口（用户裁决：「③ 落点 = **notes 结论层**」）。

**D1 落点 = notes 结论层（**不**回写 rag 语料面）。** 「文档 → 摘要」两条可选落点：**rag 库**
（把摘要当又一块 chunk 存回向量库）或 **notes**（canonical 结论层）。裁决落 **notes**：
(a) rag 是**检索**面，把摘要塞回 chunk 面会**污染检索语料**（摘要与原文重复入场）；
(b) notes 是**真相 / 结论**面 —— `digest` 会按 Consult 命中注入推理上下文，正是「这份文档讲了
什么」该在的位置。

**D2 显式旗即 opt-in，无配置键。** `--summarize` 是**一次性的显式意图**（「这次摄取顺便总结」）
⇒ 无需 `features.*` / `rag.*` 配置键，也**无环境行为**（不带旗 ⇒ 逐字不变）。与「缺省关的新行为」
纪律**不冲突**：此处不是**隐藏的缺省行为**，而是**显式的每命令参数**；除 canonical 笔记外
**不落新的运行时态**。

**D3 摘要调用 = 入口侧复刻 `_llm_text` 4 行接缝。** 组合根的 `_llm_text` 是**闭包**、不可外部
取用；而入口侧 `_rag_ingest` **已有** `runtime` ⇒ 直接 `runtime.llm.completion(LLMRequest(...,
model=runtime.app.llm.model))` 复刻同一 4 行形状。**不复用** `memory/summarize.py`（那是**会话
压实**形状：多轮 `MemoryEntry` 列表 → 摘要；此处是**单文档全文 → 摘要**，形状不同）。

**D4 落点订正（实施期）—— 桥搭在 `entry`，不落 `notes` 包。** 初版拟新增
`src/core/notes/rag_summary.py::write_doc_summary`，被本仓 **ADR-0148 三面边界**的结构门禁
`tests/test_architecture.py::test_memory_notes_api_excludes_document_corpus_dimension`
（change `0189` / E126 立）**判红**：该门禁以 AST 抽出 `notes` **公开面**的函数名 / 形参名，
凡命中 `_CORPUS_DIMENSION_TOKENS`（含 `doc` / `document` / `rag` / `corpus` …）即失败；实测
offender 为 `write_doc_summary -> ['doc']`、`doc_id -> ['doc']`。门禁 docstring 明写：「先改
ADR、再开规格变更，而非顺手补签名」—— 本 change 的规格/裁决**不含**「放开 notes 包承载文档
语料」，故**不退门禁**、改**落点**：桥移到 **`entry`**（`test_rag_not_imported_by_reference_chain`
明列的**两个 rag 例外**之一），直接调用**公开** `NoteStore.update`（**唯一**写路径，与
`promote.py` 同纪律）⇒ **`notes` 包零改动**。行为与初版**逐字相同**。桥的两端（rag 全文 / notes
写盘）都在入口侧 —— 恰是 D1「落笔记在入口侧、守三面边界」的**贯彻**，非权宜。

**D5 「双守护」是免费获得、非新机制。** `notes.rag` **不进**任何覆写路径的目标：
(a) `observe_turn`（`store.py`）只覆写 `source == notes.turn` 的笔记 ⇒ 撞上 `notes.rag` 走
`<topic>-<n>` 回落；
(b) `promote_session_summary`（`promote.py`）撞上非 `notes.promote` 的既有笔记且未显式
`as_note_id` ⇒ 返回 `None`、**不写盘**。
⇒ 本 change **零改动**这两条路径，摘要笔记天然受保护（`test_rag_summary.py` 以锚点证明）。

**D6 进 digest 命中节选（刻意不入 `_ARCHIVE_SOURCES`）。** `_ARCHIVE_SOURCES = frozenset(
{PROMOTE_SOURCE})`（`store.py:54`）的存在理由是「提升产物正文源自 memory 会话摘要、已由 loop
『历史摘要』块每轮注入，避免**重复**」。文档摘要**无**此重复来源 ⇒ **不入**归档来源 ⇒ 进 digest
的「命中的笔记」**节选**块。这是**目的**（结论层要在上下文可见），**非**疏漏 —— 本 change 不动
`_ARCHIVE_SOURCES`。

**D7 失败不阻断摄取。** 摘要（模型调用 / 落盘）失败**不**回退已完成的摄取、**不**使命令非零退出
（摄取已是既成事实）；失败告警落 **stderr**、**只报 `doc_id`**（**绝不回显正文 / 摘要正文 /
任何密钥**）。

**D8 已知局限。** ① **摘要质量无门** —— 一次性 LLM 调用，无 JEV 质量门（如需另立 change）；
② **大文档全文直喂** —— 无分段 / 递归摘要（超出模型窗口由调用方自理）；③ **重摄取才刷新** ——
摘要与文档内容绑定于摄取时刻，源文档改了但未重摄取 ⇒ 摘要是旧的（与 rag 索引同生命周期）；
④ **CLI 专属入口** —— 无 Agent 工具 / 无 API 触发摘要（摄取本就是 CLI 一次性动作）。

- **落点**：`src/core/entry.py`（`_SUMMARY_NOTE_SOURCE` / `_doc_summary_note` / `_DOC_SUMMARY_PROMPT` /
  `_write_doc_summary_note`、`_add_rag_parser` 的 `ingest --summarize`、`_rag_ingest` 分支、`_RAG_USAGE`）、
  `tests/test_rag_summary.py`（新 ×8）、`doc/04-testing/test-cases.md` §126、`coding-plan/known-risk.md`、
  `doc/02-modules/notes.md` / `rag.md`、`doc/03-interfaces/notes-interface.md`。
  **`src/core/notes/` 与 `src/core/rag/` 零改动**。
- **规格**：`rag` **MODIFIED**「文档摄取与分块」（全量替换；narrative 补「可选摘要」/「摘要失败不
  阻断」两 bullets，＋ **ADD** Scenario「摄取可选摘要落结论笔记」；既有 3 Scenarios **逐字保留**）＋
  `notes` **ADDED**「文档摘要笔记（notes.rag）」＋ Scenario ×4 —— canonical: rag **7 → 7** req /
  **15 → 16** scen（「文档摄取与分块」条内 3 → 4）；notes **5 → 6** req / **42 → 46** scen。
- **反证**：**两组**，(A) `_rag_ingest` 摘要分支强制关（`if False and args.summarize`）⇒
  `1 failed, 7 passed`（`test_cli_ingest_summarize_writes_note` 红）；(B) `_ARCHIVE_SOURCES` 加上
  `"notes.rag"` ⇒ `1 failed, 7 passed`（`test_doc_summary_note_enters_digest_excerpt` 红）；
  两次复原 ⇒ **md5 逐字节相同**（`ENTRY-RESTORED-OK` / `STORE-RESTORED-OK`）并复测 8 passed。
- **局限**：见 D8。来源另见 `doc/openspec/changes/archive/2026-10-11-0213-rag-doc-summary-notes/design.md`。

## ADR-0204：主循环会话轮级检查点 —— 两写点 / `turn.` 命名空间隔离 / 轮面独立呈现（change 0214 / 台账 E151）

**背景 —— 长时单轮被杀，整轮无痕。** `create_checkpoint` 的生产调用链**只有一条**：编排器波次回调
（`runtime.py` 的 `_checkpoint` / `_done` 注入点）。⇒ 一个**非编排的长时单轮**（例如一次长 ReAct）
若中途被杀，**整轮无任何落盘痕迹**，且重启后**无呈现**（`_recover_incomplete` 只认编排任务）。
本 change 补主 loop 的轮级写点（用户裁决：「⑤b 主 loop 轮级检查点」进本批）。

**D1 写点 = 轮首 / 轮末两处，**不**逐步刷新。** `CheckpointStore._persist` 每次 `put` **全量重写**
文件 ⇒ 逐步写会是 **O(n²)**。故只两写：轮首（`_load_pinned_notes` 后，用户消息已进 transcript、序一致）
置 `done=False`；轮末（`remember` 后，**成功与 `limit_reason` 两路都达**）置 `done=True`。`astream`
**无 `try/finally`** ⇒ 轮内异常 / 进程被杀**天然**留 `done=False`（镜像波次语义，不谎报完结）。增长
由**保留策略**兜 —— 故 `0208`（RetentionManager 接线）**先行**。

**D2 命名空间隔离 `turn.<trace_id>`。** 轮面检查点用 `task_id = f"turn.{trace_id}"` ＋
`state["kind"] = "turn"`（前缀 + kind **双判据**）。理由：**防 `task --resume` 误接** —— 轮面
**不可**重放（无撤销账本，见 D7），若落入任务续跑面 ⇒ CLI 会提示一个**无法真正恢复**的续跑。

**D3 闭包注入（loop **不** import durability）。** 新可选参
`turn_checkpoint: Callable[[str, str, str, bool], None] | None`（`(trace_id, session_id, goal, done)`），
沿 `turn_observer` / `cold_path` / `act_wrapper` **闭包注入先例**（loop → durability 是**红线**外的
依赖，必须由组合根注入）。闭包自防御用 `except DurabilityError`（**非**裸 `Exception`）：满足规格
「写入失败（持久化不可用）SHALL 只记录告警」，同时**不吞**编程错误（保持 loud）；含
`retention_policy` 落盘后 `apply`（与 `0208` 同点）。

**D4 分流 = 两套扫描语义，**不**做共享重构。** `_recover_incomplete` 的既有语义「**任一**快照
`done=True` ⇒ 该任务已完成」**必须逐字不变** ⇒ 不改写为共享 helper，而是第一环**收集** `turn_tasks`
集合、第二环**守卫**跳过（`if cp.task_id in turn_tasks or _is_turn_task(cp.task_id): continue`）；
`_turn_incomplete(checkpoints)` 用**独立**的「**最新可读快照**」语义（坏快照跳过、按 ts 排序）——
两者语义**不同**，硬合并会破坏任务面。**反证订正**：摘**第一环** `kind` 分类 ⇒ 18 passed（**被第二环
前缀守卫遮蔽 ⇒ 冗余，非缺证据**）；有效反证是摘**第二环**守卫 ⇒ 4 红（见「反证」）。

**D5 呈现独立一段、**不给**续跑提示。** 两面的**恢复语义不同**：任务面「**显式** `task --resume`
续跑」、轮面「**续聊即恢复**」（**不**自动重执行，守 P2 / `durability/spec.md`）。故
`_surface_incomplete` 扩**独立一段**：报中断轮**数量与会话标识**，**不含** `task --resume` —— 且
**绝不回显轮目标正文**（留痕只报 id / 会话键）。

**D6 缺省关 ⇒ 逐字不变。** `loop.turn_checkpoint`（bool **缺省 False**）⇒ 构造参 `None` ⇒
`_mark_turn` 首行 `if self._turn_checkpoint is None: return` ⇒ **零写入**（零回归锚）。

**D7 已知局限。** ① **不含撤销账本** —— `EffectTracker` 的 `undo` 是**闭包、不可序列化**
（`entry.py` 已认此项）⇒ 轮面检查点**不做假耐久**（落不了可重放的 undo）；② **快照仅供呈现不供
重放** —— `goal` / `done` 只服务启动呈现与分流，**恢复语义仍是显式**（不给自动重执行）；③ **仅主
loop 接线** —— 子 / 神兽 / 宠物 loop **不接**（沿既有隔离注记）；④ **轮内不刷新** —— 长轮中途被杀
只留轮首快照（`goal` 是最新、`rounds` 不更新；这是 D1 的 O(n²) 取舍的直接代价）。

- **落点**：`src/core/loop/default.py`（`TurnCheckpoint` 别名 / `turn_checkpoint` 参 / `_mark_turn` /
  轮首·轮末两写点）、`src/core/runtime.py`（`_TURN_TASK_PREFIX` / `_TURN_KIND` / `_turn_checkpoint`
  闭包（晚绑定）/ `_is_turn_task` / `_turn_incomplete` / `_recover_incomplete` 分流守卫 /
  `Runtime.recover_turns()`）、`src/core/entry.py`（`_surface_incomplete` 轮面段）、
  `src/core/configuration/manager.py`（`loop.turn_checkpoint` spec ＋ `turn_checkpoint()` 访问器 ＋
  `_loop_errors` 校验）、`tests/test_turn_checkpoint.py`（新 ×18）、`tests/test_entry.py` /
  `tests/test_phase13.py`（既有桩补 `recover_turns` 协作方）。
- **规格**：`durability` **ADDED**「会话轮级检查点」＋ Scenario ×5（轮首未完结 / 轮末完结 / 中途中断
  留未完结 / 启动扫描独立呈现不提示续跑 / 缺省关零写入）；**既有 4 Requirement 逐字保留**（本 change
  **不** MODIFY）—— canonical durability **4 → 5（+1）** req / **17 → 22（+5）** scen。
- **反证**：**四组**，(A) 摘轮末 `done=True` ⇒ `3 failed, 15 passed`；(B) 摘轮首写 ⇒
  `4 failed, 14 passed`；(C) 摘第一环 `kind` 分类 ⇒ `18 passed`（被第二环前缀守卫**遮蔽 ⇒ 冗余**，
  记录为「冗余已验证」而非失败）；(C') 摘第二环**续跑面守卫** ⇒ `4 failed, 14 passed`；全部复原 ⇒
  `src/core/loop/default.py` / `src/core/runtime.py` **md5 / diff -q 逐字节相同**。
- **局限**：见 D7。来源另见 `doc/openspec/changes/archive/2026-10-11-0214-loop-turn-checkpoint/design.md`。

## ADR-0205：提示词文本 pin —— 9 条 prompt 头逐字钉死（change 0215 / 台账 E152）

**背景 —— 措辞是私有常量，零测试 pin ⇒ 漂移静默改行为。** 控制面/数据面的提词措辞是模块私有
常量（实现细节），而 `tests/` 对 9 条核心 prompt 头的引用数**为零**；唯一内容锚是
`tests/test_memory.py` 的 `build_prompt`（一条 builder 的**结构**）。后果：改一个约束句（如
「绝不输出密钥明文」「谓词必须归入闭表白名单」「工具 JSON 单独成块」）即**静默**改模型行为、
无测试拦截 —— 对**承重措辞**而言，漂移即**能力退化或安全面收窄**。

**D1 只 pin，不改 `src/`。** 零 `src/` 改动；新 `tests/test_prompt_pinning.py`（12 用例）持
**独立副本**逐字比较。副本是**有意重复**（pin 的本质）：src 措辞一改，断言以清晰 diff 转红，
逼改者**显式**确认「这是有意的行为改动」。承重措辞逐字进副本，**不只首句**。

**D2 pin 的是实现细节，**不**升进规格。** 规格约束的是「抽取/归纳**发生**及其产物形状」，不是
模型的措辞；把 prompt 字面量升进规格即**过约束**（措辞非对外契约，且会锁死换模型的自由度）。
故**规格中性**：无 spec delta，`.openspec.yaml` `skip_specs: true`（沿 `0156` / `0189` /
`0195` / `0199` 先例）。

**D3 结构与措辞分离：两类锚。** 逐字头（9）钉**措辞**；结构不变量（3）钉**渲染契约**（与既有
`build_prompt` 锚同口径）：① 六 builder 产物恒以头开头且条目行 `- ` 前缀；② 模板占位符解析后
无残留、闭合谓词白名单**集合恒等**且全量出现；③ 节选上界**钉死为字面量**（400）且超长正文不炸
prompt。**为何把「上界 = 400」也钉成字面量**：若测试从模块常量**派生**上界（`×10` 构造超长、
再用同常量断言），则常量翻倍时用例**恒绿**（自我指涉 ⇒ 空过）—— 必须用**独立字面量**作绝对锚。

- **规格（规格中性）**：无 spec delta；`openspec validate --all` 32 passed（31 canonical ＋ 1 change）
  → 归档后 31 passed。canonical 规格计数**不变**。
- **反证（四组，实测）**：① `extract._PROMPT_HEAD` 的「绝不」→「请勿」⇒ `1 failed, 11 passed`
  （仅 `test_extract_head_verbatim`）；② `planner._SYSTEM_PROMPT` 删「，不得用代码块围栏包裹」⇒
  仅 `test_planner_system_prompt_verbatim` 红；③ `_CANONICAL_PREDICATES` 去 `related_to` ⇒ 仅结构锚
  `test_item_lines_prefixed_and_placeholders_resolved` 红（集合恒等）；④ `extract._MAX_ENTRY_CHARS`
  400→4000 ⇒ 仅 `test_entry_excerpts_bounded` 红（字面量锚）。全部复原 ⇒
  `src/core/memory/extract.py` / `src/core/loop/planner.py` **diff -q 逐字节相同**，12 绿。
- **局限**：① pin 的是**当前**措辞 ⇒ 有意改措辞时须**同步**改副本（这是设计意图，非缺陷）；
  ② 只覆盖 9 条**核心**头（**`0219`/ADR-0209 已补 ⑧ 情景归纳 / ⑪ 源码修补 / ⑫ 候选审查 至 12 条**），
  仍未覆盖 `LoopContext`/诊断等次级文本与 `_system_prompt` 的块序；
  ③ 结构锚只钉「有界 / 前缀 / 占位符」，不钉**块拼接顺序**（归 `0201` 的 `plan_blocks` 锚域）。
- 来源另见 `doc/openspec/changes/archive/2026-10-11-0215-prompt-text-pinning/design.md`。

## ADR-0206：关键事实抽取门控 —— 缺省 True 的 kill-switch（change 0216 / 台账 E153）

**背景 —— 同族三键两门控，唯一缺口。** `runtime.py` 的组合根接线里，关键事实抽取（`0155`）**无条件**
`extract_with(_llm_text)`；而实体关系抽取（`0203`，`:581`）与重要度闸门（`0181`，`:584`）都门控。
关键事实抽取**每次压实跑一次模型**（烧 token）却**无法关闭** ⇒ 缺一个 kill-switch。

**D1 缺省 `True`（kill-switch 而非 opt-in）。** 本键是**既在用能力**的开关，**非**新能力。翻缺省为
False 等于**静默删除一个在用能力**（非缺陷修复），方向与「缺省关 ⇒ 逐字不变」纪律的**初衷相反**
（该纪律保护的是**既有行为不被新特性改变**，而非让既有能力默认消失）。缺省 True ⇒ 恒走原分支
`extract_with(_llm_text)` ⇒ 与今日**逐字等价**。

**D2 非法取值回落 `True`（与同段其余键**相反**）。** `memory` 段**非结构化**（不在
`_STRUCTURED_SECTIONS`）⇒ 非法取值不阻断启动、只归一。同段 `relation_extract`/`importance_gate`
归一方向是**关闭**（安全侧 = 「不做那件事」）；本键的保守侧是**保持能力** ⇒ 归一为**开启**
（`not in _FEATURE_FALSE`）—— 一次拼写错误**不得**静默停用在用能力。

**D3 规格 MODIFIED 末句 ＋ ADD Scenario ×2。** 末句扩为「未注入抽取器**或配置关闭**⇒ SHALL NOT 抽取」，
并声明新键 SHALL 为**组合根接线闸**、缺省 true、只决定**是否接线**、SHALL NOT 改本条其余
脱敏/有界/落库判据；**既有 15 Scenario 逐字保留**（MODIFIED = 整段替换，须原样带上）。

- **规格**：`memory` **MODIFIED**「结构化实体抽取（关键事实）」＋ **ADD Scenario ×2**（配置关闭不接线 /
  缺省开保留既有抽取）⇒ canonical memory **16 → 16** req / **117 → 119（+2）** scen；
  `openspec validate --all` 32 → 归档后 **31 passed**。
- **反证（两组，实测）**：(A) `runtime.py:578` 恢复无条件接线 ⇒ `1 failed, 7 passed`（仅
  `test_build_runtime_omits_extractor_when_disabled`）；(B) ConfigSpec `default` ＋ 访问器缺省 ＋
  `raw.get` 缺省一并翻 False ⇒ `3 failed, 5 passed`（`test_spec_declares_key_fact_extract` /
  `test_default_is_on` / `test_build_runtime_default_wires_extractor`）。两次复原 ⇒
  `src/core/configuration/manager.py` / `src/core/runtime.py` **`diff -q` 逐字节相同**，复测 8 绿。
  测试 **+8**（2433 → **2441**）。
- **局限**：① 只补关键事实抽取，同族「会话摘要 / SOP 提炼 / 编排 / RAG」的同类门控**未补**
  —— 用户裁决只补本键；② `memory` 非结构化 ⇒ 非法取值**不阻断启动**（与同段其余键同口径），
  拼错只静默回落 True；③ 门控是**组合根接线闸**，`MemoryStore` 类级缺省仍是 UNWIRED（逐字不变），
  二者语义不同不可混同。
- 来源另见 `doc/openspec/changes/archive/2026-10-11-0216-key-fact-extract-gate/design.md`。

## ADR-0207：既往失败教训注入块 —— 零效应读面 ＋ 第 11 个提示词块（change 0217 / 台账 E154）

**背景 —— 失败经验「有沉淀、无专属消费面」。** 四类记忆里成功经验有「可用技能」＋「相关笔记」块、
语义事实有「相关事实」块、压缩产物有「历史摘要」块；唯**失败经验**（`loop.failure.<trace_id>`，
`0179` / ADR-0170 已沉淀、`tags=["loop","failure"]`）**无专属注入面** —— `Diagnoser`（`0188` / ADR-0179）
只把它喂**诊断报告**、**不回灌推理提示**，通用事实面按**相关性**排序取数（失败条目无优先权、长会话
极易被挤出）。缺口 = 缺一个**按会话、按时间倒序**的失败教训专块。

**D1 零效应读面，不走 `read()`。** `read()` 命中即经 `_reinforce` **+1 `reuse_count` 并落盘一个
可撤销效应**（`0187` / ADR-0178）。本读面**每轮推理都跑** ⇒ 走 `read()` 会 i) 污染复用信号（教训被
反复「使用」而虚高）、ii) 在 `EffectTracker` 堆积与用户意图无关的效应、iii) 破坏「读取面零效应」的
既有口径（`session_chain` / `summary_for` 同律）。故新开只读快照面，走 `_all_entries()`。

**D2 层无关（`failure` 标签驱动，不按层过滤）。** 失败条目**仍走遗忘**（`_PRESERVE_TAGS` 只豁免
**压实**、不豁免遗忘 ⇒ 会迁 L4）。若读面要求 L2，则「教训已积累但被遗忘归档」的会话**恰在最需要时
看不见自己的教训** ⇒ 故只按 `tags` 过滤。

**D3 新增**第 11 个**提示词块 —— 与 ADR-0191 不冲突。** `ADR-0191`（`0201`）拒的是**重切预算份额**
（`plan_blocks` 的五份），**不是**「块的数量」。本块与之**三项不冲突**：不改任何既有份额、不改任何
既有块字节（缺省关 ⇒ 逐字不变）、长度**有界**（至多 `_FAILURE_LESSON_LIMIT` = 5 条）。**不折入
「相关事实」**：事实块按「相关性 + 预算」截断 ⇒ 教训会被**静默丢弃**；独立块**无条件在场**（只判空），
这正是失败教训要的语义。

**D4 「专块承载 ⇒ 退出事实面」，条件化是最高风险点。** 块启用后失败条目会**双份注入** ⇒
`exclude_fact_tags` 追加 `failure`（同 `0185` 压缩产物 / `0186` 原始步序口径）。**关键在条件化**：
块**未启用**（缺省）⇒ `exclude_fact_tags` **逐字**为既有 `frozenset({"steps"})` ⇒ 事实面行为
**逐字不变**（有专门逐字锚测试守住）。

**D5 钩子 arity 由**取数维度**决定（三钩子各不相同）。** `notes_consult: (任务文本) → str`（按任务命中）、
`pinned_notes_consult: () → str`（零参、与任务无关）、`failure_lessons_consult: (会话标识) → str`
（**按会话**）。不强行统一 —— arity 是**契约**的组成部分。

**D6 不做因果 / 归因（以 `0202` / ADR-0192 为先例）。** 仓内无确定性因果事实，模型生成的归因散文
不可测正确性、非可逆、且是**新脱敏面**。本块只做**时序倒序的原文回顾**，SHALL NOT 推断「这次失败
是因为上次」。教训正文**已在写入时**逐行脱敏（`0179` over-redact）⇒ 读面**不引入**新脱敏判据。

- **规格**：`memory` **MODIFIED**「情景链」（首段「两件事」→「三件事」、(e) **条件化**、新 **(h)** 只读
  失败教训读面；**既有 7 Scenario 逐字保留** ＋ ADD Scenario ×3）；`loop` **MODIFIED**「执行循环」
  （块句 ＋ **既有 41 Scenario 逐字保留** ＋ ADD Scenario ×2）。
- **反证（三组，实测）**：(A) 摘 `planner.py` 教训块 ⇒ `2 failed, 17 passed`（`test_planner_injects_
  block_when_nonempty` / `test_block_precedes_skills_and_follows_notes`）；(B) 读面改回
  `self.read("", 1 << 30)`（走强化路径）⇒ `1 failed, 18 passed`（`test_read_is_zero_effect`）；
  (C) 摘 `runtime.py` 的 `"failure"` 条件项 ⇒ `1 failed, 18 passed`（`test_exclude_and_consult_
  wired_when_on`）。三次复原 ⇒ 七个改动文件 `md5sum` **逐个相同**；复测 **19 绿**。
  测试 **+19**（2441 → **2460**）。
- **局限**：① 教训与**语义事实面**可能内容相关（如从失败抽出的 keyfact 仍在事实面）—— 二者是
  **不同条目**、不构成重复；② 只**按会话**取，跨会话同类失败不互见（会话维度是刻意隔离口径）；
  ③ **非因果** —— 只提供时序倒序原文，模型是否借鉴由模型自决（不可测）；④ 新增第 11 个块使
  `_system_prompt` 复杂度越 `C901` 阈一档，按仓内既有先例（`astream`）以 `# noqa: C901` 局部放行
  （未改 `pyproject` lint 配置）。
- 来源另见 `doc/openspec/changes/archive/2026-10-11-0217-failure-lessons-block/design.md`。

## ADR-0208：情景归纳 —— 独立接缝 ＋ `kind="semantic"` 的结构性隔离（change 0218 / 台账 E155）

**背景 —— 情景类「无专属沉淀 prompt」。** 四类记忆里程序类有 `sop.build_sop_prompt`、语义类有
`extract.build_extract_prompt` / `build_relation_prompt`，唯**情景类**复用通用**会话摘要** prompt
（`summarize._PROMPT_HEAD`）。复用不是「少一段提示词」，而是**两路语义被同一文本压平**：材料口径
不同（摘要器把「现有摘要」当**滚动合并**输入；归纳器只看本批事件）、副作用不同（摘要器**迁移**来源
条目至 L4；归纳器**不迁移**）、产物去向不同（摘要进事实面并被滚动覆盖；归纳是**面向会话的结论快照**）。
任何一处措辞调整会**同时**改两路行为 ⇒ 无法为情景类单独演进（违 P3 可归因）。

**D1 独立接缝，不改造摘要 prompt（用户裁决）。** 新增 `MemoryStore.episodic_extractor`
（`EpisodicExtractor = Callable[[list[MemoryEntry]], str]`，缺省 UNWIRED）＋ 新模块
`core.memory.episodic`（镜像 `extract.py` 三段式：契约别名 / `_PROMPT_HEAD` / `build_episodic_prompt` /
`consolidate_with`）。与 `key_fact_extractor` / `relation_extractor` 并列 —— 合并任一路即改其 prompt
**字节**（`0203` / ADR-0193 已立此口径）。memory 依旧**不 import** 任何 LLM / rag 抽象（ADR-0045）。

**D2 契约返回文本、不引入新 dataclass（YAGNI）。** 归纳产物是给人读 / 供注入的结论快照，**没有**
机读下游消费者（关键事实必须结构化才有 `keyfact.<slug>` 实体幂等键，关系必须有谓词白名单）。故契约
取 `Callable[[list[MemoryEntry]], str]`（同 `Summarizer`），不造为不存在的消费者服务的抽象
（CLAUDE.md §2）。

**D3 `kind="semantic"` 是**承重**设计，不是标签选择。** `_episodic_groups`（打分 / 摘要 / 关键事实 /
关系 / 本次归纳的**唯一材料源**）的入选判据是 `kind == "episodic" and layer == "L2"`。归纳产物若取
`kind="episodic"`，下一轮压实即把它当材料**回喂**摘要器 ⇒「摘要 → 归纳 → 摘要」**自激环**，且每轮
放大一次。取 `kind="semantic"` ⇒ **结构性**排除（而非靠标签 / 来源串的约定）。`tags` 里的 `episodic`
只是**人读标签**、不承担任何机制（`_PRESERVE_TAGS` / `_GATE_EXEMPT_SOURCES` 均不看它）。

**D4 每会话一条、覆盖式（不是累积）。** 归纳语义 =「这段会话到目前做成了什么」⇒ 旧结论被新结论
**取代**。`id=episodic.<key>` 走 `write()` 既有幂等覆写 ⇒ 条目不增长（P5 token 有界）。不建多版本：
**没有**消费者需要历史版本，且压实产物已可由 `trace_id` 回滚。

**D5 `session_id=""`（全局层）＋ `tags` 溯源。** 归纳结论跨会话可见（同关键事实 / 关系）——「上次这个
任务怎么收的」不该被会话边界锁住；产生它的会话经 `session:<key>` 溯源。`id` 带 `key` ⇒ 会话间**不互相
覆盖**。

**D6 脱敏在 store 侧无条件（承 `extract` 红线）。** 注入的归纳器**不构成信任边界** —— 其输出可能夹带
模型**复述**的材料中明文密钥。故落库前 `redact_secrets` ＋ 截断至 `MAX_EPISODIC_CHARS`，方向恒
over-redact；失败 / 空文本 ⇒ 整条不写、留痕**只报会话键**（绝不回显正文）。

- **规格**：`memory` **ADDED**「情景归纳（episodic consolidation）」＋ 6 Scenario（**既有 16
  Requirement 逐字保留**）。
- **反证（三组，实测）**：(A) 摘 `_summarize_sessions` 的归纳调用 ⇒ `6 failed, 13 passed`；
  (B) 归纳条目的 `kind` 改 `"episodic"`（材料判据命中 ⇒ 回喂）⇒ `2 failed, 17 passed`
  （承重锚 `test_not_fed_back_to_summarizer` ＋ 形状锚 `test_consolidated_entry_shape`）；
  (C) 摘 `redact_secrets` ⇒ `1 failed, 18 passed`（`test_content_redacted_and_bounded`）。
  三次复原 ⇒ 五个 `src/` 改动文件 `md5sum` **逐个相同**；复测 **19 绿**。测试 **+19**（2460 → **2479**）。
- **两条教训（反证自身会失真，必须验证反证真的红了）**：① **承重锚不能走会话收窄路径** —— 归纳条目
  `session_id=""`，而 `_episodic_groups` 在 `session_id` 非空时按会话过滤 ⇒ 用 `compact(session_id="s1")`
  测「不回喂」**无论如何都通过**（挡它的是会话过滤、不是 `kind`）；必须走**全量** `compact()`，且断言要
  **逐组全查**（`seen[-1]` 只覆盖最后一组，归纳产物若入选会自成 `""` 组而漏检）。② **批量替换必须锚定唯一
  子串** —— `kind="semantic",` 在 `store.py` 出现 **3 次**（`_commit_summary` / `summarize_slice` /
  `_consolidate_episodic`），按「首次出现」替换会**静默改错对象**（反证 B 首跑 19 绿即此故）；
  须带前导行（`source="episodic",`）锚定并断言命中数 `== 1`。
- **局限**：① 新 `source="episodic"` **未**登记 `_GATE_EXEMPT_SOURCES` / `_FORGETTABLE_SEMANTIC_SOURCES`
  ⇒ 与 `importance_gate` 同开时该条目会**过闸**（可能被拒收 / 降层），且**恒豁免遗忘**（长期驻留）——
  登记为后续候选（本轮保最小爆炸半径）；② 归纳文本**自由不可机读**，检索只能靠词法 / 语义相似；
  ③ 每会话仅一条 ⇒ 超长会话的早期结论被后续**覆盖稀释**（结论快照语义的固有代价）。
- 来源另见 `doc/openspec/changes/archive/2026-10-11-0218-episodic-consolidator/design.md`。

## ADR-0209：内置提词总表 ＋ pin 补 3 条（change 0219 / 台账 E156）

**背景 —— 3 条未 pin ＋ 全仓无一处集中可查。** `0215`/ADR-0205 把 9 条核心 prompt 头逐字 pin，
并在其「局限②」登记：⑧ 情景归纳器（`0218` 才新增）、⑪ 源码修补者、⑫ 候选审查者**未纳入**；
⑬ 宠物人格为动态拼接、未纳。同时 prompt 散在 **12 个模块**的私有常量，「写了什么／在哪／有无
pin」须逐个 `grep`，**无集中查阅面**。

**D1 落点 = 文档镜像，非代码收拢（用户裁决）。** 交付 `doc/03-interfaces/prompts.md`，**零 `src/`**。
把 prompt 收拢进 `src/core/prompts.py` 会触及 ADR-0205「prompt 是**实现细节**、不外露」的既立口径，
且削弱 pin 的「独立副本」价值（副本与真源同文件则改一处即同改）。故只做**镜像**。

**D2 文档定位 = 现状快照，**显式**标注非真源。** 否则读者会误以为改文档即改行为。§0/§6/§7 三处
明写「真源 = 各模块常量 ＋ `tests/test_prompt_pinning.py` 的逐字副本」「改一条 prompt = **三处**
同改（模块常量 → pin 副本 → 本表），只改一处时 pin 测试转红」。**pin 拦不住文档漂移，只拦代码**
（已登记为局限①）。

**D3 pin 补 3 条（覆盖 9 → 12），不补 ⑬。** 新增 3 条逐字副本（⑧ 情景归纳 / ⑪ 源码修补 /
⑫ 候选审查）＋ 1 条情景归纳 builder 的结构不变量。⑬ 宠物人格是 `render_prompt()` **动态拼接**
（`name`/`species`/`traits`/`persona_text` 随档案变），逐字 pin 无稳定锚 —— 如将来需要，宜按
「固定槽位结构」而非逐字全文 pin。

**D4 分类口径显式声明为「解释性」。** 「控制面／数据面」在仓内另有**既定**含义（pet 控制面
`PetControl`、分布式与进化「控制面·执行面分离」）；本表 §0 明写「控制面／数据面／进化面／人格面」
是**本表**的归类，避免与正式术语冲突。

**D5 安全承重措辞单独标注。** ⑤ 关键事实抽取 / ⑥ 关系抽取的「**绝不**输出明文 ＋ `<redacted>`
＋ `coeffect:`」是「密钥不落记忆」的**第一道**（模型侧）防线（第二道 = store 侧无条件
`redact_secrets`）。表格与 §7 改动指引均单列警示：改此措辞须重评安全面，必要时补反证。

- **规格（规格中性）**：无 spec delta；`skip_specs: true`。`openspec validate --all` 32 passed
  （31 canonical ＋ 1 change）→ 归档后 31 passed。canonical 规格计数**不变**。
- **反证（三组，实测）**：① `episodic._PROMPT_HEAD` 改一字符 ⇒ `test_episodic_head_verbatim`
  转红；② `author._PROMPT_HEAD`「完整」删 ⇒ `test_author_head_verbatim` 红；③
  `validator._REVIEW_PROMPT_HEAD` 去「PASS/REJECT」判词句 ⇒ `test_review_head_verbatim` 红。
  三次复原 ⇒ 三文件 `md5sum` **逐个相同**，16 绿。
- **局限**：① **文档会漂移** —— 改 prompt 若忘同步本表，表与真源不一致（pin 只拦代码、不拦文档）；
  ② ⑬ 仍未 pin（动态拼接）；③ 只覆盖 prompt「**头**」—— 动态块正文（① 的 11 块、④ 的既有摘要
  节选等）由结构不变量与既有单测覆盖，本表只做**描述**。
- 来源另见 `doc/openspec/changes/archive/2026-10-11-0219-prompt-catalog/design.md`。

## ADR-0210：提词收紧轮低风险收口 —— strip_fence 兜底 / 镜像门禁 / ⑧ 微调（change 0220 / 台账 E157）

**背景 —— 提词收紧轮（`1f93b88`）的三项收尾。** 见 `coding-plan/Pending-Arbitration.md`：PA-04
（`strip_fence` 只剥整体围栏）、PA-05（镜像无自动校验）、PA-06（⑧ 教训段易成空话）。

**D1 PA-04 = 兜底取末块，非语法自检。** `strip_fence` 整体匹配失败时取**最后一个**围栏块（同
`planner._trailing_json_object`「只认尾部」）；**不选** `ast.parse` 自检（属验证门职责）。整串以
围栏起首仍由既有 `_FENCE` 接管 —— 兜底只覆盖「说明 + 围栏」。

**D2 PA-05 = 核对落成测试，非反向生成。** 新 `tests/test_prompt_mirror.py` 断言模块常量的每一非空行
出现在镜像；**不选**脚本反向生成（镜像含解释性旁注，生成器须重排结构）。⑤⑥ 去 `.format()` 转义
取渲染形态（仅当含 `{{` 时），① 的 `{"args": {...}}` 是字面双 `}`、不受影响。

**D3 PA-06 = 只改 ⑧，动 ⑦ 待分布证据。** ⑧ 教训段（会被「既往失败教训」块直接注入规划器）加
「须写成可复用的判据」；⑦ 牵动 `W_IMPORTANCE` 权重分布 ⇒ 保留。

- **规格（规格中性）**：无 spec delta；`skip_specs: true`。
- **反证（三组，实测）**：摘兜底 ⇒ 3 failed, 20 passed；还原 ⑧ ⇒ 2 failed, 29 passed；改 ④ 常量
  ⇒ 1 failed, 13 passed；三文件 `md5sum` 复原后逐个相同。
- **局限**：① 多围栏块取末块理论上可误取（倾向低，已显式记录语义）；② 镜像门禁不查多余行；
  ③ ⑦ 未动。
- 来源另见 `doc/openspec/changes/archive/…-0219-prompt-catalog/design.md`、`coding-plan/Pending-Arbitration.md`。

## ADR-0211：提词收紧轮登记 —— 追溯挂账 `1f93b88`（change 0221 / 台账 E158）

**背景**：提词收紧轮已提交（`1f93b88`：10 条 prompt 措辞 ＋ `parse_review` 等值 ＋ `build_sop_prompt`
轨迹分组），但未挂 change / ADR / 台账 ⇒ 追溯断点（PA-07）。本 ADR **不改任何行为**，只做登记。

**D1 三处行为变更并为一个 change。** 三者同一提交、同一动机、同一验证轮；拆开会让「一个提交挂三个
change 号」—— 追溯更乱。唯一改语义的 `parse_review` 以 **D2 独立小节**承接（不另立 change）。

**D2 `parse_review` 等值化 = 规格符合性缺陷修复（非规格变更）。** `evolution/spec.md:144-145` 已 SHALL
fail-closed（「非判定词表 ⇒ 未通过」），Scenario `:190-192` 逐字承接；旧实现 `startswith` 把「通过不了」
「PASS 但存在问题」读成**通过** ⇒ **实现偏离既有 Requirement**。收紧为首行等值是**向规格回归**，
**不**产生 spec delta（补 Scenario 是「无源之水」—— 规格已有该判据）。

**D3 `build_sop_prompt` 轨迹分组签名 = 仓内私有适配器。** `skills/spec.md` 无「按轨迹分组」条 ⇒ 无
Requirement 承载其形状；结构不变量由 test_prompt_pinning builder 锚 ＋ 新反证覆盖。

**D4 登记不改写历史。** 不 rebase / 不 amend `1f93b88`；以新提交追溯挂账（change 号 → 提交 → 文件
三段闭合，守 P3 可归因）。

- **规格（规格中性）**：无 spec delta；`skip_specs: true`。`openspec validate --all` 31 passed → 归档后
  31 passed **不变**。
- **反证**：本 change **零 `src/`/`tests/` 改动** ⇒ 无行为可反证；`git diff --stat src tests` **为空**
  即直接证据（沿 `0219` 口径）。
- **局限**：① 挂账**不改善** `1f93b88` 提交信息（其 message 未含 change 号）；② `prompts.md` 头部
  「本轮收紧」清单**不逐条**列全 10 条措辞 diff（正文镜像已逐字承载）。

## ADR-0212：夹带的动作 JSON 归一为可见失败 —— 取代 ADR-0156 子情形语义（change 0222 / 台账 E159）

**背景**：`loop` 解析器对「**已闭合**的动作 JSON + 尾随正文」（动作对象**不在**文末）旧实现整段当
答复 ⇒ **静默零执行**（动作丢失、记成功、JSON 进转录与记忆）。`0166`/ADR-0156 只堵了「正文 + **尾部**
JSON」；提词收紧（`1f93b88`）只靠模型守规矩，不构成防线（PA-01 现象①）。

**D1 新形态 5：已闭合 + 非空 `tool_id` + 其后仍有正文 ⇒ 可见失败。** `_embedded_action_payload` 逐
`{` 试 `raw_decode`，命中闭合 dict、`tool_id` 非空、`text[end:].strip()` 非空 ⇒ True；`_parse` 返失败态
终止动作（`_UNPARSED_EMBEDDED`，带 `raw_output`）。与形态 3（收在文末 ⇒ 工具动作）、形态 4（未闭合 ⇒
失败）**互斥**；次序「先 3 再 4 再 5」保尾部路径零回归。

**D2 取代 ADR-0156 子情形语义（静默丢失 ≫ 一次可见失败）。** 旧语义「正文中间夹带一律按回复」动机是
「防把解释协议时引用的 JSON 示例当执行」—— 但当模型确实**发出**完整动作协议又追加正文时，旧语义造成
**静默零执行 + 记成功 + 污染持久面**。新语义归一为**可见失败**（可观测、可恢复、不进持久面）。**ADR-0156
作为历史记录不改写**（沿 `0219`/`0221`）。

**D3 只认含非空 `tool_id` 的对象。** 夹带**无** `tool_id` 的示例/配置 JSON 仍按回复（不误伤解释）。

**D4 流式泄漏（现象②）不做。** `astream` 用首个非空 chunk 首字符判形态、判为回复后原样外发 ⇒ 漏尾随
JSON。根治须放弃边出边流（产品级取舍），单独立项（PA-01 可选项 C）。

- **规格**：`loop` **MODIFIED**「推理动作解析与失败可见」（四种→五种形态、改写中间夹带句、MODIFIED 1
  Scenario、ADDED 1 Scenario；既有其余 7 Scenario 逐字保留）⇒ canonical loop **6 → 6** req（无新增）／
  **81 → 82（+1）** scen。
- **反证（实测）**：摘 `_parse` 形态 5 分支 ⇒ `test_loop_output_protocol` **3 failed, 17 passed**；
  复原 ⇒ `md5sum` 相同、20 passed。
- **局限**：① 正文中**引用含 `tool_id` 的动作 JSON 示例**的解释型回复被判失败（取代的固有代价）；
  ② 流式泄漏未修（单独立项）；③ 多个动作对象取「任一命中即失败」，不辨「哪个是真动作」。
- 来源另见 `doc/openspec/changes/archive/…-0222-loop-embedded-action/design.md`、`coding-plan/Pending-Arbitration.md` PA-01。

## ADR-0213：技能迭代注入「失败实况」—— 从「只有计数」到「有材料」（change 0223 / 台账 E160）

**背景**：`SkillIterator.consider` 的改写 prompt（`build_iterate_prompt`）只给模型**计数**（`N 次，
失败 M 次，失败率 x%`）与**现行步骤**，不给失败现场。而 `_PROMPT_HEAD` 自己要求「新增的防护步骤要
写明它防的是**哪一类**失败」—— 没有材料即无法兑现，模型只能编造失败类别（PA-02）。

**关键事实**：失败实况**已在手** —— 同一条 `on_turn` 收尾钩子里，本轮 `steps` 已被
`sop_extractor.observe` / `note_store.observe_turn` 消费，**唯独技能迭代这条路丢掉它**。故此非
「新增数据源」，而是「补一条被漏掉的转交」。

**D1 材料注入（不改措辞）。** `build_iterate_prompt` / `consider` 各增**可选** `failure_steps`；非空
⇒ 在「执行情况」与「现行步骤」之间插一节「最近一次失败的实际执行步骤：」，逐条 `- ` 回灌。
**不改** `_PROMPT_HEAD` 一字（它是 pin + `prompts.md` 镜像的逐字锚，改一词即三处同改，与本 change
目标无关；且该措辞在**拿到材料后恰好成立**）。

**D2 落在 skills 侧、组合根只传参。** 依赖方向照 `sop.py` 先例：`runtime._loop_hooks().on_turn` 在
失败轮把 `steps` 传给 `consider`（与 `sop_extractor.observe(task, steps, ok=ok)` 同型），prompt 由
`skills` 侧自建 —— `loop` 不 import `skills`，`skills` 也不被反向注入 prompt 文本。

**D3 有界 + 行内脱敏，顺序即安全。** `steps`（`loop._action_steps` 产出）**未脱敏**，本 change 让这批
文本**首次**进改写 prompt ⇒ 在迭代器内两道处理：① `redact_secrets` 先行（`core.memory` 的 pure
helper；`skills/router.py`、`crystallizer.py` 已 import `core.memory` ⇒ **无新依赖方向、无环**），与
`loop` 的 `failure_digest` **同口径**（抹密钥子串、留工具名/路径）；② 再截断（末尾至多
`_MAX_FAILURE_STEPS=5` 步 × 单步 `_MAX_FAILURE_STEP_CHARS=200` 字）。**先脱敏后截断** ⇒ 密钥不跨
截断边界泄漏。上限意义 = **token 有界**，非信息完整。**取末尾**（失败通常落在序列尾部）。

**D4 缺省空 ⇒ 逐字不变。** `failure_steps=()` 是可选入参，既有调用点（含测试替身）不传 ⇒ 不产块 ⇒
与今日产物逐字节相同（全批纪律「缺省关 ⇒ 逐字不变」）。

- **规格**：**规格中性**（`skip_specs: true`）。`skills` spec「技能迭代闭环」只规定触发 / 灰度 / 定夺 /
  可逆四件事，**未约束 prompt 的输入材料**（属实现细节，沿 `0215`/`0219` 判据）⇒ 0 Requirement /
  0 Scenario 变动。
- **反证（实测）**：(A) 摘组合根 `failure_steps=steps` ⇒ `test_phase13` **1 failed**；(B) 摘
  `build_iterate_prompt` 的块 ⇒ `test_skills` **4 failed, 1 passed**；复原 ⇒ `md5sum` **逐字节相同**、
  目标 6 例全绿。
- **局限**：① 只注入**触发那一轮**的失败步骤（不做跨轮失败轨迹聚合 —— 轨迹级诊断属 evolution 维度2）；
  ② **SOP 路径同源暴露未修（登记）**：`sop.py::observe` 把同一批**未脱敏** `steps` 喂给
  `build_sop_prompt`，系**既有**行为、非本 change 引入，统一脱敏不在 PA-02 范围；③ 成功轮不触发
  `consider` ⇒ 不会误把成功步骤当失败材料（既有语义，本 change 未改）。
- 来源另见 `doc/openspec/changes/…-0223-skill-iteration-failure-steps/design.md`、`coding-plan/Pending-Arbitration.md` PA-02。

## ADR-0214：文档摘要落盘前无条件脱敏 —— 写入侧为信任边界（change 0224 / 台账 E161）

**背景**：`rag ingest --summarize` 把文档**全文**交一次模型调用产摘要，产物经
`entry._doc_summary_note` 落成 canonical **结论笔记**（**长期可检索**）。此前两条路径**皆无**脱敏：
① 写入侧 —— `notes` 包**无** `redact_secrets`（`memory` 侧有），模型输出原样进正文；② 提示侧 ——
`_DOC_SUMMARY_PROMPT` 只要求「总结核心结论」，未禁写密钥。⇒ 文档含密钥形态子串时，明文可能经摘要
进入长期可检索的笔记，冲突红线「密钥只引用不读取、绝不进日志/记忆」（PA-03）。

**D1 写入侧脱敏为**承重**防线（信任边界在写入者）。** 沿 `0155`（结构化抽取）的判据：「靠 prompt
让模型别写密钥」**不可审计** —— 模型是否照办无从保证、亦无从测试。故确定性一侧必须兜底：
`_doc_summary_note` 写盘前**无条件** `redact_secrets`。

**D2 复用 `core.memory.redact_secrets`（不新写）。** 口径须与仓内其余持久面**一致**
（`loop.failure_digest`、`memory` 抽取/情境链均走它）—— 新写一份只会引入形态漂移。依赖方向无新意：
`entry.py` **已** `from core.memory import …`（只多引一符号）；且它非 LLM/rag 抽象 ⇒ 不触 ADR-0048。

**D3 脱敏**只作用于正文**（不碰 `note_id` / `title`）。** 二者由 `doc_id` 确定性派生、是**幂等覆盖
的键**；若脱敏波及键，同 `doc_id` 两次落盘会得到不同 `note_id` ⇒ 破坏幂等。故边界严格限于模型产出
的 `summary`。

**D4 提示措辞（C）为纵深、非防线。** `_DOC_SUMMARY_PROMPT` 补「不要输出任何密钥…」；它无法被测试
证明「模型照办」⇒ 不计入防线（与 `0155` 同纪律）。镜像 `prompts.md` ⑭ 同步（`test_prompt_mirror`
逐行核对会拦漂移）。

**D5 `rag` 规格**不动。** 其「把文档**全文**交给一次模型调用」为既有承诺 —— 本 change **不改**送
模型的材料（送进去仍是全文），只脱敏**产物**。

- **规格**：`notes` **MODIFIED**「文档摘要笔记（notes.rag）」—— Requirement 正文增一段「落盘前
  无条件脱敏」，ADDED 1 Scenario「摘要正文落盘前无条件脱敏」；**既有 4 Scenario 逐字保留**。
  canonical `notes`：Requirement 数不变，Scenario **＋1**。
- **反证（实测）**：摘 `redact_secrets` ⇒ `tests/test_rag_summary.py` **2 failed**（`-k redact`）；
  复原 ⇒ `md5sum` **逐字节相同**、11 passed。另：改 `_DOC_SUMMARY_PROMPT` 未同步镜像 ⇒
  `test_prompt_mirror` **1 failed**（逐行核对生效，非空跑）。
- **局限**：① `redact_secrets` 是**形态匹配 + over-redact**，只覆盖 `_SECRET_PATTERNS` 所列形态与
  「长随机串兜底」，**不保证**捕获无固定形态的业务密文 —— 与仓内其余脱敏面**同一天花板**；② 提示
  措辞不可测「模型照办」（故不计防线）；③ `sop.py::observe` 未脱敏喂 `build_sop_prompt` 的**既有**
  暴露面不在本 change（见 ADR-0213 局限②）。
- 来源另见 `doc/openspec/changes/…-0224-doc-summary-redact/design.md`、`coding-plan/Pending-Arbitration.md` PA-03。

## ADR-0215：镜像失真收口 —— 落点行号 ＋ 旁注锚（change 0225 / 台账 E162）

**背景**：`doc/03-interfaces/prompts.md` 自称「全仓内置 prompt 的**现状快照（镜像）**」，change `0220`
为它加了门禁 `tests/test_prompt_mirror.py`，但该门禁只断言「模块常量的**每一非空行**出现在镜像」——
**结构性看不见**两面：① **§1 落点列的 `文件:行`**（常量上方增删行即漂移：实测 ①③⑥⑩ 四条失准，
其中 ①⑩ 由 `0222`/`0223` 引入、③⑥ 由提词收紧轮的 ②⑤ 加长引入）；② **解释性旁注**（不是模块常量
⇒ 全不受保护：实测 §4⑪ 把 `0220` 已闭的 `strip_fence` 兜底写成「仍不会被剥」、§2① 未记 `0222`
形态 5、§3⑩ 未记 `0223` 失败实况）。

**D1 落点行号改为可判定断言（非生成物）。** 在常量上方增行是常规操作 ⇒ 该列必然漂移，靠「记得复核」
在人肉流程里不可靠。故 `test_prompt_mirror` 增 14 行参数化：所列行**必须**含所列符号；符号去掉尾随
`()`（⑬ 落点写 `render_prompt()`，目标行是 `def render_prompt(self) -> str:`）。**不采**「从源码反查
生成该列」—— 那要先解决镜像里大段手写旁注的另存与结构重排（同 PA-05 选项 C）。

**D2 旁注取「已知加固点锚」而非全量校验。** 旁注是散文、无真源可核 ⇒ 无通用正确性判据。可做的是
**反向守卫**：每个已知加固点登记一个标识串（`_FENCE_ANY` / 形态 5 / `failure_steps`），断言镜像
**记到了**它 —— 拦的是「加固已闭、旁注仍写成开」这类**方向性失真**（本次即此型）。

**D3 纪律面同步。** `prompts.md` §7 补两步：复核落点行号（第 4 步）；触及行为时同步旁注 ＋ 明写
「旁注不受文本门禁保护」（第 5 步）。

**D4 PA 簿补第三条出口。** 原约定只有「转实现 / 判不做」；实测 6 个子项被**缓议 / 单独立项**却因无此
出口而只落在 ADR 局限里 ⇒ 新增「缓议 / 单独立项 ⇒ 记入 §4 ＋ `known-risk.md` §3，**不重开**闭项」
＋ §4 索引（6 项）。重开闭项是错的：裁决确实做了「本轮不做」的决定。

- **规格**：**中性**（`skip_specs: true`）—— 改动全在**测试面**与**文档面**，零 `src/`。
- **反证（实测两组）**：① §1 落点行号改回 `:50` ⇒ `test_mirror_landing_line_points_at_symbol[①]`
  **`1 failed, 31 passed`**；② 镜像摘 `_FENCE_ANY` ⇒
  `test_mirror_notes_carry_known_hardening_anchors[0220 …]` **`1 failed, 31 passed`**；复原
  `prompts.md` `md5sum` **逐字节相同**（`24a38ee64628e8a46e10ebd413b61c92`）、复测 **32 passed**。
  绿后全量 `.venv/bin/pytest -q` ⇒ **2534 passed**（基线 **2516**，**+18**；`test_prompt_mirror`
  14 → **32**）。
- **局限**：① **锚是手工清单** —— 新增加固点忘加锚则不红（旁注无真源）；② **行号核对只覆盖 §1 表** ——
  小节标题里的同一 `文件:行` 靠纪律（§7 第 4 步）而非自动；③ **不核镜像多余/过期行**（沿 ADR-0210
  局限②）；④ **未采反向生成**（同 D1）。
- 来源另见 `doc/openspec/changes/…-0225-mirror-staleness-closeout/design.md`、`coding-plan/Pending-Arbitration.md` §4。

## ADR-0216：长任务 × 记忆待裁决登记 —— 登记簿拆两轮 ＋ 结构守卫（change 0226 / 台账 E163）

**背景**：2026-10-11 用户问「**现在的 core-agent 四层记忆光谱 ＋ 四类记忆模式，满足长任务要求
了吗**」。两路只读取证（要求侧规范 / 实现侧现状）＋ 对**真实运行配置与 state** 的经验核验，结论为：
**四类记忆的能力位已落地接线**（成文映射见 `phase-38.md:7-8`），但长任务三条硬要求里**两条无对应
机制**（阶段/里程碑锚定、万条不漂移），另有一批**无立项**（M4 基准），并暴露两处**登记/索引级**缺口 ——
其中 `coding-plan/README.md` 的阶段索引漂移**已实际造成返工**：按 README 找会漏掉 `phase-36`
（长任务硬化）与 `phase-38`（**专门**对照同一份四维记忆蓝图做查漏补缺）两册最相关的账，
从而把**已裁决过的事项**重报为缺口。

**D1 登记进同一册、升级为多轮登记簿。** `Pending-Arbitration.md` 的定位即「登记需要人裁决才能推进
的开放项」，其失效方式恰是**入口分裂**：另开一份会让「还有什么在等裁决」有两个答案。故按
`§0.x`/`§1.x` 分轮，第一轮条目**逐字保留**（只改其所在分节标题）—— 沿 `known-risk.md` 对历史行号
快照的同一纪律。

**D2 加结构守卫、不判内容。** 待裁决项的**内容**无真源可核（`file:line` 随代码漂移、选项代价是人的
判断）；可判定的是**结构完整性** —— 总表↔逐条一致、闭项带 change 号、开放项有「落地面」，四条恰好
覆盖「悄悄丢项」的全部失效方式。纪律逐条镜像 `test_prompt_mirror.py`（只钉可判定部分 ＋ docstring
明写不判什么）。

**D3 §5 附录带可重跑命令、且只统计结构。** 本轮最有价值的结论是**实测**（三项配置源皆无功能键 ⇒
「缺省关」确实关着；213 条记忆里 `relation.*`/`episodic.*`/`loop.failure.*`/`compaction.mid.*` 皆为 0）。
快照会过期 ⇒ 附命令让人**自己复核**。`state`/`.env` 复核**只打印 id 前缀与变量名**，**绝不回显正文或
取值**（守 `CORE-NFR-SEC1`）。

**D4 外部材料不作判据。** 三份蓝图类材料均**未跟踪**且前两份自标「百度AI生成，仅供参考」；台账
**明写不取**其「里程碑永久删除／单库无隔离／三方依赖」（`known-risk.md:269`）；ADR-0190 已裁
**采其结构弃其数值**（`known-risk.md:106`）⇒ 「拿蓝图当尺子」得出的「不满足」是**裁决过的**，非遗漏。

- **规格**：**中性**（`skip_specs: true`）—— 改动全在**文档面**与**测试面**，**零 `src/`**
  （`git diff --stat src/` 为空）。**登记 ≠ 裁决**：PA-08~PA-12 **全部保持开放**。
- **反证（实测两组）**：(A) `### PA-09` 改名 ⇒「总表↔逐条」用例与 `test_open_items_are_actionable[PA-09]`
  转红；(B) 抹掉 PA-01 行的 change 号 ⇒「闭项必带 change 号」用例转红；复原 ⇒ `md5sum` **逐字节相同**。
  绿后全量 `.venv/bin/pytest -q` ⇒ **2542 passed**（基线 **2534**，**+8**）。
- **局限**：① **登记不等于裁决**（五项全开，一项未实现）；② **守卫不判内容**（证据漂移不会红）；
  ③ **§5 实测是当日快照**（属证据非证明）；④ **未采「合并进 `known-risk.md`」**（语义不同，合并会让
  「在等什么」不可见）；⑤ **PA-11 的根治在 PA-11 自身**（本 change 只登记缺口，未补 README）。
- 来源另见 `doc/openspec/changes/…-0226-longtask-memory-arbitration/design.md`、
  `coding-plan/Pending-Arbitration.md` PA-08~PA-12。

## ADR-0217：解析失败回喂重试 ＋ 首字符花括号失败成因细化（change 0227 / 台账 E164）

**背景**：2026-10-11 实跑事故（session `88a6a6b9…`，子 Agent trace `1c7cfb24…`）：delegate 子 Agent
在长上下文压力下（maintenance HTTP 400 → turn observer 超时 >60s）最终一轮产出**退化重复**形态 ——
`{` 开头、完整动作 JSON 缺最外层收尾 `}`、后随省略号垃圾与第二份重复对象、5029 字符截断。`_parse`
的**首字符分支**整体 `json.loads` 失败 ⇒ 通用文案终止回复、**无重试** ⇒ 子 Agent 5.6 分钟工作全部丢弃
（第一份对象里内容已完整写出）。取证确认**非 0220~0224 回归**（`{`-first 分支 0166 起未动）。

**D1 重试放规划器层、非 FaultChain。** `FaultChain`（ADR-0199）是**行动阶段**白名单容错（可逆工具的
`{TIMEOUT, EXECUTION_FAILED}`）；解析失败发生在**推理阶段**，重试单位是「一次推理请求」。放 planner 内
⇒ `DefaultLoop` 零改动、上下文一致（宪法/事实/技能照常装配）、且与流式外发边界判定（首个 `{` 缓冲）
天然同层 ——「本轮是否已外发内容增量」的信号只有这里有。

**D2 三门同时开才重试。** ① 配置门 `loop.parse_retry`（缺省关）；② 失败门 `_retryable`（空 tool_id ＋
reply 以 `LLM_PLAN_PARSE_FAILED` 前缀 —— 覆盖 `_parse` 全部失败分支；LLMError 分支前缀不同、天然
不命中）；③ 外发门 `not reply_stream`（已逐段外发的自然语言流不重试 —— 不得让已见内容「回滚」；
**PA-01 现象②流式泄漏不在本 change**）。**恰一次**（平铺两次调用，无递归失控面）；重试成功 ⇒ 按正常
结果处理，仍失败 ⇒ 第二次结果即终态。原生 tool_calls 终态同样过失败门（缺 name/参数不可解析可受益）。

**D3 nudge 不携带原始退化产出（安全承重）。** 内容 = **成因**（`{cause}` 填既有区分措辞）＋ 输出格式
协议重申（复用 `_SYSTEM_PROMPT` 措辞、不新造语义）＋「长内容分多次写」用法提示；**绝不**回喂首次的
退化文本 —— 守 0170「raw_output 只进 trace/呈现」：回喂退化文本会把重复模式重新注入，是**自激而非
纠错**。用户角色消息（同轮纠错遵从度惯例）；追加到当次 request（`_build_request` 每次新造 ⇒ 不污染 ctx）。

**D4 `{` 开头成因细化复用既有判据、零新启发式。** `_first_brace_reply` 三段：`_unclosed_action_payload`
⇒ 按 `finish_reason` 分截断/未闭合（与形态 4 同文）；`_embedded_action_payload` ⇒ 形态 5 措辞（事故的
重复对象即「对象在前、正文在后」）；皆不命中 ⇒ 通用文案**逐字**。0170/0222 的措辞承诺本就按成因区分，
只是判据在 `{`-first 分支**不可达** —— 修的是可达性，故**无条件**生效（非门控行为）；只改提示信息量，
失败语义/raw_output/终止语义不变（既有断言只断前缀 ⇒ 天然兼容）。

**D5 缺省关 ⇒ 零回归承诺。** 本能力是**韧性增强**而非缺陷修复（退化本身是模型/负载问题，上游减压是
change 乙 `~` 展开与 maintenance 400 专项）⇒ 沿仓纪律缺省关：关闭时请求形状、模型调用次数、失败语义
与既有实现**逐字一致**。部署侧在 `~/.core/config.yaml` 翻 `loop.parse_retry: true` 启用。配置镜像
`failure_lessons` 全套（三面 ConfigSpec / 访问器归一化 / `_loop_errors` bool 校验阻断启动）。

**D6 提词三处同改。** 新常量 `_RETRY_NUDGE` ⇒ pin 副本（`test_prompt_pinning`）＋ 镜像（prompts.md ⑮，
含注入条件与安全承重旁注）＋ 镜像门禁（`test_prompt_mirror` 落点表扩 ①~⑮）。常量置于 `_SYSTEM_PROMPT`
**之后** ⇒ ① 的落点行号（`planner.py:53`）不漂移。

- **规格**：`loop` MODIFIED「推理动作解析与失败可见」—— 成因措辞条款扩到 `{` 开头类 ＋ 新增回喂重试
  段（三门 / 恰一次 / nudge 约束 / 缺省关逐字不变）＋ ADDED 7 Scenario；既有 8 Scenario 逐字保留
  （82→89 scen，6→6 req）。
- **反证（实测三组）**：(A) 摘 `_retryable` 的前缀条件 ⇒ 缺省关/LLMError 用例红；(B) 摘 `_first_brace_reply`
  接线（还原通用文案）⇒ 成因区分三用例红；(C) 缺省翻 True ⇒ 缺省关用例红。复原 ⇒ `md5sum` 逐字节同。
- **局限**：① 重试**不治疗退化本身**，只把「一次退化 ⇒ 整轮报废」变为「多一次干净产出机会」；②
  `show_thinking=True` 时第一次已外发的思考增量会出现两段（呈现层折叠，登记）；③ 空响应/缺字段类轻失败
  也会被重试（成本一次、机会一次，有益无害）；④ 非流式路径无外发概念 ⇒ 恒可重试。
- 来源另见 `doc/openspec/changes/…-0227-parse-failure-retry/design.md`；上游减压见 change 乙（`~` 展开）
  与 maintenance HTTP 400 专项（长任务 G 线）。

## ADR-0218：文件工具 `~` 展开（change 0228 / 台账 E165）

**背景**：模型/用户以 `~/.core/…` 这类**家目录路径**调用 `tools.file_read` / `file_write` /
`file_patch` 时，`Path(path)` **不做** `~` 展开 ⇒ 路径被解释为**当前工作目录下字面名为 `~` 的目录**
下的文件。父目录 `./~` 不存在 ⇒ 读/写均以 `FileNotFoundError` 失败（实测 `Path('~/x').write_text(…)`
抛 `No such file or directory: '~/x'`）。**意图（家目录）与行为（字面 `~` 目录）静默背离**，错误信息
（`'~/x'` 不存在）对模型毫无线索 ⇒ 易触发重试 / 退化（与 ADR-0217 的上游压力同源）。

**D1 属缺陷修复、非新能力 ⇒ 无条件生效（不设门）。** 字面 `~` 目录不是任何合理用法；模型写 `~/…`
**无条件**指家目录。与 ADR-0210（`strip_fence` 兜底）同类：修的是「意图与行为背离」，不引入**可选**
行为 ⇒ **不设配置键**。区别于 ADR-0206 的 kill-switch（那个门保的是**既有**在用能力；本处的既有行为
是**缺陷**，翻默认不适用）。

**D2 落点 = 工具入口、动作前展开一次；撤销点与写入点一致。** `Path(path).expanduser()`（与
`core_profile.loader` 同口径）在 `handler` 入口做一次，**展开后**的路径用于实际 I/O **并存入撤销
快照**。理由：撤销闭包 `_restore(snap)` 按 `snap["path"]` 恢复 —— 若快照存**未展开**原串，撤销会恢复
到家目录**之外**的字面 `~` 路径（与写入点不一致 ⇒ 撤销失效 / 误建）。故「展开一次、全程一致」；
`_restore` 自身**不改**（快照已存展开路径 ⇒ 天然正确）。

**D3 只覆盖 `~` 展开，不引入其它路径语义。** 不做 `resolve()`（会解软链、改相对路径语义）；不做
`abspath`；不做环境变量展开（`$HOME`）；不改沙箱 / 权限的相对路径基准。最小语义：`~`（及 `~user`，
由 `expanduser` 一并处理）→ 家目录。

**D4 返回体仍回**输入**路径（contract 不变）。** `file_read` / `file_write` / `file_patch` 的返回
`{"path": …}` 保持**模型给的原文**（`~/x`）—— 形状与值域语义不变，仅**落盘位置**改变；避免为「回显
解析后路径」引入契约变更（若将来确需，另立 change）。

**规格**：`tool-use` spec **不约束**文件工具路径语义（该 spec 覆盖：工具定义与注册 / 参数校验 /
coeffect 契约 / 撤销回滚 / 超时上限 / 异步 / 插件安装 / 内置原子工具（**代码执行·网页读取**）/
质量门禁 —— **无文件工具专属 Requirement**）⇒ **规格中性**（`skip_specs: true`；零 spec delta、
canonical 计数不变）。行为在 `doc/03-interfaces/tool-use-interface.md` §3 落注。

**反证（实测）**：摘 `_expand` 的 `expanduser`（还原 `Path(path)`）⇒ 家目录三用例 ＋ 撤销两用例红；
复原 ⇒ `md5sum` 同。

**局限**：① **只展开 `~`** —— `$VAR` 与相对路径语义不动（最小语义的刻意边界）；② **`code_run`
的 `cwd` 未纳入** —— 非 `file_*` 工具，同源缺口（同样不展开 `~`），登记为**后续候选**；③ **沙箱 /
权限的相对路径基准仍是进程 cwd** —— 展开后的绝对家目录路径走既有判定，无新暴露面；对宠物 loop
而言 `~/…` 展开后落在 `SafetyBounds`（cwd 白名单）**之外** ⇒ 从「写进字面 `./~`」变为「**被正确
拦截**」（安全方向的改善，非回退）。

## ADR-0219：形态 5 判据收窄 —— 退化残渣不构成「追加了正文」（change 0229 / 台账 E166）

**背景（生产事故）**：2026-10-12 08:25（session `88a6a6b9…` / trace `6925d31f…`）子 Agent 交出一个
**完整、可执行**的 `tools.file_write` 动作（1806 字符 proposal 正文），**仅在末尾多出一个孤零零的
`}`**。`json.loads` 报 `Extra data` ⇒ 0222 的**形态 5** 命中断言「动作 JSON 之后仍跟有正文」⇒
整轮报废、**零执行**；0227 刚接进 `{` 开头分支的同一判据使提示措辞「之后仍跟有正文」**在事实层面
是假的**（后面没有正文）。`loop.parse_retry` 缺省关 ⇒ 无任何补救，用户只看到一句不准确的提示。

**根因**：`_embedded_action_payload` 的余部判据是「其后有**任何非空白字符**」—— 它把**一个多余
`}`** 与**一整段解释性正文**当成同一件事。0222 的裁决（「JSON + 真正文 ⇒ 可见失败，不做启发式
猜测」）本身正确，但**判据过粗** ⇒ 对**退化残渣**产生假阳性。

**决策**：

- **D1 判据 = 「余部是否含词元」**。新纯函数 `_has_word(text)`（`any(ch.isalnum() …)` —— 字母 /
  数字 / **CJK** 皆真）。同一谓词**两处朝向相反**，即「**正文与退化残渣的二分**」：
  `_embedded_action_payload`（形态 5）余部**含**词元 ⇒ 命中；`_trailing_json_object`（形态 3 尾部
  对象）余部**不含**词元 ⇒ 接受。
- **D2 `{` 开头分支先试「首个对象 + 残渣」**。新 `_leading_object`（`raw_decode(text, 0)`）成功
  **且**余部无词元 ⇒ 直接 `_from_dict`（形态 2 容残渣）。对**任意**首个对象成立（不止含
  `tool_id` 者）—— 否则会造出「同一谓词、两种朝向、**三种**结论」的新不对称。余部含词元 ⇒ 落到
  既有 `json.loads` → `_first_brace_reply`（0227 的成因措辞**逐字不变**）。
- **D3 `_trailing_json_object` 必须「同一谓词同时改」并去掉「须以 `}` 收尾」门槛**。① **同步收窄**：
  若只改 `_embedded` 而不动它，「正文 + 动作 JSON + 残渣」链路变成：`_trailing` 因余部非空返回
  `None` → `_unclosed` 不命中（对象闭合）→ `_embedded` 因收窄**也不命中** → 落回
  `return Action(args={"reply": text})` ⇒ **整段当答复、动作丢失、记为成功** —— 正是 0222 /
  ADR-0212 修掉的**静默零执行**。② **去门槛**：该函数的 `tail.endswith("}")` 前置门槛把「余部」硬性
  限定为「以 `}` 收尾」，而残渣可为**纯标点**（`…}。` / `…};`）⇒ 这类输出仍会落到同一个静默零执行；
  去掉后余部**只**按 `_has_word` 二分，「尾部对象 + 残渣」的容差与形态 2 **完全同源**。两处合起来
  才是「残渣二分」的完整落地。
- **D4 无条件生效、不设门**。修的是「意图（交出动作）与行为（丢弃动作）」的背离 ⇒ 同 0206 / 0210
  / 0228 判例（**缺陷修复**）。不设配置键；亦**不**顺手打开 `loop.parse_retry`（0227 的独立门，
  缺省关语义本轮不动）。
- **D5 残渣用「无词元」而非闭合白名单：代价不对称**。用「无词元」⇒ 纯符号的「真解释」（如 `→`
  / `……`）也会被当残渣而**执行**；用闭合白名单 ⇒ 更严，但会漏掉未枚举的残渣形态 ⇒ **继续误杀
  完整动作**。本缺陷代价（整轮报废、`failed=True`、分钟级工作全部丢弃）远高于「偶发执行一个
  此前也会被当动作的对象」；且 0222 真正要防的**解释性正文**必然**含词元**，被 D1 完整保留。
- **D6 不重开 0222 / 0227 裁决**。0222 的「JSON + 真正文 ⇒ 可见失败、不做启发式」**不被推翻**，
  本 change 只补它**误伤**的退化残渣（判据过粗的假阳性）。0227 的成因措辞条款**逐字不动** ——
  收窄后能走到那句措辞的必是**含词元**的余部 ⇒ 措辞**首次与事实相符**。

**规格**：`loop` **MODIFIED**「推理动作解析与失败可见」（形态 2 加「允许其后跟随退化残渣」子句 ＋
形态 3 的「允许以 Markdown 围栏收尾」扩为「允许其后跟随退化残渣（与形态 2 同一定义，含围栏收尾）」
＋ 形态 5 加「『正文』限定为含词元的余部、仅残渣 SHALL NOT 命中」子句 ＋ **ADDED 2 Scenario**：
残渣不阻止执行 / 残渣容错不适用于含词元内容）。既有 16 Scenario **逐字保留**。计数 **6 → 6** req、
**89 → 91** scen。

**反证（实测）**：① 把 `_has_word` 恒返 `True`（= 还原旧判据）⇒ 残渣用例转红、含词元用例仍绿
⇒ 断言**只**被收窄锚定；② **分两段还原 `_trailing_json_object`**：① 保留「须以 `}` 收尾」门槛、
只把余部判据还原为「非空白」⇒「正文 + 动作 + `}` 残渣」用例红；② 连同门槛一起还原 ⇒
「正文 + 动作 + **纯标点**残渣」用例**再**红一条 ⇒ D3 的两半各自被实测锚定；③ 复原 ⇒
`md5sum` 逐字节相同。

**局限**：① 判据是「无 alnum 词元」而**非**闭合白名单 ⇒ 纯符号的「真解释」会被当残渣（D5 的
刻意取舍）；② 只作用于**首个 / 尾部**对象的**余部**判定，不改 0222 对「动作 JSON 在**真正文
中间**」的拒绝（`正文 + 动作 JSON + 正文` 仍失败）；③ 动作得以执行**不等于**该轮成功 —— 本次事故
的目标路径父目录不存在，执行会得到 `EXECUTION_FAILED`（**可见的工具错误**、ReAct 下一轮可自愈），
与本缺陷（整轮报废、零执行）不是一回事；④ `loop.parse_retry` 缺省仍**关**（不在本 change 范围）。

## ADR-0220：TUI 回合收尾异常安全化 —— 忙态复位是不变式（change 0231 / 台账 E167）

**背景（用户实跑）**：2026-10-12 用户报告 core-agent TUI 一轮后**永久停在「思考中…」、输入被吞**。
只读取证（PID 727119 / `traces.jsonl` / CPU / socket）显示：该轮轮末 **maintenance 记忆调用**打到
`glm-5.3` **超时**（`maintenance_failed LLM_TIMEOUT: 调用超时（>60.0s）`），经 provider 缺省
`timeout=60.0, max_retries=3` ⇒ **4 次串行 60s 尝试（≈232s，08:49:17→08:53:09）**；期间
`_turn_busy=True` ⇒ `on_input_submitted` 一律拒绝（「处理中，请稍候（Ctrl+B 打断）」）⇒ **表现为卡死**。
进程实际健康（CPU 0、无 socket、epoll 空闲），事后自愈、**无需 kill**。

**根因**：表象是「长等待」，但**真缺陷**是**收尾顺序把表现层失败倒灌为状态失败** ——
`src/core/ui/repl.py` 三个 turn runner（`_run_turn` / `_run_beast_turn` / `_run_task_turn`）的
`finally` 里，`self._flush_live()` / `self._spin_stop()` 排在 `self._turn_busy = False` **之前**；
任一步抛错即**跳过忙态复位** ⇒ **一次瞬时收尾错误 = UI 永久拒收输入**。此外 `self._spin_start(...)`
与 `run_worker(...)` 调用点亦在 `try` **之外**，其失败同样遗留忙态。

**决策**：

- **D1 忙态复位是「不变式」，呈现收尾是「尽力而为」**。新 helper `_end_turn(self, *, flush_live=False)`：
  两个呈现收尾**各自** `contextlib.suppress(Exception)`（收尾失败类无法穷举：挂载 / 取件 / 屏幕栈
  拆除期），**最后必定** `self._turn_busy = False`。`ui` spec「回复收尾（含异常 / 中断）时挂起尾段
  SHALL 被最终固化」在收尾**成功**路径仍成立，失败路径降级为**尽力而为**。
- **D2 三个 runner 统一收尾 + `_spin_start` 移入 `try`**。`_run_turn` → `_end_turn(flush_live=True)`；
  `_run_beast_turn` / `_run_task_turn` → `_end_turn()`；各自 `_spin_start(...)` 移入 `try`（其失败也
  触发收尾复位）。
- **D3 分发口补同一不变式**。`on_input_submitted` 在 `_turn_busy = True` 之后的派发段（`/task` 分支 /
  `_handle_beast_command` / `run_worker`）包 `try/except Exception: self._turn_busy = False; raise`
  —— 派发失败亦复位，但异常**仍冒泡**（崩溃可见性不变）。
- **D4 不吞轮体异常**。`_end_turn` 只容错**收尾**，轮体异常仍由 worker 冒泡 —— 崩溃语义逐字不变。
- **D5 规格中性、不设门**。`ui` spec **无**任何 Requirement 约束「收尾顺序 / 忙态复位」；忙态仅被
  **负向**引用（「忙碌中 SHALL 拒绝并提示等待」「切换 SHALL 仅在本轮执行结束之后发生」）。本 change
  只**恢复**「忙态 ⇔ 本轮在跑」这一**既有不变式** ⇒ `skip_specs: true`（判例 `0220`/`0228`：缺陷修复）。
- **D6 「长等待本身」不属本 change**。232s 等待的**时长**由 change `0232`（`llm.timeout` /
  `llm.max_retries` 可配）治理；「重试进度可见」为后续独立 change。

**规格**：**规格中性**（`skip_specs: true`）—— 零 spec delta，canonical **31 → 31** 不变。测试 **+6
新增**（`tests/test_ui_turn_cleanup.py`，2574 → **2580**）。

**反证（实测，两组独立）**：① 把 `_end_turn` 还原为**裸序列**（去掉两处 `contextlib.suppress`）⇒
**5 红**（单元 2 ＋ 三 runner 集成 3）；② 摘掉派发守卫的复位语句（保留 `raise`）⇒ **1 红**
（`test_dispatch_failure_resets_busy`）。复原 ⇒ `md5sum` 逐字节相同（`170f8fff…`）。

**局限**：① **只保证「收尾失败不倒灌为状态失败」，不治收尾失败的根因** —— 收尾真抛错时降级为
「挂起尾段可能未固化 / 状态行可能残留」，而非「UI 卡死」；② **刻意宽捕 `Exception`** —— 收尾失败类
无法穷举，而状态复位是不变式；③ **不改 `_turn_busy` 置位时机**（与忙检同上下文、无竞态窗口）；
④ **不治「长等待本身」**（由 change `0232` 治理）；⑤ **不做「重试进度可见」**（后续 change）。

## ADR-0221：LLM 调用超时 / 重试可配置（change 0232 / 台账 E168）

**背景**：2026-10-12 用户实跑 TUI 卡死的那一轮，轮末 maintenance 记忆调用打到 `glm-5.3` **超时**，
经 `StdlibLLMProvider` 缺省 `timeout=60.0, max_retries=3` ⇒ **4 次串行 60s 尝试（≈232s）**。
表象的收尾问题由 change `0231` 治理；**长等待本身**是本 change 的对象。

**根因**：provider 构造参 `timeout` / `max_retries` **早已存在**（`stdlib_provider.py`），但
① `_CONFIG_SPECS` 无对应配置键；② 组合根 `runtime.py` 构造主 provider 时只传
`api_key / base_url / model / provider` ⇒ 恒取实现类缺省，操作者**无法**收窄单次等待上限。
而 maintenance / 摘要调用走的正是**主 provider**（`_llm_text` → `llm.completion`），
故这两个键**直接**为该等待时长设上限。

**决策**：

- **D1 新增两个可调控点，单一真源仍是 ConfigSpec**。`llm.timeout`（`default=60.0`）与
  `llm.max_retries`（`default=3`），均 `exposure=ADVANCED`、`map_to` 同名 ⇒ CLI flag / env /
  yaml 三面自动生成，`_CONFIG_SPECS` 不引入第二真源。
- **D2 校验期阻断，不静默强转**。新增两个**镜像 `_llm_context_window`** 的解析器
  （结构化段 ⇒ 构建前 `raise ConfigurationError`）：`timeout` 须 `> 0` 的数值、
  `max_retries` 须 `≥ 0` 的整数（`bool` / 小数 / 负数 / 非数值一律拒）。理由与 `context_window`
  同源：取值一旦化为数值便不可追溯，留到 `validate_schema` 已看不见原值；而 `timeout ≤ 0`
  在 provider 侧语义是「立即失败」⇒ 放行等于把配置笔误静默变成「所有调用必失败」。
- **D3 缺省 = 实现类缺省 ⇒ 行为零改变**。`LLMConfig` 与 `_CONFIG_SPECS` 与解析器回落值三处
  同为 `60.0` / `3`，与 `StdlibLLMProvider.__init__` 类缺省**逐字一致** ⇒ 未配置时组合根传入值
  与原先相同。（**有别于 `0216` 的 kill-switch**：此处是**新增可调控点**，缺省取「保留行为」侧。）
- **D4 两处 `LLMConfig` 构造点同步**。`_build_config`（冷启动）与 `apply_change`（热更新补丁）
  各构造一次 `LLMConfig`，两处**都**接线 —— 只改一处会让 `config set llm.timeout` 看似生效、
  实际被静默丢弃。
- **D5 「重试进度可见」不属本 change**。provider 逐次重试回调 → loop `astream` 并发排空 →
  api → TUI 重标注，跨 4 层 + 新增接口契约 + 改 `astream` 并发 ⇒ 另立 change。
- **D6 `embed_provider` / `JEVProvider` 不接同名键**。各自独立语义（embedding 无重试语义、
  JEV 走 `DecisionRouter` 回退主 LLM），留默认；`llm.fallback_models` / `llm.backoff` /
  `constraints.retry_attempts`（容错中间件，另一轴）亦不新增。

**规格**：`configuration`「LLM 提供商配置（必选）」**MODIFIED**（可选子项扩为
`embedding_model / context_window / show_thinking / timeout / max_retries`，新增两句取值/缺省/
拒绝口径 ＋ **ADDED 2 Scenario**：经三面解析且缺省 60.0/3 / 非法取值阻断）⇒ req **10 → 10**、
scen **60 → 62**。`llm-provider`「模型调用可靠性」**MODIFIED**（＋ 缺省 60.0s / 3 次与可覆盖
一句 ＋ **ADDED 1 Scenario**）⇒ req **10 → 10**、scen **25 → 26**。既有 Scenario **逐字保留**。

**反证（实测三组独立）**：**(A)** 拆掉 `runtime.py` 的两行传参 ⇒ **1 红**
（`test_build_runtime_injects_configured_values`）⇒ 接线被锚定；**(B1)** 把两处 ConfigSpec
`default` 改为 `0.0` / `0` ⇒ **1 红**（`test_specs_declare_timeout_and_max_retries`）；
**(B2)** 把两个解析器的回落值改为 `1.0` / `9` ⇒ **2 红**
（`test_defaults_match_provider_class_defaults` / `test_build_runtime_defaults_unchanged`）
⇒ 「缺省不变」被锚定。复原 ⇒ 三文件 `md5sum` 逐字节相同。
测试 **+17**（`tests/test_llm_reliability_config.py`，2580 → **2597**）。

**连带**：`tests/test_rag_wiring.py` / `tests/test_phase13.py` 的 provider **桩**镜像组合根构造
签名（原仅 4 参）⇒ 本 change 补 `timeout` / `max_retries` 两参（+`PLR0913` noqa），属**测试替身
随签名漂移**，非行为变化。

**局限**：① **`LLMConfig` 的 dataclass 缺省在配置路径上不可观测** —— 管理器恒经解析器显式注入
（回落值 `60.0` / `3`），故「缺省不变」的真实锚点是 **ConfigSpec default ＋ 解析器回落值**；
dataclass 缺省只服务**直接构造**（测试 / 内部代码）——反证 (B0)「把 dataclass 缺省改为 `0.0`」
实测 **17 全绿**（故未采用该组）；② **不改 provider 层的重试语义** —— 指数退避 / 降级 /
fallback_models 仍按实现类既有行为，本 change 只让**次数与单次超时**可配；③ **不给
`embed_provider` / `JEVProvider` 接线**（D6）；④ **不提供「重试进度可见」**（D5）；
⑤ **`constraints.retry_attempts` 未动**（不同轴：容错中间件重试「动作」而非「模型调用」）。

## ADR-0222：TUI 点击与流式 Markdown 换段竞态崩溃兜底（change 0238 / 台账 E169）

**背景**：用户实跑（Windows）报 Textual 崩溃 —— `App.on_event → Screen._forward_event →
AttributeError: 'NoneType' object has no attribute 'region'`（`screen.py:1914`），locals 里
`content_widget` 是 `MarkdownParagraph`、`container=None`。

**根因**：**三方库 textual 的竞态**（上游 [Textualize/textual#6643](https://github.com/Textualize/textual/issues/6643)，OPEN）。
本仓 TUI 流式回复以 `_tail_widget.update(text)` 合帧热更新 Markdown；`Markdown.update()` 换段瞬间，
旧 `MarkdownParagraph` 已从 DOM 摘除（`parent=None`）但 compositor 命中测试仍返回它 ⇒
选择初始化里 `container = content_widget.parent` 得 `None` 后直接解引用 `container.region` ⇒
整应用崩溃。**升级不可修复**：上游最新 release v8.2.8 即本仓安装版（用户 traceback 行号与
本仓副本逐字吻合）。

**决策**：

- **D1 守卫落 `ReplApp.on_event` 边界**（用户三选一裁决）。`App.on_event` 是崩溃 traceback 的
  确切帧且是我们拥有的唯一层：对 `await super().on_event(event)` 包
  `contextlib.suppress(AttributeError)`，拦住整类竞态，零框架补丁。
- **D2 只收 `AttributeError`**（该竞态的确切异常类型；宽捕会吞真缺陷）。守护锚用例钉死
  「`RuntimeError` 照常冒泡」—— 与 ADR-0220「不吞 turn body 异常」同口径。
- **D3 丢弃语义 = 丢该单个事件**：竞态命中时本次 `MouseDown` 不形成选择（再点即可）；
  非竞态路径逐字透传（守护锚钉「恰转发一次」）。`_mouse_down_offset` 虽在崩溃点前已赋值，
  但后续 `MouseUp` 分支只走 `clear_selection`（无 `.parent` 解引用）⇒ 无残留态风险。
- **D4 不 monkeypatch、不关选择**：`Screen.get_widget_and_offset_at` 过滤（上游建议修法①）需
  类级补丁三方库（上游改名即静默失效）；`ALLOW_SELECT = False` 牺牲应用内文本选择。均被否决。
- **D5 缺陷修复 ⇒ 无条件生效、不设配置门**（判例 0206/0210/0228）。

**规格**：**规格中性**（`skip_specs`）。`ui` spec 无任何 Requirement 约束事件转发 / 鼠标选择；
本 change 只把「三方库竞态不得杀死整个应用」收为呈现层不变式（判例 `0228`/`0229`/`0231`）。

**反证（实测）**：摘除 `on_event` 覆写 ⇒ **1 红**（`test_click_hit_detached_widget_survives`，
在**真实 textual 代码路径**上抛出与用户崩溃**逐字相同**的 `screen.py:1914 AttributeError` ——
承重锚以「从未挂载的 `Static` + 假命中返回非空 offset」构造 #6643 的崩溃形态）；
两守护锚（恰转发一次 / `RuntimeError` 冒泡）恒绿。复原 ⇒ `md5sum` 逐字节同（`4db7529d…`）。
测试 **+3**（`tests/test_ui_event_guard.py`，2647 → **2650** passed；5 红为并行批次遗留，
干净 HEAD 上原样复现，与本 change 无关）。

**局限**：① 守卫按异常类型收口 —— 未来其他 textual 内部 bug 产生的 `AttributeError` 也会被吞
（今日该路径上任何 `AttributeError` 都是整应用崩溃，吞事件严格优于崩溃；不进任何日志面）；
② MouseMove/MouseUp 分支的同形解引用不另设守卫（同一 `on_event` 边界已覆盖）；
③ 上游修复落地后守卫自然空转（不冲突、不必拆）；④ 承重锚模拟的是**崩溃形态**
（`parent=None` + offset 非空）而非 compositor 真竞态时序（真竞态无法确定性构造）。

## ADR-0223：post-turn 后台收尾的跨 event-loop 取消传播收口 ＋ benchmark 桩适配 0236 内容门（change 0239 / 台账 E170）

**背景**：change `0238` 收口时全量 pytest 余 **5 个行为性红**（`git stash` 于干净 HEAD 原样
复现 ⇒ 并行批次回归，非 0238 所致）：组一 ×3 `CancelledError`（`test_history_persistence` /
`test_longtask_e2e` / `test_orchestration`）；组二 ×2 空壳门拒（`test_benchmark_runner`）。

**根因**：**组一（生产真缺陷）** —— 7357a11（change 0233）把轮末收尾（`_notify_turn`/
`_maintain`）改为实例属性上的后台 task（`_post_turn_task`，`create_task` 于当轮 loop）；
`astream` 消费方（scheduler / 事件流）在 `loop_finished` 后**不等**收尾 ⇒ task 残留。下一次
调用若在**新 event loop**（`run()` 同步入口 / `TaskScheduler.run` / 测试驱动每次 `asyncio.run`
新建 loop），旧 loop 关闭清理已 cancel 残留 task ⇒ 新轮 `_await_post_turn` 的 `await task`
在已取消 task 上**重放 `CancelledError`**，杀死整轮。**组二（测试桩漂移）** —— 0236 装配
`Proposer(writer=skill_content_writer_with(_llm_text))` ＋ `Validator(require_skill_content=True)`
（空壳 fail-closed），0212 时代的 benchmark 桩对**所有**请求回 `"PASS"` ⇒ 蒸馏 `json.loads`
失败 ⇒ writer 回 `None` ⇒ 空壳门在 review 前 fail-fast ⇒ `eval=None`。

**决策**：

- **D1 分野判据 = `task.cancelled()`**。`await task` 抛 `CancelledError` 有两种来源：(a) task
  自身被宿主取消（loop 关闭清理）—— **吞**，放行新一轮（后台收尾尽力而为语义，与
  ADR-0220/0222「收尾/呈现层瞬时失败不得杀死主流程」同哲学）；(b) 当前协程被取消（用户打断
  Ctrl+B、上层 gather 级联取消）—— **传播**（取消语义必须保真）。`task.cancelled()` 恰好区分：
  task 内部取消完成 ⇒ True；外部取消当前协程时 task 仍正常运行 ⇒ False。
- **D2 不动 `_schedule_post_turn` 挂出时机**。loop 身份比较式的主动清扫引入额外耦合；`await`
  处分野最小且覆盖实测形态。
- **D3 组二修桩不修门**。空壳 fail-closed 是 0236 有意规格；桩按 prompt 头「技能内容蒸馏器」
  分派合法 `SkillContent` JSON。
- **D4 缺陷修复 ⇒ 无条件生效、不设配置门**（判例 0206/0210/0228/0238）。

**规格**：**规格中性**（`skip_specs`）。loop spec 无「跨 loop 取消传播」面约束（0233 未动 loop
spec）；组二为测试桩适配 0236 既有规格语义。

**反证（实测）**：摘 D1 分野 ⇒ **3 红**；摘桩分派 ⇒ **2 红**；同时摘 ⇒ **5 红**；复原 ⇒ 两文件
`md5sum` 逐字节同 ⇒ 63 passed。承重锚 = **既有五测试本身**（红 → 绿即锚定，零新增用例）。
全量 **2655 passed，0 失败**（2650 → 2655；并行批次提交后仓库**首次全绿**）；四门禁绿。

**局限**：① 「当前协程被取消」与「旧 task 恰好同时被取消」的极窄窗口会把 (b) 误判为 (a)
（吞掉一次打断；后果限于本轮多推进一步，无数据面影响）；② 跨 loop 残留 task 本体不清扫
（引用在下次 `_await_post_turn` 的 `finally` 释放）；③ 桩按 prompt 特征子串分派，
`_PROMPT_HEAD` 措辞变更需同步桩（镜像漂移风险同 ADR-0215 类）；④ 0233 自身的 spec delta
归档欠账（validate 红）不在本 change 范围 —— 已于 2026-10-17 回溯收口（ADR-0244）。

## ADR-0224：未过门候选教训写回（change 0234 / 台账 E171）

**背景**：`evolution/spec.md`「验证门」的「未过门丢弃」场景承诺「丢弃候选，**教训写回 L2/L3**」，
但 `engine.py::run_cycle` 的 rejected 分支只 `self._pending.record(candidate, gate)` 后返回 ——
候选携带的 `issue`、门禁 `review` 与各门结果在丢弃时**全部丢失** ⇒ **规格承诺未兑现**
（spec–实现一致性缺陷，而非新能力）。

**决策**：

- **D1 L2 承载完整教训**：id `evolution.gate_rejected.<candidate_id>`；内容含目标插件、`issue`、
  `review` 与各门结果。`issue` **有界**（`_MAX_ISSUE_CHARS = 400`，与 diagnoser note 同口径
  字面量、本模块自持不 import diagnoser）；写前 `redact_secrets`。
- **D2 L3 只写短指针**：id `evolution.gate_rejected.l3.<candidate_id>`；内容形如
  `ref=<L2 id>; target=…; review=…`，**SHALL NOT** 与 L2 同文、**SHALL NOT** 再嵌入完整
  `issue`。理由：L3 偏技能 / 程序知识面，同文双写会把门禁负样本全文当「技能料」检索，
  污染检索与结晶；指针兑现「写回 L2/L3」，详情仍留在 L2。
- **D3 未注入记忆后端 ⇒ 静默跳过**：零写、不抛、不改变 `EvolutionOutcome(status="rejected")`。
- **D4 前缀与既有写面错开**：`evolution.gate_rejected*` 与人工 `reject` 的
  `evolution.rejected.<id>`、`evolution.dissolve.*` 互不覆盖；本写回**不**经
  `memory_crystallizer.crystallize`。
- **D5 规格–实现一致性修复 ⇒ 无条件生效、不设配置门**（判例 0206/0210/0228）。

**规格**：`evolution` **ADDED**「未过门教训写回」＋ 4 Scenario；canonical **16 → 17 req**、
**87 → 91 scen**；既有「未过门丢弃」场景逐字保留。

**反证（实测，回溯补记时补做）**：摘除 rejected 分支的 `_write_rejected_lesson` 调用 ⇒
**3 红**（L2 全文 / L3 指针 / 与人工 reject 并存）；两条守护锚恒绿（`memory=None` 零写、
其余分支不新增 `gate_rejected*`）。复原 ⇒ `engine.py` `md5sum` 逐字节同（`aac77481…`）。
测试锚点 **5 例**（`tests/test_evolution_rejected_lesson.py`）。

**局限**：① 只覆盖**结晶面验证门**的 rejected 分支；`no_evidence` / `manual` / `frozen` /
`rollback` / pending 不写（只有「候选被判未过门」才是可归因的负样本）；② `issue` 有界 400
字符 ⇒ 超长诊断只保留前缀；③ L3 指针的检索价值取决于上层是否会读取该前缀；④ 回溯补记 ——
提交时（`0d82507`）未留反证快照，本次补做的反证只锚定「调用点存在」这一环，**不**锚定
`redact_secrets` 的具体脱敏形态（脱敏行为由 memory 既有测试覆盖）。

## ADR-0225：UI 活动呈现对齐 ui-scheme（change 0235 / 台账 E172）

**背景**：`doc/03-interfaces/ui-scheme.md` 要求「TUI 与 Web 一套时间线语义、分端材质」。change
`0233` 已落地 TUI 的**语义**（Thinking 缺省收起、友好标题、按 `round` 归并、撤回 Task 壳），
但留下一组中间态与跨端缺口：步骤块「末尾有界行预览 ⇄ 全文」多一次点击且易误判；折叠符统一；
spinner 与活动标题抢进度；Thinking 落静无耗时；子任务标题仍带 `▸`；Web `Chat` 无统一
`timeline[]`、`TaskPanel` 暴露 `▸` / `tool_id`。代码于 2026-10-12 随 commit `b42479b` 落地；
本记录于 2026-10-17 **回溯补建**（零代码改动）。

**决策**：

- **D1 展开即全文，去掉缩略中间态**：点击标题只在**收起 ⇄ 全文**间切换；
  `_STEP_TAIL_LINES` / `_full` / `step-more` 一并删除（该中间态在 ui-scheme 中只是 MAY）。
- **D2 折叠符按种类区分，且只做指示符**：`_STEP_SYMBOLS` 将活动种类映射到折叠符
  （Thinking `✦` / Bash `$` / Read `◇` / Write `✎` / Edit `✏` / Delete `⌫` / SubAgent `⊕` /
  Planner `▤` / WebFetch `◎` / Gate `☑` / Context `⊞` / raw `⚠` / subtask `◈`），注入
  `Collapsible(collapsed_symbol=…, expanded_symbol=…)` **同一符号**，不以 `▶/▼` 示意开合；
  **不进标题文本** ⇒ 不与 0233「标题 SHALL NOT 以 `⏺`/`▸` 为主标识」冲突；未知种类退化为 `·`。
- **D3 Thinking 耗时用块内计时锚**：新块创建时记 `_started_at = time.monotonic()`，落静时
  `_thinking_title(False, ms=…)` 生成 `Thinking · 1.2s`；耗时**不经事件载荷**（`loop.reasoning`
  无 `duration_ms`），由呈现层自测；已落静（标题以 `Thinking · ` 开头）直接返回、幂等。
- **D4 spinner 让位与审批期重新拉起**：有活动步骤块后 `_spin_defer_to_blocks()`（停 spinner）
  —— 标题已表达进度，spinner 仅兜底；审批挂起时无活动块可表达进度 ⇒ `_spin_start("等待审批")`
  重新拉起，结束后 `_spin_start("思考中")`（不用 `_spin_relabel`，spinner 可能已停）。
- **D5 Web 抽零 DOM 纯函数**：`frontend/src/lib/activity.js` 只做标题 / 摘要 / 耗时 / 折叠符
  映射，与 `repl.py` 同口径；`Chat.svelte` 消费统一 `timeline[]`；`TaskPanel.svelte` 复用
  `actionTitle`。Web 测试用 Node 原生 `node --test`（仓内无 vitest）。
- **D6 规格中性**：语义 delta **唯一归 change `0233`**（已于 2026-10-17 归档，ADR-0244）；本 change 不写 spec delta ——
  对同一 Requirement 双写 delta，归档时会按 Requirement 全量替换而互相覆盖（`0225`/`0228`
  同属 `skip_specs` 先例）。

**规格**：**规格中性**（`skip_specs`，零 spec delta；canonical 31 → 31 不变）。语义面正式规格
以 `0233` 归档结果为准。

**测试与反证**：TUI 锚点 5 例（`tests/test_repl.py`）：`test_tui_step_block_expand_shows_full_text`
（展开即全文）、`test_tui_spinner_hides_when_activity_block_appears`（活动块后终态前 spinner
隐藏）、`test_tui_thinking_settle_appends_duration`（`Thinking` / `Thinking · 12ms` /
`Thinking · 1.5s`）、`test_step_symbols_differ_by_kind`、`test_tui_thinking_and_bash_use_distinct_collapse_symbols`；
Web 侧 `frontend/src/lib/activity.test.js`（`node --test`，当前 10 个 `it`；提交记录 9 passed）。
**反证（回溯补记时补做）**：把 `_thinking_title` 的耗时后缀摘掉 ⇒ **1 红**
（`test_tui_thinking_settle_appends_duration`）；其余 4 个结构锚恒绿。复原 ⇒ `repl.py`
`md5sum` 逐字节同（`4db7529d…`）。

**局限**：① UI 呈现材质属快速迭代面，`ui-scheme.md` 是**解释性**文档（非规格真源），后续
调整不必逐条走 change；② Web 侧 `node --test` 与 `npm run build` **不在**四门禁内 —— 当前
Node `v20.11.1` < Vite 8 要求（`^20.19 || >=22.12`），构建未验；③ 本记录为回溯补建，提交时
**未留**反证快照，本次只补一条 TUI 反证；④ `0233` 已于 2026-10-17 归档（ADR-0244）；⑤ 折叠符
是**纯指示符**，开合状态靠 `Collapsible` 自身语义而非箭头（与「一眼看出开合」的直觉有取舍）。

## ADR-0226：技能候选内容生成（change 0236 / 台账 E173）

**背景**：技能级候选的**内容面为空** —— `Proposer.propose` 产出的 delta 只有 `{"issue": …}`；
`_crystallize_skill` 用 `delta.get("schema", {})` 结晶，得到 `instructions=""` / `task_types=[]` /
`preconditions=[]` 的**空壳占位技能**（不可路由、不可执行）。架构级（plugin）候选有 executor
补丁生产者兜住内容，技能级**没有任何内容生成器** ⇒ skill distillation 只蒸馏出空壳。

**决策**：

- **D1 独立内容模块 `evolution/content.py`**：`SkillContent`（`task_types` / `instructions` /
  `param_schema` 必填，`preconditions` / `description` 可选）；`validate_skill_content` 接受
  **dataclass 或 delta 内 asdict 形态（Mapping）**（Proposer 写入 dict，Validator / 结晶读到
  的也是 dict，不得要求调用方手工构造 dataclass）。
- **D2 writer 工厂走 DI、fail-closed**：`skill_content_writer_with(llm) -> writer`（照
  `skills.sop_writer_with` 先例）；evolution **不 import 任何 LLM 抽象**。非法 JSON / 结构
  不符 / 调用异常 ⇒ `None`，**不抛**；`failure_notes` 有界（`_MAX_FAILURE_NOTES = 3`、
  `_MAX_NOTE_CHARS = 400`，本模块自持字面量、不 import diagnoser）。
- **D3 Proposer 可选注入**：`kind="skill"` 且 writer 返回非空 ⇒ `delta["content"] = asdict(...)`；
  writer 返回 `None` 或未注入 ⇒ delta **仍只** `{"issue": …}`（**不**出现 `content` 键，
  逐字兼容）；`plugin` 候选**不**经本接缝。
- **D4 Validator 可选内容判据**：`require_skill_content`（缺省 `False`，裸构造逐字不变）；
  装配为开且 skill 候选无有效 content ⇒ `passed=False`、review 含「空壳」、`test_results={}`、
  **fail-fast**（不跑 review / 运行时测试）；plugin 不受影响。
- **D5 结晶真技能**：有效 content ⇒ `Skill` 映射各字段，`instructions` 写前 `redact_secrets`；
  `description` **优先** content 值、空则回退 `issue`；无效 content ⇒ 既有空壳回退（回归锚点）。
- **D6 口径递增**：`GATE_CALIBER` 2 → 3（新增「技能内容有效」判据），`models.py` 版本轨迹注释
  同步追加；caliber 2 的已确认候选 ⇒ `GATE_CALIBER_STALE`，须按现口径**重新提案**（不重判历史）。
- **D7 组合根同开同关**：`skill_content_writer_with(_llm_text)` 先工厂再注入；有 writer ⇒
  `require_skill_content=True`，无 writer ⇒ `False`。生产组合根当前**恒开**（不属于可选门控，
  而是能力装配）；装配期不调 LLM。

**规格**：`evolution` **ADDED**「技能候选内容生成」＋ MODIFIED「验证门」（内容判据 + 1 Scenario）；
canonical **17 → 18 req**、**91 → 95 scen**；既有 Scenario 逐字保留。

**反证（实测，回溯补记时补做）**：把 `validate_skill_content` 恒返 `True` ⇒ **3 红**
（四态校验 / writer 失败分支 / 装配门拒空壳）；其余 16 例恒绿（writer 解析、Proposer 写键、
结晶映射、caliber 等不依赖该谓词）。复原 ⇒ `content.py` `md5sum` 逐字节同（`2d59c94d…`）。
测试锚点 **17 个函数 / 19 个用例**（`tests/test_evolution_skill_content.py`）；另同步修改
`test_evolution_gate_data.py` / `test_evolution_gate_judgment.py` 的 provider **桩** —— 蒸馏
prompt（头「技能内容蒸馏器」）回合法 JSON、审查 prompt 回判定词（测试替身随新接缝漂移，
非行为变化）。

**局限**：① 内容质量取决于注入模型与 prompt；writer 失败即 `None`，装配门开时候选被拒
（fail-closed 降低产出率）；② `GATE_CALIBER` 2 → 3 使历史 caliber-2 候选 `STALE` 需重提案
（**不**重判）；③ writer 失败原因**不留痕** —— 非法 JSON / 结构不符 / 调用异常统一 `None`，
排障只能靠上层 rejected 教训（change `0234`）；④ plugin 候选不生成 content（有意：其内容面
由 `EvolutionExecutor` 的补丁生产者承担）；⑤ 生产组合根**恒开**内容门，无「只生成不门禁」
的配置面；⑥ 新增接缝使测试桩必须按 prompt 分派 —— change `0239` 的 benchmark 桩漂移即此
风险的实例（ADR-0223 局限③）。

## ADR-0227：运行环境感知的 shell 方言（change 0237 / 台账 E174）

**背景**：预置 prompt 与 `tools.code_run` 把「命令执行」默认成 **bash 心智**：系统提示**不注入**
宿主 OS / 默认壳 / 路径风格；`code_run` schema 仅 `python|bash` 且实现硬编码 `bash -c`；TUI
一律渲染 `Bash(...)`。在 Windows 上模型产出 POSIX/`&&`/`export`，执行面找不到 bash 或语法
非法，反复试错。对标 Claude（双工具 + 平台选主壳）与 Cursor（prompt 注入 `Shell: …`）的
交集：**软事实 + 硬方言必须同开**。

**决策**：

- **D1 环境快照为纯函数、可整替**：`probe_environment(*, system=None, which=None)` 产出
  `EnvironmentSnapshot`（`os` / `default_shell` / `shell_label` / `path_style` /
  `has_pwsh` / `has_powershell` / `has_bash`）；`system` / `which` 可注入 ⇒ 单测**不打真实
  PATH**。平台默认壳钉死：Windows ⇒ `powershell`；Darwin / Linux ⇒ `bash`；其它 ⇒ `unknown`。
- **D2 Phase 0 系统提示独立块**：`LLMPlanner(env_snapshot=…)`；`_env_block()` 在工具块之前产
  「运行环境：」独立块（OS、默认壳与标签、路径约定、句法禁忌、`file_*` 优先）；`None` ⇒
  空串、**不产块**（既有提示逐字不变）。
- **D3 Phase 1 `code_run` 多方言**：schema `type ∈ {python, bash, powershell}`；缺省由
  `resolve_run_type` 按快照解析（Windows ⇒ powershell；bash / unknown ⇒ bash，保持历史
  「未传则 bash」兼容）；显式 type 优先。argv：`python` ⇒ `sys.executable -c`；`bash` ⇒
  `bash -c`；`powershell` ⇒ `pwsh -NoProfile -Command`（回落 `powershell`）。目标解释器不在
  PATH ⇒ `ValueError` 由工具层归一为**结构化错误**，SHALL NOT 静默改方言。
- **D4 TUI 标题按有效 type 命名**：`_code_run_name(args)` 映射 `powershell` ⇒ `PowerShell`、
  `python` ⇒ `Python`、`bash` ⇒ `Bash`；括号摘要仍取 `script` 首行有界口径。
- **D5 组合根注入真实探测**：`runtime.py` 构造期 `env_snapshot = probe_environment()`，同一
  快照注入 planner（多处 planner 构造点）与 `code_run` 工具工厂；测试路径可整替快照。
- **D6 不拆双工具**：保留单 `code_run` 多 `type`（权限 / 确认门策略不变）；不做 Phase 2 回喂。

**规格**：`loop` **ADDED**「运行环境事实」＋ 2 Scenario（6 → 7 req、91 → 93 scen）；
`tool-use` **MODIFIED**「内置原子工具（代码执行 / 网页读取）」＋ 3 Scenario（9 req 不变、
26 → 29 scen）；`ui` **ADDED**「code_run 活动标题按方言命名」＋ 2 Scenario（21 → 22 req、
90 → 92 scen）。既有 Scenario 逐字保留。

**反证（实测，回溯补记时补做）**：把 `resolve_run_type` 的平台判据改为恒不命中（Windows 缺省
落回 bash）⇒ **2 红**（`test_resolve_run_type_defaults` / `test_code_run_default_type_windows`）；
Linux 缺省、显式方言、缺解释器 fail-closed、Python 回归等 51 例恒绿。复原 ⇒ `env_shell.py`
`md5sum` 逐字节同（`f448d5fb…`）。测试锚点 **20 个函数**（`tests/test_os_aware_shell.py` 18 +
`tests/test_tool_use.py` 2）。

**局限**：① 生产快照在 runtime **构造期**探测一次 —— 长驻进程内新装 / 卸载 shell 不刷新；
裸 `code_run` 工具工厂缺省（`env_snapshot=None`）则**每次调用**探测，两口径并存；② 未知 OS
缺省仍落 bash（兼容历史），未强制显式 `type`；③ `shell_label` 只报解释器名，**不**探版本
（design 曾写「版本可得则带」）；④ 单测以注入快照覆盖平台分支，**未**在真实 Windows 上跑
执行面（本机 Linux）；⑤ 只注入软事实 + 单工具多方言，未拆双 `tool_id` ⇒ 权限 / 确认规则仍是
`code_run` 单一门（与 Claude 双工具模型不同）；⑥ 不感知 MCP / 远程执行面的宿主 OS。

## ADR-0228：Windows 运行环境提示与 code_run 输出完整性（change 0240 / 台账 E175）

**背景**：`0237` 的方向正确（软事实 + 硬方言同开），但 Windows 实测仍暴露三处缺口：
① `subprocess.run(text=True)` 按宿主 locale 解码（zh-CN Windows 为 cp936），与 `pwsh` 7 的
UTF-8 输出 / 5.1 的 `[Console]::OutputEncoding` 不一致 ⇒ 中文乱码，模型误判命令失败；
② 环境块只报默认壳，不报**实际可用**的 shell，默认壳缺失时不给下一步，未知 OS 分支仍声称
「默认壳为 bash」；未说明每次 `code_run` 是全新进程与 `cwd` 的 `~` 语义；③ TUI / Web 在
`type` 缺省时一律标 Bash，Windows 上误导操作者。

**决策**：

- **D1 父侧解码确定**：`code_run` 的 `subprocess.run` 增 `encoding="utf-8",
  errors="replace"`；解码不依赖子进程 locale，非法字节降级为替换符而非工具失败。
- **D2 子侧输出配对**：powershell 在用户脚本前拼有界 preamble
  `[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; $OutputEncoding = …`
  （5.1 / 7+ 通用）；python 子进程 env 增 `PYTHONIOENCODING=utf-8`（保留其余宿主环境）。
- **D3 环境块补全**：列 PATH 上实际可用的 `pwsh` / `powershell` / `bash`；标签区分
  `PowerShell 7+ (pwsh)` 与 `Windows PowerShell 5.1 (powershell)`；默认壳不可用 ⇒ 明确建议
  `type=python`；声明全新进程 / `cd` 与环境变量不保留 / `cwd`（绝对路径，支持 `~`）；给出
  **有界** Python 回退规则（仅方言不可用或无法表达时；`pathlib` / `tempfile`，勿硬编码
  `/tmp`，勿掩盖方言错误）；未知 OS 不再声称 bash。**执行层不自动降级**：回退是模型显式
  选择 `type=python`，保持「缺解释器 ⇒ 结构化拒绝」契约。
- **D4 活动标题用有效 type**：`_code_run_name(args, default_shell)` 显式 type 优先；缺省按注入
  的平台事实（powershell ⇒ PowerShell，bash ⇒ Bash）；事实不可得 ⇒ 中性 `Shell`。
  `UIAPILayer` 增可选 `env_snapshot` 与 `default_shell`；`Runtime` 增 `env_snapshot` 字段
  （与 planner 共用启动探测），`_build_ui` / CLI `_stream` / TUI 动作与子任务里程碑统一接线。
  Web 无运行时事实 ⇒ `toolName(toolId, args)` 缺省 `Shell`，`Chat.svelte` 在 `startAction`
  时存友好名。
- **D5 `cwd` `~` 展开**：`Path(cwd).expanduser()`，其余不 `resolve` / 不 `abspath`；空串保持
  原语义。
- **D6 纠偏 ADR-0227 D5**：原文「同一快照注入 planner 与 `code_run` 工具工厂」与生产不符 ——
  `builtin_tools()` 不接收快照，生产 `code_run` **每次调用** `probe_environment()`。本 ADR
  确认该口径为**既定取舍**：执行面即时反映 PATH 变化，planner / TUI 用启动快照；不改执行代码。

**规格**：`loop` **MODIFIED**「运行环境事实」＋ 3 Scenario（7 req 不变、93 → 96 scen）；
`tool-use` **MODIFIED**「内置原子工具（代码执行 / 网页读取）」＋ 2 Scenario（9 req 不变、
29 → 31 scen）；`ui` **MODIFIED**「code_run 活动标题按方言命名」＋ 1 Scenario（22 req 不变、
92 → 93 scen）。既有 Scenario 逐字保留。

**反证（实测）**：摘掉 `encoding` / `errors` kwargs ⇒ `test_code_run_decodes_utf8_deterministically`
红；摘掉 powershell preamble ⇒ `test_code_run_powershell_sets_utf8_output_encoding` 红；摘掉
python env ⇒ `test_code_run_python_sets_utf8_io_env` 红；摘掉 `default_shell` 接线 ⇒ TUI
有效 type 三例红；复原 ⇒ 相关文件 `md5sum` 同。测试锚点：`tests/test_windows_run_completeness.py`
14 个函数 + `test_os_aware_shell.py` 既有 18 例（其中缺省标题断言改为中性 `Shell`）+
`frontend/src/lib/activity.test.js` 11 个 `it`。

**局限**：① 标签只到「7+ / 5.1」可执行名粒度，不起版本探测子进程；② `errors="replace"` 对
真正非 UTF-8 字节不可逆（可辨识但不还原原文）；③ Web 端无环境事实注入，缺省只能中性
`Shell`；④ 生产 `code_run` 每调用探测 PATH，与 planner / TUI 的启动快照在极端 PATH 变化下
可能短暂不一致（既定取舍）；⑤ 未在真实 Windows 上跑执行面（本机 Linux），编码路径以注入
测试与子进程 kwargs 锚定。

## ADR-0229：记忆与进化高危面收口 —— 评测异常 fail-closed / 派生豁免 / 密钥脱敏（change 0241 / 台账 E176）

**背景**：对记忆模块与 evolution 决策路径的全量 review 发现三处「规格已要求、实现未闭合」：
① `BenchmarkScorer` 的 runner 异常按规格冒泡，但 `Evaluator.evaluate` 未捕获 ⇒ 异常直穿
`EvolutionEngine.run_cycle` / `EvolutionWorker.maybe_run`，候选不进台账、不产 `frozen`，
`_sample_observations` 与 `_completed.clear()` 均不执行；② `episodic`（情景归纳产物）漏登记
`_GATE_EXEMPT_SOURCES`，作为派生结论却会因低分被拒收/降层；③ 摘要、循环轨迹、进化写回
（`dissolve` / `reject` / 技能内容字段）均原样落库，模型或人工输入不构成信任边界。

**决策**：

- **D1 评测器 fail-closed**：`Evaluator.evaluate` 对 `_held_out_score` 包 `try/except Exception`
  ⇒ 返回 `_frozen(baseline=baseline)`。打分异常 = **无法评测**，与「无基线/无留出分」同结论；
  SHALL NOT 冒出击穿闭环，SHALL NOT 吞成 `rollback` / `publish`。只捕 `Exception`（Ctrl-C /
  `SystemExit` 仍中断）；不新增日志出口（避免回显异常 message）。
- **D2 `episodic` 纳入评分豁免面**：`_GATE_EXEMPT_SOURCES` 增 `"episodic"`（与
  `compaction` / `context` / `extraction` / `relation` 同面）。同步修正注释：豁免评分（写入面）
  与豁免遗忘（衰减面）不是同一组来源，`episodic` 是第三类 —— `forget` 按 `kind == "episodic"`
  走衰减，不受该集合约束（**刻意设计，不改遗忘策略**）。
- **D3 写回脱敏闭环**（统一用 `core.memory.redact_secrets`，纯函数、方向 over-redact）：
  | 写回点 | 处理 |
  |---|---|
  | `_commit_summary` 会话摘要 | store 侧**无条件** `redact_secrets(summary)` |
  | 循环轨迹条目 | 整条内容 `redact_secrets("\n".join(lines))` 后写入 |
  | `dissolve` 原因 | `content=redact_secrets(reason)` |
  | `reject` 人工理由 | 拼接文本 `redact_secrets` 后落库 |
  | `_crystallize_skill` | `description` / `preconditions` / `task_types` 脱敏；`instructions` 既有已脱敏；`param_schema` 不改写 |
  | `_crystallize_plugin` | 交付 crystallizer 的 `issue` 脱敏 |
  未命中密钥形态时为**恒等变换**，正文与结局逐字不变。

**规格**：`memory` **MODIFIED**「记忆压实」（＋1 Scenario）与「写入侧重要度闸门」（豁免面补
`relation` / `episodic`，＋1 Scenario）（17 req 不变、128 → 130 scen）；`loop` **MODIFIED**
「执行循环」（轨迹内容口径改为「除密钥形态脱敏外逐字不变」，＋1 Scenario）（7 req 不变、
96 → 97 scen）；`evolution` **ADDED**「进化写回与技能内容的密钥形态脱敏」＋3 Scenario
（18 → 19 req、95 → 98 scen）。evaluator 面**规格中性**：evolution「留出评测」已要求异常冒泡
给评测器判 `freeze`，本 change 只让实现对齐。既有 Scenario 逐字保留。

**反证（实测）**：逐项还原 —— 摘 `try/except` ⇒ 2 红；摘 `episodic` 豁免 ⇒ 1 红；还原三处
脱敏（摘要 / 轨迹 / 进化写回）⇒ 6 红；复原 ⇒ 相关文件 `md5sum` 同。测试锚点：新增 9 例
（`test_evolution_gate_data.py` 2 / `test_evolution.py` 4 / `test_memory_episodic.py` 1 /
`test_memory_summary_promotion.py` 1 / `test_loop_memory_sequence.py` 1）＋
`test_memory.py` 豁免面集合断言同步扩为五来源。全量 2670 → **2679** passed。

**局限**：① 评测器只捕 `Exception`，进程级中断仍直穿（刻意）；② 脱敏为**行内替换**，不识别
跨行拼接或编码变形后的密钥（既有判据边界，全仓同源）；③ `episodic` 的遗忘面仍按 `kind` 走
衰减，本 change 只修注释与评分豁免，不改遗忘策略；④ 摘要脱敏发生在 `_commit_summary`，
`_deliver_promotion` 的长度判据仍按**脱敏前**摘要计算（越界判定不变，属既定口径）。

## ADR-0230：prompt 对齐与技能内容容错/有界（change 0242 / 台账 E177）

**背景**：记忆与 evolution 全量 review 的批次 B 暴露两类「提示词与执行口径不一致」：
① 摘要 prompt 要求「总长不超过 800 字」，而滚动合并上界 `MAX_SUMMARY_CHARS = 2000` ——
模型被要求产出远小于可承载上限的摘要；② 关键事实 / 关系的落库名额已随会话长度自适应
（`key_fact_cap(n)`，8~16），但抽取器工厂的 prompt 名额固定为 `KEY_FACTS_MIN = 8`；关系 prompt
只列规范英文谓词，而正文声称「可用中英任一变体」；③ `skill_content_writer_with` 只接受纯 JSON
文本，模型把合法对象包进代码围栏或前后杂文即整条丢弃，且 `SkillContent` 文本字段**无长度上界**。

**决策**：

- **D1 摘要 prompt 与上界同源**：`summarize._PROMPT_HEAD` 的字数要求由 `MAX_SUMMARY_CHARS`
  插值生成（模块导入时一次性渲染）—— 不新增第二份数字，也不改滚动合并/提升钩子语义。
- **D2 抽取 prompt 名额与落库同源**：`build_extract_prompt` / `build_relation_prompt` 的
  `max_facts` / `max_relations` 缺省改为 `None` ⇒ 按**本次调用**条目数计算
  `key_fact_cap(len(entries))` / `relation_cap(len(entries))`；显式传值语义不变。抽取器契约与
  store 落库名额均不变，只消除「prompt 要求 8、落库允许 16」的内耗。
- **D3 关系谓词表由白名单派生**：新增 `render_predicate_table()`，遍历 `_CANONICAL_PREDICATES`
  并从 `_PREDICATE_VARIANTS` 取出映射到该谓词的全部变体（中英），渲染为
  `depends_on（依赖/依赖于/取决于/depend on/…）`。不另写词表 ⇒ 变体集合与归一化白名单同源。
- **D4 writer 容忍围栏与杂文**：`_json_object` 先直接 `json.loads`；失败时截取**首个 `{` 至
  末个 `}`** 再解析（与 `extract._json_array` 同型容错，但对象形状独立实现 —— evolution 不
  import memory）。仍不可解析 / 非对象 ⇒ `None`（fail-closed 语义不变）。
- **D5 `SkillContent` 有界**：常量 `_MAX_INSTRUCTIONS_CHARS=4000`、`_MAX_DESCRIPTION_CHARS=400`、
  `_MAX_TASK_TYPES=16`、`_MAX_TASK_TYPE_CHARS=80`、`_MAX_PRECONDITIONS=8`、
  `_MAX_PRECONDITION_CHARS=200`。writer 解析后**裁剪**（保留可用内容，不整条丢弃）；
  `validate_skill_content` **拒绝**超界内容 —— 持久化 delta / 外部注入内容不经 writer，
  不构成信任边界；`param_schema` 为结构化对象，不做文本截断（截断会破坏 schema）。

**规格**：`memory` **MODIFIED**「记忆压实」（＋1 Scenario）、「结构化实体抽取（关键事实）」
（＋1 Scenario）、「实体关系抽取（relations）」（＋2 Scenario）（17 req 不变、130 → 134 scen）；
`evolution` **MODIFIED**「技能候选内容生成」（＋3 Scenario）（19 req / 98 → 101 scen）。
既有 Scenario 逐字保留。

**反证（实测）**：摘要 prompt 还原 800 ⇒ 1 红；抽取 / 关系名额还原 `KEY_FACTS_MIN` ⇒ 2 红；
谓词表还原纯英文 ⇒ 1 红；去掉围栏容错 ⇒ 2 红；去掉裁剪 ⇒ 1 红。复原后三个源文件
`md5sum` 同。测试锚点：新增 8 例（`test_memory.py` 1 / `test_memory_key_facts.py` 1 /
`test_memory_relations.py` 2 / `test_evolution_skill_content.py` 4，含 2 个参数化围栏用例）；
`test_prompt_pinning.py` 摘要头与谓词表渲染同步；`doc/03-interfaces/prompts.md` 镜像同步
（含 ⑥ 行号 398→403）。全量 2679 → **2687** passed。

**局限**：① prompt 字数/名额对齐**不保证模型遵守**，落库仍按上界截断/计额；② 内容裁剪是
**就近截断**，可能截在句子中间（结构不破坏，可读性受影响）；③ `param_schema` 大小仍未设
上界；④ 谓词变体表是闭合白名单的**镜像维护面**（新增变体需改 `_PREDICATE_VARIANTS`）；
⑤ 前端 `doctest` 与 Web 侧构建不在四门禁内（既有边界）。

## ADR-0231：候选终态化与观察期滑动窗口（change 0243 / 台账 E178）

**背景**：记忆与 evolution 全量 review 的批次 C 暴露两处**判定语义**缺陷：① `EvolutionEngine.
run_cycle` 的门禁拒绝 / 留出退化 / 无法评测三个分支只返回 outcome，**不把候选置终态**，而
`PendingQueue.pending()` 只按 `status == "pending"` 过滤 ⇒ 已判失败的候选仍出现在
`evolve pending`，人工 `confirm` 后才在 `crystallize` 撞 `GATE_REJECTED` / `EVAL_REGRESSED` /
`EVAL_FROZEN`；恢复面另有 fail-open：落盘记录缺失 `kind` / `risk_level` 时按 `skill` / `low`
恢复，损坏/旧格式记录可绕过架构级审批。② `ObservationWindow.mean` 对开窗以来**全部**样本求
均值且样本列表无上界 ⇒ 早期好样本永久稀释后期回归（退化永不触发），长跑下窗口无界增长。

**决策**：

- **D1 失败结局显式终态**：`run_cycle` 在 `record` **之前**置状态 —— 门禁拒绝 / 留出评测
  `rollback` ⇒ `status="rejected"`；`freeze` ⇒ `status="frozen"`（独立终态，避免把「无法评测」
  误记为「已判退化」）。`EvolutionOutcome.status` 保留三值以区分结局；`pending()` 过滤面不变。
- **D2 恢复 fail-closed**：`_candidate_from_dict` 对未知/缺失 `kind` 取 `plugin`、`risk_level`
  取 `high`；缺失/未知 `status` ⇒ `rejected`；`caliber` 缺失仍保持 `0`（不可结晶）。正常记录
  四字段齐全 ⇒ 行为不变。
- **D3 滑动窗口**：新增 `_OBSERVE_MAX_SAMPLES = 64` 与 `ObservationRegistry(max_samples=64)`；
  采样追加后超界淘汰最旧，`_load` 恢复时同样裁剪；`mean` 语义变为「最近窗口均分」。不采用
  EWMA（引入平滑系数这一不可解释的新决策参数；滑动窗口可直接写入规格与教训）。`max_samples <
  min_samples` 不额外校验（误配侧是「永不触发」，保守方向）。
- **D4 基线口径写明而非改码**：基线仍是发布时留出评测分；规格明确在线样本是归因 trace 成功率，
  二者仅**代理可比**、容差吸收量纲差、基线不随样本重估（发布时无在线样本，无法标定在线基线）。

**规格**：`evolution` **MODIFIED**「观察期回归自动溶解（auto-dissolve）」（＋3 Scenario）与
「人工确认队列的持久化与操作面」（＋3 Scenario）—— 19 req 不变、101 → 107 scen。既有 Scenario
逐字保留。

**反证（实测）**：摘 `run_cycle` 终态赋值 ⇒ 3 红；摘滑动裁剪（采样 + 恢复）⇒ 3 红；恢复缺省
还原 fail-open ⇒ 2 红。复原后三个源文件 `md5sum` 同。测试锚点：新增 9 例（`test_evolution.py`
7：终态 3、窗口上界/恢复裁剪/不稀释/基线不变 4；`test_evolution_pending.py` 2：损坏记录
fail-closed、未知 status 不恢复为 pending）。全量 2687 → **2696** passed。

**局限**：① 观察窗口仍是进程内 + 单文件状态，多进程并发采样无锁（既有局限，未扩大）；
② `frozen` 只影响待确认快照 —— `find()` 仍可定位该候选（留痕需要），`crystallize` 的既有
门禁/评测校验仍会拒绝；③ 基线（留出分）与在线样本（成功率）量纲不同，容差是唯一调节面，
未做在线基线标定；④ 已确认（`confirmed`）后 `confirm` 再次调用仍会覆盖状态（既有行为，本
change 未收紧）；⑤ `max_samples` 与 `min_samples` 的关系不校验，误配靠「永不触发」兜底。

## ADR-0232：记忆批量落盘、热集有界与派生抽取/教训块预算（change 0244 / 台账 E179）

**背景**：记忆与 evolution 全量 review 的批次 C 暴露三处**规模/放大**问题：① `_reinforce` 对
本次检索选中的每条目逐条 `put`，而 `FileBackend._persist` 是**全量 JSONL 重写** ⇒ 一次 read
命中 k 条即 k 次 O(N) 落盘；`_hot`（写入侧热字典）无上界，长跑写入持续增长。② 压实
`_summarize_sessions` 在 summarizer 返回**空摘要**时仍照常提交并跑派生抽取（关键事实/关系/
情节巩固）；空摘要使原条目**不会归档**、下轮仍是同一批材料 ⇒ 每轮对同一材料重复抽取（模型
调用放大）且以同一 trace 覆盖写。③ 既往失败教训注入块最多 5 条但**每条正文不限长** ⇒ 单条
长教训即可占满 prompt 预算。

**决策**：

- **D1 批量落盘**：新增 `FileBackend.put_many(entries)` —— 一次更新 `_entries` / `_index`
  后**单次** `_persist`，语义与逐条 `put` 相同（同 id 覆盖、索引去重后追加）。`MemoryStore`
  经 `getattr` 特性探测调用，后端无该入口时逐条 `put` **回退**（鸭子类型后端不受影响）。
  `put_many` **不进** `MemoryBackend` Protocol 必选面（避免强制既有/测试后端实现）。
  逐条 `memory.reuse` 可撤销效应与其顺序**不变**。
- **D2 热集有界**：`_HOT_MAX = 512`，`_hot_put` 统一入口按**写入序淘汰最旧**（读路径从不填
  `_hot`，故为 FIFO 而非严格 LRU）。后端内存集才是全量真源，`_all_entries()` 冷热并集与读面
  不受淘汰影响；`_restore_importance` 对已淘汰条目**回退冷区**定位，保证撤销正确。
- **D3 空摘要守卫**：summarizer 返回空 ⇒ 告警（只报会话键，不回显正文）并 `continue`，
  本轮跳过提交与派生抽取/巩固。**不**引入持久「已尝试」状态位——材料未归档是事实，下轮重试
  是必要行为（模型侧持续失败则持续告警）。
- **D4 教训块预算**：抽出纯函数 `_render_failure_lessons`：条数上限 5 不变，单条正文 ≤500
  字符、总正文 ≤1500（按选取顺序消耗预算），每行折叠为单行。

**规格**：`memory` **MODIFIED**「温度分层检索」（＋1 Scenario）与「记忆压实」（＋1 Scenario）
⇒ 17 req 不变、134 → 136 scen；`loop` **MODIFIED**「执行循环」（＋1 Scenario）⇒ 7 req / 97 →
98 scen。既有 Scenario 逐字保留。

**反证（实测）**：摘 `put_many` 分支（强制逐条）⇒ 批量用例红；摘 `_hot` 裁剪 ⇒ 热集上界用例
红；摘空摘要 `continue` ⇒ 跳过抽取用例红；摘教训截断 ⇒ 有界用例红。复原后两文件 `md5sum` 同。
测试锚点：新增 5 例（`test_memory.py` 4：批量一次落盘 / 无 `put_many` 回退 / 热集有界且后端为
真源 / 空摘要跳过；`test_failure_lessons.py` 1：教训块有界）。全量 2696 → **2701** passed。

**局限**：① `_hot` 是 FIFO 而非严格 LRU（读路径不填充热集；严格 LRU 需读时提升，收益不抵
写路径外的新变动）；② `_restore_importance` 冷区回退用 `search("")` 线性定位，撤销路径罕见、
未建二级索引；③ 空摘要守卫只作用于**本轮**，摘要模型持续失败会逐轮重复 summarize + 告警（材料
未归档，属必要重试），未做退避；④ `put_many` 靠能力探测而非类型约束，后端实现偏离时只在批量
路径退化；⑤ 教训预算按**字符**计而非 token，CJK 下偏保守，与 token 估计口径问题同源（留
change 0245）。

## ADR-0233：基准会话隔离与 CJK 感知的 token 估计（change 0245 / 台账 E180）

**背景**：记忆与 evolution 全量 review 的批次 C 剩余两项：① 基准执行以
`session_id="bench"` 跑主 loop（`runtime.py:322-329`），会话隔离只覆盖 `read`；维护节拍
仍会 `memory.compact(session_id="bench")`，而 `_summarize_sessions` 的关键事实 / 关系 /
episodic 三类派生**均以 `session_id=""` 全局层落库**，摘要提升还写 canonical 真相层 ⇒
合成基准内容经抽取进入用户全局检索面，违背 `evolution` 「评测基建」既有承诺（「会话隔离，
SHALL NOT 污染全局记忆层」）。② 共享估计器与记忆读预算都用 `len // 4`（`context/budget.py`、
`memory/store.py`、`memory/transcript.py`）⇒ 中文按 ≈1 token/字符时低估 2–4 倍，事实预算、
历史/摘要预算与压实触发的事前判断在中文会话下失真。

**决策**：

- **D1 临时会话（ephemeral）**：`MemoryStore(ephemeral_sessions=(...))`（缺省空 ⇒ 逐字不变）。
  命中会话的压实**只做会话级摘要与原条目归档**（L2 有界、条目迁 L4），**跳过**
  `_deliver_promotion` 与三类全局派生。组合根仅在 `features.evolution_benchmark_runner`
  开启时传 `("bench",)` ⇒ 与执行面**同开同关**；不新增配置键（`bench` 是内部约定，非用户旋钮）。
  不采用「独立 bench loop + `maintenance_interval=0`」：`general_agent.loop` 与兜底子 Agent
  共用实例，关维护会连带关闭普通子任务维护；独立 loop 只挡「维护」一条路径而读面仍写，
  且装配重复。
- **D2 单一估计器**：新增中性模块 `core/tokens.py` —— **CJK 字符 ≈1 token/字符**（统一表意
  文字含扩展 A / CJK 标点 / 假名 / 谚文 / 全角形式），其余 4 字符 ≈1 token，空串至少 1。
  `context.budget` 与 `memory.store` / `memory.transcript` 共用（memory 不能 import context
  —— ADR-0045；`core.persistence` 已有「中性模块被能力包共用」先例）。CJK 取 1 token/字符
  是**保守上界**（宁高勿低：低估使预算事后失真，高估只是更早裁剪）。
- **D3 窗口换算 4 → 2**：`window._CHARS_PER_TOKEN = 2`（CJK 1 / 非 CJK 4 的混合折中），
  避免中文中层摘要按 4 倍 token 预算产出；份额常量不变（规格只钉份额）。

**规格**：`evolution` **MODIFIED**「评测基建」（Requirement 正文不动，＋1 Scenario：
基准会话不写全局派生）—— 19 req 不变、107 → 108 scen。CJK 估计属规格中性缺陷修复
（既有要求「token 控制在预算内」被低估破坏）；口径写入接口文档，防漂移。

**反证（实测）**：摘 `ephemeral` 守卫 ⇒ 基准会话用例红（对照用例仍绿）；估计器退回
`len // 4` ⇒ 3 红（CJK 计数 / 混合 / 记忆读预算）；窗口改回 4 ⇒ 1 红。复原后三文件
`md5sum` 同。测试锚点：新增 10 例（`test_token_estimate.py` 5、`test_memory.py` 3：
ephemeral 派生 0 调用 + 普通会话对照 + CJK 读预算；`test_benchmark_runner.py` 2：门控开/
关的接线）。全量 2701 → **2711** passed。

**局限**：① 基准执行仍注入 skills / SOP / notes（`_loop_hooks.on_turn` 会写 canonical 笔记与
技能反馈）——读面与学习信号隔离是独立议题，本 change 只收口**记忆压实派生**；
② `_score_importance` 仍对基准会话条目打分（会话内写 importance，非全局），省调用未做；
③ `ephemeral_sessions` 是构造期集合：运行期新增合成会话若未登记仍会派生（当前仅 `bench`）；
④ token 估计是**字符集粗估**：不区分代码/数字密集文本，不与供应商 tokenizer 对齐，CJK 取 1
token/字符偏保守；⑤ `_CHARS_PER_TOKEN=2` 是混合折中：纯中文摘要仍可能有 ≤2 倍预算误差，
纯英文摘要比旧行为短一半。

## ADR-0234：编排失败恢复（重试 1 次 + 重新拆解 1 次）（change 0246 / 台账 E181）

**背景**：`TaskScheduler.astream` 此前是线性 `for wave`：任一波次出现失败子任务即
`VERIFYING→RECOVERING` 后直接 `return`。`RECOVERING` 不是终态，任务永久悬置；`run()`
消费端虽把 `task_failed` 还原为抛错，但生产路径（`--resume` / delegate）拿到的是一个既无
终态、也无法继续的状态。规格 `orchestration` R2 早已要求「回退重试（有限次）或重新规划」，
实现未闭合。另有三处同源缺口：① `_fan_out` 的 `asyncio.gather` 无异常兜底，子 Agent 抛出
的异常直穿调度器；② 检查点不携带恢复预算；③ 空计划（planner 返回空 / 旧检查点无子任务）
因「空成功标准视为通过」被判 `DONE`。

**决策**：

- **D1 有限恢复回路**：把「拆解 → 波次执行 → 终态判定」包进 `while True`。波次 fan-in 后
  `EXECUTING→VERIFYING`；有失败 ⇒ `VERIFYING→EXECUTING`，**只对失败子任务**重跑 1 次
  （`_MAX_SUBTASK_RETRIES = 1`，新建同波次信号量、复用事件排水；`SubtaskOutcome.attempt`
  与 `subtask_started.attempt` 标记执行序号；重试目标追加有界失败提示）；仍失败 ⇒
  `VERIFYING→RECOVERING`，重新拆解 1 次（`_MAX_REPLANS = 1`）。预算耗尽 ⇒ `FAILED`，
  错误码沿用最后一次失败原因（`SUBTASK_VERIFY_FAILED` / `SUBTASK_EXECUTION_FAILED` /
  `DEADLOOP_DETECTED` / `PROGRESS_NOT_MET`），payload 增 `attempts` / `replans`；**不新增
  错误码**，保调用方兼容。
- **D2 重新拆解语义**：输入 = 原 goal + 已完成子任务摘要 + 失败项与原因（有界
  `_MAX_HANDOFF_CHARS`）；新计划保留原 `goal` 与原 `success_criteria`（原标准非空时）。
  重拆后**清空本任务的 tracker 完成集、`_results` 与累计 outcomes** —— 新 DAG 可能复用 id
  但语义不同，清理避免误跳过与脏依赖。重拆异常或空计划 ⇒ 直接 `FAILED`，不再消耗预算。
- **D3 计数持久化**：`Plan.replans: int = 0` 随 `plan_to_dict` / `plan_from_dict` 往返；
  重拆前**先落计数与检查点**，崩溃续跑不重置恢复预算。子任务重试次数是**进程内**有界计数，
  不跨进程持久化（崩溃续跑重新获得 1 次重试，仍有界）。`CheckpointFn` 4 参签名不动。
- **D4 异常归一**：`_guarded_subtask` 捕获 `OrchestrationError` 保留原码，其余 `Exception`
  → `SUBTASK_EXECUTION_FAILED`；`CancelledError`（`BaseException`）透传。执行异常进入同一
  重试/重拆回路，不再裸崩调度器。
- **D5 空计划守卫**：`plan.subtasks` 为空或 `plan.waves` 为空 ⇒ `FAILED`
  （`SUBTASK_VERIFY_FAILED`），不因「空标准视为通过」误判 `DONE`（顺带闭合 P0-6 的空计划
  续跑假成功）。
- **D6 状态机**：`_enter_executing` 增 `RECOVERING→EXECUTING` 分支；既有转移表已含该边，
  无需新边。成功路径的事件序列逐字不变；新增事件 `task_retrying` / `task_replanning` 仅在
  失败路径出现，`plan_ready` 增 `replan` 字段。

**规格**：`orchestration` R2「子任务拆解」**MODIFIED**（恢复回路段落 + 6 Scenario）、
R4「断点续跑」**MODIFIED**（`Plan.replans` 持久化 + 1 Scenario）—— 11 req 不变、
50 → **57** scen。

**反证（实测）**：`_MAX_SUBTASK_RETRIES = 0` ⇒ `test_run_retry_succeeds_without_replan` 红；
`_MAX_REPLANS = 0` ⇒ `test_run_verify_failure_retries_then_replans_then_fails` /
`test_run_replan_after_retry_exhausted` 红；摘 `_enter_executing` 的 `RECOVERING` 分支 ⇒
`test_run_replan_after_retry_exhausted` 红；复原 ⇒ `scheduler.py` `md5sum` 同
（`c97840f7f12ff7c65db08e5394af49f0`）。测试 +6（1 例改名替换既有用例，净 +5：
2711 → **2716**）。四门禁全绿；`openspec validate --all` 中本 change 绿（`0230` / `0233`
两项既有归档欠账均已收口；`0233` 于 2026-10-17 归档，ADR-0244）。

**局限**：① 重试/重拆各 1 次是**固定策略**（无配置旋钮），费用有界但复杂故障可能不够；
② 任务级判定可能误判，fail-closed 只触发一次恢复（`0248` 接判定器后同）；③ `cancel`
只转状态、不断流（D1 既有缺口，不在本 change）；④ 消费方断流/运行中取消未覆盖；
⑤ 重试是**进程内**计数，崩溃续跑会重新获得 1 次重试；⑥ 重拆清空 `_results` 后，新计划
若复用已完成子任务 id 且不重新执行，依赖上下文需由新执行重新填充（由「已完成摘要 +
不重复安排」提示约束，非硬保证）。

## ADR-0235：TaskHandoff 统一执行框架（beast / pet / 主任务复用）（change 0247 / 台账 E182）

**背景**：`TaskScheduler._run_subtask` 直接 `profile.loop.astream(goal)`，`TaskHandoff` 的
`context_pack` / `acceptance` / `deadline` / `priority` **零消费**；beast 虽走
`MultiAgentRouter.handoff`，也只用了 `task` / `session_id`。依赖结果靠手写字符串拼接、无总预算；
`deadline` 无执行方（无子任务超时）；委托（delegate）子 Agent 的轨迹落全局层，不随发起会话归组。
规格 `orchestration` R3 已承诺交接协议字段，实现未闭合。

**决策**：

- **D1 共享执行器**：新增 `src/core/orchestration/handoff.py` —— `build_context_pack` /
  `render_handoff` / `stream_handoff` / `run_handoff`。scheduler / router / beast / pet 复用同一套
  交接代码，**不合并**各自的 loop 与上下文：`session_id` 仍由调用方填对（主任务 = 发起会话、
  beast = `beast.agent_id`、pet = UUID），执行器只转发、不解释。
- **D2 上下文有界**：`build_context_pack` 以 `core.tokens.estimate_tokens`（change 0245 口径）
  为预算单位（`DEFAULT_CONTEXT_TOKENS = 2000`），按依赖顺序装入；单字段（goal / result）以
  `MAX_HANDOFF_CHARS = 2000` 字符封顶；最后一条按剩余预算几何截断（`_fit_tokens`）并在首次
  截断后停止装入 ⇒ 交接文本不随依赖数量无界增长。`MAX_HANDOFF_CHARS` 成为单点真源，
  scheduler 的依赖注入 / 检查点截断统一引用。
- **D3 全字段消费**：`TaskScheduler._build_handoff` 构造完整 `TaskHandoff`（`task`、`context_pack`
  含原目标与依赖结果、`acceptance`、`deadline`、`priority`、`session_id`），经
  `MultiAgentRouter.handoff_stream` 执行 ⇒ 保留 `subtask_progress` 流式回流。`priority` 继续由
  就绪队列排序消费；`deadline` 由配置 `orchestration.subtask_timeout` 注入（`0` ⇒ `None`）。
- **D4 渲染语义（行为分界）**：`render_handoff` 在 `context_pack` 与 `acceptance` 均为空时
  **逐字返回 `task`** ⇒ beast / pet 现有 prompt 逐字不变；scheduler 路径必然非空 ⇒ prompt 追加
  「原始目标 / 前置子任务结果 / 验收标准」段，属**有意**行为变更（规格要求的字段消费，非隐藏开关）。
- **D5 超时归一**：`stream_handoff` / `run_handoff` 以 `asyncio.timeout(deadline)` 包住整段执行，
  超时取消子流并归一 `OrchestrationError(SUBTASK_TIMEOUT)`（新增错误码）；进入 `0246` 的
  重试/重拆回路，不裸崩。`run_handoff` 经 `arun`（而非 `collect_result(astream)`）执行，保留
  `DefaultLoop.arun` 的回合收尾语义。
- **D6 配置与 `config set`**：照 `difficulty_policy` / `max_concurrency` 模板新增
  `orchestration.subtask_timeout`（int ≥0，默认 `0`；CLI/env/yaml 三面；校验期阻断；组合根注入）。
  `_key_to_patch` 白名单加入 `orchestration`，并修 `_merge_patch` 对 `extra` 寄居段的合并 ——
  此前只浅合并 `loop`，`orchestration` patch 会被静默丢弃（「报成功却不生效」，与账本 E15 同型）。
- **D7 会话隔离（委托透传）**：`DefaultLoop` 在 `_act` 前后 set/reset
  `current_session_id` ContextVar（`finally` 复位，异常不泄漏）；`runtime._dispatch` 读取后传给
  子 Agent `arun(task, session_id=…)`。`exclude_source_prefixes=("beast.","pet")` 与三命名空间
  `source` 规则**逐字不动**；不引入 `AgentProfile.session_scope`。
- **D8 beast / pet 收口**：beast `summon` 的 `session.recall()` 移入 `finally`（成功 / 失败 / 超时 /
  异常均回归 `RECALLED`，不滞留 `ACTIVE`）；pet `wake` 经 `asyncio.run(run_handoff(...))`，
  空上下文 ⇒ prompt 逐字相同。

**规格**：`orchestration` R3「多 Agent 协同」**MODIFIED**（2 → 6 Scenario，+4）；`configuration`
「编排调度配置」**MODIFIED**（新增 `subtask_timeout` 与校验口径，3 Scenario 数不变）。
规格总量 11 req / 57 → **61** scen。

**反证（实测）**：`render_handoff` 忽略上下文/验收 ⇒ 3 红（render / router / scheduler 全字段）；
摘 `asyncio.timeout` 包装 ⇒ 超时用例**挂起**（15s 限时 `exit=124`，非绿）；scheduler 退回最小
`TaskHandoff(task, session_id)` ⇒ 2 红（全字段 / deadline+priority），超时用例挂起；摘
`current_session_id` set/reset ⇒ `test_current_session_id_visible_in_act_and_reset_afterward` 红；
`runtime._dispatch` 丢弃会话 ⇒ `test_delegate_forwards_current_session_to_subagent` 红。
复原后 `md5sum` 同：`handoff.py` `de07985ac72b935a45ef7b2263bf2e15`、
`scheduler.py` `d0a1061e34023c4b82cf0b757702f682`、`loop/default.py`
`e778e4e328e3537dcdab84f217e3980f`、`runtime.py` `3d738cd28cda2284fbe6315af905a420`。
测试净 +24（2716 → **2740**）。四门禁全绿；`openspec validate --all` 中本 change 绿
（`0230` / `0233` 两项既有归档欠账均已收口；`0233` 于 2026-10-17 归档，ADR-0244）。

**局限**：① `deadline` 默认关闭（`0`），需显式配置；`asyncio.timeout` 依赖 Python 3.11+（项目基线）；
② 单次交接上下文最多 2000 token，超长依赖结果被截断（保头不保尾，可能丢结论）；
③ 委托/取消/挂起仍不安全（D1）：`cancel` 只转状态、不断流；`on_done` 异常仍可能逃逸；
`_results` 不在终态清理；④ 跨命名空间既有风险（Agent 2）：`compact(session_id="")` 可能从
beast/pet episodic 派生全局事实；canonical notes 提升绕过 source 排除；子 Agent 共享 loop 实例的
单槽 `_post_turn_task`。三者**会话数据不混**，登记为已知局限；⑤ `subtask_timeout` 以整数秒配置，
亚秒级仅测试可达（构造参数为 `float`）。

## ADR-0236：目标监控闭环（planner 生成成功标准 + 任务级判定）（change 0248 / 台账 E183）

**背景**：规格 `orchestration` R6 承诺「用 Goal 与 SuccessCriteria 定义任务级成功标准，并由
ProgressTracker 追踪进度」，实现却空转：拆解 prompt 只产 subtasks，`success_criteria` 无生产者；
`decomposer.decompose` 忽略调用方传入的标准；`success_checker` 签名只拿标准、看不到子任务结果，
组合根从未注入（无标准时无人调用，有标准时只会 `MISSING_SUCCESS_CHECKER`）；`ProgressTracker`
只有完成集合，失败/重试不可见。

**决策**：

- **D1 标准由拆解产出**：`_DECOMPOSE_SYSTEM` 顶层改为
  `{"success_criteria": ["..."], "subtasks": [...]}`，约定 2-5 条、每条可客观判定真伪、覆盖整体
  目标而不复述子任务 acceptance。新增 `DecomposeResult(subtasks, success_criteria)`；`Planner`
  协议接受 `list[Subtask] | DecomposeResult`（既有单参 lambda 桩零改动）。
- **D2 解析与优先级**：`_parse_criteria` 只收非空字符串、strip、保序去重、至多 5 条；
  `decompose` 的优先级为「显式非空 > planner 生成 > 空」；`_fallback` 恒不带标准 —— planner 调用
  失败时若仍生成标准，同源 LLM 判定的 fail-closed 会把本可执行的任务拖死。重新拆解时原标准非空
  则保留（`Plan.success_criteria` 随计划入检查点）。
- **D3 任务级判定器**：新增 `LLMTaskVerifier`，**复用** `_VERIFY_SYSTEM` 与模块级 `_judge` /
  `_fail_closed`（不新增 prompt 常量，镜像零改动）；输入 Goal + 标准逐条 + 每子任务状态与结果
  节选（单条 ≤ `_MAX_OUTCOME_REPLY = 500`），整体 `redact_secrets` 脱敏后以
  `_MAX_VERIFY_CHARS = 4000` 截断；单次重试后仍失败 ⇒ fail-closed。criteria 为空时直接判过、
  不发请求。
- **D4 调度器接线**：`SuccessChecker` 改为
  `Callable[[str, list[str], list[SubtaskOutcome]], VerifyResult | Awaitable[VerifyResult]]`；
  `_success_met` 改 async 并接收 outcomes；异常/非法返回经 `_coerce_verdict` 归一 fail-closed；
  未达标以 `PROGRESS_NOT_MET` 进入 `0246` 恢复回路（重拆预算未用尽则重拆，否则 `FAILED`）。
  存在标准但未注入 checker 仍 fail-fast（`MISSING_SUCCESS_CHECKER`）。
- **D5 三态进度**：`ProgressTracker` 增 `started` / `failed` 两个集合与
  `progress(task_id) -> {"started","completed","failed"}`；`start` / `record` 清 failed，
  `fail` 标失败，`reset` 清空；`detect_stall` 仍以 completed 签名判定（口径不变）。
- **D6 缺省开启**：组合根注入 `LLMTaskVerifier(llm, model=app.llm.model)`。用户裁决为缺省开启，
  且**必须**与 D1 同 change 落地 —— 只生成标准不注入 checker 会让生产任务全量
  `MISSING_SUCCESS_CHECKER` 失败（本 change 的 P0 前置）。

**规格**：`orchestration` R6「目标监控」**MODIFIED**（3 → 6 Scenario，+3；既有
「成功标准定义」逐字保留）。规格总量 11 req / 61 → **64** scen。

**反证（实测）**：摘 `_parse` 的 criteria 解析 ⇒ DAG / 限条两用例红（生成标准为空）；摘组合根
注入 ⇒ `test_build_runtime_injects_policy_and_limit` 红；`LLMTaskVerifier._render` 忽略子任务
结果 ⇒ `test_llm_task_verifier_judges_goal_criteria_and_outcomes` 红。复原后 `md5sum` 同：
`planner.py` `35348dbf13e89eb10bb7ef0002019085`、`runtime.py`
`0504ee0f1ed5997ecc5238caecd23554`。测试净 +12（2740 → **2752**）。四门禁全绿；
`openspec validate --all` 中本 change 绿（`0230` / `0233` 两项既有归档欠账均已收口；`0233` 于 2026-10-17 归档，ADR-0244）。

**局限**：① planner 生成的标准质量取决于模型，可能过宽/过窄；判定为同源 LLM，存在共模误判，
仅 fail-closed 兜底；② 任务级判定每任务额外一次 LLM 调用（判失败时重试一次），费用有界但非零；
③ 判定输入只含每子任务 500 字符结果节选，超长结果的关键证据可能被截断；④ 标准不参与
`PROGRESS_NOT_MET` 之外的错误码，调用方无法区分「子任务验收失败」与「整体目标未达成」的细粒度
原因（payload 中带 reason）；⑤ 重拆时若原标准为空则采纳新标准，两条路径的判定口径可能随重拆变化。

## ADR-0237：长任务记忆缺口修复（token 估算器注入 / 预算降级 / L2 软上限 / keyfact 跨批合并 / 文件检查点）（change 0230 / 台账 E184）

**背景**：长任务存活面盘出五项「规格已承诺 / 结构上该有、实现缺失」的缺口：① token 估算口径
写死为启发式，无法注入精确实现（预算与记忆读预算各自内联，口径漂移只能靠测试护栏）；
② loop 预算触顶**直接终止**，不给模型收尾机会；③ L2 活跃层无软上限，长任务下只增不减；
④ keyfact 跨批次重复抽取虽按 `keyfact.<slug>` 覆盖，但**首见时间戳被重置**（长任务时间线失真）；
⑤ 编排检查点只有注入面，无缺省文件实现，进程重启即丢。G3/G6（检索预算阈值、记忆层间摘要）
属 ADR-0045 刻意设计，本 change 只记录不改。

**决策**：

- **D1 token 估算器注入（G1）**：新增 `core.tokens.TokenEstimator` 协议（`estimate(text) -> int`）、
  `HeuristicEstimator` 缺省实现与 `DEFAULT_ESTIMATOR`；`BudgetManager(estimator=None)`、
  `DynamicAssembler(token_estimator=None)`、`MemoryStore(token_estimator=None)` 均接受注入，
  未注入回落同一启发式 ⇒ **行为逐字不变**。`budget.py` 保留 `estimate_tokens` 模块属性并在
  `__all__` 声明（既有两个调用面「共用一把尺子」的守卫按模块属性比对）。
- **D2 预算降级续跑（G2）**：抽出 `DefaultLoop._budget_retry`：预算触顶且本轮未降级过、已注入
  压实器 ⇒ 强制压实一次（复用 `compacted` 闸门）并给**一轮收尾机会**；收尾轮完成即正常收口，
  仍未完成才 `TOKEN_BUDGET_EXCEEDED`。**口径调和**：压实只做持久化/摘要/遗忘，**不减少本轮
  消息记账**（`ctx.token_used` 不因压实下降），故原任务书「压实后重试一轮」只能落为「收尾轮」，
  不能落为「压完继续跑」；收尾轮后记账重算为 `max(_context_tokens, 上报 prompt tokens)`，
  保证 trace 口径与模型实际输入一致。未注入压实器 ⇒ 立即终止（既有行为不变）。
- **D3 L2 活跃层软上限（G5）**：`MemoryStore(l2_soft_max_entries=None)` 缺省关闭；写路径末尾
  `_enforce_l2_cap`：超限先走既有 `forget()`，仍超限则按 `ts` 升序对**可遗忘条目**
  （`_forgettable`，与 `forget` 共用判据）逐条 `migrate(L2 → L4)`；异常降级 `warnings.warn`，
  **不阻塞写入**。语义是软上限：非可遗忘条目（L0/L3、非 opt-in semantic）不因上限被迁移。
- **D4 keyfact 跨批合并（G4）**：同实体条目本就按 `keyfact.<slug>` 覆盖写入，本 change 补上
  `ts=existing.ts`（首见为正时间戳时保留），使「跨批次同实体合并」不重置时间线；批内归并
  （change 0172）语义不变。
- **D5 文件型检查点（G7）**：新增 `FileCheckpoint(path=".core/scheduler-checkpoint.json")`
  dataclass，满足 `CheckpointFn` 四参调用契约：JSON 落盘 `task_id / session_id / plan /
  completed / results`，**原子写**（同目录 `.tmp` + `os.replace`）；`load(task_id=None)` 读回并可
  按任务过滤，损坏/缺失返回 `None`。**保持 opt-in**：调度器未显式收到 `FileCheckpoint` 时
  SHALL NOT 自行落盘（缺省行为逐字不变），上层注入的回调仍优先、不产生文件 I/O。

**规格**：4 个 capability 新增 6 个 requirement / 17 个 Scenario（context +1/+3、loop +1/+4、
memory +3/+7、orchestration +1/+3），全部 ADDED，既有 requirement 逐字不动。

**测试**：新增 15 例（`test_context.py` 3、`test_loop.py` 2、`test_memory_key_facts.py` 1、
`test_memory_long_task_gaps.py` 6、`test_orchestration.py` 3）；全量 2752 → **2767**。

**反证（实测，`cp` 备份 + md5 复原）**：`budget._tokens` 改回直连启发式 ⇒ 注入估算器 2 红；
`_budget_retry` 首行改 `if True` ⇒ 收尾轮 2 红；keyfact 去掉 `ts=existing.ts` ⇒ 首见时间戳 1 红；
`write` 摘 `_enforce_l2_cap` 调用 ⇒ 软上限 3 红；`FileCheckpoint` 的 `completed` 写空 ⇒ 落盘往返
1 红；复原后 md5 同：`budget.py` `b0569f6e704dd151d90be39131af11b4`、`default.py`
`e6dfb9d97d0800a493201fe29895fc7e`、`store.py` `dc80f4fc3f2af3b789d11304c612b742`、
`scheduler.py` `d6a0751414cd9965c69676041a50e90b`。四门禁全绿；`openspec validate --all` 中本
change 绿（`0233` 已于 2026-10-17 归档，ADR-0244，与本 change 无关）。

**局限**：① 估算器只覆盖预算/读预算/短带截断，三层窗口的「token → 字符」换算仍按 2 字符/token
（与 ADR-0233 同口径）；② 预算降级只给**一轮**收尾，收尾轮本身仍可能产出大量 token（上界由
`max_rounds` 与单轮模型输出约束，非硬截断）；③ L2 软上限按**条目数**而非字节/token，单条超长
内容不受限；④ `_enforce_l2_cap` 的排序+迁移是 O(n) 扫描，条目极多时写路径有额外开销（缺省关闭）；
⑤ 文件检查点只保证**单进程单写者**原子性（`os.replace`），多进程并发同路径会互相覆盖（既有
`CheckpointStore` 也未做跨进程锁）；⑥ keyfact 首见时间戳保留依赖旧条目仍在冷/热区，若旧条目已
归档则新写以 `ts=0` 起算。

## ADR-0238：运行中取消与消费方断流（协作取消信号 / 在途扇出打断 / 任务级上下文终态释放）（change 0249 / 台账 E185）

**背景**：D1 遗留（ADR-0236 局限行、任务书 D1）：① `cancel` 只把状态转 `FAILED` —— 在途
波次继续跑、`_results` 不清、执行流仍可能朝 `VERIFYING` / `DONE` 推进（取消被后续事件覆盖）；
② `astream` 无退出收口 —— 消费方 `aclose()` / 断流后后台扇出与任务级缓存残留、状态悬置；
③ 取消不可观测（无 `TASK_CANCELLED`，调用方无法区分「取消」与「自然失败」）。

**决策**：

- **D1 协作取消信号**：`TaskScheduler` 维护 per-task `asyncio.Event`（`_cancel_events`）与当前
  波次扇出任务登记（`_wave_tasks`，`task_id → gather Task`）。`cancel(task_id)`：终态任务
  **幂等返回**（不抛 `INVALID_TRANSITION`）；否则置信号、**立即 `cancel()` 在途扇出**、转
  `FAILED`、`tracker.reset`、清 `_results`。执行流在四个观察点检查信号（拆解后、每轮波次前、
  波次 drained 后、任务级判定后），以 `task_failed {code: TASK_CANCELLED}` 终止（状态已由
  `cancel` 转移，`_cancelled` **不重复转移**）。
- **D2 消费方断流收口**：`astream` 拆为薄包装 + `_stream_task`（主管线），包装层
  `finally: _release(task_id)` 覆盖**任意退出路径**（正常终态 / 取消 / 断流 / 异常）：取消在途
  波次（若仍登记）、清 `_cancel_events` / `_wave_tasks` / `_results`；**未达终态 ⇒ `FAILED`** +
  `tracker.reset` + trace `task_aborted`（`reason` 区分「任务已取消」/「消费方断流」，不伪装成功）。
  正常 `DONE` / `FAILED` 路径只释放缓存，不动状态与进度。
- **D3 单一清理归属**：在途波次取消有且只有两个主动点 —— `cancel()`（用户主动、立即打断）与
  `_release()`（退出兜底）；`_stream_wave` 的 `finally` 只 `await` 收拢并注销登记，**不**二次
  cancel。实测两条路径互为兜底 ⇒ 单独摘任一条，断流用例仍绿（无法反证）；收敛为单点后
  `_release` 成为可反证的唯一兜底。
- **D4 取消边界**：取消**不能**打断正在 `await` 的拆解 / 任务级判定等外部调用（此时无在途
  波次），信号在其返回后观察；外部 `CancelledError`（非本调度器取消）照常透传，
  `_stream_wave` 仅当信号已置时吞掉 `CancelledError`（安静收拢）。
- **D5 事件与错误码**：不新增事件类型（UI/CLI 已按 `task_failed` 收口），新增错误码
  `TASK_CANCELLED`；`run()` 消费 `astream` 时按既有语义抛出 `OrchestrationError`。

**规格**：`orchestration` **ADDED**「运行中取消与消费方断流」1 req / 4 Scenario（取消打断在途
子任务 / 断流释放执行单元 / 终态清理任务级缓存 / 重复取消终态任务幂等）；既有 requirement
逐字不动。

**测试**：`tests/test_orchestration.py` +4（2767 → **2771**）。反证（`cp` 备份 + md5 复原）：
摘 `cancel` 的扇出取消 ⇒ 取消用例红；摘 `_release` 的在途取消 ⇒ 断流用例红（5.34s 超时）；
摘 `_release` 的 `_results` 清理 ⇒ 终态清理用例红；摘波次后取消观察点 ⇒ 取消用例红；
摘终态幂等守卫 ⇒ 幂等用例红。复原 md5 同：`scheduler.py`
`b8d4f2551dd213a47da2cce5b9d81211`、`errors.py` `7fda28e4b1f721361352569ca3ac174f`、
`test_orchestration.py` `cf371aa76b5aa2315a6bbc80b3a1d052`。四门禁全绿。

**局限**：① 取消只能打断**波次内**子任务；拆解 / 任务级判定 `await` 进行中只能等其返回后观察
（最长一个模型调用时延）；② 已执行子任务的副作用与检查点结果**不回滚**（可逆性由效应追踪与
既有断点语义承担，取消不是回滚）；③ `cancel` 为事件循环内同步调用，跨线程 / 跨进程取消不覆盖；
④ 取消与断流**同为 `FAILED`**，仅 trace `task_aborted.reason` 区分；⑤ 消费方只 `break` 而
**不**调用 `aclose()` 时，异步生成器延迟终结 ⇒ 在途波次可能持续到下一次 GC / 事件循环关闭
（调用方应显式 `aclose()`；`astream` 的 `finally` 只在生成器终结时运行）。

## ADR-0239：进化留出评测缺省策略 —— 全链路 opt-in，`frozen` 为安全姿态（台账旧行收口）

**背景**：`known-risk.md` §1 旧行「留出评测生产 runners 未接 ⇒ 候选恒 `frozen`」（来源
`phase-34.md:68` / ADR-0112）已过时 —— change `0212` / ADR-0202 已把真实执行器接到组合根
（`module_health` / `tool_use`），但执行面缺省关，且评测还需**已注册基准**与**已注册基线**。

**决策**：保持**全链路 opt-in**（三步缺一不可）：① `features.evolution_benchmark_runner: true`；
② `core-agent evolve benchmark register <id> --plugin-id <target> --task-type …`；
③ `core-agent evolve benchmark set-baseline <target> <score>`。**不**翻转缺省、**不**自动引导基线。
判据「注册基准 ≠ 同意执行」（`evolution` spec「执行面门控（缺省关）」逐字要求）。

**理由**：① 执行面真实调用模型、产生费用，属「关得住、且是关着的」执行面（与
`evolution_executor` 同极性）；② 翻转开关**并不消除** `frozen` —— 无注册基准 / 基线仍 `freeze`，
只减少一步却扩大意外开销面；③ 自动基线会把「当前实现分」当阈值，改变评测语义（自证循环），
须另立 change 与反证，不在本决策面。

**影响**：缺省部署下进化候选终态为 `frozen` 属**预期**安全姿态，不是缺陷；开启路径写入
`doc/02-modules/evolution.md` §3.8 与台账 §1 行。**放弃的替代项**：缺省开 runner / 自动引导
基线（理由同上）。无代码与规格变更（规格本就要求缺省关）。

## ADR-0240：宠物人格固定与故障韧性（persona pinning / 落盘边界 / 唤醒退避恢复）（change 0250 / 台账 E186）

**背景**：宠物专项复盘发现三处生产可达缺陷：① `PetSession.snapshot()` 不含人格，组合根恢复
工厂也未传 `persona` ⇒ 从注册表恢复的会话是**无人格裸任务**，规格「独立人格」「人格约束行为」
在新进程不成立；② 注册表只在 `register/start/stop/remove` 落盘 —— `wake`（消费任务、计数递增）、
`assign`、`sleep` 全为内存态 ⇒ 新进程看到旧快照：已消费任务**重放**、已派发任务**丢失**、计数归零；
③ `wake()` 直接 `asyncio.run(...)`，异常裸抛；`backoff()` 无生产调用方，`BACKOFF` 无出口 ⇒
「异常退避」在唤醒路径未落地，失败任务静默丢失且宠物无恢复途径。

**决策**：

- **D1 人格随快照固定**：`snapshot()` 增 `persona` 字段（`name/species/persona_text/traits/
  preferences`，无人格 ⇒ `None`）；`restore(..., persona_factory=...)` 解析序 = **显式人格 >
  快照 + 工厂 > 无**。`persona_from_record()` 与 `Persona` 字段一一对应，缺键取 dataclass 缺省、
  未知键忽略（描述性文本，无版本迁移面）。组合根恢复工厂传 `persona_factory=persona_from_record`。
  无人格调用方（`persona=None` 且快照无该键）行为**逐字不变**。
- **D2 落盘边界 = 变更后持久化**：新增公开 `PetManager.persist()`（无路径 ⇒ no-op）；`PetControl`
  的 `sleep/wake/assign` 变更成功后落盘（`stop` 经 `manager.stop` 已落盘）；`pet run` 的 `on_tick`
  **先** `manager.persist()` **再**呈现 —— 覆盖「驱动唤醒消费任务 / 计数递增」这类非控制面变更。
  整表覆盖写、不追踪脏位：多余一次落盘无害，漏落盘就是丢进度。
- **D3 唤醒故障 → BACKOFF + 上抛**：`wake()` 捕获 `Exception`（**不**捕获 `CancelledError` /
  `KeyboardInterrupt`）⇒ `backoff(exc)` 置 `BACKOFF` + 故障原因 ⇒ **原样 re-raise**，驱动按
  `FAILED` 记录且不中断其余宠物（既有隔离契约不变）。
- **D4 控制面退避出口**：新增 `PetSession.recover()`（`BACKOFF → ACTIVE`、清故障；其余态抛
  `PET_NOT_ACTIVE`）；`PetControl.wake` 对 `BACKOFF` 走 `recover()`，其余仍走既有 `resume()` ——
  宿主无感内部态，同一动词即「睡醒」也「退避恢复」。
- **D5 失败任务不回队**：任务在执行前出队（一次性语义），失败原因经 `_fault` 与驱动 `FAILED`
  观测面可见；自动重放会绕开「主人派发」的明确意愿，且无退避上限 —— 是否重派由主人/控制面决定。

**规格**：`pet-mode` **MODIFIED** 4 req（Background Pet Session Lifecycle / Multi-Pet Management /
Pet Persona and Prompt / Pet Control Surface），新增 5 Scenario（唤醒异常退避与恢复 / 唤醒进度与
人格跨进程还原 / 人格跨进程固定 / 退避恢复），既有 Scenario 与 Requirement 文本逐字保留。

**测试**：新增 `tests/test_pet_resilience.py`（12 例）+ `test_entry.py::test_pet_run_drives_restored_sessions`
扩为断言 tick 落盘（2771 → **2783**，+12）。反证（`cp` 备份 + md5 复原）：
P1 摘 `snapshot` 的 persona 字段 ⇒ 人格往返用例红（KeyError）；P2 摘 `restore` 的工厂分支 ⇒ 人格
往返 + 运行时工厂用例红；P3 摘 `wake` 的 try/except ⇒ 退避用例红（`ACTIVE`）；P4 摘控制面 BACKOFF
分支 ⇒ 退避恢复用例红（`PET_NOT_ACTIVE`）；P5 摘 `assign` 的 persist ⇒ 跨进程可见用例红；P6 摘
`on_tick` 的 persist ⇒ entry 驱动用例红。复原 md5 同：`session.py`
`e1dd1f9dd72e2480019c41f5c47fade4`、`control.py` `ee002a18e5cc10bd0a0373ea68e96e01`、
`manager.py` `c220892dc61213ea8db0d7bad3e875a3`、`persona.py` `a3a27207f1ed5ae8957f34e70cf4f494`、
`entry.py` `dd723e374341879f75e0132729bb3a84`、`test_entry.py`
`a66863b1b2e55de88cd309cefc79d40b`。四门禁全绿。

**局限**：① 整表快照落盘，多进程**同时**写同一注册表为「最后写者胜出」（既有架构，未引入锁/合并）；
② `recover()` 只清故障、**不**重置 `wake_count`（累计事实，不是故障状态）；③ 失败任务不回队，
需主人重新 `assign`；④ `persona_from_record` 不校验人格内容语义（与 `parse_persona` 同口径：
文本直通）；④ 控制面仍只作用本进程 live 会话（规格明文「有意不做跨进程」）；⑤ `restore` 对
快照中**形状非法**的 persona（非 dict）静默按无人格处理（不 fail-fast）。

## ADR-0241：L2 活跃层软上限的组合根接线（change 0251 / 台账 E187）

**背景**：记忆框架对比审查（P0）发现「规格已实现、生产不可达」：change `0230` 按规格
「L2 活跃层软上限」实现了 `MemoryStore(l2_soft_max_entries=...)` 与 `_enforce_l2_cap()`，
但组合根 `build_runtime` **没有传该形参**，`memory` 段也**没有对应 ConfigSpec** ⇒ 该能力在
任何生产配置下都关闭。代价是真实的：`FileBackend._load()` 整份加载 JSONL、`search()` 线性
扫描 ⇒ L2 只增不减时，常驻内存与每轮检索成本随运行时长单调上升。同时 `memory.md` 把 L1
描述为「指向 L2/L3 的最小索引（what→where）」，实现却是后端 `id → layer` 映射（不参与检索）。

**决策**：

- **D1 新键 `memory.l2_soft_max_entries`**：`ConfigSpec` 单一真源，`exposure=ADVANCED`，
  `default=None`。缺省 `None` = 能力关闭 —— 与 `MemoryStore` 形参语义一一对应，避免升级后
  一个缺省数字**静默归档**用户数据。是否设默认上限是运维决策，不由代码代替。
- **D2 访问器 `l2_soft_max_entries() -> int | None`**：读 `extra["memory"]`，经 `_parse_int`
  归一；`bool` / 小数 / 非数值 / `0` / 负数一律 → `None`。`0` 特意不收：直通会**清空 L2**
  （每次写入都迁走可遗忘条目），属危险笔误方向；归一为关闭不丢数据。返回原始值而非能力层
  类型（`configuration` 是底座模块，不得 import `memory`）。
- **D3 组合根接线**：`build_runtime` 的 `MemoryStore(...)` 增
  `l2_soft_max_entries=config.l2_soft_max_entries()`。收口逻辑本身不动（写入后先 `forget`、
  再按 `ts` 最旧迁 L4，`l2_cap.<id>` trace 可撤销）。
- **D4 文档订正**：`memory.md` 增 §3.14（装配、未启用即无界、只在写入后收口）；L1 行与
  「索引与事实不一致」行改为实现事实（后端同步维护 `id → layer`，无异步同步窗口）。

**理由**：① 能力已存在且有测试，唯一缺口是**接线**；补接线比重新设计爆炸半径小。② 缺省
关闭保证升级行为零变化 —— 软上限会改变「写入后条目还在不在 L2」，不能替运维决定。
③ 非法值归一为关闭是**同段既有口径**（`memory` 非结构化段），且方向安全（不设上限 ≠ 丢数据）。

**测试**：新增 `tests/test_memory_soft_cap_config.py`（13 例）。反证（`cp` 备份 + md5 复原）：
P1 摘组合根实参 ⇒ 接线 + 端到端 2 红；P2 摘 ConfigSpec ⇒ 三面元组 + env 覆盖 2 红；P3 摘
`>= 1` 归一 ⇒ `0` / 负数 2 红。复原 md5 同：`manager.py`
`5c64a712ee9b1f72470a8424d94ef8cc`、`runtime.py` `0897bbc3d7b60cde66aab78476ba5c56`。

**局限**：

1. **只在写入后收口** —— 存量超限库要等下一次写入才收敛（不在 `load()` 里跑，避免启动即迁移）。
2. **仅收口 L2**；L4 归档只增不减（「不物理删除」规格的必然结果）。
3. `FileBackend` 仍**整份加载 JSONL** —— 上限降低活跃条目数与检索扫描面，不改变文件总体量。
4. 非法取值**静默归一为关闭**（`memory` 段非阻断口径），不产生启动期错误。
5. **缺省未启用** —— 不设默认上限是运维决策，代价是缺省部署仍无界增长。

## ADR-0242：缺省词法检索的 IDF 加权与长度归一（change 0252 / 台账 E188）

**背景**：未配置 `llm.embedding_model` 时（**所有缺省部署**），记忆检索走词法相似，原公式为
`|交集| / |查询词元|` —— 所有查询词元等权、完全不看文档长度。后果：常见词把罕见词稀释成
同等权重；长文档只要多命中一个词元就压过短文档；CJK 二元组下尤为明显。这是检索排序的
**正确性**问题，不是可选增强。

**决策**：

- **D1 BM25 口径**：`idf(t) = ln(1 + (N - df + 0.5) / (df + 0.5))`，二值词频（tf=1），
  `k1 = 1.2`、`b = 0.75`；词元得分 `idf · (k1+1) / (1 + k1·(1 - b + b·dl/avgdl))`；
  按查询词元 IDF 总和归一，并收顶 1.0（短文档因子可 >1，与层权重同量纲）。
- **D2 一次检索建一次统计**：`build_lexical_stats(entries, query)` 对候选集分词并算
  `df` / `avgdl`，缓存 `doc_tokens`；`LexicalStats` 只对构建它的 query 有效。`MemoryStore.read`
  在排序前调用一次，排序阶段查缓存（不重复分词）。空查询 / 空语料 ⇒ `None` ⇒ 原公式。
- **D3 兼容面**：`stats` 是 `relevance` / `rank` 的**关键字参数**，缺省 `None` ⇒ 原重叠公式
  逐字不变（公开 API 与既有调用方零改动）。`MemoryStore.read` 始终传 stats；embedder 抛错
  降级时同样使用 stats（降级不丢 IDF/长度归一）。
- **D4 启动提示**：`entry._build_ui` 在 `llm` 存在且未配置 `embedding_model` 时向 stderr
  输出一次「词法匹配、语义检索未启用」；用 `getattr(llm, "embedding_model", "")` 读取，兼容
  无该属性的测试/嵌入式替身。已配置时不输出。
- **D5 文档落点**：`entry.py` 插行使 `prompts.md` ⑭ 落点由 1681 漂到 1689，随本 change 同步。

**理由**：① 缺省部署全走词法，IDF/长度归一是排序正确性；② 只改**缺省词法**路径，注入
embedder 时余弦相似路径逐字不变，爆炸半径小；③ 语料统计由 `read` 一次构建，排序复杂度仍为
O(候选数 × 查询词元数)，无额外 IO；④ 保留 `stats=None` 原公式，避免破坏 `relevance` 的公开契约。

**测试**：新增 `tests/test_memory_lexical_scoring.py`（9 例：IDF 罕见词、长度归一、CJK 二元组
精确覆盖、`stats=None` 原公式、`read` 端到端 IDF、embedder 失败仍用统计、空查询/空语料、原公式
忽略顺序、空查询 `rank` 不抛错）；`tests/test_entry.py` +2（提示有/无）。反证（`cp` 备份 +
md5 复原）：P1 摘 `read` 的 stats 传递 ⇒ 端到端 2 红；P2 摘 IDF 乘子 ⇒ 4 红（含罕见词）；
P3 `b=0` ⇒ 长度归一 1 红；P4 摘提示分支 ⇒ 1 红。复原 md5 同：`relevance.py`
`d7835f66e5f245a953f54141ae864409`、`store.py` `02c67a06403b0ab2b7db87165a5cd1e0`、
`entry.py` `4dc923db798dba552f6bb552d3cd96cb`。四门禁全绿（pytest 2807 passed）。

**局限**：

1. **二值 tf**（不做词频饱和）—— 同词出现多次不加权，省略 BM25 的 tf 饱和项以避免长文档
   靠重复堆分；若重复词后续被证为有效信号，需重新评估。
2. **统计范围 = 过滤后的候选集** —— 来源排除 / 会话过滤在统计之前生效，同一 query 在不同
   `session_id` / 排除面下 IDF 不同；`FileBackend.search` 目前返回全部条目（不截断），若后端
   未来预过滤或截断候选，IDF 会随之漂移。
3. **`avgdl` / `dl` 以词元数计**：CJK 二元组使中文文档长度约为字数，不区分词长；标点/数字
   处理沿用 `tokens()` 既有口径。
4. **归一后收顶 1.0**：短文档原始 BM25 分 >1 时被压平，多词命中与单词命中的相对差距被压缩
   （测试余量按收顶后的实际倍率设定）。
5. **提示只看 `llm.embedding_model`**：自定义 embedder 注入路径不在此提示范围；`entry._rag`
   另有 RAG 索引提示，二者口径不同（前者记忆检索、后者 RAG）。

## ADR-0243：压实/抽取成本的观测面（change 0253 / 台账 E189）

**背景**：维护节拍（会话压实 / 中期摘要 / 遗忘 / 冷路径）与轮内压实都在工作线程执行，含**同步
模型调用**（摘要器、关键事实抽取器）。但此前成功路径**没有任何耗时观测**；失败只有
`maintenance_failed` 的 error 字符串，多步并发时无法归因到具体步骤。调维护间隔、评估摘要器 /
抽取器成本、定位「收尾慢」都缺少数据。

**决策**：

- **D1 两类成本事件**：`_maintain` 每实际节拍产一条 `maintenance`（`elapsed_ms` + `steps`：
  `session_compact` / `mid_summary` / `forget` / `cold_path`）；`_compact` 每次产一条
  `compaction`（`trigger`：`threshold` / `budget_retry` + `elapsed_ms` + `steps`：`persist` /
  `memory_compact` / `forget`）。`steps` 只含**实际执行**的步骤（依赖未注入则不出现）。
- **D2 计时口径**：`time.perf_counter()` 分步计时（失败步骤经 `finally` 记账），耗时保留 3 位
  小数。不用 `time.time()`（回拨会产生负耗时）。
- **D3 失败归因**：两处 `maintenance_failed` payload 增 `step`；步骤失败仍降级不中断，成本事件
  照常产出。`_compact` 的 `persist` 保留原有 `ContextError` 静默分支。
- **D4 范围克制**：不接 `MetricsCollector`（需给 `DefaultLoop` 增注入面）、不新增配置键、不记录
  条目数 / token（`MemoryStore.compact` 不返回计数）、不改任何执行逻辑。

**理由**：① tracer 本身就是观测开关，未注入 ⇒ `_trace` 空转，缺省行为零变化；② 事件面已足够
导出面聚合与延迟归因，P2-lite 到此为止；③ 分步计时把「哪一步慢/失败」直接写进 payload，
不需要消费方反推。

**测试**：新增 `tests/test_loop_cost_observability.py`（6 例：节拍成本事件、节拍闸门、失败步骤
归因且其余继续、压实成本 + trigger、persist 失败归因、budget_retry 触发归因）。反证（`cp` 备份 +
md5 复原）：P1 摘 `maintenance` 事件 ⇒ 3 红；P2 摘 `compaction` 事件 ⇒ 3 红；P3 硬编码
`trigger="threshold"` ⇒ 2 红；P4 摘失败 payload 的 `step` ⇒ 1 红。复原 md5 同：`default.py`
`c52205596c513f87489bfe1f95f6aa4f`。四门禁全绿（pytest 2813 passed）。

**局限**：

1. **只记时间，不记数量** —— 被压实条目数 / 摘要 token 数不可见（`MemoryStore.compact` 不返回
   计数）；抽取成本只能按 `memory_compact` 总时长近似。
2. **事件在末尾发出** —— 进程在节拍中途崩溃时该次 `maintenance` 事件不存在（已执行步骤的失败
   留痕仍在）。
3. **无聚合 / 分位数** —— 每节拍 / 每压实一条原始事件，聚合依赖导出面；高频维护时事件量随
   节拍线性增长。
4. **`steps` 键是契约** —— 新增步骤向后兼容，改名属破坏性变更。
5. **线程内计时** —— `_compact` 在 `asyncio.to_thread` 工作线程执行，`elapsed_ms` 不含线程
   排队等待。

## ADR-0244：TUI 活动块（Thinking 缺省收起 / 友好标题 / 撤回 Task 壳）（change 0233 / 台账 E190）

**背景**：`0169` 把 TUI 思考/工具块的缺省态定为**缩略**（末尾 N 行可见）。产品反馈缩略仍占
时间线、符号噪音大 ⇒ `0233` 改为**缺省收起**（仅标题行），「在干什么」由友好标题摘要承载；
同时按 `round` 归并思考增量、撤回外层 `Task(<摘要>)` 壳。代码于 2026-10-12 随 commit `7357a11`
落地，但 spec delta 归档被拒、change 长期 active ⇒ `openspec validate --all` 恒 1 红。本次
2026-10-17 回溯收口：只校正规格 delta / 归档 / 台账，**零 `src/` 改动**。

**决策**：

- **D1 缺省收起优先于缩略**：思考块与工具块创建即 `collapsed=True`（仅标题可见）；点标题在
  **收起 ⇄ 展开**间切换，展开即全文（若正文极长，展开态内部可再提供末尾预览，但不是缺省）。
- **D2 标题无装饰符号**：`Read(path)` / `Write(path)` / `Edit(path)` / `Delete(path)` /
  `Bash(script 首行)` / `SubAgent(task 摘要)` / `Planner(goal 或波次摘要)` / `Thinking`
  （进行中 `Thinking…`；**不**把思考原文写进标题）。摘要只取白名单结构性字段、单行有界；
  正文类参数与内部 `tool_id` 不进标题；取不到摘要只留友好名 / 空括号。
- **D3 思考按 ReAct 步归并**：`loop.reasoning` 载荷增 `round`；同一 `round` 的增量追加到同一块，
  不同步用不同块；缺 `round` 时降级归并到当前未完成步（或新建块），**不丢增量**。
- **D4 撤回 Task 壳**：外层 `Task(<用户输入摘要>)` 折叠壳撤回，时间线改回扁平
  （思考块 / 工具块 / 主回复直接挂时间线）。
- **D5 delta 形态校正（本次回溯）**：旧「TUI 步骤块（缩略 / 全文 / 收起）」是 `0169` 的三态语义，
  `0233` 以「活动块：缺省收起 + 友好标题」**整体替换** —— 用 `REMOVED`（旧块）+ `ADDED`（新块）
  表达，而非沿用旧标题写 `MODIFIED`；「思考过程回显」属真 `MODIFIED`，场景名沿用
  `TUI 思考折叠回显` 并更新内容（OpenSpec 的 `MODIFIED` 整块替换要求场景名连续）。Task 壳的
  `REMOVED` 项在 canonical 中已不存在（历史上未归档即撤回）⇒ CLI 按「already removed」告警放行。

**规格**：`ui` MODIFIED ×1（Think，3 → 4 scen）+ REMOVED ×1（旧步骤块，6 scen）+ ADDED ×1
（新步骤块，7 scen）；canonical **22 req 不变、93 → 95 scen（+2）**。归档后
`openspec validate --all` **31 passed / 0 failed**（此前恒有 1 红）。

**测试**：代码与测试随 `7357a11` 已落地，本记录零新增。承载锚点（`tests/test_repl.py`）：
`test_tui_thinking_stream_merges_and_updates_in_place`（同 round 归并）、
`test_tui_thinking_splits_by_round`（不同步不同块）、
`test_tui_thinking_title_stays_without_content_while_streaming`（标题不刷原文）、
`test_tui_step_block_title_toggles_collapse`（收起 ⇄ 展开）、
`test_tui_step_block_shows_target_but_not_raw_args`（标题只取结构化摘要）、
`test_tui_bash_title_keeps_script_when_args_long` / `test_tui_subagent_title_from_task_field`
（Bash / SubAgent 括号摘要）。

**局限**：① 回溯收口未重跑 `tasks.md` 4.1 记的 Windows 8 红（路径分隔符 / `geteuid` /
`SIGKILL` / sidecar / durability 时间窗，与 0233 无关）；② 旧步骤块 6 个场景整体废止，
「缩略窗口 / 点正文切换」语义不再由规格承接（`0235` 已删除实现）；③ Task 壳 `REMOVED` 在
canonical 无对应项，归档仅告警；④ 0233 原始提交无 ADR，本记录为回溯补建，反证未重做；
⑤ 同一 commit 还含 planner 协议加严与轮末收尾后台化，其中跨 event-loop 取消传播缺陷由
`0239` / ADR-0223 另行收口。

## ADR-0245：记忆写回卫生（脱敏 / 有界 / 空值拒收 / 陈旧清理）（change 0254 / 台账 E191）

**背景**：2026-10-17 对五条记忆通道（会话滑窗压实 / SOP 技能进化 / evolution / 情景经验 /
任务关键信息）做「信息提取决策是否完善」审计。结构性门禁（来源白名单、可逆效应、容量上限）
完整，但**内容卫生**存在六处缺口，且全部位于**默认开启**的写入路径上（质量门反而缺省关闭，
开关方向倒置）：

1. `NoteStore.observe_turn` 的行动行原样拼进 canonical 正文（无 `redact_secrets`）；
2. `Compactor.persist` 把命中关键词的整段消息原样写 L2（无脱敏、无长度上界）；
3. 压实产物按 `compaction.*.<i>` 序号覆盖写回 ⇒ 上一轮多、本轮少时**旧序号条目残留**，
   陈旧事实永不消失；
4. `SkillRouter._record_miss` 把整句任务原样落 L2（无脱敏、无界）；
5. `SopExtractor.observe` 把提炼器输出原样 `register`（提炼器可能复述轨迹中的密钥）；
6. `scrub_key_fact` 允许空白 `value` 通过 ⇒ 空值**覆盖**同实体既有关键事实。

**决策**：

- **D1 写回边界统一脱敏，复用同一份判据**：五处均调用 `core.memory.redact_secrets`（与关键事实 /
  关系 / episodic 同一启发式，一处定义多处消费），命中段 → `<redacted>`；**先脱敏后截断**，
  截断不得使明文逃逸。不做整段抹除 —— 工具名 / 路径 / 动作结构保留（「做了什么」仍可读）。
- **D2 压实产物有界 + 陈旧清退**：单条 `_MAX_PRODUCT_CHARS=400`；关键词分类仍基于**原始消息**
  （口径不变）。`persist` 写完后对 `compaction.fact.<key>` / `compaction.open.<key>` 从本轮条数
  起逐号清退，走**新增的公开** `MemoryStore.discard(id)`（内部复用 `_delete_entry` ⇒ 热区 + 后端 +
  可逆 `memory.delete` 效应，不另开删除路径）；清退失败降级为保留残留、不阻断本轮写回。
- **D3 空值拒收先于引用式判定**：`entity` 或 `value` 在 `strip()` 后为空 ⇒ 丢弃，即便给出
  `coeffect:<名称>` 引用；`_plan_key_facts` 对其**静默跳过**（不计入「因密钥丢弃」留痕 ——
  空值不是脱敏结果，也不覆盖同实体既有条目）。
- **D4 未命中记录脱敏但有界不动 id**：正文 `redact_secrets(task)[:400]`；id 仍由**原始任务** +
  会话键派生 ⇒ 同会话幂等、跨进程重启不互相覆盖的既有语义逐字不变；`misses` 诊断窗口保留原文。
- **D5 缺省行为与可逆性**：全部为缺陷修复、**缺省开启**；不新增配置键、不新增模型调用。
  脱敏不改变任何闸门判据（闸门看未脱敏行 / 脱敏后的提炼文本按规格）。压实清退记可逆效应，
  回滚可复原。

**规格**：`notes` ADDED ×1（2 scen）、`context` ADDED ×1（3 scen）、`skills` ADDED ×2（2 scen）、
`memory` ADDED ×1（2 scen）；无 MODIFIED / REMOVED。归档后 `openspec validate --all` 全绿。

**测试**：`tests/test_memory_write_hygiene.py` 六个用例逐一锚定六处缺口（notes 密钥 + 结构保留 /
压实脱敏 + 单条 ≤400 / 同会话陈旧序号清退 / 路由 miss 脱敏 + 有界 + 幂等 / SOP instructions 脱敏 /
空 keyfact 丢弃且不覆盖既有）。反证：逐点摘除实现 ⇒ 对应用例红，复原后 md5 一致（6/6）。四门禁：
`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、`pytest -q` **2819 passed**。
`memory/extract.py` 与 `skills/sop.py` 顶部常量的行号因本次插入而漂移，
`doc/03-interfaces/prompts.md` §1 落点同步（178→181、403→406、48→49）。

**局限**：① 启发式只覆盖已知令牌形态，方向恒为 over-redact，不构成「绝不泄漏」的密码学保证；
② 既有条目不做历史清洗（只约束新写入）；③ 本 change 只做 P0（脱敏 / 有界 / 空值 / 陈旧），
P1 确定性 SOP 发布质量门、P2 抽取拒绝反馈与去重、P3 任务记忆摘要、P4 benchmark 执行候选
仍为后续批次；④ `DefaultLoop._record_observation` 仍以未截断 `json.dumps` 记观测面（非本次
写回面，登记待 P3 一并收口）；⑤ **SOP 提炼的输入**（`build_sop_prompt` 的步骤轨迹）仍不经
本模块脱敏（ADR-0214 局限③ 已有登记）—— 本 change 只约束落库的 `instructions`。

## ADR-0246：技能提炼确定性质量门与字段上界（change 0255 / 台账 E192）

**背景**：P0（`0254`／ADR-0245）只收口了记忆写回的**内容卫生**（脱敏 / 有界 / 空值 / 陈旧），
进化侧的**内容质量**仍有缺口：

1. SOP 提炼达阈值即自动 `active` 发布；唯一的发布前质量门（0198 `SopGate`）**仅在 JEV 配置时
   注入**，缺省部署下**单步 / 超短 / 逐字重复**的模型输出会直接成为可路由技能；
2. `SkillLibrary.register()` 只校验 `skill_id` 非空与 `param_schema` 为 dict，**无字段上界** ——
   模型 / 下载内容可不限量入库；
3. evolution 另有一份 `validate_skill_content` 上界（0242），与技能库**各写一套数值**，口径漂移
   风险。

**决策**：

- **D1 确定性门缺省开启、零模型调用**：发布路径固定为
  `writer → redact_secrets → 非空 → 确定性门 → 判定门（可选）→ 退役守卫 → register`。
  判据：`strip()` 后 10 ≤ 长度 ≤ 4000；≥ 2 个步骤行（`_STEP_LINE` 接受数字 / `-` / `*` / `•`
  列表）；不与库中任一技能 `instructions` 逐字相同。零模型调用使缺省开启不推翻「未配置 JEV
  ⇒ 零额外调用」的既有承诺。
- **D2 失败路径与判定门同构**：不入库 + **清组** + `warnings.warn` 只报组键（绝不回显正文）。
  空文本仍**保留样本**（模型瞬时失败），确定性拒绝则清组（同批样本已产出不可用文本，重抽只会
  放大调用）—— 沿用 0198 的既有取舍。
- **D3 只拦逐字重复**：不做 embedding / 相似度阈值（需新依赖，且阈值成为不可解释的发布判据）。
  同组重复本就覆盖同一 `skill_id`；跨组逐字相同 ⇒ 技能库不增长。
- **D4 上界单一定义**：`skills/models.py` 定义公开常量（`MAX_SKILL_ID_CHARS=120`、
  `MAX_INSTRUCTIONS_CHARS=4000`、`MAX_DESCRIPTION_CHARS=400`、`MAX_TASK_TYPES=16`、
  `MAX_TASK_TYPE_CHARS=80`、`MAX_PRECONDITIONS=8`、`MAX_PRECONDITION_CHARS=200`）；
  `SkillLibrary.register` 与 `evolution.content` 共同引用。`register` 越界抛既有
  `INVALID_SKILL_SCHEMA`（不新增错误码），错误文案只报字段名与上界、**绝不回显字段内容**。
- **D5 兼容性**：满足确定性门的多步 SOP 发布路径逐字不变（字段 / id / 状态 / 可逆效应 / 清组）；
  上界内的 `register`（含同 id 覆盖）逐字不变；不新增配置键。缺省发布路径**有意收紧**
  （单步 / 超短 / 重复不再入库），这正是本 change 的目的。

**规格**：`skills` **MODIFIED** ×2 req ——「原子技能库」（+1 scen 字段越界）、「SOP 提炼」
（+2 scen 确定性门 / 逐字重复；既有 10 场景名全部保留）。`openspec validate --all` 全绿。

**测试**：`tests/test_skill_extraction_quality.py` 15 个用例（两步照常发布 / 单步与超短清组 /
超长拒绝 / 确定性门先于判定门 / 逐字重复 / 7 类字段越界 + 不覆盖 + 上界内不变）。既有单步桩
改为两步（`test_skills.py` / `test_skill_retirement.py`，测试基线有意变更）。反证 5/5：摘确定性
门调用 ⇒ 5 红；`_MIN_STEPS=1` ⇒ 单步红；摘重复检查 ⇒ 重复红；摘 `_check_bounds` ⇒ 8 红；
摘确定性分支清组 ⇒ 3 红。复原 `md5sum` 一致。四门禁：`ruff check` / `ruff format --check` 绿、
`pyright` 0 errors、`pytest -q` **2834 passed**。`skills/sop.py` 顶部常量行号漂移，
`prompts.md` §1 落点同步（49→57）。

**局限**：① 只拦**逐字**重复，近似重复（换词 / 换序）不拦；② 步骤行判据依赖模型遵守
「编号步骤清单」的结构契约，散文式合格 SOP 会被误杀（over-reject 侧，需 prompt 对齐）；
③ 长度按字符计而非 token；④ 确定性门无关闭开关（缺省安全检查，关闭须改规格）；
⑤ `param_schema` 仍无大小上界（结构化对象，截断会破坏 schema，与 ADR-0230 局限③同）；
⑥ P2（抽取拒绝反馈 / 去重）、P3（任务记忆摘要）、P4（benchmark 执行候选）仍为后续批次。

## ADR-0247：运行稳定性三项（流式超时 / 中断留痕 / 压实有界）（change 0256 / 台账 E193）

**背景**：对实跑会话 `cb37aba3ddf54bcc9336be2464c95c07` 的复盘确认三条**同时发生**的稳定性缺陷：

1. **流式挂起无上限**：`StdlibLLMProvider.astream` 的消费端对 `queue.get()` **无超时**；生产者线程
   只在拿到 `data:` 帧时入队，而 SSE 注释 / keep-alive 行被 `_iter_sse_payloads` 跳过。socket 读
   超时管不到「连接活着但持续只发心跳」的端点 ⇒ 事件循环无限等待。
2. **中断无痕**：`Tracer` 事件在内存缓冲、仅在 `end_trace` 时经导出器落盘；`DefaultLoop.astream`
   无 `try/finally`。消费方断流 / 取消 / 未收尾异常时本轮事件**静默丢失**，事后无法归因。
3. **压实静默阻塞**：轮内压实把同步模型调用卸载到工作线程，但等待**无上限**；实测单次 38–54s。
   期间事件面没有任何进度信号，表现为「无响应」，也无法区分「慢」与「挂死」。

**决策**：

- **D1 队列级空闲超时**：`astream` 每块等待包进
  `asyncio.wait_for(queue.get(), timeout=self._timeout)`（复用既有 `llm.timeout`，不新增配置键）；
  超时 ⇒ 尽力关闭响应、抛 `LLMTimeoutError`。按**相邻增量间隔**而非总时长设限：合法长生成不被
  误杀，心跳型挂起必被截断。**流式不重试**：已交付增量不可回滚，重试会造成重复文本；上层既有
  `LLMError` 分支落失败终止动作并正常收尾。
- **D2 中断留痕薄包装**：公开 `astream` 变为包装器，执行体改名 `_astream_events` 并以
  `contextlib.aclosing` 关闭；`state["finished"]` 标记执行体是否已正常封口。未收尾时补记
  `loop_aborted`（`reason` 只取异常**类型名**，不含消息 / 用户文本 / 密钥）后再 `end_trace`。
  正常路径的封口时机与 `trace_observer` 回调顺序**逐字不变**（执行体自己封口）；中断路径
  **不**追加转录、**不**写轮末记忆、不改变既有回滚语义。
- **D3 压实进度与上限**：阈值压实前后各产出一条 LoopEvent：`loop.compacting`（`round`）与
  `loop.compacted`（`round` / `elapsed_ms` / `timeout`）；载荷不含正文或摘要。等待上限
  `compact_timeout`（构造注入，缺省 **120s**，`None` 关闭）经 `asyncio.wait_for` 生效；超时记
  `maintenance_failed.step="compaction_timeout"` 并返回 `timeout=True`，本轮**放行**
  （fail-open：与 `_compact` 内「单步失败不中断本轮」同语义）。预算降级压实复用同一上限。
- **D4 UI 契约**：`_EVENT_MAP` 显式登记两条事件（该表是 LoopEvent → SSE 的唯一契约面）；TUI
  `_format_event` 渲染 `上下文压缩中…` / `上下文已压缩（<ms>ms）`（超时追加「（超时放行）」）。
  Web / APP 对未知类型忽略，零改动。

**规格**：`llm-provider` **ADDED**「流式增量等待超时」（2 scen）；`loop` **ADDED**「流式中断留痕」
（3 scen）与「轮内压实进度与上限」（2 scen）。选用 ADDED 而非 MODIFIED 巨型 R1/R4：delta 聚焦、
不改写既有需求正文。`openspec validate --all` 32/0。

**测试**：新增 9 个用例 —— `test_llm_provider.py` 2（空闲超时 + 持续增量不误杀）、
`test_loop.py` 3（消费方关闭 / 执行异常留痕、正常轮无 `loop_aborted`）、
`test_loop_cost_observability.py` 2（进度事件 / 超时 fail-open）、`test_repl.py` 1（渲染文本）、
`test_ui.py` 1（契约表登记）。反证 4/4：摘队列超时 / 摘 `loop_aborted` / 摘两条事件 / 摘
`wait_for` 上限 ⇒ 对应用例红；复原 `md5sum` 一致。四门禁：`ruff check` / `ruff format --check`
绿、`pyright` 0 errors、`pytest -q` **2843 passed**。架构门 `test_control_flow_nesting_max_three`
促使把等待封装为 `_await_chunk`（`astream` 嵌套回到 3 层内）。

**局限**：① `wait_for` 只取消**等待**，工作线程无法强杀，超时后压实仍可能在后台写完
（记忆写回为追加型，与既有维护节拍并发假设一致）；② 流式超时**不重试**，长网断会直接本轮失败；
③ trace 仍为**轮末批量导出**，仅中断路径补封口，未做逐事件持久化；④ provider 线程中已入队的
增量在超时后可能继续产生（消费端已停止读取，队列随调用结束回收）；⑤ 会话复盘暴露的
「并行 tool_calls 只执行首个 / 重复 file_write / 非原子写入」属 P1，另 change 处理。

## ADR-0248：并行工具调用全量执行、重复抑制与原子写（change 0257 / 台账 E194）

**背景**：会话 `cb37aba3ddf54bcc9336be2464c95c07` 复盘在 P0（ADR-0247）之外确认三条 P1 缺陷：

1. **并行调用只执行首个**：planner 的 `_from_tool_calls` 直接取 `calls[0]`，其余原生
   `tool_calls` **静默丢弃**。模型发出批量调用后只看到一个结果，误判失败并在后续轮次重发。
2. **重复调用无抑制**：同一批次内完全相同的调用、以及相邻轮次完全相同的覆盖写，均会**重复执行**；
   与缺陷 1 叠加形成「写一次 → 误判 → 再写」的放大回路。
3. **覆盖写非原子**：`file_write` 以 `open("w")` 就地截断后写入。并发读者可能读到空文件 / 半截内容，
   进程中断则留下截断文件；写工具是模型最常用的副作用面，风险高于读类工具。

**决策**：

- **D1 动作组 `ActionGroup`**：`Action` 保持单工具协议不变（避免 20+ 处测试桩与消费方漂移）；
  新增并列类型 `ActionGroup(actions: list[Action])`。planner 仅在多调用时返回组（按 provider
  `index` 升序），单调用仍返回 `Action`。批次内任一调用参数非法（非 JSON / 非对象 / 缺函数名）
  ⇒ 整个批次归一为**单个**失败终止动作（`LLM_PLAN_PARSE_FAILED`），**零部分执行** —— 部分执行会
  让模型看到的工具结果与它发出的调用数量不一致，且无法可靠对应 call id。
- **D2 待执行队列**：循环维护 `pending`，组展开后逐个进入**既有单动作执行体**（中间件 → 确认门 →
  执行 → 观测回灌 → 事件 → 压实阈值）。每个动作仍推进轮次、逐动作受 `max_rounds` / 预算闸门约束。
  事件序为 N 组 `action_started` / `action_completed` / `step_completed`，**载荷键集不变**。
  单调用路径的推理 / 事件 / 观测逐字不变（`pending` 为空时才推理）。
- **D3 两层重复抑制**（只作用于**完全相同**的调用）：
  1. **批内**：键 = `(tool_id, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))`，
     保留首个，后续复用其结果；
  2. **轮内紧邻**：写动作（`tools.file_write` 非追加模式、`tools.file_patch`）与**上一条已执行
     动作**键相同且上次成功 ⇒ 跳过执行并复用结果；任何其他动作执行后重置「上一条」记忆（防止
     轮询 / 读取类重复被误杀）。
  被抑制的调用仍产出正常动作事件（`duration_ms=0`）、观测回灌与 `step_completed`，trace 增
  `action_deduplicated`（`scope="batch"|"turn"` / `tool_id` / `round`；**不含参数正文**）。
- **D4 覆盖写原子化**：`file_write` 覆盖模式在同目录创建 `.<name>.<uuid>.tmp`（`O_CREAT|O_EXCL`），
  写入后 `flush` + `fsync`，既有文件复制其权限位，再 `os.replace` 原子替换；任一步失败 ⇒ 清理临时
  文件并原样抛出，目标逐字不变。新建文件 0o666 经 umask 掩码，与 `open()` 一致；追加模式
  `open("a")` 不变；快照仍在写入成功后压栈，撤销语义逐字不变。

**规格**：`loop` **ADDED**「单次推理多工具动作」（4 scen）；`tool-use` **ADDED**「文件写入原子性」
（3 scen）。`openspec validate --all` 32/0（归档前）。

**测试**：`tests/test_parallel_tool_calls.py` 8 个（planner 非流式/流式全量映射、单调用保持 Action、
批次解析失败零执行、动作组逐动作执行、批内重复、轮内紧邻写重复、隔其他动作不抑制）；
`tests/test_tool_use.py` 3 个（原子覆盖无残留、替换失败目标不变且临时文件清理、权限位保留）。
反证 5/5：摘全量映射 / 摘组展开 / 摘批内去重 / 摘轮内去重 / 摘原子替换 ⇒ 对应用例红；复原
`md5sum` 一致。四门禁：`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、`pytest -q`
**2854 passed**。架构门「控制流嵌套 ≤3」促使把流式条目归一抽为模块级异步生成器
`_convert_reason_item`（早期 `elif` 链 + 内层循环达 4 层）。

**局限**：① 并行调用按 `index` **串行**执行，总时长为各调用之和（可预测优先，未做真并发）；
② 无依赖分析 —— 同一批由模型一次性给出，后一个调用看不到前一个的观测，批次执行不做中途重规划；
③ 抑制仅认**完全相同**的键：参数键序不同、路径写法不同（`~` / 绝对路径）均不抑制；
④ 原子性只覆盖 `file_write` 覆盖模式，`file_patch` 仍为读-改-写（可后续复用同一助手）；
⑤ 每次覆盖多一次 `fsync`，小文件写的相对开销上升；未 `fsync` 目录，跨崩溃目录项持久化不在本
change 范围；⑥ 去重键基于 planner 原始参数，中间件改写后的参数不参与比较。

## ADR-0249：命令执行进程治理与后台任务（change 0259 / 台账 E195）

**背景**：对比审查（2026-10-18）确认 `tools.code_run` 的超时语义与长命令能力存在两层缺陷：

1. **超时只取消等待，不终止进程**：handler 用 `asyncio.to_thread(subprocess.run, timeout=…)`；
   `ToolProvider.ainvoke` 外层 `asyncio.wait_for(timeout_s=60)` 只取消协程，工作线程与子进程继续运行；
   `subprocess.run` 的内层超时只杀直接子进程，**孙进程可逃逸**。上层收到 `TIMEOUT` 时命令仍可能
   在写文件。脚本层超时还被归为 `EXECUTION_FAILED`，与规格「超时 ⇒ 终止并返回超时错误」不一致。
2. **长命令不可用**：脚本超时缺省 10s、工具外层 60s，编译 / 测试 / 构建常被截断；没有后台执行，
   模型只能反复轮询短命令。接口文档长期列有 `tools.process`，但代码中**不存在**该工具。

**决策**：

- **D1 执行 seam `tools/execution.py`**（L1、仅 stdlib）：前景改用 `asyncio.create_subprocess_exec`；
  POSIX `start_new_session=True`（独立会话 / 进程组），Windows `CREATE_NEW_PROCESS_GROUP`。超时 /
  `CancelledError` 先终止进程树并回收直接子进程，再抛 `TimeoutError` ⇒ Provider 归一为 `TIMEOUT`。
  模块级 seam（`_create_subprocess_exec` / `_POPEN` / `_IS_WINDOWS`）供测试替换，不 patch 全局
  `asyncio`（既有 9+ 处 `subprocess.run` 替身随迁）。
- **D2 进程树终止**：POSIX `os.killpg(os.getpgid(pid), SIGKILL)`（`ProcessLookupError` /
  `PermissionError` 回退 `proc.kill()`）；Windows `taskkill /PID <pid> /T /F`，不可用则回退直接 kill。
  不引入三方依赖。
- **D3 超时口径**：`timeout` 缺省 **120s**、允许 `(0, 600]` 且须为有限数（`Validator` 只校验类型，
  区间在 handler 校验）；非法值结构化拒绝且**不启动子进程**。工具外层 `timeout_s=660` > 内层硬上限，
  外层只作兜底。
- **D4 后台执行**：`background=true` 立即返回 `pid` + 输出文件路径；stdout / stderr 合并写入
  `$CORE_STATE_DIR/run/<type>-<uuid>.log`（目录 0700、文件 0600），**不接受**模型指定输出路径。
  后台任务不随 loop 结束强杀，由 `tools.process_kill` 显式管理。注册表 `ProcessRegistry` 有界（32），
  插入前淘汰已退出项；全在运行 ⇒ 拒绝新任务（不杀活进程腾位）。**不存脚本正文**。
- **D5 进程工具拆两个**：`tools.process`（`list` / `status` / `output`；`process:read`、可逆 ⇒ 自动
  放行；`output` 只读注册表内 pid 的日志尾部，缺省 8K、上限 64K）与 `tools.process_kill`
  （`process:write`、不可逆 ⇒ 确认门）。拆两个是因为 `ToolDef` 只有**工具级** `reversible`：单工具
  `action=kill` 会让只读 status 也每次要求审批，或让 kill 绕过确认门。未知 pid 返回 `found=false`，
  不触达任意系统进程。
- **D6 权限分级**：把 `process` 加入 `PolicyEngine._READ_TOKENS`（否则 `tools.process` 落
  deny-by-default `HIGH_RISK`）；`process_kill` 先命中 `_HIGH_RISK_TOKENS` 的 `kill`，仍判
  `high-risk` —— 权限门与 SafetyGate 双层保护。
- **D7 组合根**：`builtin_tools()` 创建**一份**注册表并注入 `code_run` 与两个进程工具；不同
  `builtin_tools()` 调用（主子 Agent / 神兽 / 宠物）各自独立注册表，只能管理自己启动的任务。
  `runtime` 注册 `process:read` / `process:write` coeffect。

**规格**：`tool-use` **MODIFIED**「超时与资源上限」（+4 scen）、**ADDED**「后台命令执行与进程管理」
（6 scen）；`permission` **MODIFIED**「分级权限体系」（+2 scen）。`openspec validate --all` 31/0
（归档前）。

**测试**：新增 `tests/test_process_execution.py` 13 例（超时杀孙进程、取消杀树、TIMEOUT 归一、
非法 UTF-8 替换、timeout 越界 / NaN / inf 拒绝、POSIX 进程组、Windows creationflags / taskkill、
后台 pid + 0600 日志 + 巡检 + 尾部输出、kill 审批、未知 pid、注册表上界、工具声明）；适配
`test_tool_use.py` / `test_os_aware_shell.py` / `test_windows_run_completeness.py` 的执行 seam、
`test_permission.py` 分级、`test_phase13.py` 工具面集合。反证 3/3：摘进程树终止 / 摘
`start_new_session` / 摘 `process` 只读词元 ⇒ 各 1 红；复原 `md5sum` 一致。四门禁：`ruff check` /
`ruff format --check` 绿、`pyright` 0 errors、`pytest -q` 全绿。

**局限**：① 后台注册表仅进程内，重启后无法接管旧任务，日志文件不自动清理；② Windows 终止依赖系统
`taskkill`，不可用时回退 `proc.kill()`（仅直接子进程）；③ 超时返回不携带部分 stdout / stderr
（需要完整输出请用后台日志）；④ `tools.process output` 与前景 stdout 同口径，日志中的敏感文本可能
回灌模型（写记忆前仍经 `redact_secrets`）；⑤ 后台任务上限 32、无优先级 / 排队语义。

## ADR-0250：长任务默认值（change 0260 / 台账 E196）

**背景**：对比审查（2026-10-18）确认长任务的两个缺省值偏保守：`loop.max_rounds` 缺省 10 步，
真实编码闭环（读 → 改 → 测 → 看 → 修）稍有回环即撞上限；`orchestration.subtask_timeout`
缺省 0（不设限），卡死的子任务可无限占用调度槽。

**决策**：

- **D1 `loop.max_rounds` 缺省 10 → 20**：`configuration/manager.py::_DEFAULT_MAX_ROUNDS` 与
  `loop/default.py::DefaultLoop.__init__(max_rounds=...)` **同值**。后者是直接构造
  （beast / pet / UI 的 `DefaultLoop()`）的缺省；不同步会让「有配置源」与「无配置源」两条路径
  缺省分叉。token 预算派生、token 阀与校验上界（≥1 整数）逐字不变；`loop.compact_steps`
  缺省 6 仍 **< 20** ⇒ 压实步数维度仍可提前触发。
- **D2 `orchestration.subtask_timeout` 配置缺省 0 → 600 秒**：600s 覆盖多数编译 / 测试子任务，
  又给卡死任务一个上界。校验范围不变（≥0 的整数，`bool` 非法）；显式 `0` 仍合法，语义仍为
  「不设限」（`TaskScheduler` 侧 `> 0` 转 `deadline`，`0` 保留 `None`）。
- **D3 两处缺省口径有意不同**：`TaskScheduler(subtask_timeout: float = 0)` **保持 0** ——
  构造缺省表示「不注入即不改变既有行为」；生产由组合根 `build_runtime` 显式注入配置值
  （缺省配置下为 600）。缺省值变更只作用于配置面，不靠构造缺省扩散；直连调度器的调用方仍为
  不设限，该差异写入接口文档。
- **D4 规格同步、校验不变**：`loop`「错误与预算控制」与 `configuration`「循环预算配置」的缺省
  句与 Scenario 改 20；「编排调度配置」缺省句与 Scenario 改 600，并新增「显式 0 仍表示不设限」
  Scenario。ConfigSpec 三面 / 优先级链 / 校验上下界均不变。

**规格**：`loop` **MODIFIED** 1 req（+1 scen 缺省轮数放宽）；`configuration` **MODIFIED** 2 req
（循环预算 / 编排调度缺省值，编排 +1 scen 显式 0）。`openspec validate --all` 32/0（归档前）。

**测试**：缺省断言随迁移（`test_loop_budget_config.py` 16 处、`test_llm_config_hot_update.py`
5 处、`test_orchestration_config.py` 4 处）；新增 4 例：`DefaultLoop` 构造缺省与配置缺省同值、
配置层显式 `0` 仍不设限、组合根对显式 `0` 原样注入、`TaskScheduler` 构造缺省仍为 `0`。
全量基线 2872 → **2876 passed**。反证 3/3：还原 `_DEFAULT_MAX_ROUNDS=10` ⇒ 缺省用例红；还原
`_DEFAULT_ORCHESTRATION_SUBTASK_TIMEOUT=0` ⇒ 缺省与组合根注入用例红；还原
`DefaultLoop(max_rounds=10)` ⇒ 构造缺省用例红；复原 `md5sum` 一致（注：同秒内 `cp` 复原可能
命中陈旧 `.pyc`，反证后清 `__pycache__` 复核）。四门禁：`ruff check` / `ruff format --check`
绿、`pyright` 0 errors、`pytest -q` 全绿。

**局限**：① 20 / 600 是启发式缺省，未做真实任务成功率调优；② 轮数提高会放大单任务的最坏
token 消耗，token 预算仍独立生效，但「最坏耗时」没有同等硬上限；③ `TaskScheduler` 构造缺省
与配置缺省不同值，直连调度器的调用方不会获得 600s 保护（仅生产组合根注入）；④ 显式 `0`
关闭 deadline 的能力保留，用户可主动回到无界语义（有意）。

## ADR-0251：记忆检索质量离线基准（change 0261 / 台账 E197）

**背景**：对比审查（2026-10-18）确认记忆检索缺**质量回归门**。BM25 词法排序（change 0252）
此前只有零散「相关性顺序」单元测试，没有固定语料覆盖「当前事实 vs 陈旧事实」「跨会话」
「L2/L3/L4 混合」；排序公式或分词口径的任何改动都可能悄悄降低召回、让陈旧事实压过当前事实，
而现有测试不会红。引入真实 LLM / embedder 评测又带不确定性、成本与网络依赖，不能作常规门禁。

**决策**：

- **D1 固定合成语料 + 阈值门禁**：`tests/test_memory_quality.py` 内置 26 条条目（L2 当前事实 /
  L3 技能 / L4 归档 / 跨会话 / `source="bench.stale"` 陈旧冲突 / 诱饵）与 12 条带 gold 的查询。
  度量 **recall@5 ≥ 0.9**、**MRR@5 ≥ 0.7**、**stale_hits = 0**。阈值留 1 条查询的召回余量，
  不做分数逐位相等断言；变更语料或阈值视为**显式重定基线**，须记录原因，不得为变绿静默放宽。
- **D2 stale 口径按危害而非出现**：只在「陈旧条目排名**高于**对应当前 gold」时计一次
  `stale_hits`；陈旧事实未压过当前事实时出现在相关结果里是无害的。这比「stale 是否进 top5」
  更贴近真实风险。
- **D3 每条查询新建 store 重放**：`read()` 的 `_reinforce` 会改写 `reuse_count`，复用同一 store
  会让查询顺序影响后续排名。`FileBackend()` 无 path ⇒ 纯内存、不落盘。所有条目
  `ts=4_000_000_000`（未来时间戳）⇒ `recency_decay` 恒 `1.0`，消除时钟噪声；另以「两次独立
  重放 top-5 id 序列一致」钉住确定性。基准不依赖 embedder / 真实 LLM / 网络。
- **D4 不只靠词法排序验证陈旧隔离**：另加 `exclude_source_prefixes=("bench.stale",)` 用例，
  断言排除发生在排名与预算之前（change 0131 的既有机制），防止基准退化为「排序碰巧赢」。
- **D5 只建门、不改生产代码**：本 change 不新增生产路径、不改排序公式。若基准揭示缺陷，
  另立 change 修复；基准本身是后续记忆改动的回归门。

**规格**：`memory` **ADDED** 1 req「检索质量离线基准」（3 scenarios：基线达标 / 陈旧来源可排除 /
重放确定性）。`openspec validate --all` 32/0（归档前）。

**测试**：新增 `tests/test_memory_quality.py`（3 例）。基线 `recall@5=1.000 mrr@5=1.000
stale_hits=0`。全量基线 2876 → **2879 passed**。反证 4/4：① 摘除 `read()` 的
`exclude_source_prefixes` 过滤（`if exclude_source_prefixes:` → `if False:`）⇒ 排除用例红；
② 改坏 2 条 gold 内容 ⇒ recall `0.917`（仍在阈值内）但 `stale_hits=2` ⇒ 质量门红 —— 说明 gold
丢失会先以陈旧压过当前的形式暴露；③ 改坏 3 条 gold ⇒ recall `0.833 < 0.9` ⇒ 召回阈值红，
证明阈值本身可被触发；④ 互换 `c-pytest` / `st-pytest` 内容 ⇒ `stale_hits=1` ⇒ 红。复原后
`md5sum` 一致（store.py `ceb150fb…`、test 文件 `7f9d57ae…`）。四门禁：`ruff check` /
`ruff format --check` 绿、`pyright` 0 errors、`pytest -q` 全绿。

**局限**：① 合成语料只覆盖词法可分的英文 token，不度量中文长句、语义改写与 embedder 质量；
② 语料固定且基线满分（recall/MRR = 1.0），这是**回归门**而非质量上限，存在对固定语料过拟合的
风险（现实噪声查询可能更低）；③ 单 gold 查询无法度量多相关条目的排序质量，故不设
precision@5（单 gold 下上限仅 0.2）；④ recall 阈值留 1 条查询余量 ⇒ 单条 gold 丢失不会触发
召回红（但通常触发 stale_hits 红）；⑤ 未覆盖长任务端到端成功率（需真实模型与预算，另立评测）。

## ADR-0252：记忆检视与纠错 CLI（change 0262 / 台账 E198）

**背景**：记忆是核心资产，但运维面此前只有 `memory maintain` / `repair-keyfacts`：用户看不到
系统存了什么、取不出单条全文、也无法删除一条错误记忆。对比审查（2026-10-18）把「缺用户纠错面」
列为 P1 短板 —— 错误事实只能等自然遗忘（`_FORGET_THRESHOLD` 衰减），没有最直接的纠正手段。

**决策**：

- **D1 三个一次性子命令**：`memory list [--limit N]`、`memory get <id>`、`memory delete <id>`，
  与既有 `maintain` / `repair-keyfacts` 同构（装配 runtime → 一次动作 → 打印 → 退出），不启动
  常驻进程、不改变运行态。
- **D2 `list` 的 `--limit` 只限制展示**：底层 `audit(None)` 恒全量加载（冷热并集）；缺省 50，
  `0` = 全部，负数 / 非整数由 argparse 拒绝（退出码 2）。截断时输出「共 N 条」提示。字段顺序固定
  （id / layer / kind / source / session / importance / ts / 单行摘要），便于脚本与目视。
- **D3 `get` / `list` 输出经 `redact_secrets`**：先脱敏再截断（避免明文跨越截断边界），与
  「密钥只引用不读取、绝不进日志/记忆」同源；不打印 `reuse_count` / `updated_at` 等内部字段。
- **D4 删除「先备份、后删除」**：`discard` 的可逆效应随 CLI 进程退出即失效，故把条目 JSON
  **追加**到 `$CORE_STATE_DIR/memory-deleted.jsonl`（`O_APPEND` 单次写、0600，追加后尽力
  chmod 收紧）。备份写入失败 ⇒ **fail-closed**（一条不删、退出码 1）；未知 id ⇒ 退出码 1 且
  **不落备份**。不用「一份时间戳文件」：单条删除无整次操作边界，追加日志天然可累积、可人工重放。
- **D5 只读复用公开 API**：`audit(None)` + `discard`；不新增 `tools.memory` 工具面、不读私有
  `_all_entries`、不新增恢复子命令（沿用 `repair-keyfacts` 的备份先例）。

**规格**：`cli-ops` **MODIFIED**「运维命令集」（命令清单 + 3 scenarios：记忆检视 / 记忆删除 /
删除未知条目）。`openspec validate --all` 32/0（归档前）、31/0（归档后）。

**测试**：`tests/test_entry.py` 新增 6 例（list 字段与 limit、get 与未知 id、delete 备份 0600 +
条目消失、未知 id 不落备份、备份失败 fail-closed、密钥形态脱敏）。另因 `entry.py` 增行导致
`doc/03-interfaces/prompts.md` §1 落点行号漂移，已把 ⑭ 的 `entry.py:1689/1681` 同步为 `1810`
（`test_prompt_mirror.py` 的 34 例守护）。全量基线 2879 → **2885 passed**。反证 4/4：摘备份写入
⇒ 备份用例红；备份后不 `discard` ⇒ 条目消失用例红；`get` 不脱敏 ⇒ 脱敏用例红；未知 id 也写备份
⇒ 不落备份用例红；复原 `md5sum` 一致（`b9d841f5…`）。四门禁：`ruff check` / `ruff format --check`
绿、`pyright` 0 errors、`pytest -q` 全绿。

**局限**：① 无 `restore` 子命令，恢复靠备份 JSONL 人工重放；② `audit()` 全量加载，大库（数万条）
的内存与耗时未做分页；③ 运行中的实例不感知 CLI 删除，可能以内存快照短暂「复活」条目，重启后
一致；④ `--limit 0` = 全部，与「0 条」直觉相反（写入帮助文本）；⑤ 不做批量 / 按条件删除，避免
一次误删大面积记忆。

## ADR-0253：压实产出与丢弃的可观测计数（change 0263 / 台账 E199）

**背景**：`compaction` 成本事件（change 0253）只有 `trigger` / `elapsed_ms` / `steps`：能回答
「压实花了多久」，回答不了「这次消化了多少、产出了什么、丢了什么」。上下文压实后模型表现变差
或用户质疑「为什么这条信息没了」时，运维面缺少可比数字。对比审查（2026-10-18）把「压实丢弃
不可观测」列为 P1 短板。

**决策**：

- **D1 五项计数**：``compaction`` payload 增 `messages`（`len(ctx.messages)`）与压实产物的
  `conclusions` / `decisions` / `open_items` / `dropped` 列表长度。`_compact` 改为先取
  `compaction = compactor.compact(...)` 再 `persist(compaction, ...)` —— 原先内联在实参里，
  拿不到产物。
- **D2 失败语义**：`compact` 抛错 ⇒ 产物四项记 `0`（`messages` 仍为输入数）；`persist` 失败
  ⇒ 已取得的计数保留（失败只影响落盘，不影响「压出/丢了什么」）。事件次数、`trigger` /
  `elapsed_ms` / `steps` 与写回/终止语义逐字不变。
- **D3 不发 `kept`**：`messages - dropped` 不是「保留」口径 —— `dropped` 只统计**有 id 且
  `redundant=True`** 的冗余条目（生产中通常为空），消息是被摘要/结论**替换**而非逐条保留。
  发 `kept` 会让消费方误读「保留了多少条消息」。
- **D4 payload 红线不变**：只发计数，不发条目 id 或正文；不含摘要文本与会话标识。
- **D5 顶层 key 契约钉住**：测试断言 payload 顶层 key 集合恰为八个键（`trigger` /
  `elapsed_ms` / `steps` + 五项计数），防止未来误删既有键或漏发新键。

**规格**：`observability` **MODIFIED**「全链路日志」（payload + 五项计数、+1 scenario
「压实产出与丢弃计数」）。`openspec validate --all` 32/0（归档前）、31/0（归档后）。

**测试**：`tests/test_loop_cost_observability.py` 新增 3 例（计数与顶层 key 集、`compact` 抛错
全 0、`persist` 失败保留真实计数）。全量基线 2885 → **2888 passed**。反证 3/3：`dropped` 恒 0
⇒ 计数用例红；异常路径填非零默认 ⇒ 全 0 用例红；摘 `messages` 键 ⇒ key 集用例红；复原
`md5sum` 一致（`150cef8a…`）。四门禁：`ruff check` / `ruff format --check` 绿、`pyright`
0 errors、`pytest -q` 全绿。

**局限**：① `dropped` 仅统计 `Compaction.dropped`（有 id 的冗余条目），生产中通常为空；
② 不记录 token 前后量（需额外估算口径，且压实是替换而非删除）；③ `compact` 部分产出后抛错时
计数记 0（不反映部分产物，与「失败即无产物」的既有降级语义一致）。

## ADR-0254：工具面打磨（change 0264 / 台账 E200）

**背景**：对比审查（2026-10-18）把三处「静默降级 / 近似重复 / 有损截断」列为 P2 打磨项：
① `CheckpointStore._load` 只捕 `JSONDecodeError`，结构不符行（缺键 / 缺必需字段）会让
`Checkpoint(**record["checkpoint"])` 抛 `TypeError` / `KeyError`，**中断整份加载**；坏 JSON 行跳过
却无任何提示，用户不知道检查点丢了。② 重复调用抑制只按**逐字参数**判重：同一文件写成
`~/x` 与展开后的绝对路径、CRLF 与 LF 正文、省略 `mode` 与显式 `"w"`，都会被当作不同调用重复
写盘。③ `code_run` 输出截断只保留头部，而错误结论通常在**尾部**（traceback 末行、测试摘要），
模型看到的是「执行了但没说结论」的半截输出。

**决策**：

- **D1 损坏行告警一次、不阻断**：`_load` 逐行 `try` 覆盖 `json.loads` + `Checkpoint(...)` +
  `Snapshot(...)`，捕 `(ValueError, TypeError, KeyError)`（`JSONDecodeError` ⊂ `ValueError`），
  跳过并累计；加载结束后若有跳过项，发**一次** `UserWarning`（`stacklevel=2`），消息只含
  **跳过条数与文件名**，与 `FileBackend._load` 同口径。**不回显行内容**（可能含任务正文 /
  记忆 / 密钥）。合法行照常加载。不做损坏行落盘隔离 / 去重告警（见局限）。
- **D2 去重参数规范化只对文件写/补丁**：`_action_key` 先经 `_normalize_action_args` 得到参数
  **视图**再序列化；执行仍用原始 `action.args`。`path` = `expanduser → abspath → normpath →
  normcase`（Windows 折大小写 / 统一分隔符）；`content` / `old_content` / `new_content` 仅把
  `\r\n` 归一为 `\n`（纯 CR 不动）；`file_write` 省略 `mode` 视同 `"w"`，`"a"` / `"append"` 归一
  为 `"a"`（仍与覆盖写不同）。`code_run` / `web_fetch` **保持精确匹配** —— shell 字符串与 URL 的
  语义等价性不可靠，归一的风险高于收益（重定向、host 大小写、查询参数顺序、转义）。
- **D3 输出首尾保留**：新增 `_truncate_output(text, limit=8192)`；超限时头部 `budget // 3`、
  尾部其余，中间插 `\n…[truncated N chars]…\n`（N = 省略字符数，含标记自身预算）。总长
  **≤ 上限**（标记按最大位数预估，只会多留余量）。`stdout_truncated` / `stderr_truncated`
  判据不变（原始长度 > 上限）。仅 `code_run` **前景**结果；后台日志文件不截断
  （`tools.process output` 读尾部）。尾部权重 2/3 因为错误结论在尾部。

**规格**：`durability` **ADDED**「检查点加载损坏行告警且不阻断」（3 scen）；`loop` **MODIFIED**
「单次推理多工具动作」（+1 scen「文件写参数规范化去重」）；`tool-use` **MODIFIED**「内置原子工具
（代码执行 / 网页读取）」（+1 scen「长输出首尾保留」）。`openspec validate --all` 全绿（归档前/后）。

**测试**：`tests/test_durability.py` +2、`tests/test_parallel_tool_calls.py` +5、
`tests/test_tool_use.py` +2，净 **+9**（2888 → **2897**）。反证 4/4：P1 摘 `_load` 告警 ⇒
TC-THARD-01 红；P2 只捕 `ValueError` ⇒ 结构行冒泡 ⇒ TC-THARD-01 红；P3 摘规范化 ⇒
TC-THARD-03/04/05 红；P4 退化纯头截断 ⇒ TC-THARD-08 红；复原后 `md5sum` 一致
（`store.py 7c31f0d5…` / `default.py 3bf6864b…` / `builtin.py 0a1e47bf…`）。四门禁：
`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、`pytest -q` 全绿。

**局限**：① 路径归一用 `abspath`（依赖当前工作目录）：同一文件在不同 cwd 下的相对路径可能
判为不同；不做 inode / 符号链接 / 大小写不敏感文件系统的完整等价判定。② 不做 shell / URL
语义归一（有意）：`code_run` 的等价脚本、`web_fetch` 的等价 URL 仍可能重复调用。③ 截断标记的
N 是「省略字符数（含标记占用的预算）」，非精确尾部缺口；极端小 `limit` 下标记可能超上限
（生产常量 8192 不受影响）。④ 检查点损坏行只告警不隔离，重复启动会重复告警；不归档损坏行。

## ADR-0255：组内只读工具并发执行（change 0265 / 台账 E201）

**背景**：planner 的原生多 `tool_calls` 已全量进入 `ActionGroup`，但循环**逐个串行**执行；模型一次
请求读多个文件 / 查多个后台任务时，耗时是各动作之和。且 `ToolProvider._call` 在事件循环线程上
直接调用同步 handler —— 即使外层用 `gather` 发起，事件循环也被阻塞，「真并发」只对协程 handler
成立。

**决策**：

- **D1 并发资格只认工具声明**：`_is_concurrent_safe` 检查 `ToolDef.coeffects`，任何 coeffect 含
  `write` / `spawn` / `outbound` 词元即不并发；终止动作 / 无定义工具（fail-closed）不并发。
  `file_read`（`filesystem:read`）、`process`（`process:read`）、`context_read`（`[]`）可并发；
  `file_write` / `file_patch` / `code_run` / `gate_run` / `web_fetch` 一律串行。
- **D2 连续只读段 + 写屏障**：仅当**当前**动作可并发、无去重命中且键唯一时，才向后吸收
  `pending` 头部连续可并发动作；遇到写 / 副作用 / 未知工具立即停止，该动作留作下一轮串行执行
  （写序与撤销快照序不被并发打乱）。重复键也不吸收 —— 复用前一个结果需其**已提交**。
  吸收上限 = `max_rounds - ctx.rounds`，并发批次不越过轮次剩余额度。
- **D3 执行与提交分离**：去重 / 中间件 / 确认门**顺序**执行（确认门可能含人工审批，不能并发
  询问）；随后按原序发出全部 `action_started`（`round = ctx.rounds + i`），`asyncio.gather`
  并发执行（保留 `act_wrapper` 重试链与 per-action 会话 ContextVar），结果按**原序**提交
  （`action_completed` / 观察者 / 观测回灌 / 失败回滚 / `observe` / `step_completed`）。
  压实与预算在整批提交后判定一次。单动作路径与 `concurrent_reads=False` 时事件序逐字不变。
- **D4 同步 handler 卸载**：`ToolProvider._call` 对非协程 handler 用 `asyncio.to_thread`，
  协程 handler 仍在事件循环上 await。普通调用不再阻塞事件循环，多个 `ainvoke` 可真并发。

**规格**：`loop` **MODIFIED**「单次推理多工具动作」（+4 scen：只读并发 / 写屏障 / 按序提交 /
关闭开关）；`tool-use` **MODIFIED**「异步工具调用」（+2 scen：同步 handler 不阻塞事件循环 /
同步 handler 并发）。`openspec validate --all` 32/0（归档前）/ 31/0（归档后）。

**测试**：新增 `tests/test_concurrent_group_tools.py` 8 例，净 **+8**（2897 → **2905**）。
反证 4/4：P1 `_is_concurrent_safe` 恒 False ⇒ 并发用例红；P2 `_call` 退回内联调用 ⇒ 事件循环
阻塞 / 同步并发两例红；P3 `_is_concurrent_safe` 恒 True（摘屏障）⇒ 写屏障用例红；P4 提交逆序 ⇒
按序提交用例红；复原后 `md5sum` 一致（`default.py d48fd3a4…` / `provider.py c0b26b0a…`）。
四门禁：`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、`pytest -q` 全绿。

**局限**：① 并发仅限**同一组内连续只读段**；跨轮次 / 跨动作组的调度不做，单动作时无收益。
② `asyncio.wait_for` 无法终止已进入的工作线程：超时返回 `TIMEOUT` 后线程可能继续运行至返回
（Python 线程不可取消）；受影响的同步 handler 均为本地短操作（默认 `timeout_s=30`）。
③ 只读判定依赖插件如实声明 coeffects —— 声明为只读但实际有副作用的插件会被并发执行
（插件契约责任，非本层可验证）。④ 并发段执行早于其前置动作的压实：同一批内动作在压实前
已全部执行（批次语义）；对只读动作无副作用影响。

## ADR-0256：后台进程跨重启登记（change 0266 / 台账 E202）

**背景**：后台任务以 `start_new_session=True` 启动，core-agent 退出后仍在运行；但
`ProcessRegistry` 只存在于内存，重启后 `tools.process` 的 `list` / `status` / `output` 全部
查不到 —— 日志文件在磁盘上，模型却丢失 pid 与路径的唯一入口；也无法判断某 pid 是否仍是当初
启动的进程。

**决策**：

- **D1 元数据持久化**：注册表把 `pid` / `output_path` / `started_at` / `run_type` /
  `start_ticks` 整体写入 `$CORE_STATE_DIR/processes.json`（`O_CREAT|O_EXCL` 0600 临时文件 +
  `flush` + `fsync` + `os.replace`）。**不**记录命令 / 脚本 / 环境变量。落盘失败被吞掉
  （后台任务必须照常登记）；损坏文件按空注册表、非法条目跳过。
- **D2 启动时恢复**：`ProcessRegistry.__init__` 加载登记项为**恢复项**（`proc=None`），
  `list` / `status` / `output` 继续可用；`info()` 附加 `restored` 标记，退出码为 `null`。
  恢复条目按 `started_at` 保留最新 `max_jobs` 条，遵守注册表上界。
- **D3 存活与身份核对**：本进程任务看 `Popen.poll()`；恢复项用 `os.kill(pid, 0)` 判活
  （Windows 改 `OpenProcess` + `GetExitCodeProcess`，因 `os.kill(pid, 0)` 在 Windows 会
  `TerminateProcess`），Linux 再比对 `/proc/<pid>/stat` 的 starttime（字段 22）。starttime
  不符 ⇒ PID 已被复用，判为已退出；非 Linux / 读取失败时只凭存活判定。
- **D4 恢复项拒绝终止**：进程树终止依赖 `Popen` 句柄，重启后没有句柄；非 Linux 又无身份
  核对。故 `tools.process_kill` 对恢复项返回 `found=true` / `killed=false` /
  `restored=true`，**不触达**进程。终止能力仍仅限本进程启动的任务；注册表外 pid 仍
  `found=false`。

**规格**：`tool-use` **MODIFIED**「后台命令执行与进程管理」（+3 scen：重启后仍可巡检 /
PID 复用不误报 / 恢复项不可终止；另 +1 scen 持久化文件损坏不阻断）。
`openspec validate --all` 32/0（归档前）/ 31/0（归档后）。

**测试**：新增 `tests/test_process_persistence.py` 9 例，净 **+9**（2905 → **2914**）。
反证 4/4：P1 摘恢复加载 ⇒ 恢复 / 身份 / 上界等 6 例红；P2 摘身份核对 ⇒ PID 复用用例红；
P3 摘恢复项拒绝终止 ⇒ 恢复项 kill 用例红（`NoneType.poll` 归一 `EXECUTION_FAILED`）；
P4 改非原子直写 ⇒ 0600 / 原子替换两例红；复原后 `md5sum` 一致
（`execution.py 0d7c20dd…` / `builtin.py 9971c87e…`）。四门禁：`ruff check` /
`ruff format --check` 绿、`pyright` 0 errors、`pytest -q` 2914 passed。

**局限**：① 恢复项只读，**不可终止**；需要终止时用户须按 pid / `output_path` 自行处置
（保 `run_type` 不保命令，故无法自动重建）。② Windows 无 starttime 核对，恢复项只凭
`OpenProcess` 判活；PID 复用时可能误报 `running=true` —— 因拒绝终止，不会误杀。
③ 持久化为整体重写、假设**单写者**（生产只有一个注册表实例）；多实例共享同一
`CORE_STATE_DIR` 会互相覆盖。④ 落盘失败静默（该层无日志设施）；恢复项退出码恒 `null`。
⑤ 已退出的恢复项在下一次 `add` 淘汰时才从文件移除，`list` 会短暂保留（与既有内存注册表
行为一致）。

## ADR-0257：委托动作并发判级修正（change 0267 / 台账 E203）

**背景**：`tools.delegate` 的 coeffect 是 `agent:delegate`，不含 `write` / `spawn` /
`outbound` 词元。组内并发判定只看 coeffect 词元，故同批多个 delegate 被判为「只读」并
`gather` 并发执行；而子 Agent 可写文件、可执行命令。一旦并发，写序与撤销快照序不再由父
loop 的屏障保证，且子 Agent 写入不进入父 `EffectTracker`，无法按序撤销。

**决策**：

- **D1 词元补全**：`_CONCURRENT_DENY_TOKENS` 增加 `"delegate"`；`agent:delegate` 命中即
  视为有副作用，串行执行并作为并发批次之间的屏障。判定仍是声明式、fail-closed 的词元匹配。
- **D2 不以 `reversible` 作判据**：`reversible` 表达「效应能否撤销」而非「是否只读」；既有
  只读测试工具也常声明 `reversible=False`，该口径会误伤只读并发。未来跨边界能力应在
  coeffect 命名中沿用 `spawn` / `write` / `delegate` 词元。
- **D3 无运行时开关**：这是正确性修复，缺省即生效；`concurrent_reads=False` 仍可整体关闭并发。

**规格**：`loop` **MODIFIED**「单次推理多工具动作」（只读并发条件补 `delegate` 词元，新增
「委托动作作为屏障」场景）。`openspec validate --all` 32/0（归档前）/ 31/0（归档后）。

**测试**：`tests/test_concurrent_group_tools.py` 新增 1 例，净 **+1**（2914 → **2915**）。
反证：摘 `delegate` 词元 ⇒ 用例红（两个 delegate 重叠执行）；复原后 `md5sum` 一致
（`default.py 2d96a5e8…`）。四门禁：`ruff check` / `ruff format --check` 绿、`pyright`
0 errors、`pytest -q` 2915 passed。

**局限**：① 子 Agent 的写入仍**不进入**父 `EffectTracker`；本修复只保证串行（不发生并发
写乱序），不提供跨 Agent 的撤销归因。② 词元匹配是启发式：未来若新增跨边界 coeffect 而
未沿用既有词元，仍可能误判；须在新增工具时同步维护 deny 词元表。③ 仅约束同一
`ActionGroup` 内的批次；不同会话 / 不同 loop 实例之间的并发不受此判定管辖。

## ADR-0258：失败回滚可见性（change 0268 / 台账 E204）

**背景**：`DefaultLoop` 在动作失败时按 trace 整轮回滚，但 `ToolProvider.rollback` 返回的
`RollbackReport` 被丢弃：模型只看到失败动作的 `error`，不知道先前成功写入已被撤销；规格
「单轮回滚」已写明「并写遥测」，实现却没有任何回滚事件。模型可能基于「文件已写入」的错误
世界状态继续规划。

**决策**：

- **D1 保留 trace 整轮回滚**：规格承诺「回到该轮开始前状态」；缩窄为只撤销失败动作会留下
  半完成写入。本 change 只增加可见性，不改回滚范围。
- **D2 返回报告**：`DefaultLoop.rollback(trace_id) -> RollbackReport | None`，提交循环捕获。
- **D3 遥测**：非空报告（`reverted` 或 `undo_failed`）记 `kind="trace_rolled_back"`，
  载荷键恰为 `reverted` / `undo_failed` 计数；不含 EffectId、路径、参数、错误正文。
  走 `Tracer` 而非新增 `LoopEvent`，`astream` 七类事件契约不变。
- **D4 观察回灌**：失败动作的 tool observation 在非空回滚时附加
  `rollback: {reverted, undo_failed}`；空回滚不出现该键。回滚先于观测回灌，模型看到失败
  结果时世界状态已回退。
- **D5 撤销失败**：留在既有 QUARANTINE 账目，不自动重试 / 删除；计数告知模型与遥测。

**规格**：`loop` **ADDED**「失败回滚可见性」（3 scen）。`openspec validate --all` 32/0
（归档前）/ 31/0（归档后）。

**测试**：新增 `tests/test_rollback_visibility.py` 3 例，净 **+3**（2915 → **2918**）。
反证 3/3：P1 `rollback` 丢弃报告 ⇒ 2 例红；P2 观测不注入回滚 ⇒ 2 例红；P3 不产事件 ⇒
2 例红；复原后 `md5sum` 一致（`default.py eb910c0f…`）。四门禁：`ruff check` /
`ruff format --check` 绿、`pyright` 0 errors、`pytest -q` 2918 passed。

**局限**：① 模型只看到**计数**，不知道具体哪些路径被撤销（避免把路径/参数写进遥测）；
② 整轮回滚可能撤销模型本想保留的成功写入 —— 这是既有原子轮语义，本 change 只让它可见；
③ 终止动作失败没有 observation（无可续轮次），只有遥测；④ 撤销失败不自动重试，需人工
按账目介入；⑤ `trace_rolled_back` 只经 `Tracer`，消费方未订阅导出器时不可见。

## ADR-0259：钩子实现（change 0269 / 台账 E205）

**背景**：ADR-0155 只交付钩子**契约**（change `0164`：规格 + 模块文档 + 设计稿，零 `src/` 改动）。
实现在台账 **E101** 挂了近一年：没有 `src/core/hooks/`；loop 缺 `turn.before` 注入点；`middlewares` /
`action_observers` 只接受同步返回值，异步钩子无法消费；`MemoryStore` 无写入观察者；配置面无
`hooks.*`；YAML 解析器不支持块序列 ⇒ `hooks.entries` 连声明都不成立。操作者要挂一条策略仍须改
Python 代码并重打包。

**决策**：

- **D1 复用既有接缝，不建总线**（承 ADR-0155 ①）：`tool.before` → `middlewares`；
  `tool.after` → `action_observers`；`turn.after` → 新增 `turn_after` **同步**注入点
  （trace 封口**前**，钩子遥测随本轮导出；后台 `turn_observer` 保持「封口后异步收尾」）；
  `turn.before` / `session.*` / `memory.write` → 新增注入形参（loop 构造参 / 组合根适配器 /
  `MemoryStore(write_observer=)`）。loop 与 memory **不 import** hooks。
- **D2 可等待中间件**：`Middleware` / `ActionObserver` 的返回值 MAY 为 coroutine，loop 逐个
  `await`；同步实现（不返回可等待对象）与引入前**逐字等价**。这是钩子能消费既有接缝的前置条件，
  也是唯一改动既有接缝语义的点 —— 由「返回值类型放宽」而非新分支实现。
- **D3 before / after 分治**：`before` 类（`turn.before` / `tool.before`）退出码非 0 或回调返回
  `False` ⇒ 阻断（`tool.before` 走既有「已拒绝」终止语义）；异常 / 超时 / `OSError` 按 `on_error`
  处置，缺省 `block`（fail-closed）。`after` 类一律只留痕，不改本轮结局。
- **D4 安全边界**：子进程 argv 启动（不经 shell）、**白名单环境**（不继承父进程密钥）；
  载荷出进程前逐条 `redact_payload`（正则密钥形态 + `register_secret` 登记明文 → `<redacted>`），
  单串截断 4096；`tool.*` 只给长度 + 哈希前缀；子进程 stdout / stderr **丢弃**（不进日志 / 记忆 /
  对话）；trace 只记事件名、命令 basename、退出码、时长、`blocked_by`。
- **D5 不可逆（显式例外）**：钩子副作用不进 `EffectTracker` —— 这是系统「一切副作用可逆」的
  **唯一显式例外**，规格明示。
- **D6 声明面**：三个标量（`hooks.enabled` / `timeout_s` / `on_error`）走 `ConfigSpec` 三面；
  `hooks.entries` 只从 `config.yaml` 结构化段读；`enabled` 缺省 **false**；`timeout_s` 硬上限 60s
  （超限截断 + 告警）。
- **D7 YAML 子集扩展**：解析器 / 转储器补**块序列**与**行内 flow** 列表 / 映射，使 `hooks.entries`
  可声明且 `write_patch` 重写后 **round-trip 保真**；锚点 / 多文档 / 块标量仍不支持（见局限⑦）。
- **D8 会话生命周期**：`session.start` 由 `turn.before` 适配器**首轮幂等**触发；`session.end`
  由 `HookManager.close()`（`atexit` 注册）对每个活跃会话投递一次。
- **D9 trace 归因**：`astream` 期间设 `current_trace_id` ContextVar，钩子 trace 落在当前轮；
  无活跃 trace（`session.*`）⇒ 临时 `hook.<event>` trace 后立即封口。生成器在**另一上下文**
  关闭时 `Token.reset` 抛 `ValueError`，降级为原地清空（该上下文随即结束，不丢本轮遥测）。

**规格**：`hooks` **MODIFIED**「钩子形态与接缝」（`turn.after` 改挂同步注入点）、`loop` **MODIFIED**
「横切中间件插入」（+可等待语义、+轮首注入点可否决、+终止动作不触发观察者）。`openspec validate --all`
32/0（归档前）/ 31/0（归档后）。

**测试**：新增 `tests/test_hooks.py` **20 例**（事件面 / 摘要 / 脱敏 / 阻断 / 只留痕 / 超时
`on_error` / 环境白名单 / 输出不回灌 / 三层优先级与超时截断 / YAML 块序列与 round-trip /
非法条目跳过 / 会话幂等 / 记忆不可否决 / 组合根开关 / 四个 loop 接缝）。净 **+20**
（2918 → **2938**）。反证 3/3：P1 摘 `_dispatch_before` 阻断分支（`continue`）⇒
`test_tool_before_hook_blocks_execution_and_traces_blocked_by` 红；P2 `_hook_env` 返回完整父环境 ⇒
`test_subprocess_does_not_inherit_secret_env` 红；P3 `redact_payload` 直通 ⇒
`test_turn_payload_redacts_registered_and_shaped_secrets` 红。复原后 `md5sum` 一致
（`manager.py 1ac7541d…` / `executor.py 75e3d106…` / `model.py 679d36c8…`）。四门禁：
`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、`pytest -q` **2938 passed**。

**局限**：① **同步阻塞语义** —— `asyncio.to_thread` 只把子进程搬离事件循环，同一事件的多个钩子
按声明序**串行**，`timeout_s` 累加，慢钩子拖慢每一轮；② `session.end` 依赖 `atexit`，`SIGKILL`
/ 崩溃时不投递；③ `memory.write` 观察者**同步**执行在写入路径上；④ 钩子副作用不可逆（契约例外）；
⑤ 无并行 / 权重 / 否决覆盖；⑥ `hooks.entries` 只走 `config.yaml`；⑦ YAML 解析仍是子集实现
（块序列 / 行内 flow / 标量；锚点、多文档、块标量 `|` / `>` 不支持）；⑧ `turn_after` 在 trace
封口前执行 ⇒ 慢钩子延迟本轮遥测导出。

## ADR-0260：后台子 Agent、完成通知与模型侧任务清单（change 0270 / 台账 E206）

**背景**：`tools.delegate` 只有**阻塞**语义 —— 子 Agent 跑完前主循环不能推进；结果只在本轮
工具结果里可见，跨轮后**彻底丢失**；模型无法自检「刚才派出去的任务怎么样了」。对照
claude-code 的「后台任务 + 完成推回」，core-agent 缺三件事：非阻塞派发、下一轮可见的完成通知、
只读任务清单。

**决策**：

- **D1 注册表归 L4**：`BackgroundAgentRegistry` 放 `core/orchestration/background.py` —— 管理的是
  **子 Agent 的 loop**（跨边界能力），不是 OS 进程；与 L1 的 `ProcessRegistry` 语义分离。
  组合根在主工具面注册 `tools.tasks`；子 Agent 的 provider 由 `_agent_tools()` 独立构造，
  **结构上**既无 `tools.delegate` 也无 `tools.tasks`。
- **D2 完成通知走轮首独立块**：`LoopContext.notices` + `DefaultLoop(notices_consult=...)`
  （入参 = 会话标识），planner 出「后台任务通知：」独立块。**不**新增 `LoopEvent`（UI 可见 ≠
  模型可见），**不**写记忆（瞬态协调信号不是知识）。缺省 `None` ⇒ 零调用、`notices` 恒空、
  提示词**逐字不变**。
- **D3 一次性 + 按会话**：`drain_notices(session_id)` 取走即清；`tools.tasks` 只读状态、
  **不**清空通知。两条消费面分离。
- **D4 有界**：运行中任务 8（超限结构化拒绝、不排队）；每会话待投递通知 32（丢最旧）；
  单轮渲染 10 条 / 单行 400 字符；单任务回复保留 4000 字符。
- **D5 终态与失败面**：`running → done | failed | cancelled` 不可逆；子 Agent 异常只记
  **异常类型名**（不回传任意异常正文）；`LoopResult.failed=True` ⇒ failed；取消同步落终态并
  仍产生通知。注册表强引用 `asyncio.Task` 直至终态（避免「异常从未取回」告警）。
- **D6 权限：字面量工具 id 豁免**：`PolicyEngine` 对 `tools.tasks` 精确判 read；**不**把
  `tasks` 加入只读词元（否则未来含该词元的动作会静默降级，破坏 deny-by-default）。
- **D7 默认行为不变**：`background` 缺省 false ⇒ 阻塞路径逐字不变；无新配置键、无新依赖；
  `tools.tasks` 因 `task:read` 不在 `_DEFAULT_EXPOSED_COEFFEXTS` 而**不**进 MCP 默认暴露面。

**规格**：`orchestration` **ADDED**「后台委托与完成通知」（7 scen）、`loop` **ADDED**「轮首通知注入」
（3 scen）、`permission` **MODIFIED**「分级权限体系」（+字面量 `tools.tasks` 豁免 +2 scen）。
`openspec validate --all` 32/0（归档前）/ 31/0（归档后）。

**测试**：新增 `tests/test_background_agents.py` **21 例**（立即返回 / 终态 / 异常不泄正文 /
取消留痕 / 上限与名额回收 / 通知一次性 / 会话隔离 / 每会话上界 / 渲染上界 / `notices` 缺省 /
取用入参与降级 / planner 独立块与逐字锚 / 块序 / `background` 工具路径 / 超限结构化失败 /
缺省阻塞不变 / 清单含未知 id / 清单不清空通知 / 权限字面量豁免 / 子 Agent 不可见）。
净 **+21**（2918 → **2959**）。反证 4/4：P1 `_delegate` 忽略 `background` ⇒ 立即返回用例
**挂起超时**（`timeout 15` 退出码 124，非通过）；P2 `drain_notices` 不取走 ⇒ 一次性用例红；
P3 通知按空串而非会话键 ⇒ 会话隔离 + 后台委托用例红；P4 planner 摘通知块 ⇒ 注入用例红。
复原后 `md5sum` 一致（`runtime.py 46cd1763…` / `background.py 292f8301…` /
`planner.py ec13d1cf…`）。四门禁：`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、
`pytest -q` **2959 passed**。

**局限**：① **纯进程内** —— 不落盘、不跨重启恢复、不跨会话唤醒，进程退出即在途任务随事件循环
取消（注册表提供 `cancel_all`，组合根当前未注册关闭钩子）；② **无轮内推送** —— 通知只在该会话
下一轮轮首投递，运行中只能靠 `tools.tasks` 主动查；③ **上限为进程级**（不按会话）—— 单个会话
可占满 8 个名额，其余会话得到结构化拒绝；④ 通知**取走即丢** —— `drain_notices` 后本轮若异常
终止，该通知不再重投；⑤ 任务文本 / 回复仅在内存且有界（回复 4000 字符，清单返回同界截断）；
⑥ **取消不回滚**子 Agent 已产生的副作用（可逆性仍归效应追踪）；⑦ `tools.tasks` 不进 MCP
默认暴露面，外部 MCP 客户端不可查；⑧ 后台子 Agent 继承发起会话标识（与前台委托一致），
其记忆写入与主会话同维度；⑨ `background` 无排队 / 优先级 / 重试语义。

## ADR-0261：语义检索默认化（端点推导 embedding 模型，change 0271 / 台账 E207）

**背景**：记忆 / RAG 的语义检索此前是**显式配置才启用** —— `llm.embedding_model` 为空时组合根
不注入 embedder，`MemoryStore` 恒走词法、RAG 用 `HashEmbedder` 降级基线，CLI 每次启动打印
「语义检索未启用」。真实配置常不写该键（例如智谱端点 `open.bigmodel.cn` 明明提供 `embedding-3`）
⇒ 能力默认不在场，原因不是模型不支持，而是要求用户知道并手写一个与聊天模型无关的模型名。

**决策**：

- **D1 推导放在有效配置属性，不回写字段**：新增 `LLMConfig.embedding_auto`（缺省 `true`）与只读
  `effective_embedding_model`。口径：显式 `embedding_model` 非空 ⇒ 恒用它；否则开关开启 ⇒
  端点表推导；否则空。`embedding_model` 字段仍表示「用户写了什么」——`_merge_patch` 热更新基线
  取显式值 ⇒ 换端点后推导自动跟随，旧端点推导值不会被固化成用户声明。
- **D2 确定性端点表**：新 `configuration/embedding_models.py`，四行有据可查的 OpenAI 兼容端点
  （`api.openai.com` / `open.bigmodel.cn` / `dashscope.aliyuncs.com` / `api.siliconflow.cn`），
  按主机名**精确或子域**匹配（大小写不敏感、允许省略 scheme）。未命中返回空 = **不猜**；
  不启动 `/models` 探测（无网络、无启动延迟、测试确定性）；不引入本地语义模型（沿用既有裁决
  语义走 `LLMEmbedder`）。表无配置键面 ⇒ 不是第二真源；显式配置永远胜出。
- **D3 开关与非法取值**：`llm.embedding_auto` 进 `ConfigSpec` 三面（`--llm.embedding-auto` /
  `CORE_LLM_EMBEDDING_AUTO` / yaml `llm.embedding_auto`），缺省 `true`；取值口径与 feature flag
  同集，非法值在 `_build_config` 当场 `raise ConfigurationError`（`bool("maybe")` 为真会静默开启）。
  关闭开关 = 逐字保留旧行为（词法 / `HashEmbedder` / 启动提示）。
- **D4 单一有效模型、两条通路共用**：组合根以 `effective_embedding_model` 构造既有单一
  `embed_provider`：记忆走 `batch_embed(LLMEmbedder)`、RAG 走 `LLMEmbedder`；为空 ⇒ 不注入 /
  `HashEmbedder`。不新增 provider、不改 `MemoryStore` / `RagService` 契约。
- **D5 提示**：CLI `_build_ui` 按有效值判断 —— 空 ⇒ 既有词法提示；仅推导 ⇒ 一次
  「按端点自动选用 <model>（可用 llm.embedding_model 覆盖）」，不回显 endpoint / 密钥；
  显式配置 ⇒ 无额外提示。`_rag` 的降级提示同样改看有效值。

**规格**：`configuration` **MODIFIED**「LLM 提供商配置（必选）」（+`embedding_auto` 子项、
+4 scen，保留原「未配置 embedding 模型回退词法」）；`memory` **MODIFIED**「温度分层检索」
（启动提示改按有效值，+2 scen）；`rag` **MODIFIED**「本地 Embedding」（+1 scen）。
`openspec validate --all` 32/0（归档前）/ 31/0（归档后）。

**测试**：新增 `tests/test_semantic_default.py` **21 例**（端点表精确/子域/大小写/无 scheme/
未知/边界；有效值显式优先、开关关闭、未知端点；配置三面 + 非法阻断 + 热更新不固化；
组合根推导注入 / 开关关闭 / 显式优先 / 未知端点 / 推导不可达降级），`tests/test_entry.py`
**+3 例**（推导提示 / 开关关闭回词法 / 显式无推导提示），并调整 `test_rag_wiring` 维度失配用例
显式钉住未知端点配置（不再依赖用户 HOME 配置）。净 **+24**（2959 → **2983**）。
反证 3/3：P1 `effective_embedding_model` 推导分支返回 `""` ⇒ 6 例红；P2 摘开关判断 ⇒ 4 例红；
P3 入口仍取显式字段 ⇒ 推导提示用例红。复原后 `md5sum` 一致（`models.py 28018332…` /
`entry.py 175d4395…`）。四门禁：`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、
`pytest -q` **2983 passed**。

**局限**：① 端点表**静态**：新端点/新模型名需改表；未命中只退回词法、不报错；② 推导模型
**不验证可用性**：首次检索若 404/超时，记忆按既有 `_embed_failed` 短路降级、RAG 按调用期
降级，启动不阻断但首轮可能有一次失败网络往返；③ 代理/自建网关无法识别端点语义 ⇒ 不推导；
④ 推导开启后首次语义检索产生远端调用与费用（`llm.embedding_auto=false` 可关）；
⑤ 有效值属性不参与 `config show` 的字段展示（仍显示显式值）；⑥ 端点表按主机名匹配，CDN /
网关域名若与官方主机不同名则不命中。

## ADR-0262：工具参数按需注入（change 0272 / 台账 E208）

**背景**：主工具面从「内置七件」增长到十五件以上：内置原子工具（含后台进程管理）、
`tools.gate_run`、`tools.context_read`、`tools.delegate`、`tools.install` /
`tools.uninstall` / `tools.list`、`tools.tasks`，加上 MCP 端点动态注册的工具。每一轮推理请求
都把**全部**工具的完整参数 schema 随请求发送，而单轮通常只用其中两三个 —— 工具 schema 是
每轮固定成本，工具越多越贵，且挤占上下文预算。

**决策**：

- **D1 只过滤请求侧 schema，不动注册面**：`ToolProvider.active_tools()` 仍是全量真源；收窄
  只发生在 `LLMPlanner._tool_schemas(ctx)` 生成的 `LLMRequest.tools` 副本。参数校验 / 权限 /
  coeffect / 确认门 / 撤销 / 去重全部继续看全量集合 —— `auto` **不是访问控制**；文本 JSON
  动作路径调用未注入 schema 的工具照常执行。
- **D2 两个 scope 与阈值**：`loop.tool_scope` 取值 `all` | `auto`（缺省 `auto`）。`all` =
  恒注入全部（kill-switch，与引入前逐字一致）。`auto` 在「已注册工具数 > 8 且
  `tools.schema_read` 已注册」时只注入核心集 + 本回合已加载 + `schema_read`；否则回落全量
  （小工具面免加载；不得造出模型无法加载参数的不可达工具面）。阈值 8 = 核心集 7 +
  schema_read 1 ⇒ 子 Agent（内置七件）/ 宠物（白名单）天然全量，无需按 loop 类型分叉。
- **D3 核心集**：`file_read` / `file_write` / `file_patch` / `code_run` / `web_fetch` /
  `context_read` / `delegate` —— 判据是「几乎每轮都可能用」；按需集是情境触发型
  （进程管理 / 门禁 / 插件 / 任务清单 / MCP）。
- **D4 `tools.schema_read`**：可选 `tool_ids` 数组；无参列全量目录（id + 描述），有参返回
  `description` + `parameters`（参数 schema 放进工具观察，文本 JSON 动作路径的模型也能读到），
  未知 id 记入 `unknown` 不阻断。`coeffects=["schema:read"]`、`reversible=True` ⇒ 权限分词命中
  `read` 词元、只读放行。catalog 用闭包 `tools.active_tools`（调用时真实注册面，含 MCP）。
  只挂主工具面（子 Agent / 神兽 / 宠物不注册、也不需要）。
- **D5 加载吸收与生命周期**：`LoopContext.loaded_tools`（回合内集合）。循环在动作提交阶段、
  `observe` 之前把 `schema_read` **成功**请求的已注册 id 吸收进去，**下一轮**请求即携带其
  schema；集合随 `perceive()` 新建上下文包而清空（不写记忆、不跨会话）。吸收放循环而非工具：
  `schema_read` 是 L1 工具，不感知 `LoopContext`；只有循环知道回合边界。
- **D6 系统提示**：目录（id + 描述）**不收窄**；`auto` 生效时追加一行
  「未注入参数 schema 的工具，先调用 tools.schema_read 获取参数（下一轮生效）」；`all` 不产
  该行（提示词逐字不变）。这是模型行为的唯一提示，成本远低于被裁掉的 schema JSON。
- **D7 配置与缺省分工**：`loop.tool_scope` 进 ConfigSpec 三面（`--loop.tool-scope` /
  `CORE_LOOP_TOOL_SCOPE` / yaml），缺省 `auto`；非法值校验期阻断启动。**构造缺省分叉是故意的**：
  `LLMPlanner(tool_scope="all")` 是库级保守缺省（既有直接构造的调用方零变化）；生产主 planner
  由组合根显式注入 `config.tool_scope()`。`all` 同时是产品面 kill-switch。

**规格**：`loop` **ADDED**「工具参数按需注入」（9 scen）；`configuration` **ADDED**
「工具注入范围配置」（3 scen）；`tool-use` **ADDED**「工具参数查询」（3 scen）。
`openspec validate --all` 32/0（归档前）/ 31/0（归档后）。

**测试**：新增 `tests/test_tool_scope.py` **23 例**（配置三面 / 归一 / 非法阻断；auto 收窄 /
all 全量 / 构造缺省 / 小工具面 / 无 schema_read 回落 / 已加载可见 / 目录不收窄与说明行；
吸收后下一轮可见且新回合重置 / 未知 id 不吸收；schema_read 列表 / 按 id + unknown / 权限只读；
组合根 auto 接线 / all 接线）；`tests/test_phase13.py` 生产工具面断言补 `tools.schema_read`；
`doc/03-interfaces/prompts.md` 两处 planner 常量落点随行号更新（55→91、72→108）。
净 **+23**（2983 → **3006**）。反证 4/4：P1 摘过滤 ⇒ 2 例红；P2 忽略 `loaded` ⇒ 2 例红；
P3 摘吸收 ⇒ 1 例红；P4 忽略 scope ⇒ 2 例红（all / 构造缺省）。复原后 `md5sum` 一致
（`planner.py e20e0902…` / `default.py 74f76844…`）。四门禁：`ruff check` /
`ruff format --check` 绿、`pyright` 0 errors、`pytest -q` **3006 passed**。

**局限**：① `auto` 缺省改变主 loop 的请求形状：依赖原生 tool_calls 的模型在加载前**不能**
直接调用按需工具（机制本身；文本 JSON 动作路径不受限）；② 每次按需加载多一轮模型往返 ——
单轮只用核心集时净省 token，反复加载多工具时可能更贵；③ 核心集是静态启发式（同 embedding
端点表）：任务长期以 `gate_run` / MCP 为主时需 `tool_scope=all` 或后续扩核心集；④ 已加载集合
按回合重置 ⇒ 多轮长任务每回合重新加载；⑤ 系统提示目录不收窄 ⇒ 工具数极多时目录本身仍有成本；
⑥ `schema_read` 输出不设条目上限（模型可一次请求全部 schema，属自伤性入参）。

## ADR-0263：里程碑报告锚定（change 0273 / 台账 E209）

**背景**：长任务的早期硬约束会丢 —— 会话摘要在后续压实中被稀释（ADR-0208③）、零复用记忆约
19 天被归档 L4（ADR-0170③）。仓内已有「常驻（pinned）笔记」通道（整篇纳入 / 逐轮无条件 /
紧随宪法块 / 优先级决定在场 / 超预算整篇排除且可见），但**置位靠人**：人工 `notes pin`，或
`notes promote`（只搬运会话摘要，不装配决策与硬约束，且显式触发才常驻）。结果就是 PA-08 的
现象：**忘了 pin** 等于硬约束没锚住，而 `promote` 的产物也不含结构化的「关键决策 / 硬约束 /
关键事实」。

**决策**：

- **D1 复用 pinned 通道，不造第二个注入块**：里程碑产出只是一篇普通 canonical note
  （`pinned=True` + 高优先级），注入路径零改动。第二条注入通道会造成两套预算、两处 prompt
  位置、两套在场判定 —— 风险大于收益。「永久置顶」由此落地为「常驻块内最靠前」。
- **D2 确定性装配、零 LLM**：固定节次序「结论 → 关键决策 → 硬约束 → 关键事实」，空节省略。
  来源可组合：显式条目（保持调用方次序）、该会话压实摘要（并入结论节）、该会话 keyfact
  （`key_fact` 标签 + `session:<id>`，按 `id` 升序 ⇒ 确定性）。不做模型归纳。
- **D3 身份与来源守护**：`note_id = "milestone-" + slug_topic(<name>)`，`--as` 显式覆盖；
  同 id 重复收口走 `NoteStore.update()`（唯一写路径）幂等覆盖。目标撞上来源非
  `notes.milestone` 的既有笔记且未给 `--as` ⇒ 返回空、不写盘、非零退出（与 promotion 同构）；
  显式 `--as` 视为授权。既有 tags 并入产出、标题缺省沿用既有。
- **D4 有界与脱敏**：所有装配内容经 `redact_secrets`（承 ADR-0141① 密钥红线）；正文上限
  `MAX_MILESTONE_CHARS = 3000`（< 常驻总预算 4000），**保留头部**并留含被截字符数的标记。
  上限作用于装配后的正文，单条超长输入无法绕过。
- **D5 缺省优先级 100**：高于人工 `notes pin` 的缺省 0，表达「阶段硬约束优先于一般常驻笔记」；
  `--priority` 可覆盖（含 0）。`unpin` 语义逐字不变（清常驻并归零）。
- **D6 CLI 面**：`notes milestone <name> [--session SID] [--as ID] [--title T] [--priority N]
  [--conclusion T]... [--decision T]... [--constraint T]...`。成功回执退出 0；无可写内容 /
  派生 id 为空 / 来源冲突 ⇒ stderr 报明确原因、退出 1、**不写任何文件**。`--session` 无摘要
  不报错（keyfact 与显式条目仍可成文）。
- **D7 显式触发裁决（C 维持否决）**：阶段结束判定不可靠（loop 无阶段实体；编排进度事件是执行面
  状态），自动写入未 review 的内容并逐轮注入与 ADR-0142①（notes 是刻意知识）和 ADR-0141①
  （常驻内容密钥红线）冲突。本 change **仅**提供显式动词；自动置常驻仍须显式翻案。

**规格**：`notes` **ADDED**「里程碑报告锚定（milestone anchoring）」（9 scen）。
`openspec validate <change>` 通过（归档前）；`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_notes_milestone.py` **8 例**（结构 / 幂等 / 摘要与 keyfact 装配且
确定性 / 空内容 / 空 slug / 来源守护与 `--as` / 脱敏与有界 / 优先级次序）；
`tests/test_entry.py` **4 例**（CLI 落盘与 show 读回 / `--session` 装配 / 空内容非零 /
usage 列出动词）。净 **+12**（3006 → **3018**）。反证 5/5：摘来源守护 / 摘脱敏 / 摘截断 /
忽略优先级 / 摘空内容守卫 ⇒ 对应用例均红；复原后 `md5sum` 一致
（`milestone.py 2c355d86…`）。四门禁：`ruff check` / `ruff format --check` 绿、
`pyright` 0 errors、`pytest -q` **3018 passed**。另：`entry.py` 行号漂移更新
`doc/03-interfaces/prompts.md` ⑭ 落点（1820 → 1836）。

**局限**：① 阶段划分仍靠人/上层**显式**调用，系统不推断「里程碑已结束」；② 无模型归纳 ——
报告质量取决于输入与既有 keyfact（确定性是有意取舍）；③ 3000 字符上限保留头部 ⇒ 超长里程碑
**尾部**被截，详细内容应另行成篇；④ 常驻总预算 4000 不变 ⇒ 本篇在场可能使其它常驻笔记被
整篇排除（`notes pinned` 可查）；⑤ `--session` keyfact 只取带 `session:<id>` 标签者，跨会话 /
全局 keyfact 不入报告；⑥ 报告只经 pinned 通道 —— `unpin` 后不再每轮注入（显式语义，非缺陷）。

## ADR-0264：M4 长任务 token 增长基准（change 0274 / 台账 E210）

**背景**：产品 M4 写明「长任务 token 增长随任务数呈**次线性**（记忆外置生效）｜衡量方式：
**基准任务序列测量**」，但该基准在仓内**不存在** ⇒ M4 既不可证伪也不可证实（PA-10）。
记账口径已在 `0152` / ADR-0144 修对：`LLMPlanner.last_prompt_tokens()` 取「装配全量估算」与
「provider 实报」的较大者，覆盖系统提示、摘要块、历史与工具 schema，可直接作为逐轮探针。

**决策**：

- **D1 最小 harness（PA-10 选项 B）**：新增 `tests/test_m4_token_growth.py`，在**同一会话**内
  以固定任务序列（24 轮，用户 240 字符 / 桩回复 480 字符，等长载荷）驱动真实 `DefaultLoop`
  （`LLMPlanner` ＋ 桩 provider ＋ 本地有界摘要器），逐轮采集 `last_prompt_tokens()` ⇒
  输出曲线与最小二乘斜率。**不设绝对阈值、不入门禁**（选项 C 未采纳，阈值另行裁决）、
  不做真模型长跑（选项 D）。
- **D2 对照组而非「无记忆」**：线性基线 = 同一循环、同一序列，但关闭摘要器与维护节拍
  （`maintenance_interval=0`）且 `history_turns=count` ⇒ 全量原文回灌。比较的是
  「外置 vs 全量回灌」，不是「有记忆 vs 无记忆」。
- **D3 确定性三件套**：注入**步进时钟**（每轮 +1s ⇒ 维护节拍确定性触发）；桩 provider 从当前
  用户消息派生等长回复（无调用计数耦合）；摘要器替身保留合并内容尾部 600 字符（模拟**有界**
  模型摘要输出 —— 无界拼接会让摘要自身线性膨胀，属替身缺陷）。
- **D4 判据是机制性相对量**：远期（窗口与摘要到界后）逐轮占用**恒定**（末 8 轮
  `max - min == 0`）；外置整体斜率 < 线性基线斜率；末轮占用 < 基线末轮；两次重放曲线逐值
  一致。绝对 token 阈值留待独立裁决。
- **D5 零 `src/` 改动**：基准只消费既有探针与三层滑窗；若揭示膨胀缺陷，另立 change 修复。

**实测**（本机，固定常量）：外置曲线在**第 12 轮**到界后恒为 `7771` tokens；线性基线逐轮
`+624`，末轮 `14840`。整体斜率 `292.19` vs `624.00`，远期斜率 `0.00`。数字随常量与估计器
口径变化，属**相对增长**证据而非绝对成本。

**规格**：`loop` **ADDED**「长任务 token 增长基准」（4 scen）。`validate <change>` 通过
（归档前）；`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_m4_token_growth.py` **2 例**（次线性判定 / 重放确定性）。
净 **+2**（3018 → **3020**）。反证 2/2：① 临时让 `_load_summaries` 恒返回 `("", "")`
⇒ 外置曲线退化为 20 轮全量回灌、远期饱和判据红；② 临时让 `_estimate_prompt` 只估算最后一条
消息 ⇒ 两条曲线同时变平、斜率严格比较红。复原后 `md5sum` 一致
（`default.py 74f76844…` / `planner.py e20e0902…`）。四门禁：`ruff check` /
`ruff format --check` 绿、`pyright` 0 errors、`pytest -q` **3020 passed**。

**局限**：① 合成文本以中文为主，token 估计器口径与真实模型 tokenizer 不同 —— 测的是**同一
口径下的相对增长**，不是绝对成本；② 摘要替身不模拟真实 LLM 摘要的信息损失，只验证「有界
外置」结构性质；③ 24 轮、单一任务形态不覆盖工具调用轮（多步 ReAct）与会话交错；④ 无绝对
阈值 ⇒ 曲线整体抬升（性能退化）不会被本基准单独抓住，只能由「远期不饱和 / 斜率不低于基线」
这类结构性崩坏触发；⑤ 维护节拍按轮强制触发（`maintenance_interval=1s` + 步进时钟），
生产 15 分钟节拍下早期窗口更易线性增长 —— 本基准是**机制上界**而非生产时序复刻。

## ADR-0265：记忆检索规模基准（1 万条，PA-09 方案 B）（change 0275 / 台账 E211）

**背景**：PA-09 点名的检索面缺口（无分区权重 / 无图 / 缺省降级 / 循环内查不到向量库）都以
「先能证明优化有效」为前提，但仓内只有 `0261` 的 **26 条**排序语义基准；产品
CORE-NFR-PERF2 写明「记忆检索延迟 < 100ms（1 万条事实规模）」，却没有任何 1 万条规模的测量
文件。于是「万条后是否漂移」「是否满足性能目标」均不可判定 —— 这正是 PA-09 选项 B 的动因。

**决策**：

- **D1 固定 1 万条语料**：`_fact(i)` 确定性生成（L2 80% / L3 10% / L4 10%、`ts=0`、
  `source="bench"`），每条带唯一 ASCII 锚点 `zqNNNNN`；20 条带 gold 的查询（每 500 条取一）。
  写入内存 `FileBackend`，不落盘、不触网。
- **D2 准确率门禁**：recall@5 ≥ 0.9、MRR@5 ≥ 0.7（与 `0261` 同口径；两者互补 —— 0261 管
  **排序语义**，本基准管**规模稳定性**）。实测 recall@5 = 1.000、MRR@5 = 1.000。
- **D3 延迟只报告、不设产品门禁**：逐查询计时并输出中位 / p95 / max。产品目标
  「<100ms」**只对照**；断言仅设宽松回归上限 `p95 < 5000ms`（产品目标的 50 倍），抓
  「整体恶化一个数量级」。理由：当前实现**未达标**，若把 100ms 写成断言，基准一落地即红，
  无法区分「回归」与「既有缺口」。
- **D4 确定性**：语料生成无随机源、无时钟；两次独立生成逐条比较 `(id, layer, content)`；
  查询集固定。检索强化只改被选中条目的 `reuse_count`，唯一锚点使 gold 恒居首 ⇒ 同 store
  顺序执行的 recall/MRR 可复现。
- **D5 零 `src/` 改动**：方案 B 明确「无产品行为改动」；本 change 只建立可测性。

**实测（本机 WSL2，Python 3.11）**：20 条查询，recall@5 = **1.000**、MRR@5 = **1.000**；
延迟中位 **657.4ms**、p95 **771.9ms**、max **795.5ms** —— **未达 CORE-NFR-PERF2 的 100ms**。
cProfile 显示单次 `read()` 约 **78%** 时间在 `_truncate` 对全部 1 万候选逐条调用
`estimate_tokens`（`0245` 的 CJK 逐字符判定）；BM25 统计与排序占比小。⇒ 修复方向明确
（按条目缓存 token 估计 / 预计算），但**不在本 change**（方案 B 零行为改动），应另立 change。

**规格**：`memory` **ADDED**「检索规模离线基准（1 万条）」（3 scen）。`validate <change>`
通过（归档前）；`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_memory_scale_benchmark.py` **2 例**（规模与准确率 / 语料确定性），
约 20s。净 **+2**（3020 → **3022**）。反证 1/1：临时把 `MemoryStore.read` 的排序改为升序 ⇒
recall@5 = 0、用例红；复原后 `md5sum` 一致（`store.py d4676280…`）。四门禁：
`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、`pytest -q` **3022 passed**。

**局限**：① 唯一 ASCII 锚点让查询近乎唯一可检索 —— recall/MRR 验证**规模下的排序稳定性**，
不验证语义 / 改写召回（属选项 E）；② 单机 wall-clock 受负载影响，跨机器不可直接比较；
③ 未覆盖并发读、embedder 路径、L1 路由与真实会话混合负载；④ 全量测试增加约 20s（未标
slow，仓内无 slow 标记约定）；⑤ 延迟缺口已知但未修：本基准只保证「不继续恶化一个数量级」。

**后续（未在本 change 实施）**：① **检索延迟修复**（`_truncate` / token 估计缓存）——
建议优先于 PA-09 C；② PA-09 **C 分区加权**（`tags` / 来源三档）；③ D 图 / E 真语义须各自
独立裁决（E 与零三方依赖红线对账）。

## ADR-0266：记忆检索延迟修复（1 万条中位 <100ms）（change 0276 / 台账 E212）

**背景**：`0275` 的 1 万条基准首次把 CORE-NFR-PERF2（「<100ms / 1 万条」）变成数字：
本机中位 **657.4ms**，**未达标**。实测分解（10k 条、单次 `read`）：`estimate_tokens`
≈323–546ms（逐字符 Python `any()` 遍历 7 个 CJK 区间）> `tokens` 全量重分词 ≈89ms >
BM25 统计 ≈104ms（含分词）> 排序 ≈21ms。两处热点都**不承载检索语义**，属纯实现开销。

**决策**：

- **D1 `estimate_tokens` 换计数方式、不换口径**：把 `_CJK_RANGES` 同源编译为一个正则字符类，
  `cjk = len(text) - len(_CJK_PATTERN.sub("", text))`（C 层执行）；删除逐字符 `_is_cjk`。
  输出与 `0245` 的逐字符判定**逐位一致**（区间边界等价测试守护）；所有调用方（memory 读预算、
  context 预算、orchestration handoff）只获得速度。10k 条估算 ≈546ms → **39ms**（≈14×）。
- **D2 词元缓存：按内容校验、有界 FIFO**：`MemoryStore` 持 `_token_cache`
  （`id → (content, frozenset[token])`），`build_lexical_stats` 增可选 `token_cache`
  （缺省 `None` ⇒ 与 `0252` 逐字一致）。内容未变复用词元集；同 id 覆写内容 ⇒ 校验失败重新
  分词；不缓存 `reuse_count` 等时变字段。上界 `_TOKEN_CACHE_MAX = 20_000`（1 万目标的 2×），
  溢出按插入序 FIFO 淘汰。
- **D3 语义零变化**：不改 BM25 公式、分词规则、层权重、排序与 `_truncate` 的「跳过放不下者」
  语义；缓存只改变**分词频次**。结果由既有 3022 用例 + 基准 recall/MRR 1.000 逐条守护。
- **D4 门禁口径**：产品目标仍**只报告**（跨机/负载波动），基准回归上限由 `p95 < 5000ms`
  收紧为 **`p95 < 1000ms`**（参考机修后 ≈125ms，约 8× 余量）。`estimate_tokens` 的速度不由
  单测挂钟反证，口径由区间边界等价钉住；缓存行为由确定性用例反证。

**实测（本机 WSL2，同一 10k 语料 / 20 查询）**：

| 版本 | 中位 | p95 | recall@5 / MRR@5 |
|---|---|---|---|
| `0275` 基线 | 586.6ms | 695.9ms | 1.000 / 1.000 |
| + 快速 `estimate_tokens` | 221.9ms | 289.4ms | 1.000 / 1.000 |
| + 词元缓存（第二次起） | **83.3ms** | 109.3ms | 1.000 / 1.000 |
| 最终基准单跑 | **85.8ms** | 125.5ms | 1.000 / 1.000 |

⇒ 参考机**中位已满足 <100ms**；p95 略高于目标（首查/系统噪声），故不作跨机硬门禁。
首次检索（缓存冷）仍约 220ms —— 缓存收益自第二次检索起，这是有意取舍（不持久化缓存）。

**规格**：`memory` **MODIFIED**「检索规模离线基准（1 万条）」（延迟口径 + p95 上限）＋
**ADDED**「检索词元缓存（有界、按内容失效）」（3 scen）。`validate --all` **31/0**（归档后）。

**测试**：`tests/test_token_estimate.py` +1（区间边界等价）；新增
`tests/test_memory_token_cache.py` **3 例**（复用 / 内容变更失效 / 有界）；基准上限收紧。
净 **+4**（3022 → **3026**）。反证 2/2：① `read` 不传缓存 ⇒ 复用用例红；② 去掉内容校验
（只按 id 命中）⇒ 失效用例红；复原后 `md5sum` 一致（`store.py` / `relevance.py`）。
四门禁：`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、
`pytest -q` **3026 passed**（约 202s；基准自身由 ≈20s 降至 ≈8s）。

**局限**：① 缓存收益依赖重复检索，冷启动首读仍约 220ms；② 缓存为进程内存、按 store 实例
归属，跨进程/重启不共享；③ 排序阶段仍对全部候选 `rank`（≈21ms）与 BM25 idf 统计（≈15ms），
未做候选预裁剪以免改变召回面；④ 20k 上界对 1 万目标足够，语料远超 2× 时 FIFO 会抖动；
⑤ 挂钟数字受负载影响，跨机不可直接比较；⑥ `estimate_tokens` 提速覆盖所有调用方，行为不变
但属共享热路径改动，今后改 CJK 区间须同步测试侧区间表。

**后续**：PA-09 **C 分区加权**可在本基线上直接评估收益；D 图 / E 真语义仍须各自独立裁决
（E 与零三方依赖红线对账）。更远的候选预裁剪 / 持久化索引不在本 change。

## ADR-0267：记忆内容分区权重（tags 三档）（change 0277 / 台账 E213）

**背景**：PA-09 C（检索质量之「分区」）。`0275`/`0276` 之后检索已可在 1 万条规模下测量且延迟达标，
但 `relevance` 只有两维：`0.5·sim + 0.2·layer_priority`。`layer_priority` 是 **L0–L4 稳定度**轴，
**不是内容重要性轴** ⇒ 过程日志（`transcript`/`log`）与关键决策 / 里程碑同权。蓝图要求
「里程碑区权重拉满 / 关键决策区次之 / 过程日志区最低」。用户在 PA-09 C 裁决中选定
**tags 约定**口径（而非 source/kind 推断）。

**决策**：

- **D1 加性、居零三档**：`relevance = 0.5·sim + 0.2·layer_priority + 0.15·tier`，
  `tier ∈ {+1, 0, −1}`，系数 `_W_TIER = 0.15`。加性项与 `layer_priority` 同量纲，不改变
  `rank = relevance × recency × (1+log1p(reuse)) × (1+importance)` 的结构。
- **D2 标签约定**：高档 `{"milestone", "decision"}`；低档 `{"log", "transcript"}`；其余（无标签 /
  未知标签）默认档。**精确、区分大小写**（约定小写）⇒ `"Milestone"` 不生效、未知标签不意外降权；
  同时命中高低档 ⇒ **高档优先**（宁可多留不可漏掉）。只看 `tags`，不从 `source` / `kind` 推断。
- **D3 默认开启、无配置开关**：用户裁决。默认档**零偏移** ⇒ 未分档条目得分与分档前逐位相同，
  既有检索语义不变。
- **D4 初版默认档 `+0.075` 已证伪（评审内实测）**：`rank` 的乘性调制会放大任何非零常量偏移。
  1 万条基准中高复用填充项（`reuse_count` 经多轮检索累积）反超 gold，**recall@5 由 1.000 降至
  0.45**。改为 `{+1, 0, −1}` 后未分档条目零偏移，recall/MRR 回到 1.000。这是「加性项必须居零」
  的直接反证，写入规格。
- **D5 接口口径订正**：`memory-interface.md` 原称「`rank` / `_decay_score` 完全不看 tags」。
  现 `rank` 会读取 `tags`，但**仅**用于四个档位标签的精确匹配；`_PRESERVE_TAGS = {"failure"}`
  的压实排除面与 `_decay_score` 不受影响。

**实测（本机 WSL2）**：

| 基准 | 结果 |
|---|---|
| `0261` 检索质量（26 条 / 12 查询） | recall@5 = 1.000、MRR@5 = 1.000、stale_hits = 0（不变） |
| `0275` 1 万条规模（20 查询，三次单跑） | recall@5 = MRR@5 = 1.000；中位 **108.3 / 85.8 / 92.3ms**，p95 157.2 / 124.9 / 132.2ms |

⇒ 两个基准的准确率**逐项不变**，延迟与 `0276` 基线（85.8ms）同一水平（波动为机器负载）。

**规格**：`memory` **ADDED**「内容分区权重（tags 三档）」（4 scen：三档定序 / 冲突与未知 /
同档排序不变 / 基准不回退）。`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_memory_tiers.py` **4 例**（三档定序含权重差 / 冲突与未知与大小写 /
同档层优先级不变 / `MemoryStore.read` 端到端定序）；`test_memory_lexical_scoring.py` 数值不变
（默认档零偏移），仅更新注释。净 **+4**（3026 → **3030**）。**反证 3/3**：① 摘掉 tier 项 ⇒
三档定序红；② 低档先于高档判定 ⇒ 冲突用例红；③ 未知标签落低档 ⇒ 定序用例红；复原后
`md5sum` 一致（`relevance.py`）。四门禁：`ruff check` / `ruff format --check` 绿、
`pyright` 0 errors、`pytest -q` 3030 例（其中 `test_ui_turn_cleanup` 在全量并发下为既有时序
抖动，单跑 6/6 通过，与本 change 无关）。

**局限**：① 收益取决于写入方**显式打标**；现有库与全部既有基准语料均无这四个标签 ⇒ 落默认档、
基准无法体现收益，收益仅由单测覆盖；② 四个标签名写死在代码里，扩展档位须改代码（用户裁决的
无配置口径）；③ `milestone` 与 notes 模块的笔记 tag 同名，但笔记不是 `MemoryEntry`，两域独立；
④ 加性权重只破接近的并列，高相关低档条目仍可排在高相关高档之上（相关性优先，有意）；
⑤ 低档条目 `relevance` 可为负（`0.5·0 + 0.12 − 0.15 = −0.03` 起步），排序语义正常但分值不再
全为非负；⑥ 标签纪律缺失时不会退化 —— 默认档零偏移保证了这一点。

## ADR-0268：未完成任务自动续跑（change 0278 / 台账 E214）

**背景**：长任务无人值守的最后一处编排运维缝。启动扫描（`entry._surface_incomplete`）自
change `0191` 起按 durability「崩溃恢复」只**呈现**未完成任务（`task --resume <id>`），不自动
重执行 —— 进程崩溃/重启后需要人或外部 watchdog 手动续跑。对比 Claude Code 的长任务运维面，
「重启后自动接着跑」是缺的一环；而 `FAILED` 在调度器内是终态，同一进程无法原地重试，所以
自动续跑必须跨进程有界。

**决策**：

- **D1 显式 opt-in，默认零变化**：新配置 `orchestration.auto_resume`（缺省 `false`）。关闭时
  启动面维持「纯扫描 + 呈现」逐字不变；开启只影响 `core-agent task` 入口，`serve` / TUI /
  `mcp serve` 仍只呈现（不跨事件循环共享调度器）。配置开关即显式授权，不违反 durability
  「续跑由调用方显式触发」的既有裁决。
- **D2 跨进程有界**：同一任务最多 **3** 次自动尝试；第 n 次尝试后等
  `min(60·2^(n-1), 3600)` 秒（首次 60s，随后翻倍，封顶 1h）。尝试**执行前**记账（进程中途崩溃
  也消耗次数，保守），成功清零，失败保留检查点等待下次启动退避重试。状态落
  `$CORE_STATE_DIR/auto-resume.json`：仅 `task_id → {attempts, last_ts}`，原子写 + `0600`，
  不含任务正文 / 记忆 / 密钥；损坏 ⇒ 告警后按空状态处理；已消失任务在扫描时清退。
- **D3 重建与人工 `--resume` 同源**：`Runtime.pending_resumes()` 只读检查点，每任务取**时间戳
  最新**的可读快照，重建 `TaskResume`（plan / 已完成子集 / 交接回复 / 会话标识）；跳过
  `done=true`、`turn.` 前缀或 `kind=turn`、计划缺失（告警）与快照全损坏（告警）者。告警只报
  task id。
- **D4 执行位置**：仅 `task` 入口，串行 `asyncio.run(astream)`，与 `task --resume` 同一流式管线；
  进度事件照常打印。自动续跑在起新任务**之前**执行。
- **D5 显式入口不受限**：`task --resume-all` 续跑全部未完成任务，忽略配置开关、退避与次数上限
  （运营商显式重试）；仍记录尝试并在成功时清零。`--resume-all` 为独立模式，不与 `<目标>` /
  `--resume` 组合。
- **D6 人工入口不受状态影响**：`task --resume <id>` 不读取 `auto-resume.json`，达上限后仍可用。

**反证 3/3（均实测转红后复原，`md5sum` 一致）**：① 摘掉 `_task_resumes` 的 `done` 过滤 ⇒
已完成任务被列入续跑，重建用例红；② `AutoResumeState.due` 恒 `True`（摘退避/上限）⇒
指数退避与耗尽用例红；③ 入口改为无条件 `_run_auto_resume`（摘默认关判断）⇒「默认关闭仍续跑」
用例红。

**规格**：`orchestration` **ADDED**「未完成任务自动续跑」（4 scen）；`configuration` **MODIFIED**
「编排调度配置」（新键 + 校验）；`durability` **MODIFIED**「崩溃恢复」（显式 opt-in 例外）。
`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_auto_resume.py` **13 例**（配置三面/默认关/非法值阻断；退避-耗尽-
清零-`retain`-损坏容忍；`_task_resumes` 最新快照/跳过 done·turn·坏计划/会话占位值/全损坏告警；
`--resume-all` 执行与空扫描；新任务前自动续跑；默认关不执行；上限后自动跳过但 `--resume-all`
强制；失败保留尝试）。`tests/test_entry.py` 桩补 `config` / `pending_resumes`（默认关）。
净 **+13**（3030 → **3043**）。四门禁：`ruff check` / `ruff format --check` 绿、`pyright`
0 errors、`pytest -q` **3043 passed**。

**局限**：① **无跨进程运行锁** —— 两个进程同时 `task` 可能同时续跑同一任务（与既有
`task --resume` 同）；② 上限（3 次 / 退避曲线）为**常量非配置**，永久性配置错误会在 3 次内
反复失败后静默（告警仍可见），需人工介入或删状态文件；③ 状态文件按文件系统权限保护，不加密；
④ 只在 `task` 入口自动执行，`serve` / TUI / `mcp serve` 仍需人工 `task --resume`；⑤ 重建取
最新快照的 `done` 判定与 `_recover_incomplete` 的「任一快照 done 即完成」历史口径不同 ——
自动续跑与人工 `--resume` 一致（最新态即真态），故两处扫描口径**有意分叉**；⑥ 不做守护
进程 / cron / systemd 集成。

## ADR-0269：后台子 Agent 跨重启登记与重入队（change 0279 / 台账 E215）

**背景**：change `0270` 的后台委托注册表只在进程内：进程重启后 `tools.tasks` 清空，用户/模型
既看不到「哪些后台任务随重启被中断」，也无法重新入队。对比报告把「后台任务跨重启可见」
列为 P0 长任务缺口；`ProcessRegistry`（change `0259`）已为 OS 后台进程建立了「元数据落盘 +
重启可见」先例，子 Agent 侧需要同等基座。

**决策**：

- **D1 生产始终登记、注册表默认纯内存**：runtime 以
  `BackgroundAgentRegistry(state_path=$CORE_STATE_DIR/background-tasks.json)` 构造；
  `state_path=None`（缺省）⇒ 不读写文件，既有直接构造与全部既有测试零变化。与
  `ProcessRegistry` 同口径：**元数据登记**不改变执行语义、不放宽权限，故不设配置开关；
  有后果的动作（重入队）由独立工具 + 审批门控制。
- **D2 有界原子登记**：`{"version": 1, "tasks": [...]}`，最多保留最新 **64** 条；写入用同目录
  临时文件 + `fsync` + `os.replace`，`0600`；写失败告警一次（仅本进程内有效），不阻断主循环。
  加载遇坏 JSON / 结构不符 ⇒ 告警一次并按空登记处理；单条非法记录跳过。运行中上限仍是 8，
  `interrupted` 不占名额。
- **D3 字段与脱敏**：落盘 `task_id / agent_id / task / status / started_at / finished_at /
  session_id / error`；`task` 与 `error` **写读两侧**都经 `redact_secrets` 并有界
  （120 / 200 字符）。`session_id` 落盘以恢复重入队归属，但不进 `info()`（对模型不可见）。
  **不落 `reply`**：完成结果已由完成通知投递，避免子 Agent 输出正文长期留在状态文件。
- **D4 重启映射**：加载时 `running → interrupted`（`finished_at=None`，
  `error="进程重启导致中断"`）。该状态是终态：不可取消（无在途 `asyncio.Task`）、不重放完成
  通知（否则每次启动都会重复提醒），可见性由 `tools.tasks` 提供。
- **D5 重入队 `tools.task_retry`**：只接受 `interrupted / failed / cancelled`；`running`
  （仍在执行）与 `done`（已完成）结构化拒绝；按登记的任务正文**重新路由**子 Agent（不按
  `agent_id` 直接取 loop，配置可能变化），`spawn` 新任务并返回新 `task_id`，恢复原会话归属；
  达到运行中上限返回 `BACKGROUND_TASKS_FULL`。工具词元 `{task, retry}` 不命中只读/写词元 ⇒
  `HIGH_RISK`（审批门），coeffect `task:write` 显式注册、`reversible=False`；只挂主工具面。

**反证 3/3（均实测转红后复原，`md5sum` 一致）**：① 加载映射改为保留 `running` ⇒ 重启可见性
用例红；② 摘掉 `_info_record` / `_restore_info` 的 `redact_secrets` ⇒ 密钥 canary 落盘用例红；
③ 摘掉 `done` 状态守卫 ⇒ 已完成任务被重入队，用例红。

**规格**：`orchestration` **ADDED**「后台任务跨重启登记与重入队」（6 scen）。
`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_background_persistence.py` **12 例**（终态跨重启恢复 + 0600 +
不落 reply；无路径纯内存；损坏容忍；条目有界；密钥脱敏；`running → interrupted` 且不占名额/
不可取消/不重放通知；失败任务重入队新 id + 会话归属 + 原终态不变；running/done/未知 id 拒绝；
重入队容量上限；跨重启使用脱敏正文；runtime 只挂主工具面；词元判 `HIGH_RISK`）。
`tests/test_phase13.py` 工具清单补 `tools.task_retry`。净 **+12**（3043 → **3055**）。
四门禁：`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、`pytest -q`
**3055 passed**。

**局限**：① 多进程共用 `CORE_STATE_DIR` 时，另一进程启动会把本进程运行中的任务误标
`interrupted`（单用户 CLI 视为重启；跨进程运行锁不在本 change 范围）；② 登记最多 64 条，
被淘汰任务不再可查/可重入队；③ 重启后不恢复 `reply`，`tools.tasks` 的 `reply` 为空是预期；
④ 跨重启重入队使用脱敏后的任务正文，密钥形态子串会被 `REDACTED` 替换（原值本就不应入状态
文件）；⑤ 状态文件按文件系统权限保护，不加密。

## ADR-0270：无人值守 profile（整任务时限/预算 + 允许面 + 失败通知）（change 0280 / 台账 E216）

**背景**：长任务无人值守（CI / 定时 / 无人在屏前）需要三样东西：① 无人审批时的**放行面不能
无限**——`auto-approve` 当前全放行，一次误配置即把全部 coeffect 交给模型；② 任务可以**跑飞**
（墙钟无限、token 无限）；③ 失败**无人知晓**。三项都不引入新权限模式，而是在既有
`auto-approve` 上组合可关闭的旋钮，缺省值逐字保持引入前行为。

**决策**：

- **D1 profile 即组合，不新增模式**：无人值守 = `permission.mode=auto-approve` +
  可选 `permission.auto_approve_coeffects` + 可选 `orchestration.task_timeout` /
  `task_token_budget` + 可选 `orchestration.failure_notify_file`。四项缺省 `"" / 0 / 0 / ""`
  ⇒ 全部关闭；不改变 `serve` / TUI / 编程式调用的语义（墙钟只在 CLI `task` 入口施加）。
- **D2 允许面严格全含、只在 auto-approve 生效**：`PermissionModeGate.authorize` 在
  `AUTO_APPROVE` 顶部短路内、放行前检查**声明的全部** coeffect ⊆ 白名单；任一越界 ⇒
  `PERMISSION_DENIED`（fail-closed，不回落确认门）。空串/未配置 = `None` = 不限制（空集合与
  `None` 等价，避免「配了空值 ⇒ 全拒」的意外锁死）；其他模式**完全不看**该配置。
  条目形态 `namespace:action`（小写字母起头，`[a-z0-9_-]`），yaml/env/CLI 三面同源解析，
  逗号（含全角）分隔、去重。
- **D3 墙钟在入口而非调度器**：`entry._run_task_stream` 用
  `asyncio.wait_for(_stream_task(...), timeout)` 包住**完整任务流**，覆盖 fresh、`--resume`、
  自动续跑与 `--resume-all`。理由：`serve` / TUI / 编程式消费方不应被静默设限，墙钟是
  「无人值守会话」的策略，属于入口。超时 ⇒ `TASK_TIMEOUT`：打印、写通知、退出码 1；
  调度器 `astream` 的 `finally`/`_release` 照常保留最近波次检查点 ⇒ 可 `--resume` 续跑。
  `0` = 不设限。
- **D4 token 预算在调度器、按记账口径**：`LoopResult.token_used`（缺省 0）由 `DefaultLoop`
  以 `ctx.token_used`（上下文估算）填充；调度器按 `task_id` 累计**本任务所有子任务**的记账，
  越过正预算 ⇒ 当前子任务 `ok=False` + `TASK_TOKEN_BUDGET_EXCEEDED`，并**禁重试、禁重拆**，
  终态 `FAILED`（`extra={"token_used","token_budget"}`），`_release` 清累计。
  预算 `0` = 关闭（不改变任何裁决）；负数构造期拒绝。
- **D5 失败通知是本地 JSONL 追加**：`entry._notify_failure` 每失败一行
  `{ts,event,task_id,session_id,code,reason,goal}`；`reason`/`goal` 经 `redact_secrets` 且
  逐字段截断 500 字符；新建文件 `0600`、父目录 `mkdir -p`；写失败只 stderr 告警，**不改变
  任务结局**。`_stream_task` 在 `task_failed` 时通知，**排除 `TASK_CANCELLED`**（主动取消
  不是无人值守告警）；超时分支与自动续跑失败分支显式通知。不做远程/webhook 推送。

**反证 3/3（均实测转红后复原，`md5sum` 一致）**：① 摘掉 `_denied_coeffects` 的越界判定
（恒返回 `[]`）⇒ 越界拒绝 / 全含 / 接线三条用例红；② 摘掉 `_record_tokens` 的越界返回
（恒 `False`）⇒ 预算耗尽用例红（DID NOT RAISE）；③ 摘掉 `_notify_failure` 的
`redact_secrets` ⇒ 密钥 canary 落盘用例红。

**规格**：`configuration` **ADDED**「无人值守配置项」（4 scen）；`permission` **ADDED**
「自动放行的 coeffect 允许面」（5 scen）；`orchestration` **ADDED**「整任务时限与 token 预算」
（5 scen）与「任务失败通知 sink」（5 scen）；`loop` **ADDED**「执行结果透出本轮 token 记账」
（2 scen）。`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_unattended.py` **37 例**（三面配置与校验；允许面 5 例 + guard 顺序 +
runtime 接线；预算累计/禁重试/禁重拆/零预算不限；`LoopResult.token_used` 缺省与填充；通知
脱敏/0600/多行/空路径无操作/失败与取消；`_run_task_stream` 超时/不限；`_task` 与
`_run_auto_resume` 超时分支）。`tests/test_entry.py` / `tests/test_auto_resume.py` 的
`SimpleNamespace` 配置桩补两项缺省访问器（缺省关 ⇒ 既有断言逐字不变）。净 **+37**
（3055 → **3092**）。四门禁：`ruff check` / `ruff format --check` 绿、`pyright` 0 errors、
`pytest -q` **3092 passed**。

**局限**：① `token_used` 是**上下文估算**（同错误与预算控制口径），不是账单 token；流式
增量、工具输出截断前的真实计费可能高于该值 ⇒ 预算只能近似约束成本；② 子任务在预算越界时
`ok=False`，已执行的前序子任务结果仍写入检查点，续跑会从中间波次继续；③ 墙钟只在 CLI
`task` 入口施加，`serve`/TUI 编程式调用不受此配置约束；④ 通知是单机本地文件，多进程追加
依赖 `O_APPEND`（每行一次 `write`），不保证跨主机汇聚；⑤ 允许面按**声明的** coeffect 判定，
插件若少报 coeffect 则允许面管不住（无特权核心的既有假设：插件契约可信）。

## ADR-0271：失败通知 webhook sink（change 0281 / 台账 E217）

**背景**：ADR-0270 的失败通知只落到**本机文件**（其局限④）—— 无人值守部署若不在同一台
机器上盯文件，失败依旧无人知晓。需要一条**远程**通道，但不得为此引入三方依赖或 IM 平台方言。

**决策**：

- **D1 通用 JSON POST，不做平台方言**：`orchestration.failure_notify_webhook` 指向任意
  HTTP(S) 端点，收口时单次 `POST` 一份 JSON：`text`（一行摘要，供机器人直接展示）+ 本地
  JSONL 同源字段 `event / ts / task_id / session_id / code / reason / goal`（供自动化解析）。
  理由：仓内无真实 IM provider（`im/provider.py` 只有 Protocol），做方言等于猜测；通用
  JSON 由接收端适配。
- **D2 stdlib 单次有界推送**：新 `core/orchestration/notify.py::post_failure_webhook` 仅用
  `urllib.request`，超时 5s（`WEBHOOK_TIMEOUT_S`）、**不重试**、不排队、不持久化待发。
  推送点位于任务失败收口（进程即将退出），重试只会拖延收口；「发出一次」优先。
- **D3 两个 sink 相互独立**：`_notify_failure` 先写文件、再推远端，各自兜底；任一失败只
  stderr 告警，**不阻止另一个**、不改变任务结局与退出码。`TASK_CANCELLED` 与文件 sink 同口径
  不通知。
- **D4 密钥安全：URL 可能内嵌令牌**：非空 URL 只接受 `http/https` + 非空 host；校验错误
  信息**只报键名与合法形态、不回显取值**；推送失败的告警**只报异常类名**（`HTTPError` /
  `URLError` 的 `str` 含完整 URL）。`reason` / `goal` 与文件 sink 同源脱敏与 500 字符截断。
- **D5 缺省关闭**：默认空串 ⇒ 不发起任何网络请求，与引入前逐字一致；只校验非空取值。

**反证 3/3（均实测转红后复原，`md5sum` 一致）**：① 摘掉 `_notify_failure` 的
`redact_secrets` ⇒ 密钥 canary 进请求体，脱敏用例红；② `_valid_webhook_url` 恒 `True`
⇒ `file://` / `ftp://` / 无 host 四项校验用例红；③ 告警带上 `{webhook}` ⇒ URL 内嵌令牌
回显用例红。

**规格**：`configuration` **ADDED**「失败通知 webhook 配置」（3 scen）；`orchestration`
**MODIFIED**「任务失败通知 sink」（5 → 7 scen，新增 webhook 失败不影响结局 / 未配置不发起
请求）。`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_failure_webhook.py` **13 例**（三面与优先级；非法 URL 阻断且不回显；
POST 方法 / 头 / JSON 与脱敏 / 截断 / `text`；空配置零请求；webhook 失败不阻断文件、文件失败
不阻断 webhook；`_stream_task` 失败推送 / 取消不推送）。`tests/test_entry.py` /
`tests/test_auto_resume.py` / `tests/test_unattended.py` 的配置桩补
`orchestration_failure_notify_webhook` 缺省访问器（缺省关 ⇒ 既有断言逐字不变）。净 **+13**
（3092 → **3105**）。四门禁：ruff check / format 绿、`pyright` 0 errors、`pytest -q` 全绿。

**局限**：① 单次尝试、无重试队列 —— 端点瞬时故障即丢该条通知；② 通用 JSON 不是任何 IM
平台的原生格式，接收端需自行转换（无 Slack / 飞书 / 钉钉适配器）；③ 同步推送发生在收口
路径，最坏增加 5s 退出延迟；④ URL 本身即凭据（若内嵌 token）—— 仅保证不回显 / 不落日志，
不提供密钥轮换或签名；⑤ 不校验接收端响应体，2xx 即视为成功；⑥ 与文件 sink 同为单机进程
行为，多进程并发推送的到达顺序不保证。

## ADR-0272：auto-approve 命令模式级允许面（change 0282 / 台账 E218）

**背景**：ADR-0270 的 `permission.auto_approve_coeffects` 只按 **coeffect** 收窄放行面，
而 `tools.code_run` 的 coeffect 固定为 `process:spawn` + `filesystem:write`：无人值守部署
只有「允许执行任意命令」或「禁止执行任何命令」两种选择，无法表达「只允许 `git status` /
`pytest` 这类命令」。

**决策**：

- **D1 在 `PermissionGuard.confirm` 判定**：`PermissionModeGate.authorize(op, target,
  coeffects)` 拿不到工具实参；`confirm(tool_id, args, coeffects, reversible)` 是唯一同时具备
  模式与实参的接缝。命令面在模式放行**之后**、guardrail **之前**判定；两层都通过才 `auto`。
- **D2 条目与作用域**：`permission.auto_approve_commands`，条目 `tools.code_run:<前缀>`
  （工具 id 白名单仅 `tools.code_run` —— 当前唯一执行任意命令的工具）。无条目的工具不受
  约束；空配置 = 关闭，与引入前逐字一致。
- **D3 保守匹配**：命令取 `args["script"]`；非字符串/缺失 ⇒ fail-closed 拒绝；含 shell
  元字符（`;` `|` `&` `$` 反引号 `<` `>` `(` `)`、换行）⇒ 一律拒绝；否则须**完全等于**
  前缀或以「前缀 + 空白」开头（词元边界，`git statusx` 不匹配 `git status`）。不做 shell
  解析、不支持通配/正则。
- **D4 不回显命令**：命令正文可能内嵌令牌（`curl -H "Authorization: Bearer …"`）⇒ 拒绝
  信息只报工具 id 与「不在允许的前缀内」；配置校验错误同样不回显条目取值。
- **D5 只作用于 auto-approve**：非 auto 档仍按既有风险分级/审批语义；命令面不放宽
  coeffect 面，同时配置时取交集。
- **D6 组合根接线**：`build_runtime` 以 `config.permission_auto_approve_commands()` 注入
  `PermissionGuard(allowed_commands=...)`；未传参的既有构造行为不变。

**反证 3/3（均实测转红后复原，`md5sum` 一致）**：① 摘掉元字符判定（恒不拒绝）⇒ `&&` /
`$(…)` / 重定向 / 管道四条注入用例红；② 词元边界改为裸 `startswith(prefix)` ⇒
`git statusx` 误匹配用例红；③ 摘掉 `confirm` 的命令面分支 ⇒ 13 例红（不匹配、fail-closed、
接线）。

**规格**：`configuration` **ADDED**「自动放行的命令允许面配置」（4 scen）；`permission`
**ADDED**「自动放行的命令允许面」（7 scen）。`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_command_allowlist.py` **26 例**（三面与优先级；全角逗号与去重；
非法条目阻断且不回显；前缀匹配 / 词元边界 / 元字符 / fail-closed；其他工具、空配置与非
auto 档不受影响；组合根接线）。净 **+26**（3105 → **3131**）。四门禁：ruff check / format
绿、`pyright` 0 errors、`pytest -q` **3131 passed**。

**局限**：前缀匹配**不是沙箱** —— 参数可携带任意语义（`git config` 改配置、`pytest` 执行
仓库代码）、`cwd` 不受限、后台执行同样只按正文匹配；只降低「模型随手执行任意命令」的
概率。Python `type` 脚本通常含括号/分号，在命令面开启时会被元字符规则拒绝（保守取舍）。
不支持子命令级/参数级约束与通配；新增执行命令的工具须先改规格。

## ADR-0273：后台登记跨进程归属与写锁（change 0283 / 台账 E219）

**背景**：change `0279` 的 `background-tasks.json` 假定同一状态目录只有一个进程在用：
加载时无条件把 `running` 映射为 `interrupted`（ADR-0269 局限①），写盘为整体重写。CLI
`task`、`serve`、TUI 可能共用 `CORE_STATE_DIR`：后启动的进程会把**仍在运行**的后台任务
误标为中断（模型可随即 `tools.task_retry` 双跑），并发写则互相覆盖、丢失登记。

**决策**：

- **D1 按条目记录 owner**：持久化新增 `owner_pid` 与 `owner_start`（Linux 取
  `/proc/<pid>/stat` 第 22 字段 `starttime`；其他平台取不到时为空串）。只入状态文件，
  `info()` 不暴露。
- **D2 存活判定**：`_pid_alive` —— POSIX `os.kill(pid, 0)`（`PermissionError` 视为存活），
  Windows 用 `ctypes` 的 `OpenProcess` + `GetExitCodeProcess`（**不能**在 Windows 调
  `os.kill(pid, 0)`，它会终止进程）。`_owner_alive` 在双方都有启动标识时要求一致，识别 pid 复用。
- **D3 加载映射**：`running` 且 owner 存活 ⇒ **保持 `running`**，本进程没有句柄：不取消、
  不接管、不重放通知，`tools.task_retry` 按 running 拒绝；owner 已退出 / 旧格式无 owner /
  启动标识不符 ⇒ 维持 `interrupted`（升级前的在途记录不会被永久挂起）。存活 owner 的条目
  计入 `running_count()`（共享容量，避免多进程合计无界）。同进程第二个注册表同样按存活处理。
- **D4 锁内「读-合并-写」**：维护 `_dirty`（`spawn` / 终态 / 加载时被判中断）。写盘取
  `.{name}.lock` 的短独占锁（POSIX `fcntl.flock` / Windows `msvcrt.locking`；锁内重读磁盘，
  仅用 dirty 条目覆盖，非 dirty 条目保留磁盘版本），随后临时文件 + fsync + `os.replace`。
  这样 B 的陈旧 `running` 快照不会回滚 A 刚写入的 `done`，A 的新登记也不会被 B 覆盖。
  取锁失败（OSError）降级为无锁写；锁文件 `0600`。
- **D5 合并时再次脱敏**：磁盘记录合入前只保留白名单字段，`task`/`error` 重新
  `redact_secrets` 并有界 —— 手工编辑进文件的密钥形态正文不会经合并写回扩散。
- **D6 兼容**：`state_path=None` 纯内存路径零变化；不新增配置项、不新增三方依赖。

**反证 3/3（均实测转红后复原，`md5sum` 一致 `788b23ea…`）**：① 摘掉 `_owner_alive` 判定
（running 一律映射中断）⇒ 存活 owner / 不回滚两例红；② `_save` 不做磁盘合并（整体覆盖）⇒
保留他人登记 / 不回滚 / 合并脱敏三例红；③ 不看 `_dirty`（内存全部覆盖）⇒ 陈旧 running
回滚磁盘 done 一例红。

**规格**：`orchestration`「后台任务跨重启登记与重入队」**MODIFIED**（复制全部旧场景，修订
running 映射，新增存活 owner / pid 复用 / 并发写三场景）。`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_background_ownership.py` **10 例**；`test_background_persistence.py`
的重启用例改为「已退出子进程 pid」模拟新进程。净 **+10**（3131 → **3141**）。四门禁：
ruff check / format 绿、`pyright` 0 errors、`pytest -q` **3141 passed**。

**局限**：存活 owner 的条目只观察不接管；owner 在本进程加载**之后**死亡，需下次加载才转
`interrupted`；`msvcrt.locking` 重试上限约 10s，极端争用时降级直写；网络文件系统
（NFS/SMB）锁语义不保证；`owner_start` 在非 Linux 平台为空，只剩 pid 判活、存在复用误判
的残余风险；合并写仍按 `started_at` 保留最新 64 条。

## ADR-0274：子 Agent 工作树隔离（change 0284 / 台账 E220）

**背景**：`tools.delegate` 的前台 / 后台子 Agent 与主 Agent 共用同一进程 cwd（对齐报告
`doc/01-architecture/claude-code-alignment.md` §3.9 的 P0 缺口）。并行委托写同名文件只能靠
纪律与重复调用抑制；子 Agent 的失败改动直接落在主工作区，无法隔离、复核或回滚。

**决策**：

- **D1 工作区用 ContextVar，不重构 loop / provider**：新 `core/tools/workspace.py`（仅 stdlib）
  提供 `workspace_root()` / `use_workspace(root)` / `resolve_path(path)`。`asyncio.create_task`
  与 `asyncio.to_thread` 都会复制当前 context ⇒ 隔离按任务生效；三个 profile 的 loop 仍只构造
  一次。`DefaultLoop._normalize_action_args` **不改**：它是单次 run 内的去重键，而工作区在一次
  run 内恒定，改它只会引入 loop → workspace 的反向耦合。
- **D2 创建点在前台 `_dispatch` / 后台 `_delegate`，不在注册表**：注册表不依赖 git / 配置；
  `spawn(..., workspace=lease)` 接收租约，`_run` 在 `use_workspace(lease.path)` 内 `arun`。
  `changed_files` 为 best-effort 统计（失败返回空列表），不影响任务结果。
- **D3 不把工作树创建记为 `EffectTracker` 效应**：终态**保留**是产品决策；若挂 undo，全局
  回滚会删除用户期望保留的产物。创建的可逆面是显式 `tools.worktree.discard`，不是会话副作用。
- **D4 工具面拆两个、用点号 id、靠既有词元分级**：`tools.worktree.list` 命中只读词元 `list`
  ⇒ `READ`；`tools.worktree.discard` 无只读 / 写词元 ⇒ deny-by-default `HIGH_RISK`。
  **不改** `PolicyEngine` 代码；coeffect 为 `worktree:read` / `worktree:write`，仅开关开启时
  注册、仅主工具面。子 Agent 的 provider 结构上不含两者。
- **D5 git 原语加在 `GitBackend` / `SubprocessGitBackend`，不加在 `GitClient`**：工作树生命周期
  是本地操作，不属远程 / 审批面。新增 `repo_root` / `worktree_add` / `worktree_list` /
  `worktree_remove` / `branch_exists` / `delete_branch`；以 `-` 开头的参数一律拒绝（防选项注入），
  stderr 永不回显，clean-check 失败映射 `GIT_WORKTREE_DIRTY`。
- **D6 配置三面、缺省 OFF**：`orchestration.worktree_isolation` /
  `--orchestration.worktree-isolation` / `CORE_ORCHESTRATION_WORKTREE_ISOLATION`。非法值阻断启动
  （与 `auto_resume` 同口径），不静默降级；关闭时不构造 manager、不注册 coeffect、不挂工具。
- **D7 布局与安全**：`$CORE_STATE_DIR/worktrees/<repo_key>/<worktree_id>/`，sidecar
  `<worktree_id>.json`（0600、原子写），根 0700；`repo_key = sha256(realpath(repo_root))[:12]`，
  `worktree_id = wt-<12hex>`，分支 `core-agent/wt-<12hex>`。sidecar 只存
  `version/id/repo_root/path/branch/agent_id/created_at`。`discard` 校验 id 正则、精确布局、
  `realpath` 包含与分支名，越界即拒绝；拒绝运行中后台任务占用的工作树。
- **D8 顺带修复既有 bug**：`tools.task_retry` 的同步 handler 经 `asyncio.to_thread` 调用
  `registry.spawn`，后者在**工作线程**里 `asyncio.create_task` ⇒ 必然 `RuntimeError: no running
  event loop`。handler 改为 `async def`：`spawn` 回事件循环，工作树创建等阻塞 IO 走
  `asyncio.to_thread`。既有四个重入队测试同步改为 `await handler(...)`。
- **兼容**：`_PERSIST_VERSION` 保持 1；后台登记的 `worktree` 字段仅在非空时写，旧记录照常加载；
  读侧按白名单清洗（id 正则、文本有界、`changed_files ≤ 20`）。

**反证 3/3（均实测转红后复原，`md5sum` 一致）**：① `builtin._expand` 退回
`Path(path).expanduser()` ⇒ 前台文件隔离用例红；② `background._run` 去掉 `use_workspace`
包裹 ⇒ 后台隔离用例红，而前台用例仍绿（两支独立）；③ `discard` 去掉 `_record_valid` 改为直接
信任 sidecar 路径 ⇒ 篡改登记用例红（另一个合法工作树被误删）。

**规格**：`orchestration` / `configuration` / `git` / `permission` **ADDED**（10 + 3 + 4 + 4
场景）。`validate --all` **31/0**（归档后）。

**测试**：新增 `tests/test_worktree_backend.py` **7 例**、`tests/test_worktree_isolation.py`
**29 例**；既有 `test_background_persistence.py` 四例改为 await。净 **+36**（3141 → **3177**）。
四门禁：ruff check / format 绿、`pyright` 0 errors、`pytest -q` **3177 passed**。

**局限**：隔离是**路径作用域，不是安全沙箱** —— 绝对路径、`~` 展开结果与符号链接目标保持原
语义；git 工作树共享同一 `.git`（对象库与 refs 仍可被显式命令写入）。`TaskScheduler` 扇出未
隔离（顺序子任务依赖彼此未提交文件，合并语义另定）。工作树只增不减：无自动合并 / GC / 配额，
需显式 `discard`。后台登记中的 `changed_files` 是终态快照，不随之后的人工改动刷新。
Windows 只覆盖路径与锁的单元行为，未做手工端到端验证。`file_write` / `file_patch` 的撤销快照
列表在同一进程的并发任务间共享，工作树隔离不修复该既有问题（ADR 记录，不在本 change 范围）。

## ADR-0275：续跑批次单实例互斥（change 0285 / 台账 E221）

**背景**：对齐报告把「常驻调度形态」列为 P1，当前推荐形态是外部 cron 周期执行
`core-agent task --resume-all`。该路径没有互斥：cron 周期短于批次时长时，两个实例会同时扫描
同一批未完成任务并各跑一遍；`CheckpointStore` 跨进程是最后写者胜，`AutoResumeState` 的
临时文件写也会互相覆盖。同时缺少运维文档（cwd、状态目录、退出码、止血）。

**决策**：

- **D1 只做单实例锁，不做队列 / 守护进程**：cron 重叠是常态；跳过并等下一次 tick 重试足够。
  排队会让 cron 进程堆积，守护进程会引入生命周期 / 升级 / 日志新面。
- **D2 新增 fail-closed 的 `try_exclusive_file_lock`，不改既有 fail-open 的
  `exclusive_file_lock`**：后者用于后台登记 / 工作树 sidecar，取锁失败**无锁写**是刻意的
  尽力而为；互斥场景必须 fail-closed。新助手同文件、同平台分支（POSIX
  `flock LOCK_EX|LOCK_NB` / Windows `msvcrt.LK_NBLCK`）、锁文件 `0600`。
- **D3 三态 `acquired / busy / unavailable`，不压成 bool**：`busy` 是正常重叠（退出 0），
  `unavailable` 是权限 / 磁盘故障（显式入口退出 1），运维含义不同。创建或加锁失败一律
  `unavailable`，绝不降级为无锁续跑。
- **D4 锁在 `pending_resumes()` 之前获取，持有到批次结束**：扫描、逐任务执行、
  `AutoResumeState` 读改写都是批次的一部分；只罩扫描仍会双跑。锁文件
  `$CORE_STATE_DIR/.auto-resume.json.lock`，释放时**不删除**（避免两个进程锁到不同 inode）。
- **D5 函数体拆为 `_run_auto_resume_locked`**：架构门禁统计 `with/if/for/try` 嵌套 ≤3；
  不拆会把既有深度 3 推到 4。锁在 `with` 内交给 locked body，不得提前退出上下文。
- **D6 退出码与自动模式**：`busy` 返回 `False` ⇒ `--resume-all` 退出 0；`unavailable` 返回
  `True` ⇒ 退出 1。自动模式返回值本就被丢弃：两种跳过都不阻止本次新任务。
- **D7 锁范围只到续跑批次**：`CheckpointStore` 仍是共享 `.tmp` + 最后写者胜；fresh `task`、
  `task --resume <id>`、REPL、`serve` 不受约束。系统不声称检查点文件获得跨进程单写者一致性。
- **D8 止血靠文档，不新增删除 CLI**：`--resume-all` 的 `force=True` 绕过退避与尝试上限，
  永久失败任务会每 tick 重试。手册给出「停 cron → 备份 → 删除 `snapshot.task_id` 行」步骤；
  `task --forget` / 保留期与配额登记为后续缺口。

**反证 3/3（均实测转红后复原，`md5sum` 一致）**：① `_run_auto_resume` 去掉取锁包裹 ⇒ 并发
busy 用例红（第二个实例扫描并执行）；② 打开失败改为 `acquired`（fail-open）⇒ unavailable
用例红（不执行续跑 / 退出码预期被破坏）；③ 锁只包住扫描、循环前释放 ⇒ 「执行期仍持锁」断言红。

**规格**：`orchestration` **ADDED**「续跑批次单实例互斥」（6 场景）。`validate --all`
**31/0**（归档后）。

**测试**：`tests/test_auto_resume.py` 净 **+7 例**；`tests/test_unattended.py` 的直接调用点补
`CORE_STATE_DIR` 隔离。净 **+7**（3177 → **3184**）。四门禁：ruff check / format 绿、
`pyright` 0 errors、`pytest -q` **3184 passed**。

**局限**：锁是平台原生**建议锁**，只在单机本地盘保证；NFS / 网络盘 / 部分 WSL 挂载不保证互斥。
批次挂死会占锁到进程退出，期间 tick 全部跳过并退出 0；无锁超时、PID 诊断或过期回收。
`--resume-all` 每 tick 重试永久失败任务并重复通知（需手工止血）。锁只覆盖续跑批次，
同一 `$CORE_STATE_DIR` 仍按单写者假设使用。Windows 只做单元行为覆盖，未做手工端到端验证。

## ADR-0276：检查点运维入口（change 0286 / 台账 E222）

**背景**：ADR-0275（0285）把「永久失败任务」的止血留成文档步骤：停 cron、备份、
手工删除 `checkpoints.jsonl` 中对应行。该步骤绕过 `CheckpointStore` 的原子写，且
`--resume-all` 的 `force=True` 会让病态任务每 tick 重试并重复通知；保留策略虽有配置通道，
却没有一次性清理入口。ADR-0275 D8 明确把 `task --forget` / 配额清理登记为后续缺口，本 ADR 关闭它。

**决策**：

- **D1 两个动词挂在 `task` 下**：`--forget <task-id>` 与
  `--prune-checkpoints [--max-count N] [--older-than-s S]`。检查点是编排任务的状态载体，
  新增 `checkpoint` 顶层命令组只为两个动词引入新命名空间，不划算。
- **D2 `--forget` 精确、含 pinned、清退避**：按 `task_id` 精确匹配；pinned 只豁免**自动**
  清理，显式遗忘必须删掉，否则最新快照仍会被 `_task_resumes` 选中，止血失败。
  同时 `AutoResumeState.clear(task_id)`，避免残留账本与状态文件观感不一致。
- **D3 删除 0 条非零退出**：人工/脚本点杀时，拼错 id 静默成功比失败更危险。
- **D4 一次性清理复用保留语义**：max_count 约束未 pinned 集，time_window 删除陈旧未 pinned；
  两通道取并集；pinned 永不删除；至少给一个边界。不新增配置键。
- **D5 批量删除**：`CheckpointStore.delete_many` 单次落盘；`RetentionManager.prune` 收集待删
  集合并一次删除，`apply` 先调 `prune` 再走既有 quota 分支（该分支行为与抛出时机不变）。
  否则一次清理上千条会话轮检查点会触发 O(n²) 次全文件重写。
- **D6 与续跑批次共用锁**：两个入口在打开 store 前取 `.auto-resume.json.lock`，
  `busy` / `unavailable` 一律 fail-closed（`[checkpoints_locked]` + 退出 1）。
  不扩展到 fresh `task` / REPL / `serve`，单写者假设不变。
- **D7 不做模型工具**：删除面只给显式 CLI；暴露为工具需要审批与 schema，且是提示注入的
  高风险目标。CLI 调用即授权。

**被拒方案**：手工编辑 `checkpoints.jsonl`（半截文件会让 store 整体降级）；`checkpoint` 顶层
命令组（两个动词撑不起命名空间）；`--forget` 0 条退出 0（拼错 id 无声失败）；跳过 pinned
（留下最新快照，止血失败）；阻塞等待续跑锁（cron 批次长，维护会被挂住）。

**反证 3/3（均实测转红后复原，`md5sum` 一致）**：① 维护入口去掉取锁 ⇒ 锁占用用例红；
② `--forget` 不按 `task_id` 过滤 ⇒ 只删目标任务用例红；③ `--prune-checkpoints` 连 pinned
一起删 ⇒ pinned 保护用例红。

**规格**：`orchestration` **ADDED**「检查点运维入口」（6 场景）。`validate --all`
**31/0**（归档后）。

**测试**：新增 `tests/test_checkpoint_maintenance.py`（10 例）＋ `tests/test_durability.py`
补 2 例；净 **+12**（3184 → **3196**）。四门禁：ruff check / format 绿、`pyright` 0 errors、
`pytest -q` 全绿。

**局限**：删除不可逆，无回收站；`--max-count` 只约束未 pinned 集（保留总数可为 `N + pinned`）；
维护入口只与续跑批次互斥，fresh `task` 并发时仍是最后写者胜；NFS/网络盘不保证锁互斥；
清 `auto-resume.json` 失败只告警、不影响退出码。

## ADR-0277：coding-plan 索引守卫与 G1/G2 消歧（change 0287 / 台账 E223）

**背景**：`Pending-Arbitration.md` 在 `0226` 登记了 PA-11（README 阶段索引漂移）与 PA-12
（`phase-38` 批内缺口与记忆三面路线图共用 `G1`/`G2`）。PA-11 已造成实证返工：走查按 README 的
`phase-0~34` 范围找账，漏掉 `phase-36`（长任务硬化）与 `phase-38`（四维记忆蓝图查漏补缺），
把已裁决事项重报为缺口。两条都只动文档，但需要一条门禁防止再次漂移。

**决策**：

- **D1 PA-11 取「补索引 ＋ 守卫」（方案 C）**：只补一次仍会再漂；一条断言把「新增 Phase 忘补
  索引」从静默漂移变成测试转红。
- **D2 计数口径对齐仓库内文件，不沿用旧自述**：`phase-*.md` 共 **46** 份（主文档 43 ＋ 配套记录
  3），最大 `phase-41.md`。本地未跟踪、按约定不提交的 `phase-32.md` / `phase-3-prompt.md`
  不计入。旧句「36 份（README + `phase-0`~`phase-34`）」本身就算不平。
- **D3 守卫解析唯一「索引计数（守卫）」行**：机读份数、主文档数、配套数、最大编号，与实际 glob
  逐项比对；改文案格式时测试失败信息直接指出缺失句式。
- **D4 §1 覆盖按主文档集合判定**：解析 §1 表行的反引号文件名，要求与 `phase-N[.N].md` 集合
  **相等** —— 「正文提过、索引没列」的半漂移也会红（`phase-32.md` 正是这种）。
- **D5 PA-12 取局部改前缀（方案 B）**：§0 批内缺口改 `B38-1/2/3`，加「与路线图 G1~G5 非同组」
  注记；§118 路线图收官声明逐字保留。全局重编号（方案 C）历史成本过高，明确不做。
- **D6 登记与台账同步**：PA-11/PA-12 标已闭并带 change 号；`known-risk.md` 把「README §2 标 ✅
  与事实不符，属已知」订正为「✅ 表示 Phase 计划完成，不代表整包生产接线」。

**被拒方案**：只补索引不加守卫（会再漂）；保留旧「36 份」口径并手写解释（算不平，仍歧义）；
守卫只查 README 全文包含（漏「正文有、索引无」）；全局重编号 G1/G2（波及历史 ADR/台账）。

**验证**：`tests/test_coding_plan_index.py` 3 例；反证 3/3（改计数 / 删 §1 行 / 恢复裸 G1G2
⇒ 各红；`cp` 复原后 `md5sum` 一致）。四门禁全绿；`openspec validate --all` **31/0**（归档后）。

**测试**：新增 3 例（3196 → **3199**）；`tests/test_arbitration_ledger.py` 仅订正注释措辞。

**局限**：守卫依赖固定句式；只覆盖计数/最大编号/§1 覆盖，不判描述过时；配套记录不计入主文档
集合；`phase-32.md` / `phase-3-prompt.md` 按约定不提交，守卫硬编码排除（若将来入库须同步）；
`B38-*` 只消除 §0 批内歧义；其余文档无同类守卫；不全局重编号。

## ADR-0278：台账销账与 CLI 动词盘点（change 0288 / 台账 E224）

**背景**：`known-risk.md` §1 有两条与代码现状不符的挂账。E55 仍称主 loop「单工具协议只取
首个 `tool_call`」，而 change `0257` 已把全部原生 `tool_calls` 映射为 `ActionGroup` 并逐个
执行；E100 的 11 个未注册动词一直沿用「逐动词补 argparse 注册面」的口径，未区分「已有真实
承载」与「无真实后端」。

**决策**：

- **D1 E55 直接销账**：三层证据 —— `planner._from_tool_calls` 全量映射（`planner.py:855-871`）、
  `DefaultLoop` 展开执行（`default.py:601`）、`tests/test_parallel_tool_calls.py` 锁定
  planner 非流式/流式、执行顺序与重复调用抑制。无剩余实现面。
- **D2 E100 按真实承载分类，不一律补注册**：6 个动词已有真实承载（`version` → `--version`；
  `help` → `-h`；`install`/`uninstall`/`list` → `plugin ...`；`permission-mode` →
  `config get|set permission.mode`），不新增子命令；5 个无真实后端（`kill`/`logs`/`info`/
  `auth`/`gateway`）保持未注册，避免暴露永远成功但什么也不做的命令。
- **D3 守卫钉住差集**：`dispatcher` 六组顶层动词 − argparse 顶层子命令 = 未注册集合；
  与 `cli-ops-interface.md` 唯一「未注册动词（守卫）」行逐项比对，并核对声明计数。
- **D4 不删除不可达分支**：`CLICommandDispatcher.status()` 自 change `0162` 起不可从 CLI
  触达，但仍属六组模型；销毁性清理另立 change。

**被拒方案**：把 11 个动词全部注册（暴露 MVP 桩/空操作面，比不注册更误导）；删除
`cli_ops/dispatcher.py`（影响接口模型与测试，超出盘点范围）；把 E100 直接标已闭（5 个动词
仍无后端，属未闭实现面）。

**验证**：`tests/test_cli_verb_inventory.py` 2 例；反证 3/3（删文档动词 / 改声明计数 /
临时注册 `kill` ⇒ 各红；`cp` 复原后 `md5sum` 一致）。四门禁全绿；
`openspec validate --all` **31/0**（归档后）。

**测试**：新增 2 例（3199 → **3201**）；无 `src/` 行为改动。

**局限**：守卫只锁动词集合与计数，不锁映射说明是否过时；`version`/`help` 是 flag 不是子命令；
5 个无后端动词的判断基于 2026-10-18 代码快照；argparse 顶层命令经私有 `_subparsers` 读取；
不删除不可达 `status()` 分支。

## ADR-0279：PA-09 D/E 裁决 —— 多跳基准不建图 ＋ 语义检索可强制（change 0289 / 台账 E225）

**背景**：PA-09 的 D（图存储/遍历）与 E（真语义检索）在 2026-10-18 由用户裁决为
「**先测后裁**」与「**基准 + 可选强制**」。裁决前的事实：关系三元组以扁平 L2 条目落库
（`relation.*`，tags 含 `entity:` / `predicate:`），`MemoryBackend` 无遍历方法，
`memory.relation_extract` 缺省 `false`，本机真实记忆样本 `relation.*` 为 **0** 条；change
`0271` 已按端点表默认启用 embedding，但缺少「语义优于词法」的离线证据，且无法要求
「没有 embedding 就拒绝启动」。

**决策**：

- **D1（D）本轮不建图，只交付测量**。新增 `tests/test_memory_graph_benchmark.py`：20 条
  合成链（`Z --owns--> B`、`B --part_of--> C`），查询只命中首跳。实测：扁平 BM25 的
  第二跳 recall@5 = **0.000**；从查询实体做 2 跳 tags 邻接 BFS 后 recall@5 = **1.000**。
  机制增益成立，但生产侧关系抽取缺省关、真实数据为 0 ⇒ 现在建图等于为零数据造索引。
  轻图（tags 邻接 + 遍历 API）保留为关系抽取真实运行并积累数据后的**既定形态**。
- **D2（E）新增 `llm.embedding_required`，缺省 `false`**。`ConfigSpec` 三面
  （`--llm.embedding-required` / `CORE_LLM_EMBEDDING_REQUIRED` / `llm.embedding_required`）；
  开启且 `effective_embedding_model` 为空 ⇒ `validate_schema` 阻断 `load()` / `apply_change()`。
  错误只含键名与提示，**不回显 endpoint / 密钥**。取值口径与 `embedding_auto` 同集。
- **D3 required 的语义边界**：只断言「模型已确定」，**不探测网络可达性**；调用期
  `/embeddings` 失败仍按既有路径降级 BM25 词法。required 缺省关 ⇒ 行为逐字不变。
- **D4（E 基准）**：新增 `tests/test_semantic_benchmark.py`：20 组同义词域，确定性概念
  embedder 让改写查询与 gold 词面零重叠。实测词法 recall@1 = **0.000** / MRR@5 = 0.037，
  语义 recall@1 = 1.000 / recall@5 = 1.000 / MRR@5 = 1.000；断言语义 MRR 至少高出词法 0.5。
- **D5 关系流水线覆盖率**：同一基准度量确定性后处理 —— 闭合谓词表 48/48 变体可归一、
  未知谓词/空实体/密钥形态丢弃、同批重复归并、`relation_cap` 截断（30 条 ⇒ 8 条）。

**被拒方案**：本轮直接建轻图（零真实关系数据，无法验证收益，且触碰后端协议）；
引入本地 embedding 模型（违反零三方运行时依赖红线，2026-10-18 已裁）；required 默认开启
（把现有「未知端点词汇降级」部署变成启动失败，破坏缺省兼容）；把 required 做成网络健康探测
（与「密钥只引用不读取」纠缠，且启动期多一次不可控网络调用）。

**验证**：新增 22 例（配置三面/校验 12 + 语义基准 4 + 多跳/覆盖 6）；反证 3/3；四门禁全绿；
`openspec validate --all` 归档后 31/0。

**局限**：多跳基准是**完美抽取**的合成链，不测 LLM 抽取召回/精度；邻接在测试内模拟，
不代表真实存储/协议成本；概念 embedder 证明通路与量纲，不证明真实模型质量（须在线测量）；
required 不保证端点可达；「真实关系为 0」基于 2026-10-18 的本机记忆快照，随部署变化。

## ADR-0280：同步薄壳循环桥接 ＋ 记忆批量语义相似（change 0290 / 台账 E226）

**背景**：2026-10-18 的真实 `task` 冒烟打印
`RuntimeWarning: coroutine 'StdlibLLMProvider.aembedding' was never awaited`。根因链：
`MemoryStore.read` 在事件循环线程上同步执行 → `_similarity` 逐候选调用 embedder →
`batch_embed` 串行适配 → `LLMEmbedder.embed` → `LLMProvider.embedding` 的
`asyncio.run` → 循环嵌套 `RuntimeError`（先建协程再调用，留下未等待协程）→
`_memo_embedder` 置**粘性** `_embed_failed=True` ⇒ 本进程后续检索全走词法。
`llm.embedding_required` 抓不到（ADR-0279 明确它只做配置期阻断、不探测可达性）。
同一路径还有规模问题：逐候选调用 ⇒ N 条候选 N 次远端往返。

**决策**：

- **D1 同步薄壳在运行中事件循环内走一次性工作线程**。私有 `_run_sync(factory)` 先
  `asyncio.get_running_loop()`：无循环 ⇒ `asyncio.run(factory())`（与旧实现逐字同义）；
  有循环 ⇒ `ThreadPoolExecutor(max_workers=1)` 内新循环执行同一异步实现并 `.result()`
  等待。传**协程工厂**而非协程 ⇒ 桥接失败不留孤儿协程。三个薄壳
  （`completion` / `stream` / `embedding`）统一接入；两种上下文均为**阻塞**语义。
  不 import `core.runtime._run_coro`（架构门禁禁止 `llm_provider` 依赖 `runtime`）。
- **D2 `LLMEmbedder.embed_many(texts)`**：一次 provider 同步调用收齐一批并映射
  `LLMError → RAGError(EMBEDDING_FAILED)`；空输入返回 `[]` 不触网。**不加入 `Embedder`
  ABC**（HashEmbedder 等实现不需要批量，契约扩散无收益）；`batch_embed` 保留为
  「只提供单文本 callable」的兼容适配器。组合根 memory 通路改为注入 `embed_many`。
- **D3 `relevance.batch_similarities`**：`[query, *(content)]` 按 `_SIM_BATCH_SIZE=64`
  切块，query 恒在第一块 ⇒ 每次检索至多嵌入一次；逐块校验数量，首块取 query 向量并
  校验维度一致（`_cosine` 用 `zip(strict=False)`，维度不符会静默截断）；余弦算完即丢，
  不累计 10k 向量。**空候选集提前返回 `{}` 且不调用 embedder** —— 空读触网失败会置
  粘性降级、毒化后续检索，这是必须堵住的最小事故面。
- **D4 整次检索一个尺度**：任一批异常 / 数量或维度不符 ⇒ 返回 `None`，`read` 对**全部**
  候选走 BM25，绝不返回部分映射（否则同一排序里余弦与词法混合、尺度不可比）。
  `rank` / `relevance` 新增仅关键字 `sim: float | None`，用 `is None` 判断
  （`0.0` 与负余弦合法），`sim` 优先于 `embedder`；`build_lexical_stats` 仍无条件执行
  （预热 token 缓存并服务降级路径）。缺省词法路径、`embedding_required` 配置期语义、
  粘性失败后的词法降级均逐字保留。

**被拒方案**：同步薄壳检测到循环就抛清晰错误（`read` 是既有同步契约，抛错只是把静默
降级换成显式中断，语义检索仍不可用）；把 `read` / `ContextAssembler.build` 异步化
（调用链全改，超出缺陷修复范围）；把 `embed_many` 加到 `Embedder` ABC（强制所有实现
跟进）；进程级单 worker executor（worker 内再调薄壳会自等死锁）；语义 top-K 预筛
（真正的延迟优化，需独立召回质量评估，不能与缺陷修复捆绑）。

**验证**：新增 20 例（provider 3 / rag 4 / 批量相似 8 / 词法预计算 2 / memory 3）＋
修改 `test_phase13` 注入断言；全量 3221 → **3241**；反证 3/3（薄壳改回裸 `asyncio.run`、
组合根改回 `batch_embed`、`read` 改回逐候选）；四门禁全绿；`openspec validate --all`
归档后 31/0；真实 embedding 端点在 `asyncio.run` 内检索无告警。

**局限**：① 桥接仍**阻塞**事件循环 —— 每次远端调用期间循环停摆，非阻塞调用方须用
`a*` 入口；② 一次性线程使 `HTTPConnectionPool` 的 thread-local 连接在该路径不复用
（每次新连接）；③ `_VEC_CACHE_MAX=4096` 的 FIFO 淘汰不变，10k 候选时缓存仍抖动，
批量只减少调用次数（10k 约 157 次顺序往返）；④ 粘性 `_embed_failed` 不变：一次失败后
本进程语义检索不可用，需重启；⑤ `CORE-NFR-PERF2`（<100ms）仍是**词法**基准，不据此
外推远端 embedding 路径达标；⑥ `stream` 仍为缓冲式，桥接不使其增量；⑦ 冒烟只证明
「告警消失、语义排序生效」，不证明远端模型质量。

## ADR-0281：任务级验收反馈回流与重拆退化守卫（change 0291 / 台账 E227）

**背景**：2026-10-18 的真实 `task` 冒烟暴露两处反馈断裂。其一，子任务两次通过，任务级判定因
「缺少 CLAUDE.md 原文引用」失败（`PROGRESS_NOT_MET`），但 `_replan_input` 只在
`failure.failed` 非空时输出原因，而任务级失败的 `_Failure.failed` 恒为空 ⇒ 重拆输入只有
目标、已完成列表与通用尾句「请重新拆解尚未完成的部分」，planner 完全不知道差距是什么，
把整理说明本身当子任务又跑一遍；唯一一次重拆预算耗尽。其二，执行者只看到
`subtask.acceptance`，看不到 `plan.success_criteria`，首轮即不可能主动满足整体验收。
另有放大器：LLM 拆解失败时 decomposer 回落为「goal = 输入原文」的单子任务，如果重拆输入
是一个长 prompt，该退化回执会被当作正常子任务**执行**并再消耗一次预算。

**决策**：

- **D1 重拆输入按失败类型分支，失败信息前置且有界**。仅当
  `failure.code == PROGRESS_NOT_MET and not failure.failed`（任务级未达标）走新布局：
  `任务级验收未通过：{reason[:_MAX_EVENT_EXCERPT]}` → 可选的任务级标准块 →
  「全部子任务已完成但整体未达标；请只补充能补齐上述差距的子任务…」→
  `原始目标：{goal[:_MAX_REPLAN_GOAL_CHARS=600]}` → 已完成列表。失败段与标准
  （`_MAX_REPLAN_CRITERIA_CHARS=600`）各自有界且位于已完成列表之前，因此
  **总截断（`MAX_HANDOFF_CHARS=2000`）后失败段仍存活** —— 只调换顺序不够，6000 字目标
  会占满预算把失败段挤掉。子任务失败 / 死循环分支的文案与顺序**逐字不变**。
- **D2 任务级标准随交接进入执行输入**。私有 `_task_criteria_text(plan)` 生成
  `任务级成功标准（整体必须满足）：` + 每条标准（去空白、有界 600）。`_build_handoff`
  把它追加到 `TaskHandoff.acceptance`：子任务验收让出预算
  `MAX_HANDOFF_CHARS - len(criteria) - 2`，组合总长 ≤ `MAX_HANDOFF_CHARS`；
  无子任务验收时只放标准；**标准为空时 `acceptance` 与既往逐字节相同**（保护 beast / pet
  空上下文路径）。不新增 `TaskHandoff` 字段、**不修改** `subtask.acceptance` ⇒
  `SubtaskDecomposer.verify` 仍只看子任务自身标准，任务级标准只影响执行者可见信息，
  不改变子任务验收判定。
- **D3 退化回执 fail-fast，而不是过滤**。`decompose` 成功后、接管 `new_plan` 前，若任一
  子任务的 `goal.strip()` **精确等于**重拆输入 `.strip()`，直接转 `FAILED`
  （`SUBTASK_VERIFY_FAILED`，理由「重新拆解回执退化为拆解输入本身，未生成可执行子任务」，
  `extra={"replans": ...}`），**不执行**回执中的任何子任务（含其中的正常子任务）。
  只做去空白后的精确相等，不做子串匹配。守卫**只作用于重新拆解**；初次拆解的离线回落
  （单子任务、目标即输入）保持现状。
- **为何不「过滤退化项后交给空计划守卫」**：部分过滤会让新计划的 `order` / `waves`
  残留已删 id，`_fan_out` 静默跳过 ⇒ 空波次、脏依赖，最终以死循环或无进展收场，
  而不是预期的空计划失败。整份回执 fail-fast 更简单，语义也一致（回执没有可用计划）。

**被拒方案**：放松 `LLMTaskVerifier` 判定口径 / 在 prompt 里强调判定器要求（把缺陷从
反馈通路偷换成提示词调参，判定仍不可满足时无法定位）；只调换 `_replan_input` 的段落顺序
（6000 字目标仍会挤掉失败段）；增加重拆预算（在信息为零的输入上重复同一失败，成本更高）；
过滤式退化守卫（见 D3）；给 `TaskHandoff` 新增 `criteria` 字段（扩大六字段契约与三条执行
路径的消费面，`acceptance` 已有渲染位）。

**验证**：新增 11 例（重拆输入 4 / 退化守卫 2 / 交接组合 5）；全量 3241 → **3252**；
反证 3/3（`_replan_input` 恢复只认 `failure.failed`、`_build_handoff` 去掉标准追加、
去掉退化守卫）；四门禁全绿；真实模型 + 真实调度器的注入式 e2e（固定任务级判定失败以
触发重拆）确认重拆输入含原因与标准，真实 planner 第二次调用回落 echo 时由退化守卫以
`SUBTASK_VERIFY_FAILED` 收口（回执未执行）；真实 `task` CLI 冒烟通过、零告警；归档后
`openspec validate --all` 31/0。

**局限**：① 新布局只覆盖**任务级**未达标（`failure.failed` 为空）；子任务失败 / 死循环
分支不携带任务级标准，仍只有目标与已完成列表；② 退化守卫是去空白后的**精确相等** ——
模型把重拆输入改写一句（加前缀、换行重排、摘要）即可绕过，它是下限护栏而非语义判重；
③ 任务级标准只是执行者可见的**建议性上下文**，运行时不对子任务输出做任务级校验
（有意保持子任务验收语义不变）；④ 原因与标准各截断 600 字符，超长标准/原因会丢尾部，
极端情况下关键差距可能落在截断之外；⑤ 重拆预算仍为 1，本 change 提高的是这一次重拆的
信息质量，不增加恢复次数；⑥ 真实冒烟只证明输入内容与失败码，不证明模型第二次拆解一定
满足任务级标准。

## ADR-0282：空响应的截断成因诊断（change 0292 / 台账 E228）

**背景**：2026-10-19 真实冒烟（session `03c49ecf…`）第二轮约 89 秒后返回
`LLM_PLAN_PARSE_FAILED: 空响应`。复现确认：GLM-5.3 在 `reasoning_effort` 不下发时走默认
深度思考，把本次请求的 `max_tokens`（= `loop.output_reserve`，8192）全部耗在
`reasoning_content` 上，`content` 为空、`finish_reason="length"`。`LLMPlanner._parse`
在内容为空时先判空、未读取已传入的 `finish_reason`，于是把「输出预算耗尽/被截断」
误报为无成因的「空响应」，排障者无法区分空包、模型沉默与思考吃满预算。

**决策**：

- **D1 空内容分支读取 `finish_reason`**。去空白后为空且 `finish_reason == "length"`
  ⇒ `reply` 在既有前缀后追加「输出被截断；思考可能占用全部 max_tokens」；
  `finish_reason` 缺失、空串或非 `length` ⇒ 维持逐字
  `LLM_PLAN_PARSE_FAILED: 空响应`。保留原前缀子串，既有日志检索/呈现/前缀断言不受影响。
- **D2 只诊断，不自动兜底**。不自动加大 `max_tokens`、不自动降档重试、不探测思考长度；
  请求形状、调用次数、失败语义（`failed=true`、`ok=False`、零工具执行、无原始产出）不变。
- **D3 只读权威信号**。不按 `completion_tokens == max_tokens` 推断（部分 provider 不报
  用量，且 planner 拿不到可靠的请求侧对应关系）；`finish_reason` 是协议内的截断信号。

**被拒方案**：把空内容一律归为截断（`stop` 的空包会被误报，掩盖真实原因）；在空内容时
自动改用 `reasoning_effort=low` 重试（改变调用次数/延迟/成本，需独立恢复策略与规格）；
自动调大 `output_reserve`（改变预算分配与输入预算，超出诊断范围）。

**验证**：`tests/test_loop_output_protocol.py` 新增 2 例（length 成因 / 无信号逐字不变）；
全量 **3254 passed**（3252 → 3254）；反证 1/1（去掉 `finish_reason == "length"` 分支 ⇒ 截断文案用例红）；
四门禁全绿；真实冒烟前已用配置 `reasoning_effort: low` 完成端到端恢复。

**局限**：① 只改善提示，不阻止同类失败 —— GLM 系仍需显式 `reasoning_effort: low`
或调大 `output_reserve`；② provider 截断时不报 `finish_reason="length"`（缺失或
`stop`）仍显示旧文案；③ 不区分「思考耗尽」与「正文本身超长被截断」两个子因，后者由
非空内容的既有截断提示覆盖。

## ADR-0283：供应商输出上限能力适配与终止原因归一（change 0293 / 台账 E229）

**背景。** `loop.output_reserve`（缺省 `8192`）自 ADR-0174 起作为请求侧 `max_tokens` 下发，
但各供应商的**上限字段与数值并不统一**：OpenAI o 系 / GPT-5 系要求 `max_completion_tokens`；
`gpt-4-turbo` / `gpt-3.5` 的最大输出仅 `4096`，发 `8192` 会被端点 400。这正是 ADR-0174
局限②与 ADR-0175 局限④留下的坑（窗口表只推导上下文窗口）。同时，部分兼容层用
`MAX_TOKENS` / `max_tokens` 作为 `finish_reason` 截断别名，change 0292 的截断诊断只认
`length`，会漏报。

**决策**：

- **D1 能力表落在 `configuration` 底座层。** 新模块 `configuration/model_capabilities.py`
  （纯常量 + 纯函数）：`模型名子串 → {max_output_tokens, max_tokens_field,
  supports_reasoning_effort}`。未收录 ⇒ `None`；`max_output_tokens=0` 与
  `supports_reasoning_effort=None` 均表示「不知道」，不钳制、不告警。表不新增配置键。
  放底座层的原因：provider 要查表，配置校验要告警；而架构测试禁止底座反向依赖能力层。
- **D2 钳制与字段选择在 provider 请求体构建处。** 有效上限 =
  `min(请求值, 已知最大输出)`（只向下收紧，绝不抬高用户配置）；字段按表选
  `max_tokens` / `max_completion_tokens`，SHALL NOT 同时下发两个。未收录模型字段与数值
  逐字不变。`planner` / 组合根的注入口不动，适配全在协议边界。
- **D3 终止原因别名归一。** `max_tokens` / `MAX_TOKENS` / `max_output_tokens`
  （大小写与首尾空白不敏感）⇒ `length`，同时作用于流式与非流式；其余取值原样保留，
  不折叠为 `stop`，缺失沿用既有口径（流式空串 / 非流式 `stop`）。
- **D4 配置期仅告警。** ① 预留 > 已知最大输出 ⇒ 告警「请求将按模型上限下发」；
  ② 显式 `reasoning_effort` 对已知不支持模型 ⇒ 告警「仍会照常下发，端点可能拒绝」。
  未收录/未知能力不告警；SHALL NOT 改变校验通过与否，SHALL NOT 丢弃显式配置。

**被拒方案**：按各家 tokenizer 计算上限（维护不可持续，上限是协议常量）；启动期探测
`/models`（网络依赖与启动不确定性，ADR-0175 已拒）；同时发多个上限字段（严格端点 400、
宽松网关歧义）；按能力表静默丢弃 `reasoning_effort`（显式配置被改写）；新增
`llm.max_output_tokens` 键（当前主流族可由表覆盖，避免第二真源）；`length` 时自动加倍重试
（成本/延迟不可控，仍可能超模型上限）。

**验证**：能力表 6 例、provider 请求体/终止原因 7 例、配置告警 3 例；全量 **3270 passed**
（3254 → 3270）；反证 3/3（去钳制/字段选择、去别名归一、去告警分别变红）；四门禁全绿；GLM-5.3 真实单轮冒烟
（未收录上限、字段 `max_tokens`）确认请求形状与变更前一致。

**局限**：① 表是静态常量，新模型族需改代码；② 子串匹配无边界语义，自建模型名含
`gpt-4o` 等子串会被误纳入；③ 未收录的自研网关无法通过配置表达更低上限（本 change 不加键）；
④ `reasoning_effort` 只告警不拦截，已知不支持的端点仍会 400；⑤ 不改 `known_window`
既有窗口值（`gpt-4.1` 等窗口口径保持既有，窗口表更新是另一件事）；⑥ 不覆盖 Anthropic /
Gemini **原生协议**（仓库只走 OpenAI 兼容端点）。

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
| ADR-0097 | 03-interfaces/rag-interface.md, 02-modules/rag.md |
| ADR-0098 | 03-interfaces/skillhub-interface.md, 02-modules/skillhub.md |
| ADR-0099 | 03-interfaces/notes-interface.md, 02-modules/notes.md |
| ADR-0100 | 03-interfaces/observability-interface.md, 03-interfaces/evolution-interface.md, 02-modules/notes.md |
| ADR-0101 | 03-interfaces/plugin-registry-interface.md, 03-interfaces/tool-use-interface.md, 03-interfaces/mcp-interface.md |
| ADR-0102 | 03-interfaces/plugin-registry-interface.md, 03-interfaces/mcp-interface.md |
| ADR-0103 | 03-interfaces/loop-interface.md, 03-interfaces/memory-interface.md, 03-interfaces/context-interface.md, 03-interfaces/orchestration-interface.md, 03-interfaces/beast-mode-interface.md, 03-interfaces/pet-mode-interface.md |
| ADR-0104 | 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/phase-27.md |
| ADR-0105 | 03-interfaces/evolution-interface.md, 03-interfaces/configuration-interface.md, 02-modules/configuration.md, 04-testing/test-cases.md, coding-plan/phase-27.md |
| ADR-0106 | 03-interfaces/pet-mode-interface.md, 03-interfaces/beast-mode-interface.md, 04-testing/test-cases.md, coding-plan/phase-28.md |
| ADR-0107 | 03-interfaces/memory-interface.md, 03-interfaces/context-interface.md, 03-interfaces/loop-interface.md, 03-interfaces/skills-interface.md, 03-interfaces/pet-mode-interface.md, 03-interfaces/orchestration-interface.md, 02-modules/memory.md, 02-modules/context.md, 02-modules/loop.md, 04-testing/test-cases.md, coding-plan/phase-28.md |
| ADR-0108 | 03-interfaces/memory-interface.md, 03-interfaces/loop-interface.md, 03-interfaces/ui-interface.md, 03-interfaces/configuration-interface.md, 02-modules/memory.md, 02-modules/loop.md, 04-testing/test-cases.md, coding-plan/phase-28.md |
| ADR-0109 | 03-interfaces/ui-interface.md, 03-interfaces/cli-ops-interface.md, 02-modules/cli-ops.md, 06-ui-frontend/ui-architecture.md, 04-testing/test-cases.md, coding-plan/phase-28.md |
| ADR-0110 | 03-interfaces/memory-interface.md, 03-interfaces/context-interface.md, 03-interfaces/skills-interface.md, 03-interfaces/beast-mode-interface.md, 02-modules/memory.md, 02-modules/skills.md, 02-modules/context.md, 04-testing/test-cases.md, coding-plan/phase-30.md |
| ADR-0111 | 03-interfaces/pet-mode-interface.md, 02-modules/pet.md, 04-testing/test-cases.md, coding-plan/phase-30.md |
| ADR-0112 | 03-interfaces/evolution-interface.md, 02-modules/evolution.md, 04-testing/test-cases.md, coding-plan/phase-31.md |
| ADR-0113 | 03-interfaces/evolution-interface.md, 03-interfaces/ci-cd-interface.md, 02-modules/evolution.md, 04-testing/test-cases.md, coding-plan/phase-31.md |
| ADR-0114 | 03-interfaces/orchestration-interface.md, 03-interfaces/loop-interface.md, 02-modules/orchestration.md, 04-testing/test-cases.md, coding-plan/phase-29.md |
| ADR-0115 | 03-interfaces/ui-interface.md, 06-ui-frontend/ui-architecture.md, 04-testing/test-cases.md, coding-plan/phase-29.md |
| ADR-0116 | 03-interfaces/orchestration-interface.md, 03-interfaces/configuration-interface.md, 02-modules/orchestration.md, 04-testing/test-cases.md, coding-plan/phase-29.md |
| ADR-0117 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/phase-29.md |
| ADR-0118 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/phase-33.md |
| ADR-0119 | 03-interfaces/orchestration-interface.md, 02-modules/orchestration.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0120 | 03-interfaces/evolution-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0121 | 02-modules/plugin-registry.md, 03-interfaces/plugin-registry-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0122 | 03-interfaces/tool-use-interface.md, 02-modules/tool-use.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0123 | 03-interfaces/configuration-interface.md, 02-modules/configuration.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0124 | 03-interfaces/memory-interface.md, 02-modules/memory.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0125 | 03-interfaces/ui-interface.md, 06-ui-frontend/ui-architecture.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0126 | 03-interfaces/skills-interface.md, 02-modules/skills.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0127 | 03-interfaces/skillhub-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0128 | 03-interfaces/permission-interface.md, 02-modules/permission.md, 03-interfaces/git-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0129 | 03-interfaces/composition-interface.md, 02-modules/composition.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0130 | 03-interfaces/beast-mode-interface.md, 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0131 | 03-interfaces/git-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0132 | 03-interfaces/deployment-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0133 | 03-interfaces/context-interface.md, 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0134 | 03-interfaces/core-profile-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0135 | 03-interfaces/composition-interface.md, 03-interfaces/deployment-interface.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0136 | 03-interfaces/durability-interface.md, coding-plan/cli-contract-baseline.md, 00-product/user-guide.md, 04-testing/test-cases.md, coding-plan/phase-34.md |
| ADR-0137 | 03-interfaces/llm-provider-interface.md, 03-interfaces/loop-interface.md, 03-interfaces/ui-interface.md, 00-product/user-guide.md, 04-testing/test-cases.md, coding-plan/phase-32.md |
| ADR-0138 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0139 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0140 | 03-interfaces/memory-interface.md, 02-modules/memory.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0141 | 03-interfaces/notes-interface.md, 02-modules/notes.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0142 | 03-interfaces/memory-interface.md, 03-interfaces/notes-interface.md, 02-modules/memory.md, 02-modules/notes.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0143 | 03-interfaces/notes-interface.md, 02-modules/notes.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0144 | 03-interfaces/loop-interface.md, 02-modules/loop.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0145 | 03-interfaces/memory-interface.md, 03-interfaces/notes-interface.md, 02-modules/memory.md, 02-modules/notes.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0146 | 03-interfaces/notes-interface.md, 02-modules/notes.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0147 | 03-interfaces/memory-interface.md, 02-modules/memory.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0148 | 11-rag/rag-architecture.md, 02-modules/rag.md, 03-interfaces/rag-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/phase-35.md |
| ADR-0149 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0150 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0151 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0152 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0153 | 03-interfaces/cli-ops-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0154 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0155 | 02-modules/hooks.md, coding-plan/known-risk.md |
| ADR-0156 | 02-modules/loop.md, 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0157 | 02-modules/loop.md, 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0158 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0159 | 03-interfaces/cli-ops-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0160 | 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0161 | 02-modules/loop.md, 03-interfaces/loop-interface.md, 03-interfaces/llm-provider-interface.md, 03-interfaces/ui-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0162 | 02-modules/loop.md, 03-interfaces/loop-interface.md, 03-interfaces/notes-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0163 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0164 | 02-modules/memory.md, 02-modules/loop.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0165 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 03-interfaces/cli-ops-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0166 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 03-interfaces/cli-ops-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0167 | 02-modules/notes.md, 03-interfaces/notes-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0168 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0169 | 02-modules/loop.md, 02-modules/context.md, 02-modules/memory.md, 03-interfaces/loop-interface.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0170 | 02-modules/loop.md, 02-modules/memory.md, 03-interfaces/loop-interface.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0171 | 02-modules/notes.md, 03-interfaces/notes-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0172 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/phase-35.md |
| ADR-0173 | 02-modules/context.md, 02-modules/configuration.md, 03-interfaces/context-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/phase-35.md |
| ADR-0174 | 02-modules/llm-provider.md, 02-modules/configuration.md, 02-modules/loop.md, 03-interfaces/llm-provider-interface.md, 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/phase-35.md |
| ADR-0175 | 02-modules/configuration.md, 02-modules/llm-provider.md, 03-interfaces/configuration-interface.md, 03-interfaces/llm-provider-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/phase-35.md |
| ADR-0176 | 02-modules/context.md, 03-interfaces/context-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/phase-35.md |
| ADR-0177 | 02-modules/context.md, 03-interfaces/context-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/phase-35.md |
| ADR-0178 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/phase-35.md |
| ADR-0179 | 02-modules/evolution.md, 03-interfaces/evolution-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/phase-35.md |
| ADR-0180 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 02-modules/cli-ops.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0181 | 03-interfaces/durability-interface.md, 02-modules/cli-ops.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0182 | 02-modules/loop.md, 02-modules/memory.md, 02-modules/context.md, 03-interfaces/context-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0183 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0184 | 02-modules/loop.md, 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0185 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0186 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0187 | 02-modules/skills.md, 03-interfaces/skills-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0188 | 02-modules/skills.md, 03-interfaces/skills-interface.md, 03-interfaces/judgment-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0189 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0190 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0191 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/context.md |
| ADR-0192 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/memory.md |
| ADR-0193 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/memory.md |
| ADR-0194 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/memory.md |
| ADR-0195 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/skills.md |
| ADR-0196 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0197 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/cli-ops.md, 02-modules/durability.md |
| ADR-0198 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/durability.md, 02-modules/configuration.md |
| ADR-0199 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/constraints.md, 02-modules/loop.md |
| ADR-0200 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/rag.md, 02-modules/context.md |
| ADR-0201 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/memory.md, 03-interfaces/ui-interface.md |
| ADR-0202 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/evolution.md, 03-interfaces/evolution-interface.md |
| ADR-0203 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/notes.md, 02-modules/rag.md, 03-interfaces/notes-interface.md |
| ADR-0204 | 04-testing/test-cases.md, coding-plan/known-risk.md, 02-modules/durability.md, 02-modules/loop.md, 03-interfaces/durability-interface.md |
| ADR-0205 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0206 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0207 | 02-modules/memory.md, 02-modules/loop.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0208 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0209 | 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0210 | 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0211 | 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0212 | 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0213 | 03-interfaces/skills-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0214 | 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0215 | 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0216 | 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0217 | 03-interfaces/prompts.md, 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0218 | 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0219 | 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0220 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0221 | 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0222 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0223 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0224 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0225 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0226 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0227 | 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0228 | 03-interfaces/prompts.md, 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0229 | 03-interfaces/memory-interface.md, 03-interfaces/evolution-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0230 | 03-interfaces/prompts.md, 03-interfaces/memory-interface.md, 03-interfaces/evolution-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0231 | 03-interfaces/evolution-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0232 | 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0233 | 03-interfaces/memory-interface.md, 03-interfaces/context-interface.md, 02-modules/memory.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0234 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0235 | 02-modules/orchestration.md, 02-modules/beast-mode.md, 02-modules/pet.md, 03-interfaces/orchestration-interface.md, 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0236 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0237 | 03-interfaces/context-interface.md, 03-interfaces/memory-interface.md, 03-interfaces/loop-interface.md, 03-interfaces/orchestration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0238 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0239 | 02-modules/evolution.md, coding-plan/known-risk.md |
| ADR-0240 | 02-modules/pet.md, 03-interfaces/pet-mode-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0241 | 02-modules/memory.md, 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0242 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0243 | 02-modules/loop.md, 03-interfaces/observability-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0244 | 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0245 | 03-interfaces/notes-interface.md, 03-interfaces/context-interface.md, 03-interfaces/skills-interface.md, 03-interfaces/memory-interface.md, 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0246 | 02-modules/skills.md, 03-interfaces/skills-interface.md, 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0247 | 02-modules/loop.md, 03-interfaces/loop-interface.md, 03-interfaces/llm-provider-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0248 | 02-modules/loop.md, 02-modules/tool-use.md, 03-interfaces/loop-interface.md, 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0249 | 02-modules/tool-use.md, 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0250 | 02-modules/configuration.md, 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0251 | 02-modules/memory.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0252 | 03-interfaces/cli-ops-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0253 | 02-modules/loop.md, 03-interfaces/observability-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0254 | 02-modules/durability.md, 02-modules/loop.md, 02-modules/tool-use.md, 03-interfaces/durability-interface.md, 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0255 | 02-modules/loop.md, 02-modules/tool-use.md, 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0256 | 02-modules/tool-use.md, 03-interfaces/tool-use-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0257 | 02-modules/loop.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0258 | 02-modules/loop.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0259 | 02-modules/hooks.md, 02-modules/loop.md, 02-modules/memory.md, 03-interfaces/loop-interface.md, 03-interfaces/memory-interface.md, 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0260 | 02-modules/orchestration.md, 02-modules/loop.md, 02-modules/permission.md, 03-interfaces/orchestration-interface.md, 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0261 | 02-modules/configuration.md, 02-modules/memory.md, 02-modules/rag.md, 03-interfaces/configuration-interface.md, 03-interfaces/prompts.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0262 | 02-modules/loop.md, 02-modules/tool-use.md, 02-modules/configuration.md, 03-interfaces/loop-interface.md, 03-interfaces/tool-use-interface.md, 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0263 | 02-modules/notes.md, 03-interfaces/notes-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0264 | 04-testing/test-cases.md, 00-product/product-definition.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0265 | 02-modules/memory.md, 04-testing/test-cases.md, 00-product/requirements.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0266 | 02-modules/memory.md, 04-testing/test-cases.md, 00-product/requirements.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0267 | 02-modules/memory.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0268 | 02-modules/orchestration.md, 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0269 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0270 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 03-interfaces/configuration-interface.md, 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0271 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0272 | 02-modules/permission.md, 03-interfaces/permission-interface.md, 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0273 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0274 | 02-modules/orchestration.md, 02-modules/tool-use.md, 02-modules/configuration.md, 02-modules/permission.md, 03-interfaces/orchestration-interface.md, 03-interfaces/git-interface.md, 03-interfaces/configuration-interface.md, 03-interfaces/permission-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0275 | 05-development/unattended-ops.md, 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 00-product/user-guide.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0276 | 05-development/unattended-ops.md, 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 03-interfaces/durability-interface.md, 00-product/user-guide.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0277 | 04-testing/test-cases.md, coding-plan/README.md, coding-plan/phase-38.md, coding-plan/Pending-Arbitration.md, coding-plan/known-risk.md |
| ADR-0278 | 03-interfaces/cli-ops-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0279 | 03-interfaces/configuration-interface.md, 03-interfaces/memory-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md, coding-plan/Pending-Arbitration.md |
| ADR-0280 | 03-interfaces/llm-provider-interface.md, 02-modules/llm-provider.md, 03-interfaces/memory-interface.md, 02-modules/memory.md, 03-interfaces/rag-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0281 | 02-modules/orchestration.md, 03-interfaces/orchestration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0282 | 02-modules/loop.md, 03-interfaces/loop-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
| ADR-0283 | 02-modules/llm-provider.md, 03-interfaces/llm-provider-interface.md, 03-interfaces/configuration-interface.md, 04-testing/test-cases.md, coding-plan/known-risk.md |
