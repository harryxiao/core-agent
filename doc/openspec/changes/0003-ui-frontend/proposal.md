# Change: UI 界面与启动模式（CLI / Web / Desktop）

## Why
core-agent 内核（loop/memory/tool-use/mcp/evolution/permission 等）已规格化，但只有"代码级"入口，用户无法以产品形态使用。本变更新增统一 UI 呈现层：CLI（终端友好交互）、Web（浏览器 + 可配置 LLM API）、Desktop（可打包安装 + 可配置 LLM API）三种启动模式，三者共享同一内核与同一配置源，解决"裸内核无入口、配置分散、体验不一致"三个问题。

## What Changes
- 新增 `ui` 规格：三模统一内核启动、LLM API 可配置、CLI 友好交互（Textual 复刻 Ink）、Web 界面访问（HTTP + SSE）、桌面打包（Tauri 壳 + sidecar）、Web/桌面体验一致。

## Impact
- **Affected specs**: ui（新增）
- **Affected specs (integration)**: loop / memory / tool-use / mcp（由后端 API 层暴露给三种模式）
- **Affected code**: 新增 `src/cli/`（Textual 前端）、`src/api/`（FastAPI 层）、`frontend/`（单 SPA）、`src-tauri/`（桌面壳）；内核层不动
- **Dependencies**: 依赖 0001 主轴能力 + 0002 横切能力（API 层复用内核与权限/可观测链路）
