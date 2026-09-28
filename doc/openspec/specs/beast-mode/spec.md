# Beast Mode Specification

## Purpose

神兽召唤层（beast-mode）为 core-agent 提供前台重大任务执行能力（pet-mode 后台重复简单任务的对偶）：20 个预定义山海经神兽，各持独有神通（L3 Skill），召唤复用编排层 `MultiAgentRouter.handoff` 交接语义，异步并发执行并据 `LoopResult.failed` 自动回归，多实例并发（兽间并行、兽内串行），三入口（/summon 斜杠命令、summon <beast> [task] CLI argv、WebUI 自然语言）激活，相当于"人类召唤神兽"——前台接管重大任务、独立记忆、共享主 Agent 通用能力。

## Requirements

### Requirement: Beast Registry
系统 SHALL 内置 20 个山海经神兽作为只读注册表：每兽以 `agent_id = beast.<拼音>` 唯一标识，含称号、领域职责、独有神通（skill_id）与能力标签（capabilities，供 `MultiAgentRouter.match()` 关键词打分路由）；注册表只读，区别于 pet.md 的用户自定义角色。

#### Scenario: 神兽唯一标识
- **GIVEN** 注册表已内置 20 神兽
- **WHEN** 查询某神兽
- **THEN** 以 `beast.<拼音>` 唯一标识，含称号、领域、独有神通、能力标签

#### Scenario: 注册表只读
- **GIVEN** 运行时尝试增改注册表神兽
- **WHEN** 写入神兽定义
- **THEN** 拒绝，注册表维持内置 20 兽不变（用户自定义留待后续，非本变更）

### Requirement: Beast Session Lifecycle
系统 SHALL 以 `DORMANT → MANIFEST → ACTIVE → RECALLED` 四态管理神兽会话，维护 `dict[agent_id, BeastSession]` 多实例：可同时显形多兽并行执行（兽间并行、互不阻塞）；同兽重复召唤先拒绝或先回归（兽内串行，无同兽双实例）。

#### Scenario: 多实例并发
- **GIVEN** 已有神兽 A 在岗（MANIFEST/ACTIVE）
- **WHEN** 发起另一神兽 B 的召唤
- **THEN** A、B 同时显形并行执行（兽间并行、互不阻塞）

#### Scenario: 同兽重复召唤拒绝
- **GIVEN** 某兽已在岗（MANIFEST/ACTIVE）
- **WHEN** 再次召唤同兽
- **THEN** 拒绝或先回归该兽（兽内串行，无同兽双实例）

#### Scenario: 四态转移
- **GIVEN** 神兽会话处于某态
- **WHEN** 召唤/执行/回归/复位
- **THEN** 沿 DORMANT→MANIFEST→ACTIVE→RECALLED 合法转移，非法转移拒绝

### Requirement: Summon via Handoff
系统 SHALL 将召唤实现为 `MultiAgentRouter.handoff`：神兽是内置预定义 `AgentProfile`，召唤即 `handoff(beast_id, TaskHandoff(...))`，复用编排层既有交接语义与上下文打包，不另造第二真源。

#### Scenario: 召唤交接
- **GIVEN** 用户召唤某神兽执行重大任务
- **WHEN** 构造 `TaskHandoff`（task/context_pack/acceptance/deadline/priority）
- **THEN** 经 `MultiAgentRouter.handoff` 交接给对应神兽 `AgentProfile`，复用编排层交接

#### Scenario: 无匹配神兽
- **GIVEN** 用户召唤不存在的兽
- **WHEN** 路由无匹配
- **THEN** 返回 `NO_AGENT_MATCH`，不显形任何神兽

### Requirement: Independent Sub-Agent with Shared Capability
系统 SHALL 让神兽以独立 `AgentProfile.loop`（独立 `LoopPlugin` 实例）运行：独立记忆命名空间（`MemoryEntry.source = beast.<agent_id>`，与主 Agent `source=loop` 隔离）+ 独立上下文装配（`DynamicAssembler.build()` 按神兽任务阶段装配 `ContextPack`）；运行时能力分两层——L1 工具共享全局 `ToolProvider`（loop 原生消费，通用能力真实可用）+ L3 技能（神通 `beast.*`）注册进全局 `SkillLibrary`（注册/共享实例可验证；loop→skill 运行时调用 deferred）。

#### Scenario: 独立记忆命名空间
- **GIVEN** 神兽执行任务产生记忆
- **WHEN** 写入记忆
- **THEN** `MemoryEntry.source = beast.<agent_id>`，与主 Agent（`source=loop`）隔离，不污染主记忆

#### Scenario: 共享 L1 工具
- **GIVEN** 神兽 loop 调用通用工具
- **WHEN** 消费 `ToolProvider`
- **THEN** 与主 Agent 同源共享全局 `ToolProvider` 实例，通用能力运行时真实可用

#### Scenario: 共享 L3 技能库
- **GIVEN** 神通 `beast.*` 已注册
- **WHEN** 查询全局 `SkillLibrary`
- **THEN** 注册/共享实例可验证（loop→skill 运行时调用 deferred）

### Requirement: Innate Skills and Dedicated Routing
系统 SHALL 为每兽注册独有神通 Skill（`beast.<拼音>.<skill>`）进全局 `SkillLibrary`，命名空间 `beast.<拼音>`；专属路由语义：某兽的独有神通仅该兽可路由，他兽不可路由（runtime 调用 deferred，本变更定语义 + 单测断言）。

#### Scenario: 神通注册
- **GIVEN** 20 神兽已定义
- **WHEN** 启动时注册神通
- **THEN** 20 个 `beast.*` Skill 进入全局 `SkillLibrary`，字段符合 Skill 契约（skill_id/preconditions/param_schema）

#### Scenario: 专属路由
- **GIVEN** 神兽 A 的独有神通 `beast.a.<skill>`
- **WHEN** 神兽 B 尝试路由该神通
- **THEN** 不可路由（专属路由语义，由 `BeastSession` 按 agent_id 前缀过滤候选，runtime 调用 deferred）

### Requirement: Async Concurrent Execution and Auto-Recall
系统 SHALL 异步并发执行召唤（`handoff` 经 `loop.arun` 非阻塞，多兽并行互不阻塞，契合前台重大任务），任务完成后据 `LoopResult.failed` 判定成败自动回归：神兽会话迁至 `RECALLED`，记忆分区封存（`source=beast.*` 不再被主 loop read 命中）。

#### Scenario: 异步并发执行
- **GIVEN** 神兽在岗执行重大任务
- **WHEN** 召唤（handoff）发起
- **THEN** 经 `loop.arun` 异步执行，不阻塞调用方，多兽可并行；完成后返回完整 `LoopResult`

#### Scenario: 成败判定自动回归
- **GIVEN** 神兽 loop 完成返回 `LoopResult`
- **WHEN** 判定 `failed`
- **THEN** 据 `failed` 迁至 `RECALLED`，记忆分区封存

### Requirement: Manual Recall
系统 SHALL 支持手动复位：`/recall <beast>` 斜杠命令、`recall <beast>` CLI 动词、NL「召回」均按 beast_id 复位目标兽至 `RECALLED`（异步执行下无「中断在岗兽」窗口，仅复位目标兽，他兽不受影响），复位后可再次召唤该兽。

#### Scenario: 手动复位
- **GIVEN** 神兽会话非 DORMANT 态
- **WHEN** 经 `/recall <beast>`/`recall <beast>` CLI/NL 触发复位
- **THEN** 目标兽迁至 `RECALLED`（他兽不受影响），可再次召唤该兽

### Requirement: Three-Entry Activation
系统 SHALL 支持三入口召唤：`/summon` 斜杠命令（候选来自 plugin-registry 注册的 command/tool 元数据经统一 API `list_tools` 拉取，不进内核接口）、`summon <beast> [task]` CLI argv（cli-ops-interface `CommandGroup` 扩展）、WebUI 自然语言「召唤 X 兽做 Y」（经 `UIAPILayer`/`IMGateway.on_message` 消息驱动会话）；三入口最终落到同一 `BeastSession` 生命周期。

#### Scenario: /summon 斜杠召唤
- **GIVEN** UI 层输入 `/summon` 触发命令面板
- **WHEN** 选择神兽候选（经统一 API `list_tools` 拉取）
- **THEN** 激活对应神兽会话，不进内核接口

#### Scenario: summon CLI 召唤
- **GIVEN** 宿主 CLI 输入 `summon <beast> [task]`
- **WHEN** 解析 argv（cli-ops-interface `CommandGroup` 扩展）
- **THEN** 激活对应神兽会话

#### Scenario: WebUI 自然语言召唤
- **GIVEN** WebUI 输入「召唤 X 兽做 Y」
- **WHEN** 经 `UIAPILayer`/`IMGateway.on_message` 进入内核 loop，Agent 理解意图
- **THEN** 激活神兽会话并绑定任务，与 slash/CLI 同源
