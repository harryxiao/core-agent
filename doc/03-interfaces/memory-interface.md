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
        allow_source_prefixes: tuple[str, ...] = (),
        session_id: str = "",
    ) -> list[MemoryEntry]:
        """检索相关记忆，返回按相关性排序的条目，总 token ≤ budget。

        ``exclude_source_prefixes`` 命中的 ``source`` 前缀在**排名与预算之前**剔除
        （被排除项不吃预算、不被复用计数强化）；缺省空元组 ⇒ 检索语义与既往逐字一致。
        记忆分区隔离（如主 loop 不命中 `beast.*`）的**读取侧**开关，见 beast-mode-interface §4。

        ``allow_source_prefixes`` 是排除面的**例外面**（change 0117 / ADR-0110）：命中**排除**
        前缀**且未**命中**放行**前缀的条目才剔除 ⇒ 缺省空元组时语义逐字不变，排除面为空时
        放行面**不产生任何效果**（无排除即无所放行）。神兽用例：封存 ``("beast.",)`` 不变 +
        放行 ``beast.<agent_id>`` ⇒ 兽可召回**自身**轨迹，他兽仍被排除。

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

    def forget(self, *, threshold: float = 0.05) -> list[MemoryId]:
        """遗忘（见 §3）：衰减评分低于 threshold 的 L2 episodic 条目迁 L4 归档，
        返回被归档条目 id（撤销句柄 forgetting.<id>）；不物理删除。"""

    def index(self) -> IndexEntry:
        """返回 L1 最小索引。"""

    def compact(
        self, query: str = "", budget: int = 4096, *, session_id: str = ""
    ) -> "DecisionResult | None":
        """压实记忆：注入 summarizer 时按 ``session_id`` 聚合 L2 episodic 提炼为 semantic 摘要
        并归档原条目；注入 compactor 时逐条目打分写回 ``importance`` 并做价值门控（全部可撤销）。
        带 ``_PRESERVE_TAGS`` 标签者**不入材料**（change `0179` / ADR-0170，见下「压实材料的排除面」）。

        ``session_id`` 为**聚合范围的收窄形参**（change `0131` / ADR-0124 / 账本 E66）：非空 ⇒
        只聚合**该会话**条目（SHALL NOT 跨会话提炼/迁移）；空串 ⇒ **全量** —— 该全量语义**保留给
        **显式调用**（CLI / 运维命令面）；**循环内路径**（轮内压实 ``DefaultLoop._compact`` 与维护节拍
        ``_maintain``）**一律**以本轮会话标识收窄（change `0192` / ADR-0182 / 账本 E129）。
        **不是** ``query`` —— 两者语义无干（此前按位置传入被当成 ``query``）。

        注入 ``summary_promoter`` 时，某会话摘要**首次越过** ``MAX_SUMMARY_CHARS`` 即把该摘要
        条目交付钩子**一次**（change `0153` / ADR-0145 / 路线图 G3）；缺省 UNWIRED ⇒ 行为不变。
        投喂摘要器的既有摘要槽为**首尾保留**节选（未越界逐字、越界「首部＋中略标记＋尾部」且总量恰为
        上界），比**纯头截断**（会无声销毁尾部 = 最新结论）**不**削弱「越界即交付」的触发语义 ——
        触发判据仍读 ``len(prior.content)`` 全体长度（change `0193` / ADR-0183 / 账本 E130）。"""

    def audit(self, trace_id: str | None = None) -> list[MemoryEntry]:
        """审计写入记录。"""

    def summary_for(self, session_id: str) -> MemoryEntry | None:
        """按会话取回既有摘要条目（**只读**；change `0150` / ADR-0142 / 账本 E94）。

        id 口径与压实写入**同一**（``compaction.summary.<session_id or 'default'>``）；无则 ``None``。
        SHALL NOT 产生任何写入 / 效应记录，SHALL NOT 变更条目的 ``reuse_count`` / ``importance`` /
        ``updated_at`` —— 供上层（如 CLI ``notes promote``）取数。"""

    def mid_summary_for(self, session_id: str) -> MemoryEntry | None:
        """按会话取回既有**中期**摘要条目（**只读**；change 0178 / ADR-0169 / 账本 E115）。

        id = ``compaction.mid.<session_id or 'default'>``；无则 ``None``。只读语义与
        ``summary_for`` **完全同形**（不写、不记效应、不变更 ``reuse_count``/``importance``/``updated_at``）。"""

    def summarize_slice(
        self, session_id: str, entries: list[MemoryEntry], *, max_chars: int
    ) -> str | None:
        """把一段**会话原文桩**滚合并为该会话的**中期**摘要（change 0178 / ADR-0169 / 账本 E115）。

        ``entries`` 为上层从转录切出的**临时桩**（``source="transcript"``，**不在库中**）——
        本方法**只读它们、SHALL NOT 将其落库**。产出为**一条** ``kind="semantic"`` 条目
        （``source="compaction"``，``id``/``trace_id`` = ``compaction.mid.<key>``）；
        已有中期摘要时把其内容作为材料**首条**一并投喂（滚动合并）；写前 ``redact_secrets``、
        截断至 ``max_chars``；**不 migrate** 任何来源；写入可撤销（按 trace_id 回滚即移除）。

        摘要器 UNWIRED / ``entries`` 为空 / ``max_chars`` 非正 ⇒ ``None`` 且**零写入零效应**。"""
```

**构造注入点**（均为可选依赖注入，缺省不启用）：

```python
MemoryStore(
    backend=None,          # 可插拔后端（缺省 FileBackend）
    effect_tracker=None,   # 可逆效应追踪（缺省自建）
    embedder=None,         # 批量向量化契约，见 §3（缺省词法降级）
    compactor=None,        # judgment.Compactor：压实决策评分 + 逐条目 importance 打分（见 §3）
    summarizer=None,       # Summarizer：压实时的 LLM 摘要提炼，见 §3（缺省只评分不写）
    summary_promoter=None, # SummaryPromoter：摘要首次越过 MAX_SUMMARY_CHARS 时交付 (session_id, 条目)
                           # 一次（change 0153；缺省 UNWIRED ⇒ 不交付）
    importance_scorer=None,# ImportanceScorer：写入侧重要度闸门评分器 (MemoryEntry -> float)，
                           # 见 §3「写入侧重要度闸门」（change 0177；缺省 UNWIRED ⇒ 写入逐字不变）
    ephemeral_sessions=(), # 临时会话集合（change 0245 / ADR-0233）：压实只做会话级摘要与归档，
                           # SHALL NOT 写全局派生（关键事实/关系/episodic）或交付 canonical 提升；
                           # 缺省空 ⇒ 压实逐字不变。组合根仅在执行面门控开启时传 ("bench",)
    token_estimator=None,  # 读预算/短带截断的 token 估算器（change 0230 / ADR-0237）：
                           # 缺省 core.tokens.DEFAULT_ESTIMATOR（启发式，行为逐字不变）
    l2_soft_max_entries=None,  # L2 活跃层软上限（change 0230 / ADR-0237）：缺省 None 关闭；
                               # 超限先 forget，再按 ts 升序迁移可遗忘条目至 L4，异常降级不阻塞写
    write_observer=None,   # 写入观察者 Callable[[Layer, MemoryEntry], None]（change 0269 / ADR-0259）：
                           # 公开 write 落库**之后**同步通知、不可否决、异常吞掉；缺省 None ⇒ 零调用
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

    def window(session_id: str, *, short_turns: int, mid_turns: int,
               short_tokens: int) -> tuple[list[dict], list[dict]]
        # **分层切分读取（一次 read()）**：返回 (短带原文, 中带原文)。短带 = 末 short_turns 轮
        # （按 short_tokens 从新到旧截断 + 丢开头孤儿 assistant 行，同 tail）；中带 = 其前 mid_turns
        # 轮（**不**按 token 截断）。两带**不重叠**；轮数不足 ⇒ 短带吃满、中带为空；
        # short_turns <= 0 ⇒ ([], [])（change 0178 / ADR-0169）

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
def rank(entry, query, embedder=None, *, stats=None, sim=None) -> float:
    """rank = relevance(entry, query)          # 语义相似 × 层结构 × 内容分区（加性）
                × recency_decay(entry)        # 新鲜度衰减 1/(1 + age/天)
                × (1 + log(1 + reuse_count))  # 复用频次
                × (1 + importance)            # 主观重要度
    """

def relevance(entry, query, embedder=None, *, stats=None, sim=None) -> float:
    """relevance = w1·sim(entry, query) + w4·layer_priority(entry.layer) + w5·tier(entry)

    仅含语义、层结构与内容分区（change 0277；tier ∈ {+1, 0, −1}，按 tags 精确判定）；
    时间/复用/重要度由 ``rank`` 乘性调制（避免双重计数）。
    """
```

默认层优先级：`L0(1.0) > L3(0.8) > L2(0.6) > L1(0.4) > L4(0.2)`。

- ``sim`` 默认**词法相似**（BM25 口径：IDF 加权 + 文档长度归一，离线可测）；注入 ``embedder``
  则升级为**余弦相似**，embedder 抛错时**降级词法**、检索不中断。``relevance`` / ``rank`` 的
  ``stats=`` 是内部优化参数：``MemoryStore.read`` 对候选集构建一次 ``LexicalStats``（分词缓存）；
  缺省 ``None`` ⇒ 原「交集 / 查询词元数」公式，公开调用方零改动。
- **embedder 契约**：批量可调用 ``(list[str]) -> list[list[float]]``。单条可调用（如 rag
  ``Embedder.embed``）经 ``memory/embedding.py::batch_embed`` 适配；memory **不依赖 rag**。
  组合根注入了 ``LLMEmbedder.embed_many``（一次 provider 调用收齐一批，change `0290` / ADR-0280）。
- **批量相似契约**（change `0290` / ADR-0280）：``relevance.batch_similarities(entries, query,
  embedder, *, batch_size=64) -> dict[str, float] | None``。``[query, *(content)]`` 按批切块、
  一次一批调用，**query 恒在第一块**（每次检索至多嵌入一次）；返回 ``id → 余弦``，向量算完即弃。
  **空候选集返回 ``{}`` 且不调用 embedder**（空读触网失败会置粘性降级、毒化后续检索）。任一批
  异常 / 返回数量不符 / 向量维度不符 ⇒ 返回 ``None``，``read`` 对**全部**候选走 BM25 ——
  绝不返回部分映射（禁止同一排序混合余弦与词法两种尺度）。``MemoryStore.read`` 排序前调用它，
  并把结果经 ``sim=`` 传给 ``rank``；``sim`` 以 ``is None`` 判缺失（``0.0`` 与负余弦合法）且
  优先于 ``embedder``。
- **向量缓存**：``read`` 对 query **至多向量化一次**；条目按 ``content`` 哈希缓存向量，
  内容未变即复用；缓存**进程内易失**（不落盘）。
- **强制与降级的边界**（change `0289` / ADR-0279）：``llm.embedding_required=true`` 只在
  **配置校验期**要求有效模型非空（空则阻断启动，见 configuration 接口）；它**不**探测可达性，
  也**不**改变本节的调用期降级——远端 ``/embeddings`` 失败仍降级 BM25 词法、检索不中断。
  语义 vs 词法的离线基准见 ``tests/test_semantic_benchmark.py``；多跳/关系流水线基准见
  ``tests/test_memory_graph_benchmark.py``（均只测通路与量纲，不测真实模型质量）。
- **复用强化**：命中条目 ``reuse_count`` 递增并**写回持久后端**（change 0187 / ADR-0178）——
  ``read`` 是**有副作用的读**（副作用**有界**：只覆盖进入预算的**选中**条目；非选中候选不写、不强化），
  每条写回记**可撤销效应**（``op="memory.reuse"``，``trace_id="reuse.<entry_id>"``，undo **还原**
  强化前的值、幂等非自减）。**批量提交**（change `0244`）：后端提供 ``put_many`` 时，一次检索
  的全部选中条目经**一次批量落盘**写回（不逐条全量重写）；无批量入口时逐条回退、语义不变。
  跨会话 / 进程重启后强化保持 ⇒ 遗忘曲线（``_decay_score`` 的
  ``freshness ** (1/(1+log1p(reuse_count)))`` 项）连续。``summary_for`` / ``mid_summary_for``
  **不经** ``read`` ⇒ 其「零写入 / 零效应」契约**不受影响**（逐字不变）。

- **摘要契约（Summarizer）**：``Summarizer = Callable[[list[MemoryEntry]], str]`` —— 同一会话的
  episodic 条目 → 一段提炼事实。prompt 文本属 memory 域（``memory/summarize.py::build_prompt``），
  模型调用经 ``summarize_with(llm)`` 适配；memory **不 import LLM/rag 抽象**（同 ``batch_embed``
  的依赖方向），由 L5 组合根注入。**材料 SHALL 含既有摘要条目**（若该会话已有摘要，它以
  ``MemoryEntry`` 形态作为**首元素**并入投喂）——摘要为**滚动合并**（change `0148` / ADR-0140）。

### 摘要式压实（compact）

注入 ``summarizer`` 时，``compact`` 按 ``session_id`` 聚合 **L2 episodic** 条目，逐会话提炼为
**一条** semantic 摘要条目，并把被聚合的原条目**迁 L4 归档**（不删除）：

| 字段 | 取值 |
|---|---|
| `id` | `compaction.summary.<session_id>`（空会话用 `default`；同会话重复压实为**滚动合并**——内容融合、条目不增长） |
| `kind` | `semantic`（提炼事实，不再被下次聚合选中） |
| `source` | `compaction`（短标签；**不塞 trace 列表**——`source` 会作为出处标签进 prompt） |
| `trace_id` | `compaction.<session_id>`（摘要写入与全部迁移共用，`rollback(trace_id)` 整体逆转） |
| `tags` | `["compaction", "summary", "from:<原条目 id>", ...]`（出处可追溯） |

摘要落库前 store 侧**无条件** ``redact_secrets``（change `0241`）：注入的摘要器**不构成信任
边界**，其输出可能夹带模型复述的明文密钥；未命中密钥形态时正文逐字不变。

未注入 ``summarizer`` 时**只评分不写**：不写摘要条目、不改动原条目层级（降级）。摘要提炼
异常**不吞**：向上传播给触发点记录重试，原条目保持不变。

**聚合范围按会话收窄**（change `0131` / ADR-0124 / 账本 E66）：``compact`` 的仅关键字形参
``session_id`` **非空**时**只**聚合该会话条目（打分写回随之只覆盖该会话）——会话级入口（Web
「压缩本会话记忆」）SHALL NOT 顺手提炼/归档他会话条目；**空串**（缺省）保持**全量**语义，
供循环内节拍压实使用（``loop/default.py`` 的 ``memory.compact()`` 不传该形参）。

**增量滚动摘要**（change `0148` / ADR-0140 / 账本 E90）：若该会话已存在摘要条目，
``compact`` SHALL 把**既有摘要内容**与本轮新增 episodic 条目**一并**投喂摘要器，产出**融合既有
结论与新增事实**的更新摘要——既有结论**不被静默丢弃**。滚动的是**内容**，`id` 与「每会话至多
一条、不增长」口径**不变**；既有摘要**只被吸收进新摘要**（**不**入 L4 迁移列表）。

**压实材料的排除面**（change `0179` / ADR-0170）：聚合只取 ``_episodic_groups()`` 的输出，
而该函数 SHALL 排除带 ``_PRESERVE_TAGS``（现为 ``{"failure"}``）标签的 L2 条目 ⇒
**摘要提炼、逐条目打分（``_score_importance``）、结构化关键事实抽取（``_extract_key_facts``）
三者一致地看不到失败条目**（同一材料源、一处排除三处生效）。故失败条目**不被摘要吸收**、
**不随压实迁 L4**、其 id **不入**摘要条目 ``tags`` 的 ``from:`` 出处。
判据用 **tag** 而非 ``source``：``_decay_score`` **不看 tags**；``rank`` 自 change `0277` 起
**只读四个档位标签**（``milestone`` / ``decision`` / ``log`` / ``transcript``），``failure`` 等既有 tag 语义零副作用，
且不触碰 ``exclude_source_prefixes`` 的命名空间红线。**遗忘路径不受此豁免**：``forget``
逐字不动 ⇒ 失败条目仍按自然衰减归档 L4（有界）。
写入侧闸门（§3）**不改**：注入 ``importance_scorer`` 时失败条目照常受闸门约束。

**上界可见性与提升钩子**（change `0153` / ADR-0145 / 路线图 G3）：滚动合并上界
``MAX_SUMMARY_CHARS``（公开常量，缺省 2000）是既有摘要**投喂时的节选上限** ⇒ **越界即下一轮滚合并
开始截断既有内容**。摘要 prompt 的字数要求与同一常量**同源**：``summarize_with`` 渲染时直接取
``MAX_SUMMARY_CHARS``，不另写死数字（change `0242` ⇒ prompt 与存储上界不再漂移）。注入 ``summary_promoter``（契约 ``SummaryPromoter = Callable[[str, MemoryEntry],
object]``）时，某会话摘要**首次越过**上界（既有摘要长度 ≤ 上界「或尚无摘要」而本次产出 > 上界）
即把**本次产出的**摘要条目交付钩子**一次**；**已越界**的会话 SHALL NOT 重复交付；``session_id``
空串 ⇒ 不交付。钩子 UNWIRED（缺省）⇒ 不交付、行为逐字不变；钩子抛错 ⇒ 降级（``warnings.warn``
留痕，不牵连压实的写回与迁移）。memory **只报边界**、**不** import notes（落盘由组合根注入的闭包完成）。

### 结构化关键事实抽取（compact，change `0155` / ADR-0147 / 路线图 G4）

注入 ``key_fact_extractor``（契约 ``KeyFactExtractor = Callable[[list[MemoryEntry]], list[KeyFact]]``，
缺省 UNWIRED）时，``compact`` 对**同一批**被聚合的 episodic 条目抽取「实体 → 取值」关键事实：

| 字段 | 取值 |
|---|---|
| `id` | `keyfact.<实体 slug>`（**同实体至多一条**；重复抽取**覆盖式更新**、条目不增长；跨批次覆盖**保留首见正时间戳**，change 0230 / ADR-0237） |
| `kind` | `semantic`（提炼事实，不再被下次聚合选中） |
| `source` | `extraction`（短标签） |
| `trace_id` | `compaction.<session_id>`（**与压实同 trace**：`rollback(trace_id)` 与摘要、迁移**一并**逆转） |
| `tags` | `["key_fact", "entity:<slug>", ("ref:<ref>")?, ("session:<sid>")?]` |
| `session_id` | **空串**（全局层、**不**参与会话隔离 —— 跨会话长期知识；会话只作 `tags` 溯源标注） |

``KeyFact``（``core.memory.extract``）：``entity`` / ``value`` / ``ref``（``ref`` **仅当形如
``coeffect:<名称>``** 才构成**引用式** —— 真值经 ``CoeffectResolver`` 在使用时注入 ⇒ ``value`` 恒为
``"<redacted>"``；**非该形态**的 ``ref`` **视为无引用**（弃用、不落 ``ref:`` 标签），取值回裸值判据
—— change `0173`）。

**公开脱敏判据**（change `0173`，``core.memory`` 导出）：``looks_like_secret(text) -> bool``
（密钥形态启发式）与 ``redact_secrets(text) -> str``（**子串**替换为 ``"<redacted>"``、保留其余结构）。
loop 侧把行动序列写入 L2 **前**复用同一份判据 ⇒ **一处定义、两处消费**。

**密钥红线**（本能力的核心）：脱敏在 **memory 侧**对抽取器返回的**每一条**结果**无条件**执行 ——
注入的抽取器**不构成信任边界**。规则 ① ``value`` 呈密钥形态（令牌前缀族 / 私钥块 / JWT /
``key[:=]value`` / 长随机串兜底）⇒ **强制** ``"<redacted>"``；② ``ref`` **仅当形如 ``coeffect:<名称>``**
⇒ ``value`` **一律** ``"<redacted>"``（非该形态视为无引用 ⇒ 取值回裸值判据）；③ **裸密钥无可用引用
⇒ 整条丢弃** + ``warnings.warn`` 留痕（含实体名、**不含**取值；「无可用引用」含空串**与**非
``coeffect:`` 形态）；④ ``entity`` 或 ``value`` 在 ``strip()`` 后为空 ⇒ **拒收**（change 0254 /
ADR-0245）：不落库、**不覆盖**同实体既有条目，且不计入「因密钥丢弃」留痕（空值不是脱敏结果）。
方向恒为 **over-redact**。**先脱敏后截断**（``_MAX_FACT_CHARS``=200；条数上界**自适应**
``key_fact_cap(n) = clamp(ceil(n × 0.25), 8, 16)``，``n`` = 本次压实聚合的 episodic 条数 ——
change `0177`／ADR-0168；下限取既有死值 8 ⇒ **只放宽不收紧**，``MAX_KEY_FACTS_PER_COMPACT`` 保留为
兼容别名）。**缺省抽取 prompt 的条数要求与同一旋钮同源**（change `0242`）：``build_extract_prompt``
未显式覆盖时按 ``key_fact_cap(n)``、``build_relation_prompt`` 按 ``relation_cap(n)``（同一函数别名）；
关系 prompt 的谓词白名单由公开的 ``RELATION_PREDICATES`` **渲染**（含全部中英文变体），不另写死清单。
截断面：``entity`` / ``ref`` 头部截断，``value`` 超长时**首尾保留**
（头 / 尾各半、中以 ``…`` 连接，总长仍 ≤ 上限 —— 取值常「头定名、尾定值」；change `0172`）。
**同批同 slug 归并**：同一批内 ``slug_entity(entity)`` 相同者归并为一条、**只留首条**落库（后至者
**不**挤占额度；归并后条数计额 = 本次 ``cap(n)`` 名额、**不重复占用**），被归并者经 ``warnings.warn``
留痕（含实体名、**不含**取值；与因密钥丢弃的留痕
**各自独立**）。跨压实的「重复抽取」不走此路 —— 由 ``id`` 同实体幂等覆盖处理。

**降级**：抽取器抛错 / 返回不可解析 ⇒ **不抽取**（``warnings.warn`` 留痕），**不**牵连压实的摘要
写回与条目迁移；未注入抽取器（缺省）⇒ 零抽取、压实行为**逐字不变**。**解析失败可观测**（change
`0172`）：``extract_with`` 判据为「**有输出但无 JSON 数组**」⇒ 告警（只报失败事实与文本长度、
**不含**输出正文，正文可能含明文密钥）；**合法空数组** ``[]``（模型明确无可抽）**不**告警。
抽取器与摘要器**互不依赖**：
``compact`` 的会话循环在「摘要器**或**抽取器」注入时运行。模型调用经 ``extract_with(llm)`` 适配
（prompt 与解析器属 memory 域；memory **不** import LLM 抽象）。

### 失效关键事实的运维修复（change `0174` / ADR-0165）

``MemoryStore.repair_stale_key_facts(*, dry_run: bool = False) -> RepairReport``（**只读预演**：
``dry_run=True`` 时不删、不落库、不落备份）。

``RepairReport``（``core.memory`` 导出）：``identified`` / ``sessions`` / ``deleted`` / ``written`` /
``backup_path`` / ``skipped``（**原因 → 条目 id 或会话**：``no_session`` / ``no_extractor`` /
``extract_failed`` / ``backup_failed``）/ ``dry_run``。

语义（**三段式**，备份口径见 change `0175`／ADR-0166）：**识别**失效条目（``tags`` 带 ``ref:`` 且该 ref
**非** ``coeffect:`` 形态、``content`` 取值为 ``"<redacted>"``）⇒ 按 ``session:<sid>`` 标签**按会话**
分组 ⇒ ① **收集**：每会话取 episodic 材料（**全层**：``layer`` 不过滤，已归档 L4 的条目同样参与）⇒
复用本能力 prompt / 脱敏 / 有界**重抽** ⇒ 落新；② **备份**：各成功会话待删条目的**并集** ⇒ **一份**文件
（``backup_path`` 指向它，**每次操作恰好一份**、共用一个时间戳）；③ **删除**：统一删各会话**全部旧**
keyfact（**排除**本次已写入的 id）。**fail-closed 三处**：抽取器未注入 / 该会话重抽抛错（**会话级**）/
备份写入失败（**操作级 ⇒ 跨会话一并阻断**，``skipped["backup_failed"]`` 列出全部会话）⇒ **不删**。
重抽返回合法空数组 ⇒ 视为成功 ⇒ 旧条目**仍删**。无失效条目 ⇒ 幂等（零写入、零备份）。
CLI：``core-agent memory repair-keyfacts [--dry-run]``。

``MemoryBackend`` 契约**零改动**（删除走既有 ``delete``）；memory 仍**不** import ``core.notes`` /
``core.loop``。

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

**复用延缓衰减**（change `0177`／ADR-0168）：``store._decay_score`` 的 **freshness 项**改为
``freshness ** (1 / (1 + log1p(reuse_count)))`` —— 被检索复用越多的条目衰减越慢（同时间戳 / 同
``importance`` 下评分**高于**未复用者）。**调制只落 ``_decay_score``**：``relevance.recency_decay``
是**检索（``rank``）与遗忘共用**的函数，故 ``recency_decay`` / ``rank`` / §3 相关性打分公式
**逐字不动**（``reuse_count=0`` 时 ``pow(x,1.0)==x`` 逐位相等，行为不变）。

### 写入侧重要度闸门（write，change `0177`／ADR-0168，接线与豁免面 change `0181`／ADR-0172）

注入 ``importance_scorer``（``ImportanceScorer = Callable[[MemoryEntry], float]``，缺省 UNWIRED ⇒
``write`` 逐字不变）后，``write`` **先评分再落库**（阈值为常量、无 LLM 二次判断）：

| 分数 | 行为 |
|---|---|
| ``< _IMPORTANCE_FLOOR``(0.2) | **拒收**：不写、无效应记录、``warnings.warn`` 留痕、返回 ``None`` |
| ``[_IMPORTANCE_FLOOR, _IMPORTANCE_AMBIT)`` | 按**意向层**写入后**降层 L4**（见下「降层可撤销」） |
| ``>= _IMPORTANCE_AMBIT``(0.4) | 按**意向层**入库并**写回** ``importance``（可逆，trace 取**条目自身 trace**） |

- **降层可撤销**：``EffectTracker.rollback`` 按**逆序**撤销 ⇒ 降层的「写入 + 迁移」**不得同 trace**
  （否则先迁回再**删除**）。实现为**两步双 trace**：先 ``write(意向层, entry)``（记条目自身 trace），
  再 ``migrate(意向层, "L4", trace_id=f"gate.<id>")`` ⇒ ``rollback(f"gate.<id>")`` 把条目**迁回原意向层**。
- **降级放行**：评分器抛错 / 返回界外值（``not 0.0 <= score <= 1.0``）⇒ 按意向层正常写入 +
  ``warnings.warn`` 留痕，不中断主流程。**留痕只报条目 id**、绝不回显正文（密钥红线）。
- ``_persist(layer, entry)`` 是 ``write`` 的**无闸门主体**（落库 + 记 ``Effect(op="memory.write")``）。
- **豁免面**（change `0181`／ADR-0172）：条目 ``source`` 属 ``_GATE_EXEMPT_SOURCES``（``compaction`` /
  ``context`` / ``extraction``）⇒ **不经评分**、与 UNWIRED **逐字同路径**（不拒收、不降层、不写
  ``importance``、无留痕）。判据落 ``source``（「**谁**产生」）而非 ``kind``（内容分类）—— 许可未来**有机**
  semantic 写入仍受评分。豁免在 ``write`` **调用点**短路，``_gate_score`` 与阈值常量逐字不动。
  **口径**：非豁免来源不分内外 —— 内部写（如 ``loop.<trace>``）与有机写同样经闸门。
- **工厂**：``memory.importance.score_with(llm)``（同一 ``str→str`` 接缝）把「prompt → 文本」适配为
  ``ImportanceScorer``；解析不出数值 ⇒ 抛 ``ValueError``、界外值 ⇒ 原样返回（**均**交闸门既有降级路径，
  方向恒为**放行**）。异常消息只含输出长度，不回显正文（密钥红线）。
- **配置键**：``memory.importance_gate``（bool，缺省 ``false``；``--memory-importance-gate`` /
  ``CORE_MEMORY_IMPORTANCE_GATE`` / yaml ``memory: importance_gate``）—— 组合根为 true 时注入
  ``score_with(_llm_text)``，否则 ``None``（缺省 ⇒ 与变更前逐字一致）。

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
    # 可选能力（change 0244）：批量写回 = 单次落盘。未实现时 `_reinforce` 逐条 `put` 回退。
    def put_many(self, entries) -> None: ...
```

MVP 实现：`FileBackend`（`memory/*.md` + `memory/*.jsonl`）。`put_many` 是**可选**成员（不进
`MemoryBackend` Protocol 的必选面，鸭子类型后端不受影响）：一次更新内存集与索引后**只落盘一次**。

**落盘耐久承诺（change `0206`／ADR-0196，缺省生效）**：`FileBackend` 的 JSONL 落盘**原子提交**
（写同目录 tmp ＋ `os.replace` ⇒ 目标文件不出现半写/空文件）；`_load` **逐行容错**（坏行跳过、
末尾汇总告警 `损坏 N 行`，**不收 `OSError`**、**不回显行内容**）。⇒ 半写崩溃从「启动直接抛异常」
变为「跳过坏行继续启动」。这是**缺陷修复**（完好文件行为逐字不变），不是可关的新行为。

---

## 6. 约束

- 密钥/敏感内容**只存引用**，绝不进入任何记忆层。
- `read` 返回 token 硬性 ≤ budget，超限截断并标记被截断项。token 估计为 **CJK 感知**
  （change 0245）：CJK 字符 ≈1 token/字符、其余 4 字符 ≈1 token（共享 `core.tokens`，
  与 `context.budget` / 转录短带截断同一口径）。
- `read` 命中即 `reuse_count += 1`（复用即强化；**落盘**，写放大有界于选中集，且经
  `put_many` 单次批量落盘 —— change `0244`）。写入侧热字典有界（`_HOT_MAX=512`，写入序淘汰）；
  后端内存集才是全量真源，读面不受淘汰影响。
- `read` 的会话过滤在**排名/预算之前**生效（被滤项不吃预算、不被强化），与来源排除同口径；
  空标识不过滤 ⇒ 存量未归属条目构成全局层（ADR-0107）。
- 来源排除的**例外面**（`allow_source_prefixes`）与排除**同一位置**生效（排名/预算之前）；
  封存**不得**以删除或层间迁移实现 —— 排除是**读取面**语义，条目本体照常留存（ADR-0110）。

---

## 7. 关联

- 模块：`02-modules/memory.md`
- 进化联动：`evolution-interface.md`
- 规格：`openspec/specs/memory/spec.md`
