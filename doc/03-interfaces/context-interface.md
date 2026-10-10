# 接口设计：上下文工程（Context Engineering Interface）

> 模块：`02-modules/context.md` ｜ 规格：`openspec/specs/context/spec.md`

---

## 1. 上下文包模型

```python
@dataclass
class ContextPack:
    task: str
    stage: str                  # 装配阶段标注（暂不参与事实选择）
    facts: list[dict]           # L2 事实（按需检索）
    constitution: list[str]     # 宪章/约束（必保）
    pending: list[str]          # 未决事项/验收标准（必保）
    pointers: list[dict]        # 信息地图**目录层**（指针，非全文；缺省空 ⇒ 逐字不变）
    token_used: int             # 实际注入 token
    token_budget: int
```

- ``pointers`` 元素为 ``{"doc_id", "section", "summary", "pointer"}``，``pointer`` 即
  ``doc_id#section``（取详情工具的入参口径）。由装配器读信息地图注入（change 0140 / ADR-0133）。

---

## 2. DynamicAssembler 接口

```python
class DynamicAssembler:
    def __init__(
        self, *, memory=None, info_map=None, constitution=None, project_info=None,
        exclude_source_prefixes: tuple[str, ...] = (),
        allow_source_prefixes: tuple[str, ...] = (),
        exclude_fact_sources: tuple[str, ...] = (),
    ) -> None:
        """``exclude_source_prefixes`` 透传记忆检索的**来源排除**（缺省空 ⇒ 不含排除）。

        组合根为主 loop 的装配器传 ``("beast.",)`` ⇒ 神兽记忆分区不进主 loop 上下文
        （beast-mode spec「记忆分区封存」；见 beast-mode-interface §4/§10）。

        ``allow_source_prefixes`` 是对应的**例外面**（透传至同一次检索，change 0117 / ADR-0110）：
        命中排除**且未**命中放行的条目才剔除。缺省空 ⇒ 语义逐字不变。

        ``exclude_fact_sources``（change 0185 / ADR-0176）为**事实面排除面**：按
        ``MemoryEntry.source`` **前缀**把「**已由专块注入**」的条目挡在「相关事实」注入面之外 ——
        组合根传 ``("compaction",)`` ⇒ 会话长期 / 中期摘要（已由「历史摘要」专块每轮注入）不再
        重复进事实面。缺省空 ⇒ **不建过滤**、装配结果与既往**逐字一致**。与
        ``exclude_source_prefixes``（**封存**面）**不同理由、不合并**：前者「永不可见」、
        本参数「已由别处注入」。过滤落在**读后** ⇒ ``MemoryStore.read`` 语义逐字不变。
        """

    def with_allow_source_prefixes(self, *prefixes: str) -> DynamicAssembler:
        """**派生**装配器：排除面逐字继承，放行面替换为给定前缀（排除面的例外面）。

        神兽用例：主 Agent 侧的封存不变、放行**自身** ``beast.<agent_id>`` ⇒ 兽可召回自己
        的过往经验，他兽仍被排除（beast-mode spec「Independent Sub-Agent」）。
        **派生而非原地改**：主 loop 与神兽共用一份配置，原地改会波及主 loop（封存红线）。
        **事实面排除面 ``exclude_fact_sources`` 逐字继承**（放行面是封存面的例外面，与事实面去重无关；
        change 0185 / ADR-0176）。
        """

    def build(self, task: str, stage: str, *, budget: int, session_id: str = "") -> ContextPack:
        """按任务装配上下文（事实以 task 为 query 召回）；超预算裁剪低相关度内容。

        ``session_id`` 为调用方会话标识（缺省空串 = 未归属），透传至 L2 事实检索的会话维度
        （见 change 0114 / ADR-0107）。

        **读信息地图**（change 0140 / ADR-0133）：把各已登记文档的**任务匹配指针**汇成目录层
        注入 ``pack.pointers``（每文档上界 ``_MAX_POINTERS_PER_DOC``）；未接地图 / 地图为空 ⇒
        目录层为空，装配行为与既往逐字一致。
        """

    def fetch_detail(self, pointer: str) -> str:
        """按信息地图指针跳转取细节（``doc_id#section``）——「模型按需取详情」的消费面。

        经 ``tools.context_read`` 暴露给模型（取数器由组合根注入）；指针无命中返空串**不抛**
        （任务不因指针失效中断）。返回**指针摘要**（既有语义；原文片段抽取不在本账内）。
        """
```

---

## 3. InfoMap 接口

```python
class InfoMap:
    def index(self, doc_id: str, content: str) -> MapEntry:
        """把长文档转为轻量目录索引（章节/要点/位置指针）。"""

    def lookup(self, doc_id: str, query: str) -> list[Pointer]:
        """按查询定位相关位置指针；**地图缺失**时对原文走受控线性扫描兜底。"""

    def register(self, doc_id: str, content: str) -> None:
        """登记**原文**（不建目录索引）—— `index` = 原文+索引（一阶），本方法 = 仅原文
        （**索引不可用**态，二阶兜底入口；段数上界 ``_MAX_SCAN_SEGMENTS``）。"""

    def documents(self) -> list[str]:
        """已登记原文的文档 id（含未建索引者）—— 装配器读地图的入口。"""

    def rebuild_if_stale(self, doc_id: str, content_hash: str) -> None:
        """文档变更（hash 不同）时增量重建。"""

@dataclass
class Pointer:
    doc_id: str
    section: str
    summary: str                # 要点摘要（非全文）
    offset: int | None
```

---

## 4. Compactor 接口

```python
class Compactor:
    def __init__(self, memory: MemoryStore | None = None, *, step_threshold: int = 6) -> None:
        """``step_threshold``：**本轮工具步数**阈值（缺省 ``6``；组合根按 ``loop.compact_steps`` 注入）。"""

    def should_compact(self, steps: int, token_used: int, budget: int) -> bool:
        """判断是否触发压实（**本轮工具步数**/token 阈值）。

        ``steps`` 是本轮内已记账的工具动作步数（``LoopContext.rounds``，每用户轮自 ``0`` 起算），
        **非**对话轮数（change 0182 / ADR-0173）。本方法是**纯判据**：同轮**至多压实一次**
        由调用方（``DefaultLoop.astream`` 的本轮标记）把关。
        """

    def compact(self, history: list[dict]) -> Compaction:
        """多轮关键信息摘要沉淀，保证关键信息不丢失。"""

    def persist(self, c: Compaction, *, session_id: str = "") -> None:
        """沉淀产物写回 MemoryStore（L2 提炼事实）：kind="semantic"，tags 带原始 id 出处。

        产物按**本轮会话**归属（缺省空串 = 未归属），条目 id 带会话键（缺省 ``default``）
        ⇒ 跨会话不再同名覆盖（见 change 0114 / ADR-0107）。
        """

@dataclass
class Compaction:
    conclusions: list[str]      # 已完成子任务结论
    decisions: list[str]        # 关键决策
    open_items: list[str]       # 未决事项
    dropped: list[str]          # 被清理的冗余内容 id
    source_ids: list[str]       # 贡献历史的原始 id（tags 写为 from:<id>，出处可追溯）
```

**降级路径声明**：本压实器是**启发式**降级路径（关键词识别结论/决策/未决事项），其输入是
多轮 ``history``（自由文本）；LLM 提炼统一由记忆压实通道（``MemoryStore.summarizer``，
见 memory-interface §3）承担，此处**不新增模型调用点**。触发点由 loop 接线：轮数达阈值或
token 预算超限时 ``persist`` → ``memory.compact``，终止语义不变。

---

## 5. BudgetManager 接口

```python
class BudgetManager:
    def enforce(self, pack: ContextPack, budget: int) -> ContextPack:
        """裁剪低相关度内容至预算内；宪章/未决事项/验收标准优先保留。"""
```

- 保留策略：按**相关度降序**依次纳入可容纳项，**跳过**放不下的项（不掐断后续），
  避免单个大项阻塞其后更小的低相关项。

---

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `BUDGET_EXCEEDED` | token 超预算（触发裁剪） |
| `MAP_STALE` | 信息地图失效（触发重建，期间降级全文检索） |
| `COMPACTION_LOSSY` | 压实产物丢失关键信息（不替换原文） |

---

## 7. 关联

- 模块：`02-modules/context.md`
- 规格：`openspec/specs/context/spec.md`
- 变更：`openspec/changes/0140-infomap-wiring/`（信息地图装配接线，change 0140 / ADR-0133）
