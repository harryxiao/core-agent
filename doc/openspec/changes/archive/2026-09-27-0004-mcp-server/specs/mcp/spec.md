MCP Server 模式让 core-agent 以 MCP server 身份对外暴露 L1 工具与技能，供外部 Agent 挂载；暴露面受白名单约束，调用走 permission/observability 安全链路，多客户端会话隔离。

## ADDED Requirements

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

### Requirement: 工具暴露与白名单
系统 SHALL 通过白名单控制对外暴露的工具集合，默认最小暴露，命名空间隔离。

#### Scenario: 默认最小暴露
- **GIVEN** 未配置白名单
- **WHEN** server 启动
- **THEN** 仅暴露只读类工具，写/删除/敏感工具默认不暴露

#### Scenario: 白名单显式开放
- **GIVEN** 配置了白名单
- **WHEN** server 启动
- **THEN** 仅暴露白名单内的工具，其余不可见

### Requirement: 安全约束透传
系统 SHALL 让外部调用走与本地调用相同的 permission 确认门与 observability 审计链路，不绕过内核。

#### Scenario: 高危操作确认
- **GIVEN** 外部客户端调用高危工具
- **WHEN** 执行
- **THEN** 触发确认门，记录来源为外部客户端，审计落盘

#### Scenario: 越权拒绝
- **GIVEN** 外部调用未授权工具
- **WHEN** 执行
- **THEN** 返回 `PERMISSION_DENIED`，不执行

### Requirement: 会话与调用隔离
系统 SHALL 为每个 MCP 连接建立独立会话，错误隔离不拖垮主循环。

#### Scenario: 多客户端隔离
- **GIVEN** 多个外部客户端并发连接
- **WHEN** 各自调用
- **THEN** 会话状态互不串扰

#### Scenario: 单连接故障隔离
- **GIVEN** 某客户端异常/崩溃
- **WHEN** 其调用失败
- **THEN** 熔断该连接，不影响其他客户端与主循环

