# 设计 — 压实触发的诚实化与配置注入（change 0182）

## D1 诚实化止于「触发面」：`rounds` → `steps`

`Compactor.should_compact` 的第一参数改名 `steps`、常量 `_ROUND_THRESHOLD` 改名
`_STEP_THRESHOLD`、构造 kwarg 改名 `step_threshold`。理由：该位置的**真实语义**是
`ctx.rounds`（工具步数），把名字改成与语义一致，避免下一位读者重犯 E96 的推理错误。

**不**改 `LoopContext.rounds` 字段名：它是公开 dataclass 字段，被 planner 提示装配、事件载荷
（`step_completed` 的 `round`）、观测面与多个测试断言引用；改名是**跨模块重命名**，超出本条 change
的局部化边界（P3）。⇒ 记为局限：`LoopContext.rounds` 仍是「工具步数」的**历史名**，
诚实化只覆盖压实触发面与配置面。规格条款中显式写明「`ctx.rounds` —— 每轮自 `0` 起算，
**非**对话轮数」，把这一事实**写进规格**而非留在代码注释里。

## D2 阈值默认 `6`：让步数维度**能**触发

`_STEP_THRESHOLD = 6`，且配置缺省同为 `6`。依据：

- 触发检查点在 `observe()` 之后（`default.py:450`），此时 `ctx.rounds >= 1`；
- 循环顶的终止判据是 `ctx.rounds >= max_rounds`（缺省 `10`）⇒ 阈值**必须严格小于**
  `max_rounds` 才可能「提前」触发；缺省 `6` 相对 `10` 留出 4 步余量，既能让长工具链任务
  在中途压实，又不会在第 1~2 步就把短任务拖进压实（每次压实含 LLM 摘要，有真实成本）。
- 若用户把 `loop.compact_steps` 调到 `>= max_rounds`，则该维度**退化为「与终止同刻」**
  （见 D4 与规格 Scenario）——这是**允许的合法配置**，不是错误：语义仍是「至少压实一次」，
  但不再提前。此退化行为**写进规格**，不留暗坑。

## D3 单一真源：常量与 ConfigSpec 缺省的一致性

`manager.py` 侧新增 `_DEFAULT_COMPACT_STEPS = 6` 并用于 `ConfigSpec(default=…)`，与
`compactor.py` 的 `_STEP_THRESHOLD` **同值两地**。这是本仓**既有纪律**
（先例：`_DEFAULT_PERMISSION_MODE` 在 `manager.py:715` 与 permission 模块各有一份；
`_DEFAULT_HISTORY_TURNS` 同理），理由：`configuration` 不得 import `context`（分层方向），
反向 import 只为拿一个默认值不划算。=> 用**测试**钉住一致性：`test_config_default_matches_compactor_default`
断言 `configuration._DEFAULT_COMPACT_STEPS == compactor._STEP_THRESHOLD`，把「两地」变成**受门禁约束的
两地**。

配置面：`ConfigSpec("loop.compact_steps", "--loop.compact-steps", "CORE_LOOP_COMPACT_STEPS",
default=_DEFAULT_COMPACT_STEPS, map_to="loop.compact_steps", exposure=ADVANCED)`。
`loop` 段已在 `_known_sections()` 白名单内（`map_to` 前缀合并，`manager.py:373-375`）
⇒ **无需**改 `_KNOWN_EXTRA_SECTIONS`。

访问器 `compact_steps()` 走**独立访问器**先例（同 `history_turns()` / `importance_gate()`）：
不并入 `loop_limits()` 二元组（该 arity 被多处解包断言钉死）。

校验：`_loop_errors` 增一条 —— `loop.compact_steps` 须为 **≥1 的整数**（`bool` 非法）。
选择「阻断启动」而非静默兜底，与同段既有三键**同口径**（对齐 `configuration/spec.md`
「非法取值校验期拒绝」）。**不**做「阈值 ≤ max_rounds」的跨键校验：见 D2，
阈值 ≥ 上限是合法退化配置。

## D4 同轮至多一次：`astream()` 内的执行态标记

问题：触发检查在**每一步**都跑。阈值 `6`、上限 `10` ⇒ 第 6~10 步（含终止步）都满足
`steps >= 6` ⇒ 最多 5 次 `_compact`（每次 LLM 摘要 + 关键事实抽取）。这不是「更安全」，
而是**成本放大且语义重复**（同一轮同一份历史被反复摘要）。

设计：`astream()` 循环外的局部标记 `compacted = False`；触发点改为

```
if not compacted and self._should_compact(ctx):
    await asyncio.to_thread(self._compact, ctx, trace_id)
    compacted = True
```

- 标记**不放进 `LoopContext`**：它是**执行态**（本轮调度决策），不是上下文事实；放进 `ctx` 会污染
  公开数据契约、且被 `observe()` 造新 ctx 时需额外搬运。
- `astream()` 是**唯一**循环体（`run()` 委托它，`default.py:380` 附近注释已声明）⇒ 标记一处即全路径覆盖。
- 与既有测试口径一致：`test_loop_default_wiring_compacts_exactly_once_at_round_ten`
  已断言 `rec.compacted == 1`，本 change 让「恰好一次」从**巧合**（阈值==上限）变成**规格保证**。

## D5 组合根注入

`runtime.py`：`ContextCompactor(memory=memory, step_threshold=config.compact_steps())`。
`config` 为 `None`（无配置文件）时 `compact_steps()` 返回 `_DEFAULT_COMPACT_STEPS` ⇒
构造值等于模块缺省 ⇒ 行为与「不注入」**逐字一致**。

## 不变式

- **I1** 无压实器（`_compactor is None`）⇒ 永不压实（`_should_compact` 首行短路，**不动**）。
- **I2** token 触发路径**逐字不变**（`token_used >= budget` 判据、`budget <= 0` 时的退化入参
  `should_compact(ctx.rounds, 0, 1)`，`default.py:638-640`）—— 但注意其**首参**现按步数语义传入，
  语义不变、行为不变（`0 >= 1` 为假、步数维度照常按阈值判定）。
- **I3** 终止语义不变：`TOKEN_BUDGET_EXCEEDED` / `LOOP_LIMIT_EXCEEDED` 的产生条件与次序不动。
- **I4** 「压实已触发」标记**每轮重置**（`astream()` 局部变量 ⇒ 天然随轮重置）。
- **I5** `loop.compact_steps` 未配置 ⇒ 取 `6`，与 `_STEP_THRESHOLD` 同值。
- **I6** `exclude_source_prefixes=("beast.","pet")`（`runtime.py:603`）**逐字不动**。
- **I7** 不新增第三方依赖、不新增 import 方向（`configuration` 不 import `context`）。

## 被改写的规格条款（有意）

- `context`「上下文自动压实」：canonical 原文**无触发判据句**（只写「对多轮关键信息自动摘要沉淀」），
  本 delta **新增**一段触发判据（工具步数 or token、每轮至多一次），并把首个 Scenario 的 GIVEN
  由「轮数或 token 达到阈值」改为「**工具步数**或 token 达到阈值」—— 属**措辞诚实化**，
  场景语义不变（该场景断言的仍是「触发后产物落库且可追溯」）。
- `context`「三层窗口比例分配」：canonical 括注「不新增配置键」写于**配额分配面**；
  本 delta 把括注改为「本**配额分配面**不新增配置键 —— 压实**触发**阈值是另一面，
  自 change 0182 起可经 `loop.compact_steps` 配置」，**消除与 change 0182 的字面冲突**，
  不改该 Requirement 的任何行为条款（份额、单调性、零守卫全部逐字保留）。
- `configuration`「循环预算配置」：canonical 为「三项」，本 delta 改为「四项」并在同句追加
  `loop.compact_steps` 的默认值与校验口径，`缺省取内置默认值` Scenario 的 THEN 追加
  `loop.compact_steps` 取 `6`。属**同一 Requirement 的条款增补**，非新 Requirement。

## 测试设计（先红）

1. `test_step_threshold_default_is_six`：`_STEP_THRESHOLD == 6`（常量面）。
2. `test_should_compact_on_step_threshold`：`Compactor().should_compact(6, 0, 10**9) is True`；
   `should_compact(5, 0, 10**9) is False`（步数维度**活着**）。
3. `test_should_compact_step_threshold_injectable`：`Compactor(step_threshold=3)` ⇒ `3` 触发、`2` 不触发。
4. `test_config_default_matches_compactor_default`：两地常量同值（D3 门禁）。
5. `test_compact_steps_config_key_parses` / `_validates`：三面解析 + 非法（`0` / `-1` / 布尔 / 小数）阻断。
6. `test_loop_compacts_at_most_once_per_turn`（**新红**）：阈值 `2`、`max_rounds=6`、工具链持续产出
   ⇒ `rec.compacted == 1`（改前为多次）。
7. 回归：`test_loop_default_wiring_compacts_exactly_once_at_round_ten`（缺省阈值 ⇒ 仍恰好一次）、
   token 维度用例、现有 `round_threshold=` 调用点更名后行为不变。
