# 变更提案 — 压缩产物退出事实注入面（change 0185）

## 为什么

**ADR-0169 局限⑥**（三层会话滑窗）与 **ADR-0171 局限③**（语义记忆去重）同源：压缩产物经**两条通道**
进入同一次请求。中层摘要 `compaction.mid.<key>` / 长期摘要 `compaction.summary.<key>`
（`src/core/memory/store.py:457` / `:651`）的正文**已由专块**「历史摘要（中期）/（长期）」
（`src/core/loop/planner.py:326-331`）每轮注入；同时它们 `source="compaction"` **不在**装配面排除面内
（`src/core/context/assembler.py:114-125`）⇒ 只要与任务检索命中，**同一份正文第二次**进「相关事实」块。

后果有两层：

- **预算浪费**：同一段文字在窗口里占两份 token，而事实面预算本就紧张。
- **证据误读（更实质）**：同内容出现两次，模型会读成**两条独立证据**（两条不同 source 的 fact），
  对本已模糊的召回质量形成虚假置信。

规格侧本已有同类纪律的先例：`notes`「会话摘要提升」明文「同一份内容 SHALL NOT 经两条通道重复注入同一次请求」
（`doc/openspec/specs/notes/spec.md:61-66`）；「动态上下文构建」尚无对应条款。

## 改什么

| 面 | 变更 |
|---|---|
| `context/assembler.py` | `DynamicAssembler` 新增装配级参数 `exclude_fact_sources: tuple[str, ...] = ()`；`_gather_facts` 读后按 `entry.source` **前缀**过滤 |
| `runtime.py` | 主装配器传 `exclude_fact_sources=("compaction",)` |
| 规格 | `context` **MODIFIED**「动态上下文构建」（+ 事实面排除面条款）+ 1 Scenario |
| 测试 | mid 不进事实面（仍进专块）/ 长期摘要同理 / `compaction.fact`·`open`（`source="context"`）不受影响（回归锚）/ 缺省空 ⇒ 逐字不变 |

## 影响

- **行为变更（有意）**：未显式传入时**无**任何变化；组合根传入后，`source="compaction"` 的条目
  （当前**恰好**是中层摘要与长期摘要两条）退出「相关事实」块，改由「历史摘要」专块承载 ⇒
  **正文可见性不变、通道从二变一**。
- **不受影响**：`compaction.fact.<key>.<i>` / `compaction.open.<key>.<i>`（`source="context"`，
  `src/core/context/compactor.py:97-115`）**无**专块承载 ⇒ 仍留在事实面（回归锚）；
  `MemoryStore.read` 的检索语义**不变**（过滤只发生在装配面的注入步骤）。
- **封存红线不动**：`exclude_source_prefixes=("beast.","pet")`（`runtime.py:603`）**逐字不改** ——
  本次是**新参数**，不是往封存面里塞第三项。
- 无新增第三方依赖；无配置键新增（缺省空 ⇒ 无需配置面）；无 import 方向变化。
