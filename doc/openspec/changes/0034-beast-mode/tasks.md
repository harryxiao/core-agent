# Tasks

## 1. 契约层 — beast-mode spec delta（P0，本 Phase）

- [x] 1.1 写 8 Requirement（Beast Registry / Beast Session Lifecycle / Summon via Handoff / Independent Sub-Agent with Shared Capability / Innate Skills and Dedicated Routing / Async Concurrent Execution and Auto-Recall / Manual Recall / Three-Entry Activation）
- [x] 1.2 proposal What Changes ADDED bullet 标题与 delta Requirement 逐字一致
- [x] 1.3 delta 与 specs/beast-mode/spec.md 逐字一致（archive 后）

## 2. loop/orchestration 契约 delta（P0，本 Phase）

- [x] 2.1 MODIFIED loop「执行循环」：LoopResult 补 failed 成败信号
- [x] 2.2 MODIFIED orchestration「多 Agent 协同」：handoff 异步执行（loop.arun）并返回完整 LoopResult

## 3. 需求编号（P0，本 Phase）

- [x] 3.1 requirements.md 新增 1.28 beast-mode（CORE-BEAST-R1~R8）

## 4. 验证（P0）

- [x] 4.1 openspec validate --all 全绿
