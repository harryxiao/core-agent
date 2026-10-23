"""`memory audit` / `memory export`（change 0308 / ADR-0298）。

钉住：导出必须 `--yes` 显式确认、内容脱敏、jsonl/json 两格式与 0600 文件权限、
导出留审计痕、审计只读面按尾部 limit 展示。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from core.entry import main
from core.memory import FileBackend, MemoryAuditLog, MemoryEntry, MemoryStore

_SECRET = "sk-abcdefgh12345678"
_MODE_0600 = 0o600

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


def _entry(entry_id: str, *, layer: str = "L2", content: str = "内容") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,  # type: ignore[arg-type] — 测试内层字面量合法
        content=content,
        tags=[],
        source="test",
        trace_id="t1",
        ts=1_700_000_000.0,
        session_id="s1",
        importance=0.4,
        kind="semantic",
    )


def _seed_memory(*entries: MemoryEntry) -> MemoryStore:
    store = MemoryStore(
        backend=FileBackend(_state("memory.jsonl")),
        audit_log=MemoryAuditLog(_state("memory.audit.jsonl")),
    )
    for entry in entries:
        store.write(entry.layer, entry)
    return store


def _run_memory_cli(monkeypatch, tmp_path: Path, store: MemoryStore, *argv: str) -> int:
    class _FakeRuntime:
        memory = store

    monkeypatch.setattr("core.entry.build_runtime", lambda *a, **kw: _FakeRuntime())
    return main(["--config", _write_config(tmp_path), "memory", *argv])


def _audit_records() -> list[dict[str, Any]]:
    return MemoryAuditLog(_state("memory.audit.jsonl")).read(None)


def test_export_requires_explicit_yes(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """缺 `--yes` ⇒ 退出 1、stdout 为空、不落文件、不留导出审计。"""
    store = _seed_memory(_entry("e1"))

    assert _run_memory_cli(monkeypatch, tmp_path, store, "export", "--out", "out.jsonl") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "确认" in captured.err
    assert not (tmp_path / "out.jsonl").exists()
    assert [r["op"] for r in _audit_records()] == ["write"]


def test_export_jsonl_redacts_and_audits(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """jsonl 导出：正文脱敏、全层快照、成功留 export 审计（target=-）。"""
    store = _seed_memory(
        _entry("e1", content=f"api key = {_SECRET}"),
        _entry("e2", layer="L4"),
    )

    assert _run_memory_cli(monkeypatch, tmp_path, store, "export", "--yes") == 0
    out = capsys.readouterr().out
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]

    assert [row["id"] for row in rows] == ["e1", "e2"]
    assert _SECRET not in out
    assert rows[0]["content"] == "api key = <redacted>"
    assert rows[0]["content_hash"] == store.audit(None)[0].content_hash
    event = _audit_records()[-1]
    assert (event["op"], event["count"], event["target"], event["format"]) == (
        "export",
        2,
        "-",
        "jsonl",
    )


def test_export_json_to_file_is_0600(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """json 文件导出：可解析、0600、打印目标路径；条目不被改动。"""
    store = _seed_memory(_entry("e1", content="正文"))
    target = tmp_path / "dump.json"

    assert (
        _run_memory_cli(
            monkeypatch,
            tmp_path,
            store,
            "export",
            "--format",
            "json",
            "--out",
            str(target),
            "--yes",
        )
        == 0
    )

    rows = json.loads(target.read_text(encoding="utf-8"))
    assert [row["id"] for row in rows] == ["e1"]
    assert target.stat().st_mode & 0o777 == _MODE_0600
    assert str(target) in capsys.readouterr().out
    assert [e.reuse_count for e in store.audit(None)] == [0]  # 导出不触发复用强化
    event = _audit_records()[-1]
    assert (event["op"], event["target"], event["format"]) == ("export", str(target), "json")


def test_memory_audit_prints_tail(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`memory audit --limit 1`：只打印文件尾部一行。"""
    store = _seed_memory(_entry("e1"), _entry("e2"))

    assert _run_memory_cli(monkeypatch, tmp_path, store, "audit", "--limit", "1") == 0
    out = capsys.readouterr().out

    assert "e2" in out
    assert "e1" not in out


def test_memory_audit_empty(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """无审计文件 ⇒ 明示无记录、退出 0。"""
    store = MemoryStore(backend=FileBackend(_state("memory.jsonl")))

    assert _run_memory_cli(monkeypatch, tmp_path, store, "audit") == 0
    assert "无审计记录" in capsys.readouterr().out
