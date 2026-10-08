# 0169 · TUI 步骤块：缺省展开 + 缩略末尾 N 行 + 点击展开全文

> 触发：用户 2026-10-08 实测 TUI 后提出 ——
> 「core-agent TUI 输入会话后默认只有『思考中...』，实时的 Think + 扩展部分内容（缩略部分内容——
> 点击可展开/可回缩），每一个步骤无论 Bash/Write/gate_run/code_run 等都执行信息的灰色显示，
> 点击箭头只有看到结果，而且也不自动换行；要求 Thinking 推理过程实时，每一个步骤读/写/执行/门禁/等
> 都有步骤标题（一个任务中间的小步骤），有 L 形状下拖的原始执行信息（max 可以显示 8-10 行，
> 超过缩略，可以点击展开），这样至少看上去知道 Agent 在干活」。

## Why（四点根因，已逐行核实）

| # | 现象 | 根因 |
|---|---|---|
| ① | 看不到实时思考，只有转轮「✻ 思考中…」 | 事件流是**通**的（`show_thinking: true`），但 `repl.py:1003` 建块 `collapsed=True` ⇒ **收端缺省收起** |
| ② | 工具动作「点击箭头只有结果」，看不出在干什么 | `repl.py:973` 同样 `collapsed=True`，且标题**不带目标**（只有友好名） |
| ③ | 长行**不自动换行**（被裁） | `repl.py:401` 的 `.hint { width: auto }` 用在折叠区正文 `Static` 上：Textual 下 `width: auto` 的 `Static` 宽度 = **最长行宽**，超出部分被祖先 `overflow-x: hidden` **裁掉而非折行** |
| ④ | 思考「不实时」（长流越跑越卡） | `repl.py:1008` 每来一个 delta 就 `str(detail.render()) + text` **全文重拼 + 重解析**（O(n²)） |

规格侧另有一处**硬约束冲突**：`ui`「思考过程回显（Think）」把「**缺省收起**」写成了三端同一要求 ⇒
TUI 改缺省形态**必须**先改规格。

## What Changes

**只动呈现层单文件 `src/core/ui/repl.py`**（CLI / 事件面 / 转录 / 记忆 / 日志零改动）。

1. **新增 `_StepBlock(Collapsible)`**（`build_app` 内，紧邻 `_PaletteList`），统一承载**思考块**与
   **工具动作块**；三态 + **append-only 行缓冲**（消 O(n²)）：

   | 态 | 实现 | 正文 |
   |---|---|---|
   | 缩略（**缺省**） | `collapsed=False` + 末尾 `_STEP_TAIL_LINES`(=8) 行 | 首行 `└ ` 角标 + 末行 `⋯ 还有 M 行 · 点击展开全文` |
   | 全文 | `collapsed=False` + 全量 | 末行 `⋯ 点击正文收起` |
   | 收起 | `collapsed=True`（Textual 原生） | 仅标题 |

   点**正文**切 缩略 ⇄ 全文；点**标题**切 收起 ⇄ 展开（Textual 原生）。

2. **标题目标摘要**：新增模块级纯函数 `_tool_target(tool_id, args)` —— **白名单**结构性字段
   （`file_read`/`file_write`/`file_patch`→`path`、`web_fetch`→`url`、`code_run`→`script`、
   `gate_run`→`gate`、`context_read`→`pointer`），**单行**（取首个 `\n` 前）+ **有界长度**（超长 `…`）；
   `args` 非映射（含事件面「超长节选」的 str 形态）或取不到 ⇒ `""`（标题只留友好名）。
   **正文类参数**（`content` / `old_content` / `new_content`）与内部 `tool_id` **永不出现**。

3. **两处调用点**：`_add_action_widget`（标题带目标；`completed` 落 `✓ (耗时)` / `✗` 并 `set_text(output)`，
   去掉 `输出：` 前缀）+ `_add_reasoning_widget`（增量走 `feed()` 实时刷新）。

4. **CSS**：新增 `.step-body { color: $text-muted; width: 1fr; }`（**确定宽度 ⇒ 折行**，修「不自动换行」）
   与 `.step-more { color: $text-disabled; width: 1fr; }`。**不复用 `.hint`**（同优先级两条规则会打架）。

5. **规格 `ui`**：「思考过程回显（Think）」**MODIFIED**（缺省形态分端：TUI 缩略 / Web + APP 逐字保留
   收起）+ 新增 Requirement「TUI 步骤块（缩略 / 全文 / 收起）」**ADDED**（6 Scenario）。

## Non-goals

- **不改** CLI（`entry.py`）、Web / APP（SPA）呈现；**不改**事件面与 `loop` / `observability` 规格。
- **不改** `format_action_event`（CLI 与子任务里程碑共用，6 处断言依赖其逐字输出）。
- **不改**子任务折叠块（`▸ 子任务 N`）与子 Agent 焦点视图（用户裁决：**本轮不改，另立 change**）。
- **不改** `_flush_tail` / `_touch_tail` / `_show_delta`（回复流式合帧节流**专供回复**）。
- **不改** `CollapsibleTitle` 自带 `▶/▼` 与标题手写 `⏺/▸` 的**双字形**既有瑕疵（不属本次诉求）。
- **不引三方库**。

## Risks

- **`file_write` / `file_patch` 标题无目标**：其正文参数使事件面 `args` 超过既有 **≤400 字符**上界
  （`_args_excerpt`）而退化为**字符串** ⇒ TUI 不解析 repr，取不到 `path`（**路径仍在 `└` 输出摘录**里）。
  根治需改 `loop` 的节选口径（牵动 `observability` 契约）⇒ **另立 change**，本 change 记入台账 E106。
- **`code_run` 目标取 `script` 首行** ⇒ 操作者自填内联凭据会与终端显示命令**同等**暴露（步骤块不落盘）。
- **双字形**：`▶ ⏺ Read` —— 既有形态，本 change 不裁决（只**不新增**字形）。
