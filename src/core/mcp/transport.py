"""MCP 传输抽象（mcp）。

:class:`Transport` 定义传输契约；生产 stdio/http 传输依赖 MCP SDK（未安装）
故以 ``build_transport`` 明确报错；测试注入 :class:`FakeTransport` 验证
连接 / 重连 / 心跳 / 异常隔离，不碰真实网络。

对应接口：doc/03-interfaces/mcp-interface.md §2
"""

from __future__ import annotations

from typing import Any, Protocol

from .errors import MCPError, MCPErrorCode
from .models import MCPEndpoint


class Transport(Protocol):
    """传输契约：连接 / 调用 / 心跳 / 关闭。"""

    def connect(self, endpoint: MCPEndpoint) -> None: ...

    def call(self, method: str, params: dict[str, Any]) -> Any: ...

    def ping(self) -> bool: ...

    def close(self) -> None: ...


class FakeTransport:
    """测试用内存传输：可注入工具 / 资源 / 提示与连接 / 调用故障。"""

    def __init__(
        self,
        *,
        fail_connect: bool = False,
        protocol_version: str = "2024-11-05",
    ) -> None:
        self.fail_connect = fail_connect
        self.protocol_version = protocol_version
        self.connected = False
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_methods: set[str] = set()
        self._tools: dict[str, dict[str, Any]] = {}
        self._resources: dict[str, dict[str, Any]] = {}
        self._prompts: dict[str, dict[str, Any]] = {}

    def add_tool(
        self,
        name: str,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema or {"type": "object"},
        }

    def add_resource(self, uri: str, name: str = "") -> None:
        self._resources[uri] = {"uri": uri, "name": name}

    def add_prompt(self, name: str, description: str = "") -> None:
        self._prompts[name] = {"name": name, "description": description}

    def connect(self, endpoint: MCPEndpoint) -> None:
        if self.fail_connect:
            raise OSError("connection refused")  # noqa: TRY003 — 模拟远端传输错误
        self.connected = True

    def call(self, method: str, params: dict[str, Any]) -> Any:  # noqa: C901, PLR0911
        self.calls.append((method, params))
        if method in self.fail_methods:
            raise OSError(f"{method} crashed")  # noqa: TRY003 — 模拟远端传输错误
        if method == "initialize":
            return {"protocolVersion": self.protocol_version}
        if method == "tools/list":
            return list(self._tools.values())
        if method == "tools/call":
            name = params.get("name")
            if name not in self._tools:
                raise KeyError(name)
            return {"result": f"ok:{name}", "args": params.get("arguments", {})}
        if method == "resources/list":
            return list(self._resources.values())
        if method == "resources/read":
            uri = params.get("uri")
            if uri not in self._resources:
                raise KeyError(uri)
            return {"content": f"res:{uri}"}
        if method == "prompts/list":
            return list(self._prompts.values())
        if method == "prompts/get":
            name = params.get("name")
            if name not in self._prompts:
                raise KeyError(name)
            return {"text": f"prompt:{name}"}
        raise ValueError(f"unknown method {method}")  # noqa: TRY003 — 模拟远端传输错误

    def ping(self) -> bool:
        return self.connected

    def close(self) -> None:
        self.connected = False


def build_transport(endpoint: MCPEndpoint) -> Transport:
    """生产 stdio/http 传输（懒 import MCP SDK，M2 接入）。

    当前离线环境未安装 MCP SDK，故明确报错；测试经 ``MCPClient(transport_factory=...)``
    注入 :class:`FakeTransport`。
    """
    raise MCPError(MCPErrorCode.MCP_CONNECT_FAILED, "生产传输需 MCP SDK（离线未安装）")
