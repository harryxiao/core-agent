# Change: 模块抽象层（MAL）——三方依赖边界统一契约

## Why

架构审计（2026-09-27）走查三方依赖边界发现：llm-provider 已用「抽象接口 + 依赖注入隔离」把 LiteLLM 收敛为可替换默认实现，im 用 IMGateway+IMProvider 同法；但 rag 的 spec 把 sqlite-vec / sentence-transformers+BGE 写死进 Requirement 本体、接口无装配 seam，mcp 的传输层 Transport 只存在于设计稿、未进接口契约，git 无 git-interface.md、无 GitClient 抽象。三方替换成本不一致，缺一条统一约定。

## What Changes

- 新增 `git`（ADDED GitClient 抽象接口与依赖注入隔离 + MODIFIED 版本控制核心操作补 stash）
- 修改 `rag`（MODIFIED 本地向量库存储 / 本地 Embedding 去具体化 + ADDED 存储与 Embedding 依赖注入隔离）
- 新增 `mcp`（ADDED 传输层抽象与依赖注入隔离）
- 新增接口文档 `03-interfaces/git-interface.md`；`rag-interface.md` / `mcp-interface.md` 补装配 seam / Transport
- 新增 ADR-0040（MAL 四条约定）

## Impact

- **Affected specs**：`specs/git/spec.md`、`specs/rag/spec.md`、`specs/mcp/spec.md`
- **Affected docs**：`03-interfaces/git-interface.md`（新增）、`03-interfaces/rag-interface.md`、`03-interfaces/mcp-interface.md`、`01-architecture/adr.md`（ADR-0040）
- **Affected code**：无（本 change 声明抽象接口与依赖注入隔离语义，不涉及具体实现代码）
- **Dependencies**：无（git / rag / mcp 三处缺口相互独立，均复用既有 plugin-registry / llm-provider 依赖注入范式）
