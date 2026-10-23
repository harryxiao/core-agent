# Spec Delta — memory（0311 记忆指标与效果评测：P2-5）

## MODIFIED Requirements

### Requirement: 召回的多样性控制与注入统计

`MemoryStore.recall()` SHALL 返回 `RecallResult`（条目 + `matched_count` / `injected_count` /
`excluded_by_budget` / `excluded_by_diversity` / `minimum_budget` / `injected_tokens` /
`scores`）；`read()` SHALL 保持既有签名与返回类型，语义等价于 `recall(...).entries`。

检索管线 SHALL 在**排名之后、预算之前**施加两道多样性过滤（被滤条目不吃预算、不被复用强化，
且不改变排名顺序）：

- **近重复抑制**：`content_hash` 相同的条目只保留排名最高的一条；旧行哈希为空时按同口径现算。
  正文 `strip()` 为空者 SHALL NOT 参与近重复抑制。
- **同会话上限**：`session_id` 非空的条目，每个会话最多 3 条；`session_id == ""` 的全局条目
  不受该上限约束。调用方已用 `session_id` 参数收窄到单会话时 SHALL NOT 施加该上限
  （结果本就来自同一会话，施加上限只会截断该会话自身的事实面）。

统计口径：`matched_count` 为通过既有硬过滤后进入排名的候选数；`injected_count` 为最终返回数；
`excluded_by_budget` 为预算截断跳过数；`excluded_by_diversity` 为多样性过滤剔除数；
SHALL 满足 `matched_count == injected_count + excluded_by_diversity + excluded_by_budget`。
`minimum_budget` 为再注入第一条被预算跳过条目所需的最小预算（无预算剔除 ⇒ 0）。

`injected_tokens` SHALL 为本次注入条目的 token 估算总和（口径与预算截断相同；空结果 ⇒ 0）。
`scores` SHALL 与 `entries` **等长同序**，元素为该条目的相关度分值（排序所用同一分值的
快照）；空结果 ⇒ 空列表。`scores` 的尺度随排序后端（语义 / 词法降级）变化，SHALL NOT 被
解释为跨运行可比较的绝对质量。

`recall()` 与 `read()` SHALL 接受关键字 `reinforce: bool = True`：为 `False` 时 SHALL NOT
自增 `reuse_count`、SHALL NOT 写回条目、SHALL NOT 记复用效应（诊断面「只看不强化」）；
缺省 `True` SHALL 与既往语义逐字一致。

本要求 SHALL NOT 引入 kind 配额（`MemoryEntry.kind` 无 procedural 类）或 `source` 级上限
（本仓 `source` 为粗粒度管道标签，按它限流会饿死关键事实）。

#### Scenario: 同会话最多三条

- **GIVEN** 同一 `session_id` 的 4 条命中条目与另一会话的 1 条命中条目
- **WHEN** 以缺省参数 `read()` 检索
- **THEN** 该会话最多返回 3 条；另一会话的条目不受影响

#### Scenario: 会话收窄时不施加上限

- **GIVEN** 同一 `session_id` 的 4 条命中条目
- **WHEN** 以该 `session_id` 为参数 `recall()`
- **THEN** 4 条均可返回，`excluded_by_diversity == 0`

#### Scenario: 全局条目不受会话上限

- **GIVEN** 5 条 `session_id == ""` 的关键事实均命中查询
- **WHEN** `read()` 检索
- **THEN** 5 条均可返回（仅受预算约束）

#### Scenario: 近重复只留最高分

- **GIVEN** 两条正文完全相同（或仅首尾空白不同）的条目与一条不同正文的条目
- **WHEN** `recall()` 检索
- **THEN** 同文条目只返回排名最高的一条，`excluded_by_diversity >= 1`

#### Scenario: 注入统计可返回

- **GIVEN** 命中条目数超过给定预算
- **WHEN** 调用 `recall(..., budget=小值)`
- **THEN** `matched_count == injected_count + excluded_by_diversity + excluded_by_budget`，
  `excluded_by_budget > 0`，`minimum_budget > 0`

#### Scenario: 注入 token 与分值可返回

- **GIVEN** 一次命中若干条目的检索
- **WHEN** 调用 `recall()`
- **THEN** `injected_tokens == 0` 当且仅当 `injected_count == 0`；
  `len(scores) == len(entries)`，且分值按条目返回顺序**非增**

#### Scenario: 诊断检索零强化

- **GIVEN** 一条会被命中的条目，其 `reuse_count` 为 0
- **WHEN** 调用 `recall(..., reinforce=False)`
- **THEN** 返回结果与缺省检索相同，但该条目 `reuse_count` 仍为 0、无写回、无复用效应

#### Scenario: read 兼容

- **GIVEN** 任意检索参数
- **WHEN** 分别调用 `read(...)` 与 `recall(...)`
- **THEN** `read()` 返回的对象与 `recall().entries` 逐条相同（同一列表内容）

## ADDED Requirements

### Requirement: 记忆运行指标快照

`MemoryStore` SHALL 提供 `metrics_snapshot() -> dict[str, float]`，返回**存储实例作用域**的
累计指标（生产运行时一个进程一个实例；不落盘、不跨实例共享；键名与 SDD §11.1 对齐）：

- `memory.writes.<kind>`：成功落库的写入数，按条目 `kind` 分组（`kind` 规范化：小写化、
  非 `[a-z0-9_]` 替换为 `_`、空值记为 `unknown`）；
- `memory.writes.deduped`：幂等重放快路径命中数；
- `memory.writes.rejected`：重要度闸门拒收数；
- `memory.recall.calls` / `memory.recall.candidates` / `memory.recall.injected` /
  `memory.recall.injected_tokens` / `memory.recall.excluded_by_budget` /
  `memory.recall.excluded_by_diversity`；
- `memory.consolidation.runs` / `memory.consolidation.failures` /
  `memory.consolidation.elapsed_ms`。

固定键 SHALL 在快照中**始终存在**（未发生时值为 0）；`memory.writes.<kind>` 只在对应 kind
发生写入后出现。快照 SHALL 为零 I/O、零写回、零效应，SHALL NOT 包含条目正文、查询文本、
session / trace 标识。实例销毁后计数 SHALL 消失（SHALL NOT 宣称跨实例或跨进程持久）。

`read()` 委托 `recall()` SHALL 计入 recall 指标；存储内部为巩固决策打分等发起的检索
SHALL NOT 计入（避免虚增注入统计）。`consolidation.runs` SHALL 只在压实**实际执行**时计数
（开关关闭 / 并发跳过不计）；执行抛错 SHALL 计入 `failures` 后照常向上抛出；`elapsed_ms`
SHALL 以注入的单调钟测量并累计为整数毫秒。

#### Scenario: 写入与重放计数

- **GIVEN** 一个新存储
- **WHEN** 成功写入 2 条 `episodic`、重放其中 1 条（同层同 id 同载荷）、再被闸门拒收 1 条
- **THEN** 快照含 `memory.writes.episodic == 2`、`memory.writes.deduped == 1`、
  `memory.writes.rejected == 1`

#### Scenario: 召回统计累计

- **GIVEN** 两次 `read()` 检索（其中一次预算截断）
- **WHEN** 读取指标快照
- **THEN** `memory.recall.calls == 2`，`candidates` / `injected` / `injected_tokens` /
  `excluded_by_budget` 为两次检索之和，且 `candidates == injected + 两类剔除`

#### Scenario: 内部打分读不计入

- **GIVEN** 一个注入了 compactor 的存储，且从未被外部检索
- **WHEN** 调用 `compact()`（内部为打分执行一次检索）
- **THEN** `memory.recall.calls == 0`

#### Scenario: 巩固耗时与失败

- **GIVEN** 注入单调钟与抛错的摘要器
- **WHEN** 调用 `compact()` 并捕获异常
- **THEN** `memory.consolidation.runs == 1`、`failures == 1`、`elapsed_ms` 为时钟差值

### Requirement: 记忆运维统计（memory stats）

CLI SHALL 提供 `memory stats [--json]`：**只读**聚合既有持久数据，SHALL NOT 触发复用强化、
SHALL NOT 写入任何状态。统计 SHALL 覆盖：

- `storage_bytes`：`$CORE_STATE_DIR/memory.jsonl` 的文件字节数（文件缺失 ⇒ 0）；
- 条目面（`audit(None)` 全量）：`entries_total` / `entries_active` / `entries_retracted` /
  `entries_superseded` / `entries_forgotten`，`by_layer`（仅 active）与 `by_status`（全量）；
- `content_bytes`：active 条目正文 UTF-8 字节总和；
- 审计面（`memory.audit.jsonl`，坏行跳过、文件缺失 ⇒ 空）：`writes_by_kind`（`op="write"`）、
  `deletes_by_reason`（`op="delete"`）、`forgets_by_reason`（`op="forget"`）、
  `exports`（`op="export"` 计数）。

`--json` SHALL 输出固定键的 JSON 对象；映射字段 SHALL 按 key 排序以稳定输出。文本模式 SHALL
输出可逐行处理的摘要（含存储字节、条目数、层分布、写入分布、治理计数）。输出 SHALL NOT
包含条目正文、查询文本或密钥明文。空库 / 缺文件 SHALL 正常输出全 0 统计并以 0 退出。

#### Scenario: 全量聚合

- **GIVEN** 库内有 active / 墓碑 / 被取代条目，审计日志含写入、删除、遗忘与导出事件
- **WHEN** 执行 `memory stats --json`
- **THEN** 各计数与条目状态、审计事件一致；`storage_bytes` 等于 `memory.jsonl` 大小；
  输出不含任何正文

#### Scenario: 零强化

- **GIVEN** 库内有可被任意查询命中的条目，`reuse_count` 为 0
- **WHEN** 执行 `memory stats`
- **THEN** 所有条目 `reuse_count` 不变、无新审计写入事件

#### Scenario: 空库降级

- **GIVEN** 记忆文件与审计文件均不存在
- **WHEN** 执行 `memory stats --json`
- **THEN** 输出全 0 统计，退出码 0，不创建任何文件

### Requirement: 召回解释（memory why）

CLI SHALL 提供 `memory why <query> [--budget N] [--session S]`：执行一次**零强化**检索
（`reinforce=False`）并输出：

- 统计行：`matched` / `injected` / `excluded_by_diversity` / `excluded_by_budget` /
  `minimum_budget` / `injected_tokens`；
- 注入条目行：按相关度降序，含排名、分值、层、kind、source、session、id、importance、
  `reuse_count` 与**脱敏后**的单行内容摘要。

`--budget` 缺省 SHALL 为 4096（与 `read()` 缺省一致）；`--session` SHALL 透传会话过滤。
输出 SHALL NOT 包含未脱敏正文或密钥明文。无命中时 SHALL 只输出统计行并以 0 退出。
执行 SHALL NOT 修改任何条目、SHALL NOT 产生复用效应。

#### Scenario: 统计与条目序

- **GIVEN** 库内 3 条命中条目、预算足以全部注入
- **WHEN** 执行 `memory why <query>`
- **THEN** 统计行 `matched == injected == 3`，条目行按分值非增排列

#### Scenario: 内容脱敏

- **GIVEN** 命中条目正文含密钥形态字符串
- **WHEN** 执行 `memory why <query>`
- **THEN** 输出中密钥已被脱敏替换，不出现明文

#### Scenario: 零强化

- **GIVEN** 命中条目 `reuse_count == 0`
- **WHEN** 执行 `memory why <query>`
- **THEN** 执行后该条目 `reuse_count` 仍为 0，且无写回效应

#### Scenario: 无命中

- **GIVEN** 空库
- **WHEN** 执行 `memory why <query>`
- **THEN** 只输出统计行（全 0），退出码 0

### Requirement: 记忆效果离线评测（有 / 无记忆回放）

系统 SHALL 提供离线、确定性的记忆效果评测：以固定任务集（问题 + gold 答案 + gold 事实 +
干扰事实）回放两臂 —— **有记忆**（库内灌入 gold 事实）与 **无记忆**（空库），两臂 SHALL
使用**同一**真实链路（`DefaultLoop` + `LLMPlanner` + `DynamicAssembler`）与桩 provider，
SHALL NOT 访问网络或真实模型。

评测 SHALL 度量并报告：任务成功率（最终回复命中 gold 答案的比例）、prompt token、轮数、
墙钟耗时。成功判据 SHALL 只依赖确定性输出；墙钟 SHALL 仅报告、SHALL NOT 作为门禁（机器
噪声）。评测 SHALL 断言：有记忆成功率 ≥ 0.9；有记忆成功率**严格高于**无记忆；有记忆的
prompt token 大于无记忆（证明事实确实进入提示词）。

#### Scenario: 有记忆显著提升成功率

- **GIVEN** 固定任务集与桩 provider（仅当提示词含 gold 事实时才答对）
- **WHEN** 分别以有记忆 / 无记忆两臂回放
- **THEN** 有记忆成功率 ≥ 0.9 且严格高于无记忆

#### Scenario: 评测确定性

- **GIVEN** 同一任务集
- **WHEN** 连续两次独立回放
- **THEN** 两臂的成功判定与 prompt token 完全一致（无时钟 / 随机 / 网络依赖）
