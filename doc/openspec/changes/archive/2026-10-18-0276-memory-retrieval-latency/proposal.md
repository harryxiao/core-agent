# Proposal 0276 — 记忆检索延迟修复（1 万条 <100ms）

## Why

`0275` 首次在 1 万条规模上度量检索延迟：本机中位 **≈657ms**，对照 CORE-NFR-PERF2
（`<100ms` / 1 万条事实规模）**未达标**。实测分解（10k 条、单次 `read`）：

| 环节 | 耗时 | 说明 |
|---|---|---|
| `_truncate` → `estimate_tokens` | **≈323ms** | 对全部候选逐条、逐字符 Python 判定 CJK 区间 |
| `build_lexical_stats` → `tokens` | ≈89ms | 每次检索对全部候选重新分词（正则 + 中文二元组） |
| BM25 统计（idf/avg_len） | ≈15ms | |
| `sorted(rank)` | ≈21ms | |

`0275` 按选项 B 只记录、不修；本 change 修这两处**不改变任何检索语义**的开销。

## What Changes

- `src/core/tokens.py`：`estimate_tokens` 的 CJK 计数由**逐字符 `any(range)`** 改为**单次
  预编译正则 `sub` 计数**（区间由 `_CJK_RANGES` 同源生成）。**输出逐位不变**，参考机
  10k 条估算 ≈320–550ms → ≈39–45ms（同进程微基准 ≈14×；读路径整体 ≈586→222ms）。
- `src/core/memory/relevance.py`：`build_lexical_stats` 增加可选 `token_cache`
  （`id → (content, frozenset[token])`）——内容未变则复用词元集，内容变更自动失效。
  缺省 `None` ⇒ 行为与既有逐字一致（外部调用方零改动）。
- `src/core/memory/store.py`：`MemoryStore` 持有**有界**（FIFO，`_TOKEN_CACHE_MAX = 20_000`）
  词元缓存并传入 `build_lexical_stats`；排序、打分、预算裁剪与结果逐条不变。
- `tests/test_memory_scale_benchmark.py`：回归上限由 `p95 < 5000ms` 收紧为 `p95 < 1000ms`
  （参考机修后实测 ≈83ms 中位 / ≈109ms p95，留约 9× 余量）；产品目标仍只报告、不作跨机硬门禁。
- 新增确定性测试：`estimate_tokens` 区间边界等价；词元缓存复用 / 内容变更失效 / 有界淘汰。

## Impact

- `src/core/tokens.py`、`src/core/memory/relevance.py`、`src/core/memory/store.py`。
- `tests/test_token_estimate.py`（补边界等价）、`tests/test_memory_token_cache.py`（新）、
  `tests/test_memory_scale_benchmark.py`（收紧上限）。
- 规格：`memory` **MODIFIED**「检索规模离线基准（1 万条）」+ **ADDED**「检索词元缓存」。
- 文档：ADR-0266 / 台账 E212 / `doc/04-testing/test-cases.md` §188 / `doc/02-modules/memory.md` /
  `doc/00-product/requirements.md`（CORE-NFR-PERF2 标注改为已达标）。

## 不做（明确边界）

- 不改 BM25 公式、分词规则、层权重、排序与预算语义；不改 `estimate_tokens` 的估计口径。
- 不做分区加权（PA-09 C）、图（D）、真语义（E）；不改 `_truncate` 的「跳过放不下者」语义。
- 不引入三方依赖；不做跨进程/持久化缓存（进程内存、随实例回收）。
