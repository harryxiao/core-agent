# Tasks — mcp-stdio-transport

## 1. 规格先行
- [x] 1.1 mcp delta（MODIFIED 传输层抽象[分派场景] + MODIFIED 安装与移除[来源分流场景] + ADDED 传输实现与沙箱常驻进程）
- [x] 1.2 permission delta（MODIFIED 沙箱隔离[常驻子进程受配额场景]）
- [x] 1.3 `openspec validate 0054-mcp-stdio-transport` 全绿

## 2. 测试先行（先红）
- [x] 2.1 `SandboxManager.spawn`：拉起常驻子进程受 rlimit 约束（写内存超配额 → QUOTA/信号终止）；后端不可用 → SANDBOX_UNAVAILABLE
- [x] 2.2 `StdioTransport` 端到端：真实子进程（stdlib echo MCP server）握手 + `tools/list` + `tools/call`，请求/响应按 id 配对
- [x] 2.3 `StdioTransport.close`：子进程被终止回收（`poll() is not None`）
- [x] 2.4 `StdioTransport` 超时：服务端不响应 → `REMOTE_TIMEOUT`（不永久阻塞）
- [x] 2.5 `build_transport` 分派：stdio → StdioTransport；未知 transport → 结构化错误
- [x] 2.6 `build_http_transport`：非白名单 host → `PERMISSION_DENIED`；白名单 + 无 SDK → `MCP_CONNECT_FAILED`（含安装提示）；白名单 + 有 SDK → 明确「会话待接入」
- [x] 2.7 `MCPClient.add` 分流：URL → http 端点；命令行 → stdio 端点；显式 command 覆盖
- [x] 2.8 `MCPClient._call` 直通传输层 `MCPError`（结构化错误码不被重包为 MCP_UNAVAILABLE）
- [x] 2.9 消费侧确认门：`MCPToolAdapter` 适配的工具经 `PermissionGuard.confirm` → `GateDecision("confirm")`
- [x] 2.10 生产装配：`build_runtime` 后 `runtime.mcp_client` 非空且其沙箱已注入
- [x] 2.11 回归：`tests/test_mcp.py` 既有连接/心跳/重连/异常隔离用例不变；`test_architecture.py` 分层不破

## 3. 实现
- [x] 3.1 `permission/sandbox.py`：`SandboxManager.spawn(cmd, env, budget) -> Popen`
- [x] 3.2 `mcp/transport.py`：`StdioTransport`（Popen + 读线程 + 队列超时 + 换行分帧）
- [x] 3.3 `mcp/transport.py`：`build_http_transport`（白名单 → SDK 懒加载）+ `build_transport` 分派
- [x] 3.4 `mcp/client.py`：构造注入 `sandbox`/`budget`/`policy`；`add` 分流；`_call` 直通 `MCPError`
- [x] 3.5 `plugins/install.py`：`_install_mcp` 传 transport/command/args
- [x] 3.6 `runtime.py`：组合根建 `SandboxPolicy`/`SandboxManager`/`MCPClient` + `Runtime.mcp_client`
- [x] 3.7 `pyproject.toml`：optional-dependencies `mcp = ["mcp>=1"]`

## 4. 文档同步
- [x] 4.1 `doc/03-interfaces/mcp-interface.md`（stdio/http 传输实现 + 来源分流 + 沙箱接线）
- [x] 4.2 `doc/03-interfaces/permission-interface.md` §6（`SandboxManager.spawn` 常驻子进程）
- [x] 4.3 `doc/02-modules/mcp.md`（传输实现现状 + 组合根装配）
- [x] 4.4 `doc/01-architecture/adr.md` ADR-0057 + 文末映射表行

## 5. 门禁与归档
- [x] 5.1 四门全绿：ruff check/format · pyright · pytest · openspec validate --all
- [x] 5.2 手动归档（合 delta → mv 到 `archive/<date>-0054-mcp-stdio-transport/`）
- [x] 5.3 账本 B1 部分关闭 + 后续行 B2/B3/B4/B5
- [x] 5.4 提交（`feat(mcp): stdio 传输生产实现 + 消费侧安全接线（change 0054）`）
