# Change: 上下文按任务召回记忆（task-keyed memory recall）

## Why

`doc/01-architecture/architecture-overview.md:117` 的热路径把「检索 + 注入」钉在
`ContextEngine.assemble ─► MemoryStore.retrieve(注入)`——检索由上下文装配器发起；
`Loop.perceive` 只做观察（收状态、拼上下文包），不承担检索。

现状与架构图有两处偏离（Phase 17.5 §3.1 走查实证）：

- **装配器检索用错 query**：`assembler._gather_facts(stage, budget)` 以 `stage` 作检索
  query（`assembler.py:56-60`），而 `stage` 恒为常量 `"reason"`（`planner.py:124`
  唯一调用点）——检索退化为「拿阶段名当关键词」，召回与任务无关。
- **perceive 越权检索**：`perceive` 额外做了 `self._memory.read(user_input)` 填
  `LoopContext.memory`（`default.py:213`），但该字段无任何消费方——重复检索 + 死字段。

两者同属「检索归属错位」，合并为一个变更：把检索收敛回装配器，并改为 task-keyed。

## What Changes

- **装配器按任务召回**（context，MODIFIED「动态上下文构建」，对应 `CORE-CTX-R1`）：
  `_gather_facts` 检索 query 由 `stage` 改为 `task`；`stage` 降为装配阶段标注，
  **暂不参与事实选择**（不再作检索关键词）。token 上界（预算）不变。
- **perceive 撤越权检索**（loop，无规格变更）：「执行循环」Requirement 只要求 perceive
  完成「观察」，未要求其检索记忆；移除 perceive 的冗余 `memory.read` 不改变循环语义。
- **接口文档同步**：`context-interface.md`（`build` 语义 = 按任务召回 + 阶段标注）、
  `loop-interface.md`（`perceive` 注释「检索记忆」删除，检索归 ContextEngine）。

## Non-goals

- 不改 `MemoryStore.read` 排序算法（多因子化属 Phase 18 交付物 #2）。
- 不接 embedder（运行时仍词法兜底，属 Phase 18 遗留 C7）。
- 不删 `LoopContext.memory` 字段（其废弃化属 Phase 18 遗留 A1）。
- 不给 perceive / act 阶段扩展装配（属 Phase 18 遗留 B6）。

## Impact

- **Affected specs**：`context/spec.md`（1 MODIFIED：「动态上下文构建」——检索 query 由
  阶段改为任务；新增场景「按任务召回事实」）。`CORE-CTX-R1` 语义不变，仅澄清检索依据。
- **Affected docs**：`03-interfaces/context-interface.md`（`build` 语义 / `stage` 注释）、
  `03-interfaces/loop-interface.md`（`perceive` 注释）
- **Affected code**：`src/core/context/assembler.py`（`_gather_facts(task, budget)`）、
  `src/core/loop/default.py`（`perceive` 撤 `memory.read`）
- **Dependencies**：无新依赖
- **风险**：召回内容随 query 变化（stage→task），依赖「stage 命中」的测试需同步；低——
  唯一调用点本就传 `stage` 常量，无外部依赖其检索行为。
