"""冲突裁决的可见性与计数（change 0312 / SDD §5.5，只实现「新证据 > 旧证据」）。

钉住：取代裁决的指标计数、审计事件形状、统计口径（`superseded_by` 非空、与状态正交）、
`memory conflicts` 只读派生（成对 / 排序 / limit / 脱敏 / 历史链不依赖审计 / 零强化）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.entry import main
from core.memory import (
    REDACTED,
    FileBackend,
    KeyFact,
    MemoryAuditLog,
    MemoryEntry,
    MemoryStore,
    collect_stats,
)

_SECRET = "sk-abcdefgh12345678"

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _state(name: str) -> Path:
    return Path(os.environ["CORE_STATE_DIR"]) / name


def _write_config(tmp_path: Path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION, encoding="utf-8")
    return str(cfg)


def _episodic(entry_id: str, session_id: str = "s1") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content="事件",
        tags=["loop"],
        source="loop",
        session_id=session_id,
        kind="episodic",
        trace_id="t",
    )


def _store(
    holder: dict[str, list[KeyFact]],
    *,
    audit_log: MemoryAuditLog | None = None,
) -> MemoryStore:
    return MemoryStore(
        summarizer=lambda entries: "摘要：事实",
        key_fact_extractor=lambda entries: list(holder["facts"]),
        audit_log=audit_log,
    )


def _supersede_once(
    store: MemoryStore, holder: dict[str, list[KeyFact]], *, count: int = 2
) -> None:
    """让同一实体经历 `count` 次「取值变化」（首版 + (count-1) 次取代）。"""
    for index in range(count):
        holder["facts"] = [KeyFact(entity="部署环境", value=f"生产集群 {index}")]
        store.write("L2", _episodic(f"e{index}"))
        store.compact(session_id="s1")


def _versioned(
    entry_id: str,
    *,
    content: str,
    ts: float,
    status: str = "active",
    superseded_by: str = "",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=["key_fact"],
        source="extraction",
        trace_id="compaction.s1",
        ts=ts,
        kind="semantic",
        status=status,  # type: ignore[arg-type]
        superseded_by=superseded_by,
    )


def _seed_chain(store: MemoryStore) -> None:
    """两条冲突链：v1→v2（较旧）与 w1→w2（较新）。"""
    store.write(
        "L2",
        _versioned(
            "keyfact.部署环境",
            content="部署环境: A",
            ts=100.0,
            status="superseded",
            superseded_by="keyfact.部署环境.v2",
        ),
    )
    store.write("L2", _versioned("keyfact.部署环境.v2", content="部署环境: B", ts=200.0))
    store.write(
        "L2",
        _versioned(
            "keyfact.数据库",
            content="数据库: X",
            ts=300.0,
            status="superseded",
            superseded_by="keyfact.数据库.v2",
        ),
    )
    store.write("L2", _versioned("keyfact.数据库.v2", content="数据库: Y", ts=400.0))


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: MemoryStore, *argv: str) -> int:
    class _FakeRuntime:
        memory = store

    monkeypatch.setattr("core.entry.build_runtime", lambda *_a, **_kw: _FakeRuntime())
    return main(["--config", _write_config(tmp_path), "memory", *argv])


# ---- 计数与审计 ----


def test_supersede_increments_conflicts_metric() -> None:
    holder: dict[str, list[KeyFact]] = {"facts": []}
    store = _store(holder)

    _supersede_once(store, holder)

    assert store.metrics_snapshot()["memory.conflicts"] == 1


def test_same_value_refresh_does_not_count() -> None:
    holder: dict[str, list[KeyFact]] = {"facts": []}
    store = _store(holder)

    _supersede_once(store, holder)
    before = store.metrics_snapshot()["memory.conflicts"]
    holder["facts"] = [KeyFact(entity="部署环境", value="生产集群 1")]
    store.write("L2", _episodic("same"))
    store.compact(session_id="s1")

    assert store.metrics_snapshot()["memory.conflicts"] == before


def test_supersede_writes_conflict_audit_row(tmp_path: Path) -> None:
    audit = MemoryAuditLog(tmp_path / "audit.jsonl")
    holder: dict[str, list[KeyFact]] = {"facts": []}
    store = _store(holder, audit_log=audit)

    _supersede_once(store, holder)

    rows = [row for row in audit.read(None) if row["op"] == "conflict"]
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "keyfact.部署环境"
    assert row["target"] == "keyfact.部署环境.v2"
    assert row["reason"] == "newer_wins"
    assert row["trace_id"] == "compaction.s1"
    raw = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "生产集群" not in raw


def test_conflict_counted_without_audit_log() -> None:
    holder: dict[str, list[KeyFact]] = {"facts": []}
    store = _store(holder)

    _supersede_once(store, holder)

    assert store.metrics_snapshot()["memory.conflicts"] == 1
    assert [entry.status for entry in store.audit() if "key_fact" in entry.tags] == [
        "superseded",
        "active",
    ]


def test_conflict_counted_when_audit_fails(tmp_path: Path) -> None:
    unwritable = tmp_path / "audit-as-dir"
    unwritable.mkdir()
    holder: dict[str, list[KeyFact]] = {"facts": []}
    store = _store(holder, audit_log=MemoryAuditLog(unwritable))

    with pytest.warns(RuntimeWarning):
        _supersede_once(store, holder)

    assert store.metrics_snapshot()["memory.conflicts"] == 1


# ---- 统计口径 ----


def test_stats_conflicts_count_superseded_by() -> None:
    store = MemoryStore()
    _seed_chain(store)

    stats = collect_stats(store.audit(None), [])

    assert stats.conflicts == 2  # noqa: PLR2004 — 两条链各一次取代
    assert stats.entries_superseded == 2  # noqa: PLR2004 — 两条旧版仍在盘上


def test_stats_conflicts_orthogonal_to_retracted_status() -> None:
    store = MemoryStore()
    _seed_chain(store)
    store.retract("keyfact.部署环境")

    stats = collect_stats(store.audit(None), [])

    assert stats.conflicts == 2  # noqa: PLR2004 — 冲突数与当前状态正交
    assert stats.entries_superseded == 1
    assert stats.entries_retracted == 1


# ---- CLI：memory conflicts ----


def test_conflicts_text_pairs_and_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = MemoryStore()
    _seed_chain(store)
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "conflicts") == 0

    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 2  # noqa: PLR2004 — 两条冲突链
    first = lines[0]
    assert "entity=数据库" in first
    assert "old_id=keyfact.数据库" in first
    assert "new_id=keyfact.数据库.v2" in first
    assert "decision=newer_wins" in first
    assert "old_value=数据库: X" in first and "new_value=数据库: Y" in first
    assert "entity=部署环境" in lines[1]


def test_conflicts_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = MemoryStore()
    _seed_chain(store)
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "conflicts", "--limit", "1") == 0

    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 1
    assert "entity=数据库" in lines[0]


def test_conflicts_limit_zero_means_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = MemoryStore()
    _seed_chain(store)
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "conflicts", "--limit", "0") == 0

    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 2  # noqa: PLR2004 — limit=0 输出全部两条


def test_conflicts_json_fixed_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = MemoryStore()
    _seed_chain(store)
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "conflicts", "--json") == 0

    data = json.loads(capsys.readouterr().out)
    assert len(data) == 2  # noqa: PLR2004 — 两条冲突链
    assert set(data[0]) == {
        "entity",
        "old_id",
        "new_id",
        "old_ts",
        "new_ts",
        "decision",
        "old_value",
        "new_value",
    }
    assert data[0]["entity"] == "数据库"
    assert data[0]["decision"] == "newer_wins"


def test_conflicts_history_does_not_need_audit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = MemoryStore()  # 未接线审计 ⇒ 无 conflict 行
    _seed_chain(store)
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "conflicts", "--json") == 0

    data = json.loads(capsys.readouterr().out)
    assert {row["old_id"] for row in data} == {"keyfact.部署环境", "keyfact.数据库"}


def test_conflicts_empty_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, tmp_path, MemoryStore(), "conflicts") == 0

    assert "（无冲突记录）" in capsys.readouterr().out


def test_conflicts_zero_reinforcement_and_no_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = MemoryStore(backend=FileBackend(_state("memory.jsonl")))
    _seed_chain(store)
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "conflicts") == 0

    assert [entry.reuse_count for entry in store.audit(None)] == [0, 0, 0, 0]
    assert not _state("memory.audit.jsonl").exists()
    # 只读命令不得新增条目：四条种子仍在
    assert len(store.audit(None)) == 4  # noqa: PLR2004 — 四条种子仍在


def test_conflicts_redacts_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = MemoryStore()
    store.write(
        "L2",
        _versioned(
            "keyfact.凭据",
            content=f"凭据: {_SECRET}",
            ts=100.0,
            status="superseded",
            superseded_by="keyfact.凭据.v2",
        ),
    )
    store.write("L2", _versioned("keyfact.凭据.v2", content=f"凭据: {_SECRET}", ts=200.0))
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "conflicts") == 0

    out = capsys.readouterr().out
    assert _SECRET not in out
    assert REDACTED in out


def test_conflicts_entity_for_non_keyfact_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = MemoryStore()
    store.write(
        "L2",
        _versioned(
            "custom-old", content="旧", ts=100.0, status="superseded", superseded_by="custom-new"
        ),
    )
    store.write("L2", _versioned("custom-new", content="新", ts=200.0))
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "conflicts", "--json") == 0

    data = json.loads(capsys.readouterr().out)
    assert data[0]["entity"] == "custom-old"


def test_usage_lists_conflicts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class _FakeRuntime:
        memory = MemoryStore()

    monkeypatch.setattr("core.entry.build_runtime", lambda *_a, **_kw: _FakeRuntime())

    assert main(["--config", _write_config(tmp_path), "memory"]) == 1

    assert "conflicts" in capsys.readouterr().err
