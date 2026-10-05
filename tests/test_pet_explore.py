"""pet-explore 单元测试（只读优先、未授权阻断、清单可配置）。

默认清单已订正为**真实工具 id**（change 0081 / 账本 E25）：原清单
`file.read`/`memory.read`/`web.search` 与真实 id 不对应；
`available()` 现为受限 provider 的白名单真源。
"""

from __future__ import annotations

import pytest

from core.pet.explore import Explorer


def test_available_returns_allowlist() -> None:
    assert set(Explorer().available()) == {"tools.file_read"}


def test_read_tool_runs() -> None:
    assert "tools.file_read" in Explorer().run("tools.file_read")


def test_unauthorized_tool_blocked() -> None:
    with pytest.raises(PermissionError):
        Explorer().run("tools.file_write")


def test_allowlist_configurable() -> None:
    explorer = Explorer(allowlist=["tools.web_fetch"])
    assert explorer.available() == ["tools.web_fetch"]
    with pytest.raises(PermissionError):
        explorer.run("tools.file_read")
