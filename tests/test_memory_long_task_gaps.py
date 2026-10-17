"""长任务记忆缺口（change 0230）：L2 软上限 + 记忆读预算估算器注入。

对应规格：doc/openspec/specs/memory/spec.md「L2 活跃层软上限」/
「记忆读预算的可注入估算器」。
"""

from __future__ import annotations

import time

from core.memory import MemoryEntry, MemoryStore

_DAY = 86400.0


class _FixedEstimator:
    """定值估算器：每条固定成本（change 0230 / G1）。"""

    def __init__(self, value: int) -> None:
        self.value = value

    def estimate(self, text: str) -> int:
        return self.value


def _entry(entry_id: str, *, age: float = 0.0, **overrides: object) -> MemoryEntry:
    fields: dict[str, object] = {
        "id": entry_id,
        "layer": "L2",
        "content": f"{entry_id} 内容",
        "tags": [],
        "source": "loop",
        "trace_id": "t",
        "ts": time.time() - age,
        "kind": "episodic",
    }
    fields.update(overrides)
    return MemoryEntry(**fields)  # type: ignore[arg-type]


def _layers(store: MemoryStore) -> dict[str, str]:
    return dict(store.index().entries)


# ---- G1：记忆读预算估算器 ----


def test_store_read_budget_uses_injected_estimator() -> None:
    store = MemoryStore(token_estimator=_FixedEstimator(100))
    for i in range(3):
        store.write("L2", _entry(f"m{i}"))

    hits = store.read("任意查询", budget=150)

    assert len(hits) == 1, "注入估算器：首条占 100，其余放不下"


def test_store_read_budget_default_unchanged() -> None:
    store = MemoryStore()
    for i in range(3):
        store.write("L2", _entry(f"m{i}"))

    hits = store.read("任意查询", budget=100)

    assert len(hits) == 3, "未注入 ⇒ 启发式成本极小，三条均保留"  # noqa: PLR2004


# ---- G5：L2 活跃层软上限 ----


def test_l2_soft_cap_archives_low_score_entries() -> None:
    store = MemoryStore(l2_soft_max_entries=2)
    for i in range(3):
        store.write("L2", _entry(f"old{i}", age=30 * _DAY))

    layers = _layers(store)
    active = [entry_id for entry_id, layer in layers.items() if layer == "L2"]
    assert len(active) <= 2, "超限 ⇒ 经遗忘路径归档至上限内"  # noqa: PLR2004
    assert any(layer == "L4" for layer in layers.values()), "归档走既有 L4 迁移"


def test_l2_soft_cap_evicts_oldest_when_forget_insufficient() -> None:
    store = MemoryStore(l2_soft_max_entries=2)
    store.write("L2", _entry("a", age=1000))
    store.write("L2", _entry("b", age=500))
    store.write("L2", _entry("c", age=0))

    layers = _layers(store)
    assert layers["a"] == "L4", "评分未达遗忘阈值 ⇒ 按 ts 最旧迁移"
    assert layers["b"] == "L2" and layers["c"] == "L2"


def test_l2_soft_cap_skips_non_forgettable_entries() -> None:
    store = MemoryStore(l2_soft_max_entries=1)
    store.write(
        "L2",
        _entry(
            "summary",
            age=30 * _DAY,
            source="compaction",
            kind="semantic",
            tags=["compaction"],
        ),
    )
    store.write("L2", _entry("episodic", age=30 * _DAY))

    layers = _layers(store)
    assert layers["summary"] == "L2", "摘要类条目不参与软上限归档"
    assert layers["episodic"] == "L4"


def test_l2_soft_cap_disabled_by_default() -> None:
    store = MemoryStore()
    for i in range(3):
        store.write("L2", _entry(f"m{i}", age=30 * _DAY))

    assert {layer for layer in _layers(store).values()} == {"L2"}, "未启用 ⇒ 行为不变"
