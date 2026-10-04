# 接口设计：记忆接口（Memory Interface）

> 层：L2 ｜ 对应规格 `memory/spec.md` ｜ 模块 `02-modules/memory.md`

---

## 1. MemoryStore 接口

```python
class MemoryStore(Plugin):
    plugin_id = "memory.store"

    def read(self, query: str, budget: int = 4096) -> list[MemoryEntry]:
        """检索相关记忆，返回按相关性排序的条目，总 token ≤ budget。"""

    def write(self, layer: Layer, entry: MemoryEntry) -> MemoryId:
        """写入记忆（带 trace_id / 来源 / 时间戳）。"""

    def migrate(self, entry_id: MemoryId, src: Layer, dst: Layer) -> None:
        """层间迁移：结晶(→代码层) / 溶解(→技能层)。"""

    def index(self) -> IndexEntry:
        """返回 L1 最小索引。"""

    def audit(self, trace_id: str | None = None) -> list[MemoryEntry]:
        """审计写入记录。"""
```

---

## 2. 数据结构

```python
Layer = Literal["L0", "L1", "L2", "L3", "L4"]

@dataclass
class MemoryEntry:
    id: str
    layer: Layer
    content: str
    tags: list[str]
    source: str             # 来源（loop/evolution/user）
    trace_id: str
    reuse_count: int = 0    # 复用次数（结晶阈值依据）
    ts: float = 0.0          # 时间戳
    session_id: str = ""     # 会话 ID（跨轮记忆归组，缺省空串）
    importance: float = 0.0                          # 主观重要度 [0,1]（缺省 0 不调制）
    kind: Literal["episodic", "semantic"] = "episodic"  # 事件 / 提炼事实
```

---

## 3. 相关性打分

检索排序得分 ``rank`` 由**语义/结构**（加性）与**时间/复用/重要度**（乘性）两部分构成：

```python
def rank(entry, query, embedder=None) -> float:
    """rank = relevance(entry, query)          # 语义相似 × 层结构权重（加性）
                × recency_decay(entry)        # 新鲜度衰减 1/(1 + age/天)
                × (1 + log(1 + reuse_count))  # 复用频次
                × (1 + importance)            # 主观重要度
    """

def relevance(entry, query, embedder=None) -> float:
    """relevance = w1·sim(entry, query) + w4·layer_priority(entry.layer)

    仅含语义与层结构；时间/复用/重要度由 ``rank`` 乘性调制（避免双重计数）。
    """
```

默认层优先级：`L0(1.0) > L3(0.8) > L2(0.6) > L1(0.4) > L4(0.2)`。

- ``sim`` 默认**词法相似**（token 重叠，离线可测）；注入 ``embedder`` 则升级为**余弦相似**，
  embedder 抛错时**降级词法**、检索不中断。
- **embedder 契约**：批量可调用 ``(list[str]) -> list[list[float]]``。单条可调用（如 rag
  ``Embedder.embed``）经 ``memory/embedding.py::batch_embed`` 适配；memory **不依赖 rag**。
- **向量缓存**：``read`` 对 query **至多向量化一次**；条目按 ``content`` 哈希缓存向量，
  内容未变即复用；缓存**进程内易失**（不落盘）。

---

## 4. 结晶 / 溶解钩子

```python
class Crystallizer:
    def crystallize(self, skill_entry: MemoryEntry) -> PluginCandidate:
        """把 L3 技能提升为插件候选（交 L4 Validator）。"""

    def dissolve(self, plugin_id: str) -> MemoryEntry:
        """把失败插件降级为 L3 技能（保留教训）。"""
```

---

## 5. 后端接口（可插拔）

```python
class MemoryBackend(Protocol):
    def get(self, layer, entry_id) -> MemoryEntry | None: ...
    def put(self, entry: MemoryEntry) -> MemoryId: ...
    def search(self, query, layer) -> list[MemoryEntry]: ...
    def list_index(self) -> IndexEntry: ...
    def delete(self, entry_id) -> None: ...
```

MVP 实现：`FileBackend`（`memory/*.md` + `memory/*.jsonl`）。

---

## 6. 约束

- 密钥/敏感内容**只存引用**，绝不进入任何记忆层。
- `read` 返回 token 硬性 ≤ budget，超限截断并标记被截断项。
- `read` 命中即 `reuse_count += 1`（复用即强化；进程内强化，不落盘避免写放大）。

---

## 7. 关联

- 模块：`02-modules/memory.md`
- 进化联动：`evolution-interface.md`
- 规格：`openspec/specs/memory/spec.md`
