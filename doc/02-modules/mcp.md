# 模块设计：MCP 集成（MCP Integration）

> 对应规格：`doc/openspec/specs/mcp/spec.md` ｜ 接口：`doc/03-interfaces/mcp-interface.md`

---

## 1. 模块定位

MCP（Model Context Protocol）集成让 CORE 具备**双向** MCP 能力：

- **client 方向（吃）**：消费外部 MCP server 的 **tools / resources / prompts**，统一纳入 L1 工具层与 L3 上下文，
  **受与本地工具完全相同的约束**（可逆追踪 + 确认门 + coeffect 校验）。
- **server 方向（被吃）**：以 MCP server 身份对外暴露 L1 原子工具与技能，供外部 Agent（Claude Code / Cursor / Kiro 等）
  挂载复用，形成「机器 → core-agent」入口，与 UI 三入口（CLI/Web/Desktop，见 `06-ui-frontend/ui-architecture.md`）对称；
  暴露面受白名单约束，调用走与本地一致的 permission/observability 安全链路，能力复用但安全不下放。

---

## 2. 架构

```
【client 方向：吃】
L3 Loop ──► ToolProvider ──► [本地工具 | MCP 适配工具]
                                │
                     MCPClient ─┴─► 外部 MCP Server (stdio / HTTP)
                                       ├── tools
                                       ├── resources
                                       └── prompts

【server 方向：被吃】
外部 Agent (Claude Code / Cursor) ──► MCPServer ──► 白名单 ──► ToolProvider（同一内核）
```

- **MCPClient**：负责发现（initialize/list_tools）、传输（stdio 子进程 / HTTP）、协议编解码。
  经组合根（`runtime.py`）装配：注入 `SandboxManager` + `SandboxPolicy`，stdio 子进程受沙箱配额、
  http 出站受白名单管控（`Runtime.mcp_client`）。
- **MCP 适配器**：把远程 tool 包装成 `ToolDef`，符合四要素契约，注册进 PluginRegistry。
- **MCPServer**：负责握手（initialize/list_tools/call_tool）、传输（stdio / Streamable HTTP）、把本地工具经白名单包装为 MCP tool。

---

## 3. 关键设计

### 3.1 能力发现（client）

- 启动/配置时 `initialize` + `list_tools` + `list_resources` + `list_prompts`。
- 发现的 tools 包装为 `mcp.<server>.<tool>` 命名空间的 `ToolDef`，进入注册表；
  **`<server>` 即安装名**（`mcp add --name` 或派生名）⇒ 工具名跨进程稳定（change `0074`）。

### 3.2 传输方式

| 传输 | 说明 | 适用 |
|---|---|---|
| **stdio** | 子进程标准输入输出 JSON-RPC（换行分帧） | 本地、无网络暴露 |
| **Streamable HTTP** | 远程连接，单连接多会话复用（Mcp-Session-Id） | 跨机、云 MCP |

**生产实现现状**（ADR-0043 / ADR-0057，`src/core/mcp/transport.py`）：

- **stdio 已落地**：`StdioTransport` 为 stdlib 手写（`subprocess` + 换行分帧 + 读线程 + 队列超时），
  零新依赖；子进程经 `SandboxManager.spawn` 以资源配额拉起，`close` 终止回收。
- **http/streamable-http 部分落地**：连接前经网络出站白名单校验（非白名单 → `PERMISSION_DENIED`），
  `mcp` SDK 走可选 extra `[mcp]` 懒加载（未装 → `MCP_CONNECT_FAILED` 提示安装）；
  **会话层（`Mcp-Session-Id` 复用 + SSE 分帧）待接入**。
- `MCPClient.add` 按来源形状分流：`http(s)://` URL → http 端点；本地命令行 → stdio 端点。

### 3.3 与本地工具同等的安全约束

| 约束 | MCP 工具的落地 |
|---|---|
| 可逆追踪 | 远程 tool 结果记入 EffectTracker；不可逆的标注并走确认门 |
| coeffect 校验 | 声明所需权限（如 `network:outbound`），缺失拒绝 |
| 确认门 | 远程写/删除/敏感操作先 `ask_user` |

### 3.4 resources 与 prompts 入上下文

- `resources` 作为只读上下文来源，纳入 Perceive 阶段的预算裁剪。
- `prompts` 作为可选的推理模板，供 Reason 阶段选用。

### 3.5 MCP Server 模式（对外工具源）

- **暴露面复用 ToolProvider**：不复制工具实现，经白名单从 ToolProvider/PluginRegistry 挑选并包装为 MCP tool，
  命名空间 `core.<tool>`，与本地 `mcp.<server>.<tool>` 隔离。
- **默认最小暴露**：未配置白名单时仅暴露只读类工具；写/删除/敏感工具默认不暴露。
- **安全约束透传**：外部调用走同一 invoke 链路（permission 确认门 + observability 审计），来源标注 `external:<client_id>`。
- **会话隔离**：每个 MCP 连接独立 session，单连接熔断隔离不拖垮主循环。
- **会话多流复用**：单一 HTTP(TCP) 连接经 Mcp-Session-Id 会话标识承载多个会话，会话与连接解耦，请求按 Session-Id 分流互不串扰。
- **禁止二级代理**：初版不把 MCP client 已发现的远程工具再转暴露，防 A 挂 B、B 挂 A 的无限代理。
- **事件循环（change `0073`）**：stdio 方向由 `MCPServer.serve_stdio` 承载（换行分帧 JSON-RPC，
  stdin 读 / stdout 写，日志走 stderr）；`mcp serve` 装配 runtime 后即以 `runtime.tools` 为工具源进入循环，
  阻塞至 stdin EOF。**stdin/stdout 可注入** ⇒ 循环行为可纯内存验证。HTTP/streamable-http 方向事件循环待接入
  （`Mcp-Session-Id` 复用）。
- **故障隔离**：单条请求的异常（方法未实现 / 工具提供者抛错 / 应答不可序列化）降级为该 `id` 的错误应答，
  **不终止事件循环**；协议层错误码（`-32601` / `-32603`）与工具层结论（`CallResult.code`）分层。
- **远端错误码映射（change `0077`，账本 B8）**：client 侧收到远端 JSON-RPC `error` 时按「方法 + 标准码」
  归一 —— `tools/call` 上的错误 = **调用被拒**（未知工具 / 非法参数）⇒ `MCP_TOOL_NOT_FOUND`；其余方法
  `-32700`/`-32600`/`-32601`/`-32602` ⇒ `MCP_PROTOCOL_MISMATCH`，`-32603`/未知码 ⇒ `MCP_UNAVAILABLE`。
  原始远端码与消息保留在错误文本中（`transport.map_remote_error`）。
- **wire 形状（标准 envelope，change `0075`）**：`tools/list` 回容器键 `{"tools": [...]}`、
  `tools/call` 回 `{"content": [{"type": "text", "text": <JSON 载荷>}], "isError": <bool>}`，
  `initialize` 回 `protocolVersion`/`capabilities`/`serverInfo` —— **双向对齐标准 MCP**（server 可被
  Claude Code / Cursor 直接挂载，client 可挂 `claude mcp serve` 等标准 server）；client 侧同时**兼容旧式
  裸形状**应答（不打破既有服务端），见 `doc/03-interfaces/mcp-interface.md` §6。
- **本地工具结果信封（change `0319` / ADR-0309）**：`InstallDispatcher` 适配出的
  `mcp.<server>.<tool>` 返回恒定四键、可 JSON 序列化的信封 `{ok, data, code, error}`
  （成功 `data` 为远端载荷；远端 `isError`/协议失败 `ok=false` 并保留归一码与正文）；本地
  `ToolResult.ok` 恒 `true`、不触发本轮回滚；载荷只嵌在 `data` 下，避免被 `observe` 误判为
  终止回复。不可直接返回 `CallResult`（观测落盘 `json.dumps` 会抛 `TypeError`）。

### 3.6 端点注册表与装配期注册（change `0074`）

- **注册表**：`mcp add` 的成果落 `$CORE_STATE_DIR/mcp-endpoints.json`（单文件 JSON，**原子写**）。
  端点注册表是**运行期状态**、非配置项 —— 端点名是开放集合（同 `features.<模块>` 之于 `GATABLE_MODULES`），
  由 `mcp add` 写入、带连接句柄语义，故不进 `ConfigSpec`。
- **命令面**：`mcp add <endpoint> [--name N] [--transport T] [--command C] [--args ...]` / `mcp remove <name>` /
  `mcp list`。`add` **先连通验证再落盘**，`remove` 先卸载（释放连接）再删记录（对称）；`list` 不连接。
- **装配期注册**：组合根读回注册表 → 经**同一安装管线**（`InstallDispatcher._install_mcp`）连接、适配、
  注册工具为 `mcp.<端点名>.<工具>`；`handle_id` 取安装名 ⇒ 跨进程稳定（此前为随机 `uuid`，同一端点两次
  装配得到两个工具名）。
- **降级**：单个端点不可达只 `warnings.warn` 跳过，**不阻断装配**（坏端点不得让整个系统不可用）；注册表
  损坏 / 条目残缺同样告警降级。

---

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| server 连接失败 | 标记该 server 为 `DEGRADED`，不阻塞其他工具 |
| 协议/版本不兼容 | 降级尝试，失败则记录并跳过 |
| 远程工具超时 | 按 timeout 中止，返回 `REMOTE_TIMEOUT` |
| 远程不可逆操作 | 强制确认门，拒绝则改写 |
| 外部未授权调用 | 返回 `PERMISSION_DENIED`，不执行 |
| 默认面外工具（跨边界：出网 / 委托驱动） | 默认不暴露，调用 → `PERMISSION_DENIED`（change `0076`） |
| 外部高危操作 | 强制确认门 + 审计（来源 external） |
| 外部连接异常/崩溃 | 熔断该连接，不影响其他客户端 |
| 已装端点装配期不可达 | 告警并跳过该端点，装配照常完成（change `0074`） |
| 端点重名安装 | `ENDPOINT_NAME_CONFLICT` 拒绝，不静默覆盖（change `0074`） |
| 第三方 server 应答带厂商扩展字段 | 只取已知键（`name`/`description`/`inputSchema`），扩展字段忽略（change `0075`） |
| 远端应答为旧式裸形状 | 仍可解析，不抛（向后兼容，change `0075`） |

---

## 5. 关联

- 规格：`doc/openspec/specs/mcp/spec.md`
- 工具层：`doc/02-modules/tool-use.md`
- 接口：`doc/03-interfaces/mcp-interface.md`
- MCP Server 模式方案：`doc/07-mcp-server/mcp-server.md`
- 横切：`02-modules/permission.md` / `02-modules/observability.md`
- 测试：`doc/04-testing/test-cases.md`（MCP 系列）
