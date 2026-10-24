# Tasks — 计划轮可信度与可打断性（0316）

## 1. 规格与测试先行

- [x] 1.1 `proposal.md` / `design.md` / `specs/tool-use/spec.md`（MODIFIED ×1）/
      `specs/orchestration/spec.md`（MODIFIED ×1）/ `specs/ui/spec.md`（MODIFIED ×2）
- [x] 1.2 `tests/test_install_tools.py`（红）：`tools.list` 描述明示「不含内置原子工具」；
      载荷含 `note` 说明内置原子工具与插件状态无关、空清单不代表无工具
- [x] 1.3 `tests/test_self_run.py`（红）：`draft_plan` 回落归一（子任务目标 == 送入文本 ⇒
      还原为原始目标）；正常单子任务计划（目标不同）不被改写
- [x] 1.4 `tests/test_plan_mode.py`（红）：`plan.drafting` 在 `plan.draft_ready` **之前**产出，
      且在拆解调用**发起前**产出；更新既有事件序列断言
- [x] 1.5 `tests/test_repl.py`（红）：Ctrl+B 取消在途快速轮（忙态复位 + 输入恢复）；
      Ctrl+B 丢弃待决计划草案（模式回 quick、编排器不被驱动）；空闲 Ctrl+B 保持既有提示

## 2. 实现

- [x] 2.1 `src/core/tools/install_tools.py`：`list` 描述与载荷 `note`
- [x] 2.2 `src/core/orchestration/scheduler.py::draft_plan`：回落归一
- [x] 2.3 `src/core/ui/api.py::run_plan_turn`：拆解前产出 `plan.drafting`
- [x] 2.4 `src/core/ui/repl.py`：`plan.drafting` → 状态行「拆解计划中」；`_turn_worker` 登记
      （计划轮 / 快速轮 / 神兽轮）；`action_barge_in` 三态分支

## 3. 门禁

- [x] 3.1 聚焦跑：`uv run pytest tests/test_install_tools.py tests/test_self_run.py
      tests/test_plan_mode.py tests/test_repl.py tests/test_orchestration*.py` = **303 passed**
- [x] 3.2 全量 `uv run pytest` = **3653 passed**（基线 3646 ⇒ +7）
- [x] 3.3 `uv run ruff check` / `uv run ruff format --check`（改动文件）干净
- [x] 3.4 `uv run pyright`（`src`）= **0 errors**
- [x] 3.5 反证 **4/4**（`cp` 到 `/tmp` + `md5sum` 复原，复原后再跑聚焦全绿）：
      1. 去载荷 `note` ⇒ TC-PLANTURN-TOOLS-01 红；
      2. 去 `draft_plan` 回落归一 ⇒ TC-PLANTURN-DRAFT-01 红；
      3. 去 `plan.drafting` ⇒ TC-PLANTURN-UI-01/02 红；
      4. `action_barge_in` 恢复为仅 TTS 提示 ⇒ TC-PLANTURN-UI-03/04 红

## 4. 文档与收口

- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0306（+ 变更追踪行）
- [x] 4.2 `coding-plan/known-risk.md`：E252 + §3 ADR-0306 行
- [x] 4.3 `doc/04-testing/test-cases.md`：§229（TC-PLANTURN-* + 反证）
- [x] 4.4 `doc/03-interfaces/ui-interface.md`（`plan.drafting` / 草案归一 / Ctrl+B 三态）与
      `doc/03-interfaces/tool-use-interface.md`（`tools.list` 载荷注）同步
- [x] 4.5 `openspec validate --all` = **32 passed, 0 failed**（含本 active change）
- [ ] 4.6 用户确认后归档 + 提交；回填 walkthrough / MEMORY.md

## 5. 实测（2026-10-24）

- 聚焦：`tests/test_install_tools.py tests/test_self_run.py tests/test_plan_mode.py
  tests/test_repl.py tests/test_orchestration*.py` = **303 passed**。
- 全量：`uv run pytest` = **3653 passed**（基线 3646 ⇒ +7）。
- `uv run ruff check` / `ruff format --check`（8 个改动文件）干净；`uv run pyright`（`src`）=
  **0 errors, 0 warnings**。
- 反证 4/4（见 3.5），每次复原后 `md5sum` 与备份一致，并复跑聚焦确认全绿。
- `openspec validate --all`（含本 change）= **32 passed, 0 failed**。

## 6. 已知局限 / 未做

- `tools.list` 的纠偏是**提示性**的：模型仍可能忽略 `note` 自行推断；未引入结构化「可用工具」返回面。
- `draft_plan` 的回落判定只认**逐字相等**；拆解器未来若改变回落形态（如拆多子任务）须同步守卫。
- `Ctrl+B` 只取消 worker 协程：已在线程中执行的工具不停（线程不可中断，与 Ctrl+Q 的放弃语义一致），
  已发起的 LLM 请求可能仍在服务端计费。
- `plan.drafting` 是阶段信号，不携带进度百分比。
- 只覆盖 TUI（Web / CLI 无计划轮）。
