# Tasks — 计划轮延迟与勘察工具面保真（0317）

> 规格先行：先落 delta（tool-use MODIFIED ×1、orchestration ADDED ×1、ui ADDED ×1），再红→绿。

## 1. 规格

- [x] 1.1 `specs/tool-use/spec.md`：MODIFIED「工具参数查询」——补受限视图目录口径 + Scenario
  「受限视图不泄漏视图外工具」。
- [x] 1.2 `specs/orchestration/spec.md`：ADDED「拆解与验收调用的输出上界」。
- [x] 1.3 `specs/ui/spec.md`：ADDED「计划拆解的等待上界」。
- [x] 验证：`openspec validate 0317-plan-turn-latency` 绿。

## 2. 红测（先写、确认失败）

- [x] 2.1 `tests/test_plan_mode.py::test_plan_tool_view_schema_read_does_not_leak`：根面注册
  `tools.web_fetch`，计划视图内 `schema_read()` 无参列表不含它，按 id 请求落 `unknown` 且无 schema。
- [x] 2.2 `tests/test_plan_mode.py::test_run_plan_turn_draft_timeout_is_structured`：拆解挂起
  > 上界 ⇒ `UI_PLAN_DRAFT_FAILED`，文案含上界与 `/quick`，且无 `plan.draft_ready`、无草案。
- [x] 2.3 `tests/test_orchestration.py`：拆解器 / 验收器注入 `max_tokens=123` ⇒ 请求携带 123；
  未注入 ⇒ `None`（逐字不变）。
- [x] 验证：三条用例在未改动实现前**均红**。

## 3. 实现

- [x] 3.1 `src/core/runtime.py`：新增 `_plan_tool_view(tools)`（subset + `SCHEMA_READ_TOOL_ID`
  重绑到 `view.active_tools`），计划视图构造改用它。
- [x] 3.2 `src/core/orchestration/planner.py`：`LLMSubtaskPlanner` / `LLMVerifier` 接受可选
  `max_tokens`；仅正数写入请求。
- [x] 3.3 `src/core/runtime.py`：planner / verifier 注入 `config.output_reserve()`（与主 planner 同源）。
- [x] 3.4 `src/core/ui/api.py`：`UIAPILayer(..., plan_draft_timeout=None)`；
  `run_plan_turn` 用 `asyncio.wait_for` 包住 `draft_plan`，超时 ⇒ `UI_PLAN_DRAFT_FAILED`。
- [x] 验证：三条红测转绿；既有 `tests/test_plan_mode.py` / `test_orchestration.py` / `test_ui_api.py` 不回归。

## 4. 门禁

- [x] 4.1 `uv run pytest`（全量）全绿。
- [x] 4.2 `uv run ruff check src tests` + `uv run ruff format --check src tests` 干净。
- [x] 4.3 `uv run pyright` 无新增错误。
- [x] 4.4 反证（`cp` → `/tmp` 改坏 → 复原 → `md5sum` 比对）：
  - 去目录重绑 ⇒ 2.1 红；
  - 去 `max_tokens` 透传 ⇒ 2.3 红；
  - 去 `wait_for` ⇒ 2.2 红。
- [x] 4.5 `openspec validate --all` 32/0（含本 active change；归档后 31/0）。

## 5. 文档与台账

- [x] 5.1 `doc/01-architecture/adr.md`：ADR-0307（视图目录绑定 + 拆解输出上界 + 拆解墙钟）。
- [x] 5.2 `doc/04-testing/test-cases.md`：§230 用例表。
- [x] 5.3 `coding-plan/known-risk.md`：E253（端点长尾不可控、在途线程不可取消）。
- [x] 5.4 `doc/03-interfaces/`：`ui-interface.md`（拆解上界与错误码）、`tool-use-interface.md`
  （受限视图目录口径）、`orchestration-interface.md`（`max_tokens` 构造参数）。

## 6. 收口（须用户确认）

- [ ] 6.1 归档 `openspec archive 0317-plan-turn-latency -y`。
- [ ] 6.2 提交（`feat(ui): …（change 0317 / ADR-0307 / 台账 E253）`）。
- [ ] 6.3 推送 `origin/phase20-base`。
