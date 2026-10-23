"""`memory stats` / `memory why`（change 0311 / P2-5）。

钉住：统计只读（零强化、零文件创建）、JSON 固定键与排序、文本可读；召回解释按 rank 序
输出分值、正文脱敏、诊断检索不强化。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.entry import main
from core.memory import REDACTED, FileBackend, MemoryAuditLog, MemoryEntry, MemoryStore

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


def _entry(
    entry_id: str,
    *,
    layer: str = "L2",
    content: str = "内容",
    kind: str = "semantic",
    status: str = "active",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,  # type: ignore[arg-type] — 测试内层字面量合法
        content=content,
        tags=[],
        source="test",
        trace_id=f"t.{entry_id}",
        ts=1_700_000_000.0,
        session_id="s1",
        importance=0.4,
        kind=kind,
        status=status,  # type: ignore[arg-type]
    )


def _seed(*entries: MemoryEntry) -> MemoryStore:
    store = MemoryStore(
        backend=FileBackend(_state("memory.jsonl")),
        audit_log=MemoryAuditLog(_state("memory.audit.jsonl")),
    )
    for entry in entries:
        store.write(entry.layer, entry)
    return store


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: MemoryStore, *argv: str) -> int:
    class _FakeRuntime:
        memory = store

    monkeypatch.setattr("core.entry.build_runtime", lambda *_a, **_kw: _FakeRuntime())
    return main(["--config", _write_config(tmp_path), "memory", *argv])


# ---- memory stats ----


def test_stats_json_counts_entries_and_audit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _seed(_entry("a", kind="episodic"), _entry("b", kind="semantic"))
    store.retract("b")
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "stats", "--json") == 0

    data = json.loads(capsys.readouterr().out)
    assert data["entries_total"] == 2  # noqa: PLR2004 — 两条种子条目
    assert data["entries_active"] == 1
    assert data["entries_retracted"] == 1
    assert data["by_layer"] == {"L2": 1}
    assert data["writes_by_kind"] == {"episodic": 1, "semantic": 1}
    assert data["deletes_by_reason"] == {"tombstone": 1}
    assert data["storage_bytes"] == _state("memory.jsonl").stat().st_size


def test_stats_json_fixed_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, tmp_path, MemoryStore(), "stats", "--json") == 0

    data = json.loads(capsys.readouterr().out)
    assert set(data) == {
        "storage_bytes",
        "entries_total",
        "entries_active",
        "entries_retracted",
        "entries_superseded",
        "entries_forgotten",
        "by_layer",
        "by_status",
        "content_bytes",
        "writes_by_kind",
        "deletes_by_reason",
        "forgets_by_reason",
        "exports",
    }


def test_stats_zero_reinforcement_and_no_new_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _seed(_entry("a", content="巡检 内存"))
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "stats", "--json") == 0

    assert [entry.reuse_count for entry in store.audit()] == [0]
    assert not _state("memory.metrics.jsonl").exists()


def test_stats_text_mode_is_line_oriented(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _seed(_entry("a", kind="episodic"))
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "stats") == 0

    out = capsys.readouterr().out
    assert "storage_bytes" in out
    assert "entries=" in out
    assert "layers=" in out
    assert "writes=" in out


# ---- memory why ----


def test_why_prints_stats_and_ranked_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _seed(
        _entry("a", content="巡检 内存 水位"),
        _entry("b", content="巡检 内存 水位 复核"),
    )
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "why", "巡检 内存") == 0

    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line]
    assert lines[0].startswith("matched=")
    assert "injected=2" in lines[0]
    assert lines[1].startswith("#1 ")
    assert lines[2].startswith("#2 ")
    assert "score=" in lines[1]


def test_why_is_zero_reinforcement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _seed(_entry("a", content="巡检 内存"))
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "why", "巡检 内存") == 0

    assert [entry.reuse_count for entry in store.audit()] == [0]


def test_why_redacts_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _seed(_entry("a", content=f"巡检 内存 密钥 {_SECRET}"))
    capsys.readouterr()

    assert _run(monkeypatch, tmp_path, store, "why", "巡检 内存") == 0

    out = capsys.readouterr().out
    assert _SECRET not in out
    assert REDACTED in out


def test_why_no_match_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, tmp_path, MemoryStore(), "why", "没有任何命中") == 0

    out = capsys.readouterr().out.strip()
    assert out.startswith("matched=0")
    assert "injected=0" in out


def test_why_budget_and_session_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _seed(_entry("a", content="巡检 内存 水位"))
    capsys.readouterr()

    assert (
        _run(monkeypatch, tmp_path, store, "why", "巡检 内存", "--budget", "8", "--session", "s1")
        == 0
    )

    out = capsys.readouterr().out
    assert "injected=1" in out


def test_usage_lists_new_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class _FakeRuntime:
        memory = MemoryStore()

    monkeypatch.setattr("core.entry.build_runtime", lambda *_a, **_kw: _FakeRuntime())

    assert main(["--config", _write_config(tmp_path), "memory"]) == 1

    usage = capsys.readouterr().err
    assert "stats" in usage
    assert "why" in usage
