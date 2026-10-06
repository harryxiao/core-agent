# Context Specification Delta

## MODIFIED Requirements

### Requirement: 动态上下文构建

系统 SHALL 以**任务目标**为检索信号按需加载上下文（L2 事实检索以 task 为 query；stage 为装配阶段标注、
暂不参与事实选择），控制注入 token 上界，超预算裁剪低相关度内容。装配 SHALL 另接受可选的**调用方会话标识**
`session_id` 并**透传**至 L2 事实检索，作为该次检索的会话维度；标识缺省空串时，检索语义与既往**逐字一致**。

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

#### Scenario: 超预算裁剪保留关键

- **GIVEN** 装配结果 token 超预算
- **WHEN** 预算管理器裁剪
- **THEN** 裁剪低相关度内容，优先保留宪章/未决事项/验收标准

### Requirement: 上下文自动压实

系统 SHALL 对多轮关键信息自动摘要沉淀，写回记忆，避免重复传递冗余内容；沉淀产物 SHALL 为
`kind="semantic"` 的记忆条目，且 SHALL 标注来源出处（`tags` 携带被沉淀历史的原始 id），
使「沉淀」可追溯到原文而非匿名条目。压实产物 SHALL 以**本轮会话标识**归属写回（缺省空串 = 未归属，
归全局层），且产物条目的 id SHALL 携带**会话键**（`session_id` 非空取自身，否则取缺省键），
以免不同会话的压实产物互相覆盖。本压实器为**启发式降级路径**（关键词识别结论/决策/未决
事项）：LLM 提炼统一由记忆压实通道承担，此处不新增模型调用。

#### Scenario: 触发压实并沉淀

- **GIVEN** 轮数或 token 达到阈值
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
