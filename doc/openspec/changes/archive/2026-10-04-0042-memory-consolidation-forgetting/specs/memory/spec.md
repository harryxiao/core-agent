# Memory Specification Delta

## ADDED Requirements

### Requirement: 记忆固化（consolidation）
系统 SHALL 对会话内 episodic 条目**自动打分**并据此**门控固化**：注入 scorer（judgment `score`
原语，JEV 优先、低置信/不可达回退主 LLM）时，SHALL 将分值写回条目的 `importance`（写入可撤销，
打分失败保留原值而非写零）；且 SHALL 仅在会话分值达阈值的会话上执行语义提炼（产出
`kind="semantic"` 条目、原条目迁 L4 归档，口径同「记忆压实」），低价值会话 SHALL 保留 episodic
原状。未注入 scorer、或本轮未取得任何分值（打分失败 / 超出打分上界）时 SHALL 不设价值门槛
（不因缺少决策能力或决策服务抖动而停止固化）。

#### Scenario: 重要度自动写回
- **GIVEN** 注入了 scorer 且存在 L2 episodic 条目
- **WHEN** 固化运行
- **THEN** 条目 `importance` 被写为分值（[0,1]），且该写入可撤销（回滚即恢复旧值）

#### Scenario: 价值门控生效
- **GIVEN** 注入了 scorer，某会话分值低于阈值、另一会话达阈值
- **WHEN** 固化运行
- **THEN** 达标会话提炼为 semantic 条目并归档原条目；低价值会话保持 episodic 原层不动

#### Scenario: 打分失败不降级为零重要度
- **GIVEN** scorer 调用抛错或回退失败
- **WHEN** 固化尝试打分
- **THEN** 该条目 `importance` 保持原值（不被写为 0），该会话不因缺分值而被门槛拦下，
  固化流程不中断

### Requirement: 记忆遗忘（forgetting）
系统 SHALL 按衰减评分（新鲜度 × 复用频次 × 重要度）识别低价值记忆并**归档**：评分低于阈值的
**L2 episodic** 条目 SHALL 迁移到 L4 归档层（**不物理删除**、`audit` 可见、检索降权），且每条
迁移 SHALL 记录可逆效应（按 trace 回滚即迁回原层）。semantic 条目、L0 元策略与 L3 技能 SHALL
不受遗忘影响；时间戳未知（`ts<=0`）的条目 SHALL 不被惩罚。遗忘 SHALL NOT 中断 Agent 主流程。

#### Scenario: 低分条目归档
- **GIVEN** 一条陈旧且从未复用的 L2 episodic 条目
- **WHEN** 遗忘运行
- **THEN** 该条目迁至 L4 归档层，`audit` 仍可见，且返回其撤销句柄

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
