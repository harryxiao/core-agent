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
    skills: list[dict]          # L3 技能（按需）
    constitution: list[str]     # 宪章/约束（必保）
    pending: list[str]          # 未决事项/验收标准（必保）
    token_used: int             # 实际注入 token
    token_budget: int
```

---

## 2. DynamicAssembler 接口

```python
class DynamicAssembler:
    def build(self, task: str, stage: str, *, budget: int) -> ContextPack:
        """按任务装配上下文（事实以 task 为 query 召回）；超预算裁剪低相关度内容。"""

    def fetch_detail(self, pointer: str) -> str:
        """按信息地图指针跳转取细节。"""
```

---

## 3. InfoMap 接口

```python
class InfoMap:
    def index(self, doc_id: str, content: str) -> MapEntry:
        """把长文档转为轻量目录索引（章节/要点/位置指针）。"""

    def lookup(self, doc_id: str, query: str) -> list[Pointer]:
        """按查询定位相关位置指针。"""

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
    def should_compact(self, rounds: int, token_used: int, budget: int) -> bool:
        """判断是否触发压实（轮数/token 阈值/子任务切换）。"""

    def compact(self, history: list[dict]) -> Compaction:
        """多轮关键信息摘要沉淀，保证关键信息不丢失。"""

    def persist(self, c: Compaction) -> None:
        """沉淀产物写回 MemoryStore（L2 事实 / L3 技能）。"""

@dataclass
class Compaction:
    conclusions: list[str]      # 已完成子任务结论
    decisions: list[str]        # 关键决策
    open_items: list[str]       # 未决事项
    dropped: list[str]          # 被清理的冗余内容 id
```

---

## 5. BudgetManager 接口

```python
class BudgetManager:
    def enforce(self, pack: ContextPack, budget: int) -> ContextPack:
        """裁剪低相关度内容至预算内；宪章/未决事项/验收标准优先保留。"""
```

- 保留策略：按**相关度降序**依次纳入可容纳项，**跳过**放不下的项（不掐断后续），
  避免单个大项阻塞其后更小的低相关项；`skills` 用事实裁剪后的**剩余预算**。

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
