# 接口设计：检索增强生成（RAG Interface）

> 模块：`02-modules/rag.md` ｜ 规格：`openspec/specs/rag/spec.md`

---

## 1. VectorStore 接口（存储与索引）

```python
@dataclass
class Chunk:
    chunk_id: str               # 全局唯一块 id（如 "doc_id#3"）
    doc_id: str                 # 来源文档 id
    text: str                   # 分块文本
    embedding: list[float]      # 向量（逐块生成后写入）

@dataclass
class SearchHit:
    chunk: Chunk
    score: float                # 向量相似度得分（供后续裁剪排序）

class VectorStore:
    def put(self, chunk: Chunk) -> None:
        """写入块向量并建索引（默认 SqliteVectorStore 嵌入式落盘，零服务）。"""

    def get(self, chunk_id: str) -> Chunk | None:
        """按块 id 读取；不存在返回 None。"""

    def delete(self, doc_id: str) -> None:
        """删除某文档的全部块与其内容指纹（增量重建前清旧块）。"""

    def search(self, embedding: list[float], *, top_k: int = 5) -> list[SearchHit]:
        """按向量相似度返回 top-k 命中（得分降序）。"""

    def record_document(self, doc_id: str, content_hash: str) -> None:
        """记录文档内容指纹（增量重建的变更判据；落盘实现跨进程可见）。"""

    def document_hash(self, doc_id: str) -> str | None:
        """读取文档内容指纹；未记录返回 None。"""
```

**默认实现 `SqliteVectorStore(path)`**（change 0104）：stdlib `sqlite3` 三张表 —— `chunks`
（块 + 向量 BLOB）、`documents`（文档内容指纹）、`meta`（`dim` 索引向量维度）。嵌入式零服务、
零三方依赖，落盘于 `$CORE_STATE_DIR/rag-index.db` ⇒ **跨进程复用**（一次 ingest 的成果在后续
进程检索中可见）。相似度在进程内暴力余弦计算（规模未到 ANN 门槛）；`sqlite-vec` 等向量扩展可得时
经本抽象替换，调用方零改动。**维度守护**：首个 `put` 定档 `dim`，此后 `put`/`search` 的向量维度
不一致即 `RAGError(INDEX_CORRUPT, …须重建索引)` —— 不静默按短边截断比较（换 embedding 后端后
沿用旧索引正是可达路径）。`InMemoryVectorStore` 保留为无落盘场景（测试 / 单次进程）。

---

## 2. IngestionPipeline 接口（摄取与增量更新）

```python
@dataclass
class Document:
    doc_id: str                 # 知识文档唯一 id
    content: str                # 原始文本
    content_hash: str           # 内容 hash（增量更新失效检测用）

class IngestionPipeline:
    def ingest(self, doc: Document) -> int:
        """导入 / 刷新知识文档：分块 → 逐块 embedding → 写入向量索引。
        返回本次写入块数；内容指纹未变 ⇒ 0（不重建）。"""

    def refresh(self, doc: Document) -> bool:
        """按 content_hash 检测源文档变更并增量重建，返回是否触发重建
        （重建窗口期该文档检索降级旧索引）。"""
```

内容指纹的判定在**存储侧**（`document_hash` / `record_document`）⇒ 跨进程成立（CLI 每次调用
都是新进程）；`refresh(doc)` 等价于 `ingest(doc) > 0`。

---

## 3. Embedder 接口（本地 Embedding）

```python
class Embedder:
    def embed(self, text: str) -> list[float]:
        """默认本地 sentence-transformers + BGE 推理生成向量，不请求外部 API。"""
```

远端模型切换经 llm-provider 归一化 embedding 入口完成，调用方零改动。

---

## 4. Retriever 接口（语义检索）

```python
class Retriever:
    def search(self, query: str, *, top_k: int = 5) -> list[SearchHit]:
        """查询语句 embedding → VectorStore.search，返回 top-k 片段 + 相关度得分。"""
```

---

## 5. RagGenerator 接口（生成融合）

```python
class RagGenerator:
    def generate(self, query: str, hits: list[SearchHit]) -> str:
        """检索片段经 context 装配器按预算裁剪后注入提示词 → llm-provider 生成；
        hits 为空时降级纯 LLM 生成。"""
```

---

## 6. 依赖注入隔离（MAL）

- **VectorStore / Embedder 是三方依赖边界**：底层向量库（默认 stdlib `sqlite3`；`sqlite-vec` 等扩展可经同一抽象替换）与 embedding 后端（默认离线 `HashEmbedder` 降级基线，配 `llm.embedding_model` 则走 `LLMEmbedder` → llm-provider）收敛于单一适配器，异常归一到领域错误码（见 §7），不泄漏底层库异常结构。
- 经依赖注入装配（构造 / registry / 组合根），`Retriever` 与 `RagGenerator` 只依赖抽象接口；替换向量库或 embedding 后端仅改装配点，调用方零改动。
- **主链路门面 `RagService`**（change 0104）：组合根装配 `RagService(embedder, store, chunk_size, generator)` 并挂 `runtime.rag`；CLI（`rag ingest|search|ask`）与宿主只调用门面（`ingest` / `refresh` / `search` / `ask`），不各自拼装 `IngestionPipeline` / `Retriever` / `RagGenerator`（避免装配知识渗进调用方与第二真源）。

---

## 7. 错误码

| 错误码 | 含义 |
|---|---|
| `EMBEDDING_FAILED` | embedding 生成失败（本地推理或远端切换失败） |
| `INDEX_CORRUPT` | 向量索引损坏或**向量维度与当前 embedding 不一致**（提示重建索引） |
| `REBUILD_FAILED` | 增量重建失败（降级旧索引，可重试） |
| `GENERATION_UNAVAILABLE` | 检索增强生成未装配生成器（服务层无 llm-provider 通路）⇒ fail-closed，不返回空答案 |

---

## 8. 关联

- 模块：`02-modules/rag.md`
- 规格：`openspec/specs/rag/spec.md`
