# 0152 · 任务清单（loop token 记账口径 / 账本 E96）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`loop` **MODIFIED**「错误与预算控制」（记账口径条款 + 2 Scenario）。
> 状态：**已归档**（2026-10-07）；四门禁全绿；`openspec validate --all` 归档前 31/0 ⇒ 归档后 30/0。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/loop/spec.md`（delta，MODIFIED）：「错误与预算控制」+ 记账口径条款 + 2 Scenario
- [x] 1.2 `openspec validate 0152-loop-token-accounting` ⇒ valid；`validate --all` ⇒ 归档前 31/0 ⇒ 归档后 30/0
- [x] 1.3 ADR-0144（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_loop_token_accounting.py`：planner 探针报出的提示 token 数被计入 ⇒ 本轮消息极短也能触发 `TOKEN_BUDGET_EXCEEDED`
- [x] 2.2 `tests/test_loop_token_accounting.py`：无探针 planner（既有替身形态）⇒ 退化为估算、本轮照常完成（**零回归**）
- [x] 2.3 `tests/test_loop_token_accounting.py`：探针抛错 ⇒ 降级为「无观测」、不阻断本轮
- [x] 2.4 `tests/test_loop_token_accounting.py`：`LLMPlanner.last_prompt_tokens()` 无 usage 时按**装配全量**估算（> 0，且含系统提示前缀）
- [x] 2.5 `tests/test_loop_token_accounting.py`：`LLMPlanner.last_prompt_tokens()` 以 provider 实报为**下界**（≥ 实报值，且 ≥ 纯估算）
- [x] 2.6 `tests/test_loop_token_accounting.py`：估算**计入工具 schema**（有工具 > 无工具）
- [x] 2.7 红态确认：实现前 4 红 / 2 护栏绿；实现后 6/6 绿（基线 1806 passed）

## 3. 实现

- [x] 3.1 `src/core/loop/planner.py`：`_last_prompt_tokens` 状态 + `last_prompt_tokens()` 探针 + `_estimate_prompt()`（装配全量估算）；`_complete` / `astream` 各在装配后记录（`_complete` 以 `max(估算, 实报)` 抬升下界）
- [x] 3.2 `src/core/loop/default.py`：`_context_tokens(ctx)` 统一记账（历史 + 本轮消息，口径同共享 `estimate_tokens`）；`perceive` / `observe` 改用之；`_reported_prompt_tokens()` 探针消费（缺省 / 异常 ⇒ 0）；删除被替代的 `_history_tokens`
- [x] 3.3 `src/core/runtime.py`：**零改动**（探针走 duck-typing，注入面不变）

## 4. 文档同步

- [x] 4.1 `doc/02-modules/loop.md`：§3.1.1 记账口径改为「覆盖全量装配 + provider 实报下界」
- [x] 4.2 `doc/03-interfaces/loop-interface.md`：§4 新增记账口径条款（含 `last_prompt_tokens` 探针，可选能力）
- [x] 4.3 `doc/04-testing/test-cases.md`：新增 `## 68.`（TC-TOKACC-01 ~ 07）
- [x] 4.4 `coding-plan/known-risk.md`：§1 `E96` → 已修（原文保留为「原判…已践行」）；§3 加 ADR-0144 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ 357 files already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ **1806 passed**（含本 change 新增 6 例）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（loop）⇒ `shutil.move` 至 `archive/2026-10-07-0152-loop-token-accounting/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E96 → 已修）；ADR-0144 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`fix(loop): token 记账覆盖全量装配，provider 实报为下界（change 0152）`
