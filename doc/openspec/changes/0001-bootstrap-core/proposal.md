# Change: Bootstrap Core Capabilities

## Why
CORE-Harness 需要先落地六大核心能力作为引擎主轴与扩展基底：执行循环（loop）、分层记忆（memory）、工具使用（tool-use）、MCP 集成（mcp）、插件注册表（plugin-registry）、进化引擎（evolution）。这六个能力构成"插件即原子、记忆即光谱、进化即结晶"的最小可运行闭环。

## What Changes
- 新增 `loop` 规格：观察→推理→行动→记忆主循环、横切中间件插入、预算控制。
- 新增 `memory` 规格：L0–L4 分层记忆、热/温/冷检索、无行动不记忆、记忆压实。
- 新增 `tool-use` 规格：工具 schema 注册、参数校验、coeffect 副作用契约。
- 新增 `mcp` 规格：连接管理、工具/资源发现、调用转发与错误隔离。
- 新增 `plugin-registry` 规格：插件生命周期、依赖解析、隔离与安全。
- 新增 `evolution` 规格：经验采集、结晶为技能、溶解回收。

## Impact
- **Affected specs**: loop, memory, tool-use, mcp, plugin-registry, evolution（全部新增）
- **Affected code**: 无（纯规格阶段，SDD 先行）
- **Dependencies**: 后续 0002 横切能力依赖本批次主轴能力
