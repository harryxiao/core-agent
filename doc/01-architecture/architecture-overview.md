# CORE-Harness 架构总览（Architecture Overview）

> 版本 v0.2 ｜ 本文给出**总体架构**：分层模型、组件职责、数据流、部署视图。
> 详细决策取舍见 `adr.md`；模块内部细节见 `02-modules/*`；接口契约见 `03-interfaces/*`。
> 与 `core_harness_architecture.md`（架构原始构想）一一对应，本文是其"工程化"展开。

---

## 1. 架构总纲

CORE-Harness 采用**无特权核心（No Privileged Core）+ 分层插件化**架构。核心只有一层薄薄的
"组合基底"（L0），其余——循环、记忆、进化引擎、模型适配器——**全部是插件**，可在运行时替换。
在分层主链之外，另有 **4 个横切能力**（权限、约束、可观测、持久性）贯穿所有层，统一收口安全与质量。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        L5 组合分发（Composition & Distribution）          │
│              profile（配置集） · bundle（能力集） · patch（进化补丁）      │
├─────────────────────────────────────────────────────────────────────────┤
│                     L4 进化引擎（Evolution Engine）                        │
│        诊断(Diagnose) → 提案(Propose) → 验证(Validate) → 评测(Eval)       │
│              ── 留出评测 held-out · 验证门 gate · 世代 generation          │
├─────────────────────────────────────────────────────────────────────────┤
│                  L3.5 任务编排（Orchestration）                            │
│        任务状态机 · 子任务拓扑 · TaskHandoff 交接 · 断点续跑               │
├─────────────────────────────────────────────────────────────────────────┤
│                     L3 智能体循环（Agent Loop）                            │
│              感知(Perceive) → 推理(Reason) → 行动(Act) → 写记忆(Remember) │
│   context 上下文工程(信息地图·压实·预算) · skills 技能封装(版本/灰度/路由)  │
├─────────────────────────────────────────────────────────────────────────┤
│                 L2 分层记忆（Layered Memory）                              │
│     L0元规则 · L1索引 · L2事实 · L3技能(SOP) · L4归档   （可检索·有上界）  │
├─────────────────────────────────────────────────────────────────────────┤
│                 L1 原子工具（Atomic Tools / Tool Use）                     │
│   code_run · file_read/write/patch · web_scan/js · ask_user · proc · mem  │
├─────────────────────────────────────────────────────────────────────────┤
│                 L0 组合基底（Substrate / Plugin Registry）                 │
│     插件注册 registry · 可逆效应追踪 reversible-effect · coeffect 解析     │
│                      · 热插拔 HMR · 组合代数                               │
└─────────────────────────────────────────────────────────────────────────┘
        ▲                        ▲                        ▲
   MCP Client ──────────── 外部能力（tools/resources/prompts）────────
   ═══════════════════════════════════════════════════════════════════
   横切能力（Crosscutting，贯穿 L0–L5）
   permission 权限/审批/沙箱 · constraints 约束/熔断 · observability 日志/指标/追踪 · durability 持久性/恢复/回滚
```

---

## 2. 分层职责（Layer Responsibilities）

| 层 | 名称 | 一句话职责 | 依赖方向 |
|---|---|---|---|
| L0 | 组合基底 Substrate | 提供插件注册、组合、可逆效应、coeffect 的组合代数，是唯一"核心" | 无依赖 |
| L1 | 原子工具 | 最小可逆能力单元（副作用 + 撤销 + Schema + coeffect 声明） | L0 |
| L2 | 分层记忆 | 五层记忆读写/检索/压实/结晶，控制上下文上界 | L0（+可选 L4 反馈） |
| L3 | 智能体循环 | 四阶段闭环，把工具/记忆/模型装配成智能体 | L0/L1/L2 |
| L3 | 上下文工程 | 上下文装配、信息地图、自动压实，控制窗口上界 | L0/L2 |
| L3 | 技能封装 | 技能库版本/灰度/路由，进化结晶产物的治理与调用面 | L0/L2/L4 |
| L3.5 | 任务编排 | 任务状态机、子任务拓扑、多 Agent 交接、断点续跑 | L3 |
| L4 | 进化引擎 | 观测 L3 运行 → 诊断 → 提案 → 验证，结晶产物沉淀至 memory/skills | L0/L1/L2/L3（只读） |
| L5 | 组合分发 | 把 profile/bundle/patch 打包、版本化、分发 | 全部 |

**横切能力（不属于任一层，贯穿所有层）**：

| 能力 | 一句话职责 |
|---|---|
| 权限与审批 permission | 分级权限（只读/数据编辑/高危）、高危默认拦截、人工审批流、沙箱隔离 |
| 约束与容错 constraints | schema 校验、熔断/降级/重试等横切中间件 |
| 可观测性 observability | 结构化日志、指标聚合、trace 追踪、审计，统一供给进化与审批 |
| 持久性 durability | 检查点快照、崩溃恢复、时间旅行回滚、保留策略 |

**关键约束**：依赖方向**只向下**（L4 → L3 → L2 → L1 → L0），禁止向上依赖；跨层交互一律通过 L0 的注册表/事件总线解耦；横切能力通过 L0 的中间件/切面机制注入，不产生层间硬依赖。

---

## 3. 核心组件

| 组件 | 所在层 | 职责 | 接口文档 |
|---|---|---|---|
| PluginRegistry | L0 | 插件注册/查找/生命周期/版本 | plugin-registry-interface.md |
| EffectTracker | L0 | 记录每个 effect 及撤销函数，支持时间旅行 | plugin-registry-interface.md |
| CoeffectResolver | L0 | 解析注入权限/宪章/配置，缺失拒绝 | plugin-registry-interface.md |
| CoreProfileEngine | L0 | 启动/载入读取两级 Core.md，合并注入 constitution coeffect/人格/项目信息 | core-profile-interface.md |
| ToolProvider | L1 | 聚合原子工具为 LLM 可调用的 tool schema | tool-use-interface.md |
| MemoryStore | L2 | 五层存储 + 检索 + 迁移 | memory-interface.md |
| AgentLoop | L3 | 四阶段闭环驱动 + 中间件 hook（横切注入点） | loop-interface.md |
| ContextEngine | L3 | 上下文装配/信息地图/压实 | context-interface.md |
| SkillRegistry | L3 | 技能库版本/灰度/路由 | skills-interface.md |
| Orchestrator | L3.5 | 任务状态机/子任务拓扑/交接/断点续跑 | orchestration-interface.md |
| Diagnoser/Proposer/Validator/Evaluator | L4 | 进化四插件 | evolution-interface.md |
| PermissionGuard | 横切 | 分级鉴权/审批/沙箱 | permission-interface.md |
| ConstraintMiddleware | 横切 | 校验/熔断中间件链 | constraints-interface.md |
| Telemetry | 横切 | 日志/指标/trace/审计 | observability-interface.md |
| MCPClient | 横切 | 消费外部 MCP server | mcp-interface.md |
| CheckpointManager / CrashRecovery / TimeTravel / RetentionManager | 横切 | 执行态持久化/恢复/回滚/保留 | durability-interface.md |

---

## 4. 数据流（关键路径）

### 4.1 单轮循环（热路径）

```
用户输入 ─► Loop.perceive ─► ContextEngine.assemble(信息地图 + 压实) ─► MemoryStore.retrieve(注入)
   ─► LLM(Reason) ─► PermissionGuard.check(动作分级) ─► Loop.act
   ─► ToolProvider.invoke(tool) ─► ConstraintMiddleware(schema/熔断) ─► EffectTracker.record(effect, undo)
   ─► Loop.remember ─► MemoryStore.write ─► Telemetry.emit(trace) ─► 下一轮
```

### 4.2 任务编排路径（长任务）

```
用户目标 ─► Orchestrator 拆解子任务 + 建依赖拓扑 ─► 逐个派发 AgentLoop
   ─► 子任务间 TaskHandoff 交接上下文 ─► 状态机推进 ─► 挂起/恢复/取消（断点续跑）
```

### 4.3 结晶路径（冷路径，异步）

```
Evolution 观测 N 轮 loop 日志（统一 Telemetry 数据源）─► Diagnoser 找重复模式/缺陷
   ─► Proposer 生成世代化技能/插件补丁 ─► Validator(review + 运行时测试)
   ─► Evaluator(留出集) ─► 通过则 Crystallize：技能→SkillRegistry；失败则 Dissolve + 回写教训
```

### 4.4 回滚路径

```
用户/进化引擎请求 rollback ─► EffectTracker.replay(undo 栈)
   ─► Registry 卸载目标世代 ─► MemoryStore 回写教训（L3 降级）
```

---

## 5. 运行时视图（进程模型）

MVP 采用**单进程**：主循环线程 + 记忆/进化后台任务 + MCP 传输通道。

```
┌──────────────────────────── core-agent 进程 ────────────────────────────┐
│  MainLoop (L3)                                                          │
│  ├─ PluginRegistry (L0, 内存索引)                                       │
│  ├─ MemoryStore (L2, 文件后端 + 内存缓存)                                │
│  ├─ ContextEngine / SkillRegistry (L3)                                  │
│  ├─ Orchestrator (L3.5, 任务队列)                                       │
│  ├─ EvolutionWorker (L4, 后台，低优先级)                                 │
│  ├─ PermissionGuard / ConstraintMiddleware / Telemetry (横切)           │
│  ├─ DurabilityManager (横切)                                            │
│  └─ MCPClient (横切, stdio/HTTP 子进程或连接)                            │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 部署视图

```
core-agent/                      # 仓库根
├── core_harness_architecture.md # 架构原始构想（本文的"源头"）
├── doc/                         # 本文档集（SDD）
├── openspec/                    # （可选）OpenSpec CLI 生成的规格目录
├── src/core/                    # 源码（待实现）
│   ├── substrate/               # L0：registry/effect/coeffect/hmr
│   ├── tools/                   # L1：原子工具
│   ├── memory/                  # L2：分层记忆
│   ├── loop/                    # L3：智能体循环
│   ├── context/                 # L3：上下文工程
│   ├── skills/                  # L3：技能封装
│   ├── orchestration/           # L3.5：任务编排
│   ├── evolution/               # L4：进化引擎
│   ├── permission/              # 横切：权限与审批
│   ├── constraints/             # 横切：约束与容错
│   ├── observability/           # 横切：可观测性
│   ├── durability/              # 横切：持久性
│   └── mcp/                     # MCP 集成
└── tests/                       # 测试（对齐 04-testing）
```

---

## 7. 关联文档

- 架构决策：`doc/01-architecture/adr.md`
- 数据模型：`doc/01-architecture/data-model.md`
- 模块设计：`doc/02-modules/*`
- 接口设计：`doc/03-interfaces/*`
