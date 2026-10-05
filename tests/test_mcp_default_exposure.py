"""MCP 默认暴露面收窄（change 0076 / 账本 B7）。

规格「工具暴露与白名单」场景「默认最小暴露」写「仅暴露只读类工具，写/删除/**敏感**工具默认不暴露」，
而旧判据 `_is_readonly`（coeffects 不含 `write`）把「敏感」漏掉 ⇒ 驱动子 loop 的 `tools.delegate`
（coeffects 为空）与有网络出站的 `tools.web_fetch` 默认即在暴露面内。

新判据：默认仅暴露**声明的 coeffect 集合为纯本地只读**（`⊆ {"filesystem:read"}`，未声明 coeffect
视为只读）的工具；含 写 / 进程派生 / 网络出站 / 委托驱动 等跨边界 coeffect 者默认不出。
"""

from __future__ import annotations

from core.mcp import MCPServer, ServerConnection
from core.plugin_registry import CoeffectResolver
from core.tools import Tool, ToolDef, ToolProvider


def _provider() -> ToolProvider:
    provider = ToolProvider(coeffect_resolver=CoeffectResolver())

    def _register(tool_id: str, coeffects: list[str]) -> None:
        provider.register(
            Tool(
                definition=ToolDef(
                    tool_id=tool_id,
                    description=tool_id,
                    schema={"type": "object"},
                    coeffects=coeffects,
                    reversible=False,
                ),
                handler=lambda **_: {"ok": True},
            )
        )

    _register("tools.file_read", ["filesystem:read"])  # 只读 → 默认出
    _register("tools.list", [])  # 未声明副作用 → 视为只读 → 默认出
    _register("tools.file_write", ["filesystem:write"])  # 写 → 不出
    _register("tools.code_run", ["process:spawn", "filesystem:write"])  # 进程派生 → 不出
    _register("tools.web_fetch", ["network:outbound"])  # 网络出站 → 不出
    _register("tools.delegate", ["agent:delegate"])  # 委托驱动 → 不出
    return provider


def _conn() -> ServerConnection:
    return ServerConnection(connection_id="c1", session_id="s1", client_id="ext")


def _names(server: MCPServer) -> set[str]:
    return {t.name for t in server.list_tools(_conn())}


def test_default_face_excludes_cross_boundary_tools() -> None:
    """默认面 = 纯本地只读（含未声明 coeffect），跨边界工具一律不出。"""
    assert _names(MCPServer(tool_provider=_provider())) == {
        "core.tools.file_read",
        "core.tools.list",
    }


def test_network_and_delegation_tools_are_not_default_exposed() -> None:
    """账本 B7 点名的两个工具：出网 / 驱动子 loop，默认即不可见。"""
    names = _names(MCPServer(tool_provider=_provider()))
    assert "core.tools.web_fetch" not in names
    assert "core.tools.delegate" not in names


def test_whitelist_still_overrides_default_face() -> None:
    """显式白名单照旧开放跨边界工具（收窄只改默认面，不改白名单语义）。"""
    server = MCPServer(tool_provider=_provider(), whitelist=["tools.web_fetch"])
    assert _names(server) == {"core.tools.web_fetch"}


def test_cross_boundary_call_denied_by_default() -> None:
    """默认面外的工具被调用 → PERMISSION_DENIED 且不执行。"""
    server = MCPServer(tool_provider=_provider())
    result = server.call_tool(_conn(), "core.tools.delegate", {"task": "x"})
    assert result.ok is False
    assert result.code == "PERMISSION_DENIED"
