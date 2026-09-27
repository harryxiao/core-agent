# Change: 新增三方插件统一安装能力（plugin-registry/mcp/tool-use 扩展）

## Why

架构审计（`coding-plan/architecture-audit.md`，2026-09-26）结论：架构对 **skill** 有完整闭环（L3 skillhub：市场发现→多源路由→签名校验→发布审核），但 **mcp / cli** 无运行期安装生命周期；plugin-registry 只有进程内生命周期（注册/启停/卸载/依赖/隔离），无「来源（PluginSource）」抽象；skillhub 的「签名校验 / 多源路由」未上提到统一层复用，导致 mcp/cli 无法复用；tool-use 无 install/uninstall 工具，Agent 无法经 AI 对话安装。本 change 闭合维度 A（三方插件统一安装）：扩展 L0 plugin-registry 提供统一「可安装资产 + 来源」抽象，横切 mcp 补安装/移除生命周期，L1 tool-use 补 install/uninstall/list 三工具（契约层，代码随 Phase 3）。

## What Changes

- **插件来源与安装**（plugin-registry，ADDED）：系统 SHALL 支持从四类来源（local-path / git-repo / market-registry / mcp-endpoint）安装插件，统一 discover→verify→install→register→activate→deactivate→uninstall 生命周期；skillhub 签名校验/多源路由语义上提到此统一层。
- **MCP Server 安装与移除**（mcp，ADDED）：mcp add/remove 复用 PluginSource（mcp-endpoint），安装后进入现有连接管理，移除释放连接资源。
- **插件安装工具**（tool-use，ADDED）：install / uninstall / list 三工具，经 SafetyGate + 权限审批流约束。
- **delta 双写**：`changes/0028-plugin-install/specs/{plugin-registry,mcp,tool-use}/spec.md`（delta 与 specs 根目录逐字一致）。
- **data-model.md**：横切实体表追加 `InstallableAsset / PluginSource` 单一权威索引（M1/M2/M3 共享，spec 不写字段）。
- **adr.md**：追加 ADR-0037（统一插件安装抽象）。

## Impact

- **Affected specs**：`plugin-registry`（扩展：Purpose + 追加「插件来源与安装」）；`mcp`（扩展：Purpose + 追加「MCP Server 安装与移除」）；`tool-use`（扩展：Purpose + 追加「插件安装工具」）
- **Affected docs**：`openspec/changes/0028-plugin-install/`（新建三件套 + delta）、`openspec/specs/plugin-registry/spec.md`、`openspec/specs/mcp/spec.md`、`openspec/specs/tool-use/spec.md`、`01-architecture/data-model.md`（横切表 +1 行）、`01-architecture/adr.md`（+ADR-0037）
- **Affected code**：M1（plugin-registry：InstallableAsset/PluginSource/生命周期 + SOURCE_NOT_FOUND/SIGNATURE_INVALID/INSTALL_FAILED）、M2（mcp：add/remove）本 Phase 回填；M3（tool-use install/uninstall/list）代码随 Phase 3
- **Dependencies**：ADR 编号=当前最大+1（0037）；skillhub 现有 4 Requirement 不动（D3 语义上提不合并执行实现）；InstallableAsset{kind} 只做 registry 层统一，不合并 skill/mcp/cli 执行实现
