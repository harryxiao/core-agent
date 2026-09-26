# Design: 三方插件统一安装抽象的边界

## Context

架构审计（2026-09-26）维度 A：只有 skill 有安装闭环，mcp/cli 无运行期安装生命周期。本 change 在 L0 plugin-registry 建立统一「可安装资产 + 来源」抽象，横切 mcp 复用该来源补安装/移除，L1 tool-use 补 install/uninstall/list 三工具（供 AI 对话安装通道）。

## Decisions

- **来源抽象上提到 registry 层**：`InstallableAsset{kind∈skill|mcp|cli}` 只做 registry 层统一（来源发现/校验/安装/生命周期），执行实现按 kind 适配，不合并 skill/mcp/cli 的执行实现（D3）。
- **skillhub 语义上提不搬家**：skillhub 现有 4 Requirement 不动，其「签名校验 / 多源路由」语义上提到统一层复用，执行仍归 skillhub。
- **数据结构属 how 不进 specs**：`InstallableAsset` / `PluginSource` 字段收敛到 `data-model.md` 单一权威索引，spec Requirement 只写 what 语义。
- **M2 复用现有连接管理**：mcp add 安装后进入 Phase 2 已交付的连接管理（连接/心跳/复用逻辑不改），remove 释放连接资源。

## Non-Goals

- **不合并执行实现**：skill/mcp/cli 三类执行实现各自保留（D3）。
- **不新增分层**：来源抽象落在现有 L0 plugin-registry，不新增层。

## Risks

- **来源抽象过泛**：仅覆盖四类来源（local-path/git-repo/market-registry/mcp-endpoint），后续新来源扩展 PluginSource 枚举而非新建抽象。
- **签名校验链路**：签名校验密钥体系依赖选型，与 skillhub TrustVerifier 对齐。

## Open Questions

- market-registry 远端服务与凭证待工程实现收敛。
- git-repo 来源的版本锁定（tag/branch/commit）策略待实现确定。
