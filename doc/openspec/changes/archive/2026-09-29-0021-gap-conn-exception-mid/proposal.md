# Change: 异常处理与连接管理查漏补缺（中优先级八模块）

## Why

全局架构审查（2026-09-22）发现：中优先级八模块的异常处理与连接管理存在缺口——ui 的 SSE 流式连接缺少断线重连与心跳；deployment 的 Harness Host 缺少客户端断线清理与资源释放；observability 的遥测缓冲缺少上限与溢出兜底；rag 的摄取管线缺少失败降级；memory 的检索与压实缺少降级与并发一致性；orchestration 缺少断点续跑与 fan-out 幂等；im 缺少重复消息幂等与重连退避；skills 缺少超时与资源上限。这些缺口会导致流式输出卡死、资源泄漏、缓冲无限增长、索引损坏阻断检索、任务挂起无法恢复、重复消息重复处理、技能执行拖垮主循环。本 change 补齐中优先级八模块的异常处理与连接管理语义。

## What Changes

- 新增 `ui`（MODIFIED SSE 断线重连）、`deployment`（ADDED 客户端断线与会话清理）、`observability`（ADDED 遥测缓冲与导出重试）、`rag`（MODIFIED 摄取/重建失败降级）、`memory`（MODIFIED 检索失败降级 + 并发压实一致性）、`orchestration`（ADDED 断点续跑 + MODIFIED fan-out 幂等派发）、`im`（MODIFIED 重复消息幂等 + 重连退避）、`skills`（ADDED 超时与资源上限）共 8 个 capability 的 spec

## Impact

- **Affected specs**：`specs/ui/spec.md`、`specs/deployment/spec.md`、`specs/observability/spec.md`、`specs/rag/spec.md`、`specs/memory/spec.md`、`specs/orchestration/spec.md`、`specs/im/spec.md`、`specs/skills/spec.md`
- **Affected docs**：`00-product/requirements.md`（1.20 节追加 CORE-DEP-R6 行、1.9 节追加 CORE-OBS-R5 行、1.11 节追加 CORE-SKILL-R5 行）
- **Affected code**：无（本 change 声明异常处理与连接管理语义，不涉及具体实现代码）
- **Dependencies**：无（八模块缺口相互独立，互不依赖）
