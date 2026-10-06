# Beast Mode Specification Delta

## MODIFIED Requirements

### Requirement: Independent Sub-Agent with Shared Capability
系统 SHALL 让神兽以独立 `AgentProfile.loop`（独立 `LoopPlugin` 实例）运行：独立记忆命名空间（`MemoryEntry.source = beast.<agent_id>`，与主 Agent `source=loop` 隔离）+ 独立上下文装配（`DynamicAssembler.build()` 按神兽任务阶段装配 `ContextPack`）；运行时能力分两层——L1 工具共享全局 `ToolProvider`（loop 原生消费，通用能力真实可用）+ L3 技能（神通 `beast.*`）注册进全局 `SkillLibrary` 并被神兽 loop **运行时真实路由**。

- **组合根装配**：组合根 SHALL 注册神通并构造神兽管理器（为每兽按域装配独立 `LoopPlugin`、注入共享 `MemoryStore`）；`BeastSession` SHALL NOT 停留在「无记忆 + echo loop」的默认实例上（那会使命名空间隔离与神通路由在生产不可达）。
- **自身轨迹可召回**：神兽的独立上下文装配 SHALL 在**排除面**（主 Agent 侧的 `source=beast.*` 封存）内
  **放行自身**命名空间（`source = beast.<agent_id>`）—— 封存 SHALL NOT 使神兽读不到**自己**的过往经验；
  **他兽**命名空间 SHALL NOT 进入该兽检索面（放行项为该兽自身 `agent_id`，余者仍被排除）。
  主 Agent 侧的封存语义 SHALL 逐字不动。

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

#### Scenario: 神兽可召回自身轨迹
- **GIVEN** 神兽 `beast.a` 的命名空间已沉淀 `source=beast.a` 的轨迹，且库中另有神兽 `beast.b` 的条目
- **WHEN** 神兽 `beast.a` 装配上下文并检索
- **THEN** 自身 `source=beast.a` 的条目**出现**，`source=beast.b` 的条目**不出现**

#### Scenario: 主 Agent 侧封存不受影响
- **GIVEN** 神兽命名空间已向其自身放行（同上），且主 Agent 装配上下文
- **WHEN** 主 Agent 按任务检索
- **THEN** 任何 `source=beast.*` 条目**都不出现**（封存语义逐字不动）
