# Context Engineering Specification

## Purpose
上下文工程解决长任务下信息过载与关键信息丢失问题：按需加载、信息地图、自动压实三管齐下，保证每次只把当前任务最需要的上下文装进窗口。

## Requirements

### Requirement: 动态上下文构建
系统 SHALL 以**任务目标**为检索信号按需加载上下文（L2 事实检索以 task 为 query；stage 为装配阶段标注、
暂不参与事实选择），控制注入 token 上界，超预算裁剪低相关度内容。装配 SHALL 另接受可选的**调用方会话标识**
`session_id` 并**透传**至 L2 事实检索，作为该次检索的会话维度；标识缺省空串时，检索语义与既往**逐字一致**。

装配 SHALL 另支持**可选的事实面排除面** `exclude_fact_sources`（按 `MemoryEntry.source` **前缀**匹配；
缺省空 ⇒ **不含排除**、装配结果与既往**逐字一致**）：**已由专块注入**的压缩产物 SHALL NOT 再次进入
「相关事实」注入面 —— 会话长期 / 中期摘要（`source` 为 `compaction`）的正文 SHALL 只经「历史摘要（长期）」
/「历史摘要（中期）」专块承载，同一份内容 SHALL NOT 经两条通道重复注入同一次请求（对齐 `notes`「会话摘要
提升」的**同型纪律**）。该排除 SHALL **只**落在装配面的**注入步骤**：`MemoryStore.read` 的检索语义、排序、
预算与复用强化 SHALL **逐字不变**（`compaction.*` 条目对其他消费者 —— 抽取素材、检索素材、CLI 查询 ——
仍可见）；**无**专块承载的压缩产出（`source` 为 `context`，如压缩产出的事实 / 未决事项）SHALL **不受影响**。

装配 SHALL 另支持**可选的第二事实面排除面** `exclude_fact_tags`（按 `MemoryEntry.tags` **交集**匹配 ——
`tags` 与排除面有交集即排除；缺省空 ⇒ **不含排除**、装配结果与既往**逐字一致**）：**声明角色为素材**
（非注入面事实）的条目 SHALL NOT 进入「相关事实」注入面 —— 本轮**原始行动序列**
（`loop.steps.<trace_id>`，`tags` 含 `steps`，其声明角色为**抽取器素材**）SHALL NOT 被注入 prompt，
其信息 SHALL 由同轮轨迹条目（`loop.<trace_id>`）与（失败时）失败摘要（`loop.failure.<trace_id>`）承载；
同型的**标签**面排除纪律在 `memory` 侧已有先例（`_PRESERVE_TAGS`，见 `memory`「压实」），本条款是其在
**装配面**的对应。该排除同样 SHALL **只**落在装配面的**注入步骤**：`MemoryStore.read` 的检索语义、排序、
预算与复用强化 SHALL **逐字不变**（`loop.steps.*` 条目对其声明消费者 —— 关键事实**抽取器** —— 仍可见）；
**无** `steps` 标签的条目（`loop.<trace_id>` / `loop.failure.<trace_id>` / 压缩产物 / 关键事实）SHALL
**不受影响**。

#### Scenario: 按需加载与预算控制
- **GIVEN** 一个任务处于某阶段
- **WHEN** 上下文装配器构建上下文
- **THEN** 以任务目标为检索信号加载相关事实，token 控制在预算内

#### Scenario: 按任务召回事实
- **GIVEN** MemoryStore 含与当前任务相关的历史事实
- **WHEN** 上下文装配器以该任务构建上下文
- **THEN** 命中与任务相关的事实并注入 `facts`（检索 query 为 task，非阶段名）

#### Scenario: 会话维度透传
- **GIVEN** 一次携带会话标识的装配，且库中含他会话的事实
- **WHEN** 装配器构建上下文
- **THEN** 事实检索以该会话标识为会话维度，他会话事实**不进入** `facts`

#### Scenario: 压缩产物不进事实面
- **GIVEN** 会话已产出长期 / 中期摘要（`source` 为 `compaction`），其内容与当前任务检索命中；
  且库中同时含同一次压实产出的事实 / 未决条目（`source` 为 `context`）
- **WHEN** 装配器以排除面 `("compaction",)` 构建上下文
- **THEN** 长期 / 中期摘要**不出现**在 `facts` 中（其正文仍经「历史摘要」专块每轮注入 ⇒ 可见性不变、
  通道从二变一），而 `source` 为 `context` 的条目**仍在** `facts` 中；**未**传排除面时两者**都在**
  `facts` 中（与既往**逐字一致**）

#### Scenario: 原始步序素材不进事实面
- **GIVEN** 库中含本轮原始行动序列（`loop.steps.<trace_id>`，`tags` 含 `steps`）与同轮轨迹条目
  （`loop.<trace_id>`，`tags` 为 `loop` / `trajectory`），二者内容均与当前任务检索命中
- **WHEN** 装配器以排除面 `exclude_fact_tags=frozenset({"steps"})` 构建上下文
- **THEN** 原始行动序列**不出现**在 `facts` 中（其声明角色为抽取器素材，经 `MemoryStore.read` **仍可召回**
  ⇒ 抽取面不受影响），而同轮**轨迹**条目**仍在** `facts` 中；**未**传排除面时两者**都在** `facts` 中
  （与既往**逐字一致**）

#### Scenario: 超预算裁剪保留关键
- **GIVEN** 装配结果 token 超预算
- **WHEN** 预算管理器裁剪
- **THEN** 裁剪低相关度内容，优先保留宪章/未决事项/验收标准
### Requirement: 信息地图
系统 SHALL 把长文档转化为轻量化目录索引，模型按需跳转获取细节，不把全文塞入窗口。

#### Scenario: 地图定位与按需取详情
- **GIVEN** 一份千页级业务文档已建立信息地图
- **WHEN** 模型需要某章节细节
- **THEN** 先用地图定位指针，再 fetch 对应片段，而非加载全文

#### Scenario: 地图失效重建
- **GIVEN** 源文档内容变更导致地图索引失效
- **WHEN** 检测到 hash 不一致
- **THEN** 触发增量重建，期间降级为全文检索

#### Scenario: 重建失败二阶兜底
- **GIVEN** 地图索引失效且增量重建失败，全文检索同样不可用或超预算
- **WHEN** 模型仍需获取文档细节
- **THEN** 降级为对原始文档的受控分段线性扫描并逐段命中，任务不中断，不因索引不可用而失败
### Requirement: 上下文自动压实
系统 SHALL 对多轮关键信息自动摘要沉淀，写回记忆，避免重复传递冗余内容；沉淀产物 SHALL 为
`kind="semantic"` 的记忆条目，且 SHALL 标注来源出处（`tags` 携带被沉淀历史的原始 id），
使「沉淀」可追溯到原文而非匿名条目。压实产物 SHALL 以**本轮会话标识**归属写回（缺省空串 = 未归属，
归全局层），且产物条目的 id SHALL 携带**会话键**（`session_id` 非空取自身，否则取缺省键），
以免不同会话的压实产物互相覆盖。产物条目的 `trace_id` SHALL 亦携带**会话键**（`compaction.<key>`，`key = session_id or "default"`），与记忆侧其他压实 trace（会话摘要 / 关键事实 / 中期摘要）**同口径** ⇒ 回滚可按会话细化归因；SHALL NOT 使用**不区分会话**的常量 trace。本压实器为**启发式降级路径**（关键词识别结论/决策/未决
事项）：LLM 提炼统一由记忆压实通道承担，此处不新增模型调用。

压实**触发判据** SHALL 为：本轮**工具步数**达到 `loop.compact_steps`（缺省 `6`）**或** token 用量
达到 token 预算。工具步数 SHALL 是**本轮内已记账的工具动作步数**（`ctx.rounds` —— 每轮自 `0` 起算，
**非**对话轮数），故步数阈值 SHALL 小于 `loop.max_rounds` 才可能在本轮内触发。压实 SHALL
**每轮至多触发一次**：本轮首次满足判据后 SHALL NOT 重复压实（避免同轮多次模型调用）。

#### Scenario: 触发压实并沉淀
- **GIVEN** 工具步数或 token 达到阈值
- **WHEN** 压实器运行
- **THEN** 关键结论/决策/未决事项被摘要沉淀，写回 MemoryStore，产物 `kind="semantic"` 且
  `tags` 携带原始 id 出处

#### Scenario: 压实产物归属会话且不与他会话同名
- **GIVEN** 某会话（标识非空）的多轮消息触发压实
- **WHEN** 沉淀写回
- **THEN** 产物条目的 `session_id` 等于该会话标识，且其 id 含该会话键（与他会话产物不同名、不互相覆盖）

#### Scenario: 未归属压实归缺省键
- **GIVEN** 一次未携带会话标识的压实
- **WHEN** 沉淀写回
- **THEN** 产物 `session_id` 为空串（全局层），id 含缺省会话键

#### Scenario: 压实不丢关键信息
- **GIVEN** 压实产物丢失关键信息
- **WHEN** 校验发现关键信息缺失
- **THEN** 不替换原文，返回 `COMPACTION_LOSSY`

#### Scenario: 工具步数阈值可在本轮内触发且每轮至多一次
- **GIVEN** 步数阈值小于 `loop.max_rounds`（如阈值 `2`、上限 `5`）且本轮持续产生非终止工具动作
- **WHEN** 本轮执行
- **THEN** 压实**确实被触发**（不再等到终止步才触发，阈值维度不是死的），且**恰触发一次**
  （后续步虽仍满足 `步数 ≥ 阈值`，SHALL NOT 重复压实）

#### Scenario: 步数阈值达上限时不再重复压实
- **GIVEN** 步数阈值等于 `loop.max_rounds`（如二者皆 `10`）
- **WHEN** 本轮执行至终止步
- **THEN** 压实至多在终止步触发一次，且本轮已因 `LOOP_LIMIT_EXCEEDED` 终止 —— 触发与终止同刻，
  该阈值**不能**让压实提前于终止发生

#### Scenario: 压实产物 trace 携带会话键
- **GIVEN** 某会话（标识非空）的多轮消息触发上下文压实
- **WHEN** 沉淀写回
- **THEN** 产物条目的 `trace_id` 为 `compaction.<该会话键>`（与其他压实 trace 同口径），按该 trace 回滚即整批撤销本会话压实产物
### Requirement: 宪法约束注入
系统 SHALL 将 Core Profile 的「宪法与全局规则」分区作为 constitution:v1 coeffect 注入上下文，作为必保约束参与执行。

#### Scenario: 宪法分区注入
- **GIVEN** 全局 Core.md 含「宪法与全局规则」分区
- **WHEN** 上下文装配器构建上下文
- **THEN** 该分区内容作为 constitution:v1 coeffect 注入，并作为必保约束保留
### Requirement: 项目信息注入
系统 SHALL 在载入项目时由 ContextEngine 按 cwd 向上查找项目级 Core.md，将其内容作为项目信息注入上下文窗口。

#### Scenario: 项目信息注入
- **GIVEN** 当前工作目录位于某项目内，且项目根存在 Core.md
- **WHEN** ContextEngine 装配项目上下文
- **THEN** 命中的项目级 Core.md 内容注入上下文，作为项目信息参与任务

#### Scenario: 未命中降级
- **GIVEN** 从 cwd 向上至文件系统根均未发现项目级 Core.md
- **WHEN** ContextEngine 查找失败
- **THEN** 静默降级，不注入项目信息，不影响任务执行
### Requirement: 三层窗口比例分配
系统 SHALL 把会话历史回灌的**分层策略**收敛为**确定性纯函数**（零 I/O、零模型调用）：给定
`loop.history_turns`（三层轮数总量）与历史预算（`token_budget // 2`），算出短层轮数、中层轮数、
短层 token 上界与中层摘要字符上界。份额 SHALL 为**固定配比**（短 0.5 / 中 0.3 / 长 0.2），
且 SHALL 为**模块常量**、不新增配置键（本**配额分配面**不新增配置键 —— 压实**触发**阈值是另一面，
自 change 0182 起可经 `loop.compact_steps` 配置）；`loop.history_turns` SHALL 仍是
唯一用户可调旋钮（三层配比随之等比缩放）。

该函数 SHALL 保证：轮数或预算非正 ⇒ 全零（关闭回灌）；**非分层**（冷会话 / 未注入摘要器）⇒
「短层 = 全部 `history_turns` 轮 + 全部预算、中层零」，与既有「双重上界」**逐字等价**；分层时
短层轮数 SHALL 不低于 `1`、短层与中层轮数之和 SHALL NOT 超过总量、各配额随总量**单调不减**。
LLM 压缩 SHALL 仍统一由**记忆压实通道**承担，本分配**不新增模型调用点**。

#### Scenario: 非分层等价既有双重上界

- **GIVEN** 非分层（冷会话 / 未注入摘要器）
- **WHEN** 计算三层配额
- **THEN** 短层轮数 = `loop.history_turns`、短层 token 上界 = 历史预算、中层零配额 —— 与既有
  「双重上界」逐字等价

#### Scenario: 分层按固定份额切分

- **GIVEN** 分层且 `loop.history_turns` 与历史预算均大于 `0`
- **WHEN** 计算三层配额
- **THEN** 短层轮数 ≈ 总量 × 0.5、中层轮数 ≈ 总量 × 0.3、短层 token 上界 = 预算 × 0.5，
  长层以会话整体摘要形式覆盖更早全部内容（不占轮数 / 字符配额）

#### Scenario: 关闭回灌的零守卫

- **GIVEN** `loop.history_turns` 或历史预算非正
- **WHEN** 计算三层配额
- **THEN** 全部配额为零（不读不注入）

#### Scenario: 短层恒不低于一轮且短中不超总量

- **GIVEN** 分层且总量为正
- **WHEN** 计算三层配额
- **THEN** 短层轮数 ≥ `1`，且短层轮数 + 中层轮数 ≤ 总量（无重叠配额）

#### Scenario: 配额随总量单调

- **GIVEN** 分层，总量递增
- **WHEN** 逐值计算三层配额
- **THEN** 短层轮数与中层轮数**单调不减**
