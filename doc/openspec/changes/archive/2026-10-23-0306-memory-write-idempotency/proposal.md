# Proposal — 0306 写入幂等重放

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 §5.1「幂等：同一 `(eventId, namespace)` 在保留窗口内只写
一次；重试是 at-least-once，但落库是幂等的」与走查 **P1-6**。

本仓的记忆写入**逻辑 id 稳定**（`loop.<trace>` / `loop.steps.<trace>` / `compaction.summary.<key>` /
`keyfact.<slug>` 等），重复投递不会产生重复条目。但**重放同一条逻辑写入仍是破坏性的**（实测）：

1. `reuse_count` 被重置为 0 —— 重放会把累积的复用证据清零，而该计数正是技能结晶阈值（3 次）的依据；
2. `ts` 被改写（旧条目变「新鲜」）—— 影响新鲜度排序与遗忘衰减；
3. 重复记录 `memory.write` 效应 —— 回滚账目多出无意义的撤销，跨 trace 回滚更易误删；
4. 重复触发 `write_observer` —— 钩子方按「一次写入一次通知」实现时会重复处理；
5. 重复执行重要度评分 —— 注入评分器时重放会二次消耗模型调用。

## What Changes

`MemoryStore.write()` 增加**幂等快路径**：同层已存在同 id 条目，且语义载荷与原条目相同
（见 design D1 的相等口径；`reuse_count`、`importance` 与入参 `ts <= 0` 不参与比较）⇒ 直接返回既有 id，
**零落盘、零效应、零通知、零评分**。

## Non-goals

- **不加**重试 / 本地 spool / 死信队列：本仓本地 JSONL 是唯一权威，写入以原子替换落盘，失败向
  调用方传播（`memory.md` §5 已由 change `0302` 订正为「不重试、无本地队列」）；spool 会引入第二
  权威并掩盖真实失败。
- **不做**内容指纹跨 id 去重：不同 trace 的相同正文是**不同事件**（重试是独立证据），按内容合并会
  销毁合法记忆。
- **不**把「同 id 不同载荷」的写入改成合并/保留旧字段：那是覆盖语义，不属于重放。
- 不改既有 `_persist` / 效应撤销的结构。

## Impact

- 代码：`src/core/memory/store.py`（`write()` 前置判断 + 私有相等谓词）。
- 行为：重复投递同一条写入由「破坏性覆盖」变为 no-op；首次写入与不同载荷写入逐字不变。
- 规格：`memory` **ADDED** ×1。
- 测试：新增 `tests/test_memory_write_idempotency.py`。
