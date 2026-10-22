"""记忆内容分区权重（change 0277 / ADR-0267 / 台账 E213）。

`relevance` 在「语义相似 × 层结构」之上叠加一维**加性**分区权重（`0.15·tier`）：
`milestone` / `decision` ⇒ 高档（+1），`log` / `transcript` ⇒ 低档（−1），其余 ⇒ 默认档（0，
不产生偏移 ⇒ 未分档条目排序逐位不变）。冲突高档优先；标签精确、小写匹配。
"""

from __future__ import annotations

import pytest

from core.memory import Layer, MemoryEntry, MemoryStore
from core.memory.relevance import rank, relevance

_CONTENT = "共同 内容"


def _entry(
    entry_id: str, tags: list[str], layer: Layer = "L2", content: str = _CONTENT
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,
        content=content,
        tags=tags,
        source="tier",
        trace_id="t",
        ts=0.0,  # 未知新鲜度 ⇒ recency_decay 恒 1.0
    )


def test_three_tiers_order_relevance_and_rank() -> None:
    """同内容/层/时间戳，仅 tags 不同 ⇒ relevance 与 rank 均为 高 > 默认 > 低。"""
    high = _entry("high", ["milestone"])
    default = _entry("default", ["bench"])
    low = _entry("low", ["log"])

    assert relevance(high, "共同") > relevance(default, "共同") > relevance(low, "共同")
    assert rank(high, "共同") > rank(default, "共同") > rank(low, "共同")
    # 权重差：高 − 默认 = 默认 − 低 = 0.15（档位 +1 / 0 / −1）
    spread = relevance(high, "共同") - relevance(default, "共同")
    assert spread == pytest.approx(0.15)
    assert relevance(default, "共同") - relevance(low, "共同") == pytest.approx(0.15)


def test_conflict_prefers_high_and_unknown_is_default() -> None:
    """冲突（milestone + log）按高档；未知标签与大小写漂移落默认档。"""
    baseline = relevance(_entry("default", ["bench"]), "共同")
    assert relevance(_entry("conflict", ["milestone", "log"]), "共同") > baseline
    assert relevance(_entry("unknown", ["unknown"]), "共同") == baseline
    assert relevance(_entry("case", ["Milestone"]), "共同") == baseline


def test_same_tier_keeps_layer_priority() -> None:
    """未分档条目的层优先级语义不变（默认档为常量偏移）。"""
    l2 = _entry("l2", [], layer="L2")
    l3 = _entry("l3", [], layer="L3")
    assert rank(l3, "共同") > rank(l2, "共同")


def test_store_read_orders_by_tier() -> None:
    """端到端：三条等价条目按 高 → 默认 → 低 返回（正文互异，避免 0304 近重复抑制）。"""
    store = MemoryStore()
    for entry in (
        _entry("low", ["transcript"], content=f"{_CONTENT} 甲"),
        _entry("default", ["bench"], content=f"{_CONTENT} 乙"),
        _entry("high", ["decision"], content=f"{_CONTENT} 丙"),
    ):
        store.write(entry.layer, entry)

    rows = store.read("共同", budget=4096)
    assert [entry.id for entry in rows] == ["high", "default", "low"]
