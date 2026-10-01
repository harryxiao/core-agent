"""插件安装接线（plugins）。

把 ``PluginInstaller`` 的 resolve / install 两个钩子接到真实执行层，按
``PluginKind`` 分发：skill → ``SkillLibrary.register``；mcp → MCP 客户端
注册并适配进 ``ToolProvider``；cli → ``CLIAdapter`` 注册。组合根注入本
分发器，替换 ``installable.py`` 的空壳默认值。

对应接口：doc/03-interfaces/plugin-registry-interface.md §8
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.mcp import MCPClient, MCPToolAdapter, ServerHandle
from core.plugin_registry import (
    DomainError,
    ErrorCode,
    InstallableAsset,
    PluginKind,
    PluginSource,
)
from core.skills import Skill, SkillLibrary
from core.tools import Tool, ToolDef, ToolProvider

from .cli_adapter import CLIAdapter


class InstallDispatcher:
    """按 kind 分发的真实 resolver / installer（组合根注入 PluginInstaller）。"""

    def __init__(
        self,
        skill_library: SkillLibrary,
        tool_provider: ToolProvider,
        *,
        mcp_client: MCPClient | None = None,
        cli_adapter: CLIAdapter | None = None,
    ) -> None:
        self._skills = skill_library
        self._tools = tool_provider
        self._mcp = mcp_client if mcp_client is not None else MCPClient()
        self._adapter = MCPToolAdapter()
        self._cli = cli_adapter if cli_adapter is not None else CLIAdapter()

    def resolve(self, source: PluginSource, location: str) -> dict[str, Any]:
        """真实来源解析：LOCAL_PATH 读本地 manifest；外部源离线未接入。"""
        if source is PluginSource.LOCAL_PATH:
            path = Path(location)
            if not path.is_file():
                raise DomainError(ErrorCode.SOURCE_NOT_FOUND, f"来源不可达: {location}")
            return json.loads(path.read_text(encoding="utf-8"))
        raise DomainError(ErrorCode.SOURCE_NOT_FOUND, f"来源不可达（未接入 resolver）: {location}")

    def install(self, asset: InstallableAsset) -> None:
        """按 PluginKind 分发：skill / mcp / cli。"""
        if asset.kind is PluginKind.SKILL:
            self._install_skill(asset)
        elif asset.kind is PluginKind.MCP:
            self._install_mcp(asset)
        else:
            self._install_cli(asset)

    def _install_skill(self, asset: InstallableAsset) -> None:
        manifest = asset.manifest
        self._skills.register(
            Skill(
                skill_id=str(manifest.get("skill_id") or manifest.get("plugin_id") or ""),
                description=str(manifest.get("description") or ""),
                param_schema=manifest.get("param_schema") or {},
            )
        )

    def _install_mcp(self, asset: InstallableAsset) -> None:
        url = str(asset.manifest.get("url") or asset.manifest.get("endpoint") or "")
        name = str(asset.manifest.get("name") or "mcp")
        handle = self._mcp.add(url, name)
        for remote in self._mcp.list_tools(handle):
            definition = self._adapter.adapt(remote, handle)
            self._tools.register(self._remote_tool(definition, handle, remote.name))

    def _install_cli(self, asset: InstallableAsset) -> None:
        self._tools.register(self._cli.adapt(asset))

    def _remote_tool(self, definition: ToolDef, handle: ServerHandle, name: str) -> Tool:
        def handler(**kwargs: Any) -> Any:
            return self._mcp.call_tool(handle, name, dict(kwargs))

        return Tool(definition=definition, handler=handler)

    def uninstall(self, asset: InstallableAsset) -> None:
        """按 PluginKind 对称回退 install：skill 移除 / mcp 卸载工具并释放连接 / cli 卸载工具。"""
        if asset.kind is PluginKind.SKILL:
            self._uninstall_skill(asset)
        elif asset.kind is PluginKind.MCP:
            self._uninstall_mcp(asset)
        else:
            self._uninstall_cli(asset)

    def _uninstall_skill(self, asset: InstallableAsset) -> None:
        manifest = asset.manifest
        skill_id = str(manifest.get("skill_id") or manifest.get("plugin_id") or "")
        self._skills.remove(skill_id)

    def _uninstall_mcp(self, asset: InstallableAsset) -> None:
        name = str(asset.manifest.get("name") or "mcp")
        handle = self._mcp.named(name)
        if handle is not None:
            for remote in self._mcp.list_tools(handle):
                self._tools.unregister(self._adapter.tool_id(remote, handle))
        self._mcp.remove(name)

    def _uninstall_cli(self, asset: InstallableAsset) -> None:
        self._tools.unregister(self._cli.adapt(asset).definition.tool_id)
