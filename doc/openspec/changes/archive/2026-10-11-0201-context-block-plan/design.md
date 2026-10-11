# Design 0201 — 上下文区块配比（五区块 / 80-20 安全线）

## 一句话

把蓝图的五区块配比做成**确定性纯函数**，并让 loop 的 token 预算**首次真正到达 planner**
（`build(budget=2048)` → 派生额度）——**缺省关**，关时逐字不变。

## 五区块本仓对照

| 蓝图区块 | 份额 | 本仓对应面 | 本 change 是否接线 |
|---|---|---|---|
| 系统提示 | `20%` | `_SYSTEM_PROMPT` + 宪法 + 常驻笔记 + 摘要专块（`_system_prompt` 的其余九块） | **否**（咨询性） |
| 记忆 | `15%` | 装配器 `build(budget=…)` ⇒「相关事实」/「文档目录」 | **是** —— 本 change 的唯一消费者 |
| 窗口 | `30%` | 回灌历史（`_window_plan` 的 `token_budget // 2`） | **否**（咨询性；已有自己的 `//2` 口径） |
| 归档 | `15%` | L4 归档 / 压实产物（不进 prompt） | **否**（咨询性） |
| 缓冲 | `20%` | 输出预留（`loop.output_reserve`，**已扣**） | **否**（见下，只作上界） |

**为什么不摊到十个提示词块**：`_system_prompt` 今日组装的是**十**个块（系统提示 / 宪法 /
常驻笔记 / 历史摘要（长）/（中）/ 相关事实 / 文档目录 / 相关笔记 / 可用技能 / 可用工具）。
把**五**份额摊到**十**块是**提示词契约重写**，需要逐块估算、逐块记账、逐块回归 —— 那是另一个
change，且必须在体量上单独论证。本 change 只做「让预算真的到达唯一有预算旋钮的那个面」。

## 关键裁决：20% 缓冲 = 上界，不是减法

蓝图把缓冲列为**第五块**（`20%`），容易被实现成 `usable = total × 0.8`。本仓**已经有**一个
20% 级的预留：

```
loop_limits() → token_budget = 上下文窗口 − loop.output_reserve   # 缺省预留 8192
```

⇒ 若缓冲再实现为 `total − 0.2×total`，则**同一次输出预留被扣两遍**（一次在 `loop_limits()`，
一次在区块计划）。裁决：**缓冲是「不分配」的结果，不是一次运算** ——

```
system   = int(total × 0.20)      # 咨询性
memory   = int(total × 0.15)      # ← 唯一消费者
window   = int(total × 0.30)      # 咨询性
archive  = int(total × 0.15)      # 咨询性
reserve  = total − (system + memory + window + archive)   # 余量，恒 ≥ 0.20×total
```

`reserve` 取**余数**而非 `int(total × 0.20)`：这样五块之和**恰为** `total`（断言更强），
且因四个可用块均为**向下取整**，`reserve ≥ 0.20 × total` **恒成立**（取整只会让余量变大）。

## 返回 `None` vs 返回全零 —— 刻意偏离 `plan_window`

`plan_window` 在预算非正时返回 `WindowPlan(0,0,0,0)`，因为它的消费者**就是**那个机制
（全零 = 关闭回灌，是**有语义**的取值）。

`plan_blocks` 的消费者是**提示词预算**：这里「零配额」与「无配额」在消费面上**语义不同** ——
若返回全零，消费者会把 `build(budget=0)` 当作「预算为零」传下去，而正确意图是**「不接管，
沿用你的既有字面量」**。故用 `None` 表达不接管。这条不对称写入模块 docstring。

## 消费者接线（唯一一处）

```
LoopContext.token_budget: int = 0        # protocol.py，缺省 0 ⇒ 未接线
DefaultLoop.perceive → ctx.token_budget = self._token_budget
LLMPlanner(block_plan=False)             # 构造参，缺省关
LLMPlanner._system_prompt:
    plan = plan_blocks(ctx.token_budget, enabled=self._block_plan)
    budget = plan.memory_tokens if plan is not None else 2048
    self._assembler.build(..., budget=budget, ...)
```

- `ctx.token_budget` 缺省 `0` ⇒ `plan_blocks` 返回 `None` ⇒ 直连构造的 `LoopContext`
  （大量既有测试）**逐字不变**。
- `block_plan=False`（缺省）⇒ 同上。**两重保险**，任一未接线都不改变行为。

## 开关合法性

`loop.block_plan`（缺省 `False`，独立访问器 + ConfigSpec 行 + 校验期拒绝非布尔字面量）。
规格只在**配额分配面**禁新键；本键在**启用面** —— 与 `0182` 的 `loop.compact_steps`
（压实**触发**阈值）同性质，`三层窗口比例分配` 原文已明文许可「触发阈值是另一面」。

注入面：与 `max_tokens` 同型，组合根算一次 `config.block_plan()`，注入**四个 loop
的全部 planner**（main / sub / beast / pet）—— 每只 loop 各自的 `ctx.token_budget` 派生各自的
额度，与 `token_budget` 的既有注入口径一致。

## 回归锚（真正的绊线）

读完既有用例后的**订正**：`tests/test_infomap_wiring.py:48` 与 `tests/test_phase13.py:185`
**不是**本 change 的绊线 —— 它们**自己**显式传 `budget=2048` 去调 `_assembler.build(...)`，
测的是装配器的契约，**从不**观察 `_system_prompt` 往 `build()` 里传了什么。

⇒ 真正的逐字锚必须是**新的**：用**桩装配器捕获 `build(budget=)`**，断言
「`block_plan` 关 ⇒ 捕获到 `2048`」。反证：把 `LLMPlanner(block_plan=False)` 缺省翻成 `True`
⇒ 该锚转红（且此时 `ctx.token_budget` 非零的用例才暴露差异）。

`tests/test_loop_token_accounting.py` 的两条精确增量用例**不受影响**：`_context_tokens`
只读 `history` / `messages` / `summary_long` / `summary_mid`，新字段 `token_budget` 不在其中。

## 已知局限（登记）

1. **四个非事实块的配比不驱动任何行为** —— 它们是**咨询性数字**（`BlockPlan` 的四个字段今日
   仅供观测/未来消费）。本 change **不**声称系统按五区块分配了窗口；如实登记「配比已表达、
   一个面已接线」。
2. **不覆盖 `_window_plan` 的 `//2`** —— 窗口面已有独立口径，统一它属另一个 change
   （会动历史回灌的预算，回归面更大）。
3. **块内不做二级分配** —— 「记忆」份额在关键事实 / 关系（`0203`）/ 摘要之间**不细分**
   （`cap` 有界，参 `0203`）。
