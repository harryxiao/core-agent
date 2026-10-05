# design — MCP Server 模式 stdio 事件循环（change 0073）

## 决策

### ① 事件循环归属：`MCPServer.serve_stdio(endpoint, ...)`，不自造传输对象

server 侧的 stdio **就是本进程的 stdin/stdout**，不存在「到远端的传输对象」（`StdioTransport`
是 **client 侧** 用来拉起子进程的，方向相反）。故：

- 新增 `serve_stdio(endpoint, *, stdin, stdout)`：按 endpoint **自绑连接**（与 `serve()` 同一条
  `_bind` 路径），再跑循环。`stdin/stdout` 可注入 ⇒ 循环行为可纯内存验证（红→绿无需子进程）。
- 既有的 `serve(transport, endpoint)` **签名不动**（`doc/03-interfaces/mcp-interface.md` §6 已
  文档化），改为委托 `_bind` —— http 方向的事件循环将来在它之上接入。

**已否决**：在 CLI 里 `serve(StdioTransport(), endpoint)`（把 client 侧传输对象摆到 server 侧，
语义错误）；把 `transport` 参数删掉（改已文档化的公开签名）。

### ② 错误分层：协议层错误码与工具层 `CallResult` 分开

| 层 | 载体 | 例 |
|---|---|---|
| 协议层 | JSON-RPC `error`（-32601 未知方法 / -32603 内部异常） | 方法不存在、提供者抛错、应答不可序列化 |
| 工具层 | 成功应答里的 `result` = 序列化 `CallResult` | `PERMISSION_DENIED`（未暴露工具）、工具自身结构化失败码 |

理由：越权是**业务结论**（客户端应当能读到 `PERMISSION_DENIED` 这个码并据此决策），不是协议
故障 —— 与 client 侧 `call_tool` 把 payload 包进 `CallResult(ok=True, data=payload)` 的既有
形状一致。`_respond` **永不抛**：任何单条请求的异常都降级为该 `id` 的错误应答，循环继续（规格
「请求异常不终止事件循环」）；`_encode` 另有一层「应答不可序列化」降级。

### ③ 暴露面：`core.` 前缀 + 白名单归一 + 禁二级代理

- **前缀**：对外名 `core.<tool_id>`（`doc/07-mcp-server/mcp-server.md` §4 与接口 §6 早已写明）。
  命名空间把三组名字隔开：本地 `tools.*` / 远程 `mcp.*` / 对外 `core.*`。
- **白名单归一**：接受裸名与 `core.` 前缀名两种写法。理由：用户最自然的写法是照 `tools/list`
  应答**抄名字**（带前缀），若只认裸名则「配了却不匹配」且**静默**（与 B5 的「配了却连不上」同型）。
- **禁二级代理**：`list_tools` 过滤 `mcp.*`。规格场景「远程工具不被二级代理暴露」+ 模块设计 §4；
  两个 core-agent 互相挂载会让暴露面沿 `core.mcp.core.mcp...` 递归膨胀。

### ④ 协议版本常量同源

`PROTOCOL_VERSION` 移入 `models.py`（client 与 server 共同依赖的最小模块），client 侧原私有
`_PROTOCOL_VERSION` 删除。理由：握手的**判定在 client、应答在 server**，两处各写一份字面量是
「改一处忘一处」的典型漂移面；常量放在二者都依赖的 `models` 里，不引入 client↔server 依赖边。

### ⑤ 沿用仓内 wire 形状（**已知偏离标准 MCP envelope**）

`tools/list` 应答为**裸列表**、`tools/call` 应答为 `CallResult` 直出。二者与
`MCPClient` / `FakeTransport` / 既存 echo server 三方一致（change 0054 确立），本变更不擅自
改契约（改则三处联动且本变更主题是**接线**）。

**代价（明说）**：标准 MCP 服务端/客户端用 `{"tools": [...]}` / `{"content": [...], "isError": ...}`
封装，故 **Claude Code / Cursor 等第三方客户端直接挂载本 server 尚不可用** —— 已登记为新账本行
（B3 关闭的残余），对齐标准 envelope 属独立变更。

## 已知接受项 / 后续

- `mcp serve --transport http|streamable-http` 明确拒绝（HTTP 会话与 `Mcp-Session-Id` 复用未接入）。
- `mcp list/add/remove` 仍为 stub（账本 B4：端点注册表跨进程持久化）。
- 默认暴露面沿用既有 `_is_readonly`（coeffects 不含 `write`）**粗粒度**启发式 ⇒
  `tools.delegate` / `tools.web_fetch` 亦在默认暴露面（**新登记账本行**，是否收窄待裁决）。
