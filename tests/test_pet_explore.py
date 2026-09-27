"""pet-explore 单元测试（只读优先、未授权阻断、清单可配置）。"""

from __future__ import annotations

import pytest

from core.pet_explore import Explorer


def test_available_returns_allowlist() -> None:
    assert set(Explorer().available()) == {"file.read", "memory.read", "web.search"}


def test_read_tool_runs() -> None:
    assert "file.read" in Explorer().run("file.read")


def test_unauthorized_tool_blocked() -> None:
    with pytest.raises(PermissionError):
        Explorer().run("file.write")


def test_allowlist_configurable() -> None:
    explorer = Explorer(allowlist=["memory.read"])
    assert explorer.available() == ["memory.read"]
    with pytest.raises(PermissionError):
        explorer.run("file.read")
