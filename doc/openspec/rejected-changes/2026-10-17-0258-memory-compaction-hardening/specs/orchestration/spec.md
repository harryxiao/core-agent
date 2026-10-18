# orchestration — 检查点损坏降级留痕（change 0258 提案）

## ADDED Requirements

### Requirement: 检查点损坏降级留痕

`FileCheckpoint.load` 遇到损坏 JSON SHALL NOT 抛异常：SHALL 将损坏文件重命名为
`<path>.corrupt-<ts>` 留痕，SHALL 以 `checkpoint_corrupted` 记录（日志 / 警告，SHALL NOT
回显文件正文），并返回 `None` 降级为从头执行。写入 SHALL 保持既有「文件型检查点实现」
Requirement 的同目录临时文件 + `os.replace` 原子替换语义（逐字不变）；自定义
`CheckpointFn` 的注入面与原子性保证范围 SHALL 不变。

#### Scenario: 损坏 JSON 降级为从头执行
- **GIVEN** 检查点文件内容为半截 JSON
- **WHEN** `FileCheckpoint.load` 读取
- **THEN** 返回 `None` 且不抛异常，损坏文件被重命名为 `.corrupt-<ts>` 并留痕
  `checkpoint_corrupted`（不含文件正文）

#### Scenario: 有效检查点读取路径不变
- **GIVEN** 检查点文件为完整 JSON 且任务标识匹配
- **WHEN** `FileCheckpoint.load(task_id)`
- **THEN** 返回既有 payload 结构，字段与改造前逐字一致
