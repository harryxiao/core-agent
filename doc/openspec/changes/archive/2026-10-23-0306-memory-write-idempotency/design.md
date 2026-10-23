# Design — 0306 写入幂等重放

## D1 相等口径

```python
def _same_payload(self, existing: MemoryEntry, incoming: MemoryEntry, layer: Layer) -> bool:
    if existing.layer != layer:
        return False
    if existing.content != incoming.content:      # 精确比较，不做归一化
        return False
    if existing.tags != incoming.tags: ...
    # source / trace_id / session_id / kind / status / version /
    # parent_id / superseded_by 逐项相等
    # reuse_count：**不比较**（累积证据不参与载荷身份）
    # importance：**不比较**（由闸门写回，非调用方载荷；本仓无调用方显式设置）
    # ts：入参 <= 0 视为「未指定」⇒ 不比较；入参显式给值 ⇒ 必须相等
```

**被拒**：用 `content_hash` 判等（会把仅首尾空白不同的正文判为同一条，与 `write()` 的覆盖语义
不一致）；把 `reuse_count` 纳入比较（重放时入参恒 0 ⇒ 永不相等 ⇒ 幂等失效）；`ts` 严格比较
（所有调用方都以 `ts=0` 表示「现在」，严格比较会让快路径永不命中）。

## D2 快路径位置

判断放在「无行动不记忆」守卫**之后**、重要度评分**之前**：重放不应二次消耗评分器（注入评分器时
是真实 LLM 成本），也不应二次触发闸门降级/写回。命中即 `return existing.id`，不调用 `_persist`、
`_enforce_l2_cap`、`_notify_write`。

**被拒**：在 `_persist` 内做判断（效应已在上层记录，且评分已发生，救不回来）；在效应层按目标去重
（`EffectTracker` 是通用基础设施，不应理解记忆条目的载荷语义）。

## D3 与既有幂等的关系

逻辑 id 稳定已保证「重复投递不产生**重复条目**」；本 change 补的是「重复投递不产生**重复副作用**
与**证据丢失**」。`remember` / `compact` / 同值关键事实的重放由既有测试路径覆盖，新增用例把
「条目集合不增」与「效应/通知不增」一并钉住。

## D4 局限

- 同 id **不同载荷**仍是覆盖（`reuse_count` 归零、`ts` 更新）——那是「同一 id 的新内容」，不是重放；
  若未来出现「内容修订但复用证据应延续」的消费方，再单独设计。
- 快路径只比较单条载荷，不做跨条目的内容指纹去重（重试/不同 trace 的同文事件是独立证据）。
- 相同载荷的跨 trace 重放不再产生该 trace 的效应 ⇒ 回滚**首个**创建该条目的 trace 会删除条目，
  即使后续 trace 重放过同一载荷（不支持多 trace 共同所有权；如需引用计数须另立设计）。
- 重放不再刷新 `ts`：同一事件重复到达不构成新的新鲜度证据（对齐 SDD「只写一次」）。

## 测试与反证计划

`tests/test_memory_write_idempotency.py`：

1. 同载荷重放 ⇒ 单条、`reuse_count` 保留、`ts` 不变、`memory.write` 效应数不增；
2. 重放不触发 `write_observer`；
3. 注入评分器时重放不二次评分；
4. 不同载荷（正文 / 标签）同 id ⇒ 正常覆盖，效应数 +1（不误判）；
5. 不同 id 同正文 ⇒ 两条（不按内容去重）；
6. `remember` 同 trace 重放、`compact` 同会话重放 ⇒ 条目集合与效应数不增。

反证（`cp` + `md5sum`）：去掉快路径 ⇒ 1/2/3/6 红；把 `reuse_count` 纳入比较 ⇒ 1 红；把 `ts` 严格
比较 ⇒ 1 红（`ts=0` 入参不命中）；按正文跨 id 去重 ⇒ 5 红。
