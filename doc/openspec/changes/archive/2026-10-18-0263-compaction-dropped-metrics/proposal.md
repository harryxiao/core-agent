# Proposal 0263 — 压实丢弃与产出的可观测计数

## Why

`compaction` 成本事件目前只有 `trigger` / `elapsed_ms` / `steps`：能回答「压实花了多久」，
回答不了「这次压实消化了多少、产出了什么、丢了什么」。当上下文被压实后模型表现变差、或
用户质疑「为什么这条信息没了」时，运维面没有可比数字。对比审查（2026-10-18）把「压实丢弃
不可观测」列为 P1 短板。

## What Changes

- `DefaultLoop._compact` 先取 `compaction = Compactor.compact(ctx.messages)`，再 `persist`；
  在既有 `compaction` 事件 payload 中补五个**计数**：
  - `messages`：本轮输入消息数（`len(ctx.messages)`）；
  - `conclusions` / `decisions` / `open_items` / `dropped`：压实产物的各列表长度。
- `compact` 抛异常时五项记 `0`；`persist` 失败不影响已取得的计数。事件次数、
  `trigger` / `elapsed_ms` / `steps` 与写回/终止语义逐字不变。
- **不发** `kept`：`messages - dropped` 不是「保留」口径（`dropped` 是有 id 的冗余条目，
  消息经摘要被替换而非逐条保留），语义含混。

## Impact

- `src/core/loop/default.py`（`_compact`）。
- 规格：`observability` **MODIFIED**「全链路日志」（payload 增五项计数 + 1 scenario）。
- 文档：`doc/02-modules/loop.md`、`doc/03-interfaces/observability-interface.md`、
  `doc/04-testing/test-cases.md` §175、ADR-0253 / 台账 E199。
- 测试：`tests/test_loop_cost_observability.py`（计数、顶层 key 集、compact 抛错全 0）。

## 不做（明确边界）

- 不记录被丢弃条目的正文 / id（payload 红线：不含正文、摘要与会话标识）。
- 不改 `Compactor` 的压缩算法、`Compaction` 字段或写回语义。
- 不发 `kept` / `tokens_before` / `tokens_after`（语义含混或需额外计数口径，另立 change）。
