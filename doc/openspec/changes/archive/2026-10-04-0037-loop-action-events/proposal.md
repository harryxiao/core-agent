# Change: loop 工具动作事件——action_started / action_completed

## Why

UI 对标 Claude CLI 的「⏺ Bash(cmd) 动作行」呈现，需要 loop 层在**工具执行前后**
外发结构化动作事件。当前 astream 只产出五类事件（loop_started / step_completed /
reply_delta / loop_finished / loop_failed），工具调用被折叠进 step_completed 的
round 计数里：UI 无从得知"调了什么工具、参数是什么、耗时多久、结果节选"，
只能显示笼统的回合推进。编排子任务的折叠块已携带验收/判定/结果节选（上一变更），
普通会话内的工具动作成为进度呈现的最后一块空白。

事件面是规格钉死的（loop/spec.md「异步流式执行」Requirement 枚举五类），
按 SDD 先改规格再改代码。

## What Changes

- **工具动作事件**（loop，MODIFIED「异步流式执行」）：astream 事件面五类 → 七类，
  新增 `action_started`（round, tool_id, args 节选）与 `action_completed`
  （round, tool_id, ok, duration_ms, output 节选）；仅非终止动作（tool_id 非空）
  产出；既有五类事件的节奏与语义不变。
- **UI 动作行**（ui，无规格变更——「折叠块展示」场景已覆盖）：TUI 以
  `⏺ tool(args 摘要)` 单行彩点行呈现，完成后标题落 ✓/✗ + 耗时，点击展开
  完整参数与输出节选；CLI 打单行文本。
- **事件映射**（ui-interface，同步）：`_EVENT_MAP` 补
  `action_started → loop.action_started` / `action_completed → loop.action_completed`，
  替换未实现的 `loop.action` 占位行。

## Impact

- **Affected specs**：`loop/spec.md`（1 MODIFIED：「异步流式执行」五类→七类 + 新场景「工具动作事件」）；对应规格 Requirement「异步流式执行」（事件面内聚于该 Requirement，产品需求清单 CORE-LOOP-R1–R4 未单列流式事件，无需变更）
- **Affected docs**：`03-interfaces/loop-interface.md`（事件面七类）、`03-interfaces/ui-interface.md`（§1.1 `loop.action` 占位行 → 两行动作事件）
- **Affected code**：`src/core/loop/default.py`（astream 工具执行前后包夹发事件）；`src/core/ui/api.py`（`_EVENT_MAP` 两行）；`src/core/ui/repl.py`（`format_action_event` + TUI 动作行折叠块）；`src/core/entry.py`（CLI run 动作行）
- **Dependencies**：无新依赖；事件载荷节选 400 字符对齐 orchestration `_MAX_EVENT_EXCERPT` 惯例
