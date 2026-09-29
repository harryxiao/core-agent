# Change: 异常处理与连接管理查漏补缺（低优先级七模块）

## Why

全局架构审查（2026-09-22）发现：低优先级七模块的健壮性与连接管理存在轻微缺口——mcp 的「心跳」仅在 Requirement 文字提及、无独立保活 Scenario，且缺连接关闭与资源释放条目；plugin-registry 缺并发热插拔原子性与注册超时；loop 的「该轮回滚」（R3）在 spec 无显式 Scenario；composition 缺 bundle 循环依赖检测与 patch.yml 覆盖冲突兜底；context 缺重建失败的二阶兜底（全文检索也失败时）；permission 的沙箱「自动销毁」（R3）无资源回收 Scenario；evolution 缺多提案并发评测资源上限。这些缺口会导致 MCP 连接泄漏、插件热插拔竞态、单轮失败污染后续轮次、循环依赖致 bundle 分发失败、重建失败后检索不可用、沙箱资源泄漏、并发评测打爆资源。本 change 补齐低优先级七模块的健壮性语义。

## What Changes

- 新增 `mcp`（MODIFIED 心跳保活 + 连接关闭与资源释放）、`plugin-registry`（MODIFIED 并发热插拔原子性 + 注册超时）、`loop`（MODIFIED 单轮回滚）、`composition`（MODIFIED bundle 循环依赖检测 + patch.yml 覆盖冲突兜底）、`context`（MODIFIED 重建失败二阶兜底）、`permission`（MODIFIED 沙箱销毁与资源回收）、`evolution`（MODIFIED 并发评测资源上限）共 7 个 capability 的 spec

## Impact

- **Affected specs**：`specs/mcp/spec.md`、`specs/plugin-registry/spec.md`、`specs/loop/spec.md`、`specs/composition/spec.md`、`specs/context/spec.md`、`specs/permission/spec.md`、`specs/evolution/spec.md`
- **Affected docs**：无（本 change 均为对既有 Requirement 追加 Scenario，不新增 Requirement，`00-product/requirements.md` 无改动）
- **Affected code**：无（本 change 声明健壮性与连接管理语义，不涉及具体实现代码）
- **Dependencies**：无（七模块缺口相互独立，互不依赖）
