# 0097 上下文压实「出厂默认阈值」守护用例

## Why

用户问「记忆上下文累计默认超过多少需要压缩」时，一手核实出的答案是
**轮数 ≥ 10 或 token ≥ 65536**（`context/compactor.py:20`、`loop/default.py:121`）。
但回溯既有用例发现：**触发逻辑已被充分覆盖，默认值这一层没有**——

- `test_context.py::test_compactor_should_compact_threshold` —— 谓词边界，但**注入 budget=100**；
- `test_loop.py::_compacting_loop` 一族 4 例 —— loop 级触发（含 `token_budget=0` 守卫），
  但**全部注入 `round_threshold=1/100` 与 `token_budget=1/0`**。

⇒ **出厂默认值（10 / 65536）与「组合根未覆盖二者」这一事实无任何断言**：若有人把
`_ROUND_THRESHOLD` 或 `token_budget` 缺省改小/改大，现有 1102 例**全绿漏过**。

本 change 补这一层，属**行为不变的守护/特征化测试**（同 change `0060` E11① 先例）。

## What Changes

- 新增 `tests/test_context_compaction.py`（3 例）：
  1. `test_default_round_threshold_boundary` —— 默认轮数阈值 = 10（9 不触发 / 10 触发）；
  2. `test_default_token_budget_boundary` —— 默认 token 预算 = 65536（65535 不触发 / 65536 触发）；
  3. `test_loop_default_wiring_compacts_exactly_once_at_round_ten` —— **缺省装配**（不注入任何阈值）
     非终止动作连跑，压实**恰在第 10 轮触发一次**，loop 以 `LOOP_LIMIT_EXCEEDED` 终止
     （顺带锁住组合根未覆盖 `token_budget`）。
- **不改 `src/`**（`src/` 零改动）；**不加 spec delta**。

## Non-goals

- **不**改阈值、**不**把它做成 `ConfigSpec` 可配项 —— 本轮只补守护，是否可配属独立议题。
- **不**重复既有断言（谓词 / loop 级触发、`token_budget<=0` 守卫已各有用例）。
- **不**断言私有常量（`_ROUND_THRESHOLD`）；一律经公开行为断言。

## 风险

- 新增 3 例，全部**确定性、无网络、无 LLM**（驱动真实 `Compactor` / `DefaultLoop`）。
- 唯一可预见影响：若将来**有意**调整缺省阈值，此文件会红 —— 这正是其存在意义（须同步改这里）。
