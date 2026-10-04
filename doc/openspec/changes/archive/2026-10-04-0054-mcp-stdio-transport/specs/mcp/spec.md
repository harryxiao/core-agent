# mcp spec delta — mcp-stdio-transport

MCP 传输生产实现：client 本地 stdio 走 stdlib 手写 JSON-RPC（零新依赖，经沙箱常驻子进程拉起）；
远端 http/streamable-http 走 `mcp` SDK 懒加载（可选 extra），连接前经网络出站白名单校验；
`MCPClient.add` 按来源形状分流构建端点。（来源：`0033-mcp-install-security` tasks 2.x–4.x 实现切片 + ADR-0043，2026-10-04）

## MODIFIED Requirements

### Requirement: 传输层抽象与依赖注入隔离
系统 SHALL 通过 Transport 抽象接口隔离底层 MCP 传输实现（stdio/http/streamable-http 的 SDK 或 JSON-RPC 实现），MCPClient 与 MCPServer 只依赖该抽象；替换底层传输实现或 MCP SDK 时，调用方零改动。

#### Scenario: 替换传输实现
- **GIVEN** 需要替换底层 MCP 传输实现（如官方 SDK → 自研 JSON-RPC）
- **WHEN** 注册新的 Transport 实现
- **THEN** MCPClient / MCPServer 及所有调用方无需改动即可切换

#### Scenario: 生产传输按端点分派
- **GIVEN** 一个 MCPEndpoint（transport 为 stdio 或 http/streamable-http）
- **WHEN** `build_transport` 构建传输
- **THEN** stdio 分派到 stdlib 手写 StdioTransport，http/streamable-http 分派到 SDK 传输，未知 transport 返回结构化错误；测试仍可经 `transport_factory` 注入替身

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

#### Scenario: 按来源形状构建端点
- **GIVEN** 一个 MCP 服务端来源字符串（`http(s)://` URL 或本地命令行）
- **WHEN** `MCPClient.add` 安装该来源
- **THEN** URL 构建 http 端点（url+headers），命令行构建 stdio 端点（command+args）；显式 transport/command 覆盖形状推断

## ADDED Requirements

### Requirement: MCP 传输实现与沙箱常驻进程
系统 SHALL 为 MCP client 提供生产传输实现：本地 stdio 采用 stdlib 手写 JSON-RPC（`subprocess` + 换行分帧，零新依赖），经 `SandboxManager` 以资源配额拉起**常驻**子进程，连接关闭即终止并回收；远端 http/streamable-http 采用 `mcp` SDK **懒加载**（可选依赖组 `[mcp]`），连接前经网络出站白名单校验，非白名单 host 以 `PERMISSION_DENIED` 拒绝，SDK 缺失时以 `MCP_CONNECT_FAILED` 提示安装。

#### Scenario: stdio 常驻子进程握手与调用
- **GIVEN** 一个本地 stdio MCP 服务端端点（command+args）
- **WHEN** MCPClient 连接并调用其工具
- **THEN** 经 JSON-RPC 完成 initialize 握手与 tools/list、tools/call，请求/响应按 id 配对

#### Scenario: stdio 子进程随连接销毁
- **GIVEN** 一个已连接的本地 stdio MCP 服务端
- **WHEN** 关闭该连接
- **THEN** 子进程被终止并回收，无残留进程

#### Scenario: 远端 http 出站白名单拒绝
- **GIVEN** 一个远端 http MCP 端点，其 host 不在网络白名单内
- **WHEN** 发起连接
- **THEN** 以 PERMISSION_DENIED 拒绝，不建立连接

#### Scenario: 未安装 SDK 时的清晰降级
- **GIVEN** 一个远端 http MCP 端点，其 host 在白名单内，但环境未安装 mcp SDK
- **WHEN** 发起连接
- **THEN** 抛 MCP_CONNECT_FAILED，并提示安装 `core-agent[mcp]` 可选依赖

#### Scenario: 传输超时结构化
- **GIVEN** 一个已连接的 stdio MCP 服务端，其响应超出资源配额超时
- **WHEN** 发起调用
- **THEN** 返回结构化 REMOTE_TIMEOUT，不永久阻塞调用方
