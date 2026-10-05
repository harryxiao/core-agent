# mcp spec delta — mcp-standard-envelope（change 0075 / 账本 B6）

**让本 server 挂得上、本 client 也挂得上 —— 标准 MCP wire 形状双向对齐。**

规格「MCP Server 模式」字面点名 Claude Code / Cursor 可直接挂载本 server；实测一侧也挂不上：
本 server 应答为裸列表 / `CallResult` 直出，本 client 又以**空 params** 发起 `initialize`
且假定应答是裸列表。对齐标准 envelope 是「stdio 本地挂载」场景成立与否的硬前置。

## ADDED Requirements

### Requirement: 标准 MCP 互操作（双向）
系统 SHALL 在 MCP client 与 MCP server 两个方向以**标准 MCP wire 形状**（协议版本 `2024-11-05`）互操作，使第三方 MCP 客户端（如 Claude Code / Cursor）可直接挂载本 server，本 client 亦可直接挂载第三方 MCP server。

- **握手（client 向）**：`initialize` 请求 SHALL 携带标准三元组 `protocolVersion` / `capabilities` / `clientInfo`（`clientInfo` 含实现名与版本），SHALL NOT 以空参数发起；应答的 `protocolVersion` 与本端不一致时 SHALL 以 `MCP_PROTOCOL_MISMATCH` 拒绝。
- **发现（client 向）**：`tools/list` / `resources/list` / `prompts/list` 结果 SHALL 以标准容器键（`tools` / `resources` / `prompts`）承载；client SHALL 解析该容器键，SHALL 容忍**未知厂商扩展字段**（只取已知键，不得因多余字段报错），且 SHALL 仍可解析既有的**裸列表**应答（向后兼容）。
- **调用（client 向）**：标准 `tools/call` 结果 `{"content": [{"type": "text", "text": ...}], "isError": bool}` SHALL 被归一为本地 `CallResult`：`isError` 为真 ⇒ `ok=False`；`content` 文本为合法 JSON 时 SHALL 解码为该数据结构，否则 SHALL 原样承载。
- **应答（server 向）**：`tools/list` SHALL 应答 `{"tools": [...]}`；`tools/call` SHALL 应答 `{"content": [{"type": "text", "text": <JSON 载荷>}], "isError": <bool>}` —— 成功载荷为工具数据，失败载荷为 `{"code": ..., "error": ...}`；`initialize` SHALL 应答 `protocolVersion` / `capabilities` / `serverInfo` 三元组。

#### Scenario: client 以标准参数握手
- **GIVEN** 一个标准 MCP 服务端（如 `claude mcp serve`）
- **WHEN** 本 client 发起 `initialize`
- **THEN** 请求 params 含 `protocolVersion` / `capabilities` / `clientInfo` 三项（**非空参数**），对端接受并返回其 `protocolVersion`

#### Scenario: client 解析标准 tools/list（容忍扩展字段）
- **GIVEN** 一个标准 MCP 服务端，其 `tools/list` 应答为 `{"tools": [{"name": ..., "description": ..., "inputSchema": ..., <厂商扩展键>}]}`
- **WHEN** 本 client 解析
- **THEN** 取得该工具列表（**多余的厂商扩展字段被忽略，不报错**）

#### Scenario: 裸列表应答向后兼容
- **GIVEN** 一个既有（非标准）MCP 服务端，其 `tools/list` 应答为**裸列表**
- **WHEN** 本 client 解析
- **THEN** 仍取得该工具列表（旧形状不作废）

#### Scenario: client 归一标准 tools/call 结果
- **GIVEN** 标准服务端对 `tools/call` 应答 `{"content": [{"type": "text", "text": "<JSON>"}]}`
- **WHEN** 本 client 解析
- **THEN** 归一为 `CallResult(ok=True, data=<解码后的数据>)`；若应答 `"isError": true`，则归一为 `CallResult(ok=False)` 并承载错误文本（文本为 `{"code": ..., "error": ...}` 时 SHALL 还原该结构化错误码）

#### Scenario: server 以标准容器键应答 tools/list
- **GIVEN** 外部客户端对上本 server 执行 `tools/list`
- **WHEN** server 应答
- **THEN** 应答结果形如 `{"tools": [{"name": "core.tools.file_read", ...}]}`（标准容器键，非裸列表）

#### Scenario: server 以标准信封应答 tools/call
- **GIVEN** 外部客户端调用本 server 的已暴露工具（可成功或未授权）
- **WHEN** server 应答
- **THEN** 应答结果形如 `{"content": [{"type": "text", "text": <JSON 载荷>}], "isError": <bool>}` —— 成功时 `isError` 为假、载荷为工具数据，未授权时 `isError` 为真、载荷含 `{"code": "PERMISSION_DENIED", ...}`

#### Scenario: 第三方客户端直接挂载
- **GIVEN** 一个标准第三方 MCP 客户端（Claude Code / Cursor）
- **WHEN** 其以 stdio 拉起 `core-agent mcp serve` 并完成握手与工具发现
- **THEN** 连接建立、工具列表可见（**真机验收**：`claude mcp add` 挂载本 server 后 `claude mcp list` 报连接成功）
