# 统一数据模型（Data Model）

> 版本 v0.1 ｜ 本文是 Core-Agent 各层数据结构实体的**单一权威索引 + 命名冲突裁决**。
> 权威定义仍以各接口文档（`03-interfaces/*`）内的 class/字段为准；本文只做跨层收敛索引与裁决，**不重复定义字段**。
> 数据结构属"how"（实现细节），不进 openspec 行为规格（`specs/*`）；命名裁决见 `adr.md` ADR-0027。
> 本文是 `architecture-overview.md`（工程化展开）的**数据视图**。

---

## 1. 定位与使用约定

1. **单一索引**：任何跨层实体（Plugin / Effect / MemoryEntry 等）在此登记「所属层 + 语义 + 权威定义位置」，避免各接口各自为政。
2. **权威定义在接口文档**：本文字段名仅为索引，字段语义冲突以接口文档为准；但**命名冲突以 §3 裁决为准**。
3. **不重复定义**：本文不新建字段表，避免与接口文档双源漂移。
4. **收敛节奏**：受 §3 影响的接口命名，在**编码阶段首个 change** 中统一改名（与 review 结论一致，不在本文执行）。

---

## 2. 分层实体清单

### L0 组合基底（一切皆插件）

| 实体 | 语义 | 权威定义 |
|---|---|---|
| Plugin | 可替换能力单元（id / version / deps） | plugin-registry-interface.md |
| Effect | 副作用 + 撤销函数（支持时间旅行） | plugin-registry-interface.md |
| ResolvedContext | coeffect 解析注入结果（权限/宪章/配置） | plugin-registry-interface.md |
| coeffect | 注入式环境依赖（声明→解析→注入） | plugin-registry-interface.md |

### L1 原子工具

| 实体 | 语义 | 权威定义 |
|---|---|---|
| ToolDef | 工具 schema 声明 | tool-use-interface.md |
| ToolResult | 工具执行结果（含可逆效应） | tool-use-interface.md |
| EffectId | 可逆效应句柄（供撤销） | tool-use-interface.md |
| GateDecision | 权限门裁决结果 | tool-use-interface.md |

### L2 记忆

| 实体 | 语义 | 权威定义 |
|---|---|---|
| Layer | 记忆分层枚举（L0–L4） | memory-interface.md |
| MemoryEntry | 记忆条目 | memory-interface.md |
| MemoryIndex | 记忆索引 | memory-interface.md |
| IndexEntry | 索引项 | memory-interface.md |
| PluginCandidate | 待结晶的插件候选 | memory-interface.md |
| MemoryBackend | 记忆后端抽象 | memory-interface.md |

### L3 循环 / 上下文 / 技能

| 实体 | 语义 | 权威定义 |
|---|---|---|
| LoopContext | 循环上下文 | loop-interface.md |
| LoopResult | 循环结果 | loop-interface.md |
| Action | 待执行动作 | loop-interface.md |
| ActionResult | 动作结果 | loop-interface.md |
| Step | 循环步骤 | loop-interface.md |
| ContextPack | 信息地图 | context-interface.md |
| Pointer | 记忆指针 | context-interface.md |
| MapEntry | 信息地图条目 | context-interface.md |
| Compaction | 上下文压实产物 | context-interface.md |
| Skill | 技能封装（版本/灰度/路由） | skills-interface.md |
| SkillMatch | 技能匹配结果 | skills-interface.md |
| ABResult | A/B 实验结果 | skills-interface.md |

### L3.5 编排

| 实体 | 语义 | 权威定义 |
|---|---|---|
| TaskState | 任务状态 | orchestration-interface.md |
| StateMachine | 状态机 | orchestration-interface.md |
| Subtask | 子任务 | orchestration-interface.md |
| Plan | 执行计划 | orchestration-interface.md |
| VerifyResult | 校验结果 | orchestration-interface.md |
| TaskHandoff | 任务交接 | orchestration-interface.md |
| AgentProfile | Agent 画像 | orchestration-interface.md |

### L4 进化引擎

| 实体 | 语义 | 权威定义 |
|---|---|---|
| DiagnosisReport | 诊断报告 | evolution-interface.md |
| GenerationCandidate | 提案候选 | evolution-interface.md |
| GateReport | 门禁报告 | evolution-interface.md |
| EvalReport | 评测报告 | evolution-interface.md |
| EvolutionOutcome | 进化产出（落 memory/skills） | evolution-interface.md |

### L5 组合与分发

| 实体 | 语义 | 权威定义 |
|---|---|---|
| Profile | 分发 profile（name/version/hash/plugin_refs） | composition-interface.md |
| Bundle | 分发 bundle | composition-interface.md |
| PatchSpec | 覆盖补丁规格 | composition-interface.md |
| ResolvedSet | 解析后的插件集合 | composition-interface.md |
| PluginRef | 插件引用 | composition-interface.md |

### 横切（不属于任一层）

| 实体 | 语义 | 权威定义 |
|---|---|---|
| LLMRequest / LLMResponse / TokenUsage / Embedding | LLM 归一化调用 | llm-provider-interface.md |
| AgentCard | 对端 Agent 名片 | distributed-interface.md |
| RiskLevel | 风险等级 | permission-interface.md |
| ApprovalRequest / Ticket | 审批请求/工单 | permission-interface.md |
| TraceEvent / Tracer / MetricsCollector | 遥测（日志/指标/追踪） | observability-interface.md |
| Middleware / ExecContext | 约束与容错中间件 | constraints-interface.md |
| MCPEndpoint / RemoteTool | MCP 外部能力 | mcp-interface.md |
| IMProvider / Message | IM 入站消息归一化 | im-interface.md |
| Checkpoint / Snapshot / RestoreHandle / RetentionPolicy | 执行态持久化（检查点/快照/恢复/保留） | durability-interface.md |
| InstallableAsset / PluginSource | 统一插件安装资产 / 来源枚举（kind∈skill\|mcp\|cli，source∈local-path\|git-repo\|market-registry\|mcp-endpoint，manifest，lifecycle） | plugin-registry-interface.md |

---

## 3. 命名冲突裁决（ADR-0027）

> 裁决为**收敛目标**；接口文档改名在编码阶段首个 change 执行。

| # | 名称 | 冲突双方 | 语义差异 | 裁决 |
|---|---|---|---|---|
| 1 | Message | llm-provider vs im | LLM 对话消息（role/content） vs IM 入站消息（platform/user_id/text/is_group/session_key） | 前缀区分：`LLMMessage` / `IMMessage` |
| 2 | Profile/Bundle/Patch | composition(L5) vs plugin-registry(L0) | 静态分发产物（name/version/hash/plugin_refs） vs 运行时组合结果（active/coeffect_sources/compose()） | L5 分发侧保留原名；L0 运行时组合侧加 `Compose` 前缀 |
| 3 | Trace | loop / evolution / observability | 执行轨迹 vs 诊断输入（消费 loop 轨迹） vs 遥测 | loop 持有 `Trace` 主语义；evolution 不新建类型（消费）；observability 已用 `TraceEvent` 区分 |
| 4 | Task | orchestration vs distributed | 编排任务（TaskState/Subtask/Plan） vs 委派任务（Task/TaskHandle） | orchestration 保留 `Task` 主语义；distributed 委派侧改 `RemoteTask`（`TaskHandle` 保留） |
| 5 | Session | im 引用未定义 | IM 会话上下文 | 本文补定义（见 §4） |

---

## 4. 待补定义实体

以下实体被接口引用但无定义，本文补语义（字段以编码阶段落地为准）：

| 实体 | 引用方 | 补定义语义 |
|---|---|---|
| Session | im-interface（reply(session, text)） | IM 会话上下文：platform + session_key + 群组标记 |
| ExecContext | constraints-interface（中间件） | 中间件执行上下文（请求/响应 + 链路信息） |
| ExecRequest / ExecResponse | constraints-interface（中间件） | 中间件执行请求 / 响应包装 |

---

## 5. 关键数据流（热路径）

```text
LoopContext ──coeffect──▶ ResolvedContext ──▶ Action ──▶ ToolResult(EffectId)
                                                          │
                                                          ▼
                                                MemoryEntry/MemoryIndex（L2）
                                                          │
                                                          ▼
                                             DiagnosisReport ──▶ GenerationCandidate
                                             （L4 进化，产物结晶落 memory/skills）
```

---

## 6. 关联文档

- 架构总览：`doc/01-architecture/architecture-overview.md`
- 架构决策：`doc/01-architecture/adr.md`（ADR-0027）
- 接口契约：`doc/03-interfaces/*`（权威定义）
