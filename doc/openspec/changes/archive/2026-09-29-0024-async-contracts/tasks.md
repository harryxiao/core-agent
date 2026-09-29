# Tasks

## 1. 架构决策（P0）

- [x] 1.1 adr.md 追加 ADR-0033「async 为主 + sync 薄壳」（编号=0032+1；三点理由：真并发扇出、流式编排、薄壳复用 asyncio.run 兼容既有调用方）

## 2. spec delta（P0）

- [x] 2.1 specs/llm-provider/spec.md delta：## ADDED Requirements「异步调用接口」acompletion/astream/aembedding + sync 薄壳语义
- [x] 2.2 specs/tool-use/spec.md delta：## ADDED Requirements「异步工具调用」ainvoke + sync 薄壳语义
- [x] 2.3 specs/loop/spec.md delta：## ADDED Requirements「异步流式执行」arun/astream + LoopEvent 五事件（loop_started/step_completed/reply_delta/loop_finished/loop_failed）
- [x] 2.4 specs/orchestration/spec.md delta：## ADDED Requirements「异步执行单元契约」扇出执行单元复用 acompletion/ainvoke

## 3. spec merged（P0）

- [x] 3.1 specs/llm-provider/spec.md 正文：Purpose 双向 + 追加异步 Requirement（与 delta 逐字一致）
- [x] 3.2 specs/tool-use/spec.md 正文：同上（与 delta 逐字一致）
- [x] 3.3 specs/loop/spec.md 正文：同上（与 delta 逐字一致）
- [x] 3.4 specs/orchestration/spec.md 正文：同上（与 delta 逐字一致）

## 4. 接口文档（P0）

- [x] 4.1 03-interfaces/llm-provider-interface.md 方法表加 acompletion/astream/aembedding 签名
- [x] 4.2 03-interfaces/tool-use-interface.md 加 ainvoke 签名
- [x] 4.3 03-interfaces/loop-interface.md 加 arun/astream 签名 + LoopEvent 定义

## 5. 架构留痕（P0）

- [x] 5.1 01-architecture/architecture-overview.md L111 留痕句改写（「预留接口待落地」→「异步契约已定义，sync 为薄壳」）

## 6. 验证（P0）

- [x] 6.1 validate --all 全绿 + git status 双向核对（Affected docs 列表 ↔ 实际改动文件一一对应）
- [x] 6.2 独立验证 subagent（读 plan_sop 第四章 → verify_context.json → 启动 → VERDICT → 按结果处理）
