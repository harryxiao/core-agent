# Design 0276 — 记忆检索延迟修复（1 万条 <100ms）

## D1 `estimate_tokens`：口径不变，计数换成 C 层正则

- 现状：`cjk = sum(1 for char in text if _is_cjk(char))`，`_is_cjk` 对每个字符 `any()` 遍历
  7 个区间 ⇒ 纯 Python 每字符多次调用，1 万条 × 每条 ~50 字 ≈ 50 万字符，是首热点。
- 改法：把 `_CJK_RANGES` **同源**编译为一个正则字符类
  `[　-〿぀-ヿ…]`，`cjk = len(text) - len(_CJK_PATTERN.sub("", text))`。
  `sub` 由 C 引擎执行，计数语义与逐字符判定**逐位一致**（同一组闭区间）。
- 删除 `_is_cjk`（本 change 使其无消费者；`notes/backend.py` 有同名私有函数，互不相干）。
- 影响面：`core.tokens.estimate_tokens` 的**所有**调用方（memory 读预算、context 预算、
  orchestration handoff）只获得速度，不获得语义变化。
- **反证方式**：无法用挂钟在单测里稳定反证；用**区间边界等价测试**钉住口径（每个区间的
  下界/上界/界外字符 + ASCII/空串/混合），并用基准报告值见证提速。

## D2 词元缓存：按内容校验、有界 FIFO

- 现状：每次 `read` 的 `build_lexical_stats` 对**全部候选**重新 `tokens(content)`；
  同一条目在一轮会话中会被反复检索，重复分词纯属浪费。
- 改法：
  - `MemoryStore.__init__`：`self._token_cache: dict[str, tuple[str, frozenset[str]]] = {}`。
  - `build_lexical_stats(entries, query, *, token_cache=None)`：逐条先查
    `token_cache[id] == (content, tokens)`；命中则复用，未命中则计算并写回。
  - `read` 传入 `self._token_cache`；末尾 `_trim_token_cache()`：`len > _TOKEN_CACHE_MAX`
    时按插入序 FIFO 淘汰（与 `_trim_vectors` 同风格）。
- **正确性边界**：缓存键含**内容原文**，同 id 覆写不同内容 ⇒ 校验失败 ⇒ 重新分词；
  只读 `content`，不缓存任何随时间变化的字段（`reuse_count` 等），故 `_reinforce`
  不影响缓存有效性。
- **结果不变**：命中与未命中的 `doc_tokens` 是同一 `frozenset`，`idf`/`avg_len`/`rank`
  输入逐项一致 ⇒ 排序与预算裁剪逐条不变（由既有 3022 测试 + 基准 recall/MRR 1.000 守护）。
- **有界**：`_TOKEN_CACHE_MAX = 20_000`（1 万条目标的 2×）。参考量级：每条 ~20–30 个词元，
  1 万条缓存约十几 MB；上界保证不随历史条目无限增长。溢出时截断而非全清，贴合顺序重读。
- **缺省即关闭**：`token_cache=None` 时 `build_lexical_stats` 行为与 `0252` 逐字一致；
  只有 `MemoryStore.read` 路径启用。

## D3 实测（参考机，同一 10k 语料 / 20 查询）

| 版本 | 中位 | p95 | recall@5 |
|---|---|---|---|
| `0275` 基线 | 586.6ms | 695.9ms | 1.000 |
| + 快速 `estimate_tokens` | 221.9ms | 289.4ms | 1.000 |
| + 词元缓存（第二次起） | **83.3ms** | **109.3ms** | 1.000 |

- 微基准：`estimate_tokens` 10k 条 546ms → 39ms；`tokens` 10k 条 89ms → 缓存后 ≈2ms；
  `build_lexical_stats` 104ms → ≈15ms；排序 21ms 不变。
- **产品目标 <100ms 在参考机中位达标**；p95 ≈109ms 略高于目标（首批查询/系统噪声），
  故仍**不作跨机硬门禁**，回归上限收紧到 `p95 < 1000ms`（≈9× 余量）。
- 首次检索（缓存冷）仍约 220ms：缓存收益从第二次检索起；这是本设计的已知边界。

## D4 回归护栏

1. `tests/test_token_estimate.py`：补区间边界等价（每区间上下界、界外 ±1、空串/混合），
   与既有「CJK=1/字、ASCII=1/4、至少 1」断言并存。
2. `tests/test_memory_token_cache.py`（新）：
   - **复用**：monkeypatch `relevance.tokens` 计数；同一 store 两次 `read` ⇒ 第二次仅对
     **查询**分词一次（未变条目零调用），结果与首次逐条相同。
   - **失效**：同 id 覆写不同内容 ⇒ 第三次 `read` 对新内容分词，命中新内容（旧词元不残留）。
   - **有界**：monkeypatch `store._TOKEN_CACHE_MAX` 为小值 ⇒ 多次读后缓存长度 ≤ 上界。
3. `tests/test_memory_scale_benchmark.py`：`_LATENCY_P95_CEILING_MS` 5000 → 1000；
   recall/MRR 阈值不变。

## 反证

1. `read` 不传 `token_cache`（等价于摘缓存）⇒ 复用用例的「第二次零条目分词」断言红。
2. 去掉内容校验（只按 id 命中）⇒ 内容变更失效用例红（旧词元继续参与打分）。
3. `estimate_tokens` 的速度不进单测反证（挂钟不稳定），由基准报告值见证；口径由边界等价钉住。

复原后 `md5sum` 一致。

## 已知局限

- 缓存收益依赖**重复检索**；冷启动首次读仍是 ~220ms（已去掉首热点，但分词一次不可避免）。
- 缓存在**进程内存**、按 store 实例归属：跨进程/重启不共享，多实例各自一份。
- 排序阶段仍需对所有候选 `rank`（≈21ms）与 BM25 idf 统计（≈15ms）；未做候选预裁剪，
  以免改变召回面。
- 20k 上界对 1 万条目标足够；若语料远超 2× 上界，FIFO 会抖动（重读即重新分词），
  届时应以候选预裁剪或持久化索引另案处理。
- 挂钟数字受机器负载影响；ADR 记录参考机数值与相对提速，不作跨机绝对值承诺。
