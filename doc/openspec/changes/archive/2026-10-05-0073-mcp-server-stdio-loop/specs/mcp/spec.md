# mcp spec delta — mcp-server-stdio-loop

**把 MCP **server 方向**的 stdio 事件循环补齐（账本 B3）。** 规格「MCP Server 模式」与「工具暴露与白名单」
早已列出 server 侧要求，`MCPServer` 的方法级行为（`initialize` / `list_tools` / `call_tool` / 白名单 /
会话分流）也已实现并有单测，但**没有任何事件循环**把 JSON-RPC 消息接到这些方法上：`serve()` 只绑定一个
连接对象即返回（docstring 自述「stdio/http 事件循环在 M2 接入」），CLI `mcp serve` 落到「已识别，尚未接线」。
后果：规格场景「stdio 本地挂载」（外部 agent 拉起 core-agent MCP server 并握手调工具）**在生产不可达**，
且**命名空间前缀 `core.`（模块设计 §4）与「二级代理禁止」在实现里完全缺席** —— `list_tools` 直接吐裸
`tool_id`。

## MODIFIED Requirements

### Requirement: MCP Server 模式
系统 SHALL 支持以 MCP server 身份被外部 MCP 客户端（如 Claude Code、Cursor）挂载，对外提供工具能力。stdio 方向 SHALL 以**换行分帧 JSON-RPC**（每行一条消息，stdin 读 / stdout 写）承载事件循环：`initialize` SHALL 返回与 client 侧**同一** `protocolVersion`（`2024-11-05`）并声明 tools 能力；无 `id` 的通知（如 `notifications/initialized`）SHALL NOT 应答；`tools/list` SHALL 返回白名单过滤后的暴露面；`tools/call` SHALL 按 `name` / `arguments` 转发并复用 `ToolProvider.invoke` 链路（permission / observability / 副作用追踪不绕过）；`ping` SHALL 返回空结果；未知方法 SHALL 以 JSON-RPC 错误码 `-32601` 应答。**单条请求的异常 SHALL 被隔离为错误应答，SHALL NOT 终止事件循环**；stdin EOF 即退出并释放连接。

#### Scenario: stdio 本地挂载
- **GIVEN** 外部 agent 以 stdio 方式拉起 core-agent MCP server
- **WHEN** 完成 initialize 握手
- **THEN** 返回可用工具列表并可调用

#### Scenario: Streamable HTTP 远程挂载
- **GIVEN** core-agent MCP server 以 Streamable HTTP 启动
- **WHEN** 外部客户端连接并握手
- **THEN** 建立会话并返回工具列表

#### Scenario: stdio 事件循环按 id 应答
- **GIVEN** 外部客户端以 stdio 拉起本 server
- **WHEN** 依次发送 `initialize` / `tools/list` / `tools/call`
- **THEN** 每条请求**按各自 `id`** 应答（请求与响应一一配对），无 `id` 的通知不应答，读取流关闭（EOF）后循环退出

#### Scenario: 请求异常不终止事件循环
- **GIVEN** 一条请求触发内部异常（或方法未知）
- **WHEN** server 处理该请求
- **THEN** 以错误应答回报该 `id`，**循环继续**处理后续请求（单连接内故障隔离，不拖垮会话）

### Requirement: 工具暴露与白名单
系统 SHALL 通过白名单控制对外暴露的工具集合，默认最小暴露，命名空间隔离。**对外工具名 SHALL 带 `core.` 命名空间前缀**（`core.<tool_id>`），与本地工具名及 client 侧 `mcp.*` 远程工具名天然隔离；`call_tool` SHALL ONLY 接受**已暴露**的名字，未暴露者 SHALL 返回 `PERMISSION_DENIED` 且**不执行**；SHALL NOT 把 client 侧已发现的远程工具（`mcp.*`）再对外暴露（**禁止二级代理**，防止相互挂载递归）。白名单 SHALL 可经 `mcp serve --whitelist`（逗号分隔工具名）显式声明。

#### Scenario: 默认最小暴露
- **GIVEN** 未配置白名单
- **WHEN** server 启动
- **THEN** 仅暴露只读类工具，写/删除/敏感工具默认不暴露

#### Scenario: 白名单显式开放
- **GIVEN** 配置了白名单
- **WHEN** server 启动
- **THEN** 仅暴露白名单内的工具，其余不可见

#### Scenario: 工具命名空间隔离
- **GIVEN** 本地存在工具 `tools.file_read`
- **WHEN** 外部客户端执行 `tools/list`
- **THEN** 暴露名为 `core.tools.file_read`（前缀隔离），`tools/call` 以该名调用即转发到本地 `tools.file_read`

#### Scenario: 远程工具不被二级代理暴露
- **GIVEN** 本进程作为 client 已发现远程工具（`mcp.<server>.<tool>`）
- **WHEN** 外部客户端执行 `tools/list`
- **THEN** 该远程工具**不出现**在暴露面内（禁止二级代理）
