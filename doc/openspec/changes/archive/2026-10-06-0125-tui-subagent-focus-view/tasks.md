# tasks — TUI 子 Agent 焦点视图（change 0125 / phase-33 切片 B：E61）

## 1. 规格（先行）
- [x] 1.1 `specs/ui/spec.md`：ADDED「TUI 子 Agent 焦点视图」——三入口（`/focus <sid>` / `/main` / `F2`）+
      焦点视图呈现标题/状态/详情 + 实时刷新 + 返回后主时间线逐字不变 + 未知标识不切换 + 运行中可用 +
      友好名不泄露 id·参数 + `task_started`/审批挂起回主视图
- [x] 1.2 同 delta：**6** 个 Scenario（聚焦显示子任务框 / 返回后逐字不变 / 聚焦期间实时刷新 /
      未知标识不切换 / 运行中可用 / 不泄露 id·参数）
- [x] 1.3 用户裁决沿用：phase-33 §1/§3 已裁决「焦点视图（presentation-only）」+「CLI 内嵌面板 +
      main/subagent 来回」+「命令 + F2」+「Web 沿用 `TaskPanel`」——本 change 即该裁决的落地，**未新增**裁决点
- [x] 1.4 判据订正 2 条写入 proposal（原 (b) 与 `0122`/`0124` 逐字同义 = 0 增量 ⇒ 重定义为「焦点」；
      焦点须**绑定 widget 身份**而非 sid —— `self._open` 跨任务不清空且 sid 重复）
- [x] 1.5 `openspec validate 0125-tui-subagent-focus-view` 通过（"Change ... is valid"）

## 2. 测试（先红）
- [x] 2.1 `tests/test_repl.py` 增 **6** 用例（同文件既有 headless 基建：`app.run_test()` + `_timeline_text`；
      另抽 `_panel_text` / `_GatedOrchestrator` / `_type_line` / `_wait_started` 四个小助手）：
      - `test_focus_shows_subtask_panel_and_hides_timeline`：`/focus 1` ⇒ `#panel.display is True` /
        `#timeline.display is False` / 标题含 `▸ 子任务 1` 与 `⟳` / 正文含 `验收：`；**且 `loop.inputs == []`**
      - `test_focus_panel_refreshes_on_milestone_and_completion`：放行里程碑 ⇒ 正文出现 `⏺ Bash ✓ (1.5s)`；
        放行收尾 ⇒ 标题含 `✓`（`⟳` 已替换）、正文含 `判定：` 与结果节选
      - `test_returning_to_main_view_leaves_timeline_unchanged`：`/main` 回主视图 ⇒ 时间线可见且
        `_timeline_text(app) == before`（**逐字不变**＝presentation-only 的最强证明）
      - `test_focus_command_bypasses_busy_rejection`：忙态中按 `F2` 生效（时间线复现）且 `_turn_busy` 仍真
      - `test_focus_unknown_subtask_keeps_main_view`：未开工即聚焦 / 未知标识 99 ⇒ 均不切换，提示「未找到」
      - `test_focus_panel_does_not_leak_tool_id_or_args`：面板含 `Bash`，**不含** `tools.code_run` / `print(1)`
- [x] 2.2 红：实测 `tests/test_repl.py` **6 failed / 22 passed**（首红根因：`#panel` 不存在 ⇒
      `NoMatches`；且 `/focus` / `/main` 未被识别 ⇒ 落进 `_run_turn`，收尾时 `_spin_stop` 撞
      `No nodes match '#spinner' on Screen`）

## 3. 实现
- [x] 3.1 `ui/repl.py` CSS 增 `#panel`（`height: 1fr; overflow-y: auto`）与 `#panel-title`（accent 加粗）
- [x] 3.2 `ui/repl.py` `BINDINGS` += `("f2", "focus_main", "返回主视图")`；`_HINTS_SHORT`/`_HINTS_FULL`
      补 `/focus <子任务> 聚焦 · /main 或 F2 返回主视图`
- [x] 3.3 `ui/repl.py` `compose()` 增 `Vertical(id="panel")`（`Static(id="panel-title")` +
      `Static(id="panel-body", classes="hint", markup=False)`），置于 `#spinner` **之前**；`on_mount`
      **命令式**置隐 `#panel`（与既有 `#spinner` 同法；Textual `display` setter 有「遗忘原值」TODO）
- [x] 3.4 `ui/repl.py` 新状态 `_focus_sid` / `_focus_box` / `_focus_detail` + 新方法 `_set_focus`
      （`""` 且已在主视图 ⇒ 早退；未命中 ⇒ `False` 不切换）/ `_render_panel` /
      `_handle_focus_command`（成功**零时间线写入**，仅失败给提示）/ `action_focus_main`
- [x] 3.5 `ui/repl.py` `on_input_submitted`：`_handle_focus_command(text)` **先于忙态拒绝**拦焦点命令；
      忙态**之后**、回显**之前**加 `self._set_focus("")`（普通输入回主视图）
- [x] 3.6 `ui/repl.py` 身份守卫刷新：`_progress_subtask` 末尾 `if detail is self._focus_detail` +
      `_complete_subtask` **两个出口**（skipped 早退 **与** 正常收尾）同一守卫
- [x] 3.7 `ui/repl.py` 强制回主视图：`_ask_approval`（首行）+ `_add_task_widget` 的 `task_started` 分支
- [x] 3.8 **未触** `format_task_event` / `format_action_event` / `_format_event` / `repl_loop`
      （非交互 `task` 输出逐字不变；`git diff` 仅落在 `ReplApp` 类内）

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests` —— All checks passed
- [x] 4.2 `.venv/bin/ruff format --check src tests` —— 352 files already formatted
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright` —— **0 errors, 0 warnings, 0 informations**
- [x] 4.4 `.venv/bin/pytest -q` —— **1599 passed**（基线 1593 ⇒ 新增 **6** 例；`tests/test_repl.py` 22 ⇒ 28）
- [x] 4.5 `openspec validate --all` —— 归档前 **31 passed / 0 failed**；归档后 **30 passed / 0 failed**
- [x] 4.6 端到端（离线，不触网）：真 `TaskScheduler`（打桩 `planner` 拆解器 + 打桩子 Agent loop
      产出 `action_started` / `action_completed` / `step_completed` / `loop_finished`）经 `UIAPILayer.run_task`
      驱动 headless TUI ⇒ **10/10** 断言全绿：面板可见 + 时间线隐藏 + 标题含 `▸ 子任务 1` 与 `⟳` +
      正文含验收 + 里程碑 `⏺ Bash ✓ (1.5s)` + 判定 + 结果节选 + **不含** `tools.code_run` / `print(1)` +
      `F2` 回主视图；回归：既有 22 例 `test_repl.py` 全绿、全库 1593 例无回归

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/ui/spec.md`（插在「TUI 子任务运行态与详情」
      **之后**、「Web 界面访问」之前 —— 与 TUI 条款同组；排版对齐邻块：Scenario 标题下**不留空行**；
      正文段拆为 4 段短段，避免触发「Requirement text is very long」INFO）
- [x] 5.2 `shutil.move` 进 `doc/openspec/changes/archive/2026-10-06-0125-tui-subagent-focus-view/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：ADR-0118 + 变更追踪行（焦点视图 = presentation-only 消费面接线 /
      为何 `display` 而非 unmount / 为何**身份绑定**而非 sid / 为何审批·新任务回主视图 / 为何 Web 不改 /
      判据订正 2 条 / 已知局限 4 条）
- [x] 6.2 `doc/03-interfaces/ui-interface.md`：TUI 焦点视图 + `/focus` / `/main` / `F2` 三入口
- [x] 6.3 `doc/04-testing/test-cases.md`：新 TC 节（`TC-TUI-06`~）+ 端到端离线冒烟说明
- [x] 6.4 `coding-plan/phase-33.md`：§3 裁决点 2 → **已裁决**（交互范围 = 内嵌面板 + 命令/F2；Web 沿用）
      + §2/§5 E61 标 ✅（**编辑落盘**）+ `coding-plan/README.md` 索引同步（**随提交**）
- [x] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [ ] 7.1 单次提交：`feat(ui): TUI 子 Agent 焦点视图（change 0125）`
- [ ] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（含 `settings.json`，D4 不动）、
      `coding-plan/phase-3-prompt.md`、`AI-SoftwareEngineer-4.md`、`coding-plan/phase-32.md`、
      `src-tauri/Cargo.lock`、`node_modules/`、`frontend/dist/`
