# Memory Specification Delta — 记忆系统质量闭环

## ADDED Requirements

### Requirement: 写入侧重要度闸门（importance write gate）

系统 SHALL 支持注入 **importance scorer**（`MemoryStore` 构造形参，契约
`Callable[[MemoryEntry], float]`，返回 [0,1]）—— 与 `summarizer` / `embedder` /
`key_fact_extractor` 同一依赖方向：memory SHALL NOT import 任何 LLM / rag 抽象，评分器由
L5 组合根注入；**缺省 UNWIRED**。注入后，写入路径 SHALL 先评分再落库：

- 分值低于 `IMPORTANCE_FLOOR` 的条目 SHALL **拒绝入库**（不写、无效应记录、无条目产生），
  并 SHALL 经 `warnings.warn` 留痕（留痕 SHALL 含条目可识别摘要，SHALL NOT 泄露可能含密钥的正文全文）。
- 分值在 `IMPORTANCE_FLOOR` 与 `IMPORTANCE_AMBIT` 之间 ⇒ 条目 SHALL **降层写入 L4 归档层**
  （不拒收但降检索优先级），写入 SHALL 记可撤销效应。
- 分值不低于 `IMPORTANCE_AMBIT` ⇒ 条目按原意向层正常入库，且其 `importance` SHALL 被写为分值
  （写回 SHALL 记可撤销效应，与固化写回同口径）。
- 评分器抛错或返回界外值 ⇒ SHALL **降级放行**（不评分、不拒收、不降层，按原意向层写入），
  `warnings.warn` 留痕，SHALL NOT 牵连写入主流程。
- **未注入（缺省）⇒ 写入行为 SHALL 与现状逐字一致**：不评分、不拒收、不降层、不写 `importance`。

#### Scenario: 未注入评分器时写入不变
- **GIVEN** 未注入 importance scorer 的 `MemoryStore`
- **WHEN** 写入一条条目
- **THEN** 落库层与内容与既有行为逐字一致，无评分留痕、无额外效应

#### Scenario: 低分条目拒收
- **GIVEN** 注入了 scorer，其对该条目返回 0.1（低于 `IMPORTANCE_FLOOR`）
- **WHEN** 写入该条目
- **THEN** 条目不落库（`audit()` 无变化）、无效应记录，且 `warnings.warn` 留痕

#### Scenario: 中间分降层写入
- **GIVEN** 注入了 scorer，其返回 0.3（`IMPORTANCE_FLOOR` ≤ 分 < `IMPORTANCE_AMBIT`）
- **WHEN** 写入该条目
- **THEN** 条目落至 L4 归档层，且该写入可撤销（回滚即按原意向层恢复）

#### Scenario: 高分正常入库并写回分值
- **GIVEN** 注入了 scorer，其返回 0.8
- **WHEN** 写入该条目
- **THEN** 条目按原意向层入库，`importance` 被写为 0.8，且该写回可撤销

#### Scenario: 评分器抛错降级放行
- **GIVEN** 注入的 scorer 调用时抛错
- **WHEN** 写入一条条目
- **THEN** 条目按原意向层正常入库，`warnings.warn` 留痕，写入主流程不中断

## MODIFIED Requirements

### Requirement: 记忆遗忘（forgetting）

系统 SHALL 按衰减评分（新鲜度 × 复用频次 × 重要度）识别低价值记忆并**归档**：评分低于阈值的
**L2 episodic** 条目 SHALL 迁移到 L4 归档层（**不物理删除**、`audit` 可见、检索降权），且每条
迁移 SHALL 记录可逆效应（按 trace 回滚即迁回原层）。**新鲜度衰减 SHALL 被复用信号延缓**：
条目的 freshness 衰减 SHALL 以 `freshness ** (1 / (1 + log1p(reuse_count)))` 调制——`reuse_count`
为 0 时该调制 SHALL 退化为现状（零回归锚点），复用越多衰减越缓（检索命中反哺遗忘曲线）。semantic
条目、L0 元策略与 L3 技能 SHALL 不受遗忘影响；时间戳未知（`ts<=0`）的条目 SHALL 不被惩罚。遗忘
SHALL NOT 中断 Agent 主流程。遗忘 SHALL 由**维护节拍**驱动——循环收尾按维护间隔触发，或由显式
维护入口一次性触发——而非仅依赖压实旁路；节拍只决定"何时跑"，不改上述判据、归档去向与可撤销性。

#### Scenario: 低分条目归档
- **GIVEN** 一条陈旧且从未复用的 L2 episodic 条目
- **WHEN** 遗忘运行
- **THEN** 该条目迁至 L4 归档层，`audit` 仍可见，且返回其撤销句柄

#### Scenario: 复用延缓新鲜度衰减
- **GIVEN** 两条时间戳与 `importance` 相同的 L2 episodic 条目，其一 `reuse_count=3`、另一
  `reuse_count=0`，二者评分均接近遗忘阈值
- **WHEN** 遗忘运行
- **THEN** `reuse_count=0` 的条目被归档，`reuse_count=3` 的条目因衰减被延缓而评分高于阈值、
  层级保持不变

#### Scenario: 未复用条目衰减不变
- **GIVEN** 一条 `reuse_count=0` 的 L2 episodic 条目
- **WHEN** 遗忘运行
- **THEN** 其遗忘评分与引入复用调制前**逐字一致**（调制退化为恒等）

#### Scenario: 节拍驱动遗忘
- **GIVEN** 距上次记忆维护已达维护间隔（或经显式维护入口触发）
- **WHEN** 维护节拍运行
- **THEN** 执行一次遗忘：低价值 L2 episodic 归档、其余不受影响，且不中断 Agent 主流程

#### Scenario: 高价值条目不受影响
- **GIVEN** 一条 `importance` 高或 `reuse_count` 高的 L2 条目
- **WHEN** 遗忘运行
- **THEN** 其评分高于阈值，层级保持不变

#### Scenario: 提炼产物与元策略不被遗忘
- **GIVEN** L2 存在 `kind="semantic"` 条目，L0 存在人格条目，L3 存在技能条目
- **WHEN** 遗忘运行
- **THEN** 三者层级均不变（遗忘只作用于 L2 episodic）

#### Scenario: 遗忘可撤销
- **GIVEN** 某条目已被遗忘归档
- **WHEN** 按该条目的遗忘 trace 回滚效应
- **THEN** 条目迁回 L2 原层

### Requirement: 结构化实体抽取（关键事实）

系统 SHALL 提供**结构化关键事实抽取**：在记忆压实时，从**被聚合的 episodic 条目**中抽取
「实体 → 取值」事实，落为 `kind="semantic"` 的记忆条目。抽取器 SHALL 经**依赖注入**交付
（`MemoryStore` 构造形参 `key_fact_extractor`，契约
`KeyFactExtractor = Callable[[list[MemoryEntry]], list[KeyFact]]`；缺省 UNWIRED）—— 与
`summarizer` / `embedder` 同一依赖方向：memory SHALL NOT import 任何 LLM / rag 抽象，模型调用由
L5 组合根注入。抽取材料 SHALL 是**本次压实聚合的 episodic 条目**（即「行动与结果」产生的事件），
承「无行动不记忆」。
承载本轮**行动与结果**序列的那条 L2 条目，其**内容口径**（有界、写入前脱敏）由 `loop`「执行循环」规定 —— 本能力只消费该材料，不另行定义其形态。

落库形态 SHALL 为：`id = f"keyfact.{实体 slug}"`（**同一实体至多一条** —— 重复抽取得**覆盖式
更新**，条目不增长）；`kind="semantic"`；`source="extraction"`（短标签）；`trace_id` 与压实同
（`compaction.<session_id>`）；`tags` SHALL 含 `key_fact` 与 `entity:<slug>`，给出引用时 SHALL 另含
`ref:<ref>`；`content` SHALL 为 `<entity>: <value>`（`value` 已脱敏）；产生它的会话 SHALL 经 `tags` 的
`session:<sid>` 标注溯源（`sid` 非空时）。关键事实 SHALL 属**全局层**（条目 `session_id` SHALL 置
空串、**不**参与会话隔离）—— 实体事实是**跨会话**的长期知识，与 `notes` 「刻意知识不参与会话隔离」
同一取向；**会话归属只作溯源标注，不是隔离维度**。写入 SHALL 走既有唯一写路径
`MemoryStore.write()`（记可撤销效应）⇒ 按 `compaction.<session_id>` 回滚即与压实**一并**逆转。

**密钥红线（本能力的核心约束）**：取值 SHALL **只引用不读取、绝不进记忆**。

- `value` 命中**密钥形态**（已知令牌前缀族 / 长随机串 / `key[:=]value` 赋值式）⇒ SHALL **强制**
  置为字面量 `"<redacted>"`。
- 给出 `ref` 时 ⇒ `value` SHALL **一律**为 `"<redacted>"`（引用式：真实取值在使用时经
  `CoeffectResolver` 注入；**即便**原值不含密钥形态也不得留明文）。**`ref` SHALL 仅当形如
  `coeffect:<名称>` 时才算「给出引用」**；**非该形态**的 `ref`（含模型自造的说明性文字，
  如 `round 1` / `会话事件`）SHALL 视为**无引用** —— 弃用该 `ref`、SHALL NOT 落 `ref:` 标签，
  取值随即按**裸值**判据处理。这是**放宽**而非收紧：模型把「出处说明」当引用回填时，
  不得据此把正常取值抹成 `<redacted>`。
- **fail-closed**：`value` 被判为密钥形态**且无可用 `ref`** ⇒ 该条 SHALL **整条丢弃**（记不住引用
  就**不记**），并 SHALL 经 `warnings.warn` 留痕（留痕 SHALL 含实体名，SHALL NOT 含取值）。
  「无可用 `ref`」SHALL 含 `ref` 为空串**与** `ref` 呈**非** `coeffect:<名称>` 形态两种情形
  —— 自造的说明性引用**不能**为明文密钥背书。
- **抽取器不构成信任边界**：脱敏 SHALL 在**落库前**由 memory 侧**无条件**执行（对抽取器返回的
  每一条都跑）；抽取器抛错或返回**不可解析**的结果 ⇒ SHALL 降级为**不抽取**（`warnings.warn`
  留痕），SHALL NOT 牵连本次压实的摘要写回与条目迁移。「不可解析」SHALL 判为「**有输出但无 JSON
  数组**」（合法但 0 条 SHALL NOT 告警）；该留痕 SHALL NOT 含模型输出正文（可能含明文密钥）。
- 脱敏方向 SHALL 是 **over-redact**（拿不准即多脱敏，落在安全侧），SHALL NOT 出现「拿不准就保留
  明文」。

抽取 SHALL **有界**：单次压实抽取条数 SHALL 有界——上界 SHALL **随本次压实聚合的 episodic 条目数
自适应**：`cap(n) = clamp(ceil(n × KEY_FACTS_RATIO), KEY_FACTS_MIN, KEY_FACTS_MAX)`，且
`KEY_FACTS_MIN` SHALL NOT 低于既有固定上界 `MAX_KEY_FACTS_PER_COMPACT` 的原取值（任何会话长度下
名额 SHALL 不收紧——自适应只放宽）（**同一批**内实体
slug 相同者 SHALL **归并**为一条、**只留首条**落库，归并后条数计额；被归并者 SHALL 经
`warnings.warn` 留痕（留痕含实体名、SHALL NOT 含取值）—— 同批重复是**单次模型响应内的重复枚举**，
区别于跨压实的「重复抽取」，后者由同实体幂等覆盖处理）；`entity` / `value` 长度 SHALL 有界
（`_MAX_FACT_CHARS`），且 SHALL **先脱敏后截断**（截断不得使明文逃逸）；其中 `value` 超长时截断
SHALL **首尾保留**（头尾各半、中以 `…` 连接，总长 SHALL NOT 超过 `_MAX_FACT_CHARS`）。

#### Scenario: 上限随会话长度自适应
- **GIVEN** 两次压实分别聚合 20 条与 200 条 episodic 条目
- **WHEN** keyfact 抽取落库
- **THEN** 两次压实的条数上界按 `cap(n)` 分别计算，长会话的上界不低于短会话，且均落在
  `[KEY_FACTS_MIN, KEY_FACTS_MAX]` 区间

#### Scenario: 自适应上限不低于既有死值
- **GIVEN** 任意聚合条数 n ≥ 0
- **WHEN** 计算 cap(n)
- **THEN** cap(n) ≥ 既有固定上界 `MAX_KEY_FACTS_PER_COMPACT` 的原取值（宽松化而非收紧）

未注入抽取器（缺省）⇒ SHALL NOT 抽取，压实行为（摘要写回、条目迁移、评分）**逐字不变**。

#### Scenario: 未注入抽取器 ⇒ 零抽取、逐字不变
- **GIVEN** `MemoryStore` **未**注入 `key_fact_extractor`（缺省）
- **WHEN** 压实运行
- **THEN** 不产出任何 `key_fact` 条目，摘要写回 / 条目迁移 / 评分与变更前**逐字一致**

#### Scenario: 抽取落库 + 同实体幂等覆盖
- **GIVEN** 注入抽取器，对某会话事件返回两条事实（实体 X、实体 Y）
- **WHEN** 压实该会话
- **THEN** 产出两条 `kind="semantic"` 条目（`source="extraction"`、`tags` 含 `key_fact` 与
  `entity:<slug>`、`trace_id=compaction.<sid>`、`content` 为 `<entity>: <value>`）；条目 `session_id`
  为**空串**（全局层，不参与会话隔离）而 `tags` 含 `session:<sid>`（溯源标注）；**AND WHEN**
  再次压实同一实体且取值已变 **THEN** 仍为**单条**（同 `id` 覆盖式更新，条目不增长）

#### Scenario: 明文密钥强制脱敏
- **GIVEN** 抽取器返回的事实其 `value` 为明文密钥（已知前缀族如 `sk-…`，或长随机串）
- **WHEN** 该事实落库
- **THEN** 落库 `content` **不含**该明文（`value` 为 `"<redacted>"`）——**AND GIVEN** 原值同时给出
  `ref` **THEN** 条目照常落库（`tags` 含 `ref:<ref>`），取值仍为 `"<redacted>"`

#### Scenario: 引用式取值一律脱敏
- **GIVEN** 抽取器返回的事实给出了 `ref`，但其 `value` 是一段**看起来正常**的文本
- **WHEN** 该事实落库
- **THEN** `value` SHALL 为 `"<redacted>"`（有引用即不得留明文），`ref` 进入 `tags`

#### Scenario: fail-closed —— 裸密钥无引用则整条丢弃
- **GIVEN** 抽取器返回的事实其 `value` 是密钥形态**且** `ref` 为空 / 不可用
- **WHEN** 该事实落库
- **THEN** 该条**不落库**（无 `keyfact.*` 条目），且经 `warnings.warn` 留痕（留痕含实体名、
  **不含**取值）；同批**其余**合规事实 SHALL 照常落库

#### Scenario: 抽取器抛错或返回不可解析 ⇒ 降级不抽取
- **GIVEN** 注入的抽取器在调用时抛错，**或**返回不可解析的结果
- **WHEN** 压实运行
- **THEN** 不产出 `key_fact` 条目、经 `warnings.warn` 留痕；摘要条目**仍**写回、原条目**仍**迁 L4
  （压实不中断）

#### Scenario: 关键事实条目随压实一并可撤销
- **GIVEN** 已按会话完成带抽取的压实
- **WHEN** 按 `compaction.<session_id>` 回滚效应
- **THEN** 关键事实条目与摘要条目一并被移除、被聚合的原始条目迁回原层

#### Scenario: 条数与长度有界（先脱敏后截断）
- **GIVEN** 抽取器一次返回超过上界条数的事实，且其中一条取值超长
- **WHEN** 压实运行
- **THEN** 单次落库条数不超过本次 `cap(n)`（`n` 为本次压实聚合的 episodic 条数），
  `entity` / `value` 长度不超过 `_MAX_FACT_CHARS`；**AND** 超长取值在**脱敏之后**才被截断
  （截断产物 SHALL NOT 使明文逃逸）

#### Scenario: 同批同 slug 归并（只留首条 + 留痕）
- **GIVEN** 抽取器**单次**返回两条事实，其实体不同但 slug 相同（如 `API Key` 与 `api-key`），
  **或**两次返回同一实体的**不同取值**
- **WHEN** 压实运行
- **THEN** 落库为**单条** `keyfact.<slug>` 条目，其取值为**首条**的取值；**AND** 被归并者经
  `warnings.warn` 留痕（留痕含实体名、**不含**取值）；**AND** 归并后条数计额（不重复占用本次
  `cap(n)` 名额）

#### Scenario: 解析失败留痕且不含模型输出正文
- **GIVEN** 抽取器返回的文本**非空**但**不含**可解析的 JSON 数组（如「解释文字 + 代码围栏」形态）
- **WHEN** 压实运行
- **THEN** 不产出 `key_fact` 条目，且经 `warnings.warn` 留痕；留痕 SHALL **不含**模型输出正文
  （只报失败事实与文本长度）；**AND GIVEN** 返回的是**合法空数组**（模型明确表示无可抽）
  **THEN** SHALL NOT 告警

#### Scenario: 取值超长 ⇒ 首尾保留（总额度不变）
- **GIVEN** 抽取器返回的事实其 `value` 超过 `_MAX_FACT_CHARS`
- **WHEN** 该事实落库
- **THEN** 落库 `value` 长度 SHALL NOT 超过 `_MAX_FACT_CHARS`，且**同时保留头部与尾部**
  （中以 `…` 连接）—— 而非只留头部

#### Scenario: 非 coeffect 形态的 ref 视为无引用
- **GIVEN** 抽取器返回的事实其 `value` 是一段**看起来正常**的文本，且给出了 `ref` 但**非**
  `coeffect:<名称>` 形态（如 `round 1` / `会话事件`）
- **WHEN** 该事实落库
- **THEN** `ref` 被**弃用**（不落 `ref:` 标签）、取值**按裸值判据**处理 —— **不因该 `ref` 被抹成**
  `<redacted>`（正常文本 SHALL 原样保留）；条目照常落库

#### Scenario: 非 coeffect 形态 ref + 密钥形态取值 ⇒ 整条丢弃
- **GIVEN** 抽取器返回的事实其 `value` 是**密钥形态**，且给出的 `ref` **非** `coeffect:<名称>` 形态
- **WHEN** 该事实落库
- **THEN** 该条 SHALL **不落库**（视同「无可用 `ref`」），并 SHALL 经 `warnings.warn` 留痕
  （含实体名、**不含**取值）；同批**其余**合规事实照常落库
