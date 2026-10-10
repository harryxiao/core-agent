# 设计 — 压缩产物退出事实注入面（change 0185 / ADR-0176 / 台账 E122）

## 决策

### D1 轴选 `MemoryEntry.source`，**不**选 id / tags（对计划的一处订正）

计划原文写「`_gather_facts` 读后按 `entry.source` 前缀过滤」，但给的实参是
`("compaction.summary.", "compaction.mid.")` —— 那是 **id** 前缀，拿它去匹配 **source** 轴
**一个也匹配不到**（`source` 是 `"compaction"`，不是 `"compaction.mid.<key>"`）⇒ 照抄会让本 change
**静默失效**。故按语义轴取值：

| 条目 | `id` | `source` | 有专块承载？ | 该不该进事实面 |
|---|---|---|---|---|
| 中层摘要 | `compaction.mid.<key>` | `compaction` | ✅「历史摘要（中期）」 | **否** |
| 长期摘要 | `compaction.summary.<key>` | `compaction` | ✅「历史摘要（长期）」 | **否** |
| 压缩产出的事实 | `compaction.fact.<key>.<i>` | `context` | ❌ | **是**（回归锚） |
| 压缩产出的未决 | `compaction.open.<key>.<i>` | `context` | ❌ | **是**（回归锚） |

`source` **恰好**是「压缩产物 vs 上下文派生产物」这条分界线（`compactor.py:101/115` 写 `"context"`、
`store.py:461/655` 写 `"compaction"`），且**只有**这两条是 `"compaction"` ⇒ 前缀 `"compaction"`
**精确**选中要排除的两条、**可证**不碰回归锚两条。故组合根实参为 `("compaction",)`。

### D2 **新参数**，不往封存面里塞第三项

`exclude_source_prefixes`（既有的**封存**面，`runtime.py:603` 的 `("beast.","pet")` 是 phase-26 红线）
语义是「该命名空间对本 agent **永不可见**」；本次的排除理由完全不同 ——「**已由专块注入**，故不重复」。
两个理由 ⇒ 两个参数：

- 理由不同，混在一个元组里会让后续读者以为 `compaction` 也被**封存**（它其实照常注入，只是换了通道）；
- `with_allow_source_prefixes` 派生的装配器会**继承**排除面（神兽放行自己的 `beast.<id>`）——
  若把 `compaction` 混进封存面，放行语义会与之纠缠；
- 封存面元组**逐字不动** ⇒ 红线零风险。

### D3 读**后**过滤：接受预算上是近似的，如实记账

`_gather_facts` 先 `read()` 再丢。`MemoryStore.read` 内部按预算截断 ⇒ 被丢的摘要条目**已经吃掉了**
事实面预算（这正是「先于预算过滤」的 `exclude_source_prefixes` 与本参数的分工差别）。不把过滤下沉进
`read()` 的理由：

- `read()` 是**检索语义**面（其结果是通用召回，`compaction.*` 条目对**其他**消费者——抽取器素材、
  检索素材、CLI 查询——**仍应可见**）；「已由专块注入」是**装配面**事实，只有装配器知道哪些块会被注入。
  把装配面知识塞进 `read()` 是**方向反转**（下层背负上层通道细节）。
- 代价有界：摘要正文是**一条**（每会话长期/中期各一条），远小于事实面预算 ⇒ 记为**局限①**（如实记账），
  不为此改动检索契约。

### D4 缺省空 ⇒ 逐字不变（零风险落点）

`exclude_fact_sources: tuple[str, ...] = ()`；空元组 ⇒ **不建过滤**、`_gather_facts` 的返回路径与
既有**逐字相同**。所有既有测试构造点（未传该参）行为零变化；`with_allow_source_prefixes` 派生时
**继承**（与排除面同型）—— 派生装配器同样不该看到重复通道。

### D5 规格落点：`context` MODIFIED ×1

「动态上下文构建」追加事实面排除面条款（含「缺省空 ⇒ 逐字一致」与「只落在装配面的注入步骤、
`read` 检索语义不变」两句），+ 1 Scenario「压缩产物不进事实面」。**既有 4 Scenario 逐字保留**。
不在 `memory` 规格落条款：被改的是**装配**行为，`MemoryStore.read` 的语义**未变**。

## 不变量

- **I1** 未传 `exclude_fact_sources` ⇒ 装配结果与变更前**逐字相同**。
- **I2** `MemoryStore.read` 的检索语义 / 排序 / 预算 / `reuse_count` 强化**逐字不变**。
- **I3** `source="context"`（含 `compaction.fact` / `compaction.open`）**不受影响**。
- **I4** `exclude_source_prefixes=("beast.","pet")`（`runtime.py:603`）**逐字不动**。
- **I5** 「历史摘要（中期/长期）」专块的渲染（`planner.py:326-331`）**逐字不变**。
- **I6** 无新第三方依赖；无 import 方向变化；无新配置键。

## 测试设计

| # | 用例 | 断言 |
|---|---|---|
| 1 | `test_compaction_mid_excluded_from_facts` | `source="compaction"` 的中层摘要**不进** `facts` |
| 2 | `test_compaction_summary_excluded_from_facts` | 长期摘要同理（同一前缀，两态各一） |
| 3 | `test_compaction_fact_entries_stay_in_facts` | `source="context"` 的 `compaction.fact` / `compaction.open` **仍在** `facts`（回归锚） |
| 4 | `test_fact_source_exclusion_default_is_verbatim` | 不传该参 ⇒ 摘要**仍在** `facts`（逐字兼容回归锚） |
| 5 | `test_build_runtime_excludes_compaction_from_fact_face` | 组合根装配的主装配器**真的**传了 `("compaction",)`（接线） |
| 6 | `test_summary_block_still_carries_mid_and_long` | 专块渲染不变（正文可见性未被本 change 剥夺） |

基线 **2185**；本 change 预计 **+5 ~ +6**。

## 局限

① 过滤在 `read()` **之后** ⇒ 被丢条目已占预算（D3，代价有界）；
② 前缀匹配无边界语义（`source="compaction-extra"` 之类会被一并排除，当前无此类条目）；
③ 排除面是**装配级参数**、非配置键 ⇒ 用户不可调（有意的：通道重复是**实现事实**，不是偏好）；
④ 只覆盖「装配面事实注入」这一条通道 —— 若将来出现第三条注入通道，须同样登记排除面（无自动守护，
  由 change `0189` 的边界门禁面承接）。
