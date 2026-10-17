# Design 0252 — 词法检索的 IDF 加权与长度归一

## 决策

### D1 BM25 口径（二值 tf）

```
sim = Σ_{t ∈ query ∩ doc} idf(t) · (k1+1) / (1 + k1 · (1 - b + b · dl/avgdl))  /  Σ_{t ∈ query} idf(t)
idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
```

- `k1 = 1.2`、`b = 0.75`（BM25 常用缺省）。**二值 tf**：索引阶段没有词频统计，且记忆条目
  多为短文本；用 0/1 避免「同词重复堆分」压过覆盖度。
- **按查询 IDF 总和归一** ⇒ 得分仍在 `[0, 1]`（短文档因子可 >1，故 `min(1.0, …)` 收顶），
  与既有 `_W_SIM · sim` 权重量纲一致，乘性因子（新鲜度/复用/重要度）不受影响。
- IDF 恒 `> 0`（`df ≤ N` ⇒ 括号内 ≥ 0.5/(N+0.5) > 0）⇒ 归一化分母不会为零。

### D2 `LexicalStats` 携带候选语料

```python
@dataclass(frozen=True)
class LexicalStats:
    idf: dict[str, float]          # 只含查询词元（内存有界于 query 长度）
    avg_len: float
    doc_tokens: dict[str, frozenset[str]]  # id → 词元集（一次分词，排序复用）
    query_tokens: frozenset[str]
    k1: float = 1.2
    b: float = 0.75
```

- `build_lexical_stats(entries, query)` 对候选集**只分词一次**：之后 `_lexical_sim` 直接取
  `doc_tokens[entry.id]`，不在排序键里重复 `tokens(entry.content)`（原实现每条目一次，
  现为构建一次）。条目不在缓存内（外部直接调 `relevance`）⇒ 现场分词兜底。
- `idf` 只存查询词元：候选语料的其余词元对本次打分无贡献，存全量会让每轮 read 的常驻成本
  随库增长。

### D3 `stats=None` 保持公开 API 原语义

`relevance(entry, query, embedder=None, *, stats=None)` / `rank(...)`：不传 stats ⇒ 原
重叠公式。生产路径（`read`）传 stats；`_score_importance` 的 `rank(e, "")` 不传 ⇒ 逐字不变。
**这是兼容面而非开关**：没有配置项能让生产检索退回旧公式（旧公式保留仅因它是公开函数）。

### D4 启动提示

`entry._build_ui` 在 `runtime.app.llm.embedding_model` 为空时向 stderr 输出一次：

```
未配置 llm.embedding_model：记忆检索使用词法匹配（语义检索未启用，召回质量受限）
```

- 只提示「模式与限制」，不评价用户配置对错；无 `app` / `llm` 的替身 runtime 静默。
- 每次进程启动一次（非每轮检索），与 `rag` 的既有提示节拍一致。

## 反证设计

| 探针 | 摘除 | 预期红测试 |
|---|---|---|
| P1 | `MemoryStore.read` 传入 `stats` | 端到端 IDF 排序用例红 |
| P2 | 打分中的 `idf` 乘子（改恒 1） | 罕见词优先用例红 |
| P3 | 长度归一项（`b=0`） | 短文档优先用例红 |
| P4 | `entry._build_ui` 的提示分支 | entry 提示用例红 |

## 局限

1. **统计是每次 read 现算**：候选集 O(N) 分词 + 文档频率统计；大库下是新增的常驻 CPU 成本
   （原实现排序时已逐条分词一次，本变更把「排序分词」换成「建统计分词 + 查缓存」，量级相近）。
2. **无全局语料统计**：IDF 基于本次候选集（含全库，因 `backend.search` 返回全部并按命中数排序）
   ⇒ 增删条目会让同一查询的分数轻微漂移。
3. **二值 tf 丢失词频信息**：短条目重复关键词不会额外加分（有意，见 D1）。
4. **提示不改变行为**：用户看到提示后是否配置 embedding 模型仍是其选择；词法模式没有关闭开关。
