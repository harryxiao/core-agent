"""待裁决登记簿结构守卫（change 0226 / ADR-0216 / 台账 E163）。

`coding-plan/Pending-Arbitration.md` 是「**还有什么在等裁决**」的单一入口。它通常不会「写错」，
而是**悄悄丢项**：某条只在总表、正文没了；闭项漏了 change 号；开放项没写「落地面」——
下次走查就只看到一张残缺的表（本轮实有前科：阶段索引漂移差点让最相关的两册 Phase 被漏掉）。

本文件只钉**结构完整性**，**不判内容对错**（证据是否仍准确无真源可核 —— 同 `test_prompt_mirror`
的「旁注只锚已知加固点」纪律）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_LEDGER = Path(__file__).resolve().parents[1] / "coding-plan" / "Pending-Arbitration.md"

_TABLE_ROW = re.compile(r"^\|\s*\*\*(PA-\d{2})\*\*\s*\|")
_DETAIL_HEAD = re.compile(r"^###\s+(PA-\d{2})\b", re.MULTILINE)

#: 第二轮（长任务 × 记忆）项（含已闭；已闭项仍须保留五要素）—— 新增项时**手工**加进来
#: （已知局限，见 ADR-0216②）。
_ROUND2 = ("PA-08", "PA-09", "PA-10", "PA-11", "PA-12")
_CLOSED_MARK = "已闭"
_CHANGE_NO = re.compile(r"`0\d{3}`")


def _text() -> str:
    return _LEDGER.read_text(encoding="utf-8")


def _listed() -> list[str]:
    rows = (_TABLE_ROW.match(line) for line in _text().splitlines())
    return [match.group(1) for match in rows if match]


def _section(label: str) -> str:
    parts = re.split(rf"^###\s+{label}\b", _text(), maxsplit=1, flags=re.MULTILINE)
    assert len(parts) == 2, f"§2 缺 {label} 逐条小节"  # noqa: PLR2004 — 切分恰为「前 + 一节」
    return parts[1].split("\n### ")[0]


def test_two_rounds_stay_separated() -> None:
    """两轮的边界与清单各自成节（混作一节会让「开放项」被误读成「已闭项」）。"""
    text = _text()
    for heading in ("## §0.1", "## §0.2", "## §1.1", "## §1.2"):
        assert heading in text, f"缺分节标题：{heading}"


def test_every_listed_item_has_a_detail_section() -> None:
    """总表列出的每个 PA-NN 都必须在 §2 有逐条小节（防「总表有、正文丢」）。"""
    listed = set(_listed())
    detailed = set(_DETAIL_HEAD.findall(_text()))
    assert listed, "§1 未解析到任何 PA 行 —— 表格格式变了？"
    assert listed - detailed == set(), f"总表有但 §2 无逐条：{sorted(listed - detailed)}"


def test_closed_items_carry_a_change_number() -> None:
    """标「已闭」的行必须带 change 号（否则追溯断点）。"""
    for line in _text().splitlines():
        match = _TABLE_ROW.match(line)
        if match and _CLOSED_MARK in line:
            assert _CHANGE_NO.search(line), f"{match.group(1)} 标已闭但无 change 号"


@pytest.mark.parametrize("label", _ROUND2)
def test_open_items_are_actionable(label: str) -> None:
    """开放项必须自带 现象 / 证据 / 可选项 / 建议 / 落地面 —— 缺一即不可裁决。"""
    body = _section(label)
    for required in ("**现象**", "**证据**", "可选项", "**建议**", "落地面"):
        assert required in body, f"{label} 缺「{required}」"
