# Tasks

## 1. MCP Server 骨架 + stdio（P1）

- [ ] 1.1 实现 MCPServer（initialize / list_tools / call_tool 协议握手）
- [ ] 1.2 实现 stdio transport（子进程 JSON-RPC，供 Claude Code 直接拉起）
- [ ] 1.3 实现 core-agent 可执行入口（`core-agent mcp-serve`）

## 2. 暴露面与白名单（P2）

- [ ] 2.1 实现 ToolProvider → MCP tool 适配（命名空间 `core.*`）
- [ ] 2.2 实现白名单配置（默认最小暴露，只读优先）
- [ ] 2.3 实现权限透传（外部调用走确认门 + 审计，来源标注 `external:<client_id>`）

## 3. HTTP/SSE + 多客户端（P3）

- [ ] 3.1 实现 HTTP/SSE transport（远程挂载）
- [ ] 3.2 实现鉴权（token / mTLS）
- [ ] 3.3 实现多客户端会话隔离与并发管理

## 4. 发布与集成（P4）

- [ ] 4.1 打包可执行入口与安装说明
- [ ] 4.2 提供 Claude Code / Cursor 接入配置模板
- [ ] 4.3 端到端用例（外部 Agent 调用 core 工具 → 确认门 → 审计）
