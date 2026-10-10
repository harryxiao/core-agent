# 设计 — 原始步序素材退出事实注入面（change 0186 / ADR-0177 / 台账 E123）

## D1 轴选 `MemoryEntry.tags`（**不**选 `source`，也**不**选 `id`）

**问题**：`loop.steps.<trace_id>` 与 `loop.<trace_id>` / `loop.failure.<trace_id>` 的 `source`
**逐字相同**（皆 `source=self._source` == `"loop"`，`default.py:814/828/841`）⇒ 来源面对三者
**天然不可分**。若沿用 change `0185` 的 `exclude_fact_sources`，无论传什么前缀都会**要么全挡要么全不挡**
（传 `("loop",)` 会连轨迹与失败摘要一起挡掉 —— 那是**过挡**，把有价值的事实一并杀掉）。

**备选与取舍**：

| 轴 | 判据 | 评价 |
|---|---|---|
| `source` 前缀 | 无 | **不可行**：三者 source 相同，无判别力（过挡或空操作） |
| `id` 前缀 | `loop.steps.` | 可行；但依赖 id 命名约定、对条目**显式声明**的分类无感知 |
| `tags` | 含 `"steps"` | **取此**：条目**显式分类声明**（`tags=["loop","steps"]`），与 `memory._PRESERVE_TAGS`（同为 tags 面排除，change `0179`／ADR-0170）**同型** |

**结论**：新增 `exclude_fact_tags: frozenset[str]`，语义为**交集**（条目 `tags` 与排除面有交集即挡）。
装配面由此**同时镜像 memory 的两条既有排除惯用法** —— 来源面 ← `_ARCHIVE_SOURCES`（change `0180`）；
标签面 ← `_PRESERVE_TAGS`（change `0179`）。

## D2 **并列新轴**，不并入 `exclude_fact_sources`

`exclude_fact_sources` 与 `exclude_fact_tags` **理由与判据皆不同**（前者「来源命名空间」、后者
「条目分类标签」），且二者的轴**互不覆盖**（见 D1）。合成一条会让「compaction 面」与「steps 面」
的语义纠缠、断言不可分。⇒ **两条并列参数**（构造器已有 `exclude_source_prefixes` /
`allow_source_prefixes` 的并列先例，`PLR0913` 豁免即为此设）。缺省皆空 ⇒ 逐字不变。

## D3 过滤落**读后**（与 `0185` 同构）

排除是**装配面注入步骤**的关注点，非**检索语义**：`MemoryStore.read` 的排名 / 预算 / 复用强化对
**其他**消费者（**抽取器**、检索素材、CLI 查询）必须逐字不变 —— `loop.steps.*` 的声明角色就是
**抽取器素材**，`read()` 必须仍能取回它。⇒ 过滤在 `_gather_facts` 拿到 `entries` **之后**。
代价与 `0185` 同：被挡条目**已吃掉事实面预算**（有界：每轮至多一条），见局限①。

## D4 缺省空 ⇒ 逐字不变；派生装配器继承

`self._exclude_fact_tags = frozenset()` 时 `_gather_facts` 的过滤子句恒假（空集交集为空）⇒ 返回
列表与既往逐字相同。`with_allow_source_prefixes` 派生装配器**继承**本排除面（放行面是封存面的
例外面，与事实面去重无关；与 `0185` 的 `exclude_fact_sources` 继承**同构**）。

## D5 规格落点 `context`（**不**落 `memory`）

被改的是**装配面的注入步骤**，`memory` 的 `read` 契约与「条目角色」定义**均未动**（`loop.steps.*`
的抽取器素材角色是 `loop` 侧 docstring 的既有声明，本 change 不改它）⇒ 规格写在**行为实际发生变化**
的能力上：`context`「动态上下文构建」**MODIFIED**（与 `0185` **同一** Requirement 追加**标签**面条款）。
`memory` 的两条惯用法（`_ARCHIVE_SOURCES` / `_PRESERVE_TAGS`）在 ADR 与规格中**交叉引用**，不改其文本。

## 不变量

| 编号 | 不变量 |
|---|---|
| I1 | `exclude_fact_tags` 缺省 `frozenset()` ⇒ `_gather_facts` 返回与既往**逐字相同** |
| I2 | `MemoryStore.read` 的检索语义 / 排序 / 预算 / 复用强化**逐字不变**（过滤在读后） |
| I3 | `exclude_fact_sources`（`0185`）语义**逐字不变**；`exclude_source_prefixes=("beast.","pet")` 封存红线**逐字不动** |
| I4 | 无 `"steps"` 标签的条目（`loop.*` / `loop.failure.*` / 压缩产物 / 关键事实…）**不受影响** |
| I5 | 派生装配器 `with_allow_source_prefixes` 继承两面排除（source 面 + tags 面） |
| I6 | 无新配置键、无新第三方依赖、无 import 方向变化 |

## 测试设计

| 用例 | 断言 |
|---|---|
| 排除生效 | 假 store 返 `tags=["loop","steps"]` 与 `tags=["loop","trajectory"]` 各一 ⇒ 传 `{"steps"}` 后仅后者留 |
| 缺省逐字（回归锚） | 不传 ⇒ 两条**皆留** |
| 交集语义 | 条目 `tags=["loop","steps","x"]` 仍被挡（**任一**命中即挡）；`tags=[]` 不挡 |
| `read()` 仍召回（回归锚） | 真 `MemoryStore` 写 `tags=["loop","steps"]` 条目 ⇒ `read()` 仍取回 |
| 组合根接线 | `build_runtime` 后主装配器 `_exclude_fact_tags == frozenset({"steps"})` **且** `_exclude_fact_sources == ("compaction",)` **且** 封存元组逐字不动 |

## 局限

1. **预算近似**：被挡条目在 `read()` 内已消耗事实面配额、本 change **不**回收（每轮至多一条 ⇒ 有界）。
2. **标签是自律声明**：`"steps"` 标签由 `loop` 写入侧赋予，无强制门禁；若将来有**别的**条目也打
   `"steps"` 标签而**应**进事实面，会被顺带挡掉（判据是**标签**，非条目身份）。
3. **不处理 notes 侧**：`observe_turn` 写回与 `loop.steps.*` 同源（皆 `_action_steps(ctx)`）却无对账 ——
   本 change 只处理事实注入面一侧；「同源一致性」不引入跨模块匹配（见 D6 结论）。
4. **`key_fact` vs 笔记结论**（②）**记为设计上非重复**：结构化实体面 vs 规范散文知识面，不引入匹配。
