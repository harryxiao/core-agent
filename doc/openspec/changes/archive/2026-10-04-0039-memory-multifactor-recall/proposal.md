# Change: 记忆检索多因子化（importance/kind + 语义相似 + 向量缓存）

## Why

Phase 18 交付物 #1/#2 与遗留项 C7（Phase 17.5 §3.1 走查）的**确定性、离线**部分。当前记忆
检索有两处与「记忆即光谱 / 长期记忆固化」目标不符（实证）：

- **排序单因子**：`MemoryStore.read` 仅按加性 `relevance`
  （`0.5·sim + 0.1·fresh + 0.2·reuse + 0.2·layer`，`relevance.py:46-56`）排序，条目**无
  `importance` / `kind`**（`protocol.py:20-32`）——无法表达「主观重要度」，也无法区分
  episodic（事件）/ semantic（提炼事实），下游固化（consolidation）无法据以聚合。
- **语义检索无 seam**：`build_runtime` 构造 `MemoryStore` **从不传 embedder**
  （`runtime.py:167-171`）→ 恒走词法 `_lexical_sim`；且即便传入，`relevance._similarity` 也对
  **每个候选**调用 `embedder([content, query])`（`relevance.py:66`）→ 每次 `read`
  **N+1 次 embedding** 且 query 被重复向量化（成本不可接受，见 ADR-0045）。

本变更**只做 memory 能力内部**：字段 + 多因子重排 + 适配器 + 向量缓存 + 一个 DI seam。
生产 embedding **来源**（配置旋钮与装配）不在本变更，见 `0040-memory-embedding-config`。

## What Changes

- **条目字段扩展**（memory，细化 `CORE-MEM-R2`）：`MemoryEntry` 增 `importance: float = 0.0`
  与 `kind: Literal["episodic", "semantic"] = "episodic"`（默认值向后兼容；JSONL 旧记录缺
  字段走 dataclass 默认值，`backend.py:77`）。
- **检索多因子重排**（memory，MODIFIED「温度分层检索」）：排序 key 由单 `relevance` 改为
  `relevance × recency_decay × (1 + log1p(reuse_count)) × (1 + importance)`；`relevance`
  收敛为「语义相似 + 层结构权重」加性项，时间/复用/重要度改由**乘性因子**承担（避免与旧
  加性项双重计数）；`read` 命中即 `reuse_count += 1`（复用即强化）。
- **语义相似适配器 + 向量缓存**（memory）：新增 `memory/embedding.py::batch_embed` 把**单条**
  可调用适配为 `MemoryStore` 的**批量**契约（memory 不 import rag）；`read` 对 query **只
  向量化一次**、候选条目按 `(id, hash(content))` **缓存向量**；embedder 缺省 `None` → 词法
  降级（含异常降级，`relevance.py:64-70` 语义保留）。
- **组合根 DI seam**（memory 消费侧）：`build_runtime` 增 `embedder=None` **DI 参数**（对齐
  既有 `assembler / tracer / memory_backend / approver` 模式），透传给 `MemoryStore`。

## Non-goals

- 不改 `write` 的「无行动不记忆」门（`store.py:71-72`）。
- 不实现摘要式压缩 / consolidation / forgetting（Phase 18 #3/#4/#5，另开 change）。
- 不改 `relevance` 的层优先级取值（`L0 1.0 > L3 0.8 > L2 0.6 > L1 0.4 > L4 0.2`）。
- **不新增任何配置项、不接生产 embedding 来源**——`llm.embedding_model` 旋钮与
  `LLMEmbedder` 装配属 `0040-memory-embedding-config`（本变更只把 seam 备好，默认词法）。
- **不实现 `importance` 自动打分**（接 judgment `score` 原语）——留至 Phase 18 #4/#5，
  那里才有消费者；本变更仅加字段并使其参与排序。
- **不引入本地语义模型**（sentence-transformers/BGE，与零三方依赖红线 ADR-0044 冲突）。

## Impact

- **Affected specs**：`memory/spec.md`（1 MODIFIED：「温度分层检索」——多因子重排 + 语义
  相似经 embedder + 条目 kind/importance）。**不触 configuration。**
- **Affected docs**：`03-interfaces/memory-interface.md`（`MemoryEntry` 字段清单 + 相关性
  打分公式 + embedder 批量契约/缓存语义）、`01-architecture/adr.md`（ADR-0045）。
- **Affected code**：`src/core/memory/protocol.py`（字段）、`src/core/memory/relevance.py`
  （`relevance` 收敛 + `recency_decay`）、`src/core/memory/store.py`（`_rank` + 向量缓存 +
  `reuse_count` 强化）、`src/core/memory/embedding.py`（新，适配器）、
  `src/core/runtime.py`（`embedder` DI 参数透传）。
- **Dependencies**：无新三方依赖；`0040` 依赖本变更（需先有 seam）。
- **风险**：低。`relevance` 语义收敛会改变既有排序（依赖旧公式断言的测试需同步）；默认
  路径（`embedder=None`）行为与词法现状等价、离线可测。
