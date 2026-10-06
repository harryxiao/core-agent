# Tasks · 0137 beast 三入口接线收口（skip_specs）

## 1. 规格（先行）

- [x] 1.1 **无 delta**（`beast-mode/spec.md`「Three-Entry Activation」/「Manual Recall」两 Scenario 早已是硬 SHALL，
      实现侧纯背离 ⇒ conformance）：写 `.openspec.yaml`（`schema: spec-driven` + `skip_specs: true`，先例 `0110`/`0083`）
- [x] 1.2 `openspec validate 0137-beast-three-entry-wiring` 通过

## 2. 测试（先行 · 红）

- [x] 2.1 `tests/test_ui.py`：`beast_command` / `activate_beast` 未接 ⇒ `UI_BEAST_UNSET`
- [x] 2.2 `tests/test_ui.py`：未知动词 ⇒ `UI_BEAST_UNKNOWN_VERB`；无匹配神兽 ⇒ `UI_BEAST_NOT_FOUND`；
      无在岗可召回 ⇒ `UI_BEAST_STATE_INVALID`（两类领域错误分别归一，见 3.2）
- [x] 2.3 `tests/test_ui.py`：替身 activator ⇒ verb 落到 `activate_from_slash` / `recall_from_slash`，
      返回摘要含 `agent_id` / `state` / `result_summary` 字段
- [x] 2.4 `tests/test_ui.py`：TUI `/summon <兽> <任务>` 与 `/recall <兽>` 落时间线（状态行 + 结果行）
- [x] 2.5 `tests/test_repl.py`：`_parse_beast_command` 形态解析（合法 / 无目标 / 非本命令）
- [x] 2.6 `tests/test_beast_wiring.py`：生产装配 `activate_beast` 落到同一 `BeastManager`；
      `beast_command("summon", …)` 端到端返回结果正文（离线桩 LLM）
- [x] 2.7 **验绿**：实现后全绿（红因接线缺席而红 —— 方法/字段/命令不存在）

## 3. 实现（仅接线，不改语义）

- [x] 3.1 `src/core/ui/errors.py`：`UI_BEAST_UNSET` / `UI_BEAST_UNKNOWN_VERB` / `UI_BEAST_NOT_FOUND` /
      `UI_BEAST_STATE_INVALID`（**较计划多一码**：`BeastError` 与 `OrchestrationError` 是兄弟类型，
      按「无此兽」/「有此兽但不在岗」两类用户动作纠错分码，不并作一码）
- [x] 3.2 `src/core/ui/api.py`：注入面 `beast_activator` + `activate_beast` + `beast_command`
      ＋私有 `_beast_error` 归一（`OrchestrationError` → `UI_BEAST_NOT_FOUND`；
      `BeastError` → `UI_BEAST_STATE_INVALID`）
- [x] 3.3 `src/core/ui/repl.py`：`_parse_beast_command` 纯函数 + `/summon` `/recall` 分发 + `_run_beast_turn`
- [x] 3.4 `src/core/entry.py`：`UIAPILayer(beast_activator=runtime.beast_activator)`

## 4. 文档

- [x] 4.1 `doc/03-interfaces/beast-mode-interface.md`：§7 补「三入口生产落点」表（斜杠 → `UIAPILayer.beast_command`；
      NL → `activate_beast`；CLI → `entry._summon`）
- [x] 4.2 `doc/03-interfaces/ui-interface.md`：§1 方法面补 `activate_beast` / `beast_command`；§5 错误码补三条；REPL 命令面
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0130 + `## 变更追踪` 行
- [x] 4.4 `doc/04-testing/test-cases.md`：§53（TC-BEAST3，change 0137 / ADR-0130，账本 E74）

## 5. 门禁（直连二进制，禁 `uv run`）

- [x] 5.1 `.venv/bin/ruff check src tests` —— 绿
- [x] 5.2 `.venv/bin/ruff format --check src tests` —— 绿
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` —— 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` —— **1651 passed**（基线 1639 + 12：test_ui +9、test_repl +1、test_beast_wiring +2）
- [x] 5.5 `openspec validate --all` —— **31 passed / 0 failed**（active 期含本 change；skip_specs 不增 cap ⇒
      归档后回落 30 / 0）

## 6. 收口

- [x] 6.1 手工归档至 `archive/2026-10-06-0137-beast-three-entry-wiring/`
- [x] 6.2 台账回填：`coding-plan/phase-34.md`（E74 行 + §9 表）；`coding-plan/README.md` 3 处索引行
- [x] 6.3 记忆更新：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 6.4 单次提交（`fix(ui): beast 三入口接线收口（change 0137）`）
