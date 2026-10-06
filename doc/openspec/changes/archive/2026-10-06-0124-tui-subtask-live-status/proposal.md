# 提案 — TUI 子任务运行态与详情（change 0124 / phase-29 change D：E52）

## 背景

`coding-plan/phase-29.md` 立账的编排缺口 **E52**（用户需求②「串行/并行都需 CLI + web/app **动态显示
子 agent 主题 + 运行状态**」的 CLI 半）。phase-29 §6 已裁决把该 Phase 拆为 A/B/C/D 四个 change，本
change 是 **D**（最后一个；A 事件回流 = `0121`，B HTTP 面 + Web 任务区 = `0122`，C 策略层 = `0123`）。

§3.3 已**收窄**本 change 的范围：**只做「只读详情 + 实时状态」**；「进入子 agent 会话 / 回到主 Agent」
（焦点状态机 + 输入路由语义）**不在本 change**（§7 红线②：子 agent 消息流**无数据源**）。

| # | 一手事实（2026-10-06 复核，行号已核实） | 后果 |
|---|---|---|
| 1 | `repl.py:535-567` `_add_task_widget` 分支仅 `task_started` / `plan_ready` / `wave_started` / `subtask_started` / `subtask_completed` / `task_failed` / `task_finished`——**无 `subtask_progress` 分支** | 里程碑事件到达即被**静默丢弃**（无 `else` 兜底，无痕迹）⇒ E52 根因 |
| 2 | `scheduler.py:480-495` `_emit_progress` 按 `_PROGRESS_FIELDS` 白名单转译（`action_started` / `action_completed` / `step_completed`），载荷 `{task_id, subtask_id, event, data, ts}` | 数据面**已存在且已白名单化**（change `0121`）—— 缺的只是**消费面** |
| 3 | `api.py:188-195` `run_task` 逐事件加 `task.` 前缀透传 | 事件**确实到达** `repl.py`（`event.type = "task.subtask_progress"`）⇒ 不是「没送到」，是「送到了没人管」 |
| 4 | `frontend/src/views/TaskPanel.svelte:61-65` 已消费 `task.subtask_progress`（`milestone(ev)`） | **Web 半已闭**（change `0122`）⇒ 本 change 后三面（Web/TUI/CLI）呈现口径一致 |
| 5 | `repl.py:596-606` `_open_subtask` 标题 `▸ 子任务 {sid}  {goal}`，收尾才落 `✓/✗`（`:608-623`） | 运行中**无状态徽标**（「在跑」只能靠「还没出现 ✓/✗」推断）⇒ 需求②「运行状态」的 CLI 半缺口 |
| 6 | `tests/test_repl.py:298-347` `test_task_subtask_collapsible_lifecycle` 经 `app.run_test()` headless 驱动 | **headless Textual 基建已存在** ⇒ §6 表 D 行「可验证性：**低**（Textual 无测试基建）」**判据订正**（见下） |

**契约面现状（能力缺口，非缺陷）**：`ui` spec 的「CLI 友好交互」只规定折叠块**存在**（`:89-92`），
「任务编排的 HTTP 面与 Web 任务区」（change `0122`）只覆盖 **Web 侧**的「逐子任务呈现标题与状态
（待执行/运行中/完成/失败）+ 展开可见详情（里程碑/验收/失败理由）」。**TUI 侧无对应条款** ⇒ 按本仓
SDD 惯例 **规格先行**（**非** `skip_specs`；新增能力，先例 change `0028`）。

## 变更目标

1. **`ui/spec.md` ADDED「TUI 子任务运行态与详情」**：`/task` 逐子任务呈现标题 + 运行状态（运行中 /
   完成 / 失败 / 续跑跳过）+ 展开可见详情（里程碑 / 验收 / 判定 / 结果节选）；里程碑经**友好名**呈现
   （不暴露内部 `tool_id` 与原始参数）；表外事件不呈现；+ 4 个 Scenario。
2. 实现：`repl.py` 增 `subtask_progress` 分支 → 追加里程碑行进子任务展开区；`_open_subtask` 标题加
   **运行中徽标**（`⟳`），收尾由既有 `_complete_subtask` 替换为 `✓/✗`。

## 判据订正（相对 phase-29 §6 表 D 行，2 条）

**(a)「可验证性：低（Textual 无测试基建）」不成立。** 事实 6：本仓**已有** headless Textual 用例
（`app.run_test()` + `pilot.press` 驱动输入、`_timeline_text(app)` 取时间线全量文本、`Collapsible.Contents.display`
断折叠态）——`test_task_subtask_collapsible_lifecycle` / `test_tui_action_widget_lifecycle` /
`test_task_command_busy_rejects_concurrent` 即此基建的现成用例。本 change 的验收可**全部**由同类用例
钉死（里程碑文本、徽标、表外不呈现、未知 id 忽略）⇒ 可验证性实为**高**。

**(b)「依赖 A 的呈现面」表述偏松。** A（change `0121`）交付的是**数据面**（事件 + 白名单载荷），
本 change 交付**消费面**；二者不同层。且 B（change `0122`）**已**在 Web 侧完成同一消费面的等价物
（事实 4）⇒ 本 change 的判据（呈现哪些字段、哪些不呈现）**可直接对照 Web 实现**，不需新造口径。

## Non-goals

- **不做「进入子 agent 会话 / 主-子焦点切换」**：§3.3 明确登记后续、§7 红线②给出理由（子 agent 消息流
  **无数据源**——转录只注入主 loop，change `0115`）。本 change 的「详情」**仅**指既有事件载荷内可见字段。
- **不预生成「待执行」条目**：TUI 时间线是**对话流**（按事件发生次序追加），不是清单式面板；Web 任务区
  是面板故在 `plan_ready` 即铺出全部子任务（含 pending）。此为**两面的有意差异**（见 ADR-0117 已知局限）。
- **不改事件面**：不新增事件类型、不改载荷形状（change `0121` / `0122` 的消费面不回归）；**不**触碰
  `scheduler._emit_progress` 的白名单（表外类型的静默丢弃是**有意**的既有口径）。
- **不改** `format_task_event`（`entry.py:1534` 非交互 `task` 入口共用）：本 change 只改 **TUI** 呈现，
  非交互 CLI `task` 的单行输出**逐字不变**（不扩大其输出粒度）。
- **不给子 loop 接转录**（§7 红线②的裁决前提未变）。
- **不动** phase-29 其余 change 已闭的面（A/B/C）与 `tools.delegate` 阻塞 await 语义（§5）。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 里程碑行**泄露**内部 `tool_id` 与原始参数 | 复用既有 `format_action_event`（其 `_TOOL_NAMES` 映射 + 只取 `tool_id/ok/duration_ms`，**从不**输出 `args` / `output`）⇒ 与主 loop 动作行**同一口径**；用例断 `tools.code_run` / 参数原文**不在**时间线文本中 |
| 折叠块被 `subtask_progress` **重复创建** | 里程碑**只**追加到 `self._open[sid]` 既有条目；无条目 ⇒ 静默 return（对齐 `_complete_subtask` 既有的 `entry is None` 早退口径） |
| 详情文本随里程碑**无限增长** | 里程碑由编排层白名单**有界**（每轮至多 3 类）；与既有 `subtask_completed` 的「读回详情再追加」同法（非新增累积状态） |
| 既有用例回归 | `_open_subtask` 标题仅在 `sid` 与 `goal` 间**新增** `⟳`；既有断言（`test_task_subtask_collapsible_lifecycle` 断**完成态**标题 `▸ 子任务 1  ✓ 查资料`）**不在运行态窗口内** ⇒ 不改动即守门 |

## 兼容性

- 新增分支**只**消费既有事件 ⇒ 未产生 `subtask_progress` 的编排器（测试桩、无里程碑的执行）**逐字不变**。
- 非交互 CLI（`core-agent task`）输出**零改动**（事实：本 change 不触 `format_task_event`）。
- 事件面 / 编排层 / Web / `tools.delegate` **零改动**。
