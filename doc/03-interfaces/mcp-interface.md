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
    def read_resource(self, handle, uri: str) -> str: ...
    def get_prompt(self, handle, name: str, args: dict) -> str: ...
    def add(
        self, source: str, name: str, *,
        transport: TransportKind | None = None,
        command: str | None = None,
        args: list[str] | None = None,
    ) -> ServerHandle:
        """安装并连接 MCP server（复用 PluginSource(mcp-endpoint)），进入连接管理。

        按**来源形状分流**构建端点：显式 transport/command 优先；否则 `http(s)://` URL →
        http 端点，本地命令行（`shlex` 切分）→ stdio 端点。
        """
    def remove(self, name: str) -> None:
        """移除命名 server：关闭连接并释放资源（幂等）。"""
    def named(self, name: str) -> ServerHandle | None:
        """按名称查找已命名 server。"""
```

> 构造函数：`MCPClient(transport_factory=None, *, sandbox=None, budget=None, policy=None)`。
> `transport_factory` 供测试注入替身；`sandbox`/`budget`/`policy` 为**消费侧安全**注入面
> —— stdio 子进程经 `SandboxManager` 以资源配额拉起，http 出站经 `SandboxPolicy` 白名单校验
> （组合根装配，见 ADR-0057）。

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

## 3. Transport 抽象（传输层隔离）

传输层是 MCP 的三方依赖边界：底层 MCP SDK / JSON-RPC 传输实现收敛于单一 Transport 适配器，`MCPClient` / `MCPServer` 只依赖 Transport 抽象，替换 SDK 或传输实现零改动。

```python
class Transport(Protocol):
    def connect(self, endpoint: MCPEndpoint) -> None: ...
    def call(self, method: str, params: dict) -> Any: ...
    def close(self) -> None: ...
    def ping(self) -> bool: ...
```

生产实现由 `build_transport(endpoint, *, sandbox=None, budget=None, policy=None)` 按端点分派：

- **`StdioTransport`（stdlib 手写，零新依赖）**：MCP stdio 为**换行分帧** JSON-RPC。经
  `SandboxManager.spawn` 以资源配额拉起常驻子进程，后台读线程把 stdout 行解为消息入队，
  `call` 按 `id` 配对；超时取资源配额 `timeout_s` → `REMOTE_TIMEOUT`；`close` 终止并回收子进程。
- **`build_http_transport`（`mcp` SDK 懒加载）**：连接前经 `SandboxPolicy.check_outbound`
  校验 host（非白名单 → `PERMISSION_DENIED`）；`mcp` 未安装 → `MCP_CONNECT_FAILED` 并提示
  `pip install core-agent[mcp]`。**会话层（`Mcp-Session-Id` 复用 + SSE 分帧）待接入**。
- 未知 transport → `MCP_CONNECT_FAILED`。

> `StdioTransport` 为**同步**实现（`Transport` 契约为同步；`asyncio` 反需线程桥接）。
> 测试仍可经 `MCPClient(transport_factory=…)` 注入 `FakeTransport` 断线 / 超时 / 异常，不碰真实网络。

---

## 4. 适配器（远程工具 → ToolDef）

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

## 5. 调用流程（client）

```
ToolProvider.invoke(mcp.x.y, args)
  → MCPClient.call_tool(handle, name, args)
  → 远程执行
  → 返回结果 → EffectTracker.record（可逆则含 undo，否则标注 irreversible）
```

**wire 形状（标准 MCP，change `0075`）**：`initialize` 请求携带标准三元组
`protocolVersion` / `capabilities` / `clientInfo`；`tools/list` 解析标准容器键 `{"tools": [...]}`，
**只取已知键**（`name` / `description` / `inputSchema`）故**厂商扩展字段被忽略**；`tools/call` 的
标准结果 `{"content": [{"type": "text", "text": <JSON>}], "isError": <bool>}` **归一**为本地
`CallResult`（`isError` 为真 → `ok=False`；文本为合法 JSON 时解码，否则原样承载）。旧式**裸列表 /
裸对象**应答仍可解析（向后兼容既有 server）。

---

## 6. MCPServer 接口（server）

```python
class MCPServer(Plugin):
    plugin_id = "mcp.server"

    def serve(self, transport: Transport, endpoint: MCPEndpoint) -> ServerConnection: ...
    def serve_stdio(self, endpoint: MCPEndpoint, *, stdin=None, stdout=None) -> None: ...  # 事件循环（阻塞至 EOF）
    def initialize(self, conn: ServerConnection) -> ServerCapabilities: ...
    def list_tools(self, conn) -> list[MCPTool]: ...        # 白名单过滤后的暴露面
    def call_tool(self, conn, name: str, args: dict) -> CallResult: ...  # 复用 ToolProvider.invoke
```

- **暴露面**：由白名单从 ToolProvider/PluginRegistry 挑选，包装为 MCP tool（`core.<tool>`）。
- **安全**：`call_tool` 复用 `ToolProvider.invoke` 同一链路，不绕过 permission/observability，来源标注 `external:<client_id>`。
- **多流复用**：streamable-http 下单一 HTTP(TCP) 连接经 `Mcp-Session-Id` 会话标识承载多个会话，请求按 Session-Id 分流互不串扰。

**stdio 事件循环与暴露面契约**（change `0073`，账本 B3）：

- **事件循环**：`serve_stdio` 以**换行分帧 JSON-RPC** 承载 stdin → stdout（日志走 stderr，否则污染对端分帧解析）。`initialize` 应答与 client 侧**同一** `protocolVersion`（共享常量 `core.mcp.models.PROTOCOL_VERSION`）；无 `id` 通知不应答；非 JSON 行跳过；**stdin EOF 即退出**。
- **错误分层**：协议层错误走 JSON-RPC `error`（`-32601` 方法未实现 / `-32603` 内部异常）；工具层结论走成功应答里的 `CallResult`（如 `PERMISSION_DENIED`）。**单条请求的异常隔离为该 `id` 的错误应答，不终止事件循环**（应答不可序列化同样降级）。
- **命名空间与白名单**：对外名一律 `core.<tool_id>`；白名单接受裸名与带前缀两种写法（照 `tools/list` 抄名字可用）；`call_tool` 只接受**已暴露**的名字；`mcp.*` 远程工具**不**对外暴露（禁止二级代理）。CLI 面经 `mcp serve --whitelist <逗号分隔工具名>` 声明。
- **wire 形状（标准 envelope，change `0075`，账本 B6）**：`tools/list` 应答 `{"tools": [...]}`、`tools/call` 应答 `{"content": [{"type": "text", "text": <JSON 载荷>}], "isError": <bool>}`、`initialize` 应答 `protocolVersion` / `capabilities` / `serverInfo` —— **双向对齐标准 MCP**（协议版本 `2024-11-05`）。**真机证据**：`claude mcp add` 挂载本 server 后 `claude mcp list` 报 `✔ Connected`（此前该形状被拒）；反向 `core-agent mcp add "claude mcp serve"` 成功并发现对端 **20 个**工具（此前 `-32603` 缺失握手参数）。

---

## 7. 端点注册表与 CLI 命令（change `0074`）

`mcp add` 的成果必须活过**一次性 CLI 进程**（每次调用都新建 installer / client），故端点落
`$CORE_STATE_DIR/mcp-endpoints.json`（同 `checkpoints.jsonl` / `pets.json` 的状态目录约定，**原子写**：
tmp + `os.replace`）。

```python
def mcp_endpoints_path() -> Path: ...                 # $CORE_STATE_DIR/mcp-endpoints.json
def default_endpoint_name(source: str, command: str | None = None) -> str: ...
                                                      # --name > URL 主机名 > 命令基名
@dataclass(frozen=True)
class EndpointRecord:
    name: str
    source: str
    transport: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list)
    def manifest(self) -> dict[str, Any]: ...         # 转 _install_mcp 的消费口径（单一解析点）
    def asset(self) -> InstallableAsset: ...          # kind=MCP, source=MCP_ENDPOINT

class MCPEndpointRegistry:
    def __init__(self, path: Path) -> None: ...
    def list(self) -> list[EndpointRecord]: ...       # 按名排序（读盘即最新，跨进程可见）
    def get(self, name: str) -> EndpointRecord | None: ...
    def add(self, record: EndpointRecord) -> None: ...  # 重名 → MCPError(ENDPOINT_NAME_CONFLICT)
    def remove(self, name: str) -> bool: ...
```

- **命令形状**：`mcp add <endpoint> [--name N] [--transport T] [--command C] [--args ...]`；
  `mcp remove <name>`；`mcp list`。
- **先连通验证再落盘**：`mcp add` 走既有安装管线（连接 + `initialize` 握手 + 适配注册），**连不上不持久化**
  —— 否则此后每次装配都徒劳重试一个打不通的端点。
- **`mcp remove` 对称**：先经安装管线卸载（释放连接 / 子进程），再删记录（失败不删记录）。
- **`mcp list` 不连接**：列表是配置面事实；工具面在装配后由 agent 的工具集呈现。
- **装配期注册**：组合根装配时读回注册表 → 经**同一安装管线**连接 → 远端工具注册进本地工具集，
  命名 `mcp.<端点名>.<工具>`（`handle_id` 取安装名 ⇒ **跨进程稳定**，非随机 id）。
- **降级口径**：单个端点不可达 **只 `warnings.warn` 跳过**，不阻断装配；注册表损坏 / 条目残缺同样
  告警跳过（不静默丢弃，也不阻断启动）。

---

## 8. 错误码

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
| `ENDPOINT_NAME_CONFLICT` | 端点名已存在（拒绝静默覆盖既有端点） |

---

## 9. 关联

- 模块：`02-modules/mcp.md`
- 工具契约：`tool-use-interface.md`
- MCP Server 模式方案：`07-mcp-server/mcp-server.md`
- 传输实现：`src/core/mcp/transport.py`（`StdioTransport` / `build_http_transport`）
- 决策：ADR-0043（SDK 依赖定位）、ADR-0057（stdio 生产实现 + 消费侧安全接线）
- 规格：`openspec/specs/mcp/spec.md`
