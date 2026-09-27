# Design

## Context

Git 是 Coding 编码闭环的必要能力。决策 D1 确认独立为 capability（独立状态机 + .git 保护 + 凭据安全面），而非归入 tool-use 内置工具。本 design 明确 git 版本控制操作、仓库保护、凭据安全与审批协作，作为模块/接口文档与实现的依据。

## Decisions

- **独立 capability**：Git 有独立状态机 + .git 保护 + 凭据安全面，独立成 cap，不归入 tool-use 内置工具。
- **凭据走 keychain**：复用既有 keychain 组件存凭据，不落盘明文，日志不泄露。
- **高危操作审批**：force-push / 删远程分支 / 历史改写走 permission 审批链，非交互默认拒绝。

## Risks / Trade-offs

- **合并冲突**：自动 merge 遇冲突需明确报告冲突点，避免静默覆盖。
- **凭据泄露面**：远程地址与凭据出现在报错/日志需脱敏。
- **工作区损坏**：操作失败需回滚，避免半提交/半合并状态。

## Open Questions

- 是否支持子模块 / 大文件（LFS）/ 浅克隆等高级特性，还是首期仅核心操作。
- Git 底层实现选型（系统 git CLI vs libgit2/pygit2/dulwich）留待实现阶段确定。
