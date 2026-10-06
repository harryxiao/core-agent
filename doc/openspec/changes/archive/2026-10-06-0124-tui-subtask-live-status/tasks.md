# tasks — TUI 子任务运行态与详情（change 0124 / phase-29 change D：E52）

## 1. 规格（先行）
- [x] 1.1 `specs/ui/spec.md`：ADDED「TUI 子任务运行态与详情」——标题 + 运行状态（运行中/完成/失败/续跑跳过）+
      展开详情（里程碑/验收/判定/结果节选）；里程碑经**友好名**呈现（不暴露内部 id 与原始参数）；
      表外事件不呈现；「进入子会话/焦点切换」明文不在本 Requirement（子 agent 消息流无数据源）
- [x] 1.2 同 delta：**4** 个 Scenario（运行中徽标 / 里程碑展开可见 / 表外不呈现 / 未知 id 静默忽略）
- [x] 1.3 用户裁决沿用：phase-29 §3.3 已收窄「只读详情 + 实时状态」；§4 裁决③「CLI 本期只做只读详情 +
      实时状态」——本 change 即该项的落地，**未新增**裁决点
- [x] 1.4 判据订正 2 条写入 proposal（§6 表 D 行「可验证性：低」不成立 / 「依赖 A 的呈现面」表述偏松）
- [x] 1.5 `openspec validate 0124-tui-subtask-live-status` 通过（"Change ... is valid"）

## 2. 测试（先红）
- [x] 2.1 `tests/test_repl.py` 增 **4** 用例（同文件既有 headless 基建：`app.run_test()` +
      `_timeline_text`；另抽 `_drive_task` 小助手，3 处复用）：
      - `test_subtask_milestones_render_in_collapsible_detail`：里程碑依序落展开区
        （`⏺ Bash` / `⏺ Bash ✓ (1.5s)` / `· 第 1 轮完成`）+ **泄露守门**（`tools.code_run` 与 `print(1)`
        **不在**时间线文本中）
      - `test_subtask_title_shows_running_mark_until_completion`：运行中徽标 `⟳` → 收尾替换为 `✓`（不并存）
      - `test_progress_for_unknown_subtask_is_ignored`：未知 id 静默忽略（`⏺ Read` 仅 1 次、折叠块仍 1 个）
      - `test_non_action_progress_renders_no_line`：表外类型与非字典 `data` **不落任何行**（无空行与占位）
- [x] 2.2 红：实测 `tests/test_repl.py` **3 failed / 18 passed**（`_add_task_widget` 无
      `subtask_progress` 分支 ⇒ 里程碑文本缺失 `assert 0 == 1`；运行态标题实测为 `▸ 子任务 1  查资料`，
      无徽标）—— 第 4 用例为**防御性守门**（红态前后皆绿，故与合法里程碑同用例断）

## 3. 实现
- [x] 3.1 `ui/repl.py` `_add_task_widget`：增 `subtask_progress` 分支（置于 `subtask_started` 与
      `subtask_completed` 之间）→ `_progress_subtask(sid, data)`
- [x] 3.2 `ui/repl.py` 增 `_progress_subtask`：查 `self._open[sid]`（无 ⇒ 静默 return）；工具类里程碑复用
      `format_action_event`（友好名 + 耗时，**不**输出 args/output）；轮次级落 `· 第 N 轮完成/失败`；
      以「读回详情 + 追加」写回（与 `_complete_subtask` 同法，**未**新增累积状态）
- [x] 3.3 `ui/repl.py` `_open_subtask`：标题加**运行中徽标** `⟳`（收尾仍由 `_complete_subtask` 替换为 ✓/✗）
- [x] 3.4 **未触** `format_task_event`（非交互 `task` 入口单行输出逐字不变 —— 决策⑤）

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests` —— All checks passed（先修 2 处 E501）
- [x] 4.2 `.venv/bin/ruff format --check src tests` —— 352 files already formatted
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright` —— **0 errors, 0 warnings, 0 informations**
- [x] 4.4 `.venv/bin/pytest -q` —— **1593 passed**（基线 1589 ⇒ 新增 **4** 例；`tests/test_repl.py` 18 ⇒ 22）
- [x] 4.5 `openspec validate --all` —— 归档前 **31 passed / 0 failed**；归档后 **30 passed / 0 failed**
- [x] 4.6 端到端（离线，不触网）：真 `TaskScheduler`（打桩拆解器 + 打桩子 Agent loop，产出
      `action_started` / `action_completed` / `step_completed` / `reply_delta` / `loop_finished`）经
      `UIAPILayer.run_task` 驱动 headless TUI ⇒ 8 项断言全绿：里程碑三行可见、验收可见、收尾标题
      `▸ 子任务 s1  ✓ 查资料`、**不含** `tools.code_run` / `print(1)` / 流式原文

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/ui/spec.md`（插在「CLI 友好交互」之后、
      「Web 界面访问」之前 —— 与 CLI 交互条款同组；排版对齐邻块：Scenario 后不留空行）
- [x] 5.2 `shutil.move` 进 `doc/openspec/changes/archive/2026-10-06-0124-tui-subtask-live-status/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：ADR-0117 + 变更追踪行（消费面接线 / 复用动作行口径 / 未知 id 早退 /
      不预生成 pending / 不触非交互 CLI / 判据订正 2 条 / 已知局限 5 条）
- [x] 6.2 `doc/03-interfaces/ui-interface.md`：`task.*` 行（§1.1）补「运行态徽标 + 里程碑」+ 新增
      `subtask_progress` 载荷注（白名单三型 + 不暴露 id/args + 非交互 CLI 不呈现）
- [x] 6.3 `doc/04-testing/test-cases.md`：新 TC 节 **37. TC-TUI-01 ~ 05** + 端到端离线冒烟说明
- [x] 6.4 `coding-plan/phase-29.md`：§3.3 项 1 标 ✅ + §6 表 D 行 ✅（**编辑落盘不提交** —— 含他人未提交
      §0.5 改动）+ `coding-plan/README.md`（**随提交**：余 D → 全闭）
- [x] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [ ] 7.1 单次提交：`feat(ui): TUI 子任务运行态与里程碑详情（change 0124）`
- [ ] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（含 `settings.json`，D4 不动）、
      `coding-plan/phase-3-prompt.md`、`AI-SoftwareEngineer-4.md`、`coding-plan/phase-21-findings.md`、
      `coding-plan/phase-32.md`、`src-tauri/Cargo.lock`、`node_modules/`、`frontend/dist/`
