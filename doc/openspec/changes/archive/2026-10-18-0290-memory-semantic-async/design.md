# 设计 — 0290 异步安全 embedding 桥 ＋ 批量相似

## D1. 同步薄壳：循环安全的桥接

**现状**（`src/core/llm_provider/provider.py`）：

```python
def completion(self, request): return asyncio.run(self.acompletion(request))
def embedding(self, texts): return asyncio.run(self.aembedding(texts))
```

`asyncio.run` 在已有运行循环内抛 `RuntimeError`；且 `self.acompletion(request)` 先建协程
再调用，失败时留下 “never awaited” 协程（正是冒烟里的告警）。

**改法**：

```python
def _run_sync(factory: Callable[[], Coroutine[Any, Any, _T]]) -> _T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(factory())).result()
```

- **协程工厂**：循环判断在构造协程之前；桥接失败不会产生孤儿协程。
- **无循环路径逐字不变**（`asyncio.run(factory())` 与旧实现语义相同）。
- **一次性线程而非进程级单 worker**：worker 内若再调同步薄壳，进程级单 worker 会
  自己等自己而死锁；一次性线程每次独立。
- **不 import `core.runtime._run_coro`**：架构门禁禁止 `llm_provider` 依赖 `runtime`
  （`tests/test_architecture.py:561-602`）；留一个本地私有助手，避免反转层依赖。
- `stream` 仍是缓冲式（`_collect_stream`），桥接不会让它变增量；文档写明。

**被拒**：把同步薄壳改成“检测到循环就抛清晰错误”。原因：`MemoryStore.read` 是既有
同步契约，调用方无法感知/改造事件循环；抛错只会把静默降级换成显式中断，没有解决
语义检索不可用。

## D2. `LLMEmbedder.embed_many`：真批量

```python
def embed_many(self, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        embeddings = self._provider.embedding(texts)
    except LLMError as exc:
        raise RAGError(RAGErrorCode.EMBEDDING_FAILED, ...) from exc
    return [e.vector for e in embeddings]
```

- 必须走**同步** `provider.embedding`：`tests/test_phase13.py` 的假 provider 只覆写
  同步入口；走 `aembedding` 会绕过它。
- 不加到 `Embedder` ABC：`HashEmbedder` 与其它实现不需要批量；ABC 变更会强制所有
  实现跟进，属不必要的契约扩散。
- `batch_embed` 保留：它服务“只提供单文本 callable”的注入场景（兼容面与既有测试）。

## D3. `batch_similarities`：整次检索一个尺度

**签名**：

```python
_SIM_BATCH_SIZE = 64
batch_similarities(entries, query, embedder, *, batch_size=64) -> dict[str, float] | None
```

**语义**：

1. **空候选集 ⇒ `{}` 且不调用 embedder**。空读若触网失败，会置粘性 `_embed_failed`，
   把空读变成全进程降级 —— 这是必须堵住的最小事故面。
2. `texts = [query, *(e.content)]`，按 `batch_size` 切块；query 恒在第一块 ⇒ 每次检索
   至多嵌入一次。
3. 每块校验 `len(vectors) == len(chunk)`；首块的 query 向量是后续所有块的比较基准，
   并校验每个内容向量维度一致（`_cosine` 用 `zip(strict=False)`，维度不符会**静默截断**）。
4. 余弦算完即丢弃，不累计向量（10k 候选不驻留 10k 向量）。
5. **任一异常 / 数量不符 / 维度不符 ⇒ `None`**：`read` 对全部候选走 BM25。绝不返回
   部分映射 —— 否则同一排序里前几条用余弦、后几条用词法，尺度不可比。
6. 用 `self._memo_embedder()`（文本级缓存 + 粘性失败语义），不绕过缓存。

**`read` 接线**：候选先 `list(...)` 物化一次；`sim_map` 传给 `rank(..., sim=...)`，
`rank`/`relevance` 的 `sim` 用 `is None` 判断（`0.0` 与负余弦合法）。
`build_lexical_stats` 保持无条件执行（预热 token 缓存，并服务降级路径）。

## D4. 收益与局限（如实登记）

- 调用数从 O(N) 降为 O(N/64)：10k 候选约 **157 次**调用，但仍为**顺序**调用，
  每次在事件循环上阻塞等待网络。本 change 是“正确性 + 数量级”，不是延迟修复。
- 一次性线程使 `HTTPConnectionPool` 的 thread-local 连接在该路径不复用（每次新连接）。
- `_VEC_CACHE_MAX=4096` 的 FIFO 淘汰不变：10k 候选时缓存仍抖动，批量只减少调用次数。
- 粘性 `_embed_failed` 不变：一次失败后本进程语义检索不可用，需重启。
- `CORE-NFR-PERF2`（<100ms）仍是**词法**基准；远端 embedding 路径不据此外推达标。
- 冒烟取证只证明“告警消失、语义排序生效”，不证明远端模型质量。

**被拒方案**：

- 把 `read` 改成 async（调用链上的 assembler/loop 全部要改，超出缺陷修复范围）。
- 只加缓存、不批量（没有解决“空读触网”和 HTTP 往返数）。
- 语义 top-K 预筛（真正的延迟优化，需要独立的召回质量评估，不能与缺陷修复捆绑）。
