# Proposal — MCP 远端工具结果可序列化（0319）

## Why

用户在 TUI 里调用已安装的 MCP 工具 `mcp.cbm.index_repository` 时，整轮直接崩在 Textual
traceback 上，末行：

```
TypeError: Object of type CallResult is not JSON serializable
```

根因：`InstallDispatcher._remote_tool` 的 handler 把 `MCPClient.call_tool` 的返回值
（`CallResult` dataclass）**原样**作为工具结果返回；`DefaultLoop._record_observation` 用
`json.dumps` 把结果写入观测记录，dataclass 不可序列化 ⇒ 抛 `TypeError`。该异常发生在动作
提交阶段、不属于 `ToolProvider` 的异常归一范围，故既没有结构化错误码、也没有回滚，TUI 直接
以框架异常收场。离线复现确认：`ToolResult(ok=True, data=CallResult(...))` + `json.dumps`
抛同型错误。

同一处还有两个次生口径问题（若简单地把远端失败改判为本地失败会更糟）：

1. `ActionResult.failed=True` 会触发**本轮效应回滚**（`default.py:894`），且观测只写
   `{"error": <错误码字符串>}` —— 远端服务端给出的错误正文与同轮既有成功写入一起丢失；
2. `DefaultLoop.observe` 把顶层含 `reply` 键的结果当作**终止回复** —— 远端载荷若恰好是
   `{"reply": …}`，会被误判为模型最终答复。

## What Changes

- **A（缺陷修复）** 经 `InstallDispatcher` 适配进本地工具面的 MCP 工具，其结果 SHALL 为
  **可 JSON 序列化的恒定信封** `{"ok", "data", "code", "error"}`：成功时 `data` 为远端载荷、
  `code`/`error` 为 `null`；远端逻辑失败（`isError`）或传输/协议失败时 `ok=false`、
  `data=null`、`code`/`error` 取 `CallResult` 对应字段。SHALL NOT 返回 `CallResult` 实例。
- **B（隔离口径）** 远端失败 SHALL NOT 冒充本地执行失败：本地 `ToolResult.ok` 保持 `true`、
  不触发本轮效应回滚，失败信息经信封回喂模型（ReAct 自愈）。
- **C（防误判）** 远端载荷 SHALL 只出现在 `data` 键下（不与环境信封键平铺），信封顶层
  恒为四键 —— `observe` 不会把远端载荷里的 `reply` 当成终止回复。

## Impact

- 代码：`src/core/plugins/install.py`（`_remote_tool` 一处）。
- 测试：新增 `tests/test_mcp_tool_payload.py`（成功信封 / 远端 `isError` / 协议错误码保留 /
  `reply` 不冒充终止）；既有 `tests/test_mcp*.py` / `test_phase16.py` 不回归。
- 规格：`mcp` MODIFIED ×1（「调用转发与错误隔离」补本地信封口径 + 2 个 Scenario）。
- 文档：`doc/03-interfaces/mcp-interface.md` §4/§5、`doc/04-testing/test-cases.md` §232、
  `coding-plan/known-risk.md` E255、ADR-0309。
- **零新配置键、零新依赖、零新工具**；`MCPClient` / 传输层 / 适配器契约逐字不变。

## Out of Scope

- 不改 `DefaultLoop` 失败判定与回滚语义（远端失败仍是「工具调用成功、载荷内失败」）。
- 不给 `_record_observation` 加通用序列化兜底（`default=str`）——那只会掩盖下一个形状违约。
- 不改远端工具的 `coeffects=["network:outbound"]`、`reversible=False` 与确认门行为。
- 不治理 codebase-memory-mcp 自身的 `~` 不展开等问题（服务端行为，属本地调用姿势）。
