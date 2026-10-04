# mcp-stdio-transport — MCP stdio 传输生产实现 + 消费侧安全接线（账本 B1/M2）

## Why

账本 B1（`coding-plan/phase-19.md` §4）：Phase 12 的**传输生产实现切片**（`0033-mcp-install-security`
tasks 2.x–4.x）一直未落地 —— 规格 delta 早已合并（`mcp` spec「MCP 客户端消费安全」「MCP Server
安装与移除」），阻断原因（`mcp` SDK 离线不可装 + 零三方依赖红线）已由 **ADR-0043 裁决**：

> ① stdio（client 本地 + server 本地）：**stdlib 手写**（零新依赖）；② http/streamable-http：
> `mcp` SDK 作**可选 extra** + 懒 import。

一手核实的三处残留：

1. **`build_transport` 恒抛错**（`src/core/mcp/transport.py:117`）：`MCP_CONNECT_FAILED`
   「生产传输需 MCP SDK（离线未安装）」——**连本地 stdio 都连不了**，尽管 ADR-0043 明确
   stdio 应零依赖手写。
2. **`MCPClient.add` 硬编码 http**（`client.py:138`）：`MCPEndpoint(transport="http", url=source)`
   → 即便传本地命令也当 http 端点，**不按来源分流**（违反 ADR-0043「按来源形状分流」）。
3. **消费侧零安全接线**：`MCPToolAdapter` 已标注 `coeffects=["network:outbound"]` +
   `reversible=False`（→ 走 `PermissionGuard` 确认门），但**拉起的子进程不经沙箱**、
   **http 出站不经白名单**，「MCP 客户端消费安全」需求的生产等价物不存在。

症状性质与 E1/E4 同族：**规格已写、seam 已在、接缝未接**（死代码/占位）。

## What Changes

- **`StdioTransport`（stdlib 手写，零新依赖）**：`subprocess` 拉起常驻子进程 + 换行分帧
  JSON-RPC（`initialize` / `notifications/initialized` / `tools/list` / `tools/call` / …），
  后台读线程 + 队列超时（`REMOTE_TIMEOUT`），`close` 终止并回收子进程。**同步**实现
  （`Transport` 契约为同步；`asyncio` 反需线程桥接，见 ADR-0057）。
- **`SandboxManager.spawn`**：以资源配额（POSIX rlimit）拉起**常驻**子进程并返回活 `Popen`
  （`run` 是一次性执行，无法承载长连接）；拉起失败降级 `SANDBOX_UNAVAILABLE`。
- **`build_transport` 按端点分派**：`stdio` → `StdioTransport`；`http`/`streamable-http`
  → 出站白名单校验 → `mcp` SDK 懒加载（未装给「`pip install core-agent[mcp]`」提示）。
- **`MCPClient.add` 按来源分流**：`http(s)://` URL → http 端点；本地命令（`shlex` 切分
  或显式 `command`/`args`）→ stdio 端点。`_call` 保留传输层结构化错误码（`MCPError` 直通）。
- **消费侧安全接线**：组合根建 `SandboxManager` + `SandboxPolicy`，经
  `MCPClient(sandbox=…, policy=…)` 注入；`InstallDispatcher` 用该 client。
  `Runtime` 增 `mcp_client` 字段（唯一构造点 `runtime.py`）。
- spec delta：`mcp` —— ADDED「MCP 传输实现与沙箱常驻进程」+ ADDED「MCP 安装分流」
  + MODIFIED「传输层抽象与依赖注入隔离」（补 `build_transport` 分派场景）；
  `permission` —— MODIFIED「沙箱隔离」（补常驻子进程受配额约束场景）。
- `pyproject.toml` 增可选依赖组 `mcp = ["mcp>=1"]`（ADR-0043 的 extra，默认不安装）。

## Non-Goals

- **不实现 http/streamable-http 的真实会话**（`Mcp-Session-Id` 复用 + SSE 分帧）：需 `mcp` SDK
  在目标环境**可安装**（当前 dev 网络对包解析不可靠），记**后续行 B2**。本次只落地
  「白名单校验 + SDK 缺失清晰降级」这半（**可离线验证**的部分）。
- **不做 `MCPServer.serve` 的 stdio 事件循环**（服务端本地）：同属 stdio 帧层但另一消费面，
  记**后续行 B3**。
- **不做 `mcp add/list/remove` CLI 接线**：`MCPClient._named` 仅进程内，CLI 跨进程可见性
  需端点注册表落盘（与 E4 同族的设计决策），记**后续行 B4**。
- **不做出站白名单配置化**（`permission.sandbox.host_allowlist`）：组合根暂以 default
  `SandboxPolicy()`（空白名单 = fail-closed 全拒）装配；配置面属另一变更（记后续行 B5）。
- **不给 stdio 子进程做 fs jail**：可移植的 fs 隔离需 OS 设施（namespaces/bubblewrap），
  既有 `_subprocess_backend` 同样只做 rlimit（对齐先例，设计文档明写）。
- **不动** `Transport` 抽象契约；**不删**任何既有装配路径。

## Impact

- `src/core/permission/sandbox.py`（`SandboxManager.spawn`）
- `src/core/mcp/transport.py`（`StdioTransport` + `build_http_transport` + `build_transport` 分派）
- `src/core/mcp/client.py`（构造注入 `sandbox`/`policy`/`budget`；`add` 分流；`_call` 直通 `MCPError`）
- `src/core/plugins/install.py`（`_install_mcp` 传 transport/command/args）
- `src/core/runtime.py`（组合根建沙箱 + MCP client + `Runtime.mcp_client`）
- `pyproject.toml`（optional-dependencies `mcp`）
- spec：`doc/openspec/specs/{mcp,permission}/spec.md`
- 文档：`doc/03-interfaces/{mcp-interface.md,permission-interface.md}`、`doc/02-modules/mcp.md`、ADR-0057
- 账本：B1 部分关闭（2.1/3.1/4.1/4.2[守卫]/4.3）+ 后续行 B2/B3/B4/B5
