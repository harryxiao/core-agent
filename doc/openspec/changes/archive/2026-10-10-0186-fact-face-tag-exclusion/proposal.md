# 变更提案 — 原始步序素材退出事实注入面（change 0186）

## 为什么

`loop.steps.<trace_id>`（`src/core/loop/default.py:819-831`）是每轮「工具动作（参数）→ 结果节选」
的**原始行动序列**，其**声明角色**是**抽取器素材**——`_write_trajectory` docstring 明文：另立该条
是为了让抽取器仍能看到原始序列（抽取器对**每条** L2 条目只取前 `extract._MAX_ENTRY_CHARS`(400)
字符入 prompt，与轨迹条目**并存**、轨迹条目内容逐字不变）。

但它的 `source` 与 `loop.<trace_id>`（轨迹）、`loop.failure.<trace_id>`（失败摘要）**同为** `"loop"`
（`src/core/loop/default.py:814/828/841`，`source=self._source`）⇒ 只要与任务检索命中，这条**原始**
序列就会被 `DynamicAssembler._gather_facts` 当作「相关事实」**注入 prompt**。后果：

- **噪声进窗口**：原始逐行工具序列（含参数摘要与结果节选）是**未消化的原料**，其信息已被同轮
  `loop.<trace_id>`（轨迹行 + 可检索 reply）与（失败时）`loop.failure.<trace_id>`（失败摘要）承载 ⇒
  实测是**同一份材料**在两个不同面各出现一次。
- **同源不对账**：该条目与 `observe_turn` 的笔记写回**同源**（皆出自 `_action_steps(ctx)`，
  `src/core/loop/default.py:113-135`）—— 两处消费同一份材料却无任何一致性约束。

`memory` 侧**已有**同型纪律的先例两条：`_ARCHIVE_SOURCES`（**来源**面排除，change `0180`／ADR-0171）
与 `_PRESERVE_TAGS`（**标签**面排除，change `0179`／ADR-0170）—— 二者都是「按某条**确定性判据**
把条目挡在某个消费面之外」。本 change 把**标签**面这条惯用法（`_PRESERVE_TAGS`）**一般化到装配面**：
「相关事实」注入面按 `entry.tags` 支持可选排除面 ⇒ 原始步序素材退出事实注入面。

## 为什么轴取 `tags` 而非 `source`

三者 `source` **同为** `"loop"` ⇒ **来源面天然无法**把 `loop.steps.*` 与 `loop.*` / `loop.failure.*`
分开（这正是 `exclude_fact_sources`（change `0185`）在此处**够不着**的原因）。区分判据只有两条：
`id` 前缀 `loop.steps.`，或标签 `"steps"`（`tags=["loop","steps"]`，`default.py:827`）。取 **tags**：
它是条目的**显式分类声明**（比 id 命名约定更表意），且与 `memory._PRESERVE_TAGS`（同为 tags 面）
**同型** —— 装配面因此同时镜像 memory 的两条既有排除惯用法（来源面 ← `_ARCHIVE_SOURCES`；
标签面 ← `_PRESERVE_TAGS`）。

## 改什么

| 面 | 变更 |
|---|---|
| `context/assembler.py` | `DynamicAssembler` 新增装配级参数 `exclude_fact_tags: frozenset[str] = frozenset()`；`_gather_facts` 读后按 `entry.tags`（**交集**语义）过滤 |
| `runtime.py` | 主装配器传 `exclude_fact_tags=frozenset({"steps"})` |
| 规格 | `context` **MODIFIED**「动态上下文构建」（+ 事实面**标签**排除面条款）+ 1 Scenario |
| 测试 | `loop.steps.*` 不进事实面 / `loop.*`·`loop.failure.*` 不受影响（回归锚）/ `read()` 仍召回（回归锚）/ 缺省空 ⇒ 逐字不变（回归锚）/ 组合根接线 |

## 影响

- **行为变更（有意）**：未显式传入时**无**任何变化；组合根传入后，带 `"steps"` 标签的条目
  （当前**恰好**是 `loop.steps.<trace_id>` 一条一族）退出「相关事实」块，其信息仍由同轮轨迹条目
  承载 ⇒ **窗口噪声下降、可见性不变**。
- **不受影响**：`loop.<trace_id>`（`tags=["loop","trajectory"]`）与 `loop.failure.<trace_id>`
  （`tags=["loop","failure"]`）**无** `"steps"` 标签 ⇒ 仍留在事实面（回归锚）；
  `MemoryStore.read` 的检索语义**不变**（过滤只发生在装配面的注入步骤）⇒ **抽取器素材角色不受影响**。
- **封存红线不动**：`exclude_source_prefixes=("beast.","pet")`（`runtime.py`）**逐字不改**；
  `exclude_fact_sources`（change `0185`）语义**逐字不改** —— 本次是**并列的新轴**，不是把两条塞一条。
- **（②）`key_fact` vs 笔记结论：设计上非重复**（本 change **不**引入跨模块匹配）：`key_fact` 是
  **结构化实体**（`entity:` 面），笔记结论是**规范散文知识**（canonical Markdown 真相层）——
  不同面、不同消费方式，重复不成立。仅在此登记结论。
- 无新增第三方依赖；无配置键新增（排除面由组合根**硬接线**）；无 import 方向变化。
