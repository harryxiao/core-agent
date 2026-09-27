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
        """写入块向量并建索引（默认 sqlite-vec 嵌入式落盘，零服务）。"""

    def get(self, chunk_id: str) -> Chunk | None:
        """按块 id 读取；不存在返回 None。"""

    def delete(self, doc_id: str) -> None:
        """删除某文档的全部块（增量重建前清旧块）。"""

    def search(self, embedding: list[float], *, top_k: int = 5) -> list[SearchHit]:
        """按向量相似度返回 top-k 命中（得分降序）。"""
```

---

## 2. IngestionPipeline 接口（摄取与增量更新）

```python
@dataclass
class Document:
    doc_id: str                 # 知识文档唯一 id
    content: str                # 原始文本
    content_hash: str           # 内容 hash（增量更新失效检测用）

class IngestionPipeline:
    def ingest(self, doc: Document) -> None:
        """导入知识文档：分块 → 逐块 embedding → 写入向量索引。"""

    def refresh(self, doc: Document) -> bool:
        """按 content_hash 检测源文档变更；不一致则增量重建受影响块，
        返回是否触发重建（重建窗口期该文档检索降级旧索引）。"""
```

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

- **VectorStore / Embedder 是三方依赖边界**：底层向量库（默认 sqlite-vec）与本地 embedding 模型（默认 sentence-transformers + BGE）收敛于单一适配器，懒 import，异常归一到领域错误码（见 §7），不泄漏底层库异常结构。
- 经依赖注入装配（构造 / registry），`Retriever` 与 `RagGenerator` 只依赖抽象接口；替换向量库或 embedding 后端仅改装配点，调用方零改动。

---

## 7. 错误码

| 错误码 | 含义 |
|---|---|
| `EMBEDDING_FAILED` | embedding 生成失败（本地推理或远端切换失败） |
| `INDEX_CORRUPT` | 向量索引损坏（降级重建或旧索引） |
| `REBUILD_FAILED` | 增量重建失败（降级旧索引，可重试） |

---

## 8. 关联

- 模块：`02-modules/rag.md`
- 规格：`openspec/specs/rag/spec.md`
