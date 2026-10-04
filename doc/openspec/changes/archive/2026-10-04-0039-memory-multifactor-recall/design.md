# Design: 记忆检索多因子化

## 决策 1：排序公式 —— 加性 `relevance` × 乘性因子（避免双重计数）

Phase 18 §1.3-A2 给出的目标式为 `score = relevance × recency_decay × (1 + log(1+reuse)) ×
importance`。但现网 `relevance` 已把 `freshness`/`reuse`/`layer` **加性**并入
（`relevance.py:56`），直接相乘会与旧项**双重计数**。故本变更把两项职责重新切分：

- `relevance(e, query) = _W_SIM·sim + _W_LAYER·layer_priority`（**语义 + 结构**，加性；
  与查询无关的层先验留在加性侧，避免被 0 相似度乘成 0）
- `_rank(e, query) = relevance · recency_decay(e) · (1 + log1p(reuse_count)) · (1 + importance)`
  （**时间 / 复用 / 重要度**，乘性调制）

`importance ∈ [0,1]` 缺省 0 → 因子 `1.0`，对未打标条目**行为退化**为「relevance × 时间 × 复用」。
`reuse_count` 在 `read` 命中后 `+1`（复用即强化，与旧 `_W_REUSE` 语义一致，只是搬到乘性侧）。

**取舍**：A（保留加性 relevance，另加 importance 列）→ 与目标式不符且仍无法表达「重要度
主导」；**B（本变更：加性语义 × 乘性调制）**→ 对齐 Phase 18 目标式且无双重计数。

## 决策 2：embedder 适配器归属 —— memory 层，不 import rag

`MemoryStore.embedder` 契约是批量可调用；单条可调用（如 rag `Embedder.embed`）与之不匹配。
适配器 `batch_embed(single)` 放在 `memory/embedding.py`，**只接受一个单条可调用**，不 import
rag——保持 L2（memory）不依赖 rag 抽象（依赖方向：由 L5 组合根在装配时传入单条可调用）。

## 决策 3：向量缓存 —— 进程内、按 content hash 失效

`read` 流程：`qvec = embedder([query])[0]`（**一次**）；每个候选 `evec = cache[(e.id,
hash(e.content))]` 命中即复用，miss 才 `embedder([e.content])[0]` 并写缓存。复杂度由
**N+1 次/read** 降为 **1 + 增量 miss**。缓存键含 `content` 哈希 → 条目内容变更自然失效。
缓存**易失**（进程内 dict，不落盘、不改后端 schema）——代价是重启后首次 `read` 有冷
miss；收益是零 schema/迁移成本。详见 ADR-0045。

## 决策 4：embedder 来源 —— DI 参数，配置留 0040（架构边界）

`build_runtime` 增 `embedder: Callable[[list[str]], list[list[float]]] | None = None` **DI
参数**，与既有 `assembler / tracer / memory_backend / approver` 同模式。本变更**不新增配置
项**：内存能力的正确姿态是「说抽象、不说具体」——它只要求「可注入 embedder」，至于 embedder
从哪来是**组合根**的事。生产来源（`llm.embedding_model` 配置旋钮 + 以该 model 构造
`LLMEmbedder` 注入）属 `0040-memory-embedding-config`。

**取舍**：A（本变更同时改 configuration spec + 装配）→ 单 change 跨两个能力（L2 memory 与
横切 configuration），验证面引入远端可达性，可归因性下降；**B（本变更仅备 seam）**→ memory
能力变化自洽、完全离线可验，配置与外部不确定性隔离到 0040 薄变更。默认 `embedder=None` →
词法路径**逐字不变**。

## 风险与缓解

- **排序变化**：`relevance` 收敛改变既有排序 → 依赖旧公式的 `tests/test_memory.py` 断言同步；
  默认 `importance=0`、词法路径行为等价，回归面可控。
- **成本**：缓存把 embedding 调用压到常量级；远端不可达时降级不阻断主流程（0040 起）。
- **兼容**：`MemoryEntry` 新字段有默认值，旧 JSONL 记录（缺字段）经 `MemoryEntry(**record)`
  取默认，无需迁移。
