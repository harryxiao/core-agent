# Phase 6 — 组合、分布式与部署

> 里程碑：**无独立里程碑**（横切能力层，随 M4→M5 期间逐步交付；验收以契约红线为准）
> 位置：分层图 L2 组合层（composition）+ L? 分布层（distributed）+ 托管层（deployment）
> 上游：Phase 0（底座）+ Phase 1（能力）+ Phase 2（横切中间件）

---

## 1. 范围与定位

本 Phase 交付 **3 个能力，构成 core-agent 的「分发 → 协作 → 托管」闭环**：

| Capability | 职责一句话 | 分层 |
|---|---|---|
| composition | 静态组合代数（永不进化），经 profile/bundle/patch.yml 三要素组合分发 | L2 组合层 |
| distributed | A2A 双向互调、AgentCard 发现签名、协议绑定、安全鉴权、多设备拓扑、P2P 直连 | 分布层 |
| deployment | 自托管/可选云托管 BYOC、发布升级回滚、健康检查、Harness Host 常驻 | 托管层 |

**关键事实**：composition 是「静态组合代数」且**永不进化**（与 Phase 5 的 evolution 形成鲜明对比，evolution 只作用于能力层，不触碰组合代数）；distributed 与 MCP 互补（Server 内部经 MCP 调工具）；deployment 的 Harness Host 是常驻底座，多客户端接入统一端点。

---

## 2. 里程碑验收

**无独立里程碑**。本 Phase 完成判据 = 三组契约红线全部守住：

- [x] composition：profile 按名选用、bundle 跨部署复用、校验失败/循环依赖被拦截、patch 覆盖冲突兜底、层叠解析顺序确定
- [x] distributed：卡片签名验证通过、双向认证 + 最小权限、控制面/执行面分离、P2P 打洞直连优先、心跳保活/断线重连/调用超时/资源释放/委派重试幂等
- [x] deployment：常驻 Host 多客户端接入统一端点、客户端断线清理、连接超时回收、健康探活与恢复、升级可回滚

---

## 3. 依赖与前置

- **composition 依赖**：configuration（profile 命名选用与层叠解析的配置源）+ plugin-registry（`CompositionEngine(Plugin)` 注册）。
- **distributed 依赖**：mcp（A2A 与 MCP 互补，Server 内部经 MCP 调工具）+ permission（双向认证 + 最小权限的鉴权来源）+ composition（跨部署的 bundle 分发格式）。
- **deployment 依赖**：configuration（`RuntimeConfig`）+ plugin-registry（`HarnessHost` 生命周期）+ ci-cd（`ReleaseManager` 的制品版本化来源，与 Phase 7 衔接）。

**顺序约束**：composition（静态组合代数）→ distributed（A2A 依赖 bundle 分发格式）→ deployment（Harness Host 承载前两者的运行时托管）。

---

## 4. 首步任务

**核对三个 capability 的契约边界与衔接点**：

1. composition：核对「层叠解析顺序确定」——profile（命名组合）→ bundle（分发格式）→ patch.yml（用户覆盖）的解析优先级与覆盖冲突兜底规则，确保与 configuration 的配置源不冲突。
2. distributed：核对 A2A 与 MCP 互补边界——「Server 内部经 MCP 调工具、对外经 A2A 暴露能力」，以及 `AgentCard` 签名验证链路依赖 permission 的密钥/签名能力。
3. deployment：核对 Harness Host 的「多客户端接入统一端点」与「客户端断线清理 + 连接超时回收」——这是常驻底座的核心正确性，先写连接生命周期状态机（见 §5.3）。

**启动前核对**（按顺序执行）：
1. 读 contracts_summary §2（composition）+ §8（distributed）+ §7（deployment）原文。
2. 核对三者的数据类型（`Profile`/`Bundle`/`PatchSpec`/`ResolvedSet`、`AgentCard`、`RuntimeEnvironment`/`RuntimeConfig`/`DeployTarget`/`ReleaseInfo`/`HealthStatus`）在仓库 interface 中是否已有定义，无定义则先补。
3. 核对 deployment 的参数/命令面归属：`RuntimeConfig` 参数走 ConfigSpec（M5 全量声明 + core/advanced/hidden 分级），发布升级命令面（publish/upgrade/rollback/status/doctor）复用 cli-ops（M4），不在 deployment 内另起命令解析。

---

## 5. 实现顺序（模块级拓扑序）

### 5.1 composition（先，静态组合代数）

- `ProfileResolver.resolve()` → `CompositionEngine` 组合 → `BundlePackager.pack()`/`BundleDistributor.publish()`/`fetch()`。
- 数据流：`Profile` → `ResolvedSet` → `Bundle`（分发），`PatchSpec` 做用户覆盖；层叠解析顺序必须确定且可复现。
- 校验：bundle 校验失败、循环依赖被拦截。

### 5.2 distributed（中，A2A）

- `A2AClient` + `A2AServer` 双向互调；`AgentCard` 发现 + 签名验证；默认 JSON-RPC 绑定可换。
- 安全：双向认证 + 最小权限；控制面/执行面分离；`A2A_SCOPE_DENIED` 等 6 个错误码全实现。
- 连接：心跳保活、断线重连、调用超时、资源释放、委派重试幂等；P2P 打洞直连优先。

### 5.3 deployment（后，Harness Host 常驻）

- `HarnessHost` 常驻 + 多客户端接入统一端点；连接生命周期状态机（accept → sessions → 断线清理 → 超时回收）。
- `ReleaseManager` 发布升级回滚；`LifecycleController` 健康探活与恢复；`CloudAdapter` 可选云托管 BYOC。
- `RuntimeEnvironment`/`RuntimeConfig`/`DeployTarget`/`ReleaseInfo`/`HealthStatus` 数据类型落地。
- 参数/命令面衔接：`RuntimeConfig` 参数走 ConfigSpec（M5 全量声明 + core/advanced/hidden 分级），不散落硬编码；发布升级命令面（publish/upgrade/rollback/status/doctor）复用 cli-ops（M4），不在 deployment 内另起命令解析。

---

## 6. 契约对齐

以 `contracts_summary.md` §2/§7/§8 为唯一契约基线：

| 契约项 | 实现必须覆盖 |
|---|---|
| 组合分发 | profile 按名选用；bundle 跨部署复用；校验失败/循环依赖拦截；patch 覆盖冲突兜底；层叠解析顺序确定 |
| 组合接口 | `CompositionEngine(Plugin)`、`ProfileResolver`、`BundlePackager`、`BundleDistributor`；方法 `resolve()`/`pack()`/`unpack()`/`publish()`/`fetch()` |
| A2A 协作 | 委派外部 Agent + 对外暴露能力；卡片签名验证；默认 JSON-RPC 可换；双向认证 + 最小权限；控制面/执行面分离；打洞直连优先 |
| A2A 可靠性 | 心跳保活、断线重连、调用超时、资源释放、委派重试幂等 |
| A2A 错误码 | `A2A_AUTH_FAILED`/`A2A_CARD_INVALID`/`A2A_PEER_UNREACHABLE`/`A2A_PROTOCOL_UNSUPPORTED`/`A2A_SCOPE_DENIED`/`A2A_TASK_FAILED` 全实现 |
| 托管 | 常驻 Host 统一端点；客户端断线清理、连接超时回收；健康探活与恢复；升级可回滚 |
| 托管接口 | `HarnessHost`/`ReleaseManager`/`LifecycleController`/`CloudAdapter`；方法 `configure()`/`assemble()`/`bootstrap()`/`adapt()`/`parity_check()`/`publish()`/`upgrade()`/`rollback()`/`start()`/`stop()`/`restart()`/`probe()`/`serve()`/`accept()`/`sessions()` |

**契约红线**（违反即返工）：
1. composition 组合代数不得被 evolution 触碰（永不进化）。
2. distributed 未通过卡片签名验证的 Agent 不得接入；无最小权限的委派不得放行。
3. deployment 升级必须可回滚，健康探活失败必须能恢复。
4. 连接资源必须释放，断线必须重连（不可泄漏连接/不可静默断线）。

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

- [x] composition：层叠解析顺序确定性测试；循环依赖拦截测试；patch 覆盖冲突兜底测试
- [x] distributed：卡片签名验证测试；双向认证 + 最小权限测试；断线重连 + 委派重试幂等测试；6 错误码覆盖测试
- [x] deployment：连接生命周期状态机测试（断线清理/超时回收）；升级回滚测试；健康探活恢复测试

---

## 8. 提交规范

- **一个 Phase 一个 commit**：composition + distributed + deployment 三模块 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase6): composition/distributed/deployment 分发协作托管闭环`
- 提交后更新 `README.md` §2 总览表 Phase 6 行状态列为「完成」（本 Phase 无独立里程碑）。
