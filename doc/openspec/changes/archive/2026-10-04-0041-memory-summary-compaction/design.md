# Design: 记忆摘要式压实

## 决策 1：摘要接缝用 DI 可调用（`Summarizer`），不扩 judgment 原语

`Summarizer = Callable[[list[MemoryEntry]], str]`，prompt 文本属 memory 域（`memory/summarize.py`）；
组合根注入 `summarize_with(lambda p: llm.completion(...).content)`。理由：

1. 照 0039 `batch_embed` 先例——memory 不 import llm-provider（ADR-0045 同一套依赖方向），
   离线用假件可测；production 侧由组合根适配。
2. judgment spec 的 choice/score/noul 三原语是**决策**底座，摘要属**生成**；加原语会波及
   loop/permission 既有决策点，blast radius 不成比例。

`judgment.Compactor.score` 保留为「哪几条值得提炼」的**选择**步骤 —— 决策仍走决策底座，
LLM 只做提炼，职责不重叠。

## 决策 2：按 `session_id` 分组，不跨会话聚类

Phase 17 已落 `session_id` 字段（跨轮归组）。会话内 episodic 条目合成一条 semantic 摘要：
确定性、离线可断言、无需 embedder。`session_id` 为空（历史条目）归入 `""` 组。
跨会话语义聚类留作后续增强（需要 embedder 在线且质量难以离线断言）。

## 决策 3：原条目迁 L4（`migrate`）而非删除

spec 原文即「归档过期会话、保持 L1 索引最小」。L4 是归档层，`audit` 可见，不丢历史。
**但 `migrate` 当前不记 EffectTracker** → 迁出即不可逆，直接违反开发约定 #3。故本变更
一并修：`migrate` 记 `Effect(op="memory.migrate", undo=<迁回原层>)`。

## 决策 4：压实效应共用一个按会话确定的 trace_id

`compaction_trace_id = f"compaction.{session_id}"`（空会话 `"compaction.default"`）。
摘要条目的 `write` 与每条原条目的 `migrate` 都登记在该 trace 下 → `EffectTracker.rollback(tid)`
按逆序整体撤销（摘要条目移除 + 原条目迁回）。**不新增返回值**（phase-18 §6 要求签名不变），
撤销句柄由摘要条目的 `trace_id`/`tags` 暴露。

## 决策 5：出处放 `tags`，不放 `source`

phase-18 原话是「`source` 保留原始 trace_id 列表」，但实现必须偏离，理由具体：
`source` 会被 `context/assembler.py:61` 原样放进 facts 交给模型当**出处标签** —— 把一长串
trace_id 塞进 `source` 会污染 prompt 并白烧 token。故摘要条目用短标签
`source="compaction"`，原始条目 id 以 `tags=["compaction","summary","from:<id>",...]` 承载
（机器可读、prompt 安全）；完整原文仍可按 `source`/`layer=L4` 从归档追溯。

## 决策 6：context 压实定为「启发式降级路径」，不新增 LLM 调用点

`context.Compactor` 的输入是**多轮 history dict**（非 `MemoryEntry`），与 memory 的摘要通道
形状不同。强行共用需再包一层转换，且会引入第二个 LLM 调用点。故：

- `persist` 只做**两件收口**：产物改 `kind="semantic"`（不再默认 episodic）、`source` 带上
  原始 id 出处（`tags`），使「沉淀」不再是无出处的匿名条目；
- 明确它是**启发式降级路径**：LLM 提炼统一归 memory 的摘要通道（上游沉淀 → 下游提炼，单向）。

## 决策 7：loop 触发用既有 `should_compact`，不改终止语义

`context.Compactor.should_compact(rounds, token_used, budget)` 已存在。接线点取两处：
每轮 `observe` 后判定，以及既有 token 预算超限分支（spec 原文「触发上下文压实**或**转人工」）。
触发顺序：压实历史 → `persist` 落 L2 → `memory.compact(session_id)` 提炼摘要。
**压实后仍按既有 `TOKEN_BUDGET_EXCEEDED` 终止** —— 不改成「压实后继续」，否则循环无界，
反倒违背同一 Requirement 的「不无限烧 token」。

`loop/spec.md` 因此**不改**：既有 Scenario 本就要求此举，本变更让实现追上规格。

## 已知缺口（本轮不扩大范围，如实记录）

- **「并发压实一致性」Scenario 无对应实现**：`compact` 现在会写，并发风险上升，但仓库是单线程
  事件循环、无并发压实调用方；加锁属投机性代码（CLAUDE.md §2），故不加。该 Scenario 的实现
  缺口**先于**本变更存在，另行登记。
- **`Compactor.compact` 的启发式关键词匹配**（「结论/决定/待」）未升级为 LLM 判定：其输入是
  自由文本 history，判定质量依赖措辞。本轮只收口**产物形态**（可追溯），判定升级留待 #4。
