"""情景保留期（change 0309 / ADR-0299）。

钉住：保留期按 `layer/kind/status/ts` 判定、到期条目**墓碑化**（清正文 + retracted + L4）、
由 `forget()` 的维护节拍驱动、`0` 为 kill-switch、非法值不得静默关闭，以及墓碑不进入
压实材料 / L2 软上限计数。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.memory import FileBackend, MemoryAuditLog, MemoryEntry, MemoryStore
from core.plugin_registry import EffectTracker
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)

_DAY = 86400.0
_OLD = 200 * _DAY


def _entry(  # noqa: PLR0913 — 测试构造器按需覆盖字段
    entry_id: str,
    *,
    age: float = _OLD,
    kind: str = "episodic",
    layer: str = "L2",
    status: str = "active",
    content: str = "情景内容",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,  # type: ignore[arg-type] — 测试内层字面量合法
        content=content,
        tags=[],
        source="loop",
        trace_id="t1",
        ts=time.time() - age,
        session_id="s1",
        kind=kind,  # type: ignore[arg-type] — 测试内 kind 字面量合法
        status=status,  # type: ignore[arg-type] — 测试内状态字面量合法
    )


def _store(
    *,
    retention_days: int | None = None,
    tracker: EffectTracker | None = None,
    backend: FileBackend | None = None,
    l2_cap: int | None = None,
) -> MemoryStore:
    return MemoryStore(
        backend=backend or FileBackend(),
        effect_tracker=tracker or EffectTracker(),
        episodic_retention_days=retention_days,
        l2_soft_max_entries=l2_cap,
    )


def _by_id(store: MemoryStore, entry_id: str) -> MemoryEntry:
    return next(entry for entry in store.audit(None) if entry.id == entry_id)


# ---- 保留期判据 ----


def test_retention_default_off_for_direct_store() -> None:
    """直接构造（未注入）⇒ 保留期关闭：到期条目不墓碑化。"""
    store = _store()
    store.write("L2", _entry("old"))

    assert store.forget(threshold=0.0) == []
    entry = _by_id(store, "old")
    assert (entry.status, entry.content, entry.layer) == ("active", "情景内容", "L2")


def test_retention_tombstones_expired_episodic(tmp_path: Path) -> None:
    """到期 episodic ⇒ 迁 L4、清正文、retracted、返回 id、审计 reason=retention。"""
    audit = tmp_path / "audit.jsonl"
    store = MemoryStore(
        backend=FileBackend(),
        effect_tracker=EffectTracker(),
        episodic_retention_days=90,
        audit_log=MemoryAuditLog(audit),
    )
    store.write("L2", _entry("old"))

    assert store.forget() == ["old"]

    entry = _by_id(store, "old")
    assert entry.layer == "L4"
    assert entry.status == "retracted"
    assert entry.content == ""
    assert "retracted" in entry.tags
    rows = MemoryAuditLog(audit).read(None)
    assert [(row["op"], row["reason"]) for row in rows][-1] == ("delete", "retention")


def test_retention_keeps_fresh_entry() -> None:
    store = _store(retention_days=90)
    store.write("L2", _entry("fresh", age=10 * _DAY))

    assert store.forget() == []
    entry = _by_id(store, "fresh")
    assert (entry.status, entry.content, entry.layer) == ("active", "情景内容", "L2")


def test_retention_skips_unknown_timestamp() -> None:
    """`ts<=0` 不惩罚（沿用遗忘的同口径）。"""
    store = _store(retention_days=90)
    store.write("L2", _entry("unknown", age=0))
    _by_id(store, "unknown").ts = 0.0

    assert store.forget() == []
    assert _by_id(store, "unknown").status == "active"


def test_retention_skips_semantic() -> None:
    """摘要类/语义条目不受保留期影响（episodic 才是保留期对象）。"""
    store = _store(retention_days=90)
    store.write("L2", _entry("summary", kind="semantic", content="摘要"))

    assert store.forget() == []
    entry = _by_id(store, "summary")
    assert (entry.status, entry.content) == ("active", "摘要")


def test_retention_skips_non_active() -> None:
    store = _store(retention_days=90)
    store.write("L2", _entry("old"))
    _by_id(store, "old").status = "superseded"

    assert store.forget() == []
    assert _by_id(store, "old").content == "情景内容"
    # 非 active 条目同样不是压实材料 / 重抽材料（治理信封先于材料收集）。
    assert store._episodic_groups("s1") == {}  # type: ignore[reportPrivateUsage]  # noqa: SLF001
    assert store._material_for_session("s1") == []  # type: ignore[reportPrivateUsage]  # noqa: SLF001


def test_retention_and_decay_share_forget_return() -> None:
    """到期墓碑与衰减归档同一次 `forget()`：返回值合并，审计 reason 区分。"""
    store = _store(retention_days=90)
    store.write("L2", _entry("expired"))
    store.write("L2", _entry("decayed", age=_DAY))

    assert store.forget(threshold=10.0) == ["expired", "decayed"]

    assert _by_id(store, "expired").status == "retracted"
    decayed = _by_id(store, "decayed")
    assert decayed.status == "active"  # 衰减归档保留正文与 active 状态
    assert "forgotten" in decayed.tags and decayed.layer == "L4"


def test_retention_is_reversible() -> None:
    """回滚 `retract.<id>`：正文、状态与原层复原。"""
    tracker = EffectTracker()
    store = _store(retention_days=90, tracker=tracker)
    store.write("L2", _entry("old"))

    assert store.forget() == ["old"]
    report = tracker.rollback("retract.old")

    assert report.undo_failed == []
    entry = _by_id(store, "old")
    assert (entry.status, entry.content, entry.layer, "retracted" in entry.tags) == (
        "active",
        "情景内容",
        "L2",
        False,
    )


# ---- 压缩材料与容量 ----


def test_tombstone_not_in_compaction_material() -> None:
    store = _store(retention_days=90)
    store.write("L2", _entry("old"))
    store.write("L2", _entry("fresh", age=_DAY))
    store.forget()

    groups = store._episodic_groups("s1")  # type: ignore[reportPrivateUsage]  # noqa: SLF001
    assert [entry.id for entry in groups["s1"]] == ["fresh"]
    material = store._material_for_session("s1")  # type: ignore[reportPrivateUsage]  # noqa: SLF001
    assert [entry.id for entry in material] == ["fresh"]


def test_tombstone_does_not_count_toward_l2_cap() -> None:
    """L2 软上限只数 active：墓碑不占名额。"""
    store = _store(l2_cap=1)
    store.write("L2", _entry("old"))
    assert store.retract("old") is True

    store.write("L2", _entry("new", age=_DAY))

    assert _by_id(store, "new").layer == "L2"


# ---- 配置 ----


def _config(
    tmp_path: Path, extra: str = "", environ: dict[str, str] | None = None
) -> ConfigManager:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    return ConfigManager(
        yaml_path=str(cfg), environ={"OPENAI_API_KEY": "sk-test", **(environ or {})}
    )


def _loaded(tmp_path: Path, extra: str = "", environ: dict[str, str] | None = None) -> Any:
    manager = _config(tmp_path, extra, environ)
    manager.load()
    return manager


def test_spec_declares_retention_days() -> None:
    spec = {item.key: item for item in config_specs()}["memory.episodic_retention_days"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--memory-episodic-retention-days",
        "CORE_MEMORY_EPISODIC_RETENTION_DAYS",
        90,
        "memory.episodic_retention_days",
    )


def test_config_default_is_90(tmp_path: Path) -> None:
    assert _loaded(tmp_path).episodic_retention_days() == 90  # noqa: PLR2004


def test_config_yaml_and_env(tmp_path: Path) -> None:
    assert (
        _loaded(tmp_path, "memory:\n  episodic_retention_days: 30\n").episodic_retention_days()
        == 30  # noqa: PLR2004
    )
    manager = _loaded(
        tmp_path,
        "memory:\n  episodic_retention_days: 90\n",
        {"CORE_MEMORY_EPISODIC_RETENTION_DAYS": "7"},
    )
    assert manager.episodic_retention_days() == 7  # noqa: PLR2004


def test_config_zero_disables(tmp_path: Path) -> None:
    assert (
        _loaded(tmp_path, "memory:\n  episodic_retention_days: 0\n").episodic_retention_days() == 0
    )


@pytest.mark.parametrize("raw", ["-5", "true", "1.5", "abc"])
def test_config_invalid_normalizes_to_90(tmp_path: Path, raw: str) -> None:
    manager = _loaded(tmp_path, f"memory:\n  episodic_retention_days: {raw}\n")
    assert manager.episodic_retention_days() == 90  # noqa: PLR2004


def test_runtime_wires_retention_days(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))

    default = build_runtime(_config(tmp_path))
    assert cast(MemoryStore, default.memory)._episodic_retention_days == 90  # noqa: SLF001,PLR2004

    off = _config(tmp_path, "memory:\n  episodic_retention_days: 0\n")
    assert cast(MemoryStore, build_runtime(off).memory)._episodic_retention_days == 0  # noqa: SLF001
