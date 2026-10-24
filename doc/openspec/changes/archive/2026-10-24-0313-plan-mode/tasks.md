# Tasks — plan 模式、`/task` 收敛与单子任务自跑（0313）

## 1. 规格与测试先行

- [x] 1.1 `proposal.md` / `design.md` / `specs/ui/spec.md`（MODIFIED ×1 + ADDED ×1）/
      `specs/orchestration/spec.md`（MODIFIED ×1 + ADDED ×1）
- [x] 1.2 新增 `tests/test_plan_mode.py`（红）：
      - `PlanSessions` 缺省 quick / 非法模式拒绝 / 草案覆盖 / take 一次性 / 会话隔离
      - `UIAPILayer.run_plan_turn`：只读循环产出 `plan.draft_ready`；草案字段不含勘察原文；
        未注入 plan loop / 编排器 ⇒ `UI_PLAN_UNAVAILABLE`；非 plan 模式 ⇒ `UI_PLAN_MODE_INVALID`
      - `approve_plan`：以批准的计划 + `self_run=True` + 同会话执行；先回 quick；旧草案 ⇒
        `UI_PLAN_DRAFT_NOT_FOUND`；`discard_plan` 丢弃并回 quick
      - 只读工具子集：仅 READ 级、显式排除 `tools.delegate`、写工具调用 fail-closed
- [x] 1.3 新增 `tests/test_self_run.py`（红）：
      - 单子任务 + `self_run=True` ⇒ 主 loop 收到交接 prompt，router 不被调用
      - 多子任务 + `self_run=True` ⇒ 走既有路由，主 loop 不被调用
      - 缺省 `self_run=False` ⇒ 单子任务也走路由（逐字不变）
      - 未注入 `self_loop` ⇒ 回落路由
      - 自跑失败 ⇒ 既有重试 1 次 / 重拆 1 次 / `FAILED` 语义不变
      - `draft_plan`：上下文有界、`plan.goal` 还原为原始目标、零检查点 / 零 trace
- [x] 1.4 更新既有断言：TUI 命令真源（去 `/task`、加 `/plan` `/quick`）、欢迎语 /
      placeholder 文案、分发用例；确认 `tests/test_repl.py` 其余用例不受影响

## 2. 实现

- [x] 2.1 `src/core/tools/provider.py`：`ToolProvider.subset(tool_ids)` —— 共享依赖、复制
      工具表的只读视图（执行面同样受限）
- [x] 2.2 `src/core/orchestration/scheduler.py`：
      - 构造 `self_loop`；`run` / `astream` 增 `self_run`；沿执行管道显式透传
      - `_run_subtask` 执行者解析（单子任务 + self_run ⇒ `self_loop`；否则既有路由）
      - `handoff_stream` 改直连 `stream_handoff`（同一实现）
      - 新增 `draft_plan(goal, success_criteria=None, *, context="")`
- [x] 2.3 `src/core/ui/plan.py`（新）：`PlanDraft` / `PlanSessions`（进程内、会话级）
- [x] 2.4 `src/core/ui/errors.py`：`UI_PLAN_MODE_INVALID` / `UI_PLAN_UNAVAILABLE` /
      `UI_PLAN_DRAFT_FAILED` / `UI_PLAN_DRAFT_NOT_FOUND`
- [x] 2.5 `src/core/ui/api.py`：`plan_loop` 注入面 + `agent_mode` / `set_agent_mode` /
      `run_plan_turn` / `approve_plan` / `discard_plan`
- [x] 2.6 `src/core/runtime.py`：主 loop 与 plan loop 同工厂构造；只读工具 id 派生
      （`PolicyEngine.classify == READ`，排除 `tools.delegate`）；`Runtime.plan_loop`；
      `TaskScheduler(self_loop=loop)`
- [x] 2.7 `src/core/entry.py`：`UIAPILayer(plan_loop=runtime.plan_loop)`
- [x] 2.8 `src/core/ui/repl.py`：命令真源（删 `/task`、加 `/plan` `/quick`）、专用分发、
      计划轮与 y/n 审批、`_handle_turn_event` 抽取、placeholder / 欢迎语文案

## 3. 门禁

- [x] 3.1 聚焦跑：`uv run pytest tests/test_plan_mode.py tests/test_self_run.py tests/test_repl.py
      tests/test_scheduler.py tests/test_orchestration*.py`
- [x] 3.2 全量 `uv run pytest`（基线 3609）
- [x] 3.3 `uv run ruff check` / `uv run ruff format --check`（改动文件）
- [x] 3.4 `uv run pyright`（`src` 0 error）
- [x] 3.5 反证（`cp` 到 `/tmp` + `md5sum` 复原）：
      去掉 delegate 排除 ⇒ 只读面用例红；`self_run` 缺省改 True ⇒ 逐字不变用例红；
      `approve_plan` 不先回 quick ⇒ 失败后模式用例红；`draft_plan` 不还原 `plan.goal` ⇒
      目标用例红；TUI 恢复 `/task` ⇒ 命令真源用例红

## 4. 文档与收口

- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0303（plan 为会话级产品模式、草案进程内临时；
      甲-2 确定性自跑；被拒方案见 design §3）
- [x] 4.2 `coding-plan/known-risk.md`：E249 + §3 局限行
- [x] 4.3 `doc/04-testing/test-cases.md`：§226（TC-PLAN-* / TC-SELFRUN-* + 反证）
- [x] 4.4 `doc/03-interfaces/ui-interface.md`（或 ui-scheme）/ `orchestration-interface.md`
      同步新接口；`doc/02-modules/orchestration.md` / `ui.md` 记述模式与自跑
- [x] 4.5 `openspec validate --all` 全绿；全量 pytest 实测数与反证结果回填本文件
- [x] 4.6 用户确认后归档 + 提交；回填 walkthrough / MEMORY.md

## 5. 实测（2026-10-24）

- 聚焦：`tests/test_plan_mode.py tests/test_self_run.py tests/test_repl.py` + 调度器回归
  = **173 passed**；`tests/test_repl.py` 单跑 **111 passed**。
- 全量：`uv run pytest` = **3629 passed**（基线 3609 ⇒ +20）。
- `uv run ruff check` / `ruff format --check` 干净；`uv run pyright`（`src`）= **0 errors**。
- 反证 **5/5**（`cp` 到 `/tmp` + `md5sum` 复原）：
  1. 去掉 `readonly_tool_ids` 的 `tools.delegate` 排除 ⇒ 只读面用例红；
  2. `self_run` 缺省改 `True` ⇒ 逐字不变（多子任务仍走路由 / 缺省走路由）用例红；
  3. `approve_plan` 不先回 `quick` ⇒ 执行前模式用例红；
  4. `draft_plan` 不还原 `plan.goal` ⇒ 目标用例红；
  5. TUI 恢复 `/task` ⇒ 命令真源 / 分发用例红。
- `openspec validate --all`（含本 change）= **32 passed, 0 failed**。

## 6. 已知局限 / 未做

- 草案为**进程内**、一会话一份、一次性：进程重启即丢（与「会话内临时」裁决一致，不落盘）。
- plan 模式的勘察循环与 quick 模式的循环**同工厂构造**，仅工具面收窄为 READ（`tools.delegate` 显式
  排除）；未做独立的勘察 prompt / 预算档位。
- 自跑只覆盖**单子任务**；多子任务仍由 router 派发（本轮不做「plan 内多子任务自跑」）。
- 观察者窗口 / Web 端未接计划批（`plan.draft_ready` 为 UI 层事件，SPA 不呈现）。

