MCP 安装/传输/安全接线：安装来源覆盖本地 stdio 与远端 http；client 消费侧新增安全约束（stdio 子进程沙箱 + http 出站白名单 + 不可逆确认门）。（来源：架构审计 MCP 三方边界接线缺口，2026-09-27）

## ADDED Requirements

### Requirement: MCP 客户端消费安全
系统 SHALL 在作为 MCP client 消费外部（三方/本地）MCP 服务端时实施安全管控：本地 stdio 子进程经沙箱隔离（资源配额 + 受限文件系统 + 网络出站白名单）；远端 http 经网络出站白名单校验；其暴露工具经 MCPToolAdapter 标注 coeffects（network:outbound 等）并默认 reversible=False，走与本地工具一致的 permission 确认门与 observability 审计，不绕过内核安全链路。

#### Scenario: 本地 stdio 子进程沙箱隔离
- **GIVEN** 安装了一个本地 stdio MCP 服务端
- **WHEN** 拉起其进程执行工具调用
- **THEN** 该进程在沙箱内运行（资源配额受限、文件系统受控），越界访问被拒绝

#### Scenario: 远端 http 出站管控
- **GIVEN** 安装了一个远端 http MCP 服务端
- **WHEN** 发起工具调用请求
- **THEN** 请求经出站网络白名单校验，非白名单 host 拒绝

#### Scenario: 远程工具高危确认
- **GIVEN** 外部 MCP 服务端暴露一个不可逆/写类工具
- **WHEN** 模型调用该工具
- **THEN** 触发 permission 确认门，来源标注为外部 MCP 服务端，审计落盘

## MODIFIED Requirements

### Requirement: MCP Server 安装与移除
系统 SHALL 支持在运行时安装与移除 MCP 服务端，来源覆盖本地 stdio（command+args 拉起本地进程）与远端 http/streamable-http（url+headers）两类：安装复用插件来源（mcp-endpoint）经 discover → verify → install → register 进入现有连接管理；移除经 deactivate → uninstall 释放连接资源（含本地子进程销毁）。

#### Scenario: 运行时安装 MCP Server
- **GIVEN** 一个 MCP 服务端来源（mcp-endpoint）
- **WHEN** 执行 mcp add
- **THEN** 安装并注册该 MCP 服务端，进入现有连接管理，其工具可被动态发现

#### Scenario: 安装本地 stdio MCP Server
- **GIVEN** 一个本地 MCP 服务端来源（stdio，command+args）
- **WHEN** 执行 mcp add
- **THEN** 以沙箱受控子进程拉起并注册，进入连接管理，其工具可被动态发现

#### Scenario: 安装远端 http MCP Server
- **GIVEN** 一个远端 MCP 服务端来源（http/streamable-http，url+headers）
- **WHEN** 执行 mcp add
- **THEN** 建立网络连接并注册（经出站白名单管控），进入连接管理，其工具可被动态发现

#### Scenario: 移除 MCP Server
- **GIVEN** 一个已安装的 MCP 服务端
- **WHEN** 执行 mcp remove
- **THEN** 停用并卸载该服务端，释放连接/会话/socket 资源（含本地子进程销毁），相关工具标记不可用
