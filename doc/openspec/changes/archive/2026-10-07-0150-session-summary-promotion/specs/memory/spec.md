## MODIFIED Requirements

### Requirement: 记忆压实
系统 SHALL 定期压实记忆，合并重复条目、归档过期会话、保持 L1 索引最小；并 SHALL 在注入摘要器
（`summarizer`）时，按会话（`session_id`）聚合 episodic 条目、提炼为**一条** `kind="semantic"`
摘要条目（其 `tags` 携带原始条目 id 以追溯原文，`source` 为短标签 `compaction`，`trace_id` 为
`compaction.<session_id>`），并将被聚合的原始条目迁至 L4 归档层（不删除）。未注入摘要器时
SHALL 不做摘要提炼：不写摘要条目、不改动原始条目层级。压实产生的写入与层级迁移 SHALL 全部
可撤销（记入效应追踪，按 `trace_id` 回滚即逆转）。

压实的**聚合范围** SHALL 可**按会话收窄**：`compact` SHALL 接受可选 `session_id` —— **非空**时
SHALL 只聚合**该会话**的 L2 episodic 条目（含其重要度打分写回），SHALL NOT 跨会话提炼或迁移
他会话条目；**空串**时 SHALL 保持**全量**语义（逐字与既有行为一致，供循环内节拍压实使用）。

摘要 SHALL 为**滚动合并**而非覆盖重写：当该会话已存在摘要条目时，系统 SHALL 把**既有摘要内容**
与本次新增 episodic 条目**一并**投喂摘要器，产出**融合既有结论与新增事实**的摘要；系统 SHALL NOT
丢弃既有摘要中未被新摘要显式合并的内容。摘要条目的 `id` 与「每会话至多一条、不增长」口径 SHALL
保持不变（滚动的是**内容**，不是条目数）。

`MemoryStore` SHALL 提供**只读**访问器 `summary_for(session_id) -> MemoryEntry | None`：按 `session_id`
取回该会话既有摘要条目（`id == f"compaction.summary.{session_id or 'default'}"`，口径与摘要写入**同一**）；
无则返回 `None`。该访问器 SHALL NOT 产生任何写入或效应记录，SHALL NOT 变更条目的
`reuse_count` / `importance` / `updated_at`。

#### Scenario: 索引最小化
- **GIVEN** L1 索引膨胀
- **WHEN** 记忆清理 SOP 运行
- **THEN** 合并重复条目，索引回归最小集合

#### Scenario: 摘要提炼并归档
- **GIVEN** 同一会话下有多条 episodic 条目，且记忆存储注入了摘要器
- **WHEN** 压实运行
- **THEN** 产出 `kind="semantic"` 的摘要条目（`tags` 携带原始条目 id），原始条目迁至 L4
  归档层且不被删除（层级由 L2 变为 L4，检索优先级随之降低，仍可审计追溯）

#### Scenario: 滚动合并既有摘要（不丢失）
- **GIVEN** 同一会话已存在一条 semantic 摘要条目，其后又新增若干 episodic 条目
- **WHEN** 再次压实该会话
- **THEN** 投喂摘要器的材料 SHALL **同时**含既有摘要内容与新增条目；产出的摘要条目 SHALL 保留
  既有摘要中的结论（既有内容不被静默丢弃），且仍为**该会话唯一**的摘要条目（id 不变、条目不增长）

#### Scenario: 压实按会话收窄，不触他会话
- **GIVEN** 会话 A 与会话 B 各有若干 L2 episodic 条目，且记忆存储注入了摘要器
- **WHEN** 以 `session_id="A"` 触发压实
- **THEN** 只产出 A 的摘要条目、只迁移 A 的原始条目（B 的条目**逐字不变**、层级与重要度都不动）

#### Scenario: 按会话读取既有摘要（只读）
- **GIVEN** 某会话已完成摘要压实
- **WHEN** `summary_for(<该会话>)`
- **THEN** 返回该会话的摘要条目；`summary_for(<他会话>)` ⇒ `None`；且调用前后
  `audit()` 快照与效应追踪面**逐字不变**（只读，无写入、无效应、不动 `reuse_count` / `importance` / `updated_at`）

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
