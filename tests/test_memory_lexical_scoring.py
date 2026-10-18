"""词法检索的 IDF 加权与长度归一（change 0252 / ADR-0242 / 台账 E188）。

缺省检索（未配置 embedding 模型）此前对所有查询词元等权、忽略文档长度：常见词稀释罕见词、
长文档天然占优。本组用例锁 BM25 口径与 `stats=None` 的公开 API 兼容面。
"""

from __future__ import annotations

import time

import pytest

from core.memory import MemoryEntry, MemoryStore
from core.memory.relevance import build_lexical_stats, rank, recency_decay, relevance

_TS = 1000.0  # 固定时间戳 ⇒ 所有候选同新鲜度，排序差异只来自相似度


def _entry(entry_id: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=[],
        source="loop",
        trace_id="t",
        ts=_TS,
        kind="episodic",
    )


def _store_entries() -> list[MemoryEntry]:
    """语料：罕见词「量子」1 篇（**最后写入**）；常见词「报告」5 篇。

    罕见词后写 ⇒ 若排序退化为等权（或稳定排序按插入序），端到端用例会红。
    """
    return [
        _entry("common", "报告"),
        *[_entry(f"filler{i}", "报告 流程") for i in range(4)],
        _entry("rare", "量子"),
    ]


def test_idf_prefers_rare_query_term() -> None:
    """两条目各命中一个查询词元 ⇒ 文档频率更低（IDF 更高）者排前。"""
    entries = _store_entries()
    stats = build_lexical_stats(entries, "量子 报告")
    assert stats is not None

    rare = next(e for e in entries if e.id == "rare")
    common = next(e for e in entries if e.id == "common")
    rare_score = rank(rare, "量子 报告", stats=stats)
    common_score = rank(common, "量子 报告", stats=stats)
    # 两条目同长度 ⇒ 得分比 ≈ IDF 比（此处约 6.4×）；取 2× 余量避开浮点噪声。
    assert rare_score > common_score * 2


def test_length_normalization_prefers_short_document() -> None:
    """同词命中，长文档被长度归一项压低。"""
    short = _entry("short", "缓存")
    long = _entry("long", "缓存 " + " ".join(f"填充{i}" for i in range(20)))
    stats = build_lexical_stats([short, long], "缓存")
    assert stats is not None

    short_score = rank(short, "缓存", stats=stats)
    long_score = rank(long, "缓存", stats=stats)
    # 相似度收顶 1.0 ⇒ 实际得分倍率约 1.28×；取 1.2× 余量避开浮点噪声。
    assert short_score > long_score * 1.2


def test_cjk_bigram_exact_overlap_first() -> None:
    """CJK 二元组：完整覆盖查询字符序列的条目排前。"""
    exact = _entry("exact", "记忆检索")
    reordered = _entry("reordered", "检索记忆")
    stats = build_lexical_stats([exact, reordered], "记忆检索")
    assert stats is not None

    assert relevance(exact, "记忆检索", stats=stats) > relevance(reordered, "记忆检索", stats=stats)


def test_stats_none_keeps_legacy_overlap_formula() -> None:
    """不传 stats ⇒ 原「交集 / 查询词元数」公式（公开 API 逐字兼容）。"""
    entry = _entry("a", "alpha beta")
    query = "alpha gamma"

    # 无档位标签 ⇒ 默认档偏移为 0（change 0277 分档项不改变未分档得分）
    assert relevance(entry, query) == pytest.approx(0.5 * 0.5 + 0.2 * 0.6)
    assert rank(entry, query) == pytest.approx(
        relevance(entry, query) * recency_decay(entry) * (1.0 + 0.0) * (1.0 + 0.0)
    )


def test_store_read_uses_idf_stats_end_to_end() -> None:
    """生产路径（`MemoryStore.read`）真的按 IDF 排序。"""
    store = MemoryStore()
    for entry in _store_entries():
        store.write("L2", entry)

    hits = store.read("量子 报告", budget=100_000)

    ids = [e.id for e in hits]
    assert ids.index("rare") < ids.index("common")


def test_embedder_failure_still_uses_idf_stats() -> None:
    """embedder 抛错 ⇒ 降级词法，仍带 IDF/长度归一（不是退回等权重叠）。"""

    def broken(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedder down")  # noqa: TRY003 — 模拟 embedding 服务不可达

    store = MemoryStore(embedder=broken)
    for entry in _store_entries():
        store.write("L2", entry)

    hits = store.read("量子 报告", budget=100_000)

    ids = [e.id for e in hits]
    assert ids.index("rare") < ids.index("common")


def test_stats_default_none_for_empty_query() -> None:
    """空查询 / 空语料 ⇒ 无统计（调用方走原路径，不抛错）。"""
    assert build_lexical_stats(_store_entries(), "") is None
    assert build_lexical_stats([], "量子") is None


def test_relevance_without_stats_ignores_entry_order() -> None:
    """兼容面：原公式下两条目命中数相同时得分相同（不引入隐式排序）。"""
    a = _entry("a", "alpha")
    b = _entry("b", "alpha and much longer content")
    q = "alpha"
    assert relevance(a, q) == relevance(b, q)
    assert relevance(a, q) == pytest.approx(0.5 * 1.0 + 0.2 * 0.6)


def test_score_importance_path_unchanged() -> None:
    """`_score_importance` 以 `rank(e, "")` 排序 ⇒ 空查询沿用原语义（不抛错）。"""
    entry = _entry("a", "alpha beta")
    assert time.time() > _TS
    assert rank(entry, "") >= 0.0
