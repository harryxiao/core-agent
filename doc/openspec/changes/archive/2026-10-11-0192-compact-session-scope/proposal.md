# Change 0192 — 轮内压实会话化 + trace 会话键 + 诚实化

## Why

长任务评估取证（2026-10-11）——**同一条循环里两套压实口径**：

1. **轮内压实全会话聚合**：`DefaultLoop._compact` 裸调 `self._memory.compact()`
   （`src/core/loop/default.py:668`）⇒ 空 `session_id` = **全量聚合**，把**所有会话**的 L2 episodic
   条目一并提炼归档；而同循环的维护节拍 `_maintain`（`default.py:584`）却**会话化**
   （`self._memory.compact(session_id=session_id)`）⇒ 同一实例内两条路径**口径相反**。一个正在跑的
   长任务会话触发轮内压实，会**顺手提炼并归档他会话**的条目（违反「按会话归组」的规格口径，且
   跨会话串扰）。
2. **契约注失真**：`store.py:421-424` 的 `compact` 契约注写「**空串**……逐字与既有行为一致（供
   **循环内节拍压实使用**）」—— 但节拍路径**其实传 session**（`default.py:584`），该justification
   已**不成立**；空串全量语义的实际用途只剩**显式 CLI / 运维调用**。
3. **trace 常量非会话键**：`Compactor.persist` 用**常量** `trace_id="compaction"`
   （`compactor.py:102/:116`），而记忆侧其他所有压实 trace 都是 `f"compaction.<key>"`
   （会话摘要 `store.py:670`、关键事实 `store.py:773`、中期摘要 `store.py:486`、
   `_write_importance` `store.py:631`）⇒ 常量 trace 使**回滚归因过粗**（一次回滚跨所有会话、
   且与同会话的其他压实产物**不共组**，违反 P3 局部化与可归因）。
4. **docstring 与实输入不符**：`_compact`（`default.py:651`）与 `ContextCompactor.compact`
   （`compactor.py:44`）docstring 称「**多轮历史**提炼沉淀」，但实输入是 `ctx.messages`
   —— **仅本轮**消息（`protocol.py:54` 明禁折入 history）⇒ 文案撒谎（沿 `0182` 先例诚实化）。

## What Changes

- **轮内压实会话化**：`default.py:668` 改 `self._memory.compact(session_id=ctx.session_id)`
  ⇒ 与维护节拍**同口径**（仅聚合本轮会话条目）；空会话语义（全量）**保留给显式调用**。
- **trace 会话键**：`compactor.py` persist 的 `trace_id` 由常量 `"compaction"` 改
  `f"compaction.{key}"`（`key = session_id or "default"`，与 store 内既有口径**逐字一致**）
  ⇒ 回滚归因按会话细化、与同会话其他压实产物共组。
- **诚实化**：`_compact` 与 `ContextCompactor.compact` docstring 改「**本轮**消息 + 工具 I/O；
  多轮历史由**三层滑窗**（change 0178）与记忆压实承载」；`store.py:422-423` 契约注改
  「空串全量语义保留给**显式调用**（CLI / 运维）」。
- 规格变更：`memory`「记忆压实」（归约范围口径：循环内一律会话化 + 显式调用才全量）；
  `loop`「执行循环」（轮内压实的记忆固化步骤按本轮会话收窄）；`context`「上下文自动压实」
  （产物 trace 携带会话键）。

## Impact

- **改动面**：`src/core/loop/default.py`（`_compact` 传 `session_id` + docstring）、
  `src/core/context/compactor.py`（`trace_id` 会话键化 + docstring）、
  `src/core/memory/store.py`（仅契约注 docstring）；测试面 `tests/test_loop.py`
  （轮内压实会话化 + trace 键）、`tests/test_context_compaction.py` / `tests/test_context.py`
  （persist trace 断言）。
- **零改动面**：`MemoryStore.compact` 逻辑（仅注改）；`_maintain`（本已会话化）；`summarize_slice` /
  `_summarize_sessions` / 关键事实抽取（trace 早已会话键化）；`ContextCompactor.compact` 的
  **`source_ids` / `from:<id>` provenance 面**（**死面**：`ctx.messages` 无 `id` ⇒ 恒不触发，
  本条**只注记不活化** —— 显式不做，见 Non-goals）。
- **兼容性**：空会话轮（`session_id=""`）行为**逐字不变**（`compact(session_id="")` ≡ 裸调
  `compact()`）；会话语义仅在「多会话混跑 + 轮内压实」时**收窄**（此前是串扰缺陷 ⇒ 修正是修 bug
  而非破坏契约）。trace 值变更：无测试/生产代码断言 persist trace 为常量 `"compaction"`
  （已核：仅 id 与 store 侧 trace 被断言），time-travel 消费面按 `state["trace_ids"]` 取 id、
  不硬编码该常量。

## Non-goals

- **不**活化 `ContextCompactor.compact` 的 provenance 死面（`ctx.messages` 无 `id`；扩输入面
  是多轮历史的 token 成本与去重新决策，本条只注记）。
- **不**扩压实器输入面为多轮历史（多轮历史已由三层滑窗 `0178` + 记忆压实承载）。
- **不**改 `MemoryStore.compact` 的**全量语义实现**（空串=全量逐字保留；只改**谁**在循环内以
  何种范围调用它）。
- **不**新增 trace 消费面（仍只有 time-travel / 观测）。
- **不**改 key-fact / mid / summary 的既有 trace 口径（本已会话键化）。
