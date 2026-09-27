"""tool-use 插件安装工具单元测试（M3，契约 0028）。

覆盖：install 走 discover→verify→install→register→activate / uninstall 走
deactivate→卸载清理 / list 列出已装资产。
"""

from __future__ import annotations

from core.plugin_registry import PluginInstaller
from core.tools import install_tool, list_tool, uninstall_tool


def _installer() -> PluginInstaller:
    # 离线 resolver：不触真实网络/磁盘，manifest 由测试注入
    return PluginInstaller(source_resolver=lambda source, location: {})


def test_install_tool_registers_plugin() -> None:
    installer = _installer()
    tool = install_tool(installer)
    result = tool.handler(source="local-path", kind="skill", name="demo")
    assert result["installed"] == "installed.skill.demo"
    assert installer.installed() != []


def test_uninstall_tool_removes_plugin() -> None:
    installer = _installer()
    tool = install_tool(installer)
    tool.handler(source="local-path", kind="skill", name="demo")
    untool = uninstall_tool(installer)
    result = untool.handler("installed.skill.demo")
    assert result["uninstalled"] == "installed.skill.demo"
    assert installer.installed() == []


def test_list_tool_lists_installed() -> None:
    installer = _installer()
    tool = install_tool(installer)
    tool.handler(source="local-path", kind="skill", name="demo")
    ltool = list_tool(installer)
    result = ltool.handler()
    assert any(item["plugin_id"] == "installed.skill.demo" for item in result["installed"])
