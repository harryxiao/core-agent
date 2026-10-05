# Phase 12 — MCP 安装/传输/安全接线（本地 stdio 沙箱 + 远端网络管控）

> 里程碑：**无独立里程碑（DEFERRED，待 ADR 重开）**
> 位置：横切 mcp（传输层生产实现 + 客户端安装分流 + 消费侧安全）+ 权限沙箱（SandboxManager）
> 上游：mcp（传输抽象/连接管理/工具适配，Phase 2 已落地）+ permission（SandboxManager 沙箱）+ plugin_registry（PluginSource.MCP_ENDPOINT）
> 对应 change：`openspec/changes/0033-mcp-install-security`（10 tasks，**正式延期 DEFERRED**）

> ⚠ **本 Phase 处于 DEFERRED 状态**。全部代码条目（transport 生产实现 / client 安装分流 / 消费侧安全接线）因「引入 `mcp` SDK 触及 litellm 唯一运行时三方依赖红线 + 离线不可安装」正式延期，**不随当前里程碑交付**。本计划是**重开预案**：记录延期理由、重开条件与落地步骤，待前置条件满足后按此执行，**不是当下开工指令**。

---

## 1. 范围与定位

本 Phase 补齐 core-agent 作为 **MCP client 消费方**（导入三方/本地 MCP server）的三条接线缺口，交付 3 块能力：

| 能力块 | 职责一句话 | 分层 |
|---|---|---|
| transport 生产实现 | stdio / http / streamable-http 真实传输（替换 `build_transport` 占位抛错） | 横切 mcp |
| client 安装分流 | `MCPClient.add` 按 transport 分流构建 `MCPEndpoint`（stdio `command+args` / http `url+headers`） | 横切 mcp |
| 消费侧安全 | 本地 stdio 子进程沙箱 + 远端 http 出站白名单 + 不可逆工具确认门 | 横切权限/观测 |

**核心机制（三条铁律）**：

1. **传输生产实现依赖 MCP SDK**。stdio/http 生产传输需引入 `mcp` SDK（懒 import），这是延期的**根因**：离线不可安装、且触及「litellm 唯一运行时三方依赖」红线，须先 ADR 评估「懒 import 可选依赖 vs 边界依赖」。
2. **消费侧安全对齐本地工具链路**。外部 MCP 暴露的工具经 `MCPToolAdapter` 标注 coeffects（`network:outbound` 等）+ `reversible=False`，走与本地工具一致的 permission 确认门与 observability 审计，不绕过内核安全链路。
3. **安装复用插件来源**。`mcp add` 复用 `PluginSource.MCP_ENDPOINT` 经 discover → verify → install → register 进入现有连接管理；`mcp remove` 经 deactivate → uninstall 释放连接/会话/socket（含本地子进程销毁）。

## 2. 契约红线（实证现状 vs 契约）

### 2.1 已就绪契约

| 契约 | 实证落点 |
|---|---|
| `mcp-interface.md`（§2 传输 / §4 适配器 / §7 错误码） | `doc/03-interfaces/mcp-interface.md` 已定稿 |
| 传输抽象 `Transport`（connect/call/ping/close）+ `FakeTransport` 测试替身 | `src/core/mcp/transport.py` |
| 连接管理 `MCPClient`（connect/close/心跳/复用） | `src/core/mcp/client.py` |
| 工具适配 `MCPToolAdapter.adapt()` **已标注** `coeffects=["network:outbound"]` + `reversible=False` | `src/core/mcp/adapter.py`（4.3 已部分落地） |
| 沙箱 `SandboxManager`（子进程隔离 + 出站白名单） | `src/core/permission/sandbox.py` |
| 插件来源 `PluginSource.MCP_ENDPOINT` | `src/core/plugin_registry/` |

### 2.2 契约缺口（须走 OpenSpec 变更补齐）

| 缺口 | 现状 | 补法 |
|---|---|---|
| 「MCP 客户端消费安全」ADDED delta **未落 base spec** | `openspec/specs/mcp/spec.md` 无此需求（`MCP Server 安装与移除` MODIFIED 已在） | 重开时先 `openspec archive 0033`（落 ADDED delta）→ 代码 → 再归档 |
| `build_transport` 生产实现占位抛错 | `transport.py` 抛 `MCP_CONNECT_FAILED`（注释「M2 接入」） | stdio/http/streamable-http 真实实现（懒 import MCP SDK） |
| `MCPClient.add` 硬编码 `transport="http"` | `client.py:138` `MCPEndpoint(transport="http", url=source)` | 按来源分流：本地 stdio（command+args）/ 远端 http（url+headers） |
| 消费侧安全未接线 | 本地 stdio 未过沙箱、远端 http 未走白名单、不可逆工具未走确认门 | stdio 过 `SandboxManager` + http 走出站白名单 + `reversible=False` 工具确认门 |

## 3. 验收口径（重开后）

- **stdio transport**：懒 import MCP SDK，以 `command+args` 拉起本地子进程，`initialize` 握手 + 工具发现跑通。
- **http / streamable-http transport**：懒 import SDK，连接 + `Mcp-Session-Id` 会话复用。
- **安装分流**：`MCPClient.add` 按来源分流（stdio `command+args` / http `url+headers`）构建 `MCPEndpoint`，进入现有连接管理。
- **消费侧安全**：stdio 子进程在 `SandboxManager` 沙箱内（资源配额 + 受限文件系统 + 出站白名单），越界拒绝；http 请求走出站网络白名单；不可逆工具触发 permission 确认门 + observability 审计，来源标注外部 MCP。

## 4. 首步任务（重开时执行）

1. **ADR 评估（重开前置，本 Phase 的第一件事）**：新增 ADR，评估 `mcp` SDK 的依赖定位——「懒 import 可选依赖（optional-dependencies extra，默认不装）vs 边界依赖（与 fastapi/uvicorn/textual 同级）」，结论须守住「litellm 唯一运行时三方依赖」红线；SDK 可安装是硬前置。
2. **落 ADDED delta**：`openspec archive 0033-mcp-install-security` 使「MCP 客户端消费安全」落 base spec（或先 `openspec validate --all` 确认 delta 状态再归档）。
3. **读接口原文**：`doc/03-interfaces/mcp-interface.md` §2（传输契约）/ §4（适配器）/ §8（错误码）为唯一真源；`doc/03-interfaces/permission-interface.md` 确认 `SandboxManager` 子进程隔离 + 出站白名单方法签名。
4. **确认沙箱/白名单契约**：`src/core/permission/sandbox.py` 现有能力是否覆盖「子进程资源配额 + 受限文件系统 + 出站白名单」，缺则先补 permission 侧。

## 5. 依赖与顺序

```
permission(SandboxManager 沙箱 + 出站白名单) ─┐
plugin_registry(PluginSource.MCP_ENDPOINT) ───┼─► ADR 评估(mcp SDK 依赖定位) ─► transport 生产实现(stdio/http)
mcp(transport 抽象 / client 连接管理) ─────────┘                              ─► client 安装分流(add 分流)
observability(不可逆工具审计) ────────────────────────────────────────────────► 消费侧安全(stdio 沙箱 + http 白名单 + 确认门)
```

- **硬前置**：`mcp` SDK 可安装 + ADR 评估依赖红线通过（未满足则本 Phase 继续 DEFERRED）。
- **顺序**：ADR → 落 ADDED delta → transport 生产实现（stdio/http/streamable-http）→ client 安装分流 → 消费侧安全接线（stdio 沙箱 / http 白名单 / 确认门）→ 验证。
- **并行**：stdio 与 http transport 生产实现可并行；消费侧安全依赖 permission 沙箱能力，需先核对沙箱覆盖。

## 6. 里程碑验收清单（重开后）

- [x] ADR 落地：`mcp` SDK 依赖定位明确（懒 import 可选依赖 / 边界依赖），守住「litellm 唯一运行时三方依赖」红线 —— **ADR-0043**（+ `[mcp]` optional extra，change `0054`；stdio 同步化订正见 **ADR-0057**）
- [x] 「MCP 客户端消费安全」ADDED delta 落 base spec（`openspec/specs/mcp/spec.md` 含三场景：stdio 沙箱 / http 白名单 / 不可逆确认）—— **change `0033` 重开时已入 base**；change `0054` 另 ADDED「MCP 传输实现与沙箱常驻进程」
- [ ] `build_transport` 生产实现：stdio（command+args 拉起子进程）+ http/streamable-http（连接 + `Mcp-Session-Id` 复用），替换占位抛错 → **stdio 已闭**（change `0054`，占位抛错消除 + 按端点分派）；**http 会话 + `Mcp-Session-Id` 复用未做**（`phase-19.md` B2）
- [x] `MCPClient.add` 按 transport 分流构建 `MCPEndpoint`（stdio `command+args` / http `url+headers`），不再硬编码 http —— **change `0054`**（按来源形状分流 + 显式 transport/command 覆盖）
- [ ] 消费侧安全：本地 stdio 子进程过 `SandboxManager`（资源配额 + 受限文件系统 + 出站白名单）；远端 http 走出站网络白名单 → **配额 + 出站白名单已闭**（change `0054`：`SandboxManager.spawn` 常驻子进程受 rlimit；`build_http_transport` 连接前校验 host）；**受限文件系统（fs jail）未做**（0054 明示非目标）
- [x] `MCPToolAdapter` 标注 coeffects + `reversible=False`（4.3 已有基础，补确认门 + observability 审计接线）—— 确认门**经验证成立**（change `0054`：`network:` coeffect → `HIGH_RISK` → `GateDecision("confirm")`，无需新代码）；observability 审计接线未做
- [ ] `mcp remove` 释放连接/会话/socket 资源，含本地子进程销毁 → **`close` 终止并回收子进程已闭**（change `0054`）；**CLI `mcp remove` 接线已闭**（change `0074`：注册表落盘 + 对称卸载，`mcp remove` 释放连接与子进程）
- [x] 门禁四件套全绿：ruff check ✓ · ruff format --check ✓ · pyright 0 errors · pytest 全通过（含本 Phase 新增用例）—— 以 change `0054` 收官核验（732 passed / 0 errors）

## 7. 测试要点（重开后）

- [x] stdio transport：拉起本地子进程（fake 命令），`initialize` 握手 + 工具发现；子进程销毁（`mcp remove` 后进程退出）—— change `0054`，`tests/test_mcp_stdio.py`（真实子进程端到端）
- [ ] http transport：连接 + `Mcp-Session-Id` 会话复用；非白名单 host 拒绝 → **非白名单拒绝已闭**（change `0054`）；**会话复用未做**（`phase-19.md` B2）
- [ ] stdio 沙箱越界：子进程越界文件访问 / 超额资源被拒绝（`SandboxManager` 断言）→ **超额资源已闭**（change `0054`，rlimit 用例）；**越界文件访问未做**（fs jail 非目标）
- [x] http 出站白名单：非白名单 host → 拒绝 —— change `0054`（`build_http_transport` 连接前校验，`PERMISSION_DENIED`）
- [x] 不可逆工具确认：`reversible=False` 外部工具触发 permission 确认门，来源标注外部 MCP，审计落盘 —— 确认门已验证（change `0054`：`test_adapted_mcp_tool_triggers_confirm_gate`）；审计落盘未做
- [x] 安装分流：stdio 来源（command+args）与 http 来源（url+headers）分别构建正确 `MCPEndpoint` —— change `0054`（`MCPClient.add` 按来源形状分流）
- [ ] 移除清理：`mcp remove` 后连接/会话/socket 释放，相关工具标记不可用 → **资源释放已闭**（change `0054`）；**CLI 接线已闭**（change `0074`）；**工具标记未做**

## 8. 提交规范

- **一个 Phase 一个 commit**：ADR + transport 生产实现 + client 安装分流 + 消费侧安全接线 + 契约归档（0033）+ 门禁全绿后单次提交。
- commit message 形如：`feat(phase12): MCP 安装/传输/安全接线（stdio 沙箱 + 远端网络管控）`
- 提交后更新 `README.md` §2 总览表 Phase 12 行状态列为「完成」（同时撤销本文件的 DEFERRED 标注）。
- 契约变更走 openspec 归档（changes/0033），与代码同 commit 或紧邻提交。
