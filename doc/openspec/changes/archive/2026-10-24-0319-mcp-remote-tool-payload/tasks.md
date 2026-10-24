# Tasks — MCP 远端工具结果可序列化（0319）

> 规格先行：先落 `mcp` MODIFIED ×1，再红→绿。
> 台账编号让位并行 change `0318`（ADR-0308／E254／§231 预留），本 change 用 ADR-0309／E255／§232。

## 1. 规格

- [x] 1.1 `specs/mcp/spec.md`：MODIFIED「调用转发与错误隔离」——补本地信封口径（恒定四键、
  可 JSON 序列化、不返回 `CallResult`、远端失败不回滚、载荷嵌套）；改写 Scenario「透明转发」，
  新增「远端逻辑失败可序列化回喂」「远端载荷不冒充终止回复」。
- [x] 验证：`openspec validate 0319-mcp-remote-tool-payload` 绿。

## 2. 红测（先写、确认失败）

- [x] 2.1 `tests/test_mcp_tool_payload.py::test_remote_tool_success_returns_serializable_envelope`：
  成功调用 ⇒ `data` 顶层恰为四键、`json.dumps` 成功、`data["data"]` 为远端载荷。
- [x] 2.2 `tests/test_mcp_tool_payload.py::test_remote_is_error_is_fed_back_not_raised`：
  远端 `isError` ⇒ 本地 `ok is True`、信封 `ok=false` 且保留远端正文。
- [x] 2.3 `tests/test_mcp_tool_payload.py::test_remote_protocol_error_keeps_code`：
  `tools/call` 协议层错误 ⇒ 信封 `code` 保留（`MCP_TOOL_NOT_FOUND`）。
- [x] 2.4 `tests/test_mcp_tool_payload.py::test_remote_reply_payload_is_not_terminal`：
  远端载荷 `{"reply": …}` ⇒ 信封顶层无 `reply` 键。
- [x] 验证：四条用例在未改动实现前**均红**（首条即 `TypeError: Object of type CallResult
  is not JSON serializable`）。

## 3. 实现

- [x] 3.1 `src/core/plugins/install.py`：`_remote_tool` 的 handler 把 `CallResult` 转成信封
  `{"ok", "data", "code", "error"}`（四键恒在）。
- [x] 验证：四条红测转绿；`tests/test_mcp*.py` / `test_phase16.py` / `test_plugin_installs.py`
  不回归。

## 4. 门禁

- [x] 4.1 `uv run pytest`（全量）全绿。
- [x] 4.2 `uv run ruff check src tests` + `uv run ruff format --check src tests` 干净。
- [x] 4.3 `uv run pyright` 无新增错误。
- [x] 4.4 反证（`cp` → `/tmp` 改坏 → 复原 → `md5sum` 比对）：
  - handler 回到返回 `CallResult` ⇒ 2.1~2.4 红；
  - 信封改成成功时平铺载荷 ⇒ 2.4 红；
  - 远端失败透传为本地 `ok=False` ⇒ 2.2 / 2.3 红。
- [x] 4.5 `openspec validate --all`：合入时 34/0；归档后 33/0（并行的 `0305` / `0318` 仍为 active）。

## 5. 文档与台账

- [x] 5.1 `doc/01-architecture/adr.md`：ADR-0309（MCP 远端工具结果信封化；被拒：`default=str`
  兜底、成功平铺、远端失败透传）。
- [x] 5.2 `doc/04-testing/test-cases.md`：§232 用例表。
- [x] 5.3 `coding-plan/known-risk.md`：E255（远端逻辑失败在本地可观测面记为成功、信封不改远端
  参数语义）。
- [x] 5.4 `doc/03-interfaces/mcp-interface.md`：§4 / §5 补本地工具结果信封口径。

## 6. 收口（须用户确认）

- [ ] 6.1 归档 `openspec archive 0319-mcp-remote-tool-payload -y`。
- [ ] 6.2 提交（`fix(mcp): …（change 0319 / ADR-0309 / 台账 E255）`）。
- [ ] 6.3 推送 `origin/phase20-base`。
