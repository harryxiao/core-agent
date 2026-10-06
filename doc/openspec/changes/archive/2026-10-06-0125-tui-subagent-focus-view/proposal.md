# 提案 — TUI 子 Agent 焦点视图（change 0125 / phase-33 切片 B：E61）

## 背景

`coding-plan/phase-33.md` 立账的 **E61**（用户原始需求①「**进入子 agent 查看状态，查看完成也可以
选择回到主 Agent**」）。phase-29 四 change（`0121`~`0124`）已交付「**只读详情**」（Web `TaskPanel`
右栏任务区 = `0122`；TUI 主时间线内联折叠块 + 里程碑 = `0124`），但「**主/子来回切换**」被明文列为
non-goal（`doc/openspec/changes/archive/2026-10-06-0124-.../proposal.md:48-49`）。

2026-10-06 两条裁决（`coding-plan/phase-33.md` §1 / §3）：

- **E61 形态 = 焦点视图（presentation-only）** —— 复用既有 `subtask_progress` 事件链，**零数据源改动**、
  不触 change `0115`「转录只注入主 loop」边界（phase-29 §7 红线②）。
- **E61 交互范围 = CLI 内嵌面板 + main/subagent 来回切换**（选子 agent 显示子 agent 框、选 main 显示
  main 框）；**Web 沿用 phase-29 已落地的 `TaskPanel`（零改动）**。
- **切换方式 = 命令 + F2**：`/focus <sid>` 聚焦、`/main` 或 `F2` 返回主视图；**任务运行中亦可用**。

| # | 一手事实（2026-10-06 复核，行号已核实） | 后果 |
|---|---|---|
| 1 | `repl.py:319-326` `compose()` = `Vertical(id="timeline")` + `Static(id="spinner")` + `Vertical(id="footer")` | 只有**单一**内容区（时间线）⇒ 无「另一视图」可切换 |
| 2 | `repl.py:311` `self._open: dict[str, tuple[Collapsible, Static, str]]`；`:599-628` `_open_subtask` / `_progress_subtask` | 子任务**标题/状态/详情**均已在**主时间线的折叠块**内 ⇒ 焦点视图的呈现物**已存在**，缺的是「单独看它」的通道 |
| 3 | `repl.py:356-360` `_add` 与 `:453/:466` `_touch_tail` / `_freeze_tail` **无条件 `query_one("#timeline")`** | 时间线**只能 `display` 切换，绝不能 unmount**（否则热更新路径崩溃）⇒ 实现形态硬约束 |
| 4 | `repl.py:500-502` 忙态拒绝；`:481-517` `on_input_submitted` 顺序（审批 → 忙态 → echo → `/task` → `_run_turn`） | 焦点命令须在**忙态拒绝之前**拦截（裁决：运行中可用），且须在审批分支**之后** |
| 5 | `repl.py:481-517` + `:393-394` `_ask_approval`、`:542-545` `task_started` 分支 | 审批提示 / 新计划头**写进时间线** ⇒ 若此时时间线被隐藏则**视觉死锁**（提示不可见）⇒ 两处须强制回主视图 |
| 6 | `frontend/src/views/TaskPanel.svelte`（change `0122`）已逐子任务呈现标题 + 状态 + `<details>` 可展开详情 | **Web 半已闭** ⇒ 本 change **零 Web 改动**（有意不对称，见 ADR） |
| 7 | `tests/test_repl.py:155-167` `_timeline_text(app)` + `:170-180` `_TaskOrchestrator` + 门控式 headless 用例（`test_subtask_title_shows_running_mark_until_completion`） | headless 基建可**直接**验证焦点视图（`#panel` / `#timeline` 的 `.display`、面板文本、忙态绕过） |

**契约面现状（能力缺口，非缺陷）**：`ui` spec 既有「TUI 子任务运行态与详情」（change `0124`）明确
写明「**进入子 agent 会话 / 主-子焦点切换** SHALL NOT **在本 Requirement 内**」—— 该 scope 注**逐字
保留**（本条是**另立**的后续需求）。按本仓 SDD 惯例 **规格先行**（**非** `skip_specs`；新增能力，
先例 change `0028` / `0124`）。

## 变更目标

1. **`ui/spec.md` ADDED「TUI 子 Agent 焦点视图」**：`/focus <sid>` / `/main` / `F2` 三入口；焦点视图
   呈现标题 + 运行状态 + 详情（验收 / 里程碑 / 判定 / 结果节选）；随里程碑与收尾**实时刷新**；返回后
   主时间线**逐字不变**；未知标识不切换（提示）；运行中可用（不受忙态拒绝）；友好名不泄露 id·参数；
   `task_started` 与审批挂起回主视图；+ **6** 个 Scenario。
2. 实现（全部在 `src/core/ui/repl.py` 的 `build_app` 内）：新增 `#panel` 视图（CSS + `compose()` +
   `on_mount` 初始隐藏）；新状态 `_focus_sid` / `_focus_box` / `_focus_detail`；`_set_focus` /
   `_render_panel` / `_handle_focus_command` / `action_focus_main`；`BINDINGS` += `F2`；`_HINTS_*` 文案；
   输入拦截（忙态**前**拦命令、忙态**后**「非焦点输入 ⇒ 回主视图」）；里程碑/收尾的**身份守卫**刷新。

## 判据订正（相对 phase-33 §1 原稿，2 条）

**(a) 原 (b)「只读详情 + 状态（复用 `subtask_progress` 载荷）」与已落地件逐字同义。** 该表述与 `0124`
（TUI 里程碑渲染进展开区）+ `0122`（Web 任务区）**逐字同义** ⇒ 照做即 **0 增量**。**重定义后**的真
增量是 **「焦点」本身**：**单子任务过滤视图 + 进入 / 返回导航**（`0124` 只在**主时间线的折叠块**内联
呈现，无「进入某子任务」的概念）。本 change 即该重定义版的落地。

**(b) 焦点必须绑定 widget 身份，不能只比 sid。** `self._open` **跨任务从不清空**（`:311` 定义、
`:611-645` 只增改），而子任务标识（`"1"` / `"s1"`）**逐任务重复** ⇒ 若以 sid 判「当前焦点是否即该
`detail`」，会把**上一任务**同 sid 的陈旧条目误认作当前焦点。故存 `_focus_box` / `_focus_detail`
**对象引用**并以 `is` 比对。

## Non-goals

- **不接子 Agent 消息流**：§7 红线②的裁决前提未变（转录只注入主 loop，change `0115`）。焦点视图的
  「详情」**仅**指既有事件载荷内可见字段。
- **不改 Web**：按裁决沿用 phase-29 已落地的 `TaskPanel`（有意不对称；见 ADR 已知局限）。
- **不改事件面**：不新增事件类型、不改载荷形状；**不**触碰 `scheduler._emit_progress` 白名单。
- **不触** `format_task_event` / `format_action_event` / `_format_event` / `repl_loop`：非交互
  `core-agent task` 输出**逐字不变**。
- **不做「延迟聚焦」**：`/focus` 若早于 `subtask_started` 到达 ⇒ 按未知拒绝（无半开态）。
- **不做独立全屏视图**（裁决取「内嵌面板」）；**不**做「聚焦时隐藏 `#spinner`」（两视图均保留活性反馈）。
- **不动** phase-29 其余 change 已闭的面（A/B/C/D）与 `tools.delegate` 阻塞 await 语义。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 时间线 unmount ⇒ `_add` / `_touch_tail` / `_freeze_tail` 崩溃（事实 3） | 焦点切换**只**改 `display`（`:358/:453/:466` 的 `query_one("#timeline")` 恒可解析）；**绝不** `remove()` |
| 面板正文泄露内部 `tool_id` / 原始参数 | 面板正文读 `str(detail.render())`——即时间线折叠块**同一**已渲染文本（`format_action_event` 的友好名口径）；用例断 `tools.code_run` / 参数原文**不在**面板文本中 |
| 陈旧同 sid 条目被误判为焦点（判据订正 b） | 焦点绑定 `_focus_box` / `_focus_detail` **对象身份**（`is` 比对），非 sid 字符串 |
| 焦点命令被忙态拒绝（裁决：运行中可用） | 拦截点置于忙态检查**之前**（`:499`↔`:500`）；用例断言忙态中 `F2` 有效且 `_turn_busy` 仍真 |
| 审批提示 / 新计划头落进被隐藏的时间线 ⇒ 视觉死锁（事实 5） | `_ask_approval`（`:393-394`）与 `task_started` 分支（`:542-545`）**强制** `_set_focus("")` |
| 初始隐藏态被 Textual `display` setter 覆盖（其源码有 TODO：忘记原值） | `on_mount` 中**命令式**置 `False`（与既有 `#spinner` 隐藏同法），**不用** CSS `display:none` |
| markup 不对称导致渲染异常 | 面板标题沿用**已转义**串（`markup=True`，对齐 `CollapsibleTitle`）；面板正文为**原始**输出 ⇒ `markup=False` |
| 既有 22 例 `test_repl.py` 回归 | 新增 `#panel` **不**改任何 `#timeline` 路径；`:628`/`:637-638`/`:645` 的改动**仅**在身份命中时多调一次 `_render_panel()`（未聚焦 ⇒ 零行为差） |

## 兼容性

- 未聚焦时全部新增路径**早退**（`_set_focus("")` 在已为主视图时零 widget 抖动；身份守卫未命中 ⇒ 什么都不做）⇒ 既有行为**逐字不变**。
- 非交互 CLI（`core-agent task`）、Web、编排层、事件面 **零改动**。
