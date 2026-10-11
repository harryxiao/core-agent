# 模块设计：上下文工程（Context Engineering）

> 对应规格：`doc/openspec/specs/context/spec.md` ｜ 接口：`doc/03-interfaces/context-interface.md`
> 定位：**L2 记忆之上 / L3 输入侧**，解决长任务下信息过载、关键信息丢失的核心痛点。

---

## 1. 模块定位

上下文窗口是稀缺资源。全量塞入会让关键信息被淹没、token 爆表；什么都不塞又会遗忘关键约束。

本模块做**按需加载、信息地图、自动压实**三件事，保证"每次只把当前任务最需要的上下文装进窗口"。

---

## 2. 内部组成

```
ContextBuilder（L3 输入侧）
├── DynamicAssembler 动态上下文构建：按任务阶段按需加载
├── InfoMap          信息地图：轻量目录索引，按需跳转取细节
├── Compactor        上下文自动压实：多轮关键信息摘要沉淀
└── BudgetManager    token 预算：控制注入上界
```

---

## 3. 关键设计

### 3.1 动态上下文构建

- 根据当前任务阶段，**按需加载**对应领域文档、历史经验、规范要求，而非一次性全量塞入。
- 加载来源：MemoryStore 检索（L2 事实 / L3 技能）+ InfoMap 跳转 + 宪章/coeffect。
- 装配结果经 BudgetManager 控制 token 上界（可配置）。
- 调用方会话标识（`build(session_id=…)`）透传至 L2 事实检索 ⇒ 事实召回同样按会话隔离
  （change `0114`／ADR-0107）；缺省空串 ⇒ 不过滤，语义与既往逐字一致。
- 构造参数 `exclude_source_prefixes` / `allow_source_prefixes` 透传至同一次检索（排除面 + 其
  **例外面**，change `0117`／ADR-0110）；`with_allow_source_prefixes(*prefixes)` 派生**新**装配器
  （排除面逐字继承、放行面替换）—— 主 loop 与神兽共用一份配置，派生而非原地改（封存红线）。
- **事实面排除面** `exclude_fact_sources`（change `0185`／ADR-0176）：按 `MemoryEntry.source` **前缀**
  把「**已由专块注入**」的条目挡在「相关事实」注入面之外 —— 会话长期 / 中期摘要（`source="compaction"`）
  的正文已由「历史摘要（长期）/（中期）」专块每轮注入 ⇒ 不再重复进事实面（对齐 `notes`「同一份内容
  SHALL NOT 经两条通道重复注入」的同型纪律）。缺省空 ⇒ 逐字不变；过滤落在**读后** ⇒
  `MemoryStore.read` 的检索语义 / 排序 / 预算 / 复用强化**逐字不变**（`compaction.*` 条目对其他消费者仍
  可见）；与 `exclude_source_prefixes`（**封存**面）**不同理由、不合并**，封存元组字面不动。
  派生装配器 `with_allow_source_prefixes` **继承**本排除面（放行面是封存面的例外面，与之无关）。
- **事实面标签排除面** `exclude_fact_tags`（change `0186`／ADR-0177）：按 `MemoryEntry.tags` **交集**
  把**声明角色为素材**的条目挡在「相关事实」注入面之外 —— 本轮**原始行动序列**（`loop.steps.<trace_id>`，
  `tags` 含 `steps`）的声明角色是**抽取器素材**，其信息已由同轮轨迹（`loop.<trace_id>`）与（失败时）
  失败摘要（`loop.failure.<trace_id>`）承载 ⇒ 不再进 prompt。三个 `loop.*` 条目的 `source`
  **同为** `"loop"` ⇒ 来源面天然不可分（这正是 `exclude_fact_sources` 在此**够不着**的原因），
  故取 **tags** 轴（与 `memory._PRESERVE_TAGS` 同为标签面惯用法；装配面由此同时镜像 memory 的
  `_ARCHIVE_SOURCES` 来源面与 `_PRESERVE_TAGS` 标签面两条惯用法）。缺省空 ⇒ 逐字不变；过滤落**读后**
  ⇒ `read()` 语义逐字不变（**抽取器素材角色**不受影响）；派生装配器**继承**本排除面。

### 3.2 信息地图机制

- 把千页级业务文档转化为**轻量化目录索引**（章节/要点/位置指针），不把全文塞入窗口。
- 模型按需跳转获取细节：先用地图定位，再 fetch 对应片段。
- 地图更新策略：文档变更时增量重建（hash 比对）。

### 3.3 上下文自动压实

- 对多轮对话的关键信息自动摘要沉淀：已完成子任务的结论、关键决策、未决事项。
- 沉淀产物写回 MemoryStore（L2 事实 / L3 技能），避免重复传递冗余内容。
- 压实触发时机（change `0182`／ADR-0173 诚实化）：**本轮工具步数**达 `loop.compact_steps`（缺省 `6`）
  **或** token 用量达 token 预算。工具步数是本轮内已记账的工具动作步数（`LoopContext.rounds`，
  每用户轮自 `0` 起算，**非**对话轮数）⇒ 阈值须小于 `loop.max_rounds` 才可能提前触发。
  压实**每轮至多触发一次**（守卫在 `DefaultLoop.astream` 的本轮标记）。
- 阈值来源：`Compactor(step_threshold=…)` 由组合根按 `loop.compact_steps` 注入；未注入 ⇒ 模块缺省 `6`。
- 产物按**本轮会话**归属（`persist(session_id=…)`），条目 id 带会话键（缺省 `default`）
  ⇒ 跨会话不再同名覆盖（change `0114`／ADR-0107）；产物 `trace_id` 亦带会话键
  `compaction.<key>`（change `0192`／ADR-0182），与记忆侧其他压实 trace（会话摘要 / 关键事实 /
  中期摘要）**同口径** ⇒ 回滚按会话细化归因、与同会话其他压实产物共组；此前为**常量** `compaction`。
- 压实器输入是**本轮**消息 + 工具 I/O（`ctx.messages`），**非**多轮历史（多轮历史由三层滑窗
  `0178` 与记忆压实承载）：`Compactor.compact` docstring 自 change `0192` 起诚实化。`from:<id>`
  出处面为**死面**（本轮消息条目无 `id` ⇒ 恒不触发），**只注记不活化**。

### 3.4 三层窗口比例分配（change `0178`／ADR-0169）

- **策略纯函数**：`core.context.plan_window(history_turns, history_budget, *, tiered) -> WindowPlan`
  —— 只依赖 stdlib、**零 I/O、零模型调用**，把会话历史回灌的分层策略收敛为确定性配额。
- **份额**：短 `0.5` / 中 `0.3` / 长 `0.2`，为**模块常量**（本**配额分配面**不新增配置键，与
  `_STEP_THRESHOLD` / `MAX_SUMMARY_CHARS` 同纪律；压实**触发**阈值是另一面，自 change `0182` 起可经
  `loop.compact_steps` 配置）；`history_budget = token_budget // 2`（沿用既有 `_load_history` 口径）。
- **配额**：`short_turns` / `mid_turns` / `short_tokens`（短层 token 上界）/ `mid_chars`（中层摘要字符上界）；
  clamp —— 轮数或预算非正 ⇒ **全零**（关闭回灌）；非分层 ⇒ 「短层 = 全部 `history_turns` + 全部预算、中层零」，
  与既有双重上界**逐字等价**；分层时 `short ≥ 1`、`short + mid ≤ history_turns`、配额随总量**单调不减**。
- **LLM 压缩不在此层新开调用点**：本模块只**分配**，摘要由记忆的压实通道统一产出（`summarize_slice`）。
- **两轴口径裁决（change `0200`／ADR-0190）**：**轮轴**（本节的 `history_turns`，跨轮分层，单位 =
  转录用户行）与**步轴**（§3.3 的 `LoopContext.rounds`，轮内压实触发）**不可互换、不可混算** ——
  `loop.compact_steps` **只**是步轴阈值，SHALL NOT 读作「对话第 N 轮开始压缩」一类的轮轴边界
  （因步轴每用户轮归零，「第 N 轮」在系统内**不可计算**）。外来蓝图
  （`memory-4-layer-architecture.md` §4.1）的字面 tier 边界 `0-5 / 6-20 / 21+` **不采纳**：其
  Tier 1/2/3 **映射到轮轴**（短/中/长三层已一一对应），采其**结构**弃其**数值** —— 字面边界会与
  本节**比率相对**的份额构成**第二套冲突边界**。要求：「压缩轴口径（轮 / 步两轴不可互换）」；
  守护：`tests/test_axis_units.py`。

---

## 4. 与记忆/约束的分工

| 层 | 职责 |
|---|---|
| MemoryStore（L2） | 存储与检索事实/技能 |
| ContextBuilder | 决定"这一轮装什么"（按需 + 预算） |
| Constraints.Compressor | 执行期清理无效信息 |
| Compactor（本模块） | 跨轮摘要沉淀（写回记忆） |

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| token 超预算 | 裁剪低相关度内容，优先保留宪章/未决事项/验收标准 |
| 地图索引失效 | 触发重建，期间降级为全文检索 |
| 压实产物质量差 | 校验关键信息不丢失，否则不替换原文 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/context-interface.md`
- 规格：`doc/openspec/specs/context/spec.md`
- 测试：`doc/04-testing/test-cases.md`（CTX 系列）
