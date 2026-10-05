# design — 远端 JSON-RPC 错误码映射（change 0077 / 账本 B8）

## 一手事实

`StdioTransport._await`（change `0073` 引入）：

```python
error = message.get("error")
if error:
    raise MCPError(
        MCPErrorCode.MCP_UNAVAILABLE,
        f"远端错误: {error.get('code')} {error.get('message')}",
    )
```

码硬编码为 `MCP_UNAVAILABLE` ⇒ 三条不同的远端语义（方法未实现 / 参数错 / 工具不存在）塌缩为同一本地码。

`client._call` 让传输层 `MCPError` **直通**（不被兜底分支重包），`call_tool` 再隔离为 `CallResult`：

```python
except MCPError as exc:
    return CallResult(ok=False, code=exc.code.value, error=exc.message)
```

⇒ 映射的**唯一**落点就是 `_await`，无需动 client。

## 决策

### D1 `tools/call` 的 JSON-RPC 错误 = 「调用被拒」⇒ `MCP_TOOL_NOT_FOUND`
MCP 规范把两类失败**分层**：工具**执行**失败走**成功应答**里的 `isError: true` 结果信封
（本端 server 侧正是如此 —— `call_tool` 返回 `CallResult`，`PERMISSION_DENIED` 之类都在
成功应答内）；**协议层**错误才走 JSON-RPC `error`。因此 `tools/call` 上出现 JSON-RPC 错误，
语义上就是**这次调用本身不被接受**（未知工具 / 非法参数）—— 映射为 `MCP_TOOL_NOT_FOUND`。

**已否决**：按码判（`-32602` → 工具不存在、`-32603` → 保持 `MCP_UNAVAILABLE`）。
实测对端（`claude mcp serve`）对未知工具回的是 **`-32603`**（标准里是 Internal error），
故按码判会把本变更要修的用例**继续漏掉**；且 `-32602` 在 `tools/call` 上同样可表示未知工具，
按码判是伪精确。

### D2 其余方法按标准码映射
`-32700` / `-32600` / `-32601` / `-32602` → `MCP_PROTOCOL_MISMATCH`（请求或方法在协议层不被接受）；
`-32603` 与未知码 → `MCP_UNAVAILABLE`（对端内部问题）。

- `-32601` 与**本端 server 侧**对称：`server.py` 对未知方法回 `_METHOD_NOT_FOUND = -32601`
  ⇒ 本端作为 client 收到 `-32601` 即「对端不支持该方法」，归协议不匹配。
- 已核：无既有用例断言这些路径为 `MCP_UNAVAILABLE`（`test_mcp_stdio.py` 的 echo server 虽对
  未知方法回 `-32601`，但无用例走到该分支并断言码）。

### D3 映射为**可测的纯函数**
`map_remote_error(method, error) -> MCPError` 置于 `transport.py` 模块级：无 IO、无状态，
表驱动单测即可覆盖全码；`_await` 仅一行调用。既便于 `stdio` 端到端真子进程用例，
又避免为「查表」造子进程。

### D4 原始码与消息保留
错误文本仍为 `远端错误: <code> <message>` —— 映射是**加信息**（本地码更准）而非**换信息**（原始码不丢）。
运维排查时仍看得到对端真实码。

### D5 不引消息启发式
「按 `message` 是否含 `not found` 判工具不存在」会引入本地化 / 厂商措辞依赖，且 D1 已用
方法上下文给出了**确定性**判据 ⇒ 不引。

## 兼容性代价

- 破坏面：仅 `StdioTransport._await` 抛出的 `MCPError.code` 取值（更精确）。
- `client` / `server` / 命名空间 / 白名单 / 暴露面**均不变**；http 传输（SDK）不受影响。
- 既有用例零改动即绿（已核无相关断言）。

## 转出

无。
