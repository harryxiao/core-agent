# Spec Delta — context（0310 上下文淘汰的情景检查点）

## ADDED Requirements

### Requirement: 上下文淘汰的情景检查点

系统 SHALL 在**上下文淘汰**发生时把被淘汰的转录行回写为一条 `context_checkpoint` 情景记录，
使「被淘汰」不等于「直接消失」（SDD §4.5 / §6.7 Tier 3）。

**淘汰**的定义：滑出保留窗口（短带 ∪ 中带）的转录行。保留窗口 SHALL 与三层滑窗切分**同一
口径**（短带 token 截断、孤儿 assistant 行丢弃、中带不截断），边界由一次转录读取给出。

**写入时机**：每轮 `perceive`，在读取历史之后、追加本轮 user 行之前。故本轮 SHALL NOT 被
判为淘汰。

**记录形状**：

- 层 / 类型 / 来源：`L2`、`episodic`、`source="context"`；
- id 与 trace_id：`context_checkpoint.<session 或 "default">.<seqTo>`（确定性、可回滚）；
- `tags` SHALL 含 `context_checkpoint`、`seq_from:<n>`、`seq_to:<m>`，并对每个工件引用追加
  `artifact:<path>`；
- `content` SHALL 为**确定性抽取式摘要**（头部含 `seq` 区间与行数，逐行 `role: content`），
  写前脱敏、总长有界（≤ 800 字符）、单行截断（≤ 120 字符）；原文 SHALL NOT 复制进记录
  （转录日志仍是原文真源）。

**日志水位**：`(logId, seqFrom, seqTo) = (session_id, 区间首行下标, 区间末行下标)`，下标为
该会话转录的**行序**（派生值，不新增落盘列）。系统 SHALL 只写**新增**淘汰区间
`[watermark+1, retained_from-1]`；已写水位取本会话既有 `context_checkpoint` 条目的最大
`seq_to`。水位 SHALL 跨层跨状态单调（墓碑 / 归档 / forgotten 的检查点仍计入）。

**工件引用**：转录行 SHALL 支持可选 `artifacts` 列（本轮 `file_write` / `file_patch` 的
`path`，去重、每轮有界）；检查点 SHALL 聚合被淘汰区间内全部行的工件引用（去重、总计 ≤ 16）。
无引用 ⇒ SHALL NOT 伪造 `artifact:` 标签。

**门控与失败隔离**：关闭开关、未注入转录或记忆、会话为空、`history_turns <= 0`（无保留窗口）
⇒ SHALL 零写入、零副作用。转录读 / 水位读 / 记忆写任一失败 ⇒ SHALL 只告警并跳过本次检查点，
SHALL NOT 阻断本轮。

#### Scenario: 淘汰即回写检查点

- **GIVEN** 某会话已有 3 轮转录，`history_turns=1`（保留窗口只含末轮），检查点开关开启
- **WHEN** 处理下一轮
- **THEN** 记忆中存在一条 `context_checkpoint` 情景条目，`tags` 含 `seq_from:0`、
  `seq_to:<淘汰区间末行下标>`，`content` 含 `seq 0-<末行下标>` 与各行摘要

#### Scenario: 只写新增区间

- **GIVEN** 已写检查点覆盖 `seq 0-3`，本轮保留窗口上移使淘汰区间扩到 `seq 0-7`
- **WHEN** 处理本轮
- **THEN** 新检查点的 `seq_from` 为 `4`（不重写 0–3），`seq_to` 为 `7`

#### Scenario: 无新增淘汰 ⇒ 零写入

- **GIVEN** 当前淘汰区间与已写水位相同
- **WHEN** 再次处理一轮
- **THEN** 不新增任何记忆条目、不产生写入效应

#### Scenario: 工件引用随行聚合

- **GIVEN** 被淘汰区间内某轮的 assistant 行登记了 `artifacts=["a.py", "b.py"]`
- **WHEN** 写检查点
- **THEN** `tags` 含 `artifact:a.py` 与 `artifact:b.py`；无工件引用的区间不含任何
  `artifact:` 标签

#### Scenario: 摘要脱敏且有界

- **GIVEN** 被淘汰行的正文含密钥形态文本且总长远超上界
- **WHEN** 写检查点
- **THEN** 记录正文中密钥形态被脱敏，且长度 ≤ 800 字符、单行 ≤ 120 字符，头部水位行保留

#### Scenario: 关闭开关 / 无保留窗口 ⇒ 零写入

- **GIVEN** 检查点开关为 `false`，或 `history_turns=0`
- **WHEN** 处理任意轮次
- **THEN** 不写任何 `context_checkpoint`，记忆与转录均无新写入

#### Scenario: 回写失败不阻断本轮

- **GIVEN** 转录读取或记忆写入抛错
- **WHEN** 处理该轮
- **THEN** 只发出告警，本轮正常完成，不写检查点
