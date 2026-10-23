"""记忆治理审计日志（change 0308 / ADR-0298）。

钉住：事件只含元数据、动作成功后追加、幂等/拒收不审计、删除/遗忘可追溯、
审计失败 fail-open（单次告警）、0600 与坏行容错、配置三面与组合根接线。
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.memory import FileBackend, MemoryAuditLog, MemoryEntry, MemoryStore
from core.runtime import build_runtime

_OLD_TS = time.time() - 10 * 365 * 86400  # 十年前：衰减评分必低于遗忘阈值
_SECRET = "sk-abcdefgh12345678"
_MODE_0600 = 0o600
_EXPORT_COUNT = 3
_MAX_TARGET = 512

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _entry(entry_id: str = "e1", *, content: str = "内容", ts: float = 0.0) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=[],
        source="loop",
        trace_id="t1",
        ts=ts,
        session_id="s1",
        importance=0.4,
        kind="episodic",
    )


def _audit(tmp_path: Path) -> MemoryAuditLog:
    return MemoryAuditLog(tmp_path / "state" / "memory.audit.jsonl")


def _store(tmp_path: Path, audit: MemoryAuditLog | None = None, **kwargs: object) -> MemoryStore:
    return MemoryStore(
        backend=FileBackend(tmp_path / "state" / "memory.jsonl"),
        audit_log=audit,
        **kwargs,
    )


def _records(audit: MemoryAuditLog) -> list[dict[str, object]]:
    return audit.read(None)


# ---- 事件面 ----


def test_write_appends_metadata_only(tmp_path: Path) -> None:
    """写入 ⇒ 一行元数据；正文与密钥明文绝不进审计文件。"""
    audit = _audit(tmp_path)
    store = _store(tmp_path, audit)

    assert store.write("L2", _entry(content=f"api key = {_SECRET}")) == "e1"

    records = _records(audit)
    assert [r["op"] for r in records] == ["write"]
    record = records[0]
    assert record["id"] == "e1"
    assert record["layer"] == "L2"
    assert record["kind"] == "episodic"
    assert record["source"] == "loop"
    assert record["session_id"] == "s1"
    assert record["trace_id"] == "t1"
    assert record["content_hash"]
    raw = audit.path.read_text(encoding="utf-8")
    assert _SECRET not in raw
    assert "api key" not in raw


def test_idempotent_replay_writes_no_audit(tmp_path: Path) -> None:
    """0306 快路径：同载荷重放零落盘 ⇒ 零审计。"""
    audit = _audit(tmp_path)
    store = _store(tmp_path, audit)

    assert store.write("L2", _entry()) == "e1"
    assert store.write("L2", _entry()) == "e1"

    assert [r["op"] for r in _records(audit)] == ["write"]


def test_importance_gate_rejection_writes_no_audit(tmp_path: Path) -> None:
    """闸门拒收无持久变化 ⇒ 零审计。"""
    audit = _audit(tmp_path)
    store = _store(tmp_path, audit, importance_scorer=lambda _entry: 0.1)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert store.write("L2", _entry()) is None

    assert _records(audit) == []


def test_delete_appends_audit(tmp_path: Path) -> None:
    """物理删除 ⇒ `delete` 事件。"""
    audit = _audit(tmp_path)
    store = _store(tmp_path, audit)
    store.write("L2", _entry())

    assert store.discard("e1") is True

    assert [r["op"] for r in _records(audit)] == ["write", "delete"]


def test_forget_appends_reason_and_hash(tmp_path: Path) -> None:
    """遗忘 ⇒ `forget` + reason=decay + 内容哈希；墓碑仍是 L4 + forgotten 标签。"""
    audit = _audit(tmp_path)
    store = _store(tmp_path, audit)
    entry = _entry(ts=_OLD_TS)
    store.write("L2", entry)

    assert store.forget() == ["e1"]

    forget = _records(audit)[-1]
    assert forget["op"] == "forget"
    assert forget["reason"] == "decay"
    assert forget["content_hash"] == entry.content_hash
    tombstone = next(e for e in store.audit(None) if e.id == "e1")
    assert tombstone.layer == "L4"
    assert "forgotten" in tombstone.tags


def test_audit_failure_does_not_block_write_and_warns_once(tmp_path: Path) -> None:
    """审计路径不可写 ⇒ 写入照常成功；多个事件只告警一次。"""
    audit = MemoryAuditLog(tmp_path)  # 路径是目录：O_APPEND 必失败
    store = _store(tmp_path, audit)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert store.write("L2", _entry("e1")) == "e1"
        assert store.write("L2", _entry("e2")) == "e2"

    assert [w for w in caught if issubclass(w.category, RuntimeWarning)] != []
    assert len([w for w in caught if issubclass(w.category, RuntimeWarning)]) == 1


def test_audit_file_mode_and_bad_line_tolerance(tmp_path: Path) -> None:
    """文件 0600；读取跳过坏行。"""
    audit = _audit(tmp_path)
    store = _store(tmp_path, audit)
    store.write("L2", _entry())

    assert audit.path.stat().st_mode & 0o777 == _MODE_0600
    with audit.path.open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")

    assert [r["op"] for r in _records(audit)] == ["write"]


def test_no_audit_log_means_no_file(tmp_path: Path) -> None:
    """未接线 ⇒ 不创建审计文件（既有直接构造方零变化）。"""
    store = _store(tmp_path)

    assert store.write("L2", _entry()) == "e1"
    assert not (tmp_path / "state" / "memory.audit.jsonl").exists()


def test_record_export_noop_without_audit(tmp_path: Path) -> None:
    """审计未接线时导出事件为 no-op。"""
    store = _store(tmp_path)

    store.record_export(count=1, target="-", format="jsonl")


def test_record_export_truncates_target(tmp_path: Path) -> None:
    """导出事件记录 count/target/format；超长 target 截断（行有界）。"""
    audit = _audit(tmp_path)
    store = _store(tmp_path, audit)

    store.record_export(count=_EXPORT_COUNT, target="x" * 2000, format="jsonl")

    record = _records(audit)[0]
    assert record["op"] == "export"
    assert record["count"] == _EXPORT_COUNT
    assert record["format"] == "jsonl"
    assert len(cast(str, record["target"])) <= _MAX_TARGET


# ---- 配置三面 ----


def _write_config(tmp_path: Path, extra: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    return str(cfg)


def _manager(
    tmp_path: Path,
    extra: str = "",
    *,
    environ: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    manager.load()
    return manager


def test_spec_declares_audit_log() -> None:
    spec = {spec.key: spec for spec in config_specs()}["memory.audit_log"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--memory-audit-log",
        "CORE_MEMORY_AUDIT_LOG",
        True,
        "memory.audit_log",
    )


def test_default_audit_log_is_enabled(tmp_path: Path) -> None:
    assert _manager(tmp_path).audit_log_enabled() is True


def test_yaml_can_disable_audit_log(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "memory:\n  audit_log: false\n")

    assert manager.audit_log_enabled() is False


def test_env_overrides_yaml(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "memory:\n  audit_log: true\n",
        environ={"CORE_MEMORY_AUDIT_LOG": "false"},
    )

    assert manager.audit_log_enabled() is False


def test_cli_overrides_env(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        environ={"CORE_MEMORY_AUDIT_LOG": "false"},
        cli={"memory.audit_log": True},
    )

    assert manager.audit_log_enabled() is True


@pytest.mark.parametrize("raw", ["disable", "ong", '""'])
def test_invalid_values_normalize_to_enabled(tmp_path: Path, raw: str) -> None:
    """集合外取值 ⇒ 开启（笔误不得静默关闭审计）。"""
    manager = _manager(tmp_path, f"memory:\n  audit_log: {raw}\n")

    assert manager.audit_log_enabled() is True


# ---- 组合根接线 ----


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _memory(runtime: object) -> MemoryStore:
    return cast(MemoryStore, runtime.memory)  # type: ignore[attr-defined]


def test_build_runtime_default_wires_audit(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    audit = _memory(runtime)._audit_log  # noqa: SLF001 — 接线断言
    assert audit is not None
    assert audit.path == state_dir / "memory.audit.jsonl"


def test_build_runtime_wires_audit_off(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "memory:\n  audit_log: false\n"))
    )

    assert _memory(runtime)._audit_log is None  # noqa: SLF001 — 接线断言
