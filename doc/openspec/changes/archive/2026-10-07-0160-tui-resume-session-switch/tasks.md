# 0160 · 任务清单（TUI 会话切换 `/resume`）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`ui` **ADDED** Requirement「TUI 会话切换（`/resume`）」（4 Scenario）。
> 状态：**已闭**（四门禁全绿；`openspec validate --all` 归档后 30/0）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/ui/spec.md`（delta，ADDED）：会话切换 + 4 Scenario；`openspec validate` 单条 ⇒ valid
- [x] 1.2 ADR-0152（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 纯函数：`/resume` 二级候选取自会话面、按显示行/标识前缀收窄、不吃子任务面
- [x] 2.2 TUI：`/resume <B>` 切换 → 时间线铺入 B 转录（agent 回复成 Markdown / 围栏成代码块）
- [x] 2.3 TUI：切换后**后续轮次落 B**（`RecordingLoop.sessions`）
- [x] 2.4 TUI：未登记会话 fail-closed（时间线逐字不变 + 后续轮次仍在 A）
- [x] 2.5 TUI：`/resume` 无参数 ⇒ 只提示用法、不切换
- [x] 2.6 TUI：忙碌中拒绝切换
- [x] 2.7 TUI：切换复位呈现态（`_open` 清空、焦点视图回主视图）
- [x] 2.8 **零回归**：既有浮层/命令用例（含 `test_ghost_completion_*`、`/focus`/`/task`/审批）全绿
- [x] 2.9 **守护更新**：真源守护加入 `/resume <已登记标识>`
- [x] 2.10 红态确认：以上新用例在实现前**必红**

## 3. 实现

- [x] 3.1 `_COMMANDS` 增 `/resume`（`arg_source="session"`）
- [x] 3.2 `_palette_options` 增 `sessions` 参数（二级候选按 `arg_source` 分派来源）
- [x] 3.3 `_candidates` 按真源 `arg_source` 决定是否取会话面（按键路径不空读）+ `_session_candidates`
- [x] 3.4 `session_id` 闭包变量 → 实例字段 `self._session_id`（两处按轮读取改读实例）
- [x] 3.5 `on_mount` 历史循环提成 `_replay_history`（启动续聊与切换**同源**）
- [x] 3.6 `_handle_resume_command` / `_switch_session`（先验证后落地）/ `_reset_turn_state`
- [x] 3.7 `on_input_submitted` 插入 `/resume` 分支（**忙态检查之后**、回主视图与回显**之前**）

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/ui-interface.md` §2：补会话切换口径
- [x] 4.2 `doc/04-testing/test-cases.md`：新增 `## 75.`（TC-RESUME）
- [x] 4.3 `coding-plan/known-risk.md` §3：加 ADR-0152 局限行（E99 行已预告本 change）

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted（361 files）
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 全绿（**1895 passed**，基线 1888 ⇒ +7）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 **31/0** ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（ui）⇒ 移至 `archive/2026-10-07-0160-tui-resume-session-switch/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md` §3；ADR-0152 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`feat(ui): TUI /resume 会话切换，运行中切换并还原既有会话（change 0160）`
