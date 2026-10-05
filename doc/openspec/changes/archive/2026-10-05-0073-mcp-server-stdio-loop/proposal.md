# MCP Server 模式 stdio 事件循环（mcp-server-stdio-loop）

## Why

账本 **B3**：规格「MCP Server 模式」场景「stdio 本地挂载」要求外部 agent 以 stdio 拉起本
server → 握手 → 取工具列表 → 调用；`MCPServer` 的**方法级**行为（`initialize` / `list_tools` /
`call_tool` / 白名单过滤 / 会话分流）早已实现并有单测，但**没有任何事件循环**把 JSON-RPC 消息
接到这些方法上：

- `serve()` 只构造一个 `ServerConnection` 即返回（docstring 自述「stdio/http 事件循环在 M2 接入」）；
- CLI `mcp serve` 落进 `_dispatch` 兜底分支，打印「已识别，尚未接线」；
- 于是规格场景在生产**不可达** —— 该能力只存在于单测的直接方法调用里。

同一次一手核实还发现**两处文档已写、代码缺席**的暴露面契约（`doc/07-mcp-server/mcp-server.md`
§4 与 `doc/03-interfaces/mcp-interface.md` §6 均写「包装为 MCP tool（`core.<tool>`）」，规格
「工具暴露与白名单」要求命名空间隔离与禁止二级代理）：

1. `list_tools` 直接吐**裸** `tool_id`（无 `core.` 前缀），与本地工具名、client 侧 `mcp.*`
   远程工具名**无隔离**；
2. 无**二级代理**防护 —— 本进程作为 client 已发现的 `mcp.<server>.<tool>` 会被原样对外暴露，
   两个 core-agent 相互挂载即可递归放大暴露面。

## What Changes

- `src/core/mcp/server.py`
  - `serve_stdio(endpoint, *, stdin, stdout)`：**换行分帧 JSON-RPC 事件循环**（stdin 逐行读 /
    stdout 逐行写，日志走 stderr）；按 `id` 应答、无 `id` 通知不应答、非 JSON 行跳过、EOF 退出。
  - `_respond` / `_dispatch`：`initialize`（回 client 侧同一 `protocolVersion` + tools 能力）、
    `tools/list`、`tools/call`（转发 `arguments` → 复用 `ToolProvider.invoke`，来源仍标
    `external:<client_id>`）、`ping`；未知方法 → `-32601`。**单条请求异常（含工具提供者抛错、
    应答不可序列化）隔离为该 `id` 的错误应答，绝不终止循环**。
  - `list_tools`：对外名统一加 `core.` 前缀；过滤 `mcp.*`（禁止二级代理）；白名单接受裸名与
    `core.` 前缀两种写法（照 `tools/list` 应答抄名字亦可）。`call_tool` 只接受**已暴露**的名字。
  - `serve(transport, endpoint)` 保留为文档化接缝（http 方向），委托给新的 `_bind`。
- `src/core/mcp/models.py` + `client.py` + `__init__.py`：协议版本提为**共享常量**
  `PROTOCOL_VERSION`（此前是 client 侧私有 `_PROTOCOL_VERSION`；server 侧若各写一份，握手匹配
  的两端会各自漂移）。
- `src/core/entry.py`：`mcp serve` 接线（装配 runtime → `MCPServer(tool_provider=runtime.tools)` →
  `serve_stdio`），新增 `--whitelist`（逗号分隔工具名）与 `_mcp` 处理器注册进 `_HANDLERS`；
  非 stdio 传输明确拒绝（HTTP 会话待接入，不静默起一个空 server）。
- `tests/test_mcp_server_stdio.py`（新，14 例）：事件循环单元面（按 id 应答 / 通知不应答 /
  非法行跳过 / 未知方法 / 提供者异常 / 解码；命名空间 / 白名单两种写法 / 未暴露调用拒绝 /
  禁二级代理 / CLI 面 CSV 与传输拒绝）+ **端到端**：用本仓自己的 `MCPClient`（`StdioTransport`）
  以真实子进程拉起 `core-agent mcp serve`，完成握手 → 发现 → 调用（真读文件）→ 越权拒绝。
- `tests/test_mcp.py`：既有 server 单测对齐命名空间契约（`core.tools.file_read`）。

## Impact

- 规格「MCP Server 模式」与「工具暴露与白名单」**无需新增需求**，只把既有要求落到实现（delta 为
  MODIFIED + 4 个新场景）。
- 行为变化：对外工具名由 `tools.x` 变为 `core.tools.x`（**此前无任何生产引用**，仅单测直接调用）；
  `call_tool` 不再接受裸名。
- **不在本变更内**：http/streamable-http 事件循环（`Mcp-Session-Id` 复用）、`mcp list/add/remove`
  的跨进程持久化（账本 B4）、标准 MCP envelope 对齐与默认暴露面收窄（新登记账本行，见 design）。
