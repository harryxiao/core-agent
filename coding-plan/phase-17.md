# Phase 17 — 编排打通 + 记忆语义化 + 自动迭代前置（主 Agent 委托子 Agent + 语义记忆落盘）

> 里程碑：**M3 真实收口 + 记忆语义化补丁**（不新增里程碑；修复 Phase 13/14 装配后「多 Agent 编排实际不可用」与「记忆无语义/不落盘」两处链路断裂）
> 位置：横切 `orchestration`（router / scheduler / models + runtime 组合根装配）× `memory`（backend / protocol / store + runtime 装配）× `loop`（default.py 注入委托工具 + 语义记忆读写）
> 上游：Phase 0–15 已落地；本 Phase 仅收口修复 + 补语义化，不新增 capability、不新增三方依赖

---

## 1. 范围与定位

审查结论（2026-10-04）：TaskScheduler 机制完整（decompose→派发→handoff→checkpoint，`router.handoff` 为 `await profile.loop.arun(handoff.task)` 异步等结果），但两处装配缺陷使其**实际不可用**；记忆层只写元数据摘要、默认纯内存、检索 query 恒空，导致**跨对话无语义记忆**。二者共同阻断用户目标「core-agent 具备完善记忆 + 多任务编排，并让其自动迭代内部其余模块」。

本 Phase 三块缺口：

| 编号 | 级别 | 缺口 | 根因（真实锚点） |
|---|---|---|---|
| A | P0 | 主 Agent 无法委托子 Agent，subtask 全部回落 main 自己执行 | 装配只注册 `main_agent`（`capabilities=["default"]`），`MultiAgentRouter([main_agent], fallback=main_agent)`；`router.match` 无命中返回 fallback；主 loop 无 orchestrator 引用、无 delegate 工具 |
| B | P0 | 对话内容不入记忆（无语义、不落盘、检索空 query） | `remember` 只写 `轨迹 {trace_id}: {len} 步`；`FileBackend(path=None)` 默认纯内存；`read("")` 空 query；`MemoryEntry` 无 session 维度 |
| C | P1/P2 | 自动迭代前置不成立 | 缺 A（不能发起多步子任务）+ 缺 B（不能读历史教训）→ 主 Agent 无法自动迭代内部其余模块 |

---

## 2. 缺口 A — 编排打通（P0）

### 2.1 现状

- `runtime.py:195-199`：仅 `main_agent`（`capabilities=["default"]`）入池，`MultiAgentRouter([main_agent], fallback=main_agent)`。
- `router.py:43`：`match` 无命中时 `return self._fallback`（即 main_agent）→ `scheduler._run_subtask`（`scheduler.py:353`）对**任意** subtask 都匹配到 main_agent，`await main.loop.arun(...)` 等于主 Agent 自己重跑一遍，无真实子 Agent 分派。
- `loop/default.py`：`DefaultLoop` 不持有 `orchestrator`/`router` 引用，无 delegate/handoff 工具 → 主 Agent 在对话内无法主动「拆任务→派发子 Agent→等结果」；只能靠外部 `task` 命令路径触发 TaskScheduler，而该路径同样回落 main。

### 2.2 修复要求

1. **注册真实 subagent 池**：`build_runtime` 装配 ≥2 个 `AgentProfile`，各自 `capabilities` 标签正交（如 `coding` / `research` / `review`），每个 profile 持可 `arun` 的 `DefaultLoop`；`MultiAgentRouter` 不再 `fallback=main_agent`（或 fallback 语义显式化：无命中应抛 `NO_AGENT_MATCH`，而非静默回落 main）。
2. **主 loop 注入委托能力**：`DefaultLoop` 增加对 `orchestrator`（`TaskScheduler`）的引用或一个 `delegate`/`spawn_subtask` 工具（经 `ToolProvider` 注册），使 `LLMPlanner` 在 reason 阶段能发起子任务并**阻塞等待**其 `LoopResult` 汇总。
3. **能力标签匹配闭环**：`router.match` 的关键词打分对 subtask.goal 生效，确保「拆解出的 subtask 能命中对应 capability 的 subagent」而非永远回落；无命中走显式错误（`NO_AGENT_MATCH`）供上层感知。

### 2.3 契约红线

- `router.handoff` 的异步等待语义（`await profile.loop.arun(...)`）不变；`LoopResult` 结构不变。
- 不破坏 `TaskScheduler` 现有断点续跑 / checkpoint / 扇出并发 / stall 哨兵逻辑。
- 委托工具必须是**纯工具**（走 coeffect/effect/gate 链路），不得绕过 `PermissionGuard`。

---

## 3. 缺口 B — 记忆语义化（P0）

### 3.1 现状

- `loop/default.py:265-278`：`remember` 仅写 `content=f"轨迹 {trace_id}: {len(trajectory)} 步"`、`tags=["loop","trajectory"]` —— 只存元数据，**无任何对话/行动语义内容**。
- `loop/default.py:199`：`perceive` 用 `memory.read("", budget=2048)` —— **空 query**，检索不出任何相关历史。
- `memory/backend.py:22`：`FileBackend(path=None)` 默认纯内存热字典，**进程退出即丢**；`search`（L44-47）只按 `layer` 过滤，无语义相关性计算。
- `memory/protocol.py`：`MemoryEntry` 无 `session` 维度，无法按会话隔离/检索。

### 3.2 修复要求

1. **默认落盘**：`build_runtime` 从 config 读 `memory.path`（缺省给项目数据目录下默认 JSONL 路径），`FileBackend(path=...)` 实例化；保留 `path=None` 纯内存路径仅供测试。
2. **写入真实语义**：`remember` 写入当前轮次用户目标 + Agent 关键动作/结论摘要（含 `trace_id` 关联），而非「轨迹 N 步」；`tags` 携带能力/任务类型标签供检索。
3. **检索真实 query**：`perceive` 用当前 `ctx` 目标/最近用户输入作为 query，而非空字符串。
4. **session 维度**：`MemoryEntry` 增加 `session_id`（可选字段，默认 `""`），`read/write/search` 支持按 session 过滤；`list_index` 保留。
5. **语义检索（最小实现）**：`search` 在 layer 过滤基础上增加 query 关键词相关性打分（词元重叠即可，不引入三方 embedding），返回按相关性排序；无 query 时按时间序返回。

### 3.3 契约红线

- `MemoryBackend` 五入口（`get/put/search/list_index/delete`）签名不变；新增行为向后兼容（`search` 返回 `list[MemoryEntry]` 不变）。
- 不引入三方依赖（不做 embedding/向量库）；语义打分用内置词元重叠。
- `MemoryStore` 的冷/热区迁移（`migrate`）、结晶（`crystallize`）语义不变。

---

## 4. 缺口 C — 自动迭代前置（P1/P2）

缺口 C 是 A + B 的推论，不单独改代码：

- 完成 A 后：主 Agent 具备「拆解→派发 subagent→汇总」能力，能对「自动迭代其余模块」这类多步目标发起子任务。
- 完成 B 后：主 Agent 能读到历史缺陷/教训/提案（Phase 14/15 的进化采集与结晶产物）作为决策上下文。
- 两者闭合后，「主 Agent 自动迭代内部其余模块」才具备前提；本 Phase **只验收前置条件**，不实现自动化迭代闭环本身（该闭环依赖后续 evolution 接线，单列后续 Phase）。

验收判据：主 Agent 在一个真实对话中，能（1）读到历史记忆、（2）主动拆出 ≥2 个子任务并派发给**不同** subagent、（3）等结果汇总后作答。

---

## 5. 门禁与测试

- `ruff` 全绿、`pyright` 0 error、`pytest` 全绿（沿用 Phase 16 门禁命令，见 `coding-plan/README.md` §3）。
- 新增测试：
  - 编排：`router.match` 无命中抛 `NO_AGENT_MATCH`（不再静默回落）；≥2 subagent 装配后，不同 capability 的 subtask 命中不同 profile；委托工具阻塞等待并返回 `LoopResult`。
  - 记忆：`FileBackend(path=...)` 落盘后可 `_load` 恢复；`remember` 写入内容含语义（非「轨迹 N 步」）；`read` 用非空 query 能检索到 session 内相关条目；`MemoryEntry.session_id` 过滤生效。
  - 装配：`build_runtime` 默认 memory 有落盘 path（测试可注入纯内存）；主 loop 持有委托能力。

---

## 6. 提交规范

- 单次提交：`fix(orchestration+memory): 编排打通（主 Agent 委托子 Agent）+ 记忆语义化落盘`
- 变更范围：`src/core/orchestration/`（router / runtime 装配）、`src/core/memory/`（backend / protocol / store）、`src/core/loop/default.py`、`src/core/runtime.py`；测试同步（`tests/`）。
- 提交前门禁四者全绿；不触碰 `TaskScheduler` 断点续跑 / checkpoint 语义；不新增三方依赖。
