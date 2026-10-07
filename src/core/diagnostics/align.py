"""显示宽度对齐助手（诊断视图**共用单一实现**）。

`len()` 是**字符数**，与等宽终端下的列数不等：东亚宽 / 全角字符占 2 列。诊断视图的列补齐
SHALL 按**显示宽度**计算，且列间分隔符 SHALL 为两个空格、SHALL NOT 用制表符（其宽度由终端自定）。

两种形态各一个入口：

- `align_rows` —— **表格型**（多行多列：会话 / MCP 端点 / 笔记）：每列按列内最长显示宽度补齐；
- `align_pairs` —— **键值型**（一组 `标签 值` 行：配置 / 技能 / 运行状态）：标签列按标签中
  最长显示宽度补齐；明细行（`str`）原样透出，不参与补齐。

对应规格：doc/openspec/specs/cli-ops/spec.md「诊断视图列对齐」
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

_SEP = "  "  # 列间分隔符：两个空格（**不是** `\t` —— 制表符宽度由终端自定，正是缺陷根源）


def display_width(text: str) -> int:
    """文本的**显示列宽**：东亚宽 / 全角字符按 2 列计，其余按 1 列。"""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def pad(text: str, width: int) -> str:
    """按**显示宽度**左对齐补齐到 `width` 列（`f"{text:<{width}}"` 只数字符数）。"""
    return text + " " * max(0, width - display_width(text))


def align_rows(rows: Sequence[Sequence[str]]) -> list[str]:
    """表格型：每列按列内最长显示宽度补齐；**行末不补**（免尾随空白）。"""
    if not rows:
        return []
    last_of = [len(row) - 1 for row in rows]
    widths = [
        max(display_width(row[i]) for row in rows if i < len(row))
        for i in range(max(len(row) for row in rows))
    ]
    return [
        _SEP.join(cell if i == last_of[at] else pad(cell, widths[i]) for i, cell in enumerate(row))
        for at, row in enumerate(rows)
    ]


def align_pairs(entries: Sequence[tuple[str, str] | str]) -> list[str]:
    """键值型：标签列按标签中最长显示宽度补齐；明细行（`str`）原样透出。

    混合形态是刻意的 —— 技能视图的 `· …` 明细行夹在键值行之间，不参与补齐。
    """
    labels = [entry[0] for entry in entries if isinstance(entry, tuple)]
    width = max((display_width(label) for label in labels), default=0)
    return [
        entry if isinstance(entry, str) else f"{pad(entry[0], width)}{_SEP}{entry[1]}"
        for entry in entries
    ]
