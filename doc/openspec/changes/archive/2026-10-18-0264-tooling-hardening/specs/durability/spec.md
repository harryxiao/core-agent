## ADDED Requirements

### Requirement: 检查点加载损坏行告警且不阻断

检查点存储从 JSONL 加载时 SHALL 容忍**局部损坏**：无法解析的行（坏 JSON）与**结构不符**的行
（缺 `checkpoint` / `snapshot` 键或必需字段，导致构造失败）SHALL 被跳过并累计，SHALL NOT 中断
其余合法行的加载。加载结束后若有跳过项，系统 SHALL 发出**一次**告警（`UserWarning`），
内容 SHALL 只含**跳过条数与文件名**，SHALL NOT 回显行内容（可能含任务正文 / 记忆 / 密钥）。

#### Scenario: 坏 JSON 行告警且不阻断

- **GIVEN** 检查点 JSONL 文件含一行坏 JSON 与若干合法行
- **WHEN** 构造 `CheckpointStore` 加载该文件
- **THEN** 合法行全部可读，并发出一次 `UserWarning`，消息含跳过条数与文件名、不含坏行内容

#### Scenario: 结构不符行不中断加载

- **GIVEN** 检查点 JSONL 文件含一行合法 JSON 但缺少 `checkpoint` / `snapshot` 结构
- **WHEN** 加载该文件
- **THEN** 该行被跳过并计入告警，其余检查点照常加载（不抛异常）

#### Scenario: 无损坏行不告警

- **GIVEN** 检查点 JSONL 文件全部为合法结构
- **WHEN** 加载该文件
- **THEN** 不发出任何告警
