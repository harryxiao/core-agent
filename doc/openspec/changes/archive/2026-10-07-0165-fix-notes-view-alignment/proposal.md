# fix-notes-view-alignment

## Why

`/notes` 命令输出乱：`render_notes` 用 `\t` 拼接 note_id/title/时间戳三列，而 TUI 显示层（`Static` 纯文本）不解释制表符宽度，导致列随 note_id 长度参差不齐；组件行前缀叠加后观感更乱。

## What Changes

- `render_notes`（`src/core/diagnostics/views.py`）行构造改为**等宽列拼接**：note_id、title 各按清单内最长**显示宽度**（东亚宽 / 全角字符按 2 列计）补齐，列间分隔符为两个空格；title 为空回退 note_id 且列宽不小于回退值。
- 弃用 `\t` 分隔（避免依赖终端 tab 宽度）。
- 不改公共接口（仍返回 `Report`）、不引入新依赖。

## Spec Delta（摘要）

cli-ops 规格（视图与 doctor/status 同源同形状的约束所在）新增「诊断视图列对齐」要求：`render_notes` 输出
按**显示宽度**（非字符数）等宽列对齐、双空格分隔、`\t` 禁用。

## 不做

- 不改 TUI 端组件（`Static` / `DataTable` 升级留待独立 change）
- 不改其他 render_* 视图（各自独立提案）
