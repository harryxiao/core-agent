"""记忆检索的层过滤（change 0302 / 规格「记忆检索的层过滤（读取面）」）。

旧实现：``read()`` 全层召回 —— L0 人格（层权重 1.0）、L3 演化候选、L4 归档
都可能以「事实」名义进入 prompt 并争抢事实面预算。本文件钉住：``layers`` 白名单
只返所列层；过滤先于排名/预算（被滤条目不吃预算、不被复用强化）；缺省不过滤；
与来源排除 / 会话过滤叠加。
"""

from __future__ import annotations

import time

from core.memory import FileBackend, MemoryEntry, MemoryStore
from core.plugin_registry import EffectTracker


def _entry(
    entry_id: str,
    layer: str,
    *,
    content: str,
    source: str = "loop",
    session_id: str = "s1",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,  # type: ignore[arg-type]
        content=content,
        tags=[],
        source=source,
        trace_id="t",
        ts=time.time(),
        session_id=session_id,
    )


def _store() -> MemoryStore:
    return MemoryStore(backend=FileBackend(), effect_tracker=EffectTracker())


def test_layers_whitelist_returns_only_listed_layers() -> None:
    """白名单只返所列层：L0 / L4 命中查询也不出现。"""
    store = _store()
    store.write("L0", _entry("l0", "L0", content="alpha 人格"))
    store.write("L2", _entry("l2", "L2", content="alpha 事实"))
    store.write("L4", _entry("l4", "L4", content="alpha 归档"))

    assert [e.id for e in store.read("alpha", budget=4096, layers=("L2",))] == ["l2"]


def test_layers_filter_precedes_ranking_and_budget() -> None:
    """层过滤先于排名与预算：L0（层权重最高）被滤后不吃预算、不被复用强化。"""
    backend = FileBackend()
    store = MemoryStore(backend=backend, effect_tracker=EffectTracker())
    store.write("L0", _entry("l0", "L0", content="alpha 人格"))
    store.write("L2", _entry("l2", "L2", content="alpha 事实"))

    assert [e.id for e in store.read("alpha", budget=20, layers=("L2",))] == ["l2"]
    assert backend.get("L0", "l0").reuse_count == 0, "被层过滤的条目 SHALL NOT 被复用强化"
    # 另一份同样的库、无过滤 ⇒ 层权重 1.0 的 L0 排在 L2 之前（对照：白名单确实改变了候选集）。
    control = MemoryStore(backend=FileBackend(), effect_tracker=EffectTracker())
    control.write("L0", _entry("l0", "L0", content="alpha 人格"))
    control.write("L2", _entry("l2", "L2", content="alpha 事实"))
    assert [e.id for e in control.read("alpha", budget=20)][0] == "l0"


def test_layers_default_does_not_filter() -> None:
    """缺省（或空元组）不过滤：三层都可出现（与既往逐字一致）。"""
    store = _store()
    store.write("L0", _entry("l0", "L0", content="alpha 人格"))
    store.write("L2", _entry("l2", "L2", content="alpha 事实"))
    store.write("L4", _entry("l4", "L4", content="alpha 归档"))

    ids = {e.id for e in store.read("alpha", budget=4096)}
    assert ids == {"l0", "l2", "l4"}
    assert {e.id for e in store.read("alpha", budget=4096, layers=())} == ids


def test_layers_compose_with_source_and_session_filters() -> None:
    """层白名单与来源排除 / 会话过滤叠加生效。"""
    store = _store()
    store.write("L2", _entry("keep", "L2", content="alpha 事实"))
    store.write("L2", _entry("sealed", "L2", content="alpha 神兽", source="beast.other"))
    store.write("L2", _entry("other-session", "L2", content="alpha 他会话", session_id="s2"))
    store.write("L4", _entry("archived", "L4", content="alpha 归档"))

    ids = [
        e.id
        for e in store.read(
            "alpha",
            budget=4096,
            layers=("L2",),
            exclude_source_prefixes=("beast.",),
            session_id="s1",
        )
    ]
    assert ids == ["keep"]
