# Change: MCP 会话多流复用（Streamable HTTP 传输升级）

## Why

mcp capability 现有 R4「MCP Server 模式」支持 stdio 与 HTTP/SSE 两种传输，R7「会话与调用隔离」SHALL「为每个 MCP 连接建立独立会话」。SSE 机制下连接与会话 1:1 绑定：每个外部 MCP 客户端需独占一条 HTTP/SSE 连接，多客户端并发接入时连接数线性增长，且无法在单一 HTTP(TCP) 连接上承载多个会话。引入 MCP 规范的 Streamable HTTP 传输与 Mcp-Session-Id 会话标识，将会话与连接解耦，实现单连接多会话复用：多个客户端共享一条 HTTP(TCP) 连接、各自建立独立会话。

## What Changes

- 扩展 `mcp` capability：MODIFIED R4「MCP Server 模式」的「HTTP/SSE 远程挂载」Scenario，远程传输由 HTTP/SSE 升级为 Streamable HTTP（保留 stdio 本地挂载不变）
- 扩展 `mcp` capability：ADDED R8「会话多流复用」——单一 HTTP(TCP) 连接承载多个会话（Mcp-Session-Id 会话标识），与会话隔离正交

## Impact

- **Affected specs**：扩展 `mcp`（MODIFIED R4 传输升级 + ADDED R8 会话多流复用）
- **Affected docs**：`00-product/requirements.md`（1.5 节 CORE-MCP-R4 行传输描述更新 + 追加 CORE-MCP-R8 行）、`02-modules/mcp.md`（传输/会话描述）、`03-interfaces/mcp-interface.md`（Mcp-Session-Id / Streamable HTTP 端点）
- **Affected code**：无（本 change 声明 MCP 传输与会话复用能力，不涉及具体实现代码）
- **Dependencies**：复用 R7「会话与调用隔离」的应用层会话隔离语义、R4「MCP Server 模式」的对外工具能力
