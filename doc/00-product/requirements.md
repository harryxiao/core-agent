# CORE-Harness 产品需求文档（Requirements / PRD）

> 版本 v0.1 ｜ 需求编号规则：`CORE-<模块>-R<n>`（本表功能需求编号）；与 `openspec/specs/*` 的命名式 Requirement、`04-testing/test-cases.md` 的 `TC-*` 用例组通过命名与编号区间建立追踪映射（非严格同号）。
> 每条功能需求（FR）必须可追踪到 `openspec/specs/` 中对应的 Requirement；非功能需求（NFR）追踪到架构/测试文档。

---

## 1. 功能需求（Functional Requirements）

### 1.1 插件注册与组合（plugin-registry）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-PLG-R1 | 系统 SHALL 支持注册任意符合插件契约的能力单元，无需改动核心代码 | P0 | plugin-registry/spec.md |
| CORE-PLG-R2 | 系统 SHALL 在插件加载/卸载/升级时记录可逆副作用，支持一键回滚 | P0 | plugin-registry/spec.md |
| CORE-PLG-R3 | 系统 SHALL 解析并注入每个插件的 coeffect（权限/宪章/配置），缺失时拒绝执行 | P0 | plugin-registry/spec.md |
| CORE-PLG-R4 | 系统 SHALL 支持运行时热插拔（HMR）插件，不中断主循环 | P1 | plugin-registry/spec.md |

### 1.2 智能体循环（loop）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-LOOP-R1 | 循环 SHALL 执行 感知→推理→行动→写记忆 四阶段，每轮结束必须写记忆 | P0 | loop/spec.md |
| CORE-LOOP-R2 | 循环 SHALL 支持插件化替换（不同策略可互切），默认实现不超过 ~100 行 | P0 | loop/spec.md |
| CORE-LOOP-R3 | 循环 SHALL 在行动阶段对每个 action 做可逆追踪，异常时可回滚该轮 | P0 | loop/spec.md |
| CORE-LOOP-R4 | 循环 SHALL 遵守人机确认门：不可逆/高风险操作必须先 ask_user | P0 | loop/spec.md |

### 1.3 分层记忆（memory）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-MEM-R1 | 记忆 SHALL 分 L0元规则/L1索引/L2事实/L3技能/L4归档 五层，层间可单向/双向迁移 | P0 | memory/spec.md |
| CORE-MEM-R2 | 记忆 SHALL 支持按相关性检索，控制注入上下文的 token 上界 | P0 | memory/spec.md |
| CORE-MEM-R3 | 记忆 SHALL 支持将 L3 技能"结晶"为插件，及反向"溶解"回记忆 | P0 | memory/spec.md |
| CORE-MEM-R4 | 记忆后端 SHALL 可插拔（文件后端先行），接口与存储解耦 | P1 | memory/spec.md |

### 1.4 工具使用（tool-use）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-TOOL-R1 | 系统 SHALL 提供至少 9 个原子工具插件（code_run/file_*/web_*/ask_user/进程/memory） | P0 | tool-use/spec.md |
| CORE-TOOL-R2 | 每个工具 SHALL 声明 JSON Schema 参数，非法参数调用返回结构化错误 | P0 | tool-use/spec.md |
| CORE-TOOL-R3 | 每个写类工具 SHALL 提供撤销函数（可逆效应），支持时间旅行回滚 | P0 | tool-use/spec.md |
| CORE-TOOL-R4 | 工具执行 SHALL 有超时/资源上限，异常不拖垮主循环 | P1 | tool-use/spec.md |

### 1.5 MCP 集成（mcp）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-MCP-R1 | 系统 SHALL 作为 MCP client 发现并调用外部 MCP server 的 tools | P0 | mcp/spec.md |
| CORE-MCP-R2 | 系统 SHALL 支持读取外部 resources 与 prompts，并纳入 loop 的上下文 | P1 | mcp/spec.md |
| CORE-MCP-R3 | MCP 工具调用 SHALL 同样受可逆追踪与确认门约束 | P0 | mcp/spec.md |
| CORE-MCP-R4 | 系统 SHALL 支持 stdio 与 Streamable HTTP 两种 MCP 传输 | P1 | mcp/spec.md |
| CORE-MCP-R5 | 系统 SHALL 支持 MCP 服务端的注册、连接、心跳与断线重连 | P1 | mcp/spec.md |
| CORE-MCP-R6 | 系统 SHALL 把本地调用透明转发到 MCP，并对 MCP 异常做隔离，不拖垮主循环 | P0 | mcp/spec.md |
| CORE-MCP-R7 | 系统 SHALL 通过白名单控制对外暴露的工具集合，默认最小暴露，命名空间隔离 | P0 | mcp/spec.md |
| CORE-MCP-R8 | 系统 SHALL 支持单一 HTTP(TCP) 连接承载多个会话（Mcp-Session-Id 会话标识，会话与连接解耦） | P1 | mcp/spec.md |
| CORE-MCP-R9 | 系统 SHALL 为每个 MCP 连接建立独立会话，错误隔离不拖垮主循环 | P1 | mcp/spec.md |

### 1.6 进化引擎（evolution）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-EVO-R1 | 进化引擎 SHALL 执行 诊断→提案→验证→评测 四阶段闭环 | P0 | evolution/spec.md |
| CORE-EVO-R2 | 诊断 SHALL 定位缺陷到**单个插件**级别（可归因） | P0 | evolution/spec.md |
| CORE-EVO-R3 | 提案 SHALL 产出世代化的不可变产物，过验证门前不进入运行 | P0 | evolution/spec.md |
| CORE-EVO-R4 | 评测 SHALL 使用留出集，进化在留出集上退化时自动回滚 | P0 | evolution/spec.md |

### 1.7 权限与审批管控（permission）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-PERM-R1 | 系统 SHALL 将操作分为只读/数据编辑/高危三级，高危操作默认拦截（deny-by-default） | P0 | permission/spec.md |
| CORE-PERM-R2 | 系统 SHALL 对高危操作走人工审批流，审批 TTL 超时默认拒绝并审计归档 | P0 | permission/spec.md |
| CORE-PERM-R3 | 系统 SHALL 提供沙箱隔离执行，异常 fail-closed 并自动销毁沙箱 | P0 | permission/spec.md |
| CORE-PERM-R4 | 权限判定 SHALL 与 coeffect 声明联动，越权/缺失一律拒绝执行 | P0 | permission/spec.md |

### 1.8 任务编排（orchestration）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-ORCH-R1 | 编排 SHALL 以状态机驱动任务，非法状态转移拒绝执行 | P0 | orchestration/spec.md |
| CORE-ORCH-R2 | 编排 SHALL 支持子任务拆解并按依赖拓扑执行 | P0 | orchestration/spec.md |
| CORE-ORCH-R3 | 编排 SHALL 支持多 Agent 路由与 TaskHandoff 上下文交接 | P1 | orchestration/spec.md |
| CORE-ORCH-R4 | 编排 SHALL 支持长任务挂起/恢复/取消（断点续跑） | P1 | orchestration/spec.md |
| CORE-ORCH-R5 | 编排 SHALL 支持并行扇出（fan-out/fan-in）波次调度，同波次并行、波次间串行、受资源上限约束 | P1 | orchestration/spec.md |
| CORE-ORCH-R6 | 编排 SHALL 用 Goal/SuccessCriteria（SMART）定义成功标准并追踪进度 | P1 | orchestration/spec.md |
| CORE-ORCH-R7 | 编排 SHALL 支持子任务 priority 优先级字段并按优先级降序调度 | P1 | orchestration/spec.md |

### 1.9 可观测性（observability）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-OBS-R1 | 系统 SHALL 输出结构化 JSONL 日志，并对敏感信息脱敏 | P0 | observability/spec.md |
| CORE-OBS-R2 | 系统 SHALL 聚合指标（完成率/token/循环数/错误率） | P0 | observability/spec.md |
| CORE-OBS-R3 | 每轮 loop SHALL 携带 trace_id 贯穿全链路，支持 replay 复现 | P0 | observability/spec.md |
| CORE-OBS-R4 | 遥测 SHALL 作为单一数据源，统一供给进化经验采集与审批审计 | P1 | observability/spec.md |

### 1.10 约束与容错（constraints）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-CONS-R1 | 系统 SHALL 对工具输入做 schema 校验，对输出做结构化解析 | P0 | constraints/spec.md |
| CORE-CONS-R2 | 系统 SHALL 提供熔断/降级/重试/回滚容错中间件 | P0 | constraints/spec.md |
| CORE-CONS-R3 | 系统 SHALL 提供上下文压缩中间件，控制 token 预算 | P1 | constraints/spec.md |
| CORE-CONS-R4 | 约束 SHALL 作为横切中间件插入 loop 关键节点，可排序可配置 | P0 | constraints/spec.md |

### 1.11 技能封装（skills）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-SKILL-R1 | 系统 SHALL 维护原子技能库，技能有前置条件检查 | P0 | skills/spec.md |
| CORE-SKILL-R2 | 技能 SHALL 支持版本管理与灰度发布，A/B 退化自动回退 | P1 | skills/spec.md |
| CORE-SKILL-R3 | 技能路由 SHALL 按 Top-K 相似度匹配，未命中则沉淀为候选 | P0 | skills/spec.md |
| CORE-SKILL-R4 | 技能库 SHALL 作为 evolution 结晶/溶解的唯一交接面 | P0 | skills/spec.md |

### 1.12 上下文工程（context）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-CTX-R1 | 系统 SHALL 动态装配上下文并按 token 预算裁剪 | P0 | context/spec.md |
| CORE-CTX-R2 | 系统 SHALL 提供信息地图（目录索引 + 按需 fetch + hash 失效重建） | P0 | context/spec.md |
| CORE-CTX-R3 | 系统 SHALL 对多轮对话关键信息自动压实并写回记忆 | P0 | context/spec.md |
| CORE-CTX-R4 | 千页级文档 SHALL 以轻量索引呈现，不挤占有限上下文窗口 | P1 | context/spec.md |

### 1.13 UI 界面与启动模式（ui）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-UI-R1 | 系统 SHALL 提供 CLI、Web、Desktop 三种启动模式，三者共享同一内核与同一 LLM 配置源 | P0 | ui/spec.md |
| CORE-UI-R2 | 系统 SHALL 支持在 Web 与桌面 UI 内配置 LLM provider、endpoint、API key 与 base URL | P0 | ui/spec.md |
| CORE-UI-R3 | 系统 SHALL 在 CLI 模式提供声明式、响应式的终端交互（折叠块、流式输出、多面板、焦点管理），复刻 Claude Code 式 Ink 体验 | P1 | ui/spec.md |
| CORE-UI-R4 | 系统 SHALL 支持以 HTTP 服务 + 单页应用（SPA）形式提供 Web 界面，流式输出通过 SSE 推送 | P0 | ui/spec.md |
| CORE-UI-R5 | 系统 SHALL 支持将桌面端打包为可执行安装文件（Windows / macOS / Linux），并内置拉起本地后端的能力 | P1 | ui/spec.md |
| CORE-UI-R6 | 系统 SHALL 使桌面端复用与 Web 相同的 SPA 构建产物，保证二者体验 100% 一致 | P1 | ui/spec.md |
| CORE-UI-R9 | 系统 SHALL 支持 Web 前端作为纯静态资源独立托管，与常驻 Harness Host 后端解耦部署：前端经统一后端 API 连接 Host，前端升级不要求后端重启 | P0 | ui/spec.md |

### 1.14 IM 网关（im）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-IM-R1 | 系统 SHALL 提供统一 IMGateway 抽象屏蔽各平台协议差异，新增平台仅需实现 Provider 适配器，不改动内核 | P0 | im/spec.md |
| CORE-IM-R2 | 系统 SHALL 将 IM 消息映射为内核会话：入站消息进入同一 loop 执行，执行结果回推到来源会话；同一会话/群内多轮对话保持上下文 | P0 | im/spec.md |
| CORE-IM-R3 | 系统 SHALL 按各平台官方能力接入：Telegram/Discord 用官方 Bot API（webhook 或长轮询）、飞书用开放平台长连接 WebSocket（事件订阅）、微信用企业微信/公众号等合规通道；个人号接入因封号风险不予采用 | P0 | im/spec.md |
| CORE-IM-R4 | 系统 SHALL 对远程控制入口做身份鉴权：仅白名单用户（及群内 @ 机器人）可触发执行，防止陌生人操控 | P0 | im/spec.md |
| CORE-IM-R5 | 系统 SHALL 使 IM 远程调用走与本地一致的 invoke 链路：只读/低危操作放行，高危操作在 IM 内二次确认或拒绝，全部调用标注来源并审计落盘 | P0 | im/spec.md |
| CORE-IM-R6 | 系统 SHALL 为每个平台/用户建立独立会话，多平台多用户并发互不串扰；单连接/单平台故障熔断隔离，不拖垮主循环 | P1 | im/spec.md |

### 1.15 三方大模型归一化接入（llm-provider）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-LLM-R1 | 系统 SHALL 提供统一的 LLMProvider 抽象接口（completion / stream / embedding 三个入口与统一请求 / 响应模型），内核只依赖该接口、不感知具体供应商实现 | P0 | llm-provider/spec.md |
| CORE-LLM-R2 | 系统 SHALL 提供 LiteLLM 默认实现，任意三方 API Key + URL 配置即自动路由到对应 provider 协议，无需逐家编写适配代码 | P0 | llm-provider/spec.md |
| CORE-LLM-R3 | 系统 SHALL 通过依赖注入隔离 LLMProvider 实现，替换 LiteLLM 或接入自研后端时，内核 loop 及所有调用方无需改动即可切换 | P0 | llm-provider/spec.md |
| CORE-LLM-R4 | 系统 SHALL 将超时 / 限流 / 鉴权 / 网络异常统一为领域异常，上层只处理一类错误语义 | P1 | llm-provider/spec.md |
| CORE-LLM-R5 | 系统 SHALL 对模型调用做可观测审计，标注 provider / model 与调用结果，复用既有 observability 链路 | P1 | llm-provider/spec.md |

### 1.16 组合与分发（composition）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-COMP-R1 | 系统 SHALL 提供 profile 命名组合机制，一个 profile 命名一个可复用的插件组合集合，层叠多个 bundle 并叠加用户 patch.yml | P0 | composition/spec.md |
| CORE-COMP-R2 | 系统 SHALL 定义 bundle 作为插件的分发格式，使已结晶的技能可打包、跨部署复用 | P0 | composition/spec.md |
| CORE-COMP-R3 | 系统 SHALL 支持用户 patch.yml 对 profile 组合做局部覆盖，在不改 profile 与 bundle 的前提下按用户差异调整 | P0 | composition/spec.md |
| CORE-COMP-R4 | 系统 SHALL 按「bundle 层叠 + patch.yml 覆盖」的确定顺序解析最终组合，解析结果可逆、可回退 | P0 | composition/spec.md |

### 1.17 分布式协作（distributed）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-DIST-R1 | 系统 SHALL 同时具备 A2A Client 与 A2A Server 两种角色：作为 Client 可委派任务给外部 Agent，作为 Server 可对外暴露自身能力被外部 Agent 调用 | P0 | distributed/spec.md |
| CORE-DIST-R2 | 系统 SHALL 以 AgentCard 声明自身能力并支持签名与验证，供对等 Agent 发现与协商 | P0 | distributed/spec.md |
| CORE-DIST-R3 | 系统 SHALL 支持 A2A 三种协议绑定：JSON-RPC 2.0 over HTTP(S) 为默认/推荐，gRPC 与 REST 为备选，并保留自定义绑定能力 | P0 | distributed/spec.md |
| CORE-DIST-R4 | 系统 SHALL 支持 OAuth2 / mTLS / APIKey / OpenIdConnect 鉴权，跨设备调用按最小权限 scope 授权，高危操作复用既有 permission 审批链路 | P0 | distributed/spec.md |
| CORE-DIST-R5 | 系统 SHALL 支持云端 / 个人 PC / 移动终端 / 嵌入式四类设备分布式拓扑，实现控制面/执行面分离 | P0 | distributed/spec.md |
| CORE-DIST-R6 | 系统 MAY 支持可选的设备间 P2P 直连优化（公钥寻址、NAT 打洞直连优先、失败回退 relay、QUIC 传输），不改变上层 A2A 协议行为 | P2 | distributed/spec.md |
| CORE-DIST-R7 | 系统 SHALL 遵循 A2A 与 MCP 互补：A2A Server 内部经 MCP 调用底层工具/数据，Agent 间协作走 A2A、能力调用走 MCP | P0 | distributed/spec.md |

### 1.18 检索增强生成（rag）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-RAG-R1 | 系统 SHALL 以 sqlite-vec 作为本地嵌入式向量库存储文档向量与索引：零服务、零外部依赖，与既有 SQLite 生态统一 | P0 | rag/spec.md |
| CORE-RAG-R2 | 系统 SHALL 提供文档摄取管线：导入→分块→生成 embedding→建向量索引，并支持增量更新与索引失效检测 | P0 | rag/spec.md |
| CORE-RAG-R3 | 系统 SHALL 用 sentence-transformers + BGE 本地推理生成 embedding，无需外部 API；可经 llm-provider 归一化入口切换远端模型 | P0 | rag/spec.md |
| CORE-RAG-R4 | 系统 SHALL 按向量相似度检索 top-k 最相关片段、弥补 LLM 知识缺口，结果带相关度得分 | P0 | rag/spec.md |
| CORE-RAG-R5 | 系统 SHALL 将检索片段经 context 装配器按预算裁剪后注入 llm-provider 生成，检索缺失时降级为纯 LLM 生成 | P0 | rag/spec.md |
| CORE-RAG-R6 | 系统 SHALL 保持与 codebase-memory-mcp 互补：RAG 管知识文档语义检索，codebase-memory-mcp 管代码结构结构化理解 | P1 | rag/spec.md |

### 1.19 版本控制（git）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-GIT-R1 | 系统 SHALL 提供 Git 核心操作：clone/init/commit/branch/checkout/diff/merge/log/status/pull/push | P0 | git/spec.md |
| CORE-GIT-R2 | 系统 SHALL 保护 .git 元数据与工作区完整性：默认拒绝修改 .git 内部文件，操作失败不损坏工作区 | P0 | git/spec.md |
| CORE-GIT-R3 | 系统 SHALL 保证 Git 凭据安全：凭据经 keychain 存储不落盘明文，日志与报错不泄露凭据 | P0 | git/spec.md |
| CORE-GIT-R4 | 系统 SHALL 让高危 Git 操作（强制推送/删除远程分支/历史改写）走 permission 审批链与沙箱约束 | P0 | git/spec.md |

### 1.20 部署与托管（deployment）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-DEP-R1 | 系统 SHALL 支持自托管优先的运行环境：以抽象运行环境（进程级/容器级，不锁定选型）承载 Core-Agent 及子模块，提供环境配置、依赖装配与启动引导，一套部署可在 PC/服务器/边缘设备运行 | P0 | deployment/spec.md |
| CORE-DEP-R2 | 系统 SHALL 提供发布与升级能力：版本化发布、滚动升级与回滚，升级失败回退到上一可用版本，不处于半升级状态 | P0 | deployment/spec.md |
| CORE-DEP-R3 | 系统 SHALL 提供健康检查与生命周期管理：暴露探活端点，支持启动/停止/重启，异常时告警或自动恢复 | P0 | deployment/spec.md |
| CORE-DEP-R4 | 系统 SHALL 支持可选云托管 BYOC：允许部署到用户自选云平台，与自托管共享同一部署抽象与配置，不绑定特定云厂商 | P1 | deployment/spec.md |
| CORE-DEP-R5 | 系统 SHALL 提供 Harness Host 常驻服务形态：单一 Host 进程常驻运行，承载 Core-Agent 内核并作为统一接入端点，支持多个 Web/Desktop 客户端并发接入，各客户端建立独立会话、互不串扰 | P0 | deployment/spec.md |

### 1.21 核心画像（core-profile）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-PROF-R1 | 系统 SHALL 支持两级 Core.md 灵魂文件：全局级 `~/.core/Core.md`（承载人格、宪法与全局规则）在启动时读取，项目级 `<project>/Core.md`（承载项目信息）在载入项目时读取，塑造 Agent 行为特色与约束 | P0 | core-profile/spec.md |
| CORE-PROF-R2 | 系统 SHALL 将 Core.md 内容划分双语义分区：宪法与全局规则以 constitution:v1 coeffect 注入为必保约束，人格落 L0 记忆层作元策略与人格预设，两分区职责不重叠 | P0 | core-profile/spec.md |
| CORE-PROF-R3 | 系统 SHALL 由 ContextEngine 按当前工作目录向上逐级查找项目级 Core.md 并注入上下文，未命中时不注入项目级内容且不报错 | P0 | core-profile/spec.md |
| CORE-PROF-R4 | 系统 SHALL 定义多级合并优先级：项目级覆盖全局级；Core.md 与 CLAUDE.md 分工并存，Core-Agent 仅读取 Core.md、不加载 CLAUDE.md，二者互不干扰 | P0 | core-profile/spec.md |
| CORE-PROF-R5 | 系统 SHALL 对 Core.md 做格式校验与容错：文件缺失静默降级，格式非法告警并跳过非法分区，不阻断启动或载入 | P0 | core-profile/spec.md |
| CORE-PROF-R6 | 系统 SHALL 提供 Core.md 的题词编写规范，指导用户以可判定、可注入的方式编写各分区内容：宪法与全局规则分区采用命令式可判定句式（每条以「必须/禁止」表述、可判定真伪，不承载具体操作细节），人格分区采用结构化描述（身份/工作风格/沟通风格/决策偏好/边界意识），项目信息分区仅承载项目特有信息且不重复全局规则，单个 Core.md 篇幅受控（建议不超过 50 行，细节下沉 L2/L3 记忆层） | P0 | core-profile/spec.md |
| CORE-PROF-R7 | 系统 SHALL 提供 Core.md 题词模板（骨架），引导用户按「宪法与全局规则/人格/项目信息」三段式结构填写两级文件：全局级模板含「宪法与全局规则」「人格」两个分区，项目级模板含「项目信息」分区，模板附分区注入说明注释，注明各分区内容落向的运行时通道 | P0 | core-profile/spec.md |

---

## 2. 非功能需求（Non-Functional Requirements）

### 2.1 可观测性（Observability）

| ID | 需求 | 目标 | 追踪 |
|---|---|---|---|
| CORE-NFR-OBS1 | 所有副作用可追踪、可回放 | 100% 写操作有审计日志 | adr.md / test-plan |
| CORE-NFR-OBS2 | 结构化日志（trace-id 贯穿一轮 loop） | 单轮可复现 | test-plan |

### 2.2 性能（Performance）

| ID | 需求 | 目标 |
|---|---|---|
| CORE-NFR-PERF1 | loop 单轮延迟（不含 LLM） | < 50ms |
| CORE-NFR-PERF2 | 记忆检索延迟 | < 100ms（1 万条事实规模） |
| CORE-NFR-PERF3 | 插件热插拔 | < 1s 完成加载/卸载 |

### 2.3 可靠性与安全（Reliability & Safety）

| ID | 需求 | 目标 |
|---|---|---|
| CORE-NFR-REL1 | 进化回滚成功率 | 100% |
| CORE-NFR-SEC1 | 密钥/敏感文件 | 只引用不读取，禁止进入日志/记忆 |
| CORE-NFR-SEC2 | 不可逆操作（rm/写系统/杀进程） | 必须人工确认 |
| CORE-NFR-SEC3 | 爆炸半径控制 | 单次操作影响面可预估、可回退 |

### 2.4 可移植性 / 兼容性（Portability）

| ID | 需求 | 目标 |
|---|---|---|
| CORE-NFR-PORT1 | 运行环境 | Python 3.11+，跨 Linux/macOS/Windows |
| CORE-NFR-PORT2 | MCP 协议版本 | 兼容 MCP 最新稳定版 |

---

## 3. 需求优先级说明

- **P0（Must）**：MVP 验收必需，缺一不可。
- **P1（Should）**：MVP 应有，确有正当理由可延期。
- **P2（May）**：可选，后续迭代。

---

## 4. 关联文档

- 产品定义：`doc/00-product/product-definition.md`
- 规格（可追踪的唯一事实来源）：`doc/openspec/specs/*`
- 测试用例：`doc/04-testing/test-cases.md`
