# Design — 0233 TUI 活动块回显

## D1. 缺省态：收起优先于缩略

既有 change `0169` 把 TUI 思考/工具缺省定为**缩略**（末尾 N 行可见），动机是「一眼看见在干什么」。
产品反馈：缩略仍占时间线、符号噪音大。本 change 把缺省改为**收起**（仅标题行），「在干什么」
改由**标题摘要**承载；缩略态仍可保留为展开后的可选中间态（点正文：缩略 ⇄ 全文），或展开即全文。

**决议**：缺省 = **收起**；点标题 → 展开为**全文**（不再强制先经缩略）；若正文极长，展开后仍可用
「仅显示末尾 N 行 + 点击看全文」作为展开态内部优化，但不作为缺省。

## D2. 标题语法（无 ⏺ / ▸）

| tool_id / 事件 | 标题形式 | 摘要来源 |
|---|---|---|
| `tools.file_read` | `Read(<path>)` | args.path |
| `tools.file_write` | `Write(<path>)` | args.path |
| `tools.file_patch` | `Edit(<path>)` | args.path |
| `tools.file_delete`（若存在） | `Delete(<path>)` | args.path |
| `tools.code_run` | `Bash(<script 首行摘要>)` | args.script 首行，≤60 字 |
| `tools.delegate` | `SubAgent(<task>)` | args.task（或等价键），≤60 字 |
| 编排 `plan_ready` / 规划呈现 | `Planner(<goal 或波次摘要>)` | task/plan 事件载荷 |
| `loop.reasoning` | `Thinking` / 进行中 `Thinking…` | **不**把思考原文写入标题（防闪烁） |

- 取不到摘要 ⇒ 标题只留友好名 / `Bash()` / `SubAgent()` / `Planner()`（空括号合法，不落假路径）。
- **SHALL NOT** 在标题使用 `⏺`、`▸`、`└` 作为主标识；完成态用短后缀 `· 1.2s` / `· failed`（可选着色）。
- 正文类参数（content 等）永不进标题（承 `0169`）。

## D3. ActivityBlock 组件

在 `repl.py` 内将现 `_StepBlock` 演进为活动块语义（可同名重构或新类）：

- `collapsed=True` 创建（Thinking / Tool / SubAgent / Planner 一律）。
- 正文 `classes` 灰显（`$text-muted`）；`width: 1fr` + 软折行。
- `append_body` / `set_body` 保持 append-only，避免 O(n²) 全量重拼。
- 标题 `refresh_title()` 可合帧（80–120ms），收起态只改标题不碰正文 DOM。

## D4. Thinking 按 ReAct 步归并

现状：`loop.reasoning` 载荷仅 `{text}`，ReplApp 用单字段 `_reasoning` **整轮一个块**。

目标：同一步（同一 `round`）增量归并；新步进新块。

- loop 外发：`yield LoopEvent("loop.reasoning", {"text": ..., "round": ctx.rounds})`
  （或映射层在 `api.py` 注入当前 round）。
- UI：`dict[int, ActivityBlock]`；无 `round` 时降级挂到「当前未完成 action 的 pending 步」或
  最后一个打开的工具步之前新建 Thinking —— **不丢增量**。

开启 `llm.show_thinking` 时：若该步产生过 thinking 事件，时间线顺序为
**Thinking（收起）→ Tool/SubAgent（收起）**；无 thinking 则只有工具块。

## D5. 动态标题与 spinner

- 有任一 `phase=running` 活动块时，优先靠标题表达进度；`#spinner` 可隐藏或仅作无块兜底。
- Bash 进行中：收起标题结构性摘要可合帧更新（单行、有界）。
- Thinking：收起标题固定为 `Thinking` / 进行中 `Thinking…`，**不**刷思考原文；步结束或下一工具开始时落回 `Thinking`。

## D6. 规格边界

- Web/APP：本 change **不改**其缺省收起与 DOM；仅 TUI 标题/缺省态。
- 子任务折叠块 / `/focus`：主时间线活动块规则优先；子任务内里程碑复用同一标题函数，
  不另造符号系。
- `tools.file_delete`：**不**在本 change 实现工具；仅规格与映射表预留 `Delete(...)`。

## D7. 回合级 Task 壳 — **已撤回**

产品实测：外层 `Task(...)` 多一层点击、不友好。决议改回扁平时间线：

```
❯ <用户输入>
Thinking…                     ← 直接回显（缺省收起）
Read(path) / Bash(…)          ← 工具块按现口径
<主回复 Markdown>             ← 正文正常流式/终态显示
Thinking…                     ← 若后续仍有思考，继续同形态
```

不再建外层 Task 壳；活动块与主回复均直接挂 `#timeline`。

## 局限

- 极快多步时合帧可能合并多次标题刷新 ⇒ 可接受（与 delta 合帧同哲学）。
- Planner 若无独立 tool_id，仅绑定编排事件呈现，不虚构 tool 调用。
