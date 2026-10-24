# Design — MCP 远端工具结果可序列化（0319）

## 证据

| # | 观察 | 数值 / 来源 |
|---|---|---|
| E1 | TUI 调用 `mcp.cbm.index_repository` 整轮崩溃，末行 `TypeError: Object of type CallResult is not JSON serializable`；栈顶 `json.dumps` | 用户实测；`src/core/loop/default.py:1528`（`_record_observation`） |
| E2 | 离线复现：`ToolProvider.ainvoke("mcp.files.search", …)` 返回 `ToolResult(ok=True, data=CallResult(ok=True, data={'result': 'ok:search'}, code=None, error=None))`；对该 `data` 做 `json.dumps` 抛同型 `TypeError` | `uv run python` 复现脚本（resolver 注册 `network:outbound`、`approved=True`） |
| E3 | 根因点：handler 直接 `return self._mcp.call_tool(handle, name, dict(kwargs))`，`MCPClient.call_tool` 的返回类型是 `CallResult` | `src/core/plugins/install.py:119-123`；`src/core/mcp/client.py:211-216` |
| E4 | 若把远端失败改判为本地失败（`ToolResult.ok=False`）：该动作会 `rollback(trace_id)`，观测只落 `{"error": <码字符串>}`，远端错误正文丢失 | `src/core/loop/default.py:894`、`1519-1526` |
| E5 | `observe` 把顶层含 `reply` 的数据当作终止回复并结束本轮 | `src/core/loop/default.py:1550-1553` |

## 决策

### D1 本地工具结果信封化（修复）

`_remote_tool` 的 handler 把 `CallResult` 转成**恒定四键信封**：

```python
{"ok": result.ok, "data": result.data, "code": result.code, "error": result.error}
```

- 四键恒在（成功时 `code`/`error` 为 `null`）：模型与测试无需按成败分支，形状单一。
- 全部字段均为 JSON 原生类型（`CallResult.data` 来自 JSON 反序列化）⇒ `_record_observation`
  的 `json.dumps` 恒成功；`action_completed` 的摘要（`str(data)`）也不再是 dataclass repr。
- 远端失败（`isError` / `MCP_TOOL_NOT_FOUND` / `MCP_UNAVAILABLE` 等）已在
  `MCPClient.call_tool` 归一为 `CallResult(ok=False, code, error)`，此处只需搬运，不新增错误码。
- **被拒**：① 在 `_record_observation` 加 `json.dumps(..., default=str)` 兜底 —— 把契约违约
  点留在源头之外，模型看到的是 `"CallResult(...)"` 字符串，语义仍错，且下一个不可序列化形状
  照样穿透；② 成功时直接返回 `result.data`、失败时返回 `{"error": …}` —— 形状随成败漂移，
  且成功/失败两条路径仍可能撞上 E5 的 `reply` 键。

### D2 远端失败不冒充本地失败（隔离口径）

handler 恒返回普通值（不抛、也不让 `ToolResult.ok=False`），因此：

- 本轮**不回滚**：远端工具多为不可逆外部副作用，绑定本地回滚只会让同轮既有写入陪葬；
- 远端 `error` / `code` 正文逐字进观测，模型可据此调整参数或换工具（ReAct 自愈）；
- 代价：可观测面把这种调用记为「工具调用成功」、载荷内 `ok=false` —— 这是既有「异常隔离」
  语义的延续（MCP 服务端故障不拖垮主循环），不是新增静默。
- **被拒**：把远端 `ok=False` 透传为 `ToolResult(ok=False)` —— 见 E4（丢正文 + 回滚副作用）。

### D3 载荷嵌套，信封顶层恒四键（防误判）

远端载荷只出现在 `data` 下，信封顶层不出现远端键 ⇒ `observe` 的 `"reply" in data` 只看信封
四键，远端 `{"reply": …}` 不会终止本轮。**被拒**：把远端载荷与信封键平铺（键冲突不可避免）。

## 规格映射

- `mcp` MODIFIED「调用转发与错误隔离」：补本地信封口径（可 JSON 序列化、恒四键、SHALL NOT
  返回 `CallResult`）、远端失败不回滚不冒充失败、载荷嵌套；Scenario「透明转发」改写为信封
  断言，新增「远端逻辑失败可序列化回喂」「远端载荷不冒充终止回复」。

## 测试与反证

- 正证（`tests/test_mcp_tool_payload.py`，经真实 `InstallDispatcher` + `FakeTransport`）：
  1. 成功调用 ⇒ `ToolResult.ok is True`；`data` 顶层键恰为 `{ok,data,code,error}`；`json.dumps`
     成功；`data["data"]` 为远端载荷、`code`/`error` 为 `None`；
  2. 远端 `isError` 信封 ⇒ 本地 `ok is True`、`data["ok"] is False`、`data["error"]` 保留远端
     正文；
  3. `tools/call` 协议层错误（`MCP_TOOL_NOT_FOUND`）⇒ 信封 `code` 保留、可序列化；
  4. 远端成功载荷为 `{"reply": "x"}` ⇒ 信封顶层无 `reply` 键，载荷在 `data` 下。
- 反证（`cp` → `/tmp` 改坏 → 复原 → `md5sum`）：
  1. handler 回到返回 `CallResult` ⇒ 四条用例红（首条即 `TypeError`）；
  2. 信封改成「成功平铺载荷」⇒ 第 4 条红；
  3. 远端失败透传 `ok=False`（本地失败）⇒ 第 2/3 条红。

## 局限

- 可观测面仍把远端逻辑失败记为工具调用成功（载荷内 `ok=false`）；若将来需要按远端成败
  计数，须另加带语义的指标，不能靠 `ActionResult.failed`。
- 信封不改变远端 `CallResult.data` 的不可控性：若某传输实现返回非 JSON 原生对象，仍需在该
  实现内归一（现行 `_parse_call_result` 只做 JSON 解码，天然满足）。
- 不改 MCP 服务端自身行为（如 codebase-memory 不展开 `~`），本地仍按原样转发参数。
