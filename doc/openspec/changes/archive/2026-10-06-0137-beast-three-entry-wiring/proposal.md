# 0137 · beast 三入口接线收口（skip_specs）

> 账本：`coding-plan/phase-34.md` **E74**（三入口仅 CLI 可达）
> 规格面：**无 delta**（`beast-mode/spec.md`「Three-Entry Activation」两 Scenario 早已是硬 SHALL）｜ ADR：**0130**

## Why

`beast-mode/spec.md`「Three-Entry Activation」SHALL 三入口召唤（`/summon` 斜杠 / `summon` CLI /
WebUI 自然语言），并要求「三入口最终落到同一 `BeastSession` 生命周期」——但**生产只有 CLI 一条通**（E74）：

- `beast/activator.py` 的 `activate_from_slash` / `activate_from_nl`（及 `recall_from_slash` /
  `recall_from_nl` 孪生）**全仓零调用方**（契约方法层完备、接线缺）；
- `entry.py` 构造 `UIAPILayer` 时**未注入 `beast_activator`**，`ui/api.py` 只接了**宠物**的
  `activate_from_nl`（对称位置空缺）；
- `ui/repl.py` 的斜杠命令只有 `/focus` `/main` ⇒ `/summon` `/recall` 在 TUI 里**无入口**，
  输入被当普通对话发给 loop。

「契约备、接线缺」是本账的**判据订正**：`phase-17.5.md:45` 标「三入口已实现」实为
**契约方法层**实现，本 change 把它推到**生产可达**。

## What Changes

**全部为接线，不改语义**（规格中性 ⇒ `skip_specs`，先例 `0110` / `0083` / `0135`）：

1. `src/core/ui/errors.py`：补 `UI_BEAST_UNSET` / `UI_BEAST_UNKNOWN_VERB` / `UI_BEAST_NOT_FOUND` /
   `UI_BEAST_STATE_INVALID`（与 `UI_PET_*` 对称）。
2. `src/core/ui/api.py`：`UIAPILayer` 增 `beast_activator` 注入面 + 两个方法 ——
   - `async activate_beast(user_input) -> str`：WebUI 自然语言入口（对称 `activate_pet`；神兽激活是
     异步 handoff ⇒ 本方法为 async），走 `BeastActivator.activate_from_nl`；
   - `async beast_command(verb, target, *, task="") -> dict`：前台 `/summon` `/recall` 控制面
     （verb → `activate_from_slash` / `recall_from_slash`），返回 `result_summary()` 摘要 + `state`
     —— **结果正文只经只读查询面**（beast-mode spec「Task Result Visibility」）。
   两个入口均把**领域错误在 API 边界归一**（`repl` 只捕 `UiError`，漏一层就抛裸异常进 TUI worker）：
   `OrchestrationError`（无匹配神兽）⇒ `UI_BEAST_NOT_FOUND`；`BeastError`（重复召唤 / 无在岗可召回）
   ⇒ `UI_BEAST_STATE_INVALID` —— 二者是**兄弟类型**（无继承），**按用户可见语义分两码**，
   故较计划**多一码**（计划写三条）。
3. `src/core/ui/repl.py`：斜杠命令面补 `/summon <神兽> [任务]` 与 `/recall <神兽>`（经 `beast_command`），
   呈现状态行 + **有结果才打印**的结果行（与 `summon` CLI 同口径）；解析走纯函数 `_parse_beast_command`。
4. `src/core/entry.py`：构造 `UIAPILayer` 时注入 `beast_activator=runtime.beast_activator`（对称 pet）。
5. **不新增 HTTP 端点**：WebUI 自然语言入口是**消息驱动**（`UIAPILayer` 面），与 pet 同源
   —— 这正是 **E82 判为假阳性**的同一判据（见 change `0141`）。

## Impact

- 代码：`src/core/ui/errors.py`、`api.py`、`repl.py`、`src/core/entry.py`（4 处，均为接线/呈现）。
- 测试：`tests/test_ui.py`（+9）、`tests/test_repl.py`（+1 解析）、`tests/test_beast_wiring.py`（+2 生产装配）
  ⇒ `.venv/bin/pytest -q` **1651 passed**（基线 1639 + 12）。
- 文档：`doc/03-interfaces/beast-mode-interface.md`（§7 三入口落点）、`doc/03-interfaces/ui-interface.md`
  （§1 方法面 / §5 错误码 / REPL 命令面）、`doc/04-testing/test-cases.md`（§53）、ADR-0130。
- 兼容：新增可选注入面与方法，既有调用方零改动；beast 门控关闭时 `runtime.beast_activator is None`
  ⇒ 入口报 `UI_BEAST_UNSET`（fail-explicit，与 pet 同型）。

## 已知局限

- WebUI **自然语言「召唤 X 兽做 Y」的意图解析**仍是骨架启发式（`_resolve_nl` 取首个词元，
  `activator.py` 自注「Agent 理解意图 deferred」）——本 change **不**接 LLM 意图理解，
  只把入口接通；该 deferred 项属 phase-17.5 遗留，不在本账 25 条内。
- 三端**渲染**统一为折叠块之外的一行状态 + 一行结果（TUI）；Web/APP 沿用既有消息呈现，
  不为神兽另设前端组件（与 E82 判据一致）。
