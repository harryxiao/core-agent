# MCP Specification

## Purpose
MCP（Model Context Protocol）集成层为智能体提供双向模型上下文协议能力：作为 client 消费外部 tools/resources/prompts（工具/资源统一外部入口），作为 server 对外暴露自身 L1 工具与技能（供外部 Agent 挂载复用），二者共用同一内核安全链路；并支持运行时安装与移除 MCP 服务端（复用统一插件来源）。

## Requirements

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
