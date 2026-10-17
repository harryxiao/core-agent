# Change 0252 — 词法检索的 IDF 加权与长度归一

## 为什么

记忆框架对比审查（P1）指出：缺省（未配置 `llm.embedding_model`）检索的**词法相似度**是
`|query_tokens ∩ content_tokens| / |query_tokens|`（`relevance.py:_lexical_sim`）——
每个查询词元等权、文档长度不惩罚。后果：

1. **常见词与罕见词同权**：查询里的「的 / 报告 / 流程」与「量子」对打分贡献相同，常见词
   把真正有区分度的罕见词稀释掉，召回排序近似「随机命中一个词就等价」。
2. **长文档占优**：长内容天然覆盖更多查询词元，短而精确的条目被长而泛的条目压过。
3. **用户不知道自己在用降级模式**：未配置 embedding 模型时检索静默走词法，而 `rag` 子命令
   已有同类提示（`entry._rag`），记忆面没有 —— 召回质量受限不可见。

## 改什么

- **`core.memory.relevance`**：
  - 新增 `LexicalStats`（文档频率 → IDF、平均文档长度、每条目词元缓存、查询词元）。
  - 新增 `build_lexical_stats(entries, query) -> LexicalStats | None`（对候选集只分词一次）。
  - `_lexical_sim` 增加 BM25 口径（`k1=1.2`、`b=0.75`、二值 tf）：按 `idf ×
    (k1+1)/(1+k1·(1-b+b·dl/avgdl))` 逐词元求和，再按查询 IDF 总和归一（上界 1）。
  - `relevance` / `rank` 增**仅关键字** `stats=`；`stats=None` 时走原重叠公式（公开 API
    逐字兼容）。
- **`MemoryStore.read`**：在来源/会话过滤后、排序前对候选集构建一次 `LexicalStats` 并传入
  `rank` ⇒ 生产检索走 IDF + 长度归一；embedder 失败降级时同样带 stats。
- **CLI 提示**：`entry._build_ui` 在 `llm.embedding_model` 为空时向 stderr 打印一次
  「记忆检索使用词法匹配（语义检索未启用，召回质量受限）」，与 `rag` 的既有提示同口径。

## 影响面

- 规格：`memory` MODIFIED「温度分层检索」（词法口径 + 提示 + 2 Scenario）。
- 代码：`src/core/memory/relevance.py`、`src/core/memory/store.py`、`src/core/entry.py`。
- 测试：新增 `tests/test_memory_lexical_scoring.py`；`tests/test_entry.py` 增提示两例。
- 行为变化：**排序结果会变**（这正是目的）；打分上界与乘性因子不变，预算裁剪语义不变。
  `stats=None` 的调用方（`_score_importance` 的 `rank(e, "")`）逐字不变。

## 不做

- 不引入第三方检索库 / 本地语义模型（承 `rag` 的离线基线裁决：语义走 LLMEmbedder）。
- 不做倒排索引 / 增量语料统计（每次 read 对候选集建一次统计，登记为后续性能课题）。
- 不改 `backend.search` 的候选粗排（仍按词元命中数排序，最终排序由 `rank` 决定）。
- 不给词法模式加「关闭开关」：它是 embedder 缺失时的唯一可用路径，关掉等于检索失效。
