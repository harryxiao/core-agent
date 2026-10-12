# Proposal 0233: TUI 活动块回显（Thinking 默认收起 + 友好标题）

## Why

TUI（[`src/core/ui/repl.py`](../../../src/core/ui/repl.py)）当前步骤块以 `⏺` / `▸` / `└` 为视觉主标识，
工具标题在友好名外仍带符号；Thinking 按既有规格缺省为**缩略态（正文可见）**，长任务时时间线被
思考与工具输出淹没，可读性差。产品期望对齐 Claude 式活动行：

- **Thinking 缺省收起**，点标题展开全文；
- 工具标题用 **`Read` / `Write` / `Edit` / `Delete` / `Bash(...)` / `SubAgent(...)` / `Planner(...)`**，
  **不用** `⏺` 等装饰符号；
- 工具 / 脚本正文**灰显、默认收起**，展开后全文 + 自动折行；
- 刷得快时收起态**标题单行动态刷新**（摘要跟随最新增量）。

对应需求：`CORE-UI-R3`（CLI 声明式响应式终端交互，复刻 Claude Code 式体验）。

## What Changes

1. **MODIFIED** `ui`「思考过程回显（Think）」：TUI 缺省形态由**缩略**改为**收起**（正文隐藏，仅标题可见）；
   Web / APP 缺省收起**逐字不变**。
2. **MODIFIED** `ui`「TUI 步骤块（缩略 / 全文 / 收起）」：
   - 缺省态改为**收起**；
   - 标题语法去掉 `⏺`，改用友好名表 + 可选括号摘要；
   - 明确 `Bash(...)` / `SubAgent(...)` / `Planner(...)` 与文件工具 `Read`/`Write`/`Edit`/`Delete`；
   - 收起态允许标题合帧动态刷新；展开后正文灰显 + 折行。
3. **ADDED**（可选同条扩写）：按 ReAct **步**归并 Thinking（同一步增量同块；下一步新块），
   依赖 `loop.reasoning` 载荷带 `round`（或等价步标识）——若现状仅有 `text`，本 change 含映射层补字段。
4. ~~**ADDED**「TUI 回合活动组（Task 壳）」~~ → **REMOVED / 撤回**：扁平时间线直接回显
   `Thinking…` 与工具块；主回复正常显示（不再套外层 Task）。

明确不做：Web/APP 视觉改版；新增 `tools.file_delete` 工具实现（仅预留友好名 `Delete`）；
改默认模型 / 预算；打包。

## Impact

- **影响规格**：`doc/openspec/specs/ui/spec.md`（思考回显 + TUI 步骤块）。
- **影响代码**：`src/core/ui/repl.py`（标题 / Collapsible 缺省 / ActivityBlock）；必要时
  `src/core/ui/api.py` / `src/core/loop/default.py`（`loop.reasoning` 补 `round`）。
- **兼容性**：开启 `llm.show_thinking` 后 TUI 思考块由「缩略可见」变为「默认收起」——**有意破坏**
  既有 TUI 缺省呈现；未开启思考时事件面零新增。CLI 单行 `format_action_event` 同步去符号。
- **测试**：`tests/test_repl.py` 等 — 标题无 `⏺`、Thinking `collapsed=True`、友好名映射、
  SubAgent/Bash 括号摘要、折行 / 收起展开手势、Task 壳归组与嵌套手势。

## Non-goals

- 不改 Web/APP 思考块缺省（已是收起）。
- 不实现文件系统 Delete 工具本体。
- 不把真实网关 key / 完整工具参数打进标题。
- 不做压力测试级刷屏性能专项（合帧节拍沿用既有 tail timer 量级即可）。

## Risks

- 缺省收起后「Agent 正在干什么」在未展开时只靠**标题摘要**可见 —— 须保证动态标题合帧与
  Bash/SubAgent 摘要质量，避免空标题。
- `loop.reasoning` 补 `round` 属小协议扩展，须保证未带 round 时仍可降级为「当前打开步」归并，
  不丢思考、不拆碎块。
