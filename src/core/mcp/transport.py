"""MCP 传输抽象与生产实现（mcp）。

:class:`Transport` 定义传输契约；生产传输按端点分派（ADR-0043 / ADR-0057）：

- **stdio**：stdlib 手写 JSON-RPC（零新依赖），经 :class:`~core.permission.SandboxManager`
  以资源配额拉起常驻子进程（换行分帧 + 读线程 + 队列超时）。
- **http/streamable-http**：``mcp`` SDK 懒加载（可选 extra ``[mcp]``），连接前经网络出站
  白名单校验，SDK 缺失 / 会话未接入时给出结构化错误。

:class:`FakeTransport` 供测试注入，不碰真实进程 / 网络。

对应接口：doc/03-interfaces/mcp-interface.md §2
"""

from __future__ import annotations

import importlib.util
import json
import queue
import subprocess
import threading
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from core.permission import AccessControlError, ResourceBudget, SandboxManager, SandboxPolicy

from .errors import MCPError, MCPErrorCode
from .models import MCPEndpoint

# JSON-RPC 2.0 标准错误码 → 本地结构化码（`tools/call` 之外的方法）。
_JSONRPC_TO_LOCAL: dict[int, MCPErrorCode] = {
    -32700: MCPErrorCode.MCP_PROTOCOL_MISMATCH,  # Parse error
    -32600: MCPErrorCode.MCP_PROTOCOL_MISMATCH,  # Invalid Request
    -32601: MCPErrorCode.MCP_PROTOCOL_MISMATCH,  # Method not found
    -32602: MCPErrorCode.MCP_PROTOCOL_MISMATCH,  # Invalid params
    -32603: MCPErrorCode.MCP_UNAVAILABLE,  # Internal error
}


def map_remote_error(method: str, error: Any) -> MCPError:
    """把远端 JSON-RPC ``error`` 映射为本地结构化 :class:`MCPError`（账本 B8）。

    MCP 约定：工具**执行**失败走成功应答里的 ``isError`` 结果信封，故 ``tools/call`` 上出现
    JSON-RPC 错误即**调用本身被拒**（未知工具 / 非法参数）⇒ ``MCP_TOOL_NOT_FOUND``；其余方法
    按标准码映射（请求 / 方法层问题 → ``MCP_PROTOCOL_MISMATCH``，内部错与未知码 →
    ``MCP_UNAVAILABLE``）。
    原始远端码与消息保留在错误文本中。
    """
    if isinstance(error, dict):
        payload = cast("dict[str, Any]", error)
        code: Any = payload.get("code")
        message: Any = payload.get("message")
    else:
        code = None
        message = error
    if method == "tools/call":
        local = MCPErrorCode.MCP_TOOL_NOT_FOUND
    elif isinstance(code, int):
        local = _JSONRPC_TO_LOCAL.get(code, MCPErrorCode.MCP_UNAVAILABLE)
    else:
        local = MCPErrorCode.MCP_UNAVAILABLE
    return MCPError(local, f"远端错误: {code} {message}")


class Transport(Protocol):
    """传输契约：连接 / 调用 / 心跳 / 关闭。"""

    def connect(self, endpoint: MCPEndpoint) -> None: ...

    def call(self, method: str, params: dict[str, Any]) -> Any: ...

    def ping(self) -> bool: ...

    def close(self) -> None: ...


class FakeTransport:
    """测试用内存传输：可注入工具 / 资源 / 提示与连接 / 调用故障。

    「远端」的模型 ⇒ 应答为**标准 MCP wire 形状**（容器键 + `content`/`isError` 信封），
    与真实第三方服务端一致；旧式裸形状由 client 侧的后向解析兜底（见 change 0075）。
    """

    def __init__(
        self,
        *,
        fail_connect: bool = False,
        fail_ping: bool = False,
        protocol_version: str = "2024-11-05",
    ) -> None:
        self.fail_connect = fail_connect
        self.fail_ping = fail_ping
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
            return {"tools": list(self._tools.values())}
        if method == "tools/call":
            name = params.get("name")
            if name not in self._tools:
                raise KeyError(name)
            payload = json.dumps({"result": f"ok:{name}", "args": params.get("arguments", {})})
            return {"content": [{"type": "text", "text": payload}], "isError": False}
        if method == "resources/list":
            return {"resources": list(self._resources.values())}
        if method == "resources/read":
            uri = params.get("uri")
            if uri not in self._resources:
                raise KeyError(uri)
            return {"content": f"res:{uri}"}
        if method == "prompts/list":
            return {"prompts": list(self._prompts.values())}
        if method == "prompts/get":
            name = params.get("name")
            if name not in self._prompts:
                raise KeyError(name)
            return {"text": f"prompt:{name}"}
        raise ValueError(f"unknown method {method}")  # noqa: TRY003 — 模拟远端传输错误

    def ping(self) -> bool:
        if self.fail_ping:
            raise OSError("ping failed")  # noqa: TRY003 — 模拟探活传输错误
        return self.connected

    def close(self) -> None:
        self.connected = False


class StdioTransport:
    """本地 stdio 传输：stdlib 手写 JSON-RPC over 经沙箱拉起的常驻子进程。

    MCP stdio 为**换行分帧**（每行一条 JSON-RPC 消息）：请求写子进程 stdin，
    后台读线程把 stdout 行解为消息入队，``call`` 按 ``id`` 配对取出。
    超时取资源配额 ``timeout_s``，避免服务端挂起时永久阻塞模型循环。
    """

    def __init__(
        self,
        sandbox: SandboxManager | None = None,
        budget: ResourceBudget | None = None,
    ) -> None:
        self._sandbox = sandbox if sandbox is not None else SandboxManager()
        self._budget = budget if budget is not None else ResourceBudget()
        self._proc: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[dict[str, Any]] = queue.Queue()
        self._next_id = 0
        self._lock = threading.Lock()

    def connect(self, endpoint: MCPEndpoint) -> None:
        if not endpoint.command:
            raise MCPError(MCPErrorCode.MCP_CONNECT_FAILED, "stdio 端点缺少 command")
        self.close()
        cmd = [endpoint.command, *(endpoint.args or [])]
        self._proc = self._sandbox.spawn(cmd, budget=self._budget)
        threading.Thread(target=self._pump, name="mcp-stdio-reader", daemon=True).start()

    def _pump(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        while True:
            line = proc.stdout.readline()
            if not line:
                return
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # 非 JSON 行（服务端日志）忽略
            if isinstance(message, dict):
                self._responses.put(cast("dict[str, Any]", message))

    def call(self, method: str, params: dict[str, Any]) -> Any:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, "stdio 子进程不可用")
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            try:
                self._write(
                    {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
                )
            except OSError as exc:
                raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, f"stdio 写入失败: {exc}") from exc
        result = self._await(request_id, method)
        if method == "initialize":
            self._notify("notifications/initialized")  # MCP 握手第二步（无 id / 无响应）
        return result

    def _write(self, message: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, "stdio 子进程不可用")
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def _await(self, request_id: int, method: str) -> Any:
        while True:
            try:
                message = self._responses.get(timeout=self._budget.timeout_s)
            except queue.Empty as exc:
                raise MCPError(MCPErrorCode.REMOTE_TIMEOUT, f"{method} 无响应超时") from exc
            if message.get("id") != request_id:
                continue  # 串行化：非本请求的消息丢弃
            error = message.get("error")
            if error:
                raise map_remote_error(method, error)
            return message.get("result")

    def _notify(self, method: str) -> None:
        try:
            self._write({"jsonrpc": "2.0", "method": method})
        except MCPError:
            return  # 通知失败不影响握手结果

    def ping(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def build_http_transport(endpoint: MCPEndpoint, policy: SandboxPolicy | None = None) -> Transport:
    """远端 http/streamable-http 传输：出站白名单 → ``mcp`` SDK 懒加载（ADR-0043）。

    SDK 会话（``Mcp-Session-Id`` 复用 + SSE 分帧）待接入；本函数先落地**可离线验证**的
    两段：网络出站白名单校验（非白名单 host 以 ``PERMISSION_DENIED`` 拒绝）与 SDK 缺失
    时的清晰降级。
    """
    host = urlparse(endpoint.url or "").hostname or ""
    try:
        (policy if policy is not None else SandboxPolicy()).check_outbound(host)
    except AccessControlError as exc:
        raise MCPError(MCPErrorCode.PERMISSION_DENIED, str(exc)) from exc
    if importlib.util.find_spec("mcp") is None:
        raise MCPError(
            MCPErrorCode.MCP_CONNECT_FAILED,
            "连远程 MCP 需安装可选依赖：pip install core-agent[mcp]",
        )
    raise MCPError(
        MCPErrorCode.MCP_CONNECT_FAILED,
        "http/streamable-http 传输会话待接入（Mcp-Session-Id 复用）",
    )


def build_transport(
    endpoint: MCPEndpoint,
    *,
    sandbox: SandboxManager | None = None,
    budget: ResourceBudget | None = None,
    policy: SandboxPolicy | None = None,
) -> Transport:
    """按 ``endpoint.transport`` 分派生产传输（stdio → stdlib；http → SDK 懒加载）。"""
    if endpoint.transport == "stdio":
        return StdioTransport(sandbox=sandbox, budget=budget)
    if endpoint.transport in ("http", "streamable-http"):
        return build_http_transport(endpoint, policy)
    raise MCPError(MCPErrorCode.MCP_CONNECT_FAILED, f"未知传输类型: {endpoint.transport}")
