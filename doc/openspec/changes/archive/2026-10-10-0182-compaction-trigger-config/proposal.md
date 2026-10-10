# 变更提案 — 压实触发的诚实化与配置注入（change 0182）

## 为什么

`coding-plan/known-risk.md` §1 **E96** 的「另注」记着一处**命名与事实不符**的能力缺口：

- `Compactor.should_compact(self, rounds: int, token_used: int, budget: int)`
  （`src/core/context/compactor.py:35-37`）参数写作 `rounds`，判据写作「轮数达到阈值」；
  但实参是 `ctx.rounds`（`src/core/loop/default.py:452`），而 `LoopContext.rounds` 是
  **本轮内已记账的工具动作步数**（`default.py:741` `observe()` 内自增，且每用户轮 `perceive()`
  重造 `LoopContext` ⇒ 每轮自 `0` 起算）。
- 更实质的问题是**该维度事实上是死的**：`_ROUND_THRESHOLD = 10`
  （`compactor.py:20`）与 `loop.max_rounds` 缺省 `10`（`configuration/manager.py:40`）**恰好相等**，
  而 `astream()` 的循环顶在 `ctx.rounds >= self._max_rounds` 时先 `break`
  （`default.py:401-403`）⇒ 压实检查点（`default.py:450-455`）**永远等不到** `rounds == 10`。
  唯一的活触发维度只剩 token 预算。
- 同时 `_ROUND_THRESHOLD` 是**模块常量**，无配置键（`loop` 段只有 `max_rounds` /
  `output_reserve` / `history_turns`），用户**无法**把它调到 `max_rounds` 以下来让该维度生效。

E96 已随 change `0177`（ADR-0168 写作面）之外的「另注」保留至今；本 change 按用户 2026-10-10 裁决
**「E96 另注（压实的 `rounds`＝工具步数）= 诚实化 + 配置注入」**一次性闭合：

1. **诚实化**：参数、文档、异常文案一律改口「工具步数」，不再称「轮数」；
2. **配置注入**：新增配置键 `loop.compact_steps`（缺省 `6` < `max_rounds` 缺省 `10` ⇒
   该维度**能真正提前触发**），经组合根注入压实器构造。

附带必须一起解决的**同轮重复压实**风险：步数阈值一旦小于 `max_rounds`，判据
`steps >= threshold` 会在阈值步之后的**每一步**持续为真（`default.py:450`），若不加闸门则一轮内
可触发最多 `max_rounds - threshold + 1` 次 `_compact`（每次含 LLM 摘要 + 关键事实抽取）
⇒ 同轮多次模型调用。故本 change 同时把「**每轮至多压实一次**」钉为规格条款。

## 改什么

| 面 | 变更 |
|---|---|
| `src/core/context/compactor.py` | `_ROUND_THRESHOLD` → `_STEP_THRESHOLD`（`6`）；构造 kwarg `round_threshold` → `step_threshold`；`should_compact(rounds, …)` → `should_compact(steps, …)`，docstring 改「工具步数」 |
| `src/core/loop/default.py` | `astream()` 增本轮一次性标记 `compacted`，`_should_compact` 已触发即短路；`_should_compact` docstring 改「工具步数」 |
| `src/core/configuration/manager.py` | 新 `ConfigSpec("loop.compact_steps", …)`；`_DEFAULT_COMPACT_STEPS = 6`；新访问器 `compact_steps()`；`_loop_errors` 增 ≥1 整数校验 |
| `src/core/runtime.py` | 构造 `ContextCompactor(memory=memory, step_threshold=config.compact_steps())` |
| 规格 | `context`：`上下文自动压实` 增触发判据条款 + 同轮至多一次条款 + 2 Scenario；`三层窗口比例分配` 括注改口。`configuration`：`循环预算配置` 增第四键 + 校验 + 1 Scenario |
| 测试 | `tests/test_context_compaction.py` 更名/改默认值 + 新增「同轮至多一次」用例；`test_context.py` / `test_loop*.py` / `test_notes_loop.py` 的 `round_threshold=` 实参更名 |

## 影响

- **行为变更（有意）**：默认 `step_threshold=6` 时，本轮工具步数达 6 的**长工具链任务**将**首次**
  触发压实（此前只有 token 维度可能触发）。对短任务（步数 < 6）与 token 触发路径**逐字不变**。
- **行为变更（收敛）**：一轮内压实**至多一次** —— 此前阈值 < 上限时存在多次压实，此为**收敛**而非
  放宽（减少模型调用）。
- **向后兼容**：`LoopContext.rounds`（公开 dataclass 字段）**不改名** —— 其语义虽同「工具步数」，
  但改名会波及 planner / 观测面 / 既有断言；记为**本轮登记局限**（诚实化止于压实触发面）。
- 无新增第三方依赖；无 import 方向变化；`exclude_source_prefixes=("beast.","pet")` 主方向封存红线
  （`runtime.py:603`）**逐字不动**。
