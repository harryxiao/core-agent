# Design

## Context

ui capability 现有 R1「三模统一内核启动」下，Web/Desktop 前端以「与后端同机运行」方式接入内核；deployment capability（ADR-0028）已确立自托管优先 + 可选云托管 BYOC 的抽象运行环境，但缺少「常驻 Host 承载多客户端」的进程形态描述。多个 Web/Desktop 客户端需同时接入同一 Core-Agent 实例时，若每客户端各自拉起后端进程，会造成资源重复与状态割裂。本 change 引入 Harness Host 常驻服务与 Web Client 分离形态：单一 Host 进程常驻承载内核与多客户端，前端以纯静态资源独立托管、经统一后端 API 连接 Host。

## Decisions

- **Harness Host 常驻服务（R5）**：deployment 新增 R5，以单一常驻进程承载内核并对外暴露统一接入端点，多客户端并发接入、各自建立独立会话；Host 生命周期与单个前端客户端解耦（客户端断开不导致 Host 退出）。
- **Web Client 分离（R9）**：ui 新增 R9，Web 前端以纯静态资源（SPA）独立托管、独立升级，经统一后端 API 连接远程/本机 Host；前端不内嵌后端进程，与 Host 解耦部署。
- **单进程多会话进程模型（ADR-0031）**：单一 Host 进程内承载多客户端会话，会话隔离复用 mcp R7「会话与调用隔离」应用层语义 + 0018 R8「会话多流复用」传输层能力；不采用每客户端独立进程，避免资源膨胀。
- **spec 扩展非新 cap**：Harness Host 常驻归属 deployment（跑在哪/怎么跑）、Web Client 分离归属 ui（前端呈现），不新建 hosting/session capability。

## Risks / Trade-offs

- **进程内会话资源隔离**：多会话共处单一 Host 进程，需确保会话间状态/资源互不串扰（复用 mcp R7 隔离语义兜底），单个会话异常不拖垮整个 Host。
- **单点故障面**：常驻 Host 作为统一接入点，进程崩溃影响全部已接入客户端，需依赖 deployment R4「健康检查与生命周期」的探活/恢复能力。
- **前端与 Host 版本兼容**：Web Client 独立升级后需与 Host 后端 API 保持兼容，版本不匹配时需有明确降级/提示。

## Open Questions

- Harness Host 的具体运行器形态（进程级/容器级）延续 ADR-0028 抽象口径，留待编码阶段确定。
- 单 Host 进程承载会话数的上限与弹性伸缩策略留待实现阶段确定。
