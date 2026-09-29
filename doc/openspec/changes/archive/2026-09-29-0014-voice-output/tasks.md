# Tasks

> **状态**：spec「实时语音输出」已并入 base `ui/spec.md`；本 change 为 spec-only（proposal 已声明 `Affected code: 无`）。以下 6 条代码任务 deferred（TTS 引擎选型留待实现阶段），非本 change 范围，故不勾选。

## 1. 流式语音播报（P0）

- [ ] 1.1 内核流式文本分片接入 TTS 合成并连续播报　【deferred】
- [ ] 1.2 播报队列与缓冲，避免分片合成卡顿导致的断续　【deferred】

## 2. 打断与全双工（P0）

- [ ] 2.1 barge-in：开口/按键立即停止播报并转入语音输入　【deferred】
- [ ] 2.2 被打断文本保留在会话记录，不丢失　【deferred】

## 3. 上下文与三模一致（P1）

- [ ] 3.1 语音与文本共享同一会话记录，支持相互引用　【deferred】
- [ ] 3.2 CLI / Web / Desktop 三模语音输出行为一致　【deferred】
