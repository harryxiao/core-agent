# Design — mcp-stdio-transport

## 决策 1：stdio 传输用**同步** `subprocess`，而非 ADR-0043 字面的 `asyncio.create_subprocess_exec`

**背景**：`Transport` 契约为**同步**（`connect/call/ping/close` 皆 `def`），`MCPClient`、
`MCPServer`、`ToolProvider` 全链同步。ADR-0043 的决策是「stdio = stdlib 手写、零新依赖」，
其中 `asyncio` + `create_subprocess_exec` 是**实现建议**而非契约。

**决策**：`StdioTransport` 用 `subprocess.Popen(text=True)` + 后台读线程 + `queue.Queue`
承载 stdout 行；`call` 写请求行、按 `id` 配对响应、队列 `get(timeout=budget.timeout_s)`。

**理由**：`asyncio.create_subprocess_exec` 是 **async**，在同步契约里必须再起线程跑事件循环
才能桥接 —— 反而多一层。`Popen` + 读线程与同步契约**零阻抗**、行分帧天然（MCP stdio 即
换行分帧）、超时可确定性控制。

**否决**：① `asyncio` + `run_coroutine_threadsafe`（同步契约下更复杂，且 loop 生命周期管理
是纯负担）；② 阻塞式 `readline()`（无超时，服务端挂起会永久卡死模型循环）。

## 决策 2：沙箱常驻进程用 `SandboxManager.spawn`，不复用 `run`

**背景**：规格「MCP 客户端消费安全」要求 stdio 子进程**经沙箱隔离**（资源配额 + 受控），
但 `SandboxManager.run` 是**一次性** `subprocess.run(...)`（run-to-completion 返回
`SandboxResult`），**无法**承载 MCP 的长连接 stdin/stdout 管道。

**决策**：`SandboxManager` 增 `spawn(cmd, env, budget) -> subprocess.Popen`：复用既有
`_apply_resource_limits`（POSIX rlimit 的 `preexec_fn`），返回**活** `Popen`，句柄归调用方
（transport）持有并在 `close` 时终止；拉起失败降级 `SANDBOX_UNAVAILABLE`。

**理由**：内核安全链路的 owner 是 `permission` —— 让 transport 自己写 `preexec_fn` 等于**第二份**
rlimit 实现（与 `_subprocess_backend` 重复）。`run` 与 `spawn` 互补（一次性 vs 常驻），
共享同一 `_apply_resource_limits`，零重复。

**接受**：可移植的 **fs jail** 需 OS 设施（namespaces/bwrap），`spawn` 只做 rlimit + 调用方
自控 `env`。这与既有 `_subprocess_backend` 的限制**一致**（先例对齐），在设计文档与
接口文档明写，不假称已实现 fs 隔离。

## 决策 3：http 只落地「白名单守卫 + SDK 缺失降级」，真实会话后置

**背景**：ADR-0043 裁 http/streamable-http 走 `mcp` SDK 懒 import；但 SDK 在当前环境
**不可安装**（离线），真实 `Mcp-Session-Id` 会话**无法离线验证**。

**决策**：本次 `build_http_transport` 只做两件**可离线验证**的事：① `urlparse` 取 host →
`SandboxPolicy.check_outbound`（非白名单以 `PERMISSION_DENIED` 拒绝）；②
`importlib.util.find_spec("mcp") is None` → `MCP_CONNECT_FAILED` + 「`pip install core-agent[mcp]`」。
SDK 存在时仍明确报「会话待接入」（**不写无法验证的投机代码**，CLAUDE.md §2）。

**否决**：凭 ADR 想象写完整 SDK 适配层 —— 不可运行、不可类型检查、不可测试，等于把
未验证代码当交付。真实会话记后续行 B2。

## 决策 4：`MCPClient.add` 按来源形状分流；`_call` 直通传输层结构化错误

`add(source, name, *, transport=None, command=None, args=None)`：
显式 `transport`/`command` 优先；否则 `http(s)://` → http 端点；其余 `shlex.split` → stdio
`command+args`。既有 `client.add("https://…", "files")` 行为**不变**（仍 http）。

`_call` 增 `except MCPError: raise`（在 `KeyError` / 兜底 `Exception` 之前）——否则传输层抛出的
`PERMISSION_DENIED`/`REMOTE_TIMEOUT` 会被兜底分支重包成 `MCP_UNAVAILABLE`，**结构化错误码丢失**
（`connect` 已有同款 `except MCPError: raise` 先例）。

## 决策 5：组合根装配沙箱 + MCP client，`Runtime` 增 `mcp_client`

`build_runtime` 建一份 `SandboxPolicy()` + `SandboxManager(policy=…)`，据此建
`MCPClient(sandbox=…, policy=…)`，传入 `InstallDispatcher(mcp_client=…)`；
`Runtime` 增 `mcp_client` 字段（唯一构造点 `runtime.py`，对齐 `pet_manager`）。

空白名单 = **fail-closed 全拒**出站 —— 安全默认，且使「非白名单 host 拒绝」在生产可见。
白名单配置化（`permission.sandbox.host_allowlist`）属配置面变更，记后续行 B5。

## 决策 6：4.3「不可逆确认门」为**验证**项，非新代码

一手核实：`MCPToolAdapter.adapt` 已标 `coeffects=["network:outbound"]` + `reversible=False`；
`PolicyEngine.classify` 见 `network:` 前缀 coeffect → `HIGH_RISK` → `authorize` 返回
`approval_required=True` → `PermissionGuard.confirm` → `GateDecision("confirm")`。
故「远程工具高危确认」的生产链路**已成立**，本变更只补**端到端验证测试**（防回归），不写新代码。
审计落盘沿用工具层既有 observability 链路。

## 风险与接受项

- **接受**：stdio 子进程 fs 隔离仅到 rlimit（决策 2）；fs jail 记后续。
- **接受**：http 真实会话后置（决策 3）→ `mcp` spec「安装远端 http MCP Server」场景的
  「建立网络连接」在生产**尚不可达**（白名单守卫与错误降级可达）。
- **接受**：`MCPClient._named` 仍进程内 → CLI 跨进程可见性后置（B4）。
- **接受**：读线程为 daemon；`close` 未 join 线程（进程终止后 `readline` 返空自然退出），
  不引入显式 join 以避免在子进程异常时长阻塞。
