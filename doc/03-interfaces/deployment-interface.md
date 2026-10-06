# 接口设计：部署与托管接口（Deployment Interface）

> 横切 ｜ 对应规格 `deployment/spec.md`（无专属模块文档，横切运行时能力）

---

## 1. 运行环境抽象接口

```python
class RuntimeEnvironment:
    def configure(self, config: RuntimeConfig) -> None: ...  # 读取声明式配置，装配环境
    def assemble(self) -> None: ...                            # 依赖装配（进程级或容器级）
    def bootstrap(self) -> None: ...                           # 启动引导，拉起 Core-Agent 及子模块
```

- 只描述运行环境抽象（进程级或容器级），**不锁定具体选型**，一套配置可在个人 PC / 服务器 / 边缘设备复用。

## 2. 云托管 BYOC 适配接口

```python
class CloudAdapter:
    def adapt(self, target: DeployTarget) -> RuntimeEnvironment: ...  # 将部署抽象映射到用户自有云
    def parity_check(self, local: RuntimeConfig, cloud: RuntimeConfig) -> bool: ...
```

- 云托管（BYOC）与自托管共享同一部署抽象与配置，行为一致，不绑定特定云厂商。

## 3. 发布与升级接口

```python
class ReleaseManager:
    def publish(self, release: ReleaseInfo) -> str: ...      # 版本化发布，返回可寻址版本引用
    def upgrade(self, version: str) -> None: ...             # 滚动升级到目标版本
    def rollback(self) -> None: ...                          # 回滚到上一个可用版本
```

## 4. 健康检查与生命周期接口

```python
class LifecycleController:
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def restart(self) -> None: ...
    def probe(self) -> HealthStatus: ...                     # 健康探活端点
```

## 5. 核心数据结构

```python
@dataclass
class RuntimeConfig:
    kind: str                 # self-hosted | byoc-cloud
    target: DeployTarget      # 运行目标（PC / 服务器 / 边缘设备 / 用户自有云）
    env: dict                 # 声明式环境配置

@dataclass
class DeployTarget:
    host: str                 # 宿主机标识
    runtime: str              # 进程级 | 容器级（抽象，不锁具体选型）

@dataclass
class ReleaseInfo:
    version: str
    hash: str                 # 内容哈希，保证跨环境一致
    strategy: str             # rolling 等滚动升级策略

@dataclass
class HealthStatus:
    alive: bool
    detail: str               # 探活失败原因 / 告警信息
```

## 6. Harness Host 常驻服务接口

```python
class HarnessHost:
    def serve(self) -> None: ...                       # 常驻运行，承载内核并对外暴露统一接入端点
    def accept(self, client: ClientConnection) -> Session: ...  # 客户端接入，建立独立会话
    def sessions(self) -> list[Session]: ...           # 枚举当前接入的客户端会话（互不串扰）
    def touch(self, session_id: str) -> bool: ...      # 心跳：刷新 last_seen（在连会话 ⇒ True）
    def disconnect(self, session_id: str) -> None: ...  # 客户端断线清理
    def reap(self, timeout: float) -> list[str]: ...    # 超时回收：回收 timeout 内无活动者
```

- 单一 Harness Host 进程常驻承载内核，作为统一接入端点；多个 Web/Desktop 客户端并发接入，各自建立独立会话。
- Host 生命周期与单个客户端解耦：客户端断开不导致 Host 退出，Host 异常依赖 `LifecycleController` 探活恢复。
- **活动 vs 超时**（change `0139` / ADR-0132）：`reap` 判据是「**无活动**超过 `timeout`」，
  `last_seen` 由 `accept` **与心跳 `touch`** 共同刷新 ⇒ 活跃长连客户端不被误回收。
  `touch` **只认在连（`CONNECTED`）会话**：未知 / 已断线 / 已回收 ⇒ 返 `False` 且**不复活**
  （心跳不得撤销清理）；刷新成功即持久化（与 `accept` / `disconnect` / `reap` 同口径）。
- **已知局限**：`touch` / `reap` 今日**无生产驱动**（`entry._serve` 注册一个 `serve` 会话后直接阻塞于
  uvicorn，从不 `reap`）—— 本接口补的是**规格 SHALL 的心跳检测能力**（与 change `0138` 补 git
  高危原语同类），驱动接线不在本账范围。

## 7. 约束

- 运行环境抽象**不锁定容器 vs VM vs 进程级**，避免与沙箱选型未定的既有设计冲突。
- 自托管与云托管（BYOC）共享同一配置与部署抽象，切换运行形态不改业务逻辑。
- 升级失败自动回滚到上一可用版本，运行环境不处于半升级状态。
- 探活发现异常 → 触发告警或自动恢复，生命周期操作（启动/停止/重启）可正常执行。

## 8. 错误码

| 错误码 | 含义 |
|---|---|
| `UPGRADE_FAILED` | 升级失败（已自动回滚） |
| `ROLLBACK_FAILED` | 回滚失败 |
| `HEALTH_UNHEALTHY` | 探活异常 |
| `NOT_READY` | 生命周期非法迁移 / 未 bootstrap 就操作 |

## 9. 关联

- 打包分发互补：`composition-interface.md`（Composition 决定「装什么」，Deployment 决定「跑在哪/怎么跑/怎么升级」）
- 跨设备拓扑互补：`distributed-interface.md`
- 审计链路：`observability-interface.md`
- 规格：`openspec/specs/deployment/spec.md`
- 变更：`openspec/changes/0013-deployment/`、`openspec/changes/0019-harness-host-web-client/`
