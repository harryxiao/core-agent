# Beast-Mode Specification Delta

## ADDED Requirements

### Requirement: Task Result Visibility

系统 SHALL 使神兽**已完成的**任务结果可见：召唤交接返回的 `LoopResult` SHALL 由会话**持有**并经**只读查询面**
（`BeastSession.result_summary()` ⇒ 结构化字段：神兽 id / 是否有结果 / 结果正文 / 成败）取用；`summon` CLI
SHALL 在召唤成功后**呈现其结果正文与成败**。结果可见性 SHALL **不依赖主 loop 检索** —— 神兽记忆命名空间与
分区封存（`source=beast.*` 不被主 loop read 命中）**逐字不动**，结果 SHALL NOT 落 L2、SHALL NOT 改变记忆语义。
无结果时（会话未执行过任务）查询面 SHALL 明确报「无结果」，SHALL NOT 编造正文。

#### Scenario: 召唤后结果可见
- **GIVEN** 神兽召唤经 handoff 返回 `LoopResult`
- **WHEN** 查询该会话（`result_summary()`）或经 `summon` CLI
- **THEN** 返回结构化结果（神兽 id / 是否有结果 / 结果正文 / 成败），数据源为会话持有的 `last_result`

#### Scenario: 封存语义不受影响
- **GIVEN** 神兽会话已回归 `RECALLED`（记忆分区封存生效）
- **WHEN** 查询结果
- **THEN** 结果仅经会话查询面可见，`source=beast.*` SHALL 仍**不被主 loop read 命中**（不落 L2、不失封存）

#### Scenario: 无结果不谎报
- **GIVEN** 会话尚未执行过任务（`last_result` 为空）
- **WHEN** 查询结果 / `summon` CLI 呈现
- **THEN** 明确「无结果」（`has_result=false`），SHALL NOT 编造正文
