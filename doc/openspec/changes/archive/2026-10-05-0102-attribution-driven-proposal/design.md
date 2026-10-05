# 设计 — 归因驱动提案与结晶语义诚实化（change 0102）

## 0. 一句话

change `0101` 把**模块归因证据**送进了 `Diagnoser`；本 change 让这份归因**一路走到提案与结局**——
`kind` 不再在构造期写死，架构级结晶不再谎报 `published`。

## 1. 决策：`kind` 由**归因**驱动，而不是继续静态缺省

**问题**：`Proposer(kind="skill")` 的缺省值在组合根被无参调用（`runtime.py:450`），
「提案的类型」与「诊断说谁坏了」**完全解耦** —— 归因到 `loop.default`（架构模块）也产出技能级候选。

**备选**：

| 方案 | 评价 |
|---|---|
| (i) 组合根改成 `Proposer(kind="plugin")` | **错得更远**：所有候选一律架构级、`risk_level` 恒 `high` ⇒ 技能级缺陷被迫走审批单门 |
| (ii) 在 `run_cycle` 里按 `DiagnosisReport` 事后改写 `candidate.kind` | **两份真源**：`GenerationCandidate.kind` 由 `Proposer` 按契约产出（规格「模块级提案」），事后改写让「谁决定 kind」在代码里分裂成两处 |
| **(iii) `Proposer` 缺省按 `target_plugin` 归因判定（采纳）** | kind 的判定**收在提案器单一位置**，且判定依据正是诊断的归因结果 —— 契约（`propose(diagnosis) -> GenerationCandidate`）不变 |

**采纳 (iii)**：`kind: ... | None = None`，`None` ⇒ `target_plugin in INTERNAL_PLUGIN_IDS`。
**显式值仍覆盖归因**——保留给「专用装配 / 测试想固定 kind」的场景，且这是**既有 13 处
`Proposer(kind=…)` 调用逐字不变**的前提（改缺省而不是改签名）。

**为何「白名单」而非「前缀启发式」**：`plugin_id` 的命名空间有两套（工具 id `tools.*` 与内部
核心模块 id），二者**永不相交**（phase-21 §5.2 已核）。用前缀猜（如 `startswith("evolution.")`）
会同时漏掉 `loop.default` / `memory.store` / `im.gateway` / `composition.*`。**枚举白名单**是
唯一能把「13 个内部核心模块」这一事实**在单一位置**钉住的形态；由 `src/core/evolution/` 内的
常量承载（`Proposer` 与它同包，无跨层依赖）。

**为何常量落在 `evolution` 而非 `runtime`/`observability`**：消费方是 `Proposer`（提案器），
`observability` 只提供 `TraceEvent.module_id` 这个**字段**，不认识模块名单（与 `ConfigManager`
不认识 `GATABLE_MODULES` 同型 —— 名单归**声明方**，不归**载体**）。

## 2. 决策：架构级结晶结局为 `accepted`，而非 `published`

**事实**：`_crystallize_plugin` 唯一副作用是**写一条 L3 记忆**。没有架构产物被发布，
没有世代被晋升（E31：13 个内部模块根本不在 `PluginRegistry` 内）。

**备选**：

| 方案 | 评价 |
|---|---|
| (i) 保持 `published`，只在文档里说明「发布=登记」 | **不改谎报**：`published` 在词表里与技能分支共用，读者无法区分「真发布了」与「只登记了」 |
| (ii) 让 `_crystallize_plugin` 返回 `pending` / `confirmed` | **语义撞车**：`pending`/`confirmed` 已是**候选状态**词（`GenerationCandidate.status`），且 `confirmed` 在结晶**之前**就已成立 ⇒ 结局失去信息量 |
| **(iii) 新词 `accepted`（「已批准、待人工实施」）（采纳）** | 断言**比 `published` 更弱**且**恰好等于**实际发生的事（批准 + 留痕 + 开观察期）；技能分支语义不变 |

**采纳 (iii)**。`EvolutionOutcome.status` 词表 `+ accepted`；`models.py` 注释同步。
**人工门不放宽**：`accepted` **不是**「自动发布了」，恰恰相反 —— 它明示「需要人去做架构侧的事」。

**L3 留痕与观察期开窗保不保**：**保**。二者与「是否有产物」无关 —— 留痕是**审计轨迹**，
开窗是**基线对比**（`crystallize` 内 `observations.open(...)`，`engine.py:178`），
架构级与技能级都需要（回归判的是「批准之后系统是否变差」）。

## 3. 决策：`accepted` **不**回灌进 `run_cycle` 的结局

`run_cycle` 的结局序列（`manual` / `rejected` / `rollback` / `pending` / `no_evidence`）**不动**：
`accepted` 只在 `crystallize`（人工确认之后）出现。理由：`run_cycle` 是**提案侧**（输出候选），
`crystallize` 是**发布侧**（消费已确认候选）—— 把发布侧词表混进提案侧会让「未确认」与「已批准」
在同一函数的不同返回点长得一样，正是本 change 要消除的混淆。

**红线守护**：`run_cycle`/`maybe_run` 缺省 `status="pending"`；测试断言
「未 `confirm` ⇒ 无 `accepted` 结局」（`CANDIDATE_PENDING` 逻辑一字不动）。

## 4. 验证策略（离线、不出网）

- **单元**：`Proposer()` 对白名单 id / 非白名单 id / 显式覆盖三分支；
  `INTERNAL_PLUGIN_IDS` 与仓内 `plugin_id = "..."` 声明集**逐元素一致**（防白名单漂移）。
- **端到端（引擎内，不启 runtime）**：
  模块归因失败 trace → `run_cycle` 得 `pending` + `kind=="plugin"` → 签审批单 `confirm`
  → `crystallize` 得 **`accepted`**（而非 `published`）；技能分支对照得 `published`。
- **反向守护**：未确认候选 `crystallize` 仍抛 `CANDIDATE_PENDING`。
- **CLI 文案**：`entry._evolve_confirm` 对架构级候选举 `accepted` 时不再打印「已确认并发布」。

## 5. 已知边界（写进 ADR）

- 本 change **不**让架构级候选产生任何可部署产物 —— `accepted` 明示「待人工实施」，
  「实施」这一环**至今不存在**（无架构补丁应用器）；其账本化见 E31。
- `INTERNAL_PLUGIN_IDS` 是**枚举**：新增内部核心模块须同步登记（有逐元素一致性用例守护，
  但仍是一次手工动作）。若将来内部模块纳入 `PluginRegistry`（E31），此白名单可由注册表派生。
