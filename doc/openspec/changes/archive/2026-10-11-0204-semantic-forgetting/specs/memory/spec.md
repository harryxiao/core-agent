# Memory Specification Delta — 语义遗忘面（change 0204）

## MODIFIED Requirements

### Requirement: 记忆遗忘（forgetting）

系统 SHALL 按衰减评分（新鲜度 × 复用频次 × 重要度）识别低价值记忆并**归档**：评分低于阈值的
**L2 episodic** 条目 SHALL 迁移到 L4 归档层（**不物理删除**、`audit` 可见、检索降权），且每条
迁移 SHALL 记录可逆效应（按 trace 回滚即迁回原层）。**新鲜度衰减 SHALL 被复用信号延缓**：
条目的 freshness 衰减 SHALL 以 `freshness ** (1 / (1 + log1p(reuse_count)))` 调制——`reuse_count`
为 0 时该调制 SHALL 退化为现状（零回归锚点），复用越多衰减越缓（检索命中反哺遗忘曲线）。
**摘要类** semantic 条目（`source ∈ {compaction, context}`）、L0 元策略与 L3 技能 SHALL 不受遗忘
影响。**派生事实类** semantic 条目（`source ∈ {extraction, relation}`）SHALL **仅在**开关
`memory.semantic_forgetting` 显式开启时参与衰减归档——该开关缺省**关闭**，关闭时派生事实条目与
摘要类条目**同**不受影响（逐字回归锚点）；开启时派生事实条目的归档判据、归档去向与可撤销性
SHALL 与 episodic **同一**（同一衰减评分、同一阈值、同一 L4 归档、同一 `forgetting.<id>` 效应）。
时间戳未知（`ts<=0`）的条目 SHALL 不被惩罚。遗忘 SHALL NOT 中断 Agent 主流程。遗忘 SHALL 由
**维护节拍**驱动——循环收尾按维护间隔触发，或由显式维护入口一次性触发——而非仅依赖压实旁路；
节拍只决定"何时跑"，不改上述判据、归档去向与可撤销性。

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
- **GIVEN** L2 存在 **`source ∈ {compaction, context}` 的摘要类** `kind="semantic"` 条目，
  L0 存在人格条目，L3 存在技能条目
- **WHEN** 遗忘运行
- **THEN** 三者层级均不变（遗忘只作用于 L2 episodic 与——开关开启时的——派生事实语义条目）

#### Scenario: 遗忘可撤销
- **GIVEN** 某条目已被遗忘归档
- **WHEN** 按该条目的遗忘 trace 回滚效应
- **THEN** 条目迁回 L2 原层

#### Scenario: 开关开启时派生事实参与遗忘
- **GIVEN** 开关 `memory.semantic_forgetting` 已开启，L2 存在陈旧且从未复用的
  `source="extraction"`（或 `source="relation"`）`kind="semantic"` 条目
- **WHEN** 遗忘运行
- **THEN** 该条目迁至 L4 归档层（判据与去向同 episodic），`audit` 仍可见，且返回其撤销句柄
  `forgetting.<id>`

#### Scenario: 缺省关时派生事实不受影响
- **GIVEN** 开关 `memory.semantic_forgetting` **缺省关闭**，L2 存在陈旧且从未复用的
  `source="extraction"` `kind="semantic"` 条目
- **WHEN** 遗忘运行
- **THEN** 该条目层级保持不变（与引入该开关前**逐字一致**）

#### Scenario: 开关开启时摘要类与元策略仍不受影响
- **GIVEN** 开关 `memory.semantic_forgetting` 已开启，L2 存在陈旧且从未复用的
  `source="compaction"` 与 `source="context"` 的 `kind="semantic"` 条目，L0 存在人格条目，
  L3 存在技能条目
- **WHEN** 遗忘运行
- **THEN** 四者层级均不变（开关只放行派生事实类，摘要类与 L0/L3 恒豁免）
