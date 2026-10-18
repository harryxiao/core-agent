# Design 0263 — 压实丢弃与产出的可观测计数

## D1 计数从压实产物直接取

`Compaction` 已携带 `conclusions` / `decisions` / `open_items` / `dropped` 四个列表。`_compact`
原先把 `self._compactor.compact(ctx.messages)` 内联在 `persist(...)` 实参里，拿不到产物；改为
先赋值、再 `persist`：

```python
counts = {"messages": len(ctx.messages), "conclusions": 0, "decisions": 0,
          "open_items": 0, "dropped": 0}
try:
    compaction = self._compactor.compact(ctx.messages)
    counts.update(conclusions=len(compaction.conclusions), ...)
    self._compactor.persist(compaction, session_id=ctx.session_id)
except ContextError:
    ...
```

`messages` 在 `try` 之前取，恒为输入长度；其余四项在 `compact` 成功后才填 —— `compact`
抛异常时保持 `0`。`persist` 失败时计数已取得，事件照常带真实产出计数（`persist` 失败只影响
落盘，不影响「压出/丢了什么」）。

## D2 payload 扩展与红线

新增键：`messages` / `conclusions` / `decisions` / `open_items` / `dropped`，均为整数计数。
既有键 `trigger` / `elapsed_ms` / `steps` 逐字保留。**不**记录任何条目 id 或正文 —— payload
红线（不含正文、摘要文本、会话标识）不变。

## D3 不发 `kept`

`messages - dropped` 不是「保留」口径：`dropped` 只统计**有 id 且 `redundant=True`** 的冗余
条目（生产中通常为空），而消息是被摘要 / 结论**替换**而非逐条保留。发 `kept` 会让消费方误读
「保留了多少条消息」。以 `messages`（输入量）与四个产物计数提供「本轮消化了多少、产出了多少」
的可比数字即可。

## D4 事件契约钉住

测试除逐项断言计数外，另断言 payload 的**顶层 key 集合**恰为八个键 —— 防止未来误删既有键或
漏发新键；`steps` 键集仍单独断言。

## 反证

1. 去掉 `dropped` 计数（恒 0）⇒ 计数用例红。
2. `compact` 抛错时仍填产物计数（改为先填非零默认）⇒ 全 0 用例红。
3. 摘掉 `messages` 键 ⇒ 顶层 key 集合用例红。

## 已知局限

- `dropped` 仅统计 `Compaction.dropped`（有 id 的冗余条目），生产中通常为空；「压缩了多少
  消息」需结合 `messages` 与产物计数理解，不是逐条账。
- 不记录 token 前后量（需额外的估算口径，且压实是替换而非删除）。
- 计数在 `compact` 返回后、`persist` 前取得：若 `compact` 部分产出后抛错，计数记 0（不反映
  部分产物）—— 与「失败即无产物」的既有降级语义一致。
