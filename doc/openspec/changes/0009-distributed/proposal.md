# Change: Distributed 分布式协作层（A2A + MCP 跨设备 Agent 互调）

## Why

多设备联合开发已成常态（云端 / 个人 PC / 移动终端 / 嵌入式设备），Core-Agent 需要既能调用外部 Agent（Claude Code / Codex / Kilo 等），也能被外部 Agent 调用的分布式网络层。调研（research_findings.md，2026-09-20）确认：跨设备 Agent 协作的标准协议是 **A2A**（Linux Foundation / Apache-2.0），Agent 调用工具/资源的标准协议是 **MCP**（spec 2026-07-28），二者互补非竞争（A2A 规范附录 B 官方定性）。当前 doc/ 与 openspec specs/ 均无分布式网络层 capability，跨设备互调能力悬空、无法追踪。

## What Changes

- 新增 `distributed` capability：跨设备/跨进程 Agent 互调的网络协议层，七条 Requirement
- **A2A 双向互调**：既可作 A2A Client 委派外部 Agent，也可作 A2A Server 对外暴露
- **AgentCard 发现与签名**：以 AgentCard 声明能力/技能/接口，支持签名验证
- **协议绑定**：JSON-RPC 2.0 over HTTP(S) 默认，gRPC 与 REST 备选，支持自定义绑定
- **安全鉴权**：OAuth2 / mTLS / APIKey 多方案，敏感操作最小权限 scope
- **多设备拓扑角色**：云端（控制面+relay）/ PC（执行面留本机）/ 移动（瘦客户端）/ 嵌入式（能力提供者），控制面执行面分离
- **可选 P2P 传输优化**：公钥寻址 + NAT 打洞直连 + relay 回退，非必选
- **A2A↔MCP 互补**：A2A Server 内部经 MCP 调用底层工具/数据完成任务

## Impact

- **Affected specs**：`distributed`（新增 capability）
- **Affected docs**：`09-distributed/distributed.md`（新增，含 ADR）、`README.md`（索引）
- **Affected code**：无（本 change 声明协议层行为与拓扑，具体实现由后续步骤确定）
- **Dependencies**：复用 `mcp`（FR-7，本地/嵌入式能力经 MCP 暴露）；`composition`（远端工具/能力经组合分发）；远端推理可选 `llm-provider`；与 `orchestration`（管内任务编排）不重叠
