# Design 0204 — 语义遗忘面

## 决策一览

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| D1 | 遗忘形态 | **收窄既有 `记忆遗忘` 的豁免面**，不新开遗忘面 | 复用 `_decay_score`/阈值/`migrate`→L4/`forgetting.<id>` ⇒ 改动面仅一处布尔守卫 |
| D2 | 豁免边界 | 摘要类（`source ∈ {compaction, context}`）**永久豁免**；派生事实类（`source ∈ {extraction, relation}`）参与 | 用户裁决②：摘要是「已准入材料的骨架」，派生事实是可再抽取的细节 |
| D3 | 开关 | 构造参 `semantic_forgetting: bool = False` + 配置 `memory.semantic_forgetting`（缺省 `False`） | 用户裁决④：缺省关 ⇒ 既有路径逐字不变 |
| D4 | 判据位置 | `forget()` 守卫内**短路布尔**，判据常量模块级 `_FORGETTABLE_SEMANTIC_SOURCES` | 避免 `elif` 嵌套（`0203` 教训）；常量与 `_GATE_EXEMPT_SOURCES` 并列可读 |
| D5 | 签名 | `forget()` 签名**不动** | 三处零参调用点（`loop/default.py:601,685`、`entry.py:1206`）逐字不变 |

## D1 为什么是「收窄豁免」而非「新开遗忘面」

语义条目的归档语义与 episodic **完全同构** —— 同一衰减评分、同一阈值、同一 L4 去向、同一可撤销
效应。一个「语义遗忘」新面就会复制这四样中的每一样，且留下**两套可漂移的判据**。收窄既有
`记忆遗忘` 要求，等于在**同一条判据**上多放行一类条目 ⇒ 零新评分逻辑。

## D2 豁免边界的取证

`source` 取值经 grep 核实（`store.py` / `compactor.py`）：

- 摘要类：`source="compaction"`（`store.py:604` 中层摘要、`:806` 会话摘要提升）、
  `source="context"`（`compactor.py:109,123` 压缩产出）。
- 派生事实类：`source="extraction"`（`store.py:899` `_write_key_fact`）、
  `source="relation"`（`store.py:963` `_write_relation`，经 `_RELATION_TAG`）。

即**恰好**是 `_GATE_EXEMPT_SOURCES` 的四个成员**二分**：`{compaction, context}` vs
`{extraction, relation}`。新常量 `_FORGETTABLE_SEMANTIC_SOURCES = frozenset({"extraction",
"relation"})` **补集**即豁免面。注释须点明：**豁免评分（`_GATE_EXEMPT_SOURCES`）≠ 豁免遗忘**
—— 前者管「写入时要不要过 importance 闸门」，后者管「衰减时要不要归档」，二者是不同面。

## D4 守卫写法（关键：逐字等价 + 无 `elif`）

```python
for entry in self._all_entries():
    forgettable = entry.kind == "episodic" or (
        self._semantic_forgetting
        and entry.kind == "semantic"
        and entry.source in _FORGETTABLE_SEMANTIC_SOURCES
    )
    if entry.layer != "L2" or not forgettable:
        continue
    if _decay_score(entry) >= threshold:
        continue
    self.migrate(entry.id, "L2", "L4", trace_id=f"forgetting.{entry.id}")
    forgotten.append(entry.id)
```

- 缺省关：`and` 首项 `self._semantic_forgetting` 为 `False` ⇒ `forgettable` 退化为
  `entry.kind == "episodic"` ⇒ **与旧守卫逐字等价**。
- 短路布尔**不新增 `If` 节点深度** ⇒ `test_control_flow_nesting_max_three` 不受影响。
- 删除旧的首行 `if entry.kind != "episodic" or entry.layer != "L2": continue`（被上式取代）。

## 接线与配置

- `manager.py`：ConfigSpec（紧随 `memory.relation_extract`）+ 访问器 `semantic_forgetting()`
  （逐字复刻 `relation_extract()`）。
- `runtime.py`：`MemoryStore(..., semantic_forgetting=config.semantic_forgetting())`。

## 零回归（为什么没有既有测试转红）

既有遗忘用例全部**走缺省构造** `MemoryStore()` ⇒ `_semantic_forgetting=False` ⇒ 派生事实仍不被
遗忘 ⇒ 逐字不变。已核验：`test_memory.py:622/:646/:654/:694/:718/:1051`、`test_loop.py:676`、
`test_skills.py:736` 均不缺省构造翻转该参。⇒ **0204 零既有测试破坏**；反证必须**显式翻转**构造参。

## 局限（写入 ADR-0194）

- **归档 ≠ 移出注入面**：`read()`/`_gather_facts` 无层过滤，L4 仅加性降权 ⇒ 归档派生事实仍可被注入
  （与 episodic 同一既有语义）。语义事实 `session_id=""` 为全局层 ⇒ 跨会话注入亦不受会话过滤。
- **只归档「不再被重抽」的事实**：`_write_key_fact`/`_write_relation` 每次压实新建条目、`_persist`
  刷新 `ts` ⇒ 活跃重抽的事实永不陈旧（期望性质），代价是重抽**重置 `reuse_count`**。
