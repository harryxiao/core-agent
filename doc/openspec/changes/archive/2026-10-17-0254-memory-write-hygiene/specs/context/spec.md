## ADDED Requirements

### Requirement: 压实产物的脱敏、有界与陈旧清理

上下文压实产物（结论 / 决策 / 未决事项）SHALL 在写入 MemoryStore **前**逐条脱敏：命中密钥形态
的子串 SHALL 经同一份密钥启发式（`redact_secrets`）替换为 `<redacted>`。每条产物的正文 SHALL
**有界**（单条字符上界；脱敏后截断），SHALL NOT 因整段工具输出或无界消息而膨胀。关键词分类
（结论 / 决策 / 未决）SHALL 仍基于**原始消息**，口径逐字不变；`COMPACTION_LOSSY` 判据 SHALL
仍以脱敏后的三类非空性为准。

产物按会话键与序号写入（`compaction.fact.<key>.<i>` / `compaction.open.<key>.<i>`）。当本轮
某类产物条数少于上一轮同会话同类条目时，序号超出本轮条数的**陈旧条目** SHALL 被删除，SHALL
NOT 以旧序号残留在 L2。删除 SHALL 走既有可撤销写路径（记 `memory.delete` 效应）。删除失败
SHALL NOT 阻断本轮其余产物写回。

#### Scenario: 压实产物不含密钥明文
- **GIVEN** 本轮消息含密钥形态（如 `sk-…`）且命中结论 / 决策 / 未决关键词
- **WHEN** 压实产物写回
- **THEN** 落库条目正文**不含**该明文，命中段为 `<redacted>`；同轮未含密钥的产物**逐字不变**

#### Scenario: 单条压实产物有界
- **GIVEN** 一条命中关键词的消息正文远超单条上界
- **WHEN** 压实产物写回
- **THEN** 落库条目正文长度不超过单条字符上界（脱敏后截断）

#### Scenario: 陈旧序号被清理
- **GIVEN** 同一会话上一轮写入了 N 条压实产物，本轮同类产物只有 M 条（M < N）
- **WHEN** 本轮产物写回
- **THEN** 序号 M..N-1 的旧条目被删除，会话内该类产物**只保留本轮 M 条**
