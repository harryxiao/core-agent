# Design: 记忆系统质量闭环

## Context

既有机制盘点（避免与 0153/0173 冲突）：

- 0153（semi-auto-promotion）：摘要越界 → 提升为 canonical 长期记忆。**不在本 change 范围**，两者共用「注入钩子 + 缺省 UNWIRED」模式但互不依赖。
- 0173（memory-material-and-ref）：keyfact 密钥脱敏与 `coeffect:<名称>` 引用判据。本 change 只改**条数上界**，不动脱敏与引用语义。
- 固化（consolidation）Requirement 已有「把分值写回条目 importance」的 L5 侧行为（低置信回退），本 change 的**写入侧闸门**与其正交：固化写回是存量修正，本闸门是**增量入库门槛**。两者写 `importance` 的可撤销口径保持一致。

## Goals / Non-Goals

**Goals**：写入门槛可注入、复用反哺遗忘、keyfact 上限自适应；三项全部缺省行为不变或等值兼容。

**Non-Goals**：不改检索排序公式、不改会话隔离、不动摘要滚动合并与提升钩子、不引入任何 LLM import、不做存量记忆的重打分迁移。

## Decisions

### D1. 为何合并为一个 change

三项看似独立，实则共同依赖**同一信号：`importance` / 复用价值**——

- 写入闸门生产 `importance`（拒低分、留高分）；
- 检索命中强化衰减消费 `reuse_count`（同一「价值信号反哺」谱系的另一半）；
- keyfact 自适应上限决定**多少价值进入长期层**。

三者构成一个完整闭环（生产 → 反哺 → 配额），拆开会导致中间态出现「有闸门但遗忘曲线仍不感知复用」这类半开环；且全部落在 `src/core/memory/`，评审面一致。风险隔离靠**分层推进**（见 D4）而非拆 change。

### D2. importance scorer 依赖注入（ADR-0045 对齐）

- 契约：`ImportanceScorer = Callable[[MemoryEntry], float]`，返回 [0,1]。
- 注入点：`MemoryStore` 构造形参 `importance_scorer`，缺省 UNWIRED。
- **UNWIRED ⇒ 行为逐字不变**：不评分、不拒收、不降层——与 `summarizer` / `key_fact_extractor` / `summary_promoter` 同一「缺省不启用」纪律。
- scorer 抛错 ⇒ 降级放行（不拒收），`warnings.warn` 留痕，不牵连写入主流程。
- 拒收 vs 降层：分数低于 `IMPORTANCE_FLOOR`（常量，如 0.2）⇒ 拒绝入库（不写、返回 `None`，无效应记录——没有写入就没有可撤销效应）；分数在 `[FLOOR, AMBIT)`（如 0.2~0.4）⇒ 降层写入 L4。阈值为常量、不引入 LLM 二次判断。
- **降层写法的可撤销语义**：为满足「回滚即按**原意向层**恢复」，降层 SHALL 实现为**两步、双 trace**——先按面向的**意向层** `write(intent_layer, entry)`（记在条目自身 trace），再 `migrate(id, intent_layer, "L4", trace_id=f"gate.{id}")`（降层另记专 trace）；回滚 `gate.<id>` 时 `_undo_migrate` 把条目从 L4 **迁回意向层**。**不得同 trace 两步**：`EffectTracker.rollback` 按**逆序**撤销，同 trace 会先 `_undo_migrate`（迁回意向层）再 `_undo_write`（**删除**条目）⇒ 条目消失、与「按原意向层恢复」不符。（若直接 `write("L4", entry)`，回滚走 `_undo_write` 只会**删除**条目、不复原层，同样不符。）
- **评分写回**：通过闸门的条目，其 `importance` SHALL 写为分值，复用既有 `_write_importance`（`Effect(op="memory.importance")`、undo 恢复旧值——与固化写回**完全同口径**）。写回效应的 `trace_id` SHALL 取**该条目自身的 `trace_id`**（与 `write()` 记效应口径一致），使闸门写回随该条目的写入 trace 一并回滚。
- **两个 `importance` 生产者的先后**：闸门（写入路径，对新/覆盖条目设初值）与固化写回（压实路径，对存量条目修正）**序贯、不冲突**——二者都写 `memory.importance`、都可逆、各随其 trace 回滚；缺省均为 UNWIRED ⇒ 无写回。同一轮内若同时作用于同一条目，以**后写者**（固化）为当前值。

### D3. 检索命中强化衰减

遗忘评分公式从「新鲜度 × 复用 × 重要度」中的**纯时间新鲜度**改为：

```
freshness' = freshness ** (1 / (1 + log1p(reuse_count)))
```

- **调制落点：`store._decay_score`，不落 `relevance.recency_decay`。** `recency_decay()` 被检索排序 `rank()` 共用（`relevance.py:77`）——若把调制写进 `recency_decay` 会**一并改掉检索排序**，直接违背本 change 的 Non-Goal。故调制 SHALL 只写在 `_decay_score(entry)` 内（对 `recency_decay(entry)` 的返回值做幂变换），`rank()` 与 `recency_decay()` 逐字不动，规格亦不 MODIFY「温度分层检索」。
- `reuse_count = 0` ⇒ 指数为 1，公式退化为现状（**零回归锚点**）。
- 复用越多 ⇒ 指数越小 ⇒ freshness 被抬高（衰减被延缓），单调且与既有 `1 + log1p(reuse_count)` 乘性因子同底数、不冲突（一个是排序乘子，一个是衰减调制）。
- `ts<=0` 不被惩罚的既有豁免不变（`recency_decay` 返回 `1.0`，`1.0 ** x == 1.0`）；只作用于 L2 episodic 遗忘评分，不改检索排序。

### D4. 分层实施顺序（tasks 分组）

1. **Layer A**：keyfact 上限自适应（纯常量逻辑，零依赖，先落地）。
2. **Layer B**：reuse 强化衰减（纯公式改动 + 单测锚点 `reuse=0 ⇒ 现状`）。
3. **Layer C**：importance 写入闸门（注入面最广、涉及 EffectTracker，最后落地，依赖 A/B 建立的质量信号语义）。

每层独立可交付、独立可回滚；层间无代码依赖（C 不调 A/B 的实现）。

### D5. keyfact 上限自适应

- `MAX_KEY_FACTS_PER_COMPACT` 改为函数：`cap(n_episodic) = clamp(ceil(n_episodic * KEY_FACTS_RATIO), KEY_FACTS_MIN, KEY_FACTS_MAX)`。
- 常量取值：`RATIO = 0.25`，`MIN = 8`（等于现有死值——**任何会话长度下 cap ≥ 现状**，宽松化而非收紧，零收紧回归）、`MAX = 16`。
- 归并、脱敏、幂等覆盖等既有语义逐字不变，只放宽名额。
- **实现面（`cap(n)` 要穿过的点）**：`store._plan_key_facts` 现**硬读** `MAX_KEY_FACTS_PER_COMPACT`（`store.py:128`）且无 cap 形参 ⇒ 增 `cap` 形参，调用点 `_extract_key_facts` 以 `cap(len(entries))` 传入；`extract.py` 的 `build_extract_prompt` / `extract_via_llm` 两处 `max_facts: int = MAX_KEY_FACTS_PER_COMPACT` 默认值须与 `KEY_FACTS_MIN` 口径对齐；`core/memory/__init__.py` 公开导出同步；`tests/test_memory_key_facts.py` **5 处断言**（`:260/:266/:357/:366/:367`）以该常量为期望值，须按 `cap(n)` 复核。
- **规格一致性**：delta 内两条既有 Scenario（「条数与长度有界」「同批同 slug 归并」）原以固定常量 `MAX_KEY_FACTS_PER_COMPACT` 为界，SHALL 改引 `cap(n)` —— 否则合并后 canonical 出现「正文 `cap(n)` ≤16 条 / Scenario ≤8 条」的自相矛盾（恰在长会话 n≥36 时爆发，正是本 change 的目标场景）。

## Risks / Trade-offs

- **拒收丢数据**：FLOOR 以下整条丢弃不可恢复——但闸门默认 UNWIRED，仅 L5 显式注入后生效；拒收决策留痕（`warnings.warn`，含条目摘要不含正文密钥风险面）。
- **衰减调制改变既有遗忘测试基线**：以 `reuse_count=0` 场景为锚点逐字保持；`reuse>0` 场景为新增测试而非改写既有断言。

## Migration Plan

无需迁移：三项均缺省兼容，注入物由 L5 组合根按 profile 显式接线。

## Open Questions

- `IMPORTANCE_FLOOR` / `AMBIT` 阈值常量的最终取值（暂定 0.2 / 0.4，实现期可按评测调）。
