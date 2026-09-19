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
```

---

## 2. 端点定义

```python
@dataclass
class MCPEndpoint:
    transport: Literal["stdio", "http"]
    # stdio
    command: str | None = None       # "npx"
    args: list[str] | None = None    # ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    # http
    url: str | None = None
    headers: dict | None = None
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

## 4. 调用流程

```
ToolProvider.invoke(mcp.x.y, args)
  → MCPClient.call_tool(handle, name, args)
  → 远程执行
  → 返回结果 → EffectTracker.record（可逆则含 undo，否则标注 irreversible）
```

---

## 5. 错误码

| code | 含义 |
|---|---|
| `MCP_CONNECT_FAILED` | 连接失败 |
| `MCP_PROTOCOL_MISMATCH` | 协议/版本不兼容 |
| `MCP_TOOL_NOT_FOUND` | 远程工具不存在 |
| `REMOTE_TIMEOUT` | 远程超时 |
| `REMOTE_IRREVERSIBLE` | 远程不可逆操作需确认 |

---

## 6. 关联

- 模块：`02-modules/mcp.md`
- 工具契约：`tool-interface.md`
- 规格：`openspec/specs/mcp/spec.md`
