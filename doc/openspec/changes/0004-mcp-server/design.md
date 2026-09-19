# Design

## Context

MCP 是双向协议，core-agent 目前只实现 client 侧（消费外部 tools/resources/prompts）。外部主流 harness
（Claude Code、Cursor、Kiro 等）均支持把 MCP server 作为工具源挂载。补齐 server 侧后，core-agent 的 L1
原子工具与技能可被任意 MCP client 复用，形成「机器 → core-agent」入口，与 0003 的「人 → core-agent」
三入口（CLI/Web/Desktop）对称。

## Decisions

- **暴露面复用 ToolProvider**：不复制工具实现，通过白名单从 ToolProvider/PluginRegistry 挑选并包装为 MCP
  tool；命名空间 `core.<tool>`，与本地工具、`mcp.*` 远程工具隔离。
- **安全不绕过内核**：外部调用与本地调用走同一 `invoke` 链路 → permission 确认门 + observability 审计，
  EffectTracker 记录来源 `external:<client_id>`。
- **传输 stdio 优先 + HTTP/SSE 可选**：stdio 零配置（Claude Code 直接 `command` 拉起）；HTTP/SSE 供远程/
  多客户端，鉴权必选（token/mTLS）。
- **会话隔离**：每个 MCP 连接独立 session，状态不串；单连接崩溃熔断隔离，不拖垮主循环。
- **二级代理禁止**：初版不把 MCP client 已发现的远程工具再转暴露，防止 A 挂 B、B 挂 A 的无限代理。

## Risks / Trade-offs

- **暴露面越权**：默认最小暴露（只读工具），写/删/执行默认不暴露或走确认门。
- **网络开洞**：stdio 无网络暴露但仅单客户端；HTTP/SSE 需鉴权，否则等同于对外开洞。
- **命名冲突 / 递归挂载**：`core.*` 命名空间隔离 + 禁止二级代理，避免递归。

## Open Questions

- HTTP/SSE 的鉴权方案（token / mTLS）待 P3 定。
- 是否支持把 MCP client 发现的远程工具再转暴露（二级代理）——初版不做，后续按需评估。
