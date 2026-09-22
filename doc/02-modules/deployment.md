# 模块设计：部署与托管（Deployment）

> 对应规格：`doc/openspec/specs/deployment/spec.md` ｜ 接口：`doc/03-interfaces/deployment-interface.md`
> 定位：**运行与发布侧**，为 Core-Agent 提供可落地的运行环境与发布升级能力，回答「跑在哪、怎么跑、怎么升级」。

---

## 1. 模块定位

Deployment（部署与托管层）是 Core-Agent 的「运行与发布」层：在 Composition 决定「装什么」（bundle 打包分发）、Distributed 决定「和谁协作」（跨设备拓扑）之后，Deployment 负责把组装好的 Agent 真正跑起来、持续升级并保持可用：

- **自托管优先**：默认在用户自己的宿主机（个人 PC / 服务器 / 边缘设备）上，以抽象运行环境形态（进程级或容器级）运行，不锁定具体选型。
- **可选云托管 BYOC**：允许把同一套部署迁到用户自选云平台（Bring Your Own Cloud），与自托管共享同一部署抽象与配置，不绑定特定云厂商。
- **发布与升级**：版本化发布（内容哈希）、滚动升级、失败自动回滚，运行环境不处半升级态。
- **健康与生命周期**：暴露健康探活端点，支持启动 / 停止 / 重启，异常时及时发现并触发恢复。

它与 Composition、Distributed 语义正交、互不耦合：

| capability | 回答的问题 |
|---|---|
| Composition | 装什么（bundle 打包分发） |
| Distributed | 和谁协作（跨设备拓扑） |
| Deployment | 跑在哪、怎么跑、怎么升级 |

---

## 2. 架构

```
Deployment（运行与发布层）
├── RuntimeEnvironment   运行环境抽象：configure 读配置 → assemble 依赖装配 → bootstrap 启动引导
├── CloudAdapter         BYOC 云适配：adapt 映射到用户自有云 / parity_check 校验形态一致
├── ReleaseManager       发布与升级：publish 版本化发布（内容哈希）→ upgrade 滚动升级 → rollback 回滚
├── LifecycleController  健康与生命周期：probe 健康探活 + start / stop / restart
└── HarnessHost          常驻服务：单一 Host 进程承载内核 + 统一接入端点，多客户端并发独立会话
```

- **RuntimeEnvironment**：以抽象概念（进程级 / 容器级）描述运行环境，承载 Core-Agent 及其子模块对外提供服务，不锁定具体选型。
- **CloudAdapter**：把部署抽象映射到用户自有云，并校验自托管与云托管形态一致。
- **ReleaseManager**：以内容哈希标识发布版本，滚动升级到目标版本，失败回滚到上一可用版本。
- **LifecycleController**：暴露健康探活端点并承接启动 / 停止 / 重启等生命周期操作。
- **HarnessHost**：以单一常驻进程承载内核及其子模块，对外暴露统一接入端点，多个 Web/Desktop 客户端并发接入、各自建立独立会话。

---

## 3. 关键设计

### 3.1 运行环境抽象（自托管优先）

- 运行环境以抽象概念描述，进程级或容器级均可，**不锁定容器 vs VM vs 进程级**，一套部署可在个人 PC、服务器、边缘设备上运行。
- 环境配置采用**声明式**：装配依赖与启动引导均从声明式配置读取，迁移宿主机时复用同一配置即可完成装配与启动，无需改动业务逻辑。
- 启动引导完成后，Core-Agent 以自托管运行环境形态对外提供服务。

### 3.2 可选云托管 BYOC

- 自托管优先，云托管为可选形态（BYOC：Bring Your Own Cloud）。
- 用户把已在本地自托管运行的部署迁到自选云平台时，**复用同一环境配置与部署抽象**即可运行，自托管与云托管行为一致。
- 不强制绑定特定云厂商，切换运行形态不改业务逻辑。

### 3.3 版本化发布与升级

- **版本化发布**：以内容哈希标识每个发布版本（`ReleaseInfo.hash`），跨环境一致、可追溯、可回退。
- **滚动升级**：发布新版本后逐步切换（`strategy: rolling`），升级过程不要求整体停机。
- **失败回滚**：升级失败自动回滚到上一个可用版本，保证运行环境不处于半升级状态，服务不中断或可快速恢复。

### 3.4 健康检查与生命周期

- **健康探活**：暴露健康探活端点（`probe`），对外持续探测实例状态。
- **生命周期操作**：支持启动（`start`）、停止（`stop`）、重启（`restart`）。
- **异常恢复**：探活发现实例异常或不可用时，触发告警或自动恢复，生命周期操作可正常执行。

### 3.5 Harness Host 常驻服务

- **单一常驻进程**：以一个 Harness Host 进程常驻运行，承载 Core-Agent 内核及其子模块，对外提供统一接入端点。
- **多客户端并发接入**：多个 Web/Desktop 客户端经统一后端 API 连接同一 Host，各自建立独立会话、互不串扰。
- **生命周期解耦**：Host 生命周期与单个前端客户端解耦，客户端断开不导致 Host 退出；Host 崩溃时依赖健康探活与自动恢复（见 3.4）兜底。

---

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| 升级失败 | 自动回滚到上一个可用版本，运行环境不处半升级态 |
| 探活发现实例异常 / 不可用 | 触发告警或自动恢复，启动 / 停止 / 重启可正常执行 |
| Host 进程崩溃 | 触发健康探活告警 / 自动恢复，已接入客户端可重连恢复会话 |

---

## 5. 关联

- 规格：`doc/openspec/specs/deployment/spec.md`
- 接口：`doc/03-interfaces/deployment-interface.md`
- 架构决策：`doc/01-architecture/adr.md`（ADR-0028、ADR-0031）
- 正交 capability：`doc/02-modules/composition.md`（装什么）、`doc/09-distributed/distributed.md`（和谁协作）
