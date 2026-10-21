# 提案：TUI 行距节奏——正文/列表紧凑、章边界保留

## Why

change `0299` 把垂直留白压到「段落间 1 行」，但真实文档（章程式：章 → 小节 → 正文/列表）的观感仍是「每一行之间都空一行」：

| # | 现象（真实 REPL 实测） | 根因 |
|---|---|---|
| 1 | 段落 ↔ 段落固定空 1 行 | `MarkdownParagraph { margin: 0 0 1 0 }`（0299 刻意保留） |
| 2 | **列表每项占 2 行** | 列表项内层也是 `MarkdownParagraph`，套用同一条 bottom=1 |
| 3 | 小节（1.1/1.2/1.3）之间与小节、章之间没有密度差异 | H1 与 H2–H6 同为 `margin: 1 0 0 0` |
| 4 | 章标题后正文紧跟（0 空行），章内层次不显 | H1 下 margin 为 0 |

用户裁决：**全紧凑（方案 B）**——正文段落与列表之间 0 空行；小节标题上方 0 空行；
章标题（H1）前后各保留 1 行；章与小节的边界据此可扫。

## What Changes

- `MarkdownParagraph` margin-bottom `1 → 0`（列表项随之从 2 行/项回到 1 行/项）。
- `MarkdownBulletList` / `MarkdownOrderedList` margin-bottom `1 → 0`。
- H1 `margin: 1 0 1 0`（章前、章后各 1 行）；H2–H6 `margin: 0`（小节紧接上文）。
- 规格 `ui` **MODIFIED** ×1：重写「TUI 视觉密度预算」的 Markdown 预算段（原「段落间 1 行
  SHALL 保留、SHALL NOT 压缩为 0」被本变更取代），+2 Scenario。

## Non-goals

- 不做 `ui.density` 开关；不引入按「当前所在章」的上下文压缩（CSS 无祖先/兄弟上下文选择器）。
- 不改块引用 / 表格的既有 1 行间距（结构化块不属「每一行」）。
- 不改共享标题语法表、事件面、Web/Desktop。
- 不改终端行高（由终端模拟器决定）。

## Impact

- 呈现层：`src/core/ui/repl.py` 的 `App.CSS` 三条规则；一次 revert 整体回退。
- 文档：`doc/03-interfaces/ui-scheme.md` §5.1 密度预算表；ADR-0290；known-risk E236；
  test-cases §213。
- 测试：`tests/test_repl.py` +4（段落 0 空行、列表 1 行/项、小节前 0、章前后各 1）。
