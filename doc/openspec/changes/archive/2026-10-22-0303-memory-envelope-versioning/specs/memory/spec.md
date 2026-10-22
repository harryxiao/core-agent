# memory — 条目治理信封与关键事实版本链（change 0303）

## ADDED Requirements

### Requirement: 记忆条目的治理信封

每条记忆条目 SHALL 携带治理信封字段，缺省值保证旧数据与既有构造点**逐字兼容**：

- `content_hash`：正文 `strip()` 后的 SHA-256（十六进制）。写入路径 SHALL 在字段为空时自动计算；
  调用方显式给值 SHALL 被尊重。该字段只服务幂等比较 / 内容寻址，SHALL NOT 参与排序打分。
- `status`：`"active"`（缺省）或 `"superseded"`。
- `version`：版本号，缺省 `1`，同链递增。
- `parent_id`：被本版本替代的条目 id；首版为空串。
- `superseded_by`：仅旧版本填写，指向替代它的新版本 id。

反序列化 SHALL 对缺键的旧行应用默认值（`active` / `1` / 空串）。检索面 `read()` SHALL 在
**排名与预算之前**剔除 `status != "active"` 的条目（与遗忘 / 层过滤同一位置 ⇒ 不吃预算、
不被复用强化）；`audit()` / `index()` / `_all_entries()` SHALL NOT 施加该过滤（历史可追溯）。
本条 SHALL NOT 引入 `namespace` / `trust` / `confidence`（当前无消费方）。

#### Scenario: 旧行缺键 ⇒ 默认值加载
- **GIVEN** `memory.jsonl` 中某行为变更前写入（无治理字段）
- **WHEN** `FileBackend` 重新加载
- **THEN** 条目 `status="active"`、`version=1`、`parent_id=""`、`superseded_by=""`，
  `content_hash` 为空串，且其检索可见性与变更前一致

#### Scenario: 写入自动计算内容哈希
- **GIVEN** 调用方写入条目时未提供 `content_hash`
- **WHEN** 写入完成
- **THEN** 条目 `content_hash == sha256(content.strip())`（正文仅差首尾空白 ⇒ 哈希相同）

#### Scenario: 检索默认排除 superseded
- **GIVEN** 同一实体的两个版本：旧版 `status="superseded"`、新版 `status="active"`
- **WHEN** 以缺省参数 `read()` 检索
- **THEN** 只返回新版；旧版不占预算、`reuse_count` 不递增

#### Scenario: 审计面保留历史版本
- **GIVEN** 同一实体存在 `superseded` 旧版与 `active` 新版
- **WHEN** 调用 `audit()`
- **THEN** 两个版本都返回，旧版 `superseded_by` 指向新版


## MODIFIED Requirements

### Requirement: 结构化实体抽取（关键事实）

系统 SHALL 提供**结构化关键事实抽取**：在记忆压实时，从**被聚合的 episodic 条目**中抽取
「实体 → 取值」事实，落为 `kind="semantic"` 的记忆条目。抽取器 SHALL 经**依赖注入**交付
（`MemoryStore` 构造形参 `key_fact_extractor`，契约
`KeyFactExtractor = Callable[[list[MemoryEntry]], list[KeyFact]]`；缺省 UNWIRED）—— 与
`summarizer` / `embedder` 同一依赖方向：memory SHALL NOT import 任何 LLM / rag 抽象，模型调用由
L5 组合根注入。抽取材料 SHALL 是**本次压实聚合的 episodic 条目**（即「行动与结果」产生的事件），
承「无行动不记忆」。
承载本轮**行动与结果**序列的那条 L2 条目，其**内容口径**（有界、写入前脱敏）由 `loop`「执行循环」规定 —— 本能力只消费该材料，不另行定义其形态。

落库形态 SHALL 为：首版 `id = f"keyfact.{实体 slug}"`；同实体**取值变化**时 SHALL 新增
版本条目 `id = f"keyfact.{实体 slug}.v{version}"`（`version` 自 1 起递增、`parent_id` 指向被替代
的旧版），旧版 SHALL 置 `status="superseded"` 且 `superseded_by` 指向新版本（**版本链**，见
「记忆条目的治理信封」；SHALL NOT 原地覆盖 ⇒ 旧值仍可经 `audit()` 追溯）；同实体**取值未变**
⇒ SHALL 在活跃版本上就地刷新溯源（幂等，条目不增长、版本不升）；`kind="semantic"`；`source="extraction"`（短标签）；`trace_id` 与压实同
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

抽取 prompt 的条数要求 SHALL 与本次落库名额**同源**：注入的抽取器在未显式覆盖名额时，SHALL 按
**本次调用**聚合的 episodic 条数计算 `cap(n)` 并写入 prompt；SHALL NOT 固定为下限死值。

#### Scenario: 上限随会话长度自适应
- **GIVEN** 两次压实分别聚合 20 条与 200 条 episodic 条目
- **WHEN** keyfact 抽取落库
- **THEN** 两次压实的条数上界按 `cap(n)` 分别计算，长会话的上界不低于短会话，且均落在
  `[KEY_FACTS_MIN, KEY_FACTS_MAX]` 区间

#### Scenario: 自适应上限不低于既有死值
- **GIVEN** 任意聚合条数 n ≥ 0
- **WHEN** 计算 cap(n)
- **THEN** cap(n) ≥ 既有固定上界 `MAX_KEY_FACTS_PER_COMPACT` 的原取值（宽松化而非收紧）

未注入抽取器**或配置关闭**（`memory.key_fact_extract` = false）⇒ SHALL NOT 抽取，压实行为
（摘要写回、条目迁移、评分）**逐字不变**。配置键 `memory.key_fact_extract` SHALL 为**组合根接线闸**——
缺省 **true**（保留既有行为，不得静默停用在用能力）；显式关闭时组合根 SHALL **不**注入
`key_fact_extractor`。该键 SHALL 只决定**是否接线**，SHALL NOT 改变本条其余任何落库/脱敏/有界判据。

#### Scenario: 抽取 prompt 名额随聚合条数自适应
- **GIVEN** 注入缺省抽取器（未显式覆盖名额）
- **WHEN** 分别对 20 条与 200 条 episodic 条目构建抽取 prompt
- **THEN** 前者要求的名额 SHALL 等于 `cap(20)`（= `KEY_FACTS_MIN`），后者 SHALL 等于
  `cap(200)`（= `KEY_FACTS_MAX`）—— prompt 名额与落库名额同源

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
  再次压实同一实体**且取值未变** **THEN** 仍为**单条**（同 `id` 就地刷新，条目不增长）；
  **AND WHEN** 取值已变 **THEN** 新增 `keyfact.<slug>.v2` 版本条目，旧版 `status="superseded"`、
  `superseded_by` 指向新版（版本链，不覆盖）

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

#### Scenario: 配置关闭 ⇒ 不接线、压实逐字不变
- **GIVEN** `memory.key_fact_extract` 显式置 **false**
- **WHEN** 组合根装配 `MemoryStore`
- **THEN** **不**注入 `key_fact_extractor`（`None`）⇒ 不产出任何 `key_fact` 条目，摘要写回 /
  条目迁移 / 评分与**未引入该键时**逐字一致

#### Scenario: 门控缺省开 ⇒ 保留既有抽取
- **GIVEN** **未**显式配置 `memory.key_fact_extract`（缺省）
- **WHEN** 组合根装配 `MemoryStore`
- **THEN** 照常注入抽取器 ⇒ 关键事实抽取行为与引入该键前**逐字一致**（缺省不改变在用能力）

#### Scenario: 取值变化 ⇒ 新增版本、旧值可追溯

- **GIVEN** 某实体的关键事实已落库为首版 `keyfact.<slug>`（`version=1`、`status="active"`）
- **WHEN** 后续压实抽到同一实体但取值不同
- **THEN** 新增 `keyfact.<slug>.v2`（`version=2`、`parent_id` 指向首版、`status="active"`），首版置
  `status="superseded"`、`superseded_by="keyfact.<slug>.v2"`；**AND** 缺省检索只返回 v2，
  `audit()` 同时可见两版且旧版可直接读取（旧值未被销毁）

### Requirement: 关键事实的跨压实合并

跨压实批次重复抽取同一实体时，关键事实 SHALL 按实体 slug 维护**版本链**：
**取值未变** ⇒ 在活跃版本上**就地刷新**溯源（`trace_id` / `tags` 随本次压实刷新）；
**取值变化** ⇒ SHALL **新增版本条目**（`id = f"keyfact.{slug}.v{version}"`、`version` 递增、
`parent_id` 指向旧版），旧版 SHALL 置 `status="superseded"` 且 `superseded_by` 指向新版，
SHALL NOT 原地覆盖。任一版本条目的**首次出现时间戳**（`ts`）SHALL 在后续同版本就地刷新时保留；
新版本获得自己的写入时间戳（旧版时间戳不随之改写）。缺省检索 SHALL 只见 `status="active"`
的链头（旧版本经 `audit()` 追溯）；取代动作 SHALL 记可撤销效应并随同一
`compaction.<session_id>` trace 回滚（回滚新版 ⇒ 旧版恢复 active）。同批归并语义
（同批同 slug 只留首条）SHALL 保持不变。

#### Scenario: 跨压实同实体合并不新增条目
- **GIVEN** 两个压实批次抽取到同一实体、**相同取值**
- **WHEN** 第二批压实落库
- **THEN** 仍只有一条 `keyfact.<slug>` 条目（版本不变），`trace_id` / `tags` 刷新为第二批溯源

#### Scenario: 跨压实取值变化新增版本
- **GIVEN** 某实体的关键事实已在第一批压实落库（`version=1`）
- **WHEN** 第二批压实抽到**不同取值**
- **THEN** 新增 `keyfact.<slug>.v2`；首版 `status="superseded"`、`superseded_by` 指向 v2；
  **AND** 缺省检索只返回 v2，`audit()` 两版俱在

#### Scenario: 跨压实更新保留首见时间戳
- **GIVEN** 某实体的关键事实已在第一批压实落库
- **WHEN** 第二批压实抽到**相同取值**并就地刷新
- **THEN** 条目 `ts` 仍等于首次落库时间，未被重置为第二批写入时间

#### Scenario: 版本链可回滚
- **GIVEN** 第二批压实产生了 `keyfact.<slug>.v2` 并取代了首版
- **WHEN** 回滚第二批压实的 `compaction.<session_id>` trace
- **THEN** v2 被删除、首版恢复 `status="active"`（旧值重新可召回）

