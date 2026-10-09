# Proposal: 记忆系统质量闭环（memory quality loop）

## Why

记忆系统已具备完整光谱（L0~L4）与压实/固化/遗忘机制，但**质量信号是单向的**：

1. **写入侧无门槛**：`importance` 只在检索/遗忘评分时被**消费**（乘性因子），**写入路径从不生产它**——现有唯一产出点是压实固化（consolidation）对**存量**条目打分写回（`store._score_importance` / `_write_importance`），属**事后修正**而非入库门槛。低价值条目（一次性的原始素材转储）与高价值条目以同等身份进入 L2，垃圾只能等遗忘节拍兜底——这与「无行动不记忆」的精神只对齐了一半：有行动，但结果未必值得沉淀。
2. **遗忘曲线不感知复用**：freshness 衰减只看时间，条目被频繁检索命中（`reuse_count` 增长）并不延缓其衰减——被反复证明有用的记忆与从未被用的记忆按同一条曲线变陈旧，复用信号没有反哺遗忘。
3. **keyfact 上限是死值**：`MAX_KEY_FACTS_PER_COMPACT` 固定常量，短会话浪费名额、长会话截断有效事实，未随会话长度自适应。

## What Changes

合并为**一个 change、分层推进**（共同依赖 `importance` 信号）：

1. **importance 写入侧闭环**：`MemoryStore` 支持注入 importance scorer（契约与 `summarizer`/`embedder`/`key_fact_extractor` 同一依赖方向——memory SHALL NOT import LLM/rag 抽象，遵守 ADR-0045；缺省 UNWIRED）。注入后，写入路径先评分：低于阈值的条目拒绝入库或降层（写入 L4 归档层），且评分写回本身记可撤销效应。**未注入 ⇒ 写入行为与现状逐字一致（零回归）**。
2. **检索命中强化衰减**：遗忘评分中，`reuse_count` > 0 的条目其 freshness 衰减 SHALL 被延缓（复用信号反哺遗忘曲线；具体调制见 design）。缺省即生效（不依赖注入物），但只改**遗忘评分公式**，不改检索排序语义。
3. **keyfact 抽取上限自适应**：`MAX_KEY_FACTS_PER_COMPACT` 从死值改为**随本次压实聚合的 episodic 条目数自适应**（有上下限 `KEY_FACTS_MIN` / `KEY_FACTS_MAX`）。下限取**既有死值**（8）⇒ **任何会话长度下名额都不收紧**，自适应**只放宽**（长会话放宽到上限）。缺省取值覆盖现有死值，行为兼容。

## Impact

- **specs**：`memory/spec.md`——MODIFIED「记忆遗忘」（reuse 延缓衰减）、「结构化实体抽取（关键事实）」（上限自适应）；ADDED「写入侧重要度闸门（importance write gate）」。**「温度分层检索」不改**——衰减调制只作用于**遗忘评分**（`store._decay_score`），检索排序公式（`relevance.rank`）逐字不变（见 design D3）。
- **src**：`src/core/memory/`（store/forget/compact 路径），无跨域 import。
- **风险**：低——三项均有缺省不启用或等值兼容路径，基线测试无回归。
