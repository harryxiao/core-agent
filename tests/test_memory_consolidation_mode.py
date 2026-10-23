"""巩固的可关闭性与水位语义（change 0307 / ADR-0297）。

SDD §5.3 硬要求「可关闭」在本仓缺位：摘要器在组合根无条件接线，停掉三个抽取器仍会产摘要并
迁移原条目。本文件钉住单一开关 + 配置三面 + 组合根接线，并把「L2 未迁移条目即持久队列、
迁移即水位」的口径落成用例（不引入独立队列文件）。
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path
from typing import Any, cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.memory import FileBackend, MemoryEntry, MemoryStore
from core.plugin_registry import EffectTracker
from core.runtime import build_runtime

_OLD_TS = time.time() - 10 * 365 * 86400  # 十年前：衰减评分必低于遗忘阈值

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _entry(entry_id: str = "e1", *, ts: float = 0.0) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=f"{entry_id} 内容",
        tags=[],
        source="loop",
        trace_id="t1",
        ts=ts,
        session_id="s1",
        kind="episodic",
    )


class _ScoreResult:
    def __init__(self) -> None:
        self.answers = {"score": {"score": 0.9}}


class _ScorerSpy:
    def __init__(self) -> None:
        self.calls = 0

    def score(self, state: dict[str, Any], entries: list[dict[str, Any]]) -> _ScoreResult:
        self.calls += 1
        return _ScoreResult()


class _Hooks:
    """摘要 / 关键事实 / 关系 / 情景归纳四路计数钩子。"""

    def __init__(self) -> None:
        self.summaries = 0
        self.key_facts = 0
        self.relations = 0
        self.episodics = 0

    def summarize(self, entries: list[MemoryEntry]) -> str:
        self.summaries += 1
        return "摘要：固定"

    def key_fact(self, entries: list[MemoryEntry]) -> list[Any]:
        self.key_facts += 1
        return []

    def relation(self, entries: list[MemoryEntry]) -> list[Any]:
        self.relations += 1
        return []

    def episodic(self, entries: list[MemoryEntry]) -> str:
        self.episodics += 1
        return ""


def _hooks_store(
    hooks: _Hooks, *, enabled: bool, tracker: EffectTracker | None = None
) -> MemoryStore:
    return MemoryStore(
        effect_tracker=tracker or EffectTracker(),
        compactor=_ScorerSpy(),
        summarizer=hooks.summarize,
        key_fact_extractor=hooks.key_fact,
        relation_extractor=hooks.relation,
        episodic_extractor=hooks.episodic,
        consolidation_enabled=enabled,
    )


# ---- 行为 ----


def test_off_mode_makes_compact_a_noop() -> None:
    """off ⇒ 评分 / 摘要 / 三类抽取零调用，无新条目、无迁移、无效应。"""
    tracker = EffectTracker()
    hooks = _Hooks()
    store = _hooks_store(hooks, enabled=False, tracker=tracker)
    store.write("L2", _entry())

    assert store.compact(session_id="s1") is None

    assert (hooks.summaries, hooks.key_facts, hooks.relations, hooks.episodics) == (0, 0, 0, 0)
    assert len(store.audit()) == 1  # 无新增条目
    [entry] = store.audit()
    assert entry.layer == "L2"
    assert tracker.audit("compaction.s1") == []


def test_default_mode_still_consolidates() -> None:
    """缺省 active ⇒ 正常摘要并迁移（与变更前一致）。"""
    hooks = _Hooks()
    store = MemoryStore(summarizer=hooks.summarize)
    store.write("L2", _entry())

    store.compact(session_id="s1")

    assert hooks.summaries == 1
    summary = next(e for e in store.audit() if e.id == "compaction.summary.s1")
    assert summary.layer == "L2"
    original = next(e for e in store.audit() if e.id == "e1")
    assert original.layer == "L4"


def test_off_mode_does_not_block_forget() -> None:
    """off 只停知识固化：遗忘归档照常。"""
    store = MemoryStore(consolidation_enabled=False)
    store.write("L2", _entry(ts=_OLD_TS))

    assert store.forget() == ["e1"]
    assert next(e for e in store.audit() if e.id == "e1").layer == "L4"


def test_failure_does_not_advance_watermark() -> None:
    """摘要器失败 ⇒ 条目留在 L2（水位不前进），重试成功后才迁移。"""
    calls = {"n": 0}

    def summary(entries: list[MemoryEntry]) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return "摘要：固定"

    store = MemoryStore(summarizer=summary)
    store.write("L2", _entry())

    with pytest.raises(RuntimeError):
        store.compact(session_id="s1")
    assert next(e for e in store.audit() if e.id == "e1").layer == "L2"

    store.compact(session_id="s1")
    assert next(e for e in store.audit() if e.id == "e1").layer == "L4"
    assert any(e.id == "compaction.summary.s1" for e in store.audit())


def test_queue_survives_restart(tmp_path: Path) -> None:
    """队列在 L2（memory.jsonl），新进程（新 store）仍能处理未巩固条目。"""
    path = tmp_path / "memory.jsonl"
    first = MemoryStore(backend=FileBackend(path), summarizer=lambda _entries: "摘要：固定")
    first.write("L2", _entry())

    restarted = MemoryStore(backend=FileBackend(path), summarizer=lambda _entries: "摘要：固定")
    restarted.compact(session_id="s1")

    assert next(e for e in restarted.audit() if e.id == "e1").layer == "L4"


# ---- 配置三面 ----


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


def test_spec_declares_consolidation_mode() -> None:
    spec = {spec.key: spec for spec in config_specs()}["memory.consolidation_mode"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--memory-consolidation-mode",
        "CORE_MEMORY_CONSOLIDATION_MODE",
        "active",
        "memory.consolidation_mode",
    )


def test_default_mode_is_active(tmp_path: Path) -> None:
    assert _manager(tmp_path).consolidation_mode() == "active"


def test_yaml_can_turn_consolidation_off(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "memory:\n  consolidation_mode: OFF\n")

    assert manager.consolidation_mode() == "off"


def test_env_overrides_yaml(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "memory:\n  consolidation_mode: active\n",
        environ={"CORE_MEMORY_CONSOLIDATION_MODE": "off"},
    )

    assert manager.consolidation_mode() == "off"


@pytest.mark.parametrize("raw", ["disable", "ong", "", "true", "1"])
def test_invalid_values_normalize_to_active(tmp_path: Path, raw: str) -> None:
    """非法取值 ⇒ active（保持变更前行为，不静默停用固化）。"""
    quoted = f'"{raw}"' if raw == "" else raw
    manager = _manager(tmp_path, f"memory:\n  consolidation_mode: {quoted}\n")

    assert manager.consolidation_mode() == "active"


def test_unknown_memory_key_does_not_warn(tmp_path: Path) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _manager(tmp_path, "memory:\n  consolidation_mode: off\n")

    assert [w for w in caught if "未知配置段" in str(w.message)] == []


# ---- 组合根接线 ----


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _memory(runtime: object) -> MemoryStore:
    return cast(MemoryStore, runtime.memory)  # type: ignore[attr-defined]


def test_build_runtime_default_wires_active(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert _memory(runtime)._consolidation_enabled is True  # noqa: SLF001 — 接线断言


def test_build_runtime_wires_off(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "memory:\n  consolidation_mode: off\n"))
    )

    assert _memory(runtime)._consolidation_enabled is False  # noqa: SLF001 — 接线断言
