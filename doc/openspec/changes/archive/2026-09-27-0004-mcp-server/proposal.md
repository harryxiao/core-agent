# Change: MCP Server 模式（对外工具源）

## Why

core-agent 已具备三类「人 → core-agent」入口（CLI / Web / Desktop，0003），并作为 MCP client 可消费外部
tools/resources/prompts（`mcp` spec 现有）。但缺少「机器 → core-agent」入口：外部 Agent（Claude Code /
Cursor / Kiro 等）无法把 core-agent 的 L1 原子工具、技能与记忆能力作为 MCP 工具挂载复用。

补齐 MCP server 侧后，core-agent 既能「吃」也能「被吃」，成为多 Agent 协作网络中的可复用工具源，同时
把安全边界（权限/审计/熔断）一并外扩，能力复用但安全不下放。

## What Changes

- **扩展 `mcp` 规格**：新增 MCP Server 模式（server 角色），与现有 client 角色对称（`## ADDED Requirements`）。
- **对外暴露面**：白名单控制 L1 工具/技能暴露，命名空间 `core.<tool>`，默认最小暴露（只读优先）。
- **传输**：stdio（本地零配置，默认）+ HTTP/SSE（远程多客户端，鉴权必选）。
- **安全**：外部调用走同一 `invoke` 链路 → permission 确认门 + observability 审计，不绕过内核。

## Impact

- **Affected specs**：`mcp`（扩展，非新增 capability）
- **Affected specs (integration)**：`permission` / `observability` / `tool-use` / `skills`（对外暴露复用同一 ToolProvider 与横切链路）
- **Affected code**：新增 `src/mcp/server/`（stdio/HTTP server、暴露适配、会话管理）；内核层不改动
- **Dependencies**：依赖 0001 主轴（L1 工具层）+ 0002 横切（复用 permission/observability/constraints）
