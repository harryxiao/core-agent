# 接口设计：记忆接口（Memory Interface）

> 层：L2 ｜ 对应规格 `memory/spec.md` ｜ 模块 `02-modules/memory.md`

---

## 1. MemoryStore 接口

```python
class MemoryStore(Plugin):
    plugin_id = "memory.store"

    def read(
        self,
        query: str,
        budget: int = 4096,
        *,
        exclude_source_prefixes: tuple[str, ...] = (),
        session_id: str = "",
    ) -> list[MemoryEntry]:
        """检索相关记忆，返回按相关性排序的条目，总 token ≤ budget。

        ``exclude_source_prefixes`` 命中的 ``source`` 前缀在**排名与预算之前**剔除
        （被排除项不吃预算、不被复用计数强化）；缺省空元组 ⇒ 检索语义与既往逐字一致。
        记忆分区隔离（如主 loop 不命中 `beast.*`）的**读取侧**开关，见 beast-mode-interface §4。

        ``session_id`` 非空时**只**返回归属该会话的条目 + **全局层**（``session_id == ""``
        的未归属条目，含 L0 人格与文档化笔记层）；过滤与来源排除**同一位置**（排名与预算
        之前）⇒ 被滤项同样不吃预算、不被复用计数强化。缺省空串 = 未归属调用者 ⇒
        **不过滤**（fail-open，与既往逐字一致）。见 change 0114 / ADR-0107。
        """

    def write(self, layer: Layer, entry: MemoryEntry) -> MemoryId:
        """写入记忆（带 trace_id / 来源 / 时间戳）。"""

    def migrate(self, entry_id, src, dst, *, trace_id: str | None = None) -> None:
        """层间迁移（可撤销）：记 Effect，按 trace_id 回滚即迁回原层；
        trace_id 缺省取条目自身来源 trace，压实等批量操作传统一 trace 一起撤销。"""

    def compact(self, query: str = "", budget: int = 4096) -> DecisionResult | None:
        """压实记忆：score 原语评分决策 + 注入摘要器时的会话摘要提炼（见 §3）。"""

    def forget(self, *, threshold: float = 0.05) -> list[MemoryId]:
        """遗忘（见 §3）：衰减评分低于 threshold 的 L2 episodic 条目迁 L4 归档，
        返回被归档条目 id（撤销句柄 forgetting.<id>）；不物理删除。"""

    def index(self) -> IndexEntry:
        """返回 L1 最小索引。"""

    def compact(self, query: str = "", budget: int = 4096) -> "DecisionResult | None":
        """压实记忆：注入 summarizer 时按 ``session_id`` 聚合 L2 episodic 提炼为 semantic 摘要
        并归档原条目；注入 compactor 时逐条目打分写回 ``importance`` 并做价值门控（全部可撤销）。"""

    def audit(self, trace_id: str | None = None) -> list[MemoryEntry]:
        """审计写入记录。"""
```

**构造注入点**（均为可选依赖注入，缺省不启用）：

```python
MemoryStore(
    backend=None,          # 可插拔后端（缺省 FileBackend）
    effect_tracker=None,   # 可逆效应追踪（缺省自建）
    embedder=None,         # 批量向量化契约，见 §3（缺省词法降级）
    compactor=None,        # judgment.Compactor：压实决策评分 + 逐条目 importance 打分（见 §3）
    summarizer=None,       # Summarizer：压实时的 LLM 摘要提炼，见 §3（缺省只评分不写）
)
```

### 1.1 对话转录存储（TranscriptStore，change 0115 / ADR-0108）

**非记忆层级**：对话转录是原始对话流，**不经** `MemoryStore.read` 取出，也**不**参与温度分层检索、
排名、`reuse_count` 强化、压实、固化与遗忘；只能经本接口按会话读取。落盘为 `$CORE_STATE_DIR` 下
**单文件** JSONL（单店 + `session_id` 列，不翻案 change `0048` 的「单店按会话归组」），
写入用 `os.open(O_APPEND)` + 单次 `os.write` 整行（POSIX 追加原子，跨进程并发不写坏行）。

```python
TranscriptStore(path: Path | None = None)      # path=None ⇒ 纯内存（测试用）

    def append(session_id, role, content, *, created_at: float | None = None) -> None
        # 逐行追加；session_id == ""（未归属）⇒ **不落盘**（不制造幻影会话）

    def read(session_id: str) -> list[dict]     # 该会话全部转录（按追加次序）

    def tail(session_id: str, turns: int, *, max_tokens: int = 0) -> list[dict]
        # 最近 turns 轮（轮 = 一条 user 提问及其答复）；max_tokens > 0 时再按 token
        # 从新到旧截断，截断后若开头剩孤儿 assistant 行则一并丢弃；turns <= 0 ⇒ 空

    def summaries() -> dict[str, dict]          # {session_id: {title, updated_at}}（排除未归属）
        # title = 该会话**首条用户消息**压平换行后截断 30 字（超长补「…」），无 user 行 ⇒ 空串
```

降级：文件缺失 / 坏行 ⇒ 跳过（不抛错、不阻断主流程）。对应规格：`memory/spec.md`
「对话转录持久化（非记忆层级）」。

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
    session_id: str = ""     # 会话归属：产生该条目的会话（缺省空串 = 未归属）；压实/固化/遗忘按此归组
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
- **摘要契约（Summarizer）**：``Summarizer = Callable[[list[MemoryEntry]], str]`` —— 同一会话的
  episodic 条目 → 一段提炼事实。prompt 文本属 memory 域（``memory/summarize.py::build_prompt``），
  模型调用经 ``summarize_with(llm)`` 适配；memory **不 import LLM/rag 抽象**（同 ``batch_embed``
  的依赖方向），由 L5 组合根注入。

### 摘要式压实（compact）

注入 ``summarizer`` 时，``compact`` 按 ``session_id`` 聚合 **L2 episodic** 条目，逐会话提炼为
**一条** semantic 摘要条目，并把被聚合的原条目**迁 L4 归档**（不删除）：

| 字段 | 取值 |
|---|---|
| `id` | `compaction.summary.<session_id>`（空会话用 `default`；同会话重复压实为覆盖，不增长） |
| `kind` | `semantic`（提炼事实，不再被下次聚合选中） |
| `source` | `compaction`（短标签；**不塞 trace 列表**——`source` 会作为出处标签进 prompt） |
| `trace_id` | `compaction.<session_id>`（摘要写入与全部迁移共用，`rollback(trace_id)` 整体逆转） |
| `tags` | `["compaction", "summary", "from:<原条目 id>", ...]`（出处可追溯） |

未注入 ``summarizer`` 时**只评分不写**：不写摘要条目、不改动原条目层级（降级）。摘要提炼
异常**不吞**：向上传播给触发点记录重试，原条目保持不变。

### 固化打分 + 价值门控（compact，0042）

注入 ``compactor`` 时，``compact`` 在提炼前先**逐条目打分**并写回 ``importance``：

- ``judgment.Compactor.score`` 的 ``score`` 原语返回的是**条目集的单一分数**（无 per-item
  分数），故**每条目一次调用**；按本地多因子序取前 ``_MAX_SCORED_PER_COMPACT = 20`` 条设上界，
  控制单次压实的模型调用数。``state`` 带 ``entry_id / session_id / layer / reuse_count``。
- 写回是**可变状态写入**，逐条记 ``Effect(op="memory.importance", undo=恢复旧值)``，trace 与
  压实同批（``compaction.<session_id>``）——回滚该轮同时撤销分值写回。
- **打分失败 ≠ 打 0 分**：``score`` 抛错或无分值即跳过该条目，``importance`` 保持原值（否则一次
  抖动会清空全库重要度、连带误遗忘）。

**价值门控**：会话内**本轮取得分值**的最高分低于 ``_CONSOLIDATE_THRESHOLD = 0.5`` 时，该会话
整体跳过（不提炼、不归档、原条目保持 L2 episodic）。本轮一个分值都没取得（未注入 scorer /
打分失败 / 超出打分上界）则**不设门槛**——与「没配 judgment 不停止固化」同一取向。

> 压实决策打分（0039/0041 的 ``DecisionResult``）失败时降级为 ``None``：它是咨询性返回值、
> 无写入副作用，不连带阻断固化与遗忘；摘要提炼失败仍按上节契约向上传播。

### 遗忘（forget，0042）

衰减评分 ``recency_decay × (1 + log1p(reuse_count)) × (1 + importance)`` 低于
``_FORGET_THRESHOLD = 0.05``（≈19 天零复用零重要度）即归档：

| 维度 | 口径 |
|---|---|
| 作用面 | 仅 **L2 episodic**；semantic（提炼产物）/ L0（人格）/ L3（技能）不衰减 |
| 动作 | ``migrate(L2 → L4)``：**不物理删除**（``audit`` 可见、检索降权，L4 层优先级 0.2） |
| 可逆 | 逐条 ``trace_id = forgetting.<entry_id>``，``rollback(trace_id)`` 迁回 L2 |
| 返回值 | 被归档条目 id 列表（撤销句柄） |
| 时间未知 | ``ts<=0`` 时 ``recency_decay`` 返回 1.0，不惩罚 → 不会被遗忘 |
| 触发 | 维护节拍驱动（change `0049`）：loop 收尾按 `maintenance_interval` 触发（`_maintain`，同节拍兼触发冷路径），或经 `core-agent memory maintain` 显式触发；压实路径（``persist → compact → forget``）仍顺带 sweep。异常降级不中断主流程 |

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
- `read` 的会话过滤在**排名/预算之前**生效（被滤项不吃预算、不被强化），与来源排除同口径；
  空标识不过滤 ⇒ 存量未归属条目构成全局层（ADR-0107）。

---

## 7. 关联

- 模块：`02-modules/memory.md`
- 进化联动：`evolution-interface.md`
- 规格：`openspec/specs/memory/spec.md`
