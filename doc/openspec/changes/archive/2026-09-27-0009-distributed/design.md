# Design

## Context

分布式调研（research_findings.md）确认：A2A 是唯一面向「独立 Agent 之间对等协作/委派」的开放标准（Linux Foundation / Apache-2.0，11 核心操作、3 协议绑定 + 自定义绑定、AgentCard 发现与签名、OAuth2/mTLS 鉴权）；MCP 负责 Agent ↔ 工具/资源（spec 2026-07-28，stdio + Streamable HTTP，OAuth 2.1）。二者互补（A2A 规范附录 B）。本 design 明确 distributed 层的协议栈、拓扑角色与安全边界，作为模块/接口文档与实现的依据。

## Decisions

- **协议栈三层**：应用层 A2A（Agent↔Agent 委派）→ 能力层 MCP（Agent↔工具/资源）→ 传输/身份 mTLS/OAuth 2.1（可选 iroh 类 P2P）。不引入不可验证的性能断言（iroh「比 SSH 低 30% 延迟」无权威基准，仅作传输优化模型借鉴）。
- **双向互调**：Core-Agent 同时具备 A2A Client（委派 Claude Code / Codex / Kilo 等外部 Agent）与 A2A Server（对外暴露能力被调）两种角色。
- **控制面/执行面分离**：借鉴 Claude Code Remote Control 思想——云端承载控制面/中继/长任务，PC 本地文件系统与 MCP 工具留在本机执行，移动端仅做瘦客户端，嵌入式作为 MCP Server 能力提供者。
- **与 orchestration 边界**：orchestration = 单一循环内的任务状态机/子任务拆解/子 Agent 交接（进程内）；distributed = 跨设备/跨进程 Agent 互调的网络协议层。二者不重叠，本 capability 新建而非扩展 orchestration。

## Risks / Trade-offs

- **安全边界**：跨设备入口比本机更脆（对齐 IM 网关的顾虑），任何远程 Agent 都可能接入——以 AgentCard 签名 + OAuth2/mTLS + 最小权限 scope 收口，高危操作走既有 permission 链路。
- **协议绑定取舍**：JSON-RPC 2.0 over HTTP(S) 为默认推荐绑定（流式走 SSE），gRPC/REST 备选；若实现期对多语言互操作有强诉求，再评估 gRPC 优先。
- **P2P 选型风险**：iroh 类 P2P 的延迟收益无权威基准，不得作为选型依据；仅作为可选传输优化，且须自建基准验证。
- **生态成熟度**：OpenAI 系仅 MCP、LangChain 系 A2A 独立包未发布（PyPI 404），A2A 生态以官方 a2a-sdk 为主——实现期优先官方 SDK，避免绑定未发布包。

## Open Questions

- 自定义绑定（A2A §12）是否需在本能力实现中支持，还是仅 JSON-RPC/gRPC/REST 三种标准绑定。
- 跨设备会话（contextId/taskId 多轮）与本地 context 模块的对接方式。
- P2P 直连（P3）是否纳入首期实现，还是仅在文档标注为可选优化。
