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
| CORE-OBS-R5 | 系统 SHALL 为遥测内存缓冲设上限并溢出兜底，导出失败按指数退避重试与背压，不阻塞主循环 | P1 | observability/spec.md |

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
| CORE-UI-R7 | 系统 SHALL 支持图像与语音等多模态输入的接入，并统一路由到具备对应能力的模型处理 | P1 | ui/spec.md |
| CORE-UI-R8 | 系统 SHALL 支持将内核生成的文本回复以流式 TTS 合成语音实时播报，允许用户在播报过程中打断（barge-in），并保留语音与文本会话上下文的双向引用 | P1 | ui/spec.md |
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
| CORE-LLM-R2 | 系统 SHALL 提供 OpenAI 兼容 stdlib 默认实现，任意 OpenAI 兼容 API Key + URL 配置即路由到对应端点，无需逐家编写适配代码 | P0 | llm-provider/spec.md |
| CORE-LLM-R3 | 系统 SHALL 通过依赖注入隔离 LLMProvider 实现，替换默认实现或接入自研后端时，内核 loop 及所有调用方无需改动即可切换 | P0 | llm-provider/spec.md |
| CORE-LLM-R4 | 系统 SHALL 将超时 / 限流 / 鉴权 / 网络异常统一为领域异常，上层只处理一类错误语义 | P1 | llm-provider/spec.md |
| CORE-LLM-R5 | 系统 SHALL 对模型调用做可观测审计，标注 provider / model 与调用结果，复用既有 observability 链路 | P1 | llm-provider/spec.md |
| CORE-LLM-R6 | 系统 SHALL 保障模型调用的可靠性：调用失败自动重试（retry，指数退避）、超时（timeout）控制、服务降级（degrade 切换备用 provider/model）、底层连接复用（connection reuse / keep-alive）、流式（stream）响应断流可恢复 | P1 | llm-provider/spec.md |

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
| CORE-DIST-R8 | 系统 SHALL 管理 A2A 对等连接的完整生命周期：连接保活（keepalive 心跳/heartbeat）与超时（timeout）检测、断线自动重连（reconnect，指数退避）、连接与任务资源显式释放、委派重试幂等（同一任务不重复执行） | P0 | distributed/spec.md |

### 1.18 检索增强生成（rag）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-RAG-R1 | 系统 SHALL 以本地嵌入式零服务向量库存储文档向量与索引：零服务、零三方依赖，落盘 `$CORE_STATE_DIR` 且跨进程复用；记录向量维度，不一致时结构化拒绝（默认实现 stdlib `sqlite3`） | P0 | rag/spec.md |
| CORE-RAG-R2 | 系统 SHALL 提供文档摄取管线：导入→分块→生成 embedding→建向量索引，并支持增量更新与索引失效检测 | P0 | rag/spec.md |
| CORE-RAG-R3 | 系统 SHALL 本地优先、零外呼地生成 embedding（默认 `HashEmbedder` 离线降级基线）；配置远端模型后经 llm-provider 归一化入口切换 | P0 | rag/spec.md |
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
| CORE-GIT-R5 | 系统 SHALL 保障远程 Git 操作（clone/pull/push）的可靠性：网络超时（timeout）控制、认证失败明确报错不泄露凭据、断线自动重试（retry，指数退避）、操作结束释放连接资源 | P0 | git/spec.md |

### 1.20 部署与托管（deployment）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-DEP-R1 | 系统 SHALL 支持自托管优先的运行环境：以抽象运行环境（进程级/容器级，不锁定选型）承载 Core-Agent 及子模块，提供环境配置、依赖装配与启动引导，一套部署可在 PC/服务器/边缘设备运行 | P0 | deployment/spec.md |
| CORE-DEP-R2 | 系统 SHALL 提供发布与升级能力：版本化发布、滚动升级与回滚，升级失败回退到上一可用版本，不处于半升级状态 | P0 | deployment/spec.md |
| CORE-DEP-R3 | 系统 SHALL 提供健康检查与生命周期管理：暴露探活端点，支持启动/停止/重启，异常时告警或自动恢复 | P0 | deployment/spec.md |
| CORE-DEP-R4 | 系统 SHALL 支持可选云托管 BYOC：允许部署到用户自选云平台，与自托管共享同一部署抽象与配置，不绑定特定云厂商 | P1 | deployment/spec.md |
| CORE-DEP-R5 | 系统 SHALL 提供 Harness Host 常驻服务形态：单一 Host 进程常驻运行，承载 Core-Agent 内核并作为统一接入端点，支持多个 Web/Desktop 客户端并发接入，各客户端建立独立会话、互不串扰 | P0 | deployment/spec.md |
| CORE-DEP-R6 | 系统 SHALL 在客户端断线或超时后完成会话清理与资源释放，不影响其他并发客户端 | P0 | deployment/spec.md |

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

### 1.22 持久性（durability）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-DUR-R1 | 系统 SHALL 支持显式创建检查点（checkpoint）与快照（snapshot），在执行任意时刻捕获执行态（执行上下文、任务状态、中间结果、记忆、会话状态），形成带唯一标识与元数据（时间戳、任务/会话归属、父检查点）的可寻址快照，创建不阻塞任务执行 | P0 | durability/spec.md |
| CORE-DUR-R2 | 系统 SHALL 支持崩溃恢复（crash recovery）：执行进程意外中断后，从最近有效检查点恢复执行态，未完成步骤幂等续跑，已持久化结果不丢失；最近检查点损坏时回退到更早有效检查点并记录告警 | P0 | durability/spec.md |
| CORE-DUR-R3 | 系统 SHALL 支持执行态级时间旅行（time-travel）：将执行态回滚到任意历史检查点，沿快照差异逆序撤销写类工具副作用（复用 tool-use 可逆效应），与副作用级 EffectId undo 栈协同，不新建撤销机制 | P1 | durability/spec.md |
| CORE-DUR-R4 | 系统 SHALL 支持检查点生命周期管理：按保留策略（retention policy，数量上限/时间窗口/存储配额）自动清理过期检查点，避免无限增长；被标记的关键检查点（pinned）不受自动清理影响 | P1 | durability/spec.md |

### 1.23 配置管理（configuration）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-CFG-R1 | 系统 SHALL 以 config.yaml 为单一配置收口，支持 env 环境变量覆盖与默认值兜底（env > yaml > default），并作为 llm-provider / ui / im / git / judgment 配置语义的上层挂载能力 | P0 | configuration/spec.md |
| CORE-CFG-R2 | 系统 SHALL 将 LLM 配置（provider / model / endpoint / api_key）设为必选项，缺失或非法时阻断启动并报明确错误 | P0 | configuration/spec.md |
| CORE-CFG-R3 | 系统 SHALL 提供模块级 feature flag 开关（features 段），被关闭的功能模块不加载、不初始化 | P1 | configuration/spec.md |
| CORE-CFG-R4 | 系统 SHALL 对敏感密钥采用 env / keychain 分级存储：config.yaml 中只允许 `${VAR}` 引用，禁止明文；日志与报错中脱敏 | P0 | configuration/spec.md |
| CORE-CFG-R5 | 系统 SHALL 支持 IM 模块（账户 / ID / 密钥）接入信息配置，密钥经 env / keychain 引用，不落明文 | P0 | configuration/spec.md |
| CORE-CFG-R6 | 系统 SHALL 对配置做 schema 校验，校验通过才生效；变更即生效；写入失败回滚不留半写状态 | P1 | configuration/spec.md |
| CORE-CFG-R7 | 系统 SHALL 将决策模型（judgment）配置（provider / model / base_url / api_key / confidence_threshold）纳入 ConfigSpec 单一真源，api_key 分级存储不落明文，未配置时关闭决策能力、主 LLM 兜底 | P1 | configuration/spec.md |

### 1.24 技能市场（skillhub）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-SKH-R1 | 系统 SHALL 提供市场技能目录，支持按关键字搜索与按源列出；source 参数预留多源扩展，默认官方源 | P1 | skillhub/spec.md |
| CORE-SKH-R2 | 系统 SHALL 支持技能下载并在下载前校验签名；下载的技能以 draft 状态注册到 SkillLibrary，不自动启用 | P0 | skillhub/spec.md |
| CORE-SKH-R3 | 系统 SHALL 支持技能发布并经过审核流 uploaded → pending → published/rejected；审核通过后 VersionManager 版本 v1→v2 | P1 | skillhub/spec.md |
| CORE-SKH-R4 | 系统 SHALL 在签名校验失败时拒绝下载并返回 SIGNATURE_INVALID | P0 | skillhub/spec.md |
| CORE-SKH-R5 | 系统 SHALL 按 source 路由市场源；源不健康时回退官方源，源不存在时拒绝路由（默认单官方源起步） | P1 | skillhub/spec.md |

### 1.25 CI/CD 交付流水线（ci-cd）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-CICD-R1 | 系统 SHALL 提供 lint/typecheck/test/build 四道质量门禁；任一门禁失败阻断交付，门禁实现引用 development-toolchain | P1 | ci-cd/spec.md |
| CORE-CICD-R2 | 系统 SHALL 提供版本化制品打包与发布通道；制品可追溯、可回滚 | P1 | ci-cd/spec.md |

### 1.26 CLI 运维命令面（cli-ops）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-CLIOPS-R1 | 系统 SHALL 提供统一的 CLI 运维命令集，覆盖生命周期/状态/资产/连接/安全/网关六组命令 | P1 | cli-ops/spec.md |
| CORE-CLIOPS-R2 | 系统 SHALL 建立启动参数与配置项的一一对应，优先级链 CLI flag > env > config.yaml > 默认值，映射由 ConfigSpec 单一真源声明 | P1 | cli-ops/spec.md |

### 1.27 宠物模式（pet-mode）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-PET-R1 | 系统 SHALL 管理宠物会话的启动、休眠、恢复、异常退避、终止全生命周期，复用 Loop.run() 同步薄壳逐次唤醒 | P1 | pet-mode/spec.md |
| CORE-PET-R2 | 系统 SHALL 支持重复简单任务（信息收集、闲逛探索）作为宠物会话的可分配任务类型 | P1 | pet-mode/spec.md |
| CORE-PET-R3 | 系统 SHALL 保证宠物低优先级让行：休眠/让行复用 orchestration 任务状态机 SUSPENDED，主循环 busy 时宠物不抢锁、不阻塞主循环 | P1 | pet-mode/spec.md |
| CORE-PET-R4 | 系统 SHALL 追踪主 Agent（主人）偏好，以 MemoryEntry.source=user 落 L2 facts 层 | P1 | pet-mode/spec.md |
| CORE-PET-R5 | 系统 SHALL 支持三入口激活宠物会话：/pet 斜杠命令（候选经 list_tools 拉取）、pet <verb> CLI argv（CommandGroup 扩展）、WebUI 自然语言激活（消息驱动会话） | P1 | pet-mode/spec.md |
| CORE-PET-R6 | 系统 SHALL 支持宠物定期与主 Agent 沟通/反馈，并基于主人偏好制造惊喜（代办/取悦主人当前不太重要的事） | P1 | pet-mode/spec.md |
| CORE-PET-R7 | 系统 SHALL 将宠物实现为解耦的四层架构：基础属性层（角色/性格/喜好/物种）、自主目标循环层、探索工具集层、安全边界层；各层可独立配置与替换 | P1 | pet-mode/spec.md |
| CORE-PET-R8 | 系统 SHALL 支持同时管理多只宠物，每只宠物拥有独立会话、独立人格、独立任务队列，互不干扰、可独立启停 | P1 | pet-mode/spec.md |
| CORE-PET-R9 | 系统 SHALL 支持通过 pet.md/prompt 为每只宠物设定角色、性格、喜好，宠物行为与输出风格受其人格约束 | P1 | pet-mode/spec.md |
| CORE-PET-R10 | 系统 SHALL 提供宠物角色库，支持从预置角色模板创建宠物、自定义角色、导入/导出角色定义 | P1 | pet-mode/spec.md |
| CORE-PET-R11 | 系统 SHALL 为宠物提供受限探索工具集（只读优先），供信息收集与闲逛探索使用，工具清单可配置、需授权 | P1 | pet-mode/spec.md |
| CORE-PET-R12 | 系统 SHALL 为宠物行为施加安全边界：只读优先、不可逆操作禁止、爆炸半径可控、越界即暂停并通知主人 | P1 | pet-mode/spec.md |
| CORE-PET-R13 | 系统 SHALL 支持宠物主动通知主人（如「发现插件X一键生成测试用例，帮你试3次都成功」），通知异步投递、不阻塞主循环 | P1 | pet-mode/spec.md |
| CORE-PET-R14 | 系统 SHALL 支持宠物执行日常随机小任务（终端散步、系统小提示、给代码加无厘头注释），其中侵入性任务可配置关闭 | P1 | pet-mode/spec.md |

### 1.28 神兽召唤（beast-mode）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-BEAST-R1 | 系统 SHALL 内置 20 个山海经神兽作为只读注册表，每兽以 agent_id=beast.<拼音> 唯一标识，含称号/领域职责/独有神通/能力标签，区别于 pet.md 用户自定义 | P1 | beast-mode/spec.md |
| CORE-BEAST-R2 | 系统 SHALL 以 DORMANT/MANIFEST/ACTIVE/RECALLED 四态管理神兽会话，多实例并发（dict[agent_id, BeastSession]），兽间并行、兽内串行 | P1 | beast-mode/spec.md |
| CORE-BEAST-R3 | 系统 SHALL 将召唤实现为 MultiAgentRouter.handoff（神兽为内置 AgentProfile），复用编排层交接语义，不另造第二真源 | P1 | beast-mode/spec.md |
| CORE-BEAST-R4 | 系统 SHALL 让神兽以独立 AgentProfile.loop 运行（独立记忆命名空间 source=beast.<agent_id> + 独立上下文），共享全局 ToolProvider（L1 工具运行时共享）+ 全局 SkillLibrary（L3 技能注册共享，运行时调用 deferred） | P1 | beast-mode/spec.md |
| CORE-BEAST-R5 | 系统 SHALL 为每兽注册独有神通 Skill（beast.<拼音>.<skill>）进全局 SkillLibrary，专属路由（他兽不可路由，runtime 调用 deferred） | P1 | beast-mode/spec.md |
| CORE-BEAST-R6 | 系统 SHALL 异步并发执行召唤（handoff 经 loop.arun 非阻塞，多兽并行），据 LoopResult.failed 判定成败自动回归，记忆分区封存 | P1 | beast-mode/spec.md |
| CORE-BEAST-R7 | 系统 SHALL 支持手动复位（/recall <beast> + recall <beast> CLI + NL「召回」）按 beast_id 复位至 RECALLED | P1 | beast-mode/spec.md |
| CORE-BEAST-R8 | 系统 SHALL 支持三入口召唤（/summon 斜杠 + summon <beast> [task] CLI + WebUI 自然语言），三入口同源 | P1 | beast-mode/spec.md |

### 1.29 决策（judgment）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-JDG-R1 | 系统 SHALL 提供 choice（选项路由）/score（评分筛选）/noul（布尔判断）三类决策原语作为统一决策入口，供 loop/orchestration/evolution 在决策点调用 | P1 | judgment/spec.md |
| CORE-JDG-R2 | 系统 SHALL 经 JEV/TypeSafe「System One」决策小模型（POST /v1/systemone：state + typed questions → typed answers，答案按原语分形）接入决策原语，Provider 懒加载、api_key/base_url/model 挂载 | P1 | judgment/spec.md |
| CORE-JDG-R3 | 系统 SHALL 在决策 confidence 低于配置阈值时回退主 LLM 重新决策，并标注回退轨迹，保证决策质量下限 | P1 | judgment/spec.md |
| CORE-JDG-R4 | 系统 SHALL 将每次决策轨迹（输入 state、原语类型、选项、结果、置信度、是否回退）落 observability 链路，供进化与审批消费 | P1 | judgment/spec.md |

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
| CORE-NFR-PERF2 | 记忆检索延迟 | < 100ms（1 万条事实规模）；**实测未达标**：中位 ≈657ms（change `0275`／ADR-0265，修复待立项） |
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
