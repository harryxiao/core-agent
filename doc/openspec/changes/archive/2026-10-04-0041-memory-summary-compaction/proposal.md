# Change: 记忆摘要式压实（Summarizer 接缝 + 会话聚合 + 归档可逆 + 触发接线）

## Why

「记忆压实」这一路径**在生产是死的**，且机制与规格不符：

- `MemoryStore.compact` 仍是**判分器**（`judgment.Compactor.score` → 保留/丢弃），无摘要提炼；
  且全仓唯一生产调用点 `ui/api.py::compact` 是显式 no-op（注释：「MemoryStore 无显式 compact」）。
- `context.Compactor`（多轮历史压实器）**无任何生产构造点**（仅测试构造）→ context spec
  「触发压实并沉淀」、loop spec「token 预算超限 → 触发上下文压实」两条 Scenario 均未成真。
- `persist` 落 L2 的条目是**关键词启发式**（匹配「结论/决定/待」），`kind` 默认 `episodic`、
  `source`/`trace_id` 为常量 → 原文不可追溯，与「压实可逆」相冲。
- `MemoryStore.migrate` **不记 EffectTracker** → 层级迁移不可撤销（违反开发约定 #3）。

## What Changes

- **摘要接缝**（memory）：新增 `Summarizer = Callable[[list[MemoryEntry]], str]` 与
  `summarize_with(llm)` 适配器（`memory/summarize.py`），照 0039 `batch_embed` 先例——
  memory 不 import llm-provider，组合根注入。
- **压实升级**（memory）：`MemoryStore(..., summarizer=)`；`compact` 在注入摘要器时按
  `session_id` 聚合 episodic 条目 → 提炼**一条** `kind="semantic"` 摘要条目（`tags` 携带原始
  条目 id，`source="compaction"`，`trace_id=f"compaction.{session_id}"`）→ 原条目 `migrate` 至
  L4。未注入摘要器时不做提炼（降级：仅评分，原条目不动）。签名与返回类型不变
  （`DecisionResult | None`）。
- **迁移可逆**（memory）：`migrate` 记 `EffectTracker`（undo 迁回原层）。
- **context 收口**：`Compactor.persist` 产物改为 `kind="semantic"` + 标注原始 id 出处，
  并明确其为**启发式降级路径**（LLM 提炼统一归 memory 的摘要通道，不新增第二个 LLM 调用点）。
- **触发接线**（loop + runtime）：`DefaultLoop` 注入 `compactor`，在既有
  `should_compact(rounds, token_used, budget)` 为真或 token 预算超限时触发
  「压实历史 → 落 L2 → memory 摘要提炼」；runtime 构造 `context.Compactor(memory=memory)`
  与 `Summarizer` 并注入。

## Non-goals

- 不做跨会话语义聚类（本轮按 `session_id` 分组；聚类留作后续增强）。
- 不做 session 结束的固化时机与遗忘衰减（属 Phase 18 #4/#5）。
- 不引入第二个 LLM 调用点（context 压实只做启发式沉淀）。
- 不改变 loop 终止语义（压实触发后仍按既有 `TOKEN_BUDGET_EXCEEDED` 终止）。
- 不新增并发锁（「并发压实一致性」Scenario 的守护与既有实现缺口一致，见 design 已知缺口）。

## Impact

- **Affected specs**：`memory/spec.md`（1 MODIFIED：「记忆压实」）、
  `context/spec.md`（1 MODIFIED：「上下文自动压实」）。
  `loop/spec.md` **不改**——既有 Scenario「token 预算超限 → 触发上下文压实」本就要求此举，
  本次是让实现追上规格。
- **Affected docs**：`03-interfaces/memory-interface.md`（compact/摘要条目）、
  `03-interfaces/context-interface.md`（persist 产物）、
  `01-architecture/adr.md`（新增 ADR-0046：摘要接缝与压实可逆）。
- **Affected code**：`src/core/memory/summarize.py`（新）、`store.py`、`__init__.py`、
  `src/core/context/compactor.py`、`src/core/loop/default.py`、`src/core/runtime.py`。
- **Dependencies**：无新三方依赖；复用既有 `judgment.Compactor` / `EffectTracker` / `LLMProvider`。
- **风险**：中。`compact` 由只读变成**会写**（摘要 + 迁移），故必须：① 全部效应可撤销；
  ② 未注入摘要器/压实器时行为与现状一致（不写、不迁移）。
