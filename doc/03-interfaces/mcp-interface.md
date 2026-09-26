# 接口设计：MCP 集成接口（MCP Interface）

> 横切 ｜ 对应规格 `mcp/spec.md` ｜ 模块 `02-modules/mcp.md`

---

## 1. MCPClient 接口

```python
class MCPClient(Plugin):
    plugin_id = "mcp.client"

    def connect(self, endpoint: MCPEndpoint) -> ServerHandle: ...
    def list_tools(self, handle) -> list[RemoteTool]: ...
    def list_resources(self, handle) -> list[RemoteResource]: ...
    def list_prompts(self, handle) -> list[RemotePrompt]: ...
    def call_tool(self, handle, name: str, args: dict) -> CallResult: ...
    def read_resource(self, handle, uri: str) -> bytes: ...
    def get_prompt(self, handle, name: str, args: dict) -> str: ...
    def add(self, source: str, name: str) -> ServerHandle:
        """安装并连接 MCP server（复用 PluginSource(mcp-endpoint)），进入连接管理。"""
    def remove(self, name: str) -> None:
        """移除命名 server：关闭连接并释放资源（幂等）。"""
    def named(self, name: str) -> ServerHandle | None:
        """按名称查找已命名 server。"""
```

---

## 2. 端点定义

```python
@dataclass
class MCPEndpoint:
    transport: Literal["stdio", "http", "streamable-http"]
    # stdio
    command: str | None = None       # "npx"
    args: list[str] | None = None    # ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    # http / streamable-http
    url: str | None = None
    headers: dict | None = None
    session_id: str | None = None    # Mcp-Session-Id（streamable-http 单连接多会话复用）
```

---

## 3. 适配器（远程工具 → ToolDef）

```python
class MCPToolAdapter:
    def adapt(self, remote: RemoteTool, handle: ServerHandle) -> ToolDef:
        """把远程工具包装为符合四要素契约的 ToolDef：
        - tool_id = "mcp.<server>.<tool>"
        - schema = remote.inputSchema
        - coeffects = ["network:outbound", ...]
        - reversible 按远程工具元数据推断，默认 False → 走确认门
        """
```

---

## 4. 调用流程（client）

```
ToolProvider.invoke(mcp.x.y, args)
  → MCPClient.call_tool(handle, name, args)
  → 远程执行
  → 返回结果 → EffectTracker.record（可逆则含 undo，否则标注 irreversible）
```

---

## 5. MCPServer 接口（server）

```python
class MCPServer(Plugin):
    plugin_id = "mcp.server"

    def serve(self, transport: Literal["stdio", "http", "streamable-http"], endpoint: MCPEndpoint) -> None: ...
    def initialize(self, conn: ServerConnection) -> ServerCapabilities: ...
    def list_tools(self, conn) -> list[MCPTool]: ...        # 白名单过滤后的暴露面
    def call_tool(self, conn, name: str, args: dict) -> CallResult: ...  # 复用 ToolProvider.invoke
```

- **暴露面**：由白名单从 ToolProvider/PluginRegistry 挑选，包装为 MCP tool（`core.<tool>`）。
- **安全**：`call_tool` 复用 `ToolProvider.invoke` 同一链路，不绕过 permission/observability，来源标注 `external:<client_id>`。
- **多流复用**：streamable-http 下单一 HTTP(TCP) 连接经 `Mcp-Session-Id` 会话标识承载多个会话，请求按 Session-Id 分流互不串扰。

---

## 6. 错误码

| code | 含义 |
|---|---|
| `MCP_CONNECT_FAILED` | 连接失败 |
| `MCP_PROTOCOL_MISMATCH` | 协议/版本不兼容 |
| `MCP_TOOL_NOT_FOUND` | 远程工具不存在 |
| `REMOTE_TIMEOUT` | 远程超时 |
| `REMOTE_IRREVERSIBLE` | 远程不可逆操作需确认 |
| `PERMISSION_DENIED` | 外部调用未授权工具（server 侧越权） |
| `MCP_UNAVAILABLE` | MCP 服务端不可用（熔断） |
| `TOOL_NAME_CONFLICT` | 远程工具与本地工具重名 |

---

## 7. 关联

- 模块：`02-modules/mcp.md`
- 工具契约：`tool-use-interface.md`
- MCP Server 模式方案：`07-mcp-server/mcp-server.md`
- 规格：`openspec/specs/mcp/spec.md`
