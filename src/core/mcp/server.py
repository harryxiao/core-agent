"""MCP 服务端（mcp）。

把本地 :class:`~core.tools.ToolProvider` 以最小暴露面（默认只读类，白名单显式开放，
对外名带 ``core.`` 命名空间前缀）提供给远端；调用复用 ToolProvider.invoke 链路，
越权返回 PERMISSION_DENIED；单连接多会话经 session_id 分流。

stdio 方向的事件循环见 :meth:`MCPServer.serve_stdio`：换行分帧 JSON-RPC，逐条请求
隔离处理（单条异常不终止循环），stdin EOF 即退出。

对外应答为**标准 MCP wire 形状**（change 0075 / 账本 B6）：`initialize` 回
`protocolVersion`/`capabilities`/`serverInfo`；`tools/list` 回容器键 `{"tools": [...]}`；
`tools/call` 回结果信封 `{"content": [{"type": "text", "text": <JSON 载荷>}], "isError": bool}`
（成功载荷为工具数据，失败载荷为 `{"code": ..., "error": ...}`）—— 使第三方 MCP 客户端
（Claude Code / Cursor）可直接挂载。

对应接口：doc/03-interfaces/mcp-interface.md §5
"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import asdict
from typing import Any, TextIO, cast

from core.tools import ToolDef, ToolProvider

from .errors import MCPErrorCode
from .models import (
    PROTOCOL_VERSION,
    CallResult,
    MCPEndpoint,
    MCPTool,
    ServerCapabilities,
    ServerConnection,
)
from .transport import Transport

_PLUGIN_ID = "mcp.server"
_GENERATION = 1
_DEFAULT_SCHEMA: dict[str, Any] = {"type": "object"}

# 对外工具命名空间：本地 ``tools.*`` 与 client 侧 ``mcp.*`` 远程工具天然隔离
_NAMESPACE = "core."
_REMOTE_PREFIX = "mcp."
_SERVER_NAME = "core-agent"
_SERVER_VERSION = "0.1"

# JSON-RPC 协议层错误码（工具级失败走 CallResult.code，不回落到协议层）
_METHOD_NOT_FOUND = -32601
_INTERNAL_ERROR = -32603


class _MethodNotFoundError(Exception):
    """请求方法未实现：应答 -32601，不逃逸出事件循环。"""


def _bare_name(name: str) -> str:
    """归一工具名：去空白与 ``core.`` 前缀（白名单与调用名两种写法等价）。"""
    stripped = name.strip()
    return stripped[len(_NAMESPACE) :] if stripped.startswith(_NAMESPACE) else stripped


def _as_params(value: Any) -> dict[str, Any]:
    """JSON-RPC 参数归一为字典（缺失 / 非对象 → 空参数）。"""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _envelope(payload: Any, *, is_error: bool) -> dict[str, Any]:
    """标准 MCP `tools/call` 结果信封：`content` 文本块 + `isError`。

    载荷**总是** JSON 编码（即使已是字符串）—— 保证对端「解码即还原」的往返保真。
    """
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": is_error,
    }


class MCPServer:
    """MCP 服务端插件：本地工具以最小暴露面供远端调用。"""

    plugin_id = _PLUGIN_ID
    generation = _GENERATION
    schema = _DEFAULT_SCHEMA
    coeffects: list[str] = []

    def __init__(
        self, tool_provider: ToolProvider | None = None, whitelist: list[str] | None = None
    ) -> None:
        self._tool_provider = tool_provider
        # 白名单接受裸名与带 `core.` 前缀两种写法（照 tools/list 应答抄名字亦可用）
        self._whitelist = {_bare_name(name) for name in whitelist or [] if name.strip()}
        self._connections: dict[str, ServerConnection] = {}

    def load(self) -> None:
        return None

    def unload(self) -> None:
        self._connections.clear()

    def check(self) -> bool:
        return True

    def serve(self, transport: Transport, endpoint: MCPEndpoint) -> ServerConnection:
        """绑定传输并返回服务连接（http 方向事件循环待接入；stdio 见 serve_stdio）。"""
        return self._bind(endpoint)

    def serve_stdio(
        self, endpoint: MCPEndpoint, *, stdin: TextIO | None = None, stdout: TextIO | None = None
    ) -> None:
        """stdio 事件循环：stdin 逐行读 JSON-RPC，按 id 应答写 stdout，EOF 即退出。

        stdout 只写 JSON-RPC 帧（日志走 stderr），否则对端的换行分帧解析被污染。
        """
        connection = self._bind(endpoint)
        reader = stdin if stdin is not None else sys.stdin
        writer = stdout if stdout is not None else sys.stdout
        for line in reader:
            response = self._respond(connection, line)
            if response is None:
                continue
            writer.write(self._encode(response) + "\n")
            writer.flush()

    def route(self, session_id: str) -> ServerConnection | None:
        for connection in self._connections.values():
            if connection.session_id == session_id:
                return connection
        return None

    def initialize(self, connection: ServerConnection) -> ServerCapabilities:
        self._connections[connection.connection_id] = connection
        tools = self.list_tools(connection)
        return ServerCapabilities(tools=[t.name for t in tools], resources=[])

    def list_tools(self, connection: ServerConnection) -> list[MCPTool]:
        if self._tool_provider is None:
            return []
        exposed: list[MCPTool] = []
        for tool_def in self._tool_provider.active_tools():
            if tool_def.tool_id.startswith(_REMOTE_PREFIX):
                continue  # 禁止二级代理：client 侧已发现的远程工具不再对外暴露
            if self._whitelist:
                if tool_def.tool_id not in self._whitelist:
                    continue
            elif not self._is_readonly(tool_def):
                continue  # 默认最小暴露：只暴露只读类
            exposed.append(
                MCPTool(
                    name=f"{_NAMESPACE}{tool_def.tool_id}",
                    description=tool_def.description,
                    inputSchema=tool_def.schema,
                )
            )
        return exposed

    def call_tool(
        self, connection: ServerConnection, name: str, args: dict[str, Any]
    ) -> CallResult:
        exposed = {tool.name for tool in self.list_tools(connection)}
        if name not in exposed:
            return CallResult(
                ok=False, code=MCPErrorCode.PERMISSION_DENIED.value, error=f"未授权工具: {name}"
            )
        if self._tool_provider is None:
            return CallResult(
                ok=False, code=MCPErrorCode.MCP_UNAVAILABLE.value, error="无工具提供者"
            )
        result = self._tool_provider.invoke(
            _bare_name(name), args, trace_id=f"external:{connection.client_id}"
        )
        if result.ok:
            return CallResult(ok=True, data=result.data)
        code = result.error.code if result.error is not None else None
        error = result.error.message if result.error is not None else None
        return CallResult(ok=False, code=code, error=error)

    def _bind(self, endpoint: MCPEndpoint) -> ServerConnection:
        connection = ServerConnection(
            connection_id=uuid.uuid4().hex,
            session_id=endpoint.session_id,
            client_id=endpoint.session_id or "local",
        )
        self._connections[connection.connection_id] = connection
        return connection

    def _respond(  # noqa: PLR0911 — 每条早退对应一类不应答消息，展平比嵌套更清晰
        self, connection: ServerConnection, line: str
    ) -> dict[str, Any] | None:
        """单行消息 → 应答帧（None = 不应答：通知 / 空行 / 非 JSON / 非对象）。"""
        text = line.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None  # 非 JSON 行（对端日志等）忽略
        if not isinstance(parsed, dict):
            return None
        message = cast("dict[str, Any]", parsed)
        request_id = message.get("id")
        if request_id is None:
            return None  # 通知（notifications/initialized 等）不应答
        try:
            result = self._dispatch(connection, str(message.get("method")), message.get("params"))
        except _MethodNotFoundError as exc:
            return _error(request_id, _METHOD_NOT_FOUND, str(exc))
        except Exception as exc:  # noqa: BLE001 — 单条请求异常隔离为错误应答，循环继续
            return _error(request_id, _INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, connection: ServerConnection, method: str, params: Any) -> Any:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
            }
        if method == "tools/list":
            return {"tools": [asdict(tool) for tool in self.list_tools(connection)]}
        if method == "tools/call":
            return self._serialize_call(connection, _as_params(params))
        if method == "ping":
            return {}
        raise _MethodNotFoundError(f"未知方法: {method}")  # noqa: TRY003 — 需携请求上下文

    def _serialize_call(
        self, connection: ServerConnection, params: dict[str, Any]
    ) -> dict[str, Any]:
        """领域 `CallResult` → 标准结果信封（成功载荷为数据，失败载荷为结构错误）。"""
        result = self.call_tool(
            connection, str(params.get("name", "")), _as_params(params.get("arguments"))
        )
        if result.ok:
            return _envelope(result.data, is_error=False)
        return _envelope({"code": result.code, "error": result.error}, is_error=True)

    @staticmethod
    def _encode(response: dict[str, Any]) -> str:
        """应答编码：单条应答不可序列化时降级为错误应答，不终止事件循环。"""
        try:
            return json.dumps(response, ensure_ascii=False)
        except (TypeError, ValueError):
            return json.dumps(_error(response.get("id"), _INTERNAL_ERROR, "应答不可序列化"))

    def _is_readonly(self, tool_def: ToolDef) -> bool:
        return not any("write" in c for c in tool_def.coeffects)
