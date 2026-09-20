# 版本控制：让 Core-Agent 默认支持 Git 以完美支撑 Coding 编码能力

> 对应规格：`doc/openspec/specs/git/spec.md` ｜ 变更提案：`doc/openspec/changes/0011-git/`
> 本方案文档对应 ADR-0026

---

## 1. 定位与场景

Core-Agent 需完美支持 Coding 编码功能，默认支持 Git 是编码闭环的必要能力：代码改动需版本化管理（commit/branch/merge/diff/log/status），远程协作需 clone/pull/push。Git 有独立状态机 + .git 保护 + 凭据安全面，故独立为 capability（非 tool-use 内置工具）。

## 2. 总体架构

| 组件 | 职责 |
|---|---|
| Git 操作器 | clone/init/commit/branch/checkout/diff/merge/log/status/pull/push |
| 仓库守卫 | .git 元数据保护 + 工作区回滚 |
| 凭据适配 | keychain 存取凭据、日志脱敏 |
| 审批桥 | 高危操作接入 permission 审批链 |

## 3. 核心流程

1. **版本控制**：工作区改动 → commit → 生成记录；多分支 → checkout/merge → 冲突明确报告。
2. **保护**：操作前校验 .git 元数据 → 默认拒绝改写；操作失败 → 回滚至操作前状态。
3. **凭据**：远程操作认证 → keychain 存取 → 不落盘明文、日志脱敏。
4. **审批**：高危操作（force-push / 删远程分支 / 历史改写）→ permission 审批链。

## 4. 接口设计

| 接口 | 说明 |
|---|---|
| `clone` / `init` | 仓库初始化与克隆 |
| `commit` / `branch` / `checkout` / `diff` / `merge` / `log` / `status` | 本地版本控制 |
| `pull` / `push` | 远程协作 |
| `force-push` / `branch-delete` / `history-rewrite` | 高危操作，走审批链 |

## 5. 与其他模块的关系

| 模块 | 关系 |
|---|---|
| permission | 复用：高危操作审批链 + 沙箱 |
| keychain | 复用：凭据安全存储 |
| rag / codebase-memory-mcp | 互补：Git = 版本控制操作，非代码理解 |

## 6. ADR 索引

| ADR | 决策 |
|---|---|
| ADR-0026 | Git 独立为 capability，凭据走 keychain，高危操作走 permission 审批链 |
