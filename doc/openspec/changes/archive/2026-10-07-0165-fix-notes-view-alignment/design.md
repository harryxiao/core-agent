# Design: fix-notes-view-alignment

## 目标

`/notes` 列表在任意等宽终端下三列（note_id / title / updated_at）对齐。

## 方案

最小改动、渲染层内解决：`render_notes.rows()` 先求列宽，再按**显示宽度**补齐，分隔符为两个空格：

- `w_id = max(_display_width(note_id))`，`w_title = max(_display_width(title or note_id))`
- `_display_width(text)`：`unicodedata.east_asian_width(char) in "WF"` ⇒ 2 列，否则 1 列
- `_pad(text, width)`：`text + " " * (width - _display_width(text))`
- 行：`f"{_pad(note_id, w_id)}  {_pad(title or note_id, w_title)}  {int(updated_at)}..."`
- pinned 标记沿用原格式追加在行尾

**为什么必须按显示宽度**：`f"{v:<{w}}"` 只按**字符数**补齐 —— 中日韩字符在等宽终端下占 2 列，
`len("一个较长的标题") == 7` 但显示宽 14 ⇒ 一行中文标题会把时间戳列整体推右（实测同字符长度下
显示宽 37 / 43 / 36）。本仓笔记标题以中文为主，按字符数补齐等于没对齐。

## 备选与取舍

- TUI 端换 `DataTable`：显示更优但跨 UI（CLI/Web）不一致，且诊断视图承诺「只读、与 doctor/status 同源同形状」，对齐应发生在渲染层 —— 弃用。
- 按**字符数**补齐（`f"{v:<{w}}"`）：对纯 ASCII 清单有效，对中文清单无效（见上） —— 弃用。
- 全列统一 `\t`：终端 tab 宽度不定，正是本次 bug 根源 —— 弃用。

## 兼容性

- `Report` 接口不变；`tests/test_diagnostics.py::test_render_notes_marks_pinned` 断言（`"alpha" in out`、`"常驻" in out`）在新格式下仍成立。
- 空清单与句柄缺失路径不受影响（`_NOT_WIRED` 提前返回）。
- 列宽按清单内最长**显示宽度**动态计算，超长 title 会导致行长增长 —— 可接受（列表即本库的笔记，规模有限）。

## 风险

列宽按清单内最长**显示宽度**动态计算，超长 title 会导致行长增长 —— 可接受（列表即本库的笔记，规模有限）。
`east_asian_width` 对**歧义宽（Ambiguous）**字符（如 `±`、`→`）无全国统一裁决：本实现按 1 列计
（`"WF"` 不含 `A`）—— 与多数现代终端默认一致；若终端按双宽渲染歧义字符，该行会有 1 列偏移
（已知局限，不阻断；仅影响含歧义字符的标题）。
