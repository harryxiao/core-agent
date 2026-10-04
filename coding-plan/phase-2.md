# Phase 2 — 横切中间件（constraints / durability / permission / mcp）

> 里程碑：**无独立里程碑**（横切能力，为 Phase 3+ 主循环与编排提供安全/容错/持久/互操作底座）
> 位置：分层图 L3 中间件层（约束校验 / 持久化 / 权限沙箱 / MCP 互操作）
> 上游：Phase 0（底座）+ Phase 1（llm-provider / tool-use / memory）

---

## 1. 范围与定位

本 Phase 交付 4 个横切能力，**不产出端到端业务闭环**，而是为主循环（Phase 3）、编排（Phase 4）提供可复用的安全与容错地基：

| Capability | 职责一句话 | 关键复用方 |
|---|---|---|
| constraints | 输入输出校验 + 熔断/重试/回滚 + 上下文压缩中间件 | loop、orchestration |
| durability | 检查点/快照 + 崩溃恢复 + 时间旅行回滚 + 保留策略 | loop、evolution |
| permission | 分级权限 + 人工审批流 + 沙箱隔离 | tool-use、mcp、ui |
| mcp | MCP 连接管理 + 工具/资源发现 + 调用转发 + Server 模式 | 外部生态互操作 |

**定位原则**：四个模块全部「协议化 + 可插拔」——`Middleware(Protocol)`、`MemoryBackend` 同构的 `CheckpointManager`、`PolicyEngine`、`MCPClient/MCPServer(Plugin)`。它们被上层消费时不得反向依赖 loop/skills。

---

## 2. 里程碑验收（无 M 里程碑，以契约红线为准）

以下清单全部勾选才算 Phase 2 完成：

- [ ] constraints：输入校验失败拒绝执行；输出解析失败不执行副作用；熔断器打开短路；失败触发回滚；压缩清理冗余上下文 → **部分完成**：熔断**已生产接线**（change `0052`／ADR-0055，按 `tool_id` 隔离 + 结果侧观察者；见 `:121`）；校验由工具层 `ToolProvider._validate_args` 承担（与 `Validator.validate_input` 等价）；RetryPolicy/Fallback **有意未接**（幂等风险／无生产 fallback_fn；审慎记录于 `phase-19.md` E13/E14）
- [x] durability：显式创建检查点带元数据寻址；崩溃后自动恢复且幂等；检查点损坏降级；回滚到历史检查点并与副作用级回滚协同；保留策略自动清理 + 关键检查点 pin 保护
- [x] permission：只读放行、高危默认拦截、无法归类处理；审批通过放行、超时拒绝、可追溯；沙箱内执行与销毁、沙箱不可用降级；三域隔离、网络出站白名单、资源配额、文件系统受控访问
- [ ] mcp：注册连接、断线重连、心跳保活、关闭释放资源；动态映射工具、能力冲突处理；透明转发、MCP 异常隔离；stdio 本地 + Streamable HTTP 远程挂载；默认最小暴露、白名单显式开放；高危确认、越权拒绝；多客户端隔离；单连接多会话复用 → **部分完成**：连接管理/发现/异常隔离/多客户端隔离已由 Phase 12 首切片落地（`tests/test_mcp.py`）；**stdio 本地挂载 + 出站白名单 + 高危确认 + 子进程销毁已由 change `0054` 闭合**（ADR-0057）；**Streamable HTTP 远程挂载仍待**（`phase-19.md` B2）

---

## 3. 依赖与前置

- **上游**：Phase 0（plugin-registry / configuration / observability）+ Phase 1（tool-use 的 `ToolProvider`/`SafetyGate`、llm-provider）。
- 外部依赖：
  - mcp：官方 MCP SDK（stdio + Streamable HTTP 传输）
  - durability：后端存储走抽象，默认本地文件实现即可，不强制数据库
  - permission：沙箱执行环境（容器/进程隔离，按宿主平台选择实现）

---

## 4. 首步任务

无（四个 capability 的 spec/interface 均已齐全，无契约缺补）。

**启动前核对**：以 `contracts_summary.md` 第 4 / 9 / 15 / 19 章为契约基线，与 `specs/` 对应 spec.md + `03-interfaces/` 对应 interface 逐一比对后开工。

---

## 5. 实现顺序（模块级拓扑序）

### 5.1 constraints（最先，依赖 plugin-registry + configuration）

- 核心类/接口：`Middleware(Protocol)`、`Validator`、`CircuitBreaker`、`RetryPolicy`、`Fallback`、`Rollback`
- 关键方法：`before()`、`after()`、`validate_input()`、`parse_output()`、`record_result()`、`state()`、`should_retry()`、`backoff()`、`on_failure()`
- 错误码：`CIRCUIT_OPEN`、`OUTPUT_PARSE_FAILED`、`RETRY_EXHAUSTED`、`ROLLBACK_FAILED`
- 验收重点：before/after 管道语义、熔断状态机、指数退避、上下文压缩冗余清理

### 5.2 durability（依赖 plugin-registry 的 effect 追踪 + configuration）

- 核心类/接口：`CheckpointManager`、`CrashRecovery`、`TimeTravel`、`RetentionManager`
- 数据类型：`Checkpoint` / `Snapshot` / `RestoreHandle` / `RetentionPolicy`
- 关键方法：`create_checkpoint()`、`list_checkpoints()`、`get_snapshot()`、`restore()`、`resume()`、`rollback()`、`apply()`、`pin()`、`unpin()`
- 错误码：`CHECKPOINT_CORRUPT`、`CHECKPOINT_NOT_FOUND`、`RESTORE_DEGRADED`、`RETENTION_QUOTA_EXCEEDED`
- 验收重点：崩溃恢复幂等、时间旅行与副作用级回滚协同、pin 保护不被清理

### 5.3 permission（依赖 tool-use 的 `SafetyGate` + constraints）

- 核心类/接口：`PolicyEngine`、`ApprovalWorkflow`、`SandboxManager`
- 数据类型：`RiskLevel` / `Decision` / `ApprovalRequest` / `ApprovalResult` / `SandboxResult`
- 关键方法：`classify()`、`authorize()`、`create()`、`ask()`、`archive()`、`run()`、`destroy()`
- 错误码：`APPROVAL_EXPIRED`、`APPROVAL_REQUIRED`、`APPROVAL_TIMEOUT`、`PERMISSION_DENIED`、`SANDBOX_UNAVAILABLE`
- 验收重点：高危默认拦截、审批超时拒绝、沙箱销毁回收资源、三域隔离 + 出站白名单

### 5.4 mcp（依赖 plugin-registry + tool-use 的 `ToolProvider` + permission）

- 核心类/接口：`MCPClient(Plugin)`、`MCPServer(Plugin)`、`MCPEndpoint`、`MCPToolAdapter`
- 关键方法：`connect()`、`list_tools()`、`list_resources()`、`list_prompts()`、`call_tool()`、`read_resource()`、`get_prompt()`、`adapt()`、`serve()`、`initialize()`
- 错误码：`MCP_CONNECT_FAILED`、`MCP_PROTOCOL_MISMATCH`、`MCP_TOOL_NOT_FOUND`、`PERMISSION_DENIED`、`REMOTE_IRREVERSIBLE`、`REMOTE_TIMEOUT`
- 验收重点：MCP 异常隔离（不污染主循环）、默认最小暴露 + 白名单显式开放、会话与连接解耦

---

## 6. 契约对齐

以 `contracts_summary.md` 为唯一契约基线（本 Phase 对应第 4/9/15/19 章）：

| Capability | 章节 | 关键方法（实现必须覆盖） |
|---|---|---|
| constraints | §4 | `before()`, `after()`, `validate_input()`, `parse_output()`, `record_result()`, `state()`, `should_retry()`, `backoff()`, `on_failure()` |
| durability | §9 | `create_checkpoint()`, `list_checkpoints()`, `get_snapshot()`, `restore()`, `resume()`, `rollback()`, `apply()`, `pin()`, `unpin()` |
| mcp | §15 | `connect()`, `list_tools()`, `list_resources()`, `list_prompts()`, `call_tool()`, `read_resource()`, `get_prompt()`, `adapt()`, `serve()`, `initialize()` |
| permission | §19 | `classify()`, `authorize()`, `create()`, `ask()`, `archive()`, `run()`, `destroy()` |

**契约红线**（违反即返工）：
1. 输出解析失败不得执行副作用（先解析成功，再放行副作用）。
2. 熔断器打开后必须短路，不得穿透重试。
3. 沙箱不可用必须降级为 `SANDBOX_UNAVAILABLE`，不得裸跑高危动作。
4. MCP 异常必须隔离，不得让远端故障阻断宿主主循环。
5. 检查点崩溃恢复必须幂等，重复恢复不得产生双重副作用。

---

## 7. 门禁验收

全局四命令（见 `doc/05-development/development-standards.md`）全部通过：

```bash
ruff check src tests
ruff format --check
pyright
pytest -q
```

本 Phase 专属校验（附加于全局门禁）：

- [x] 架构测试：四模块不得反向依赖 loop/skills/orchestration
- [x] 熔断测试：连续失败触发 `CIRCUIT_OPEN`，短路期间无真实调用（**生产接线已端到端证明**：change `0052`，`tests/test_constraints_wiring.py::test_e2e_breaker_opens_through_loop` —— 达阈值后工具 handler 调用计数停住）
- [ ] 崩溃恢复测试：kill -9 后重启，`resume()` 恢复且无重复副作用（部分：`tests/test_durability.py:55/67` 有 resume 幂等单测（内存 store 模拟），**无真实 `kill -9` 子进程重启用例** → `phase-19.md` E12）
- [x] 时间旅行测试：回滚到历史检查点，副作用级回滚与快照一致
- [x] 沙箱测试：沙箱内高危动作被拦截/降级，销毁后资源清零
- [x] MCP 隔离测试：远端连接故障不阻断宿主，心跳断线可重连

---

## 8. 提交规范

- **一个 Phase 一个 commit**：4 模块 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase2): constraints/durability/permission/mcp 横切中间件`
- 提交后更新 `README.md` §2 总览表 Phase 2 行状态列为「完成」（本 Phase 无独立里程碑）。
