# 0169 · 设计

## 1. 为什么不新造控件（子类化 `Collapsible`）

| 方案 | 否决/采纳理由 |
|---|---|
| 自造 `Vertical` + 自定义折叠 | 折叠语义（隐藏正文、切换字形、切换后滚入视野）要**重造**；且既有时间线测试助手按 `isinstance(child, Collapsible)` 遍历时间线（`tests/test_repl.py`、`tests/test_ui.py`）⇒ 非 `Collapsible` 的时间线子节点会**逃过**全部既有断言 ⇒ 要改一处助手 + 复查所有断言 |
| **`_StepBlock(Collapsible)`**（**采纳**） | 子类**天然命中**既有助手与断言（零改动）；折叠由 Textual 维护；与仓内 `_PaletteList(OptionList)` 子类化惯例一致 |

`Collapsible` 的 `Contents` 自带 `padding: 1 0 0 3` ⇒ **L 形缩进是原生的**，本仓只补 `└ ` 角标。
三态与手势的 Textual 依据见 ADR-0160（`CollapsibleTitle._on_click` 先 `stop()` ⇒ 正文点击必达 `_StepBlock`）。

## 2. 三态物理落点（为什么窗口必须 Python 切片）

Textual **没有**「只显示末尾 N 行」的样式能力：`max-height` 裁**顶部**（保留首行），`overflow-y` 给的是
**滚动**而非窗口。故：

- **折叠态**（收起）＝ Textual 的 `collapsed`（样式层管）；
- **窗口态**（缩略）＝ `_render()` 里的**行切片**（语言层管）。

两者正交 ⇒ 三态 = `collapsed` × `_full` 两个布尔：

```
collapsed=True                  → 收起（正文隐藏）
collapsed=False and not _full    → 缩略（末尾 N 行 + 剩余提示）
collapsed=False and _full        → 全文（全量 + 收起提示）
```

`_full` 只在 `on_click` 里翻转；`collapsed` 由标题点击（Textual）或 `_render` 不动。

## 3. 行缓冲（消 O(n²)）

```
_lines: list[str]        # append-only；末元素是「当前未完成行」
feed(text)               # 增量：按 '\n' 切，只追加（无全文重拼、无重解析）
set_text(text)           # 一次性成文（工具输出：整体替换）
_render()                # 仅此处拼文本：切窗口 → 加角标 → 加提示行 → body.update()
```

原实现 `str(detail.render()) + text` 每 delta 全文重拼（O(n²)）⇒ 长思考流越来越卡。append-only 后
`feed` 为 O(len(text))、`_render` 为 O(窗口 + 提示)。

## 4. 目标摘要（`_tool_target`）

模块级纯函数（近 `_TOOL_NAMES`，便于单测直取）：

```
_TARGET_FIELDS = {            # tool_id → 白名单字段（结构性、非正文）
    "tools.file_read": "path", "tools.file_write": "path", "tools.file_patch": "path",
    "tools.web_fetch": "url", "tools.code_run": "script",
    "tools.gate_run": "gate", "tools.context_read": "pointer",
}
_tool_target(tool_id, args) -> str
```

- `args` **非 `Mapping`**（`_args_excerpt` 对超长参数返回**节选字符串**）⇒ `""`（**不解析 repr**）；
- 白名单字段缺失 / 非字符串 / 空串 ⇒ `""`；
- 取到值 ⇒ 单行化（首个 `\n` 前）+ 去首尾空白 + 超 `_MAX_TARGET_CHARS`(=60) 截断加 `…`。

标题拼装：`f"⏺ {友好名}  {目标}"`（无目标时只留友好名，**不落占位**）。**SHALL NOT** 呈现
`content` / `old_content` / `new_content` 或内部 `tool_id`（承「TUI 子任务运行态与详情」同一红线）。

## 5. 接缝映射（改哪、不改哪）

| 站点 | 动作 |
|---|---|
| `repl.py` 模块常量区 | **加** `_STEP_TAIL_LINES` / `_MAX_TARGET_CHARS` / `_TARGET_FIELDS` / `_tool_target` |
| `build_app` 内（`_PaletteList` 旁） | **加** `class _StepBlock(Collapsible)` |
| `ReplApp.CSS` | **加** `.step-body` / `.step-more` |
| `ReplApp.__init__` | `_actions` 值 → `(box, target: str)`；`_reasoning` → `_StepBlock \| None` |
| `_add_action_widget` | 建 `_StepBlock`（标题带目标）；`completed` 改标题 + `set_text(output)` |
| `_add_reasoning_widget` | 建 `_StepBlock("▸ 思考")`；增量走 `feed()` |
| `format_action_event` | **不动**（CLI + 子任务里程碑共用） |
| `_flush_tail` / `_touch_tail` / `_show_delta` | **不动** |
| `_add_task_widget` / `_open_subtask` / `_progress_subtask` / `_set_focus` / 焦点视图 | **不动** |
| `_reset_turn_state` | **不动**（`_actions` / `_reasoning` 清空口径不变） |
| `entry.py` / `api.py` / Web / APP | **不动** |

## 6. 规格写作要点

- 「Think」**MODIFIED**：只把「**缺省收起**」分端化（TUI 缩略 / Web + APP 保留），三端折叠块、同轮归并、
  纯呈现层、未开启不产事件 —— **逐字保留**；三态机制改为**指向**新 Requirement（不写第二份）。
- 新增 Requirement 覆盖**思考块 + 工具动作块**，明写**不覆盖**子任务折叠块与焦点视图。
- 「CLI 友好交互」的 Scenario「折叠块展示」（长内容默认折叠）**相容 ⇒ 该 Requirement 逐字不改**：
  缩略即该「折叠」的具体形态（超出有界行数者默认不可见、点开可见）。

## 7. 测试设计（红 → 绿）

- 既有断言**必改**（缺省已展开、标题现带目标）：`test_tui_action_widget_lifecycle` 的
  `contents.display is False` / `"⏺ Bash ✓ (1.5s)"` / `"参数" not in text`（换成**真守护**：
  标题不含正文参数）；`test_tui_thinking_renders_in_single_collapsed_block` 的 `all_collapsed`。
- 新增：`_tool_target` 表驱动（7 类字段 / 未知工具 / 缺字段 / 非映射 / 超长截断 / 多行取首行）；
  缩略窗口（喂 20 行 ⇒ 8 行 + 「还有 12 行」）；点正文 ⇄ 全文；点标题收起；正文含超长单行
  （守护 `width: 1fr` ⇒ 防退回裁切）；思考增量实时追加且同轮归并同一块。
- 红态证据：先写测试 ⇒ `git stash` 实现 ⇒ 新增用例**全红** ⇒ 复原 ⇒ 转绿。
