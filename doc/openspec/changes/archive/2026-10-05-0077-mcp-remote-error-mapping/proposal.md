# 远端 JSON-RPC 错误码映射（mcp-remote-error-mapping）

## Why

账本 **B8**（远端 JSON-RPC 错误码未映射，change `0075` 对齐标准 envelope 时实测转出）。
`StdioTransport._await` 把**一切**远端 JSON-RPC `error` 包成 `MCPError(MCP_UNAVAILABLE)` ——
无论对端说的是「方法未实现」「参数非法」「工具不存在」还是「内部异常」，本端一律表现为
**服务端不可用**。

一手实测（change `0075`，对 `claude mcp serve` 发标准 `tools/call` 打不存在的工具）：

```json
{"error":{"code":-32603,"message":"Tool no_such_tool not found"},"id":4}
```

⇒ 本端 `call_tool` 返回 `CallResult(ok=False, code="MCP_UNAVAILABLE")`，与「服务端崩了」
**同码**。调用方（模型）无法据此区分「工具名写错了」与「远端挂了」，前者当场可自纠、
后者该熔断重试 —— 属错误**语义丢失**，非仅文案问题。

## What Changes

- `src/core/mcp/transport.py`：新增模块级纯函数 `map_remote_error(method, error) -> MCPError`
  —— 把远端 JSON-RPC `error` 按口径映射为本地结构化码（`_await` 改调用它）：
  - **`tools/call` 的协议层错误 → `MCP_TOOL_NOT_FOUND`**：MCP 约定工具**执行**失败走成功应答里的
    `isError` 结果信封（本端 server 侧即如此），故 `tools/call` 上出现 JSON-RPC 错误即**调用本身被拒**
    （未知工具 / 非法参数）—— 归「工具不存在」而非「服务端不可用」。
  - **其余方法**按标准码：`-32700`（Parse）/ `-32600`（Invalid Request）/ `-32601`（Method not found）/
    `-32602`（Invalid params）→ `MCP_PROTOCOL_MISMATCH`；`-32603`（Internal error）与未知码 →
    `MCP_UNAVAILABLE`。
  - 原始远端码与消息**保留在错误文本中**（`远端错误: <code> <message>`），不吞信息。
- 规格 delta：`mcp` spec **MODIFIED**「调用转发与错误隔离」—— 写明远端协议错误的映射口径 + 新场景。
- 测试：`tests/test_mcp_stdio.py` 增 `_ECHO_SERVER` 未知工具分支 + 端到端用例（真子进程）+
  `map_remote_error` 纯函数表驱动用例。

## Non-goals

- **不**改 `tools/call` 之外的调用路径语义（`list_tools` / `read_resource` / `get_prompt` 照旧抛 `MCPError`，
  仅码更精确）。
- **不**引入消息文本启发式（如按 `message` 含 "not found" 判工具不存在）—— 码 + 方法上下文已足，
  文案依赖脆弱（本地化 / 厂商措辞）。
- **不**动 http/streamable-http 传输（走 `mcp` SDK，错误码由其映射；当前离线不可装）。
- **不**新增本地错误码（现有码集已能表达；新增码会波及 `MCPErrorCode` 的对外契约）。

## 风险

- **`tools/call` 归一只看方法不看码** —— 若某服务端把「工具内部异常」错报为 JSON-RPC 错误
  （而非 `isError` 结果），会被本端记成「工具不存在」。属对端**违反 MCP 约定**；本地码仍为 `ok=False`，
  且原始码保留在文本中，影响面限于码取值的精确性。
- **`-32601` 方法未实现 → `MCP_PROTOCOL_MISMATCH`**：与既有 server 侧（本端对未知方法回 `-32601`）
  对称；无既有用例断言该路径为 `MCP_UNAVAILABLE`（已核）。
