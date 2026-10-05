"""MCP 互操作数据模型（mcp）。

端点 / 服务句柄 / 远端能力 / 调用结果 / 服务连接 等数据结构。

对应接口：doc/03-interfaces/mcp-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TransportKind = Literal["stdio", "http", "streamable-http"]

# 协议版本（client 与 server 共用：server 侧 initialize 应答须与 client 侧判定同源）
PROTOCOL_VERSION = "2024-11-05"


@dataclass
class MCPEndpoint:
    """MCP 服务端点：stdio（command+args）或 http（url+headers）。"""

    transport: TransportKind
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    session_id: str | None = None


@dataclass
class ServerHandle:
    """已连接服务句柄。"""

    handle_id: str
    endpoint: MCPEndpoint


@dataclass
class RemoteTool:
    """远端工具契约。"""

    name: str
    description: str
    inputSchema: dict[str, Any]  # noqa: N815 — JSON-RPC 字段名保持 camelCase


@dataclass
class RemoteResource:
    """远端资源。"""

    uri: str
    name: str


@dataclass
class RemotePrompt:
    """远端提示模板。"""

    name: str
    description: str


@dataclass
class CallResult:
    """调用结果：成功携数据 / 失败携结构化错误码（隔离，不抛裸异常）。"""

    ok: bool
    data: Any = None
    code: str | None = None
    error: str | None = None


@dataclass
class ServerCapabilities:
    """服务端能力清单。"""

    tools: list[str]
    resources: list[str]


@dataclass
class ServerConnection:
    """服务连接：单连接多会话经 session_id 分流。"""

    connection_id: str
    session_id: str | None
    client_id: str


@dataclass
class MCPTool:
    """服务端暴露的工具。"""

    name: str
    description: str
    inputSchema: dict[str, Any]  # noqa: N815 — JSON-RPC 字段名保持 camelCase
