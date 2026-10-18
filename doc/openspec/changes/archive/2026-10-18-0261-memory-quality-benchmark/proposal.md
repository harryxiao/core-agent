# Proposal 0261 — 记忆检索质量离线基准

## Why

对比审查（2026-10-18）确认记忆机制缺少**检索质量回归门**：BM25 词法排序（change 0252）此前
只有零散「相关性顺序」单元测试，没有覆盖「当前事实 vs 陈旧事实」「跨会话」「L2/L3/L4 混合」的
固定基准。排序公式或分词口径的任何改动都可能悄悄降低召回、让陈旧事实压过当前事实，而现有测试
不会红。同时，真实 LLM/embedder 依赖会引入不确定性与成本，不能作为常规门禁。

## What Changes

- 新增 `tests/test_memory_quality.py`：固定合成语料（26 条，覆盖 L2 / L3 / L4、跨会话、
  `bench.stale` 陈旧冲突）＋ 12 条带标注 gold 的查询。
- 指标：**recall@5**（gold 命中比例）、**MRR@5**（首个 gold 的倒数排名）、**stale_hits**
  （陈旧条目排名高于对应当前事实的查询数）。阈值：recall ≥ 0.9、MRR ≥ 0.7、stale_hits = 0。
- 纯离线：`MemoryStore()`（内存 FileBackend，无落盘）、无 embedder、无真实 LLM、无网络。
- **每条查询新建 store 重放固定语料**，规避 `read()` 的 `_reinforce` 改写 `reuse_count`
  造成先后顺序耦合；另加重放确定性用例。
- 另加 `exclude_source_prefixes=("bench.stale",)` 用例，验证真实排除机制（而非只靠词法排序）。

## Impact

- `tests/test_memory_quality.py`（新）。
- 规格：`memory` **ADDED** 1 req（检索质量离线基准 + 3 scenarios）。
- 文档：`doc/02-modules/memory.md`、`doc/04-testing/test-cases.md` §173、ADR-0251 / 台账 E196+1。

## 不做（明确边界）

- 不引入 embedder / 真实 LLM / 网络依赖；不做语义向量质量评测。
- 不做长任务端到端成功率评测（需真实模型与预算，另立评测批次）。
- 不新增生产代码路径、不改排序公式或阈值；本 change 只建立回归门。
