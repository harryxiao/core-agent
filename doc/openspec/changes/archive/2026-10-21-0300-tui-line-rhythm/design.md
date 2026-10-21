# 设计：TUI 行距节奏（change `0300` / ADR-0290）

## 事实基线（真实 REPL 渲染 + `styles.margin` 实测，Textual 8.2.8）

| 位置 | 现状 | 计算来源 |
|---|---|---|
| 段落 ↔ 段落 | 1 空行 | `MarkdownParagraph { margin: 0 0 1 0 }` |
| 列表项 | **2 行/项** | 列表项内层 `MarkdownParagraph` 同套用 bottom=1 |
| 段落 → H2–H6 | 1 空行 | 标题 `margin: 1 0 0 0` |
| 段落 → H1 | 1 空行 | 同上（与小节无差异） |
| 标题 → 正文 | 0 空行 | 标题下 margin 0 |
| 块引用 | 上下各 1 行 | `MarkdownBlockQuote { margin: 1 0 }`（本变更不动） |
| 表格 | 下 1 行 | `MarkdownTable { margin-bottom: 1 }`（本变更不动） |

## 决策

- **D1 段落零空行。** `MarkdownParagraph { margin: 0 }`。同一规则同时作用于列表项内层
  段落 ⇒ 列表项从 2 行/项回到 1 行/项（无需第二条规则）。
- **D2 列表贴边。** `MarkdownBulletList, MarkdownOrderedList { margin: 0 }`（原先列表后 1 行）。
- **D3 章/节分级。** H1 `margin: 1 0 1 0`（章前、章后各 1 行）；H2–H6 `margin: 0`
  （小节紧接上文、正文紧接标题）。App 只能按标题级别区分章/节，不能按上下文压缩。
- **D4 结构化块不动。** 块引用与表格保留既有 1 行间距：它们自带缩进/边框，视觉边界已存在，
  不属用户所指的「每一行之间」。
- **D5 零开关。** 紧凑即唯一形态，不引入 `ui.density`。

## 被拒方案

- **按「当前所在章」压缩内容**：Textual CSS 无祖先/兄弟上下文选择器，无法表达「本节正文」；
  唯一可选近似就是标题级别。
- **H2–H6 也保留 1 行**（方案 C）：小节之间不收紧，与用户「1.1/1.2/1.3 紧凑」的裁决不符。
- **保留段落 1 行、只压小节**（方案 A）：正文仍逐行空行，未解主诉。
- **改 `ui.density` 配置键**：双形态测试面翻倍，无真实需求。
- **改共享标题语法 / 事件面**：超出呈现层边界。

## 测试策略

`tests/test_repl.py` 复用 `_reply_app`（delta 驱动回复）与 `query("MarkdownHeader,
MarkdownParagraph, MarkdownBulletList")` 的 y/height 度量：

1. 两个相邻段落 ⇒ 第二段 `region.y == 第一段 y + 1`（0 空行）。
2. 两项无序列表 ⇒ `MarkdownBulletList.region.height == 2`（1 行/项）。
3. 段落 → H2 ⇒ `H2.region.y == 段落 y + 1`（0 空行）。
4. 段落 → H1 ⇒ `H1.region.y == 段落 y + 2`（1 空行）；H1 → H2 ⇒ `H2.y == H1.y + 2`（章后 1 空行）。

反证（`cp` 到 `/tmp` + `md5sum` 复原）：

- 段落 margin 恢复 `0 0 1 0` ⇒ 用例 1/2 红；
- H2–H6 恢复 `margin: 1 0 0 0` ⇒ 用例 3 红；
- H1 恢复 `margin: 1 0 0 0` ⇒ 用例 4 红。

## 风险与回滚

- 风险：连续段落渲染后连成一片（Markdown 源的空行在渲染层不再体现）——这是用户明确裁决的
  取舍；标题的加粗/色彩仍提供结构线索。
- 回滚：三条 CSS 规则整体 revert，行为回到 0299 口径。

## 局限

1. 纯文本大纲（无 `#`/`##`）无法区分章/节，只能吃到段落 0 空行。
2. 块引用/表格仍保留 1 行间距（有意）。
3. 段落连排后，源文档里的分段在视觉上不可辨（内容换取密度）。
4. 终端行高（Windows Terminal 默认 1.2）仍需终端侧设置。
