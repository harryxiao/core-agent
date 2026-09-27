# Design

## Context

mcp capability 现有 R4「MCP Server 模式」支持 stdio 与 HTTP/SSE 两种传输，R7「会话与调用隔离」SHALL「为每个 MCP 连接建立独立会话」。SSE 传输机制下连接与会话 1:1 绑定：每个外部 MCP 客户端需独占一条 HTTP/SSE 连接，多客户端并发接入时连接数线性增长，且无法在单一 HTTP(TCP) 连接上承载多个会话。本 change 引入 MCP 规范的 Streamable HTTP 传输与 Mcp-Session-Id 会话标识，将会话与连接解耦：多个客户端共享一条 HTTP(TCP) 连接、各自建立独立会话。与会话隔离（R7）正交：R7 管「会话之间数据/调用互不串扰」，R8 管「一个连接承载多个会话」的传输层复用。

## Decisions

- **传输升级（MODIFIED R4）**：R4「MCP Server 模式」的远程挂载传输由 HTTP/SSE 升级为 Streamable HTTP（stdio 本地模式保留不变）；Streamable HTTP 为 MCP 规范现行推荐传输，替代 SSE 的 1 连接 1 会话限制。
- **会话多流复用（R8）**：引入 Mcp-Session-Id 会话标识，单一 HTTP(TCP) 连接可承载多个独立会话，多客户端共享连接、按 Session-Id 分流；会话与连接解耦后，连接数不再随客户端数线性增长。
- **R8 独立于 R7 正交**：R7「会话与调用隔离」管应用层隔离语义（会话间互不串扰），R8 管传输层复用（单连接多会话），两者职责不同、互不替代 → 新增独立 R8 而非扩展 R7。
- **spec 扩展非新 cap**：Streamable HTTP 升级与会话多流复用均属 mcp 既有职责扩展，不新建 capability。

## Risks / Trade-offs

- **transport 升级兼容性**：Streamable HTTP 与 SSE 端点路径/握手不同，需保留 stdio 不变、远程 transport 平滑切换；既有 HTTP/SSE 客户端需升级或走兼容路径。
- **单连接多会话的资源隔离**：多会话复用同一 TCP 连接，需在传输层按 Session-Id 正确分流请求/响应，避免会话串扰（复用 R7 应用层隔离语义兜底）。
- **Mcp-Session-Id 生命周期**：会话标识的创建/失效需与 R7 会话生命周期一致，避免悬挂会话占用连接。

## Open Questions

- Streamable HTTP 与 SSE 是否并存过渡期（兼容旧客户端）留待实现阶段确定。
- 单连接承载会话数的上限策略留待实现阶段确定。
