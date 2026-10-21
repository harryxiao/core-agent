# UI 活动呈现方案（TUI / Web 一套）

> 真源定位：本文件是 **TUI + Web（含 Desktop SPA）** 共用的活动时间线与相位口径。
> 行为约束以 `openspec/specs/ui` 与 change `0233` 为准；本文把「共享模型 → 分端材质」写清，避免两端各写一稿分叉。
> Desktop 复用 Web SPA 产物 ⇒ 与 Web **同一套**，不单列第三套 UI 语义。

## 1. 设计原则

1. **事件驱动，不另造状态机**：相位与块种类只由既有 SSE / loop 事件派生（`loop.reasoning` / `loop.action_*` / `loop.delta` / `loop.result` / 审批与 `task.*`），SHALL NOT 为 UI 新建第二事件面。
2. **共享语义，分端材质**：标题语法、归并规则、缺省收起、闲置时机两端一致；控件实现可不同（TUI=`Collapsible`/`_StepBlock`，Web=`details` 或等价折叠）。
3. **扁平时间线**：无外层 Task 壳；`Thinking` → 工具块 → 主回复 直接挂时间线。
4. **思考纯呈现**：思考原文只经 `loop.reasoning` 上屏，不进转录 / 记忆 / 日志 / trace。
5. **终态即闲置**：主回复终态（`loop.result`）到达后，状态行立刻离开「思考中」；轮末技能/维护后台化，不得继续占用思考文案。

## 2. 共享时间线模型

```
❯ <用户输入>
Thinking…                 ← 可选；同 round 归并；缺省收起
Read(path) / Bash(…)      ← 工具块；缺省收起；完成带 · 1.2s / · failed
<主回复 Markdown>         ← loop.delta 流式 + loop.result 收口
Thinking…                 ← 若后续步仍有思考，同形态追加
```

| 块种类 | 事件源 | 缺省形态 | 归并键 |
|---|---|---|---|
| Thinking | `loop.reasoning` | **收起**（仅标题） | `round`（同 round 增量同一块；无 round 时降级到当前未完成步） |
| 工具 / Planner / SubAgent | `loop.action_started` / `*_completed` | **收起** | 单次工具调用一块 |
| 主回复 | `loop.delta` → `loop.result` | 正文流式，非折叠块 | 本轮一条流 |
| 未能解析原始产出 | `loop.result.raw_output` 非空 | **收起** | 本轮至多一块 |
| 子任务（编排） | `task.*` | 折叠块（既有） | `subtask_id` |

开启 `llm.show_thinking` 时才产 Thinking 块；关闭时事件面与呈现零思考块（与既有缺省一致）。

## 3. 共享标题语法

两端标题字符串 **逐字同一表**（友好名 + 括号摘要）。折叠/摘要前的**种类图标**两端同源，**SHALL NOT** 再用统一 `▶`/`▼`/`▸` 充当所有块的主标识：

| 来源 | 图标 | 标题 | 摘要 |
|---|---|---|---|
| `loop.reasoning` | `✦` | `Thinking`；进行中 MAY `Thinking…`；落静 MAY `Thinking · 1.2s` | **禁止**把思考原文写入标题 |
| `tools.file_read` | `◇` | `Read(<path>)` | `args.path` |
| `tools.file_write` | `✎` | `Write(<path>)` | `args.path` |
| `tools.file_patch` | `✏` | `Edit(<path>)` | `args.path` |
| `tools.file_delete`（预留） | `⌫` | `Delete(<path>)` | `args.path` |
| `tools.code_run` | `$` | `Bash(<script 首行>)` | 有界摘要；空则 `Bash()` |
| `tools.delegate` | `⊕` | `SubAgent(<task>)` | 有界；空则 `SubAgent()` |
| `tools.web_fetch`（Exploring） | `◎` | `WebFetch(<url>)` | `args.url` |
| 编排规划 | `▤` | `Planner(<摘要>)` | goal / 波次；空则 `Planner()` |
| 子任务 | `◈` | `子任务 <id> …` | — |
| 未能解析原始产出 | `⚠` | `未能解析的模型原始输出` | — |

完成态 MAY 追加短后缀：`· 1.2s` / `· failed`（或 `· ok`）。正文类参数（content 等）永不进标题。
TUI：图标经 Collapsible 的 `collapsed_symbol`/`expanded_symbol`（收起/展开用**同一**种类符）。Web：图标写在 `<summary>` 前缀。

## 4. 共享相位（状态行 / 状态条）

相位是**整轮忙闲**信号，不是每个步骤块的内部状态。语义固定；展示文案可本地化。

| 相位 ID | 触发 | 用户可见文案（中文缺省） | 退出 |
|---|---|---|---|
| `idle` | 无在途轮；或刚收到 `loop.result` | （隐藏状态行） | 用户提交下一轮 |
| `thinking` | 轮已开始，尚无独占的审批/工具长等待 | `思考中… (Ns)` | 见下 |
| `acting` | 可选：工具已 `action_started` 且未完成 | 可与 `thinking` 合并为同一 busy 文案，或以工具标题表达 | `action_completed` |
| `awaiting_approval` | 确认门挂起 | `等待审批…` | y/n 决断 |
| `failed_visible` | 解析失败等带 `raw_output` / 错误条 | 错误提示 + 可选原始产出块 | 用户继续 |

**硬规则**：

- `loop.result`（映射后的终态）到达 ⇒ **立即**进入 `idle`（停 spinner / 清状态条），允许用户输入。
- 轮末 `turn_observer` / `_maintain` 等收尾 **不得**把相位拉回 `thinking`。
- 有活动步骤块时，优先用**块标题**表达「在干什么」；全局状态行只作整轮 busy 兜底。
- 状态行/提示行的**呈现密度**（单行、无边框、与谁同行）归各端材质预算（TUI 见 §5.1 密度预算），
  相位语义本身两端一致、不受密度改版影响（change 0299）。

## 5. 分端材质映射

### 5.1 TUI（Textual REPL）

| 共享概念 | 实现 |
|---|---|
| 时间线 | `#timeline` 追加 widget |
| 步骤块 | `_StepBlock` / `Collapsible`；`collapsed=True` |
| Thinking 标题 | 收起态固定 `Thinking` / `Thinking…`，不刷原文 |
| 全局相位 | `#spinner`（glyph + 文案 + 秒计时）与 `#hints` 同住 `#status` **单行**（无边框）；`loop.result` 时 `_end_turn` |
| 主回复 | Markdown 流式合帧；终态固化 |
| 审批 | 时间线提示 + 输入 y/n；spinner 改 `等待审批` |
| 文件工具块 | 展开体首行 dim 元信息（write `N 字节 · M 行写入`、patch `+N −M · hunk H`、read `N 行`）+ 按后缀 `Syntax` 高亮（patch 用 diff）+ 40 行上界；抽取失败回退纯文本（change 0299） |

**视觉密度预算（change 0299 / ADR-0289，紧凑即唯一形态、无开关）**：

| 预算项 | 值 |
|---|---|
| 底部 chrome（idle / busy） | ≤ 4 / ≤ 5 行（输入框是唯一带边框的常驻件；spinner 与快捷键同行） |
| 展开体 | 零顶空行、左缩进 2 列、正文 ≤ 40 行（超出尾行注明总行数） |
| Markdown | 围栏 N 行内容占 N 行；标题上留 1 行；`---` 1 行；段落间 1 行保留 |
| 启动横幅 | 2 行（无边框） |
| 轮次分隔 | 每轮回复结束后 1 行 dim 虚线 |
| 命令面板 | max-height 6（浮层，保留边框） |

「字体偏大」无应用侧杠杆（终端字体由终端模拟器决定）；配套建议：等宽字体（Cascadia Code /
JetBrains Mono / Maple Mono）、字号 10–12pt、行距 1.0（Windows Terminal 默认 1.2 常致体感偏大）。

不强制：呼吸灯、震动、微型终端模拟器（Textual 成本高、收益低）。工具输出进步骤块正文即可。

### 5.2 Web / Desktop SPA

| 共享概念 | 实现 |
|---|---|
| 时间线 | 会话消息流中的活动列表（与主回复同列或紧邻） |
| 步骤块 | `<details>`（或设计系统等价折叠）；**缺省收起** |
| Thinking | 同标题语法；增量 append 同一节点；不渲染 JSON 载荷当正文 |
| 全局相位 | 输入区上方/旁路状态条；文案与相位表一致 |
| 主回复 | SSE `loop.delta` 流式；`loop.result` 收口（不与 delta 共型） |
| 事件通道 | 既有 SSE；不新建端点 |

Web **允许**增强（不影响 TUI 义务）：进行中图标 pulse、失败时自动展开 `details`、工具块等宽字体预览。增强不得改变标题字符串与缺省收起语义。

### 5.2 主/子 Agent 视图（change 0294 / ADR-0284）

共享模型（两端同源，事件只取 `task.*`）：

```
标签栏 = main + 当前/最近任务的子任务（主题缩写 + ⟳/✓/✗/·）
选择键 = taskId + subtaskId（sid 仅在任务内唯一）
视图   = main（主时间线） | 子任务只读详情（验收 / 里程碑 / 判定 / 有界结果节选）
生命周期 = task_started 重置为 main-only；subtask_started upsert；收尾保留终态快照；
          /resume 或下一次 task_started 清空
```

| 共享概念 | TUI | Web / Desktop |
|---|---|---|
| 标签栏 | `Horizontal(id="task-tabs")` + 不可聚焦 `_TaskTab`；点击调 `_select_agent` | `views/TaskTabs.svelte`；点击调 `selectTaskAgent` |
| 切换入口 | 标签点击；子任务折叠块标题点击（展开语义保留） | 标签点击；任务区子任务行点击/Enter/Space |
| 主视图 | `#timeline`（`display` 切换，不 unmount） | 主聊天 DOM 保留，`.is-hidden` 切换 |
| 子视图 | 既有 `#panel` 焦点视图（复用折叠块已渲染文本） | `views/SubtaskDetail.svelte` 只读卡片 |
| 输入 | 普通输入回主视图；标签点击不抢焦点 | 输入框仅 main 渲染；详情显示只读提示 |
| 主题缩写 | `_tab_label`（单行、≤14 字符、空 goal 回退 `子任务 <sid>`） | `abbreviateGoal`（同口径） |
| 状态 | 复用折叠块标题 `⟳/✓/✗` | `subtask.status` → `⟳/✓/✗/·` |

**只读边界（硬规则）**：子 Agent 没有消息通道/转录（只注入主 loop）⇒ 子视图 SHALL NOT 新建数据源、
SHALL NOT 接子 Agent 消息流、SHALL NOT 允许发送；详情只用 `task.*` 载荷字段，Web 禁 `{@html}`。
侧边任务区仍只列**在途**任务（收尾移出）；标签栏的终态快照与其独立（任务区回落不代表标签消失）。

## 6. 动画与交互（分端义务）

| 效果 | Web | TUI |
|---|---|---|
| 流式追加不闪烁 | 应当 | 应当（合帧） |
| 收起/展开 | 应当 | 应当（点标题） |
| 失败自动展开该步 | 建议 | 建议（解析失败块保持可点开） |
| Pulse / 旋转图标 | 可选 | 不做 |
| 终端拟态 / 方块光标 | 可选（工具块内） | 不做 |
| 震动 | 不做（无障碍友好） | 不做 |

## 7. 明确不做

- 外层 Task / 会话级大壳包住整轮活动与回复。
- 标题刷思考原文或工具 JSON。
- 自然语言正文中夹杂 action JSON 却当成功回复（协议层拒绝；UI 只呈现失败/原始产出块）。
- 为 UI 舒适度新建平行事件流或轮询「伪状态」。
- 声称跨端像素级一致（材质分叉是有意的）。

## 8. 与规格 / 代码的锚点

| 锚点 | 说明 |
|---|---|
| change `0233` | TUI 活动块：缺省收起、标题语法、Thinking 按 round、撤回 Task 壳 |
| change `0294` / ADR-0284 | 主/子 Agent 标签栏与只读详情（`taskview.js` / `_TaskTab` / `_SubtaskBlock`） |
| change `0299` / ADR-0289 | TUI 视觉密度预算（chrome/留白/文件呈现）与状态行合并 |
| `doc/openspec/specs/ui/spec.md` | 三端思考回显、步骤块、SSE、会话等正式 Requirement |
| `src/core/ui/repl.py` | TUI 时间线 / spinner / `_StepBlock` |
| `src/core/ui/api.py` | 事件类型映射（`loop.reasoning` 透传等） |
| `src/core/loop/default.py` | 轮末收尾后台化，保证 `loop_finished` 不被维护堵住 |

规格与本文冲突时：**以 openspec 为准**，并回头改本文。

## 9. 演进顺序（建议）

1. **已落地（TUI）**：0233 标题与收起；展开即全文；有活动块后隐藏 spinner（标题优先）；子任务标题无 `▸`；`loop.result` 即闲置；0299 密度预算与文件工具块高亮/元信息呈现。
2. **已落地（Web）**：`frontend/src/lib/activity.js` 共享标题；`Chat.svelte` 时间线（Thinking 按 round、工具块、缺省收起、`loop.result` 即闲置）；`TaskPanel` 里程碑同标题表。
3. **可选增强（Web）**：pulse、失败自动展开、工具输出等宽预览——不回流强迫 TUI。
