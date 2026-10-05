# 0098 设计：预算派生口径与三面接线

## 1. 派生 vs 显式

**决策：token 预算由 `llm.context_window` 派生，不新增显式 `loop.token_budget`。**

| 方案 | 取舍 |
|---|---|
| 显式 `loop.token_budget` | 最直接，但用户仍须自己算「窗口减预留」；窗口与预算**可配出矛盾**（如窗口 8k、预算 200k） |
| **派生（采纳）** | 单一真源 = 模型窗口；用户只声明「模型多大」与「留多少给回复」，矛盾不可表达 |

用户裁决即此项（「固定保留输出头寸」）。派生的**代价**是灵活性：想让预算与窗口脱钩（如故意配小）
就做不到 —— 记入 Non-goals。

## 2. 为什么是「减预留」而不是「乘比例」

- 比例（`×0.75`）在大窗口上留出过多（131072 → 98304，白扔 32k），小窗口上留出不足
  （4096 → 1024，给回复只剩 3k）。
- 预留是**绝对量**：回复长度与窗口大小**无关**（一次回复几百到几千 token），故用绝对预留更贴合语义。
- 用户裁决即此项。

## 3. 落点：`extra` 而非结构化段

`llm` 已是 `_STRUCTURED_SECTIONS` 成员 ⇒ `context_window` 直接进 `LLMConfig`（两处构造点同改：
`manager.py:471` 与 `:693`）。

`loop` 是**新段**：本仓 yaml 子集解析器只认「结构化段 + ConfigSpec 声明段 + `extra` 已知段」。
照 `constraints` / `permission` 先例，`loop` 寄居 `extra`（`_KNOWN_EXTRA_SECTIONS` 加 `"loop"`），
由 `ConfigManager.loop_limits()` 读取 —— 与 `circuit_breaker()`（`manager.py:380`）**同构**：
「配置层不 import 能力层，缺省值在配置层复述」。

## 4. 校验为什么必须在校验期（而非下游兜底）

`token_budget <= 0` 在 `DefaultLoop._should_compact`（`loop/default.py:305`）的语义是
「**关闭** token 维度判定」，在 `:243` 则「不触发 `TOKEN_BUDGET_EXCEEDED` 硬停」。
故若允许 `context_window - output_reserve <= 0` 通过校验，用户的**配置错误**会静默变成
「预算维度失效」—— 与 `_circuit_breaker_errors` 拒绝「阈值 0 ⇒ 首个失败即熔断」同型。
**结论：交叉校验在校验期做，报错即阻断。**

`bool` 陷阱：`isinstance(True, int)` 为真 ⇒ 校验须显式排除 `bool`（对齐既有 `_as_number` 口径）。

## 5. 变更后行为等价性（回归锚点）

未配 `llm.context_window` 时：`token_budget = 65536`、`max_rounds = 10` ——
与变更前**逐位一致**。既有 1105 例（含 `test_loop.py` 一族）应全绿，任何变红即说明接线引入了回归。

## 6. WebUI 热更新与本 change 的边界

本 change 只做**装配期**参数化（启动时生效）。运行期热更新 + 落盘归 change `0099`
（`DefaultLoop` 需可变的 `set_limits`），WebUI 设置页归 `0100`。三者**顺序不可换**：
0099 依赖本 change 的 `loop_limits()` 与派生口径。
