"""MCP 互操作（mcp）：连接管理 + 工具发现 + 调用转发 + Server 模式。"""

from .adapter import MCPToolAdapter
from .client import MCPClient
from .errors import MCPError, MCPErrorCode
from .models import (
    CallResult,
    MCPEndpoint,
    MCPTool,
    RemotePrompt,
    RemoteResource,
    RemoteTool,
    ServerCapabilities,
    ServerConnection,
    ServerHandle,
)
from .server import MCPServer
from .transport import (
    FakeTransport,
    StdioTransport,
    Transport,
    build_http_transport,
    build_transport,
)

__all__ = [
    "CallResult",
    "FakeTransport",
    "MCPClient",
    "MCPEndpoint",
    "MCPError",
    "MCPErrorCode",
    "MCPServer",
    "MCPTool",
    "MCPToolAdapter",
    "RemotePrompt",
    "RemoteResource",
    "RemoteTool",
    "ServerCapabilities",
    "ServerConnection",
    "ServerHandle",
    "StdioTransport",
    "Transport",
    "build_http_transport",
    "build_transport",
]
