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
