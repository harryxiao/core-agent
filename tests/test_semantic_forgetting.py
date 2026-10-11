"""语义遗忘面（change 0204 / ADR-0194 / 台账 E141）单元 + 配置测试。

覆盖：缺省关 ⇒ 派生事实（`source ∈ {extraction, relation}`）不被遗忘（**零回归锚**）；
开启 ⇒ 派生事实参与**同一**衰减归档（可逆）；摘要类（`source ∈ {compaction, context}`）与
L0/L3 恒豁免；反证（同一陈旧条目随开关翻转结局）；配置 `memory.semantic_forgetting` 三面齐备 +
组合根接线。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.memory import Layer, MemoryEntry, MemoryStore
from core.memory.store import _FORGETTABLE_SEMANTIC_SOURCES
from core.plugin_registry import EffectTracker
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _semantic(entry_id: str, source: str) -> MemoryEntry:
    """一条 L2 semantic 条目（`source` 决定它落在豁免面还是遗忘面）。"""
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=f"{entry_id} 的正文",
        tags=[],
        source=source,
        trace_id="t",
        kind="semantic",
    )


def _entry(entry_id: str, layer: Layer, source: str = "loop") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,
        content=f"{entry_id} 的正文",
        tags=[],
        source=source,
        trace_id="t",
    )


def _aged(entry: MemoryEntry, days: float) -> MemoryEntry:
    entry.ts = time.time() - days * 86400.0
    return entry


def _write_config(tmp_path: Path, extra: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    return str(cfg)


def _manager(
    tmp_path: Path, extra: str = "", *, environ: dict[str, str] | None = None
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
    )
    manager.load()
    return manager


# ---- 遗忘面集合本身 ----


def test_forgettable_sources_are_the_derived_fact_sources() -> None:
    """遗忘面 = `{extraction, relation}`（评分豁免面 `{compaction, context}` 的**补集**）。"""
    assert frozenset({"extraction", "relation"}) == _FORGETTABLE_SEMANTIC_SOURCES


# ---- 缺省关：零回归 ----


def test_default_store_spares_stale_derived_facts() -> None:
    """缺省（不传 `semantic_forgetting`）⇒ 陈旧派生事实**仍留 L2**（与变更前逐字一致）。"""
    store = MemoryStore()
    store.write("L2", _aged(_semantic("keyfact.x", "extraction"), 30))
    store.write("L2", _aged(_semantic("relation.a--uses--b", "relation"), 30))

    assert store.forget() == []
    layers = dict(store.index().entries)
    assert layers["keyfact.x"] == "L2" and layers["relation.a--uses--b"] == "L2"


# ---- 开启：派生事实参与归档 ----


def test_enabled_forgets_stale_extraction_fact() -> None:
    store = MemoryStore(semantic_forgetting=True)
    store.write("L2", _aged(_semantic("keyfact.x", "extraction"), 30))

    assert store.forget() == ["keyfact.x"]
    assert dict(store.index().entries)["keyfact.x"] == "L4", "低分派生事实迁 L4 归档"
    assert "keyfact.x" in {e.id for e in store.audit()}, "归档条目仍可 audit 追溯"


def test_enabled_forgets_stale_relation_entry() -> None:
    store = MemoryStore(semantic_forgetting=True)
    store.write("L2", _aged(_semantic("relation.a--uses--b", "relation"), 30))

    assert store.forget() == ["relation.a--uses--b"]
    assert dict(store.index().entries)["relation.a--uses--b"] == "L4"


def test_enabled_spares_fresh_derived_fact() -> None:
    store = MemoryStore(semantic_forgetting=True)
    store.write("L2", _semantic("keyfact.fresh", "extraction"))

    assert store.forget() == []
    assert dict(store.index().entries)["keyfact.fresh"] == "L2"


def test_enabled_slows_reuse_for_derived_fact() -> None:
    """**判别性**：99 天陈旧 + `reuse_count=1` 的派生事实因复用调制越阈值而留存。"""
    store = MemoryStore(semantic_forgetting=True)
    reused = _aged(_semantic("keyfact.reused", "extraction"), 99)
    reused.reuse_count = 1
    store.write("L2", reused)

    assert store.forget() == [], "复用延缓衰减 ⇒ 派生事实亦越阈值留存"


# ---- 开启：摘要类与元策略恒豁免 ----


def test_enabled_spares_stale_summaries() -> None:
    """摘要类（`compaction`/`context`）是「已准入材料的骨架」⇒ **永久豁免**。"""
    store = MemoryStore(semantic_forgetting=True)
    store.write("L2", _aged(_semantic("compaction.summary.s1", "compaction"), 30))
    store.write("L2", _aged(_semantic("context.compact.x", "context"), 30))

    assert store.forget() == []
    layers = dict(store.index().entries)
    assert layers["compaction.summary.s1"] == "L2" and layers["context.compact.x"] == "L2"


def test_enabled_spares_l0_and_l3() -> None:
    store = MemoryStore(semantic_forgetting=True)
    store.write("L0", _aged(_entry("persona", "L0"), 30))
    store.write("L3", _aged(_entry("skill", "L3"), 30))

    assert store.forget() == []
    layers = dict(store.index().entries)
    assert layers["persona"] == "L0" and layers["skill"] == "L3"


# ---- 可逆 ----


def test_enabled_forgetting_is_reversible_by_trace() -> None:
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker, semantic_forgetting=True)
    store.write("L2", _aged(_semantic("keyfact.x", "extraction"), 30))

    assert store.forget() == ["keyfact.x"]
    assert dict(store.index().entries)["keyfact.x"] == "L4"

    report = tracker.rollback("forgetting.keyfact.x")

    assert report.undo_failed == []
    assert dict(store.index().entries)["keyfact.x"] == "L2", "按 trace 回滚 → 迁回原层"


# ---- 反证：同一陈旧条目随开关翻转结局 ----


def test_flag_flips_outcome_for_same_entry() -> None:
    """**反证锚**：同一陈旧派生事实，关 ⇒ 不归档；开 ⇒ 归档。必须显式翻转构造参。"""
    stale = _aged(_semantic("keyfact.x", "extraction"), 30)

    off = MemoryStore(semantic_forgetting=False)
    off.write("L2", stale)
    assert off.forget() == [], "关 ⇒ 不进遗忘面"

    on = MemoryStore(semantic_forgetting=True)
    on.write("L2", _aged(_semantic("keyfact.x", "extraction"), 30))
    assert on.forget() == ["keyfact.x"], "开 ⇒ 同一判据放行派生事实"


# ---- 配置面（ConfigSpec 单一真源） ----


def test_spec_declares_semantic_forgetting() -> None:
    spec = {spec.key: spec for spec in config_specs()}["memory.semantic_forgetting"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--memory-semantic-forgetting",
        "CORE_MEMORY_SEMANTIC_FORGETTING",
        False,
        "memory.semantic_forgetting",
    )


def test_config_default_is_off(tmp_path: Path) -> None:
    assert _manager(tmp_path).semantic_forgetting() is False


def test_config_yaml_enables(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "memory:\n  semantic_forgetting: true\n")

    assert manager.semantic_forgetting() is True


def test_config_env_overrides(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "", environ={"CORE_MEMORY_SEMANTIC_FORGETTING": "true"})

    assert manager.semantic_forgetting() is True


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _memory(runtime: object) -> MemoryStore:
    return cast(MemoryStore, runtime.memory)  # type: ignore[attr-defined]


def test_build_runtime_default_wires_semantic_forgetting_off(
    tmp_path: Path, state_dir: Path
) -> None:
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert _memory(runtime)._semantic_forgetting is False  # noqa: SLF001 — 接线断言


def test_build_runtime_wires_semantic_forgetting_when_enabled(
    tmp_path: Path, state_dir: Path
) -> None:
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "memory:\n  semantic_forgetting: true\n"))
    )

    assert _memory(runtime)._semantic_forgetting is True  # noqa: SLF001 — 接线断言
