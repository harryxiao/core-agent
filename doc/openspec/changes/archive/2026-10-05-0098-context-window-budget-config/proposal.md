# 0098 上下文窗口与预算三层可配（loop/context 预算参数化）

## Why

用户追问：「`TOKEN_BUDGET_EXCEEDED` 和 Context Window Size 可以改成可变参数吗 —— CLI 参数传入 /
配置文件写配置（没配就用代码内部预设默认值）/ WebUI·APP 有 UX 配置 LLM 的设置页面可以配置生效」。

一手核实：**三个预算参数都不是可配项，且组合根从不传参** ——

| 参数 | 现值 | 定义处 | 组合根 |
|---|---|---|---|
| `token_budget` | `65536` | `loop/default.py:121`（ctor kwarg） | `runtime.py:474/511/544/721` 四处 `DefaultLoop(...)` **均不传** |
| `max_rounds` | `10` | `loop/default.py:120` | 同上 |
| `round_threshold`（压实轮数触发） | `10` | `context/compactor.py:20`（类常量） | `runtime.py:293` `ContextCompactor(memory=memory)` 不传 |

后果：这些数字**只在源码里**，用户改不了；「更大窗口的模型」与「更省的预算」都无从表达。
而配置机制**早已就绪**（`ConfigSpec` 单一真源，三面自动生成），组合根消费范式**也早已就绪**
（`ConfigManager.circuit_breaker()` → `runtime.py:469`）。本 change 补的就是这一层**接线**。

## What Changes

- **新增配置项**（ConfigSpec 单一真源）：`llm.context_window`（模型上下文窗口，`0` = 未配）、
  `loop.output_reserve`（输出预留，缺省 `8192`）、`loop.max_rounds`（缺省 `10`）。
- **token 预算改为派生**：`llm.context_window > 0` 时 `token_budget = context_window - output_reserve`；
  未配置时回落内置缺省 `65536`（行为与变更前一致）。**不新增显式 `loop.token_budget`** —— 用户选的是
  「由窗口派生」，派生式即机制，少一层开关。
- 新增 `ConfigManager.loop_limits()`（照抄 `circuit_breaker()` 的形状）供组合根消费。
- `runtime.py` 四处 `DefaultLoop(...)` 补 `max_rounds` / `token_budget`。
- `entry.py` `_key_to_patch` 接受 `loop.` 前缀 ⇒ `config set loop.output_reserve 4096` 三面齐备。
- 校验期拒绝非法取值（非整数 / 越界 / **窗口不敷输出预留**），不静默兜底。

## Non-goals

- **不**把 `context.Compactor` 的 `round_threshold`（轮数维度压实触发）纳入配置 —— 用户问的是
  token 预算与上下文窗口；轮数维度独立，改动会牵动 context 规格的另一条 Requirement。留待后续。
- **不**做热更新生效与落盘（归 change `0099`）；**不**做 WebUI 设置页（归 change `0100`）。
- **不**把 `ctx.token_used` 从「`len//4` 粗估」改为模型回报用量 —— 那是**另一件事**（精确窗口管理），
  本 change 只把**阈值**变成可配。该局限记入 ADR-0091 的「已知边界」。
- **不**改缺省值本身（默认仍是 `65536` / `10`），保证变更后行为与变更前**逐位一致**。

## 风险

- **数值校验边界**：`context_window - output_reserve` 若 ≤ 0 会得到**非正预算**，而 `token_budget <= 0`
  在 `DefaultLoop._should_compact`（`loop/default.py:305`）语义是「**关闭 token 维度**」⇒ 静默地把
  用户的「配错」变成「预算维度失效」。故**必须在校验期拒绝**（交叉校验），不得依赖下游兜底。
- **`bool` 陷阱**：`True` 在 Python 里 `isinstance(x, int)` 为真 —— 校验须显式排除 `bool`，
  否则 `context_window: true` 会被当成 `1`。对齐 `_circuit_breaker_errors` 的既有口径。
- **未知段告警面变化**：`loop` 由「未知段（仅告警）」升为「已知段」。既有配置若已含 `loop:` 段，
  变更前会触发未知段告警、变更后不再告警 —— 这是**收敛**（该段如今真有语义并被校验），非回归。
