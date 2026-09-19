# MCP Specification

## Purpose
MCP（Model Context Protocol）集成层为智能体接入外部模型上下文协议服务提供标准通道，作为工具/资源的统一外部入口。

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
