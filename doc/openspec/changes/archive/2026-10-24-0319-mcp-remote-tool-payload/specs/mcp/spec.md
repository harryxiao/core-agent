# Spec Delta — mcp（0319 远端工具结果可序列化）

## MODIFIED Requirements

### Requirement: 调用转发与错误隔离
系统 SHALL 把本地调用透明转发到 MCP，并对 MCP 异常做隔离，不拖垮主循环。远端以 JSON-RPC `error` 应答时，系统 SHALL 按以下口径映射为**本地结构化错误码**（SHALL NOT 一律归为 `MCP_UNAVAILABLE`）：**`tools/call`** 的协议层错误 SHALL 归一为 `MCP_TOOL_NOT_FOUND`（MCP 约定工具**执行**失败走成功应答里的 `isError` 结果信封，故 `tools/call` 上出现 JSON-RPC 错误即**调用本身被拒** —— 未知工具 / 非法参数）；**其余方法**的 `-32700` / `-32600` / `-32601` / `-32602` SHALL 归一为 `MCP_PROTOCOL_MISMATCH`，`-32603` 及未知码 SHALL 归一为 `MCP_UNAVAILABLE`。原始远端码与消息 SHALL 保留在错误文本中。

经插件安装适配进本地工具面的 MCP 工具，其本地 `ToolResult.data` SHALL 是**可 JSON 序列化**的恒定信封 `{"ok": bool, "data": Any, "code": str | null, "error": str | null}`：成功时 `ok=true`、`data` 为远端载荷、`code`/`error` 为 `null`；远端逻辑失败（`isError`）或协议/传输失败时 `ok=false`、`data=null`、`code`/`error` 取本层归一后的字段。SHALL NOT 把 `CallResult` 实例（或其它不可 JSON 序列化对象）作为本地工具结果返回。远端载荷 SHALL ONLY 出现在 `data` 键下，信封顶层 SHALL 恒为上述四键（SHALL NOT 与远端载荷平铺）。远端失败 SHALL NOT 冒充本地执行失败：本地 `ToolResult.ok` SHALL 保持 `true`、SHALL NOT 触发本轮效应回滚，失败信息经信封回喂模型。

#### Scenario: 透明转发
- **GIVEN** 模型调用一个 MCP 工具
- **WHEN** 执行
- **THEN** 请求按协议转发，本地工具结果的 `data` 为 `{"ok": true, "data": <远端载荷>, "code": null, "error": null}`，且该结果可被 JSON 序列化写入观测记录

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

#### Scenario: 远端逻辑失败可序列化回喂
- **GIVEN** 远端 `tools/call` 以 `isError: true` 应答并给出错误正文
- **WHEN** 模型经本地工具面调用该工具
- **THEN** 本地工具调用 `ok` 为 `true`（不触发本轮回滚），结果 `data` 为 `{"ok": false, "data": null, "code": <码或 null>, "error": <远端正文>}`，可作为观测记录写入

#### Scenario: 远端载荷不冒充终止回复
- **GIVEN** 远端成功载荷为 `{"reply": "..."}`
- **WHEN** 本地工具结果写入观测记录
- **THEN** 信封顶层仅有 `ok`/`data`/`code`/`error` 四键，远端载荷原样嵌在 `data` 下，循环 SHALL NOT 把它当作终止回复
