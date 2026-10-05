"""MCP 客户端（mcp）。

连接管理 / 工具发现 / 调用转发 / 心跳保活 / 断线重连 / 异常隔离。

- ``connect`` 失败抛 MCP_CONNECT_FAILED，协议不匹配抛 MCP_PROTOCOL_MISMATCH。
- ``call_tool`` 远端异常隔离：不向调用方抛裸异常，返回 CallResult 承载错误码。
- 心跳失效 / 连接断开时自动重连。
- ``add`` 按来源形状分流构建端点（``http(s)://`` URL → http；本地命令 → stdio）。
- 消费侧安全：stdio 传输经沙箱拉起子进程、http 传输经出站白名单
  （``build_transport`` 注入 ``sandbox``/``policy``，见 ADR-0057）。
- **标准 MCP 互操作**（change 0075 / 账本 B6）：``initialize`` 携标准三元组
  （``protocolVersion``/``capabilities``/``clientInfo``）；发现接口解析标准容器键
  （``{"tools": [...]}``）并**容忍厂商扩展字段**（只取已知键），同时兼容旧式**裸列表**；
  ``tools/call`` 的标准结果信封（``content`` + ``isError``）归一为本地
  :class:`~core.mcp.models.CallResult`。

对应接口：doc/03-interfaces/mcp-interface.md §3
"""

from __future__ import annotations

import json
import shlex
import uuid
from collections.abc import Callable
from typing import Any, cast

from core.permission import ResourceBudget, SandboxManager, SandboxPolicy
from core.plugin_registry import PluginSource

from .errors import MCPError, MCPErrorCode
from .models import (
    PROTOCOL_VERSION,
    CallResult,
    MCPEndpoint,
    RemotePrompt,
    RemoteResource,
    RemoteTool,
    ServerHandle,
    TransportKind,
)
from .transport import Transport, build_transport

_PLUGIN_ID = "mcp.client"
_GENERATION = 1
_DEFAULT_SCHEMA: dict[str, Any] = {"type": "object"}
_URL_PREFIXES = ("http://", "https://")
_HTTP_KINDS: tuple[TransportKind, ...] = ("http", "streamable-http")
_CLIENT_NAME = "core-agent"
_CLIENT_VERSION = "0.1"


def _handshake() -> dict[str, Any]:
    """标准 ``initialize`` 参数：对端逐字段校验，缺项即拒（实测 Claude Code 回 -32603）。"""
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": _CLIENT_NAME, "version": _CLIENT_VERSION},
    }


def _unwrap(raw: Any, key: str) -> list[dict[str, Any]]:
    """标准容器键（``{"tools": [...]}``）与旧式**裸列表**双认，非映射条目丢弃。"""
    items: Any = cast("dict[str, Any]", raw).get(key) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    return [
        cast("dict[str, Any]", item) for item in cast("list[Any]", items) if isinstance(item, dict)
    ]


def _schema(value: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {"type": "object"}


def _text_of(content: Any) -> str:
    """标准 ``content`` 文本块列表 → 文本（取首个 text 块，无则空串）。"""
    if not isinstance(content, list):
        return ""
    for block in cast("list[Any]", content):
        if not isinstance(block, dict):
            continue
        entry = cast("dict[str, Any]", block)
        if entry.get("type") == "text":
            return str(entry.get("text", ""))
    return ""


def _decode(text: str) -> Any:
    """文本 → 数据：合法 JSON 即解码，否则原样承载（对端可回纯文本）。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _parse_call_result(raw: Any) -> CallResult:
    """标准 ``tools/call`` 结果信封 → 本地 ``CallResult``（旧式裸形状原样承载）。"""
    if not isinstance(raw, dict) or ("content" not in raw and "isError" not in raw):
        return CallResult(ok=True, data=raw)
    payload = cast("dict[str, Any]", raw)
    text = _text_of(payload.get("content"))
    if payload.get("isError"):
        detail = _decode(text)
        if isinstance(detail, dict):
            fields = cast("dict[str, Any]", detail)
            code = fields.get("code")
            error = fields.get("error")
            if code is not None or error is not None:
                return CallResult(
                    ok=False,
                    code=None if code is None else str(code),
                    error=None if error is None else str(error),
                )
        return CallResult(ok=False, error=text)
    return CallResult(ok=True, data=_decode(text))


class MCPClient:
    """MCP 客户端插件：经可注入传输与远端 MCP 服务通信。"""

    plugin_id = _PLUGIN_ID
    generation = _GENERATION
    schema = _DEFAULT_SCHEMA
    coeffects: list[str] = []

    def __init__(
        self,
        transport_factory: Callable[[MCPEndpoint], Transport] | None = None,
        *,
        sandbox: SandboxManager | None = None,
        budget: ResourceBudget | None = None,
        policy: SandboxPolicy | None = None,
    ) -> None:
        self._transport_factory = transport_factory
        self._sandbox = sandbox
        self._budget = budget
        self._policy = policy
        self._transports: dict[str, Transport] = {}
        self._endpoints: dict[str, MCPEndpoint] = {}
        self._named: dict[str, ServerHandle] = {}
        self._sources: dict[str, PluginSource] = {}

    def load(self) -> None:
        return None

    def unload(self) -> None:
        for transport in self._transports.values():
            transport.close()
        self._transports.clear()
        self._endpoints.clear()
        self._named.clear()
        self._sources.clear()

    def check(self) -> bool:
        return True

    def connect(self, endpoint: MCPEndpoint, *, handle_id: str | None = None) -> ServerHandle:
        """连接端点并握手。

        ``handle_id`` 决定远端工具的本地命名（``mcp.<handle_id>.<工具>``）：**命名安装**
        （``add``）传安装名 ⇒ 工具名跨进程稳定（端点持久化的前提）；匿名连接缺省取随机 id。
        """
        transport = self._make_transport(endpoint)
        try:
            transport.connect(endpoint)
            info = transport.call("initialize", _handshake())
        except MCPError:
            transport.close()  # 失败不留半开连接（子进程 / socket 回收）
            raise
        except Exception as exc:  # noqa: BLE001
            transport.close()
            raise MCPError(MCPErrorCode.MCP_CONNECT_FAILED, f"连接失败: {exc}") from exc
        version = info.get("protocolVersion")
        if version != PROTOCOL_VERSION:
            transport.close()
            raise MCPError(MCPErrorCode.MCP_PROTOCOL_MISMATCH, f"协议版本不匹配: {version}")
        handle = ServerHandle(handle_id=handle_id or uuid.uuid4().hex, endpoint=endpoint)
        self._transports[handle.handle_id] = transport
        self._endpoints[handle.handle_id] = endpoint
        return handle

    def list_tools(self, handle: ServerHandle) -> list[RemoteTool]:
        """工具发现：标准容器键与裸列表双认；**只取已知键**（厂商扩展字段忽略）。"""
        raw = self._call(handle, "tools/list", {})
        return [
            RemoteTool(
                name=str(item.get("name", "")),
                description=str(item.get("description") or ""),
                inputSchema=_schema(item.get("inputSchema")),
            )
            for item in _unwrap(raw, "tools")
        ]

    def list_resources(self, handle: ServerHandle) -> list[RemoteResource]:
        raw = self._call(handle, "resources/list", {})
        return [
            RemoteResource(uri=str(item.get("uri", "")), name=str(item.get("name") or ""))
            for item in _unwrap(raw, "resources")
        ]

    def list_prompts(self, handle: ServerHandle) -> list[RemotePrompt]:
        raw = self._call(handle, "prompts/list", {})
        return [
            RemotePrompt(
                name=str(item.get("name", "")), description=str(item.get("description") or "")
            )
            for item in _unwrap(raw, "prompts")
        ]

    def call_tool(self, handle: ServerHandle, name: str, args: dict[str, Any]) -> CallResult:
        try:
            data = self._call(handle, "tools/call", {"name": name, "arguments": args})
        except MCPError as exc:
            return CallResult(ok=False, code=exc.code.value, error=exc.message)
        return _parse_call_result(data)

    def read_resource(self, handle: ServerHandle, uri: str) -> str:
        data = self._call(handle, "resources/read", {"uri": uri})
        return str(data["content"])

    def get_prompt(self, handle: ServerHandle, name: str, args: dict[str, Any]) -> str:
        data = self._call(handle, "prompts/get", {"name": name, "arguments": args})
        return str(data["text"])

    def heartbeat(self, handle: ServerHandle) -> bool:
        transport = self._transports.get(handle.handle_id)
        if transport is None:
            return False
        try:
            alive = transport.ping()
        except Exception:  # noqa: BLE001 — 探活异常视为心跳失效
            return False
        if alive:
            return True
        try:
            transport.connect(self._endpoints[handle.handle_id])
        except Exception:  # noqa: BLE001 — 重连失败即心跳失效
            return False
        return True

    def close(self, handle: ServerHandle) -> None:
        transport = self._transports.pop(handle.handle_id, None)
        if transport is not None:
            transport.close()

    def add(
        self,
        source: str,
        name: str,
        *,
        transport: TransportKind | None = None,
        command: str | None = None,
        args: list[str] | None = None,
    ) -> ServerHandle:
        """mcp add：按来源形状构建端点（PluginSource.MCP_ENDPOINT）并连接，按 name 登记。

        discover → verify → install → register 收敛为「构建端点 + 连接 + 登记」，
        之后进入现有连接管理（心跳 / 复用逻辑不改）。
        """
        endpoint = self._endpoint_for(source, transport=transport, command=command, args=args)
        # 同名重装先释放旧连接：handle_id 即安装名，就地覆盖会漏关子进程 / socket。
        self.remove(name)
        handle = self.connect(endpoint, handle_id=name)
        self._named[name] = handle
        self._sources[name] = PluginSource.MCP_ENDPOINT
        return handle

    @staticmethod
    def _endpoint_for(
        source: str,
        *,
        transport: TransportKind | None = None,
        command: str | None = None,
        args: list[str] | None = None,
    ) -> MCPEndpoint:
        """按来源形状分流：显式 transport/command 优先，否则 URL → http、命令行 → stdio。"""
        if transport in _HTTP_KINDS:
            return MCPEndpoint(transport=transport, url=source)
        if transport == "stdio" or command is not None:
            tokens = shlex.split(command if command is not None else source)
            return MCPEndpoint(
                transport="stdio",
                command=tokens[0] if tokens else "",
                args=[*tokens[1:], *(args or [])],
            )
        if source.startswith(_URL_PREFIXES):
            return MCPEndpoint(transport="http", url=source)
        tokens = shlex.split(source)
        return MCPEndpoint(transport="stdio", command=tokens[0] if tokens else "", args=tokens[1:])

    def remove(self, name: str) -> None:
        """mcp remove：停用并卸载该服务端，释放连接 / 会话 / socket 资源。"""
        handle = self._named.pop(name, None)
        self._sources.pop(name, None)
        if handle is not None:
            self.close(handle)

    def named(self, name: str) -> ServerHandle | None:
        """按安装名查已登记的服务句柄。"""
        return self._named.get(name)

    def _make_transport(self, endpoint: MCPEndpoint) -> Transport:
        if self._transport_factory is not None:
            return self._transport_factory(endpoint)
        return build_transport(
            endpoint, sandbox=self._sandbox, budget=self._budget, policy=self._policy
        )

    def _call(self, handle: ServerHandle, method: str, params: dict[str, Any]) -> Any:
        transport = self._transports.get(handle.handle_id)
        if transport is None:
            raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, "连接不存在")
        try:
            alive = transport.ping()
        except Exception as exc:  # noqa: BLE001 — 探活异常视为远端不可用
            raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, f"心跳失效: {exc}") from exc
        if not alive:
            try:
                transport.connect(self._endpoints[handle.handle_id])
            except Exception as exc:  # noqa: BLE001
                raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, f"重连失败: {exc}") from exc
        try:
            return transport.call(method, params)
        except MCPError:
            raise  # 传输层结构化错误码直通（不被兜底分支重包）
        except KeyError as exc:
            raise MCPError(MCPErrorCode.MCP_TOOL_NOT_FOUND, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, f"远端不可用: {exc}") from exc
