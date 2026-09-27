MCP 传输层由 HTTP/SSE 升级为 Streamable HTTP，通过 Mcp-Session-Id 会话标识实现单连接多会话复用，将会话与连接解耦。（来源：探索 subagent 结论 + 用户决策，2026-09-21）

## MODIFIED Requirements

### Requirement: MCP Server 模式
系统 SHALL 支持以 MCP server 身份被外部 MCP 客户端（如 Claude Code、Cursor）挂载，对外提供工具能力。

#### Scenario: stdio 本地挂载
- **GIVEN** 外部 agent 以 stdio 方式拉起 core-agent MCP server
- **WHEN** 完成 initialize 握手
- **THEN** 返回可用工具列表并可调用

#### Scenario: Streamable HTTP 远程挂载
- **GIVEN** core-agent MCP server 以 Streamable HTTP 启动
- **WHEN** 外部客户端连接并握手
- **THEN** 建立会话并返回工具列表

## ADDED Requirements

### Requirement: 会话多流复用
系统 SHALL 支持在单一 HTTP(TCP) 连接上承载多个 MCP 会话：多个外部 MCP 客户端共享一条 HTTP(TCP) 连接，各自通过 Mcp-Session-Id 会话标识建立独立会话，请求按 Session-Id 分流、互不串扰。

#### Scenario: 单连接多会话复用
- **GIVEN** 多个外部 MCP 客户端共享一条 HTTP(TCP) 连接
- **WHEN** 各自携带不同 Mcp-Session-Id 发起请求
- **THEN** 各会话独立建立并按 Session-Id 分流，互不串扰

#### Scenario: 会话与连接解耦
- **GIVEN** 某会话已通过 Mcp-Session-Id 建立
- **WHEN** 后续请求复用同一 HTTP(TCP) 连接并携带相同 Mcp-Session-Id
- **THEN** 请求路由到该会话，无需为该会话独占连接
