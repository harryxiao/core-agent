# Design

## Context
内核（loop/memory/tool-use/mcp）与横切能力（permission/constraints/observability）已就位，但缺"呈现层"。Claude Code 的终端 UI 为 Ink（React→终端，打包进原生二进制），但 Ink 属 Node/TS 生态；core-agent 后端为 Python（ADR-0006），引入 Ink 需跨语言桥接。调研现成 Web 方案（Open WebUI/Lobe Chat/LibreChat/Cherry Studio/Dify）均为独立产品，无"可嵌入框架"。

## Decisions
- **CLI 用 Textual 而非 Ink**：取 Ink 的"声明式 + 响应式"交互哲学，用 Python 原生 Textual 同进程复刻折叠块/流式/多面板，避免 Node 桥接。
- **Web 自研单 SPA + 统一 API，而非嵌入现成产品**：硬嵌=改造 Fork 成本 > 自研；参考 Open WebUI「Python 后端 + Svelte 前端」同栈架构成熟经验。
- **桌面用 Tauri 壳复用 SPA + sidecar**：与 Web 共享同一前端构建产物实现 100% 一致，sidecar 拉起 Python 后端，体积远小于 Electron。
- **统一 API 解耦**：三种模式都走同一套后端 API（HTTP + SSE），CLI 不绕过内核直连，保证鉴权/日志/行为一致。
- **单一配置源**：LLM API 只在后端配置一次，三模不重复配置。

## Risks / Trade-offs
- **Textual 生态小于 Web**：复杂布局需自绘组件，可接受（CLI 交互面有限）。
- **自研 UI 工作量前置**：会话/流式/设置均需自研，用 P1→P4 分阶段对冲。
- **Tauri 需 Rust 工具链**：sidecar 跨平台打包需 CI 矩阵，Windows 环境需额外验证。

## Open Questions
- SPA 前端框架选型（Svelte vs React）待 P2 开工前定。
- sidecar 后端的启动失败降级策略（自动重试 / 报错引导）。
- CLI 与 Web 是否共享同一 SSE 客户端实现。
