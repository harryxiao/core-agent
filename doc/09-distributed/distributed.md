# 分布式协作层：让 Core-Agent 跨设备互调外部/被外部 Agent 调用

> 对应规格：`doc/openspec/specs/distributed/spec.md` ｜ 变更提案：`doc/openspec/changes/0009-distributed/`
> 本方案文档对应 ADR-0022 ~ 0023

---

## 1. 定位与场景

Core-Agent 已有四类入口：

| 入口方向 | 载体 | 文档 |
|---|---|---|
| 人 → core-agent | CLI / Web / Desktop | `06-ui-frontend/ui-architecture.md` |
| 机器 → core-agent | MCP Server（对外工具源） | `07-mcp-server/mcp-server.md` |
| 随身 → core-agent | IM 网关（社交 App 远程入口） | `08-im-gateway/im-gateway.md` |
| **对等 → core-agent** | **A2A 分布式协作层** | 本文档 |

分布式协作层补齐「**Agent ↔ Agent 对等协作**」：Core-Agent 作为 A2A Client 委派任务给外部 Agent（Claude Code / Codex / Kilo 等），或作为 A2A Server 对外暴露能力被外部 Agent 调用，覆盖云端 / 个人 PC / 移动终端 / 嵌入式设备的多设备联合开发。

## 2. 协议栈与架构

调研（`research_findings.md`，2026-09-20）确认：A2A 与 MCP 互补非竞争（A2A 规范附录 B 官方定性）。

```
应用层   A2A（Agent ↔ Agent 委派/协作）
            Linux Foundation / Apache-2.0
            11 核心操作 · 3 协议绑定 + 自定义绑定 · AgentCard 发现与签名
能力层   MCP（Agent ↔ 工具/资源）
            spec 2026-07-28 · stdio + Streamable HTTP
身份/传输 mTLS / OAuth2 / APIKey / OpenIdConnect · TCP/QUIC
```

- **A2A** 负责「谁帮我做」（对等委派），**MCP** 负责「用什么做」（工具/资源调用）。
- A2A Server 内部经 MCP 调用底层工具/数据完成任务（FR-7），复用既有 MCP 能力。

## 3. 多设备拓扑角色

| 设备 | 角色 | 说明 |
|---|---|---|
| 云端 | A2A Server + 控制面 + relay | 只承载协调与进度，不触碰本地数据 |
| 个人 PC | 本地 Agent | 文件系统 / MCP 工具留本机，执行面在本机 |
| 移动终端 | A2A 瘦客户端 | 仅发现 / 委派 / 订阅进度 / 展示（REST 绑定 + 推送） |
| 嵌入式设备 | MCP Server 能力提供者 | 传感器 / 执行器能力经 MCP 暴露 |

核心原则：**控制面 / 执行面分离**——云端只协调，敏感数据与工具留本机。

## 4. 安全边界

- **鉴权**：A2A 的 OAuth2 / mTLS / APIKey / OpenIdConnect，云端↔嵌入式敏感指令优先 mTLS 双向认证。
- **最小权限**：跨设备调用按最小权限 scope 授权，超出 scope 拒绝并审计（来源 `a2a:<peer>`）。
- **复用链路**：高危操作复用既有 permission 审批链路 + observability 审计落盘，不降安全等级。
- **卡片签名**：AgentCard 签名验证通过才接受对端身份与能力声明。

## 5. 接口设计

| 接口 | 职责 |
|---|---|
| `A2AClient` | 读取对端 AgentCard、SendMessage 委派任务、订阅任务进度（流式/推送） |
| `A2AServer` | 暴露 AgentCard、接收任务、执行并回报结果 |
| `DistributedGateway` | 拓扑接入与传输管理（HTTP(S) 默认 / gRPC / REST 备选；可选 P2P 直连） |

## 6. 与其他模块的关系

| 模块 | 关系 |
|---|---|
| mcp | 复用：A2A Server 内部经 MCP 调用底层工具（FR-7） |
| permission | 复用：跨设备调用按最小权限 scope，高危操作审批门 |
| observability | 复用：审计落盘，来源标注 `a2a:*` |
| constraints | 复用：熔断/隔离，单设备故障不扩散 |
| composition | 复用：远端工具/能力经组合分发 |
| llm-provider | 可选：远端推理经 LLMProvider 抽象 |
| orchestration | 不重叠：orchestration 是管内任务编排，distributed 是跨设备互调 |

## 7. ADR 索引

| ADR | 决策 |
|---|---|
| ADR-0022 | 分布式协议栈采用 A2A + MCP 互补（跨设备 Agent 互调） |
| ADR-0023 | 控制面/执行面分离拓扑（云端协调 + 本机执行） |
