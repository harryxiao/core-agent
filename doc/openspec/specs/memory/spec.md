# Memory Specification

## Purpose
记忆系统实现"记忆即光谱"——从 L0 元策略到 L4 原始会话的多层级记忆，热/温/冷三档检索温度，承载"无行动不记忆"的沉淀原则。

## Requirements

### Requirement: 分层记忆模型
系统 SHALL 按 L0（元策略）→L1（索引）→L2（事实）→L3（SOP/技能）→L4（原始会话）分层存储，层间由轻量索引连通。

#### Scenario: 分层写入
- **GIVEN** 一条经验需要沉淀
- **WHEN** 记忆系统判断其层级
- **THEN** 写入对应层级，并在 L1 建立最小索引条目

#### Scenario: 跨层检索
- **GIVEN** 一个查询命中 L1 索引
- **WHEN** 检索器解析索引
- **THEN** 按热度路由到 L2/L3/L4 取详情，而非全库扫描

### Requirement: 温度分层检索
系统 SHALL 提供热/温/冷三档检索，热数据常驻内存，冷数据按需加载；检索结果 SHALL 按
**多因子得分**排序——语义相似 × 层结构权重（加性）再经 新鲜度衰减、复用频次
（`1 + log1p(reuse_count)`）、主观重要度（`1 + importance`）**乘性调制**；条目 SHALL 携带
`kind`（episodic / semantic）与 `importance` 元数据，供下沉固化聚合。语义相似 SHALL 经
**可注入 embedder**（缺省词法、可远端向量化）计算，并对检索 query 与未变条目向量做**缓存**
（每次检索 query 至多向量化一次）。

#### Scenario: 热数据即时返回
- **GIVEN** 一个高频使用的 SOP
- **WHEN** 检索该 SOP
- **THEN** 从热区即时返回，无磁盘 IO

#### Scenario: 冷数据按需加载
- **GIVEN** 一个仅存在于 L4 的历史会话
- **WHEN** 检索命中冷数据
- **THEN** 异步加载并按预算注入上下文

#### Scenario: 检索失败降级
- **GIVEN** 检索主路径（热区/索引）发生异常或返回空结果
- **WHEN** 检索失败或未命中
- **THEN** 降级到全库扫描或返回明确未命中结果，不阻断 Agent 主流程，并记录失败原因

#### Scenario: 多因子排序
- **GIVEN** 两条候选记忆与查询的语义相似度相同
- **WHEN** 检索器排序候选
- **THEN** `importance` 更高或 `reuse_count` 更多的条目排在更前；命中条目的 `reuse_count` 递增

#### Scenario: 语义相似经 embedder
- **GIVEN** 注入了 embedder
- **WHEN** 检索一个语义相近但词面不重叠的查询
- **THEN** 以向量相似度参与排序，且本次检索对 query 只向量化一次、未变条目复用缓存向量

#### Scenario: embedder 不可用降级词法
- **GIVEN** 未注入 embedder，或 embedder 调用抛错
- **WHEN** 检索器计算相似度
- **THEN** 降级为词法相似，检索不中断

### Requirement: 无行动不记忆
系统 SHALL 只沉淀"行动与结果"产生的经验，不记录未经验证的空想。

#### Scenario: 无行动不写入
- **GIVEN** 模型产出一条未经执行验证的主张
- **WHEN** 尝试写入长期记忆
- **THEN** 被拒绝，需先有行动结果作为证据

### Requirement: 记忆压实
系统 SHALL 定期压实记忆，合并重复条目、归档过期会话、保持 L1 索引最小；并 SHALL 在注入摘要器
（`summarizer`）时，按会话（`session_id`）聚合 episodic 条目、提炼为**一条** `kind="semantic"`
摘要条目（其 `tags` 携带原始条目 id 以追溯原文，`source` 为短标签 `compaction`，`trace_id` 为
`compaction.<session_id>`），并将被聚合的原始条目迁至 L4 归档层（不删除）。未注入摘要器时
SHALL 不做摘要提炼：不写摘要条目、不改动原始条目层级。压实产生的写入与层级迁移 SHALL 全部
可撤销（记入效应追踪，按 `trace_id` 回滚即逆转）。

#### Scenario: 索引最小化
- **GIVEN** L1 索引膨胀
- **WHEN** 记忆清理 SOP 运行
- **THEN** 合并重复条目，索引回归最小集合

#### Scenario: 摘要提炼并归档
- **GIVEN** 同一会话下有多条 episodic 条目，且记忆存储注入了摘要器
- **WHEN** 压实运行
- **THEN** 产出 `kind="semantic"` 的摘要条目（`tags` 携带原始条目 id），原始条目迁至 L4
  归档层且不被删除（层级由 L2 变为 L4，检索优先级随之降低，仍可审计追溯）

#### Scenario: 未注入摘要器时降级
- **GIVEN** 记忆存储未注入摘要器
- **WHEN** 压实运行
- **THEN** 不产出摘要条目，原始条目层级保持不变（仅返回评分决策）

#### Scenario: 压实可撤销
- **GIVEN** 已按会话执行摘要压实
- **WHEN** 按该次压实的 `trace_id` 回滚效应
- **THEN** 被聚合的原始条目迁回原层，摘要条目被移除

#### Scenario: 压实失败降级
- **GIVEN** 记忆压实过程中发生写入失败或中途异常
- **WHEN** 压实流程出错
- **THEN** 记忆层不吞异常（向上传播，不写半成品），触发点捕获并经观测通道记录失败原因，
  该会话原始条目保持不变、下次压实可重试，不丢失既有记忆

#### Scenario: 并发压实一致性
- **GIVEN** 记忆压实与写入/检索并发发生
- **WHEN** 压实流程运行时存在并发读写
- **THEN** 通过加锁/事务保证压实不产生数据竞争，并发读写等待或走一致性快照，不丢失条目

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

### Requirement: Core Profile 人格注入
系统 SHALL 将 Core Profile 的「人格」分区作为 L0 元策略写入记忆，承载 Agent 的行为特色预设。

#### Scenario: 人格分区写入 L0
- **GIVEN** 全局 Core.md 含「人格」分区
- **WHEN** Agent 启动读取 Core Profile
- **THEN** 该分区内容作为 L0 元策略写入记忆，塑造 Agent 行为特色
