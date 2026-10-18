"""检索词元缓存（change 0276 / ADR-0266，规格「检索词元缓存（有界、按内容失效）」）。

三条契约：

1. **复用**：同一 store 再次检索时，内容未变的条目不得重新分词（只有查询分词）；
2. **失效**：同 id 覆写内容后，新检索使用新词元集，旧词元不残留；
3. **有界**：缓存条目数不超过 `_TOKEN_CACHE_MAX`（FIFO 淘汰）。

复用与否不改变检索结果（排序 / 预算 / 命中集）—— 由结果逐条一致断言与既有全量测试守护。
"""

from __future__ import annotations

import importlib

import pytest

from core.memory import MemoryEntry, MemoryStore
from core.memory.relevance import build_lexical_stats

relevance_module = importlib.import_module("core.memory.relevance")
store_module = importlib.import_module("core.memory.store")

_QUERY = "缓存"
_CACHE_MAX = 5
_FROZEN_TS = 4_000_000_000.0  # 冻结新鲜度衰减，排除写盘时刻噪声


def _entry(index: int, content: str) -> MemoryEntry:
    return MemoryEntry(
        id=f"cache-{index:02d}",
        layer="L2",
        content=content,
        tags=["cache"],
        source="cache",
        trace_id="cache",
        ts=_FROZEN_TS,
    )


@pytest.fixture
def token_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """记录每次 `relevance.tokens` 的入参。"""
    calls: list[str] = []
    original = relevance_module.tokens

    def counting(text: str) -> set[str]:
        calls.append(text)
        return original(text)

    monkeypatch.setattr(relevance_module, "tokens", counting)
    return calls


def _store_with(count: int) -> MemoryStore:
    store = MemoryStore()
    for index in range(count):
        store.write("L2", _entry(index, f"事实 {index:02d} 关于 缓存 分词 与 检索"))
    return store


def test_token_cache_reuses_unchanged_entries(token_calls: list[str]) -> None:
    """第二次检索只对查询分词（未变条目零重新分词），且结果与首次逐条一致。"""
    store = _store_with(50)
    first = store.read(_QUERY, budget=4096)
    before = len(token_calls)

    second = store.read(_QUERY, budget=4096)
    second_calls = token_calls[before:]

    assert [entry.id for entry in second] == [entry.id for entry in first]
    assert second_calls, "查询本身仍应分词"
    assert all(call == _QUERY for call in second_calls), "未变条目不应重新分词"
    assert len(second_calls) <= 2  # noqa: PLR2004 — backend.search 与统计各一次查询分词


def test_token_cache_invalidates_on_content_change() -> None:
    """同 id 覆写后，统计使用新内容词元；旧词元不残留。"""
    cache: dict[str, tuple[str, frozenset[str]]] = {}
    entry = _entry(0, "旧内容 苹果")
    stats = build_lexical_stats([entry], "苹果", token_cache=cache)
    assert stats is not None
    assert "苹果" in stats.doc_tokens[entry.id]

    entry.content = "新内容 香蕉"
    updated = build_lexical_stats([entry], "香蕉", token_cache=cache)
    assert updated is not None
    assert "香蕉" in updated.doc_tokens[entry.id]
    assert "苹果" not in updated.doc_tokens[entry.id]


def test_token_cache_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """缓存条目数不超过上界（FIFO 淘汰），检索照常返回。"""
    monkeypatch.setattr(store_module, "_TOKEN_CACHE_MAX", _CACHE_MAX)
    store = _store_with(20)
    rows = store.read(_QUERY, budget=4096)

    assert rows
    assert len(store._token_cache) <= _CACHE_MAX  # noqa: SLF001 — 有界性边界断言
