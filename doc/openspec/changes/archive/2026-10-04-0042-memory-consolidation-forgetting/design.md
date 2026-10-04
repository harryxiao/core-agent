# Design: 记忆固化与遗忘

## 决策 1：固化并入 `compact` 的摘要通道（价值门控），不新增 `consolidate()` 方法

0041 已建「会话分组 → `Summarizer` 提炼 → semantic 条目 + 原条目迁 L4」的通道。固化的增量是
**价值判断**，不是第二条通道：在 `_summarize_sessions` 里，提炼前先打分，`max(scores) < 门限`
的会话整体跳过（不提炼、不归档、原条目保持 episodic L2）。

- 理由：两条近乎同构的链路并存会让「哪个入口负责提炼」失去唯一答案；门控是通道内的一个条件，
  不是通道本身。
- 门控判据 = **会话内本轮取得分值的条目最高分**（`_CONSOLIDATE_THRESHOLD = 0.5`）；本轮一个分值
  都没取得（未注入 scorer / 打分失败 / 超出打分上界）即**不设门槛**——与「没配 judgment 不能
  变成什么都不固化」同一取向，避免决策服务抖动把记忆固化整个停摆。

## 决策 2：`importance` 打分走 judgment `score` 原语；**逐条目一次调用**

`score` 原语的返回形状是**条目集的单一分数**（`answers["score"]["score"]`，
`judgment/models.py` 的类型化答案 + `tests/test_judgment.py::test_score_returns_scores`），
没有 per-item 分数。故：

- `_score_importance(entries)` 对**每条**候选调一次 `Compactor.score(state, [asdict(entry)])`，
  `state` 带 `session_id` / `entry_id` / `reuse_count` / `layer` 作上下文；
- 用 `_MAX_SCORED_PER_COMPACT`（20）设上界，按本地多因子序（`rank` 无 query 的乘性部分）取前 N，
  控制单次压实的 LLM 调用数；
- 结果写回 `entry.importance`，逐条记 `Effect(op="memory.importance", undo=<恢复旧值>)`
  —— 打分是**可变状态写入**，按开发约定 #3 必须可逆，且与压实同 trace（`compaction.<sid>`）。

不采纳「按会话批量打一个分、整组套用」：组内所有条目拿到同一个 importance，会让该维度在检索
排序里退化为常数（等于没打）。也不采纳「扩 score 原语为逐条返回」：那是 judgment 规格/接口的
变更，blast radius 覆盖 JEV prompt、router 解析与既有决策点，收益不抵。

`compact` 里**既有的压实决策打分**（0039/0041，返回 `DecisionResult`）改为失败即降级为
`decision=None`：它是咨询性返回值、无写入副作用，其失败没有理由连带阻断固化与遗忘。摘要器
抛错仍按 0041 契约**向上传播**（`memory` 层不吞、不写半成品），由触发点记 `maintenance_failed`。

## 决策 3：遗忘 = 低分条目 `migrate` 到 L4（不删除），逐条可撤销

新增 `MemoryStore.forget(*, threshold=_FORGET_THRESHOLD) -> list[MemoryId]`：

- 候选 = **L2 且 `kind="episodic"`**（semantic 是提炼产物、L0 是人格、L3 是技能，均不受衰减）；
- 评分 `_decay_score = recency_decay × (1 + log1p(reuse_count)) × (1 + importance)`；
- 动作 `migrate(entry.id, "L2", "L4", trace_id=f"forgetting.{entry.id}")`（`migrate` 已记效应，
  0041 补齐），返回值即撤销句柄列表；
- 迁层而非删除：L4 是归档层，`audit` 可见、低优先级仍可检索，符合「记忆即光谱」。

**偏离 phase-18 原文**：计划写的是 `score = recency × (1 + log reuse) × importance`。直接乘
`importance` 会使**所有未打分条目**（默认 0）评分恒为 0 → 首次遗忘把全库 L2 episodic 归档。改为
`(1 + importance)`——与 `rank` 的乘性项同构，缺省时遗忘只由「陈旧 + 零复用」决定。偏离已记入
ADR-0047。

## 决策 4：触发点并入 loop 既有压实触发（`persist → compact → forget`）

`DefaultLoop` 已有 `_should_compact`（轮数阈值 / token 预算超限）。命中后按序：
`context.Compactor.persist`（历史提炼沉淀）→ `memory.compact`（打分 + 门控 + 会话摘要归档）→
`memory.forget`（衰减归档）。三者共用一次触发，**不新增触发面**，也**不改终止语义**
（压实后仍按既有预算/轮数条件终止）。任一步异常均降级：`ContextError`（无可沉淀）静默跳过，
其余经 tracer 记 `maintenance_failed`（原 `compaction_failed`），本轮继续、原记忆不丢。

## 决策 5：遗忘阈值与「不打分」的边界

- `_FORGET_THRESHOLD = 0.05`：`recency_decay = 1/(1 + age/天)`，即零复用、零重要度的条目需陈旧
  ≈19 天才被归档；`ts<=0`（时间未知）时 `recency_decay` 返回 1.0，不惩罚 → 不会被遗忘。
- **打分失败 ≠ 打 0 分**：`score` 抛错或回退失败时保持 `importance` 原值（不写 0），否则一次
  LLM 抖动会把全库重要性清零、进而让分数骤降导致误遗忘。
- **`_CONSOLIDATE_THRESHOLD = 0.5`**：会话最高分低于此值视为「不值得沉淀」；阈值偏保守
  （宁可少提炼）——提炼本身可逆，但低质 semantic 条目会稀释后续检索。

## 已知缺口（如实记录，不扩大范围）

- **跨会话固化**仍不做（同 0041）：`session_id` 生产侧为空串的问题未修，本次固化仍按会话分组。
- **无并发锁**：`forget` 会写层，与 #3 同样的单线程假设；memory spec「并发压实一致性」Scenario
  的实现缺口先于本变更存在，另行登记。
- **`forget` 无调度**：只在 loop 压实触发时顺带执行；「定时衰减循环」未实现（无调度器依赖，
  属另立变更）。
