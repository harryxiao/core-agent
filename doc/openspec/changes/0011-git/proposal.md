# Change: Git 版本控制默认支持（Coding 编码能力）

## Why

Core-Agent 需完美支持 Coding 编码功能，默认支持 Git 是编码闭环的必要能力：代码改动需版本化管理（commit/branch/merge/diff/log/status），远程协作需 clone/pull/push。Git 有独立状态机 + .git 保护 + 凭据安全面，按决策 D1 独立为 capability（来源：research_findings.md，2026-09-20）。

## What Changes

- 新增 `git` capability：版本控制核心操作（clone/init/commit/branch/checkout/diff/merge/log/status/pull/push）
- .git 仓库与工作区保护（默认拒绝改 .git 元数据、操作失败不损坏工作区）
- 凭据安全（keychain 存储、不落盘明文、日志不泄露）
- 高危操作（force-push / 删除远程分支 / 历史改写）走 permission 审批链

## Impact

- **Affected specs**：`git`（新增 capability）
- **Affected docs**：`12-git/git-architecture.md`（新增）、`README.md`（索引）
- **Affected code**：无（本 change 声明版本控制行为，具体实现由后续步骤确定）
- **Dependencies**：复用 `permission`（审批链 + 沙箱）、`keychain`（凭据存储）；与 `rag` / codebase-memory-mcp 互补（Git = 版本控制操作，非代码理解）
