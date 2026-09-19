# MCP Specification

## Purpose
MCP（Model Context Protocol）集成层为智能体提供双向模型上下文协议能力：作为 client 消费外部 tools/resources/prompts（工具/资源统一外部入口），作为 server 对外暴露自身 L1 工具与技能（供外部 Agent 挂载复用），二者共用同一内核安全链路。

## Requirements

### Requirement: MCP 连接管理
系统 SHALL 支持 MCP 服务端的注册、连接、心跳与断线重连。

#### Scenario: 注册并连接
- **GIVEN** 一个 MCP 服务端配置
- **WHEN** 启动时注册
- **THEN** 建立连接并完成能力握手（tools/resources 列表）

#### Scenario: 断线重连
- **GIVEN** MCP 连接中断
- **WHEN** 检测到断线
- **THEN** 按退避策略重连，重连期间相关工具标记不可用

### Requirement: 工具/资源发现
系统 SHALL 把 MCP 暴露的工具/资源动态映射进本地工具集合。

#### Scenario: 动态映射
- **GIVEN** MCP 服务端新增一个工具
- **WHEN** 刷新能力列表
- **THEN** 本地工具集合同步更新，无需重启

#### Scenario: 能力冲突处理
- **GIVEN** MCP 工具与本地工具重名
- **WHEN** 映射时检测到冲突
- **THEN** 返回 `TOOL_NAME_CONFLICT`，本地工具优先或显式命名空间隔离

### Requirement: 调用转发与错误隔离
系统 SHALL 把本地调用透明转发到 MCP，并对 MCP 异常做隔离，不拖垮主循环。

#### Scenario: 透明转发
- **GIVEN** 模型调用一个 MCP 工具
- **WHEN** 执行
- **THEN** 请求按协议转发，结果归一化为本地工具返回结构

#### Scenario: MCP 异常隔离
- **GIVEN** MCP 服务端超时/崩溃
- **WHEN** 调用失败
- **THEN** 返回 `MCP_UNAVAILABLE`，熔断该 MCP，不影响其他工具

### Requirement: MCP Server 模式
系统 SHALL 支持以 MCP server 身份被外部 MCP 客户端（如 Claude Code、Cursor）挂载，对外提供工具能力。

#### Scenario: stdio 本地挂载
- **GIVEN** 外部 agent 以 stdio 方式拉起 core-agent MCP server
- **WHEN** 完成 initialize 握手
- **THEN** 返回可用工具列表并可调用

#### Scenario: HTTP/SSE 远程挂载
- **GIVEN** core-agent MCP server 以 HTTP/SSE 启动
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
