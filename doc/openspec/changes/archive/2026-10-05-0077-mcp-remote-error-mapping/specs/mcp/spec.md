# mcp spec delta — mcp-remote-error-mapping（change 0077 / 账本 B8）

**远端 JSON-RPC 错误按「方法 + 标准码」映射为本地结构化码，不再一律 `MCP_UNAVAILABLE`。**

## MODIFIED Requirements

### Requirement: 调用转发与错误隔离
系统 SHALL 把本地调用透明转发到 MCP，并对 MCP 异常做隔离，不拖垮主循环。远端以 JSON-RPC `error` 应答时，系统 SHALL 按以下口径映射为**本地结构化错误码**（SHALL NOT 一律归为 `MCP_UNAVAILABLE`）：**`tools/call`** 的协议层错误 SHALL 归一为 `MCP_TOOL_NOT_FOUND`（MCP 约定工具**执行**失败走成功应答里的 `isError` 结果信封，故 `tools/call` 上出现 JSON-RPC 错误即**调用本身被拒** —— 未知工具 / 非法参数）；**其余方法**的 `-32700` / `-32600` / `-32601` / `-32602` SHALL 归一为 `MCP_PROTOCOL_MISMATCH`，`-32603` 及未知码 SHALL 归一为 `MCP_UNAVAILABLE`。原始远端码与消息 SHALL 保留在错误文本中。

#### Scenario: 透明转发
- **GIVEN** 模型调用一个 MCP 工具
- **WHEN** 执行
- **THEN** 请求按协议转发，结果归一化为本地工具返回结构

#### Scenario: MCP 异常隔离
- **GIVEN** MCP 服务端超时/崩溃
- **WHEN** 调用失败
- **THEN** 返回 `MCP_UNAVAILABLE`，熔断该 MCP，不影响其他工具

#### Scenario: 远端工具不存在映射为工具不存在
- **GIVEN** 远端对未知工具回 JSON-RPC 错误（如 `{"code":-32603,"message":"Tool X not found"}`）
- **WHEN** 本地 `call_tool` 该工具
- **THEN** 返回 `CallResult(ok=False, code="MCP_TOOL_NOT_FOUND")`，而非笼统的 `MCP_UNAVAILABLE`

#### Scenario: 远端方法未实现映射为协议不匹配
- **GIVEN** 远端对不支持的方法回 JSON-RPC `-32601`
- **WHEN** 本地调用该方法
- **THEN** 错误码归一为 `MCP_PROTOCOL_MISMATCH`（非 `MCP_UNAVAILABLE`）
