"""会话注册表单元测试（change 0094：读透 + 写时合并 + path=None 内存 + 损坏降级）。"""

from __future__ import annotations

import json
from pathlib import Path

from core.ui import SessionRegistry


def _ids(registry: SessionRegistry) -> set[str]:
    return {str(entry["session_id"]) for entry in registry.list()}


def test_persisted_session_visible_to_new_instance(tmp_path: Path) -> None:
    """落盘注册表：重开实例仍认该会话（跨进程可见的基础）。"""
    path = tmp_path / "conversations.json"
    session_id = SessionRegistry(path=path).create("cli")

    reopened = SessionRegistry(path=path)

    assert reopened.exists(session_id)
    assert session_id in _ids(reopened)


def test_path_none_is_memory_only() -> None:
    """缺省 `path=None` ⇒ 纯内存（不落盘、他实例不可见），后向兼容既有语义。"""
    registry = SessionRegistry()
    session_id = registry.create("cli")

    assert registry.exists(session_id)
    assert SessionRegistry().exists(session_id) is False


def test_create_merges_without_clobbering_other_process(tmp_path: Path) -> None:
    """写时合并：两实例（模拟两进程）各自建会话，后写者不抹掉先写者条目。"""
    path = tmp_path / "conversations.json"
    first = SessionRegistry(path=path)
    session_a = first.create("cli")
    second = SessionRegistry(path=path)
    session_b = second.create("web")

    assert _ids(SessionRegistry(path=path)) == {session_a, session_b}


def test_list_shape(tmp_path: Path) -> None:
    """枚举形状：`{session_id, mode, created_at}`。"""
    path = tmp_path / "conversations.json"
    session_id = SessionRegistry(path=path).create("cli")

    entries = SessionRegistry(path=path).list()

    assert len(entries) == 1
    assert entries[0]["session_id"] == session_id
    assert entries[0]["mode"] == "cli"
    assert isinstance(entries[0]["created_at"], (int, float))


def test_corrupt_file_starts_empty_and_recovers(tmp_path: Path) -> None:
    """派生状态损坏 ⇒ 空态启动（不阻断），后续 create 重写出合法文件。"""
    path = tmp_path / "conversations.json"
    path.write_text("{ not json", encoding="utf-8")

    registry = SessionRegistry(path=path)

    assert registry.list() == []
    assert registry.exists("anything") is False
    session_id = registry.create("cli")
    assert SessionRegistry(path=path).exists(session_id)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_exists_reads_through_to_late_writer(tmp_path: Path) -> None:
    """读透：长驻实例（装配早于晚写者）无需重建即可见新会话。"""
    path = tmp_path / "conversations.json"
    watcher = SessionRegistry(path=path)
    assert watcher.list() == []

    session_id = SessionRegistry(path=path).create("cli")

    assert watcher.exists(session_id)
    assert session_id in _ids(watcher)
