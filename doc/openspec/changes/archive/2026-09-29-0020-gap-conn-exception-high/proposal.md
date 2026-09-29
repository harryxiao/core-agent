# Change: 连接与异常处理查漏补缺（高优先级四模块）

## Why

全局架构审查（2026-09-22）发现：多个能力模块的异常处理与连接管理存在缺口——涉及连接的模块（distributed / llm-provider / git）缺少连接保活 / 心跳 / 超时 / 断线重连 / 资源释放等生命周期管理；tool-use 的 requirements 已声明「撤销与时间旅行回滚」「超时与资源上限」但 spec 正文完全缺失。这些缺口会导致 A2A 协作、模型调用、远程 Git 操作在断线 / 超时 / 认证失败等异常场景下无限挂起、资源泄漏或任务重复执行。本 change 补齐高优先级四模块的异常处理与连接管理语义。

## What Changes

- 扩展 `distributed` capability：ADDED R8「A2A 连接管理」——系统 SHALL 管理 A2A 对等连接的完整生命周期（保活 / 心跳 / 重连 / 超时 / 资源释放 / 委派幂等）
- 扩展 `llm-provider` capability：ADDED R6「模型调用可靠性」——系统 SHALL 保障模型调用可靠性（重试 / 降级 / 超时 / 连接复用 / 流式断流恢复）
- 扩展 `tool-use` capability：ADDED R3「撤销与时间旅行回滚」+ R4「超时与资源上限」——补齐 requirements 已声明但 spec 正文缺失的能力
- 扩展 `git` capability：ADDED R5「远程操作可靠性」——系统 SHALL 保障远程 Git 操作可靠性（超时 / 认证失败 / 断线重试 / 连接释放）

## Impact

- **Affected specs**：扩展 `distributed`（ADDED R8）、`llm-provider`（ADDED R6）、`tool-use`（ADDED R3/R4）、`git`（ADDED R5）
- **Affected docs**：`specs/distributed/spec.md`、`specs/llm-provider/spec.md`、`specs/tool-use/spec.md`、`specs/git/spec.md`、`00-product/requirements.md`（1.15 节追加 CORE-LLM-R6 行、1.17 节追加 CORE-DIST-R8 行、1.19 节追加 CORE-GIT-R5 行）
- **Affected code**：无（本 change 声明异常处理与连接管理语义，不涉及具体实现代码）
- **Dependencies**：复用 `constraints` 横切容错中间件层的熔断 / 回滚语义；tool-use R3/R4 语义源自 requirements 既有声明
