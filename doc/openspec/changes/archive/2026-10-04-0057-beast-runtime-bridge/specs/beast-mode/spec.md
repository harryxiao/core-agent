# beast-mode spec delta — beast-runtime-bridge

**解除 R4/R5 正文里显式写着的「runtime 调用 deferred」**：神兽的独立 loop、共享记忆命名空间、
神通注册与专属路由作用域从「语义 + 单测」推进到**生产装配可触达**。
（来源：账本 `phase-19.md` §2 E3 —— 四项同源缺口，2026-10-04 用户裁决「A 全做・解除 deferred」）

## MODIFIED Requirements

### Requirement: Independent Sub-Agent with Shared Capability
系统 SHALL 让神兽以独立 `AgentProfile.loop`（独立 `LoopPlugin` 实例）运行：独立记忆命名空间（`MemoryEntry.source = beast.<agent_id>`，与主 Agent `source=loop` 隔离）+ 独立上下文装配（`DynamicAssembler.build()` 按神兽任务阶段装配 `ContextPack`）；运行时能力分两层——L1 工具共享全局 `ToolProvider`（loop 原生消费，通用能力真实可用）+ L3 技能（神通 `beast.*`）注册进全局 `SkillLibrary` 并被神兽 loop **运行时真实路由**。

- **组合根装配**：组合根 SHALL 注册神通并构造神兽管理器（为每兽按域装配独立 `LoopPlugin`、注入共享 `MemoryStore`）；`BeastSession` SHALL NOT 停留在「无记忆 + echo loop」的默认实例上（那会使命名空间隔离与神通路由在生产不可达）。

#### Scenario: 独立记忆命名空间
- **GIVEN** 神兽执行任务产生记忆
- **WHEN** 写入记忆
- **THEN** `MemoryEntry.source = beast.<agent_id>`，与主 Agent（`source=loop`）隔离，不污染主记忆

#### Scenario: 共享 L1 工具
- **GIVEN** 神兽 loop 调用通用工具
- **WHEN** 消费 `ToolProvider`
- **THEN** 与主 Agent 同源共享全局 `ToolProvider` 实例，通用能力运行时真实可用

#### Scenario: 共享 L3 技能库
- **GIVEN** 神通 `beast.*` 已注册且组合根已为神兽装配 loop
- **WHEN** 神兽 loop 在自身域内路由技能
- **THEN** 其独有神通可被该兽路由（运行时真实调用），注册/共享实例可验证

### Requirement: Innate Skills and Dedicated Routing
系统 SHALL 为每兽注册独有神通 Skill（`beast.<拼音>.<skill>`）进全局 `SkillLibrary`，命名空间 `beast.<拼音>`；专属路由语义 SHALL 由路由期**作用域强制**：某兽的独有神通仅该兽可路由，他兽不可路由，主 Agent 亦不可路由——由路由按 skill_id 前缀过滤候选（`domain` 参数），SHALL NOT 仅靠语义约定或调用方自觉。

- **作用域口径**：三节 `beast.<域>.<技能>` 形式的 skill_id 为**专属技能**，仅当路由 `domain` 等于 `beast.<域>` 时进入候选；非专属技能恒可见。主 Agent 路由不带 `domain`，故专属神通不进其候选（不污染 prompt）。

#### Scenario: 神通注册
- **GIVEN** 20 神兽已定义
- **WHEN** 组合根启动装配
- **THEN** 20 个 `beast.*` Skill 进入全局 `SkillLibrary`，字段符合 Skill 契约（skill_id/preconditions/param_schema）

#### Scenario: 专属路由
- **GIVEN** 神兽 A 的独有神通 `beast.a.<skill>`
- **WHEN** 神兽 B 或主 Agent 尝试路由该神通
- **THEN** 不可路由（路由期按域过滤，非本域技能不进入候选）
