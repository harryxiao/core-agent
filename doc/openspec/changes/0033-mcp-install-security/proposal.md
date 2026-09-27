# Change: MCP 安装/传输/安全接线——本地 stdio 沙箱 + 远端网络管控

## Why

架构审计（2026-09-27）走查 MCP 客户端侧（core-agent 作为 MCP client 消费三方/本地 MCP 服务端）发现三条接线缺口，影响「Agent 开发完毕后导入 MCP server」的可用性与安全：

1. **Transport 生产实现是占位符**：`src/core/mcp/transport.py` 的 `build_transport` 直接抛 `MCP_CONNECT_FAILED`（"离线未安装 SDK"），`MCPServer.serve` 标注 stdio/http 事件循环 M2 接入——跑不了真实连接。
2. **`MCPClient.add` 硬编码 `transport="http"`**（`client.py:138`）：只能装远端 http URL，本地 stdio MCP 服务端（`command+args`，如 `npx -y ...`）装不了。
3. **消费侧安全未接线**：本地 stdio 子进程未过 `permission/sandbox.SandboxManager` 沙箱、远端 http 未走出站白名单、不可逆工具未显式走确认门。spec 现有「安全约束透传」只覆盖 **server 侧**（外部调用进入本 Agent），缺 **client 消费侧**安全约束。

## What Changes

- **MCP 客户端消费安全**（mcp，ADDED）：本地 stdio 子进程沙箱隔离 + 远端 http 出站白名单 + 不可逆工具确认门，走与本地工具一致的 permission/observability 链路。
- **MCP Server 安装与移除**（mcp，MODIFIED）：来源覆盖本地 stdio 与远端 http/streamable-http 两类，补两类安装场景；移除含本地子进程销毁。

## Impact

- **Affected specs**：`mcp/spec.md`（1 ADDED + 1 MODIFIED）
- **Affected docs**：`03-interfaces/mcp-interface.md`（§2 端点、§4 适配器、§7 错误码——实现期同步）
- **Affected code**：`src/core/mcp/transport.py`（stdio/http 生产实现）、`client.py`（`add` 按 transport 分流构建 MCPEndpoint）、`adapter.py`（coeffects / reversible 标注）——M2
- **Dependencies**：`permission/sandbox.py`（SandboxManager 子进程隔离 + 出站白名单）、`plugin_registry`（PluginSource.MCP_ENDPOINT / coeffect 解析）；无新三方依赖
