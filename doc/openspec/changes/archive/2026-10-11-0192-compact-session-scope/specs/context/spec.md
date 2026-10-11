# Context Engineering Specification Delta — 压实 trace 会话键（change 0192）

## MODIFIED Requirements

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
