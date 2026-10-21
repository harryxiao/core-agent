# 0299 — TUI 视觉密度改版（商业级终端观感）

## Why

用户反馈：**TUI 丑 —— 显示文件间距大、字体偏大**。逐行勘察（`src/core/ui/repl.py`，
样式全在单条 `App.CSS`）后，问题不是审美而是**密度工程**：Textual 的默认留白规则未被覆盖，
底部 chrome 双盒叠加，工具输出以 dict repr 灰墙呈现。

| # | 现象 | 根因（已验证） |
|---|---|---|
| 1 | 展开块顶部空一行 + 缩进深 | 默认 `Collapsible > Contents { padding: 1 0 0 3 }` 未覆盖 |
| 2 | 回复内文件列表/代码块间距大 | Markdown 默认 margin/padding 未覆盖：围栏 = 内容+4 行、H1 +3、`---` 3 行 |
| 3 | 底部 chrome 厚（idle 6 行 / busy 8 行） | `#input-box` 与 `#hints` 各背一个 round 边框盒，`#spinner` 独占一行 |
| 4 | 启动横幅 5 行 | `.welcome` round 边框 + 下边距 |
| 5 | 展开的文件内容是灰色 plain text | `box.set_text(str(output))`：内置文件工具的 `output` 是 `str(data)[:400]` 的 **dict repr**（如 `{'path': …, 'content': 'x=1\n…'}`），无高亮、无元信息、换行转义不可读 |
| 6 | 「字体偏大」 | 终端字体由终端模拟器决定，应用无字号杠杆；体感来自空行/边框/加粗的视觉重量（文档内诚实说明 + 终端侧配套建议） |

## What Changes

**密度（CSS 覆盖，全在 `App.CSS` 一处）**

- 底部 chrome 合并为**单行状态行**：`#hints` 去边框（高 1 行），`#spinner` 并入同一行左侧；
  行数预算 **idle ≤ 4 / busy ≤ 5**（现 6/8）。`#input-box` 保留 round 边框（唯一交互锚点）。
- `Collapsible > Contents { padding: 0 0 0 2; }`：展开体零顶空行、缩进 3→2 列。
- Markdown 密度：`Markdown { padding: 0 }`、段落留白保留（`0 0 1 0`）、围栏
  `margin: 0; padding: 0 1`（N 行内容 = N 行）、H1–H6 上留 1 行、水平线压到 1 行。
- 欢迎横幅去边框：5 行 → 2 行。命令面板 `max-height 8 → 6`。
- 每轮助手回复结束后呈现 **1 行 dim 分隔**（轮次可扫性）。

**文件呈现（质量）**

- 文件三件套（`tools.file_read` / `file_write` / `file_patch`）展开体：
  - 首行 **dim 元信息行**，从 args / output 确定性推导：write `N 字节 · M 行写入`、
    patch `+N −M · hunk H`（由 old/new 节选合成 unified diff）、read `N 行`（标注 `节选`
    当内容被事件面截断）；
  - 正文按文件后缀**语法高亮**（rich 自带 `Syntax`，零新增依赖；patch 用 diff lexer）；
  - 展开体**行数上界 40**（`_MAX_BODY_LINES`），超出截断并附尾行 `…（共 X 行，已截断）`。
- 其他工具（`code_run` 等）呈现逐字不变。

**方案对既定计划的诚实修正**（实现期查证，两处）：

1. 行上界取 **40** 而非 200：`action_completed.output` 事件面已有 400 字符节选上界
   （change 0152），200 行永不触达；40 行可被换行密集输入触达（防空白行洪泛），
   正常内容不可达。
2. 「+N −M 增删行数确定性计数」的来源限定：args 逐值亦经 400 字符节选 ⇒ 大改动的计数是
   **下界**，元信息行在任一侧被截断时标注 `节选`（不谎报全量）。

## Non-goals

- 不引入 `ui.density` / 主题配置键（紧凑即唯一形态，无开关）。
- 不动 Web / Desktop 端；不改共享标题语法表（ui-scheme §3，TUI+Web 同源）。
- 不引第三方高亮库（用 rich 自带 Syntax；rich 是 textual 既有依赖）。
- 不改 loop 事件面（`action_completed` 载荷逐字不变；所有抽取都在 TUI 侧容错进行）。
- 不做截图类自动化验收（观感以人工目检为准）。
- 不解决终端字号（应用无杠杆；文档给终端侧配套建议：等宽字体、10–12pt、行距 1.0）。

## Impact

- **规格**：`specs/ui` ADDED「TUI 视觉密度预算」（一个 Requirement 收口全部密度/呈现约束；
  既有 Requirement 无行为变化 —— 状态行合并不触碰任何已规格化行为）。
- **代码**：`src/core/ui/repl.py`（CSS + compose 重排 + `_StepBlock` 高亮/截断/元信息行 +
  轮次分隔），零新配置键、零新依赖、零 spec 外行为。
- **文档**：`doc/03-interfaces/ui-scheme.md` §4（相位行）与 §5.1（TUI 材质映射）重写；
  §2/§3 不动。ADR-0289 / known-risk E235 / test-cases §212。
- **测试**：`tests/test_repl.py` 新增密度预算用例组（先红后绿）。
