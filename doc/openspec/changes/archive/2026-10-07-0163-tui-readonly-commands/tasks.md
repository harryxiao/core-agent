# 0163 · 任务清单

> 承 change `0162`（只读诊断源 `core/diagnostics`，ADR-0153）—— 本 change 是它的**第二个消费面**。
> 编号说明：原计划的 `0162`（TUI 只读命令族）因 `0161` 撞号事故顺延为 **`0163`**。

## 1. 规格与决策（先行）

- [x] 1.1 `specs/ui/spec.md` **ADDED** Requirement「TUI 只读诊断命令」+ 6 Scenario
- [x] 1.2 **ADR-0154**（真源驱动分发 / 只读命令不豁免忙态 / 不进对话不回显 / `Deps` 单接缝 /
      `/sessions` 同名异义 / 无参数面）+ 变更追踪行
- [x] 1.3 `openspec validate 2026-10-07-0163-tui-readonly-commands` ⇒ valid

## 2. 测试先行（红）

- [x] 2.1 `tests/test_repl.py`：`test_registry_commands_are_all_dispatchable` **扩到 13 条**
      （7 条新增的规范形态各驱动一次，断言 `RecordingLoop.inputs` 不增长）
- [x] 2.2 同上：新增 `test_registry_handlers_resolve`（每条 `handler` 在 app 上**解析得到**，防登记名笔误）
- [x] 2.3 同上：7 条只读命令各落结果块且**不进对话**（时间线新增 + 无 `❯` 回显 + `loop.inputs == []`）
- [x] 2.4 同上：**零副作用** —— `/status` 前后会话标识 / 会话数 / 转录条数 / 时间线三面（含既有 Markdown
      块与围栏数）逐字不变、恰好**多一条**结果块
- [x] 2.5 同上：忙碌中提交 `/doctor` ⇒ 拒绝（提示处理中）、时间线逐字不变
- [x] 2.6 同上：`/config` / `/doctor` 输出**逐字不含**注入的哨兵密钥值（含引用名在）
- [x] 2.7 同上：`/doctor 额外参数` ⇒ 只提示不执行；`/zzz` ⇒ 仍进普通对话（零回归）
- [x] 2.8 同上：一级候选清单用例按新真源（13 条）更新
- [x] 2.9 红态确认：`tests/test_repl.py` ⇒ **19 failed / 51 passed**（全为 `UIAPILayer.__init__()
      got an unexpected keyword argument 'diagnostics'`）

## 3. 实现（绿）

- [x] 3.1 `src/core/ui/repl.py`：`_Command` 增 `handler: str = ""`；`_COMMANDS` 追加 7 条只读命令
- [x] 3.2 同上：`on_input_submitted` 在**忙态检查之后**插 `_dispatch_registered(text)`（与 `/resume` 同侧）
- [x] 3.3 同上：`_dispatch_registered` + `_readonly_report`（`Deps` → 一条结果块）+ 7 个 `_show_*`
- [x] 3.4 `src/core/ui/api.py`：`__init__` 增 `diagnostics: Deps | None`；暴露 `diagnostics()` 访问器
- [x] 3.5 `src/core/entry.py`：`_diag_deps(args, *, tools=, config=)` 增可选覆盖；`_build_ui` 注入
      `diagnostics=_diag_deps(args, tools=runtime.tools, config=runtime.config)`

## 4. 文档

- [x] 4.1 `doc/03-interfaces/ui-interface.md` §2 补段（TUI 只读命令族；并更正 REPL 段「运维命令面……不并入
      REPL」—— 只读族已进 REPL，写操作族仍不并）
- [x] 4.2 `doc/04-testing/test-cases.md` 增 `## 77.`（TC-READONLY，7 条）
- [x] 4.3 `coding-plan/known-risk.md` §3 增 ADR-0154 局限行

## 5. 收口

- [x] 5.1 四门禁：`ruff check` / `ruff format --check` / `pyright`（0/0/0）/ `pytest -q`（1922 → **1923**）
- [x] 5.2 手工归档（本仓 `openspec archive` 必失败）：delta 合进 `specs/ui/spec.md` ⇒ `mv` 至
      `changes/archive/2026-10-07-0163-tui-readonly-commands/` ⇒ `openspec validate --all`
- [x] 5.3 台账 + 记忆（`MEMORY.md` / `coding-plan-leftover-walkthrough.md`）
- [x] 5.4 单次提交 `feat(ui): TUI 只读命令族（7 条，真源驱动分发）`

## 与计划的有意偏离（记录）

- **`repl.py` 会 import `core.diagnostics`**（计划原写「不 import，只经 api 层拿 `Report`」）。
  理由：① 无环 —— `core.diagnostics` **不** import `core.ui`（0162 已有 AST 守护），且 `ui` 与
  `diagnostics` 同为 capability 层（`test_phase0_modules_no_reverse_dependency` 只管 BASE → CAPABILITY，
  不涉此边）；② 7 条命令**一致走一条调用路径**优于「2 条经 api、5 条直连」的两套；③ `render` 与
  五张视图是**纯函数**，引用它们不是「另写一份逻辑」。故 `UIAPILayer` **只**暴露 `diagnostics()`
  一个访问器（计划里的 `doctor_report()` / `status_report()` 薄委托**不做** —— 无人消费的间接层）。
- **`_show_report` 定名 `_readonly_report`**（3.3）：取名即职责 —— 它是「取数（`api.diagnostics()`）+
  落块」的**只读**通道（未接线时给提示），不是通用的 `Report` 渲染器。
- **零副作用用例并入一条**（2.4）：断言点（会话标识 / 会话数 / 转录条数 / 时间线三面）同属一个场景
  ⇒ 一个 `run_test` 会话内一次驱动，避免为同一不变量重复起 TUI。
