MCP 心跳保活与资源释放：连接空闲期独立心跳探测保活，连接关闭时释放会话/socket/缓冲资源，避免半开连接与泄漏。（来源：架构查漏补缺探索结论，2026-09-22）

## MODIFIED Requirements

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

#### Scenario: 心跳保活
- **GIVEN** 一个已建立但空闲的 MCP 连接
- **WHEN** 连接进入空闲期
- **THEN** 按固定间隔发送心跳探测，无响应则判定失效并触发重连，避免半开连接长期占用

#### Scenario: 连接关闭与资源释放
- **GIVEN** MCP 服务端注销或连接关闭
- **WHEN** 触发关闭
- **THEN** 释放该连接占用的会话、socket 与缓冲资源，无泄漏，相关工具标记不可用
