# tasks — 远端 JSON-RPC 错误码映射（change 0077）

## 1. 测试先行（红）
- [x] 1.1 `tests/test_mcp_stdio.py`：`_ECHO_SERVER` 增未知工具分支（`tools/call` 非 `echo` → `-32603 "Tool X not found"`）
- [x] 1.2 端到端（真子进程）：`call_tool` 未知工具 → `CallResult.code == MCP_TOOL_NOT_FOUND`
- [x] 1.3 端到端：调不支持的方法（`resources/read`）→ `MCPError.code is MCP_PROTOCOL_MISMATCH`
- [x] 1.4 `map_remote_error` 表驱动：`tools/call` 任意码 → `MCP_TOOL_NOT_FOUND`；`-32700/-32600/-32601/-32602`
      → `MCP_PROTOCOL_MISMATCH`；`-32603`/未知码 → `MCP_UNAVAILABLE`；原始码保留于文本
- [x] 1.5 红证：实现前 1.2 得 `MCP_UNAVAILABLE`、1.3 得 `MCP_UNAVAILABLE`、1.4 import 失败

## 2. 实现（绿）
- [x] 2.1 `src/core/mcp/transport.py`：模块常量 `_JSONRPC_TO_LOCAL` + `map_remote_error(method, error)`
- [x] 2.2 `_await` 改调 `map_remote_error`
- [x] 2.3 绿证：全量 pytest 全绿（基线 940）+ 四门全绿

## 3. 规格
- [x] 3.1 `mcp` spec delta：MODIFIED「调用转发与错误隔离」+ 两新场景
- [x] 3.2 `openspec validate 0077-mcp-remote-error-mapping` 通过

## 4. 文档
- [x] 4.1 `doc/03-interfaces/mcp-interface.md` §8：错误码表后补「远端 JSON-RPC 映射」块
- [x] 4.2 `doc/02-modules/mcp.md`：错误分层处补映射口径
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0074 + 变更追踪行
- [x] 4.4 `doc/04-testing/test-cases.md`：TC-MCP-13

## 5. 收口
- [x] 5.1 `coding-plan/phase-19.md`：§1 表 B8 行、§0 结论、§4 B8 段（→ 已关闭块）、§9 第 5 项、§4 表头计数
- [x] 5.2 `coding-plan/README.md`：状态与依赖行同步
- [x] 5.3 手动归档（合并 delta + 移动目录）+ `openspec validate --all` 全绿
- [x] 5.4 记忆更新 + 提交
