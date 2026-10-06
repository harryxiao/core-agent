# 变更提案：压实按会话收窄 + 记忆分档口径两档（change 0131 / 账本 E66 + E78）

## 背景（两处账）

### E66（真缺陷·中高）—— `/session/compact` 压实**全场**

`src/core/ui/api.py:215` 的 `self._memory.compact(session_id)` **按位置**把 session_id 传给了
`MemoryStore.compact(query="")` 的 **`query`** 形参。而 `compact` 的摘要路径 `_summarize_sessions()`
**不留参**地遍历 `_episodic_groups()` —— 即**全库所有会话**的 L2 episodic 条目。

后果：用户在前端点「压缩会话 A 的记忆」，实际触发的是**全库压实** —— 会话 B、C 的条目被一并提炼、
一并迁 L4 归档（其 `trace_id` 为各自的 `compaction.<session_id>`，但**从未被请求**）。且 `session_id`
被当成 query 用，决策评分的 `count`/`query` 语义也是错的。

规格 `memory/spec.md`「记忆压实」已 SHALL「**按会话**（`session_id`）聚合 episodic 条目」—— 现状**违反**。

### E78（规格漂移·中）—— 记忆分档：规格三档、实现两档

`memory/spec.md`「温度分层检索」SHALL「提供**热/温/冷三档**检索」，但实现（`store.py`）只有
`_hot`（热，进程内常驻）+ L4 归档层（冷，经 backend 按需读）；**没有任何「温」层**（grep `温` 全仓
仅 4 处，三处是「温度分层检索」这个**词条名**、一处是 `core/memory/__init__.py:3` 自述的「热/冷」）。
规格写了实现不存在的第三档 ⇒ **规格漂移**。

## 决策

1. **E66**：`MemoryStore.compact` 增**关键字形参** `session_id: str = ""`；`_summarize_sessions` /
   `_episodic_groups` 同增可选过滤。**非空** ⇒ 只聚合该会话条目；**空串** ⇒ 逐字保留全量语义
   （既有调用点零改动）。`ui/api.py` 改传 `session_id=`。
2. **E78**：**规格改两档**（用户裁决）—— 「温度分层检索」的「热/温/冷三档」改「**热/冷两档**」，
   删除温层 SHALL。**不动代码**（实现本就是两档，无第三档可删 —— 温层无语义 ⇒ YAGNI）。

### 不做

- **不**给「温」层补实现（用户裁决：删 SHALL 而非补层；温层只增加机制不增加语义）。
- **不**改 `_commit_summary` / `_write_importance` 的 trace 口径（仍是 `compaction.<session_id>`）。
- **不**动 `loop/default.py:412` 的 `memory.compact()`（循环内压实是全库节拍，非会话入口）。

## 规格 delta

`memory` **MODIFIED** ×2：
- 「记忆压实」—— 补「`compact` SHALL 接受可选 `session_id`；非空 SHALL 只聚合该会话 episodic、
  SHALL NOT 跨会话提炼；空串语义逐字不变」+ 1 Scenario「压实按会话收窄，不触他会话」。
- 「温度分层检索」—— 三档改两档，删温层。

## 影响面

| 面 | 改动 |
|---|---|
| `src/core/memory/store.py` | `compact(…, *, session_id="")` + `_summarize_sessions` / `_episodic_groups` 过滤 |
| `src/core/ui/api.py` | `compact(session_id=session_id)` |
| `tests/` | `test_memory.py`（A 压实不动 B；空串回全量）+ `test_ui.py`（fake 签名）+ `test_serve.py` |
| 文档 | ADR-0124 + `memory-interface.md` + `02-modules/memory.md` + TC 节 |
