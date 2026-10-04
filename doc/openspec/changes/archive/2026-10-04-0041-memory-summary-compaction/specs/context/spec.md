# Context Specification Delta

## MODIFIED Requirements

### Requirement: 上下文自动压实
系统 SHALL 对多轮关键信息自动摘要沉淀，写回记忆，避免重复传递冗余内容；沉淀产物 SHALL 为
`kind="semantic"` 的记忆条目，且 SHALL 标注来源出处（`tags` 携带被沉淀历史的原始 id），
使「沉淀」可追溯到原文而非匿名条目。本压实器为**启发式降级路径**（关键词识别结论/决策/未决
事项）：LLM 提炼统一由记忆压实通道承担，此处不新增模型调用。

#### Scenario: 触发压实并沉淀
- **GIVEN** 轮数或 token 达到阈值
- **WHEN** 压实器运行
- **THEN** 关键结论/决策/未决事项被摘要沉淀，写回 MemoryStore，产物 `kind="semantic"` 且
  `tags` 携带原始 id 出处

#### Scenario: 压实不丢关键信息
- **GIVEN** 压实产物丢失关键信息
- **WHEN** 校验发现关键信息缺失
- **THEN** 不替换原文，返回 `COMPACTION_LOSSY`
