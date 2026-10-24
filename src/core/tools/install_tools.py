"""插件安装工具（tool-use install/uninstall/list）。

M3：让 Agent 可经对话/工具调用通道安装、卸载、列出插件；复用 plugin-registry
的 PluginInstaller 统一安装生命周期（discover→verify→install→register→
activate→deactivate→uninstall），经 SafetyGate 副作用校验约束，危险操作走审批。

对应规格：doc/openspec/specs/tool-use/spec.md「插件安装工具」
"""

from __future__ import annotations

from typing import Any, cast

from core.plugin_registry import PluginInstaller, PluginKind, PluginSource

from .models import ToolDef
from .tool import Tool

_INSTALL_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "kind": {"type": "string"},
        "name": {"type": "string"},
    },
    "required": ["source"],
}

_UNINSTALL_SCHEMA = {
    "type": "object",
    "properties": {"plugin_id": {"type": "string"}},
    "required": ["plugin_id"],
}

_LIST_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


class StubPlugin:
    """满足 Plugin 结构契约的最小安装载体（MVP：manifest 物化为插件）。

    供安装账本（PluginInstaller._assets）登记使用，无需承载真实业务逻辑；
    ``load``/``unload``/``check`` 为 no-op，卸载时经注册表释放即可。
    """

    def __init__(self, plugin_id: str, manifest: dict[str, Any]) -> None:
        self.plugin_id = plugin_id
        self.generation = int(manifest.get("generation", 1))
        self.schema: dict[str, Any] = manifest.get("schema") or {"type": "object"}
        self.coeffects = cast(list[str], manifest.get("coeffects") or [])

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def check(self) -> bool:
        return True


def install_tool(installer: PluginInstaller | None = None) -> Tool:
    """install 工具：经 discover→verify→install→register→activate 安装插件。"""
    inst = installer if installer is not None else PluginInstaller()

    def handler(source: str, kind: str = "skill", name: str = "") -> dict[str, str]:
        plugin_source = PluginSource(source)
        plugin_kind = PluginKind(kind)
        asset = inst.discover(plugin_source, name or source, plugin_kind)
        inst.verify(asset, str(asset.manifest.get("signature", "")))
        inst.install(asset)
        plugin_id = str(asset.manifest.get("plugin_id") or f"installed.{kind}.{name or source}")
        inst.register(asset, StubPlugin(plugin_id, asset.manifest))
        inst.activate(plugin_id)
        return {"installed": plugin_id, "kind": kind, "source": source}

    return Tool(
        definition=ToolDef(
            tool_id="tools.install",
            description="安装插件（来源发现、签名校验、安装、注册、激活）",
            schema=_INSTALL_SCHEMA,
            coeffects=["filesystem:write"],
            reversible=False,
        ),
        handler=handler,
    )


def uninstall_tool(installer: PluginInstaller | None = None) -> Tool:
    """uninstall 工具：经 deactivate→uninstall 卸载插件，清理无残留。"""
    inst = installer if installer is not None else PluginInstaller()

    def handler(plugin_id: str) -> dict[str, str]:
        inst.uninstall(plugin_id)
        return {"uninstalled": plugin_id}

    return Tool(
        definition=ToolDef(
            tool_id="tools.uninstall",
            description="卸载插件（停用并清理，无残留）",
            schema=_UNINSTALL_SCHEMA,
            coeffects=["filesystem:write"],
            reversible=False,
        ),
        handler=handler,
    )


_LIST_NOTE = (
    "本清单只含经插件安装面（tools.install）安装的插件；内置原子工具（如 tools.web_fetch / "
    "tools.code_run / 文件工具）与插件安装状态无关，始终按系统提示的「可用工具」可用。"
    "清单为空不代表没有可用工具。"
)


def list_tool(installer: PluginInstaller | None = None) -> Tool:
    """list 工具：列出已安装插件清单（不含内置原子工具；change 0316 明示口径）。"""
    inst = installer if installer is not None else PluginInstaller()

    def handler() -> dict[str, Any]:
        return {"installed": inst.installed(), "note": _LIST_NOTE}

    return Tool(
        definition=ToolDef(
            tool_id="tools.list",
            description="列出已安装插件清单（仅插件；不含内置原子工具，后者始终可用）",
            schema=_LIST_SCHEMA,
            coeffects=[],
            reversible=True,
        ),
        handler=handler,
    )
